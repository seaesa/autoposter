# TikTok → Facebook Auto Poster

Tự động đăng video TikTok lên Facebook Page: theo dõi kênh TikTok, tải video về, và đăng lên các Facebook Page đã cấu hình, có kiểm soát tần suất (quota) theo ngày.

**Stack:** FastAPI + SQLModel + PostgreSQL (backend) · React + Vite + Tailwind (frontend) · Docker Compose + Traefik

## Chạy local

### Yêu cầu

Docker + Docker Compose. (Hoặc chạy không Docker: cần Python 3.14 + uv, Node 20+ + Bun, và PostgreSQL.)

### 1. Cấu hình `.env`

Copy `.env.example` (giá trị local chạy được ngay) thành `.env`:

```bash
cp .env.example .env
```

Đổi `SECRET_KEY`, password PostgreSQL trước khi deploy. Biến bắt buộc:

| Biến | Ý nghĩa |
|---|---|
| `POSTGRES_SERVER/PORT/USER/PASSWORD/DB` | kết nối PostgreSQL |
| `SECRET_KEY` | khóa bí mật của app |
| `DOMAIN`, `ENVIRONMENT` | `localhost`, `local` khi chạy local |

### 2. Chạy bằng Docker Compose (khuyên dùng)

```bash
docker compose up --build
```

Truy cập:

- Web app: http://localhost
- API docs (Swagger): http://localhost:8000/docs
- Adminer (quản lý DB): http://localhost:8080
- Mailcatcher: http://localhost:1080

Dừng: `docker compose down`

### 3. Chạy dev (hot reload)

```bash
# backend (terminal 1)
cd backend
uv sync
uv run fastapi run --reload

# frontend (terminal 2)
cd frontend
bun install
bun dev
```

> Lưu ý: repo là uv workspace — `.venv` nằm ở root repo, không phải `backend/.venv`.

### Cấu hình ứng dụng

File `.env.example` ở root repo chứa các giá trị local chạy được ngay — copy thành `.env` và chỉnh lại. Các biến riêng của app:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `POLL_INTERVAL_MINUTES` | `30` | Scheduler bao lâu check TikTok 1 lần để bắt video mới |
| `BACKFILL_INTERVAL_HOURS` | `6` | Giãn cách giữa các bài backfill (video cũ của channel) |
| `MAX_ATTEMPTS` | `3` | Số lần retry khi đăng lên Facebook thất bại |
| `RUN_SCHEDULER` | `true` | Bật scheduler nền cùng API (`false` để tắt, chỉ dùng nút "Check now") |
| `GRAPH_VERSION` | `v21.0` | Phiên bản Facebook Graph API |
| `TIKTOK_COOKIES_FILE` | *(trống)* | Đường dẫn file cookie TikTok (xem bên dưới) |

### Cách hoạt động (auto-detect)

Worker **không** cần bấm "Check now" mỗi lần — server tự chạy:

- **Scheduler** (vòng lặp trong process backend, khởi động khi API lên) mỗi `POLL_INTERVAL_MINUTES` dò channel đang active: list video mới → lưu metadata → tạo việc đăng (PostJob).
- **Backfill**: khi thêm channel mới, toàn bộ video cũ được xếp lịch đăng dần, mỗi video cách `BACKFILL_INTERVAL_HOURS` (video mới nhất là mốc "anchor"). Video xuất hiện **sau** khi thêm channel được đăng ngay, không chờ backfill.
- **Worker** xử lý PostJob đến hạn: tải video về, upload lên Facebook Page qua Graph API, có quota theo ngày (`max_posts_per_day`, `min_interval_minutes`) chống veto spam.
- Nút "Check now" trên UI chỉ trigger scheduler chạy ngay lập tức thay vì chờ chu kỳ — không phải điều kiện để tự động chạy.

### Chống chặn TikTok

TikTok dùng WAF (Slardar) chặn request tự động — nếu `list_channel_videos` báo `Unable to extract secondary user ID`, đó là bị chặn IP, chưa phải lỗi code.

1. **Dùng cookie** (khuyên dùng): cài extension **"Get cookies.txt"** trên Chrome → vào tiktok.com → login → export cookie (Netscape format) → lưu ví dụ `backend/cookies/tiktok.txt` → đặt `TIKTOK_COOKIES_FILE` trong `.env`.
2. **Giãn nhịp**: nâng `POLL_INTERVAL_MINUTES` lên `120`–`240` để ít request hơn. Backfill vốn đã giãn 6h/video.
3. Nếu vẫn bị chặn: chờ vài giờ (block hết hạn), hoặc đổi IP/proxy.

> ⚠️ Cookie là session của tài khoản TikTok thật — dùng ít request, đừng spam, nếu không TikTok có thể ban account.

### Migrations

```bash
cd backend
uv run alembic revision --autogenerate -m "msg"   # tạo migration mới
uv run alembic upgrade head                        # áp migration
```

### Test

```bash
cd backend && uv run pytest        # backend
cd frontend && bun run tsc --noEmit && bun run lint   # frontend
```

## Deploy

Xem chi tiết: [`deployment.md`](deployment.md) — gồm Traefik (HTTPS tự động), biến môi trường production, và GitHub Actions CD.

Tóm tắt:

1. Chuẩn bị server, domain trỏ về server.
2. Cấu hình `.env` production (`DOMAIN=domain.com`, `ENVIRONMENT=production`, `SECRET_KEY` mạnh).
3. Chạy Traefik rồi stack app:

```bash
docker compose -f compose.yml -f compose.traefik.yml up -d
```

4. Migration tự chạy lúc khởi động (`scripts/prestart.sh`).
