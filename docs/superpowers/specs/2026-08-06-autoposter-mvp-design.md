# MVP Auto-Poster — Design

Ngày: 2026-08-06
Trạng thái: Đã được user duyệt

## Mục tiêu

Tool tự động phát hiện video mới của các kênh TikTok (user cung cấp), tải video về và upload lên Facebook Page tương ứng (1 kênh TikTok → 1 hoặc nhiều Page, user cung cấp). MVP cho 1 user, thiết kế để scale nhiều user sau này (chưa cần auth/rate limit/api key).

## Yêu cầu

1. Xem danh sách kênh TikTok và Facebook đã nhập
2. Biết kênh TikTok này up lên Page nào / Page được upload bởi kênh nào
3. Xem ngày hôm đó đã đăng video nào, kênh nào được đăng
4. Chỉnh sửa title, description, xóa bài đăng sau khi đăng (xóa luôn trên Facebook)
5. Title mặc định lấy từ title video TikTok
6. Backfill: tự động lấy TẤT CẢ video cũ từ thời điểm thêm channel, đăng dần mỗi 6 tiếng; process chính vẫn detect video mới và đăng bình thường
7. Chống bị chặn: cookie TikTok + giãn nhịp poll
8. Tạo `.env.example` với giá trị thật (cả key nhạy cảm), config đưa vào env
9. Xóa code/config không còn cần thiết (template leftover)

## Hiện trạng (đã verify trên code)

- SchedulerService: vòng lặp asyncio trong process FastAPI, chạy mỗi `POLL_INTERVAL_MINUTES` (30), khởi động ở lifespan `main.py` khi `RUN_SCHEDULER=True`
- `poll_new_videos`: list video mới (limit 30), upsert VideoMeta, enqueue PostJob
- `process_due_jobs`: xử lý job đến hạn — tải video, upload Facebook, retry backoff (MAX_ATTEMPTS, 2^n giây)
- Backfill hiện tại: chỉ chạy khi bấm nút (route channels), giới hạn MAX_BACKFILL_VIDEOS=50, cách 10 phút — KHÔNG đạt yêu cầu
- "Check now" là trigger tức thời, không phải điều kiện để worker chạy
- TikTok đang bị Slardar WAF chặn IP (`Unable to extract secondary user ID`) — cần cookie
- `models.py.bak`, `backend/app/frontend/` (build cũ), `copier.yml`, `AuthLayout.tsx`, `password-input.tsx`, `JOB_SCAN_SECONDS` — leftover template, chưa xóa

## Quyết định kiến trúc

### Không dùng Celery

Asyncio loop + DB làm lịch (`scheduled_at`) là đủ: 1 user, vài kênh, khối lượng nhỏ. Backfill 6h/video chỉ là PostJob với `scheduled_at` cách nhau 6 giờ — `process_due_jobs` đã xử lý đúng. Celery chỉ cần khi nhiều worker/queue phức tạp — defer.

### Backfill tự động

Khi thêm channel (route `POST /tiktok-channels`):
1. List toàn bộ video cũ của channel (không giới hạn)
2. `backfill_anchor_video_id` = video mới nhất tại thời điểm thêm
3. Enqueue video cũ nhất trước: `scheduled_at = now`, kế tiếp `now + BACKFILL_INTERVAL_HOURS`, ... (mặc định 6h/video)
4. `poll_new_videos` sau đó chỉ bắt video mới hơn anchor → đăng ngay (không chờ 6h)

Khác biệt với hiện tại:
- Bỏ nút/manual backfill route (chạy tự động khi add channel)
- Bỏ giới hạn 50 video
- Bỏ spread 10 phút → dùng `BACKFILL_INTERVAL_HOURS`
- Bỏ field `backfill_remaining` (không ai đọc) — giữ `backfill_anchor_video_id` (cốt lõi cho cơ chế mốc)
- `is_backfill` trên VideoMeta: giữ (ghi log phân biệt, chi phí 0)

### Chống chặn

- `TIKTOK_COOKIES_FILE` (env, mặc định rỗng = không dùng): file cookie Netscape format; `TikTokProvider` truyền `cookiefile=` vào yt-dlp khi có
- `POLL_INTERVAL_MINUTES` (env, 30): user tự giãn lên 120–240 nếu cần
- Giữ retry + backoff exponential hiện có
- README hướng dẫn export cookie (extension "Get cookies.txt") + cảnh báo dùng ít request

### Config thay đổi (config.py)

- Thêm: `BACKFILL_INTERVAL_HOURS: int = 6`, `TIKTOK_COOKIES_FILE: str = ""`
- Xóa: `MAX_BACKFILL_VIDEOS`, `JOB_SCAN_SECONDS`
- Giữ nguyên: POLL_INTERVAL_MINUTES, MAX_ATTEMPTS, GRAPH_VERSION, RUN_SCHEDULER, ENCRYPTION_KEY, postgres...

### `.env.example` giá trị thật

Tạo ở root với giá trị chạy được ngay: POSTGRES_*, DOMAIN, FIRST_SUPERUSER, SECRET_KEY (sinh mới), ENCRYPTION_KEY (sinh mới), SMTP_*, BACKFILL_INTERVAL_HOURS, TIKTOK_COOKIES_FILE, POLL_INTERVAL_MINUTES... Ghi chú trong README: đổi secret trước khi push repo public.

### Dọn dẹp

Xóa:
- `backend/app/models.py.bak`
- `backend/app/frontend/` (build assets cũ — frontend serve từ Dockerfile riêng)
- `copier.yml`
- `frontend/src/components/Common/AuthLayout.tsx` (không được import)
- `frontend/src/components/ui/password-input.tsx` (không được import)
- `JOB_SCAN_SECONDS` trong config

Kiểm tra khi làm:
- `frontend/src/utils.ts` vs `frontend/src/lib/utils.ts` trùng lặp → gộp
- `backend/tests/test_bootstrap.py`, `test_models.py`, `test_crypto.py` giữ nếu còn ý nghĩa

Giữ nguyên (nghiệp vụ thật): crypto.py, quota.py, stats.py, jobs/channels/pages/mappings/scheduler routes, toàn bộ UI Channels/Pages/Logs/Stats, DataTable, EditJobDialog...

## Luồng dữ liệu (target)

```
User thêm TikTokChannel
  └→ backfill tự động: list all videos → upsert VideoMeta → enqueue PostJob (scheduled_at: now, +6h, +12h...)
Scheduler loop (mỗi POLL_INTERVAL_MINUTES)
  ├→ poll_new_videos: list video mới hơn anchor → upsert → enqueue PostJob (scheduled_at=now)
  └→ process_due_jobs: job đến hạn → download video → upload Facebook → cập nhật trạng thái
User: xem/đổi title/description/xóa job (PATCH/DELETE /jobs/{id} — xóa kèm Facebook)
```

## Error handling

- WAF/network fail khi list video: bỏ qua channel, ghi `last_checked_at` cũ, retry ở poll sau (đã có try/except trong loop)
- Facebook API fail: retry backoff 2^n giây × MAX_ATTEMPTS, rồi status=failed + error_message
- RetryError tenacity: đã có `_unwrap_error`
- Cookie file không tồn tại: log warning, chạy không cookie

## Testing

- Backfill: unit test enqueue order + scheduled_at spacing; integration test add channel → jobs tạo đúng
- Anchor: poll_new_videos bỏ qua video ≤ anchor, bắt video > anchor
- Config: đọc env mới, `.env.example` có đủ key
- Chạy lại toàn bộ pytest + mypy + ruff hiện có (20 tests đang pass)
