# TikTok → Facebook Auto-Poster Design Specification

**Date**: 2026-08-06
**Status**: Approved (MVP)
**Supersedes**: `2026-08-05-tiktok-facebook-auto-poster-design.md`

## 1. Overview

Tool tự động detect video mới từ hàng loạt kênh TikTok (người dùng cung cấp), tải video về, và
đăng lên các Facebook Page tương ứng (người dùng cung cấp). Sử dụng mapping **many-to-many**:
1 kênh TikTok có thể đăng lên nhiều FB Page, 1 FB Page có thể nhận từ nhiều kênh TikTok.

MVP dành cho **1 người dùng** (không auth/rate-limit/api-key) nhưng thiết kế để mở rộng multi-user
sau này.

## 2. Quyết định thiết kế (đã chốt với user)

| Chủ đề | Quyết định |
|---|---|
| Workflow | Auto đăng hoàn toàn, sau khi đăng mới sửa title/comment/xóa |
| Detect + tải TikTok | **yt-dlp** (list metadata + download video) |
| Đăng Facebook | **Graph API chính thức** với Page Access Token (không cookie login) |
| Video cũ | Auto backfill **có cơ chế**: ưu tiên video mới, video cũ vào queue đăng lần lượt cách khoảng để tránh spam, cho đến khi hết |
| Chống spam FB | Giới hạn theo page: `max_posts_per_day` + `min_interval_minutes` |
| Lịch đăng | Liên tục: poll định kỳ (mặc định 30-60 phút) |
| Sửa sau đăng | Đồng bộ sửa title/description trên FB qua Graph API |
| Chống chặn TikTok | Poll thưa + random User-Agent + retry/backoff, không proxy |
| Kiến trúc | FastAPI app đơn + queue trong PostgreSQL |
| Đầu vào "comment" | `description` của video (caption) |

## 3. Architecture

Single FastAPI application (keep template structure), workers chạy trong process:

```
Frontend (React + TanStack Query)
   |
   | REST API
   v
Backend FastAPI
   ├── API routes          channels / pages / mappings / jobs / stats / actions
   ├── Scheduler (asyncio loop, chạy trong app)
   │     ├── Poller        detect video mới bằng yt-dlp -> enqueue job
   │     └── PostWorker    tiêu thụ post_jobs: tải + đăng lên từng page
   ├── Services
   │     ├── TikTokProvider   (wrap yt-dlp: list metadata + download)
   │     ├── FacebookClient   (Graph API: upload, edit, delete)
   │     └── QuotaGuard       (giới hạn spam theo page)
   └── PostgreSQL (SQLModel models + queue trong DB)
```

Khi đầy quy mô multi-user: tách background worker thành process riêng (vẫn dùng cùng queue DB), giữ
nguyên model. Không dùng Redis/Celery ở MVP.

## 4. Data Model

Kế thừa models trong `backend/app/models.py` (đã commit, sẽ refactor/sửa lại ở phase implement).

| Bảng | Cột & ý nghĩa |
|---|---|
| `tiktok_channels` | `username` (unique), `display_name`, `last_checked_at`, `backfill_anchor_video_id`, `backfill_remaining`, `is_active`, `created_at` |
| `facebook_pages` | `page_id` (unique), `name`, `access_token_encrypted`, `max_posts_per_day` (default 10), `min_interval_minutes` (default 10), `is_active`, `created_at` |
| `channel_page_mappings` | `tiktok_channel_id` FK, `facebook_page_id` FK, unique(cặp), `is_active`, `created_at` |
| `video_metas` | **metadata video TikTok (dedup theo kênh)**: `tiktok_video_id`, `tiktok_channel_id` FK, `title`, `description`, `thumbnail_url`, `create_time`, `download_url`, `is_backfill`, `created_at`. Index `(channel_id, create_time)` |
| `post_jobs` | **queue**: `video_meta_id` FK, `facebook_page_id` FK, `status` (`pending`/`processing`/`posted`/`failed`/`skipped`/`deleted`), `attempts`, `error_message`, `scheduled_at`, `posted_at`, `facebook_post_id`, `facebook_url`, unique(video_meta_id, facebook_page_id) |
| `app_settings` | key-value: `poll_interval_minutes`, `max_backfill_videos`, `max_attempts` (mặc định từ settings) |

Quan hệ:

- 1 video TikTok = 1 dòng `video_metas`; đăng lên N page = N dòng `post_jobs`.
- Dedup (tránh đăng trùng) = unique constraint `(video_meta_id, facebook_page_id)`.
- Xóa kênh/page → cascade xóa dữ liệu liên quan (FK cascade).

## 5. Luồng vận hành

### 5.1 Detect video mới (Poller)

- Mỗi `poll_interval_minutes` (mặc định 30), với từng `tiktok_channels` active:
  - `TikTokProvider.list_new_videos(username, since=last_checked_at)` → list metadata
  - video mới hơn `last_checked_at` (hoặc anchor khi vừa backfill):
    - tạo/upsert `video_metas`
    - với mỗi page active đã map trong mappings: tạo `post_jobs` theo quy tắc dưới
  - cập nhật `last_checked_at`
- **Ưu tiên video mới**: job video mới được `scheduled_at = now` → chạy trước.

### 5.2 Backfill (khi vừa thêm kênh, hoặc có tùy chọn)

- Khi tạo kênh, tự chạy backfill:
  - `TikTokProvider.list_recent_metas(username, limit=settings.max_backfill_videos)` — newest-first
  - **video mới nhất** → đặt `backfill_anchor_video_id` (chỉ video mới hơn anchor được đăng ưu tiên)
  - các video cũ hơn → tạo `video_metas` + `post_jobs` với `is_backfill=true`, `scheduled_at` rải cách 5–10 phút
  - `backfill_remaining` = số video cũ chưa tải hết nếu vượt `max_backfill_videos`
- **PostWorker ưu tiên job không-backfill trước**; chỉ xử lý tối đa 1 job backfill mỗi lượt quét
  để 'đăng lần lượt'.
- Khi `backfill_remaining == 0` → kênh về chế độ chờ video mới bình thường.

### 5.3 Đăng (PostWorker)

Mỗi lượt (VD mỗi 60s), lấy job `pending` sớm nhất (`scheduled_at <= now`), ưu tiên non-backfill:

1. `status = processing`
2. `QuotaGuard.check(page_id, scheduled_at)`:
   - số bài thành công hôm nay của page < `max_posts_per_day`
   - `now - posted_at_last >= min_interval_minutes`
   - Nếu không thỏa → `scheduled_at = now + (thời gian chờ)`, quay lại `pending`. Không tính là lỗi.
3. Tải video (qua `video_metas.download_url`, cache theo meta)
4. `FacebookClient.upload_video(page_id, file, title, description)` (từ video_metas title/description)
5. OK → `status=posted`, `posted_at`, `facebook_post_id`, lưu `facebook_url`
6. Lỗi → `attempts+1`; nếu `attempts >= max_attempts` → `status=failed` + `error_message`; ngược lại `scheduled_at` theo exponential backoff (1s, 2s, 4s...) và quay lại `pending`

### 5.4 Sửa / Xóa sau khi đăng

- **Sửa**: `PATCH /api/jobs/{id}` với title/description mới → cập nhật DB + gọi
  `FacebookClient.update_post(facebook_post_id, title, description)`. Lỗi API → trả 500 + rollback
  (log, không hủy DB).
- **Xóa**: `DELETE /api/jobs/{id}` → nếu có `facebook_post_id` gọi `delete_post(facebook_post_id)`
  → `status=deleted`. (API FB hỗ trợ xóa post; nếu lỗi xóa FB vẫn giữ `status=deleted` và ghi lỗi
  trong `error_message`.)

## 6. API Endpoints

```
/tiktok-channels      GET/POST/PATCH/DELETE  (POST = thêm kênh + khởi động backfill)
/tiktok-channels/{id}/pages                 GET pages mà kênh đăng lên; POST/DELETE mapping
/facebook-pages       GET/POST/PATCH/DELETE
/facebook-pages/{id}/channels               GET kênh đang upload lên page này
/mappings             POST | DELETE  (channel↔page)
/jobs                 GET?channel=&page=&status=&date=   lịch sử & "hôm nay"
/jobs/{id}            PATCH (title, description) · DELETE
/stats                GET tổng quan hôm nay, theo kênh/page, tồn đợi, scheduler status
/scheduler/run-now    POST trigger poll thủ công (chạy ngay, background task)
```

## 7. Frontend (React)

Layout:
- Sidebar: Channels · Pages · Logs · Dashboard
- **Channels tab**: bảng TikTok channels, mỗi dòng có badge các page đang map + nút mapping/backfill
- **Pages tab**: bảng FB pages, badge kênh đang up lên page, chỉnh token + quy định
- **Logs tab**: bảng `post_jobs` — filter date (mặc định hôm nay), kênh, page, status; Edit dialog
  (title/description), Delete
- **Dashboard**: thẻ tổng (hôm nay đăng mấy/video nào/kênh nào), scheduler status, failed gần đây
  + nút "Check now"

Xóa toàn bộ code mẫu auth/items/users của template (frontend lẫn backend): routes login/signup/admin,
api/users/private/login, models User/Item, security etc... Giữ lại infra (config, db, alembic, docker).

## 8. Chống ban / spam

TikTok:
- Poll thưa (30-60p), 1 kênh/lượt
- Random User-Agent, retry+backoff (1s,2s,4s; max 3) khi HTTP 429/403
- Không chạy song song download
- Chia nhỏ bằng yt-dlp (không self-scrape dễ vỡ)

Facebook:
- Dùng Graph API official + Page Access Token (không cookie) → tránh "die account"
- Quota theo page: `max_posts_per_day` + `min_interval_minutes`, enforced cả worker lẫn API
- Tokens mã hóa bằng Fernet (`ENCRYPTION_KEY`), không lưu plaintext
- Retry lỗi 5xx/connection (backoff), không retry 4xx (trừ 400/190 token expired)

## 9. Cấu hình (settings)

`backend/app/core/config.py` thêm:
- `POLL_INTERVAL_MINUTES` (default 30)
- `MAX_BACKFILL_VIDEOS` (default 50)
- `JOB_SCAN_SECONDS` (default 60)
- `MAX_ATTEMPTS` (default 3)
- `ENCRYPTION_KEY` (Fernet)

Các giá trị cấu hình được đọc từ `.env`.

## 10. Testing

- **Unit**: `TikTokProvider` (mock yt-dlp output), `FacebookClient` (mock httpx), `QuotaGuard`,
  encode/decrypt token
- **Integration**: workflow enqueue→quota→upload với TestClient + DB Postgres test
- **E2E (Playwright)**: add channel → add page → mapping → run-now → job xuất hiện → edit → delete
- Lint: `uv run ruff`, `bun run lint`, mypy

## 11. Out of Scope (MVP loại bỏ)

- Auth/authz, API key, rate limit theo user (1 user hiện tại)
- Webhook thời gian thực (vẫn poll)
- Lịch đăng theo giờ cụ thể
- Chỉnh sửa video nội dung (trim/watermark)
- Analytics (likes/views)
- Email/Slack cảnh báo
- Đa proxy pool

## 12. Mở rộng tương lai (post-MVP)

- Tách worker process (container riêng), rồi scale theo channel
- Thêm user/auth: thêm `owner_id` vào các bảng + ràng buộc
- Webhook thay poll
- Proxy pool cấu hình qua admin
- Multi token / token refresh tự động