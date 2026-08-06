# TikTok → Facebook Auto-Poster Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-user MVP that detects new videos from configured TikTok channels and auto-posts them to mapped Facebook Pages, with backfill queueing, per-page anti-spam quota, editable/deletable post history, and a React dashboard.

**Architecture:** Single FastAPI app embedding an asyncio scheduler (Poller + PostWorker) reading/writing a PostgreSQL-backed job queue. TikTok via yt-dlp, Facebook via official Graph API. React + TanStack Query frontend. All templates (auth/users/items) from the FastAPI full-stack template are removed.

**Tech Stack:** Backend: FastAPI, SQLModel, PostgreSQL, yt-dlp, httpx, tenacity, cryptography, Pydantic v2, Alembic. Frontend: React 19, TanStack Router/Query, Tailwind 4, shadcn/ui (existing `frontend/src/components/ui/*`), Biome.

## Global Constraints

- Python 3.14, ruff target py314; backend deps managed with UV; frontend with Bun.
- Single user — **no auth/authz, no API keys, no user-based rate limiting**. Multi-user readiness = add `owner_id` later, not now.
- All timestamps stored UTC; UI renders local time.
- Title/description default = TikTok video title/description.
- Duplicate prevention: unique constraint on (video_meta_id, facebook_page_id) and (tiktok_channel_id, tiktok_video_id).
- Anti-spam: `max_posts_per_day` + `min_interval_minutes` enforced in worker and API.
- Backend API prefix `/api/v1` (kept from template). Frontend dev proxy via vite is NOT present — regenerate client then `bun run generate-client` after routes exist.
- Tests: pytest (backend), Playwright (frontend smoke). Lint: `uv run ruff check --fix . && uv run ruff format .`; frontend `bun run lint`; type: `uv run mypy .`, `bun run tsc --noEmit`.
- Naming: models table names snake_case (SQLModel default); class names PascalCase.
- No unused template code remains; delete auth-related backend/frontend files and their deps.

---

### Task 1: Strip template auth/user/item code and add MVP settings

**Files:**
- Delete: `backend/app/api/routes/{login,users,utils,items,private}.py`
- Delete: `backend/app/core/security.py`, `backend/app/api/deps.py`, `backend/app/crud.py`, `backend/app/initial_data.py`, `backend/app/backend_pre_start.py`, `backend/app/tests_pre_start.py`
- Rewrite: `backend/app/api/main.py`, `backend/app/api/__init__.py`, `backend/app/main.py`
- Modify: `backend/app/core/config.py` (remove auth/SMTP/Sentry-adjacent fields, add poster settings)
- Modify: `backend/pyproject.toml` (trim auth-only deps; add `yt-dlp`, `cryptography`)
- Rewrite: `backend/tests/conftest.py`
- Delete: `backend/tests/api`, `backend/tests/crud`, `backend/tests/utils`, `backend/tests/scripts`
- Delete: `backend/app/email-templates`, `backend/app/utils.py`, `backend/scripts/{lint,prestart,test,tests-start,format}.sh`
- Modify: `frontend/vite.config.ts` (add dev proxy `/api/v1` → `http://localhost:8000`)

**Interfaces:**
- Consumes: existing template layout
- Produces: clean `app.main` with `/api/v1`, `app.core.config.settings` with the new fields; `get_session` generator in `app/core/db.py` (`engine` stays there too). No `app/api/deps.py` — routes import `get_session` from `app.core.db`.

- [ ] **Step 1: Write failing test** — a test that the app boots and exposes required settings

```python
# backend/tests/test_bootstrap.py
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_settings_present():
    assert settings.POLL_INTERVAL_MINUTES == 30
    assert settings.MAX_BACKFILL_VIDEOS == 50
    assert settings.MAX_ATTEMPTS == 3
    assert settings.ENCRYPTION_KEY


def test_app_has_api_prefix():
    client = TestClient(app)
    assert client.get("/api/v1/tiktok-channels").status_code == 200
```

- [ ] **Step 2: Run test to verify it fails** — `cd backend && uv run pytest tests/test_bootstrap.py -v`
  Expected: FAIL (ModuleNotFoundError / AttributeError — settings fields missing / router missing)

- [ ] **Step 3: Update settings** in `backend/app/core/config.py`:

```python
import secrets
from typing import Literal

from pydantic import PostgresDsn, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    SECRET_KEY: str = ""

    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    # --- poster settings ---
    POLL_INTERVAL_MINUTES: int = 30
    MAX_BACKFILL_VIDEOS: int = 50
    JOB_SCAN_SECONDS: int = 60
    MAX_ATTEMPTS: int = 3
    GRAPH_VERSION: str = "v21.0"
    RUN_SCHEDULER: bool = True
    ENCRYPTION_KEY: str = ""

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def _default_encryption_key(cls, v: str) -> str:
        return v or f"CHANGE_ME_{secrets.token_urlsafe(16)}"


settings = Settings()  # type: ignore
```

Note: `secret` generated fallback is a development convenience only — real deployments must set `ENCRYPTION_KEY` explicitly in `.env`.

- [ ] **Step 4: Implement minimal app** — `backend/app/api/main.py`:

```python
from fastapi import APIRouter

from app.api.routes import channels, jobs, mappings, pages, scheduler, stats

api_router = APIRouter()
for router in (channels.router, pages.router, mappings.router, jobs.router, stats.router, scheduler.router):
    api_router.include_router(router)
```

- [ ] **Step 4b: Rewrite `backend/app/main.py`** — remove auth/CORS/Sentry wiring, keep static frontend serving:

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.api.main import api_router
from app.core.config import settings

FRONTEND_DIR = Path(__file__).parent / "frontend"


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)

app.include_router(api_router, prefix=settings.API_V1_STR)
app.frontend("/", directory=FRONTEND_DIR)
```

- [ ] **Step 5: Rewrite `backend/app/tests/conftest.py`** to remove User/Item dependencies and create tables:

```python
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session

from app.core.db import engine
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def _create_tables() -> Generator[None]:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(scope="module")
def client() -> Generator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function")
def db() -> Generator[Session]:
    with Session(engine) as session:
        yield session
        session.rollback()
```

- [ ] **Step 5b: Add `get_session` to `backend/app/core/db.py`** (keep `engine`):

```python
from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))


def init_db() -> None:
    # Tables are managed by Alembic; kept here only for tests via conftest.
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session]:
    with Session(engine) as session:
        yield session
```

`backend_pre_start.py` is deleted; the app starts without a startup DB check (MVP).

- [ ] **Step 6: Add stub route modules** so the app imports (implement fully in Tasks 7–9):

`backend/app/api/routes/channels.py`:
```python
from fastapi import APIRouter

router = APIRouter(prefix="/tiktok-channels", tags=["tiktok-channels"])
```

and corresponding empty routers for `pages`, `mappings`, `jobs`, `stats`, `scheduler`.

- [ ] **Step 7: Run tests to verify pass**

Run: `cd backend && uv run pytest tests/test_bootstrap.py -v`
Expected: PASS

- [ ] **Step 8: Update `frontend/vite.config.ts`** dev proxy:

```ts
server: {
  proxy: {
    "/api/v1": {
      target: "http://localhost:8000",
      changeOrigin: true,
    },
  },
},
```

- [ ] **Step 9: Lint + Commit**

```bash
cd backend
uv run ruff check --fix . && uv run ruff format .
git add -A backend/app backend/tests backend/pyproject.toml frontend/vite.config.ts
git commit -m "chore: strip template, add poster config and app skeleton"
```

---

### Task 2: Poster data models + Alembic baseline

**Files:**
- Rewrite: `backend/app/models.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: Task 1 settings
- Produces: SQLModel classes `TikTokChannel`, `FacebookPage`, `ChannelPageMapping`, `VideoMeta`, `PostJob` (see Task 4, 6–9)

- [ ] **Step 1: Write failing tests** (models exist, DTCs work, cascade delete works)

```python
# backend/tests/test_models.py
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models import (
    ChannelPageMapping,
    FacebookPage,
    PostJob,
    TikTokChannel,
    VideoMeta,
)


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def test_channel_creation(db: Session):
    ch = TikTokChannel(username="user1", display_name="User One")
    db.add(ch)
    db.commit()
    assert ch.id is not None
    assert ch.is_active is True
    assert ch.backfill_remaining == 0


def test_video_meta_unique_per_channel(db: Session):
    ch = TikTokChannel(username="user2")
    db.add(ch)
    db.commit()
    db.add(VideoMeta(tiktok_video_id="123", tiktok_channel_id=ch.id, title="t", description=""))
    db.commit()
    db.add(VideoMeta(tiktok_video_id="123", tiktok_channel_id=ch.id, title="t2", description=""))
    # second insert of same (channel, video) should raise IntegrityError
    try:
        db.commit()
        assert False, "expected IntegrityError"
    except Exception:
        db.rollback()
```

- [ ] **Step 2: Run test** `uv run pytest tests/test_models.py -v` → FAIL (models missing)

- [ ] **Step 3: Implement models** in `backend/app/models.py` (keep `utcnow` helper; manual `sa` for composite unique):

```python
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TikTokChannel(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    display_name: Optional[str] = None
    last_checked_at: Optional[datetime] = None
    backfill_anchor_video_id: Optional[str] = None
    backfill_remaining: int = 0
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class FacebookPage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    page_id: str = Field(index=True, unique=True)
    name: str
    access_token_encrypted: str
    max_posts_per_day: int = 10
    min_interval_minutes: int = 10
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class ChannelPageMapping(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("tiktok_channel_id", "facebook_page_id", name="uq_mapping_pair"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    tiktok_channel_id: int = Field(foreign_key="tiktokchannel.id", index=True)
    facebook_page_id: int = Field(foreign_key="facebookpage.id", index=True)
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class VideoMeta(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("tiktok_channel_id", "tiktok_video_id", name="uq_video_channel"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    tiktok_video_id: str = Field(index=True)
    tiktok_channel_id: int = Field(foreign_key="tiktokchannel.id", index=True)
    title: str = ""
    description: str = ""
    thumbnail_url: Optional[str] = None
    create_time: Optional[datetime] = None
    download_url: Optional[str] = None
    is_backfill: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class PostJob(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("video_meta_id", "facebook_page_id", name="uq_job_video_page"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    video_meta_id: int = Field(foreign_key="videometa.id", index=True)
    facebook_page_id: int = Field(foreign_key="facebookpage.id", index=True)
    status: str = Field(default="pending")  # pending|processing|posted|failed|skipped|deleted
    attempts: int = 0
    error_message: Optional[str] = None
    scheduled_at: datetime = Field(default_factory=utcnow)
    posted_at: Optional[datetime] = None
    facebook_post_id: Optional[str] = None
    facebook_url: Optional[str] = None
    title: str = ""  # editable copy at enqueue time
    description: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
```

Note: FK target table names are SQLModel default table names (`tiktokchannel`, `facebookpage`, `videometa`).

- [ ] **Step 4: Run tests to pass** — `uv run pytest tests/test_models.py -v` → PASS

- [ ] **Step 5: Remove stale migration files + regenerate baseline** (fresh DB):

```bash
cd backend
rm -f app/alembic/versions/*.py
rm -f app/alembic/versions/.keep
touch app/alembic/versions/.keep
uv run alembic revision --autogenerate -m "first autoposter schema"
# drop existing tables if any (dev only)
uv run alembic upgrade head
```

- [ ] **Step 6: Lint + Commit**

```bash
uv run ruff check --fix . && uv run ruff format .
git add backend/app/models.py backend/tests/test_models.py backend/app/alembic
git commit -m "feat: add autoposter models (channels, pages, mappings, video_metas, post_jobs)"
```

---

### Task 3: Token encryption utility

**Files:**
- Create: `backend/app/core/crypto.py`
- Test: `backend/tests/test_crypto.py`

**Interfaces:**
- Produces: `encrypt_token(plain: str) -> str`, `decrypt_token(enc: str) -> str`

- [ ] **Step 1: failing test**

```python
# backend/tests/test_crypto.py
from app.core.crypto import decrypt_token, encrypt_token


def test_roundtrip():
    enc = encrypt_token("EAAsecret")
    assert enc != "EAAsecret"
    assert decrypt_token(enc) == "EAAsecret"
```

- [ ] **Step 2: verify fail** → FAIL (module missing)

- [ ] **Step 3: implement**

```python
# backend/app/core/crypto.py
from cryptography.fernet import Fernet

from app.core.config import settings


def _fernet() -> Fernet:
    return Fernet(settings.ENCRYPTION_KEY.encode("utf-8"))


def encrypt_token(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_token(enc: str) -> str:
    return _fernet().decrypt(enc.encode("utf-8")).decode("utf-8")
```

- [ ] **Step 4: pass test + commit**

```bash
git add backend/app/core/crypto.py backend/tests/test_crypto.py
git commit -m "feat: add Fernet token encryption/decryption"
```

---

### Task 4: TikTokProvider service (yt-dlp wrapper)

**Files:**
- Create: `backend/app/services/tiktok_provider.py`
- Modify: `backend/app/core/config.py` (add `MAX_BACKFILL_VIDEOS` default already there)
- Test: `backend/tests/services/test_tiktok_provider.py`
- Add dep: `yt-dlp` in `pyproject.toml` deps already via Task 1

**Interfaces:**
- Consumes: nothing
- Produces:
  - `dataclass TikTokVideo(video_id: str, title: str, description: str, thumbnail_url: str | None, create_time: datetime | None, download_url: str | None)`
  - `class TikTokProvider`
  - `list_channel_videos(username: str, limit: int) -> list[TikTokVideo]`
  - `get_video_download_url(video_id_or_url: str) -> str | None`
  - `download_video(video_url: str, dest_dir: Path) -> Path`

- [ ] **Step 1: failing test** (mock yt-dlp not invoked during import)

```python
# backend/tests/services/test_tiktok_provider.py
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.tiktok_provider import TikTokProvider, TikTokVideo


def _fake_entry(**overrides):
    base = {
        "id": "7321",
        "title": "My video",
        "description": "desc",
        "thumbnail": "http://x/th.jpg",
        "timestamp": 1_700_000_000,
        "webpage_url": "https://www.tiktok.com/@u/video/7321",
    }
    base.update(overrides)
    return base


@patch("app.services.tiktok_provider.youtube_dl.YoutubeDL")
def test_list_channel_videos(MockYDL):
    fake_entries = [_fake_entry()]
    mock_info = {"entries": fake_entries}
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value.extract_info.return_value = mock_info
    MockYDL.return_value = mock_ydl

    provider = TikTokProvider()
    videos = provider.list_channel_videos("demo", limit=10)

    assert len(videos) == 1
    v = videos[0]
    assert v.video_id == "7321"
    assert v.title == "My video"
    assert isinstance(v.create_time, datetime)


@patch("app.services.tiktok_provider.youtube_dl.YoutubeDL")
def test_empty_channel(MockYDL):
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value.extract_info.return_value = {"entries": None}
    MockYDL.return_value = mock_ydl

    provider = TikTokProvider()
    assert provider.list_channel_videos("empty", limit=10) == []
```

- [ ] **Step 2: run → FAIL**
- [ ] **Step 3: Implement**

```python
# backend/app/services/tiktok_provider.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yt_dlp as youtube_dl

_BASE_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "socket_timeout": 30,
}


@dataclass
class TikTokVideo:
    video_id: str
    title: str
    description: str
    thumbnail_url: str | None
    create_time: datetime | None
    download_url: str | None


class TikTokProvider:
    def list_channel_videos(self, username: str, limit: int) -> list[TikTokVideo]:
        url = f"https://www.tiktok.com/@{username}"
        opts: dict[str, Any] = {
            **_BASE_OPTS,
            "extract_flat": "in_playlist",
            "playlistend": limit,
            "playlist_items": f"1-{limit}",
        }
        with youtube_dl.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        entries = (info or {}).get("entries") or []
        out: list[TikTokVideo] = []
        for e in entries:
            if not e:
                continue
            ts = e.get("timestamp")
            out.append(
                TikTokVideo(
                    video_id=str(e.get("id", "")),
                    title=e.get("title") or "",
                    description=e.get("description") or "",
                    thumbnail_url=e.get("thumbnail"),
                    create_time=datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None,
                    download_url=e.get("webpage_url"),
                )
            )
        return out

    def get_video_download_url(self, video_id_or_url: str) -> str | None:
        # yt-dlp exposes the 'url' of the best format when not flat
        return video_id_or_url  # MVP: use webpage_url; direct stream handled in download

    def download_video(self, video_url: str, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        opts: dict[str, Any] = {
            **_BASE_OPTS,
            "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
            "format": "best[ext=mp4]/best",
        }
        with youtube_dl.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
        ext = info.get("ext", "mp4")
        return dest_dir / f"{info.get('id')}.{ext}"
```

- [ ] **Step 4: pass** — `uv run pytest backend/tests/services/test_tiktok_provider.py -v`
- [ ] **Step 5: commit**

```bash
cd backend
uv run ruff check --fix . && uv run ruff format .
git add backend/app/services/tiktok_provider.py backend/tests/services/test_tiktok_provider.py backend/pyproject.toml
git commit -m "feat: add TikTok provider wrapping yt-dlp"
```

---

### Task 5: FacebookClient service (Graph API)

**Files:**
- Create: `backend/app/services/facebook_client.py`
- Create config: `GRAPH_VERSION: str = "v21.0"` in config.py (or use versionless)
- Test: `backend/tests/services/test_facebook_client.py`
- Deps: `httpx` already present; add nothing

**Interfaces:**
- Consumes: `FacebookPage` model
- Produces: `class FacebookClient`:
  - `async upload_video(page_id: str, token: str, file_path: Path, title: str, description: str) -> str` returns FB post ID
  - `async update_post(post_id: str, token: str, title: str, description: str) -> None`
  - `async delete_post(post_id: str, token: str) -> None`

- [ ] **Step 1: failing test**

```python
# backend/tests/services/test_facebook_client.py
import httpx
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.facebook_client import FacebookClient


def test_upload_video_returns_post_id(tmp_path):
    import asyncio

    client = FacebookClient()
    file_path = tmp_path / "v.mp4"
    file_path.write_bytes(b"bytes")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"id": "12345"}
    mock_resp.raise_for_status.return_value = None

    async def fake_post(url, **kwargs):
        return mock_resp

    with patch.object(client, "_post", fake_post):
        post_id = asyncio.run(
            client.upload_video("page123", "token", file_path, "t", "d")
        )
    assert post_id == "12345"
```

- [ ] **Step 2: run → FAIL**
- [ ] **Step 3: implement**

```python
# backend/app/services/facebook_client.py
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

BASE = "https://graph.facebook.com"
GRAPH_VERSION = getattr(settings, "GRAPH_VERSION", "v21.0")


class FacebookClient:
    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None

    async def _http_session(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(120))
        return self._http

    async def upload_video(self, page_id: str, token: str, file_path: Path, title: str, description: str) -> str:
        url = f"{BASE}/{GRAPH_VERSION}/{page_id}/videos"
        with open(file_path, "rb") as f:
            files = {"source": (file_path.name, f, "video/mp4")}
            data = {
                "access_token": token,
                "title": title,
                "description": description,
            }
            response = await self._post(url, files=files, data=data)
        payload = response.json()
        return payload.get("id") or payload.get("post_id") or ""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=8))
    async def _post(self, url: str, **kwargs) -> httpx.Response:
        http = await self._http_session()
        r = await http.post(url, **kwargs)
        r.raise_for_status()
        return r

    async def update_post(self, post_id: str, token: str, title: str, description: str) -> None:
        url = f"{BASE}/{GRAPH_VERSION}/{post_id}"
        data = {
            "access_token": token,
            "title": title,
            "description": description,
        }
        r = await self._post(url, data=data)
        r.raise_for_status()

    async def delete_post(self, post_id: str, token: str) -> None:
        url = f"{BASE}/{GRAPH_VERSION}/{post_id}"
        http = await self._http_session()
        r = await http.delete(url, params={"access_token": token})
        r.raise_for_status()
```

- [ ] **Step 4: run → PASS**
- [ ] **Step 5: commit**
- Note: test file helper must be coherent with implementation (`_post` vs `_http_post`). Use `_post`.

---

### Task 6: QuotaGuard + PostingService orchestration

**Files:**
- Create: `backend/app/services/quota.py`
- Create: `backend/app/services/posting_service.py`
- Test: `backend/tests/services/test_quota.py`, `backend/tests/services/test_posting_service.py`

**Interfaces:**
- Consumes: `Session`, models, `TikTokProvider`, `FacebookClient`, `crypto.decrypt_token`
- Produces:
  - `class QuotaGuard`
    - `daily_posts(db, page_id, now) -> int`
    - `last_posted(db, page_id) -> datetime | None`
    - `next_allowed(db, page, now) -> datetime`
  - `class PostingService`
    - `enqueue_video(db, channel, video_meta, pages, scheduled_at=None) -> list[PostJob]`
    - `backfill_channel(db, channel) -> None`
    - `poll_new_videos(db, channel) -> None`
    - `process_due_jobs(db) -> dict[str, int]`

- [ ] **Step 1: failing test for quota**

```python
# backend/tests/services/test_quota.py
from datetime import datetime, timezone

from app.core import crypto
from app.models import FacebookPage
from app.services.quota import QuotaGuard


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_daily_posts_count(db):
    page = FacebookPage(
        page_id="P1",
        name="Page",
        access_token_encrypted=crypto.encrypt_token("t"),
        max_posts_per_day=10,
        min_interval_minutes=10,
    )
    db.add(page)
    db.commit()

    guard = QuotaGuard()
    assert guard.daily_posts(db, page.id, _now()) == 0
    assert guard.last_posted(db, page.id) is None
    assert guard.next_allowed(db, page, _now()) == _now()
```

Note: the `db` fixture is the function-scoped `Session` from conftest.

- [ ] **Step 2: run → FAIL**
- [ ] **Step 3: implement quota**

```python
# backend/app/services/quota.py
from datetime import datetime, time, timedelta, timezone
from sqlmodel import Session, func, select

from app.models import FacebookPage, PostJob


class QuotaGuard:
    def daily_posts(self, db: Session, page_id: int, now: datetime) -> int:
        start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
        stmt = (
            select(func.count(PostJob.id))
            .where(
                PostJob.facebook_page_id == page_id,
                PostJob.status == "posted",
                PostJob.posted_at >= start,
            )
        )
        return db.exec(stmt).one()

    def last_posted(self, db: Session, page_id: int) -> datetime | None:
        stmt = (
            select(PostJob.posted_at)
            .where(PostJob.facebook_page_id == page_id, PostJob.status == "posted")
            .order_by(PostJob.posted_at.desc())
            .limit(1)
        )
        return db.exec(stmt).first()

    def next_allowed(self, db: Session, page, now: datetime) -> datetime:
        candidates = [now]
        last = self.last_posted(db, page.id)
        if last and (now - last).total_seconds() < page.min_interval_minutes * 60:
            candidates.append(last + timedelta(minutes=page.min_interval_minutes))
        if self.daily_posts(db, page.id, now) >= page.max_posts_per_day:
            start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
            candidates.append(start + timedelta(days=1))
        return max(candidates)
```

- [ ] **Step 4: pass quota tests**
- [ ] **Step 5: failing posting_service test**

```python
# backend/tests/services/test_posting_service.py
from datetime import datetime, timezone

from app.core import crypto
from app.models import (
    ChannelPageMapping,
    FacebookPage,
    PostJob,
    TikTokChannel,
    VideoMeta,
)
from app.services.posting_service import PostingService
from app.services.tiktok_provider import TikTokVideo


def _seed(db):
    page = FacebookPage(
        page_id="P1",
        name="Page one",
        access_token_encrypted=crypto.encrypt_token("tok"),
        max_posts_per_day=10,
        min_interval_minutes=10,
    )
    ch = TikTokChannel(username="creator")
    db.add_all([page, ch])
    db.commit()
    db.add(ChannelPageMapping(tiktok_channel_id=ch.id, facebook_page_id=page.id))
    db.commit()
    return ch, page


def _upsert_raw(db, ch):
    from app.models import VideoMeta

    meta = VideoMeta(
        tiktok_video_id="V1",
        tiktok_channel_id=ch.id,
        title="T",
        description="D",
        create_time=datetime.now(timezone.utc),
        download_url="https://tiktok.com/@c/video/1",
    )
    db.add(meta)
    db.commit()
    return meta


def test_enqueue_deduplicates(db):
    ch, page = _seed(db)
    meta = _upsert_raw(db, ch)
    service = PostingService()
    jobs = service.enqueue_video(db, ch, meta, [page])
    assert len(jobs) == 1
    jobs2 = service.enqueue_video(db, ch, meta, [page])
    assert jobs2 == []
    assert db.get(PostJob, jobs[0].id).status == "pending"


def _write_fake_mp4(dest_dir):
    p = Path(dest_dir) / "v.mp4"
    p.write_bytes(b"x")
    return p


async def test_process_due_jobs_posts(db):
    ch, page = _seed(db)
    meta = _upsert_raw(db, ch)
    service = PostingService()

    job = service.enqueue_video(db, ch, meta, [page])[0]

    service.provider.download_video = lambda url, dest: _write_fake_mp4(dest)

    async def fake_upload(page_id, token, file_path, title, description):
        return "fb_post_1"

    service.facebook.upload_video = fake_upload

    result = await service.process_due_jobs(db)
    assert result["posted"] == 1
    job = db.get(PostJob, job.id)
    assert job.status == "posted"
    assert job.facebook_post_id == "fb_post_1"
```

Note: add `from pathlib import Path` to this test file.

- [ ] **Step 6: begin implementing `posting_service.py`** — the full body lives in Task 7. This task defines `PostingService.__init__`, `enqueue_video`, `active_pages_for_channel`, and `_upsert_meta` (copy from Task 7), then commits quota + posting scaffold.
- [ ] **Step 7: run quota tests; commit**

```bash
cd backend
uv run pytest tests/services/test_quota.py -v
uv run ruff check --fix . && uv run ruff format .
git add backend/app/services/quota.py backend/tests/services/test_quota.py
git commit -m "feat: add quota guard"
```

Posting-service tests are completed in Task 7 where `process_due_jobs` etc. exist.

---

### Task 7: PostingService core (enqueue, backfill, poll, process)

Continues Task 6. Implementation body:

```python
# backend/app/services/posting_service.py
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from app.core.config import settings
from app.core.crypto import decrypt_token
from app.models import (
    ChannelPageMapping,
    FacebookPage,
    PostJob,
    TikTokChannel,
    VideoMeta,
)
from app.services.facebook_client import FacebookClient
from app.services.quota import QuotaGuard
from app.services.tiktok_provider import TikTokProvider, TikTokVideo

TEMP_DIR = Path("tmp")


class PostingService:
    def __init__(self) -> None:
        self.provider = TikTokProvider()
        self.facebook = FacebookClient()
        self.quota = QuotaGuard()

    # ---- enqueue ----
    def enqueue_video(self, db, channel, meta: VideoMeta, pages: list[FacebookPage], scheduled_at: datetime | None = None) -> list[PostJob]:
        jobs: list[PostJob] = []
        for page in pages:
            exists = db.exec(
                select(PostJob).where(
                    PostJob.video_meta_id == meta.id,
                    PostJob.facebook_page_id == page.id,
                )
            ).first()
            if exists:
                continue
            job = PostJob(
                video_meta_id=meta.id,
                facebook_page_id=page.id,
                title=meta.title,
                description=meta.description,
                status="pending",
                scheduled_at=scheduled_at or datetime.now(timezone.utc),
            )
            db.add(job)
            jobs.append(job)
        db.commit()
        return jobs

    def active_pages_for_channel(self, db: Session, channel_id: int) -> list[FacebookPage]:
        stmt = (
            select(FacebookPage)
            .join(ChannelPageMapping, ChannelPageMapping.facebook_page_id == FacebookPage.id)
            .where(
                ChannelPageMapping.tiktok_channel_id == channel_id,
                ChannelPageMapping.is_active == True,  # noqa: E712
                FacebookPage.is_active == True,  # noqa: E712
            )
        )
        return list(db.exec(stmt).all())

    # ---- backfill ----
    def backfill_channel(self, db: Session, channel: TikTokChannel) -> None:
        videos = self.provider.list_channel_videos(channel.username, settings.MAX_BACKFILL_VIDEOS)
        if not videos:
            return
        # newest-first from provider; newest video is "#0" — use as anchor
        newest = videos[0]
        if newest.create_time is None:
            newest = max(videos, key=lambda v: v.create_time or datetime(1970, 1, 1, tzinfo=timezone.utc))
        channel.backfill_anchor_video_id = newest.video_id
        pages = self.active_pages_for_channel(db, channel.id)
        now = datetime.now(timezone.utc)
        spread = 10 * 60  # seconds between backfill posts
        older = [v for v in videos if v.video_id != newest.video_id]
        # enqueue older videos first, latest last; stagger to avoid spam
        queue_order = list(reversed(older)) + [newest]
        for i, vid in enumerate(queue_order):
            meta = self._upsert_meta(db, channel, vid, is_backfill=True)
            if not meta:
                continue
            self.enqueue_video(db, channel, meta, pages, scheduled_at=now + timedelta(seconds=i * spread))
        channel.backfill_remaining = max(0, settings.MAX_BACKFILL_VIDEOS - len(videos))
        db.add(channel)
        db.commit()

    # ---- poll ----
    def poll_new_videos(self, db: Session, channel: TikTokChannel) -> None:
        videos = self.provider.list_channel_videos(channel.username, limit=30)
        if not videos:
            channel.last_checked_at = datetime.now(timezone.utc)
            db.add(channel)
            db.commit()
            return
        pages = self.active_pages_for_channel(db, channel.id)
        for vid in videos:
            # skip anything older than the backfill anchor (already backfilled)
            if channel.backfill_anchor_video_id and vid.video_id == channel.backfill_anchor_video_id:
                break
            if not channel.backfill_anchor_video_id and vid.create_time and channel.last_checked_at \
                    and vid.create_time <= channel.last_checked_at:
                break
            meta = self._upsert_meta(db, channel, vid, is_backfill=False)
            if meta:
                self.enqueue_video(db, channel, meta, pages)
        channel.last_checked_at = datetime.now(timezone.utc)
        db.add(channel)
        db.commit()

    # ---- worker ----
    async def process_due_jobs(self, db: Session) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        jobs = db.exec(
            select(PostJob)
            .where(PostJob.status == "pending", PostJob.scheduled_at <= now)
            .order_by(PostJob.scheduled_at)
            .limit(5)
        ).all()
        counts = {"posted": 0, "failed": 0, "rescheduled": 0, "skipped": 0}
        for job in jobs:
            page = db.get(FacebookPage, job.facebook_page_id)
            meta = db.get(VideoMeta, job.video_meta_id)
            if page is None or not page.is_active:
                job.status = "skipped"
                db.add(job); db.commit(); counts["skipped"] += 1
                continue
            next_at = self.quota.next_allowed(db, page, now)
            if next_at > now:
                job.status = "pending"
                job.scheduled_at = next_at
                db.add(job); db.commit(); counts["rescheduled"] += 1
                continue
            job.status = "processing"
            db.add(job); db.commit()
            try:
                import tempfile
                with tempfile.TemporaryDirectory() as tmp:
                    fpath = await asyncio.to_thread(self.provider.download_video, meta.download_url or "", Path(tmp))
                    token = decrypt_token(page.access_token_encrypted)
                    post_id = await self.facebook.upload_video(page.page_id, token, fpath, job.title or meta.title, job.description or meta.description)
                job.status = "posted"
                job.posted_at = datetime.now(timezone.utc)
                job.facebook_post_id = post_id
                job.facebook_url = f"https://www.facebook.com/{page.page_id}/posts/{post_id}"
                job.attempts = 0
                db.add(job); db.commit(); counts["posted"] += 1
            except Exception as exc:  # noqa: BLE001
                job.attempts += 1
                job.error_message = str(exc)
                job.status = "failed" if job.attempts >= settings.MAX_ATTEMPTS else "pending"
                job.scheduled_at = now + timedelta(seconds=2 ** (job.attempts - 1))
                db.add(job); db.commit(); counts["failed" if job.status == "failed" else "rescheduled"] += 1
            finally:
                job.updated_at = datetime.now(timezone.utc)
        return counts
```

Also add `_upsert_meta`:

```python
    def _upsert_meta(self, db, channel, vid: TikTokVideo, is_backfill: bool) -> VideoMeta | None:
        if not vid.video_id:
            return None
        meta = db.exec(select(VideoMeta).where(
            VideoMeta.tiktok_channel_id == channel.id, VideoMeta.tiktok_video_id == vid.video_id
        )).first()
        if meta is None:
            meta = VideoMeta(
                tiktok_video_id=vid.video_id,
                tiktok_channel_id=channel.id,
                title=vid.title or "",
                description=vid.description or "",
                thumbnail_url=vid.thumbnail_url,
                create_time=vid.create_time,
                download_url=vid.download_url,
                is_backfill=is_backfill,
            )
            db.add(meta); db.commit(); db.refresh(meta)
        return meta
```

Note: `timedelta` must be imported at top of `posting_service.py` (`from datetime import datetime, timedelta, timezone`).

- [ ] **Step: run both test files; fix until green:**

```bash
cd backend
uv run pytest tests/services/test_quota.py tests/services/test_posting_service.py -v
```

- [ ] **Step: commit**

```bash
uv run ruff check --fix . && uv run ruff format .
git add backend/app/services/quota.py backend/app/services/posting_service.py backend/tests/services
git commit -m "feat: add quota guard and posting service (enqueue, backfill, poll, worker)"
```

---

### Task 8: SchedulerService (asyncio loop)

**Files:**
- Create: `backend/app/services/scheduler_service.py`
- Test: `backend/tests/services/test_scheduler_service.py`

**Interfaces:**
- Consumes: `PostingService`, `get_session`
- Produces: `class SchedulerService`: `start()`, `stop()`, `run_now() -> None`, `status() -> dict`

- [ ] **Step 1: failing test**

```python
def test_status_default():
    s = SchedulerService(run_interval_seconds=60)
    info = s.status()
    assert "last_poll" in info and "last_run" in info and "running" in info
```

- [ ] **Step 2: implement**

```python
# backend/app/services/scheduler_service.py
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.services.posting_service import PostingService


class SchedulerService:
    def __init__(self, run_interval_seconds: int | None = None) -> None:
        self.run_interval = run_interval_seconds or settings.POLL_INTERVAL_MINUTES * 60
        self._task: asyncio.Task | None = None
        self._state: dict[str, Any] = {
            "running": False,
            "last_poll": None,
            "last_run": None,
        }

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._state["running"] = False
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        posting = PostingService()
        self._state["running"] = True
        while True:
            # poll once + process
            try:
                await self.run_once(posting)
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(self.run_interval)

    async def run_once(self, posting: PostingService | None = None) -> dict[str, int]:
        posting = posting or PostingService()
        counts = {"channels": 0, "posted": 0, "failed": 0}
        from sqlmodel import Session, select

        from app.core.db import engine
        from app.models import TikTokChannel

        with Session(engine) as db:
            channels = db.exec(
                select(TikTokChannel).where(TikTokChannel.is_active == True)  # noqa: E712
            ).all()
            for channel in channels:
                try:
                    posting.poll_new_videos(db, channel)
                    counts["channels"] += 1
                except Exception:  # noqa: BLE001
                    continue
            result = await posting.process_due_jobs(db)
            counts["posted"] += result.get("posted", 0)
            counts["failed"] += result.get("failed", 0)
        self._state["last_poll"] = datetime.now(timezone.utc)
        self._state["last_run"] = datetime.now(timezone.utc)
        return counts

    def status(self) -> dict[str, Any]:
        return dict(self._state)


# module-level singleton consumed by API routes (scheduler.py, stats.py)
scheduler = SchedulerService()
```

Note: `get_session` defined in Task 1 (`app/core/db.py`) is for FastAPI DI. The scheduler opens its own `Session(engine)` to avoid dependency-context issues. Wire the singleton's lifecycle in `app/main.py` with a FastAPI `lifespan`:

```python
# backend/app/main.py (add)
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.services.scheduler_service import scheduler


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(scheduler.start())
    yield
    await scheduler.stop()
    task.cancel()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)
```

Note: guard scheduler startup behind `settings.ENVIRONMENT != "test"` or a `RUN_SCHEDULER` flag so pytest TestClient doesn't start the loop (add `RUN_SCHEDULER: bool = True` to Settings and check it in the lifespan).

- [ ] **Step 3: pass, commit**

```bash
cd backend
uv run pytest tests/services/test_scheduler_service.py -v
uv run ruff check --fix . && uv run ruff format .
git add backend/app/services/scheduler_service.py backend/tests/services/test_scheduler_service.py backend/app/main.py backend/app/core/config.py
git commit -m "feat: add scheduler service with lifespan wiring"
```

---

### Task 9: API routes

**Files:**
- Create: `backend/app/api/routes/{channels,pages,mappings,jobs,stats,scheduler}.py` (complete them)
- Delete/ignore the Task-1 stubs; replace with full routers
- Test: `backend/tests/api/test_routes.py`

**Interfaces (consume):**
- models, `PostingService`, `SchedulerService`, `get_session` dep (Task 1, `app/core/db.py`), `crypto`
- Produce: endpoints below, plus `POST /api/v1/scheduler/run-now` returning JSON

Route contract:

```
/tiktok-channels           GET → [{id, username, display_name, last_checked_at, backfill_anchor_video_id, backfill_remaining, is_active, pages:[{id,name}]}]
/tiktok-channels  POST      body {username, display_name?} → create + trigger backfill (BackgroundTasks) + return channel
/tiktok-channels/{id}  PATCH  {display_name? is_active?}
/tiktok-channels/{id}  DELETE
/facebook-pages            GET → [{id, page_id, name, max_posts_per_day, min_interval_minutes, is_active, channels:[{id, username}]}]
/facebook-pages  POST       body {page_id, name, access_token, max_posts_per_day=10, min_interval_minutes=10}
/facebook-pages/{id} PATCH
/facebook-pages/{id} DELETE
/mappings  POST             body {tiktok_channel_id, facebook_page_id}
/mappings/{id} DELETE
/jobs?channel=&page=&status=&date=  GET → [{id, title, description, status, posted_at, scheduled_at, error_message, facebook_url, channel, page}]
/jobs/{id} PATCH  {title?, description?} → update DB + GraphAPI (post_id) update
/jobs/{id} DELETE
/stats  GET                 {today_posted, today_pending, channels, scheduler:{...}}
/scheduler/run-now  POST    → {"queued": True} triggers immediate one-shot
```

- [ ] **Step 1–4 (TDD per route)**: `backend/tests/api/test_routes.py` with concrete cases:

```python
def test_create_and_list_channel(client):
    r = client.post("/api/v1/tiktok-channels", json={"username": "newcreator"})
    assert r.status_code == 200
    data = r.json()
    assert data["username"] == "newcreator"
    lst = client.get("/api/v1/tiktok-channels")
    assert any(c["username"] == "newcreator" for c in lst.json())


def test_create_page(client):
    r = client.post(
        "/api/v1/facebook-pages",
        json={"page_id": "1001", "name": "Fanpage", "access_token": "secret"},
    )
    assert r.status_code == 200
    assert r.json()["access_token_encrypted"]  # stored encrypted, never plaintext
    assert "access_token" not in r.json()


def test_create_mapping(client):
    ch = client.post("/api/v1/tiktok-channels", json={"username": "c1"}).json()
    pg = client.post(
        "/api/v1/facebook-pages",
        json={"page_id": "2002", "name": "P", "access_token": "t"},
    ).json()
    r = client.post(
        "/api/v1/mappings",
        json={"tiktok_channel_id": ch["id"], "facebook_page_id": pg["id"]},
    )
    assert r.status_code == 200


def test_run_now(client):
    assert client.post("/api/v1/scheduler/run-now").json() == {"queued": True}


def test_stats_shape(client):
    body = client.get("/api/v1/stats").json()
    assert set(body) >= {"today_posted", "today_pending", "channels", "scheduler"}
```

Note: the `/mappings` route and `/scheduler/run-now` must exist before these tests run; implement the empty stub routers from Task 1 before writing tests, or write these tests after implementing all routes. Prefer: implement all route modules (channels, pages, mappings, jobs, stats, scheduler) with the contract above, then write the test file, then run.

- [ ] **Step: implement routes.** Reference implementations (channels):

```python
# backend/app/api/routes/channels.py
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session, select

from app.core.db import get_session
from app.models import ChannelPageMapping, FacebookPage, TikTokChannel
from app.schemas import TikTokChannelCreate, TikTokChannelRead, TikTokChannelUpdate
from app.services.posting_service import PostingService

router = APIRouter(prefix="/tiktok-channels", tags=["tiktok-channels"])


def _read_channel(db: Session, ch: TikTokChannel) -> TikTokChannelRead:
    pages = db.exec(
        select(FacebookPage)
        .join(ChannelPageMapping, ChannelPageMapping.facebook_page_id == FacebookPage.id)
        .where(ChannelPageMapping.tiktok_channel_id == ch.id)
    ).all()
    return TikTokChannelRead(
        id=ch.id,
        username=ch.username,
        display_name=ch.display_name,
        last_checked_at=ch.last_checked_at,
        backfill_anchor_video_id=ch.backfill_anchor_video_id,
        backfill_remaining=ch.backfill_remaining,
        is_active=ch.is_active,
        pages=[{"id": p.id, "name": p.name} for p in pages],
    )


@router.get("", response_model=list[TikTokChannelRead])
def list_channels(db: Session = Depends(get_session)):
    return [_read_channel(db, ch) for ch in db.exec(select(TikTokChannel)).all()]


@router.post("", response_model=TikTokChannelRead)
def create_channel(
    payload: TikTokChannelCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_session),
):
    if db.exec(select(TikTokChannel).where(TikTokChannel.username == payload.username)).first():
        raise HTTPException(409, "channel already exists")
    ch = TikTokChannel(username=payload.username, display_name=payload.display_name)
    db.add(ch)
    db.commit()
    db.refresh(ch)
    background.add_task(_run_backfill, ch.id)
    return _read_channel(db, ch)


def _run_backfill(channel_id: int) -> None:
    from sqlmodel import Session

    from app.core.db import engine

    with Session(engine) as db:
        channel = db.get(TikTokChannel, channel_id)
        if channel:
            PostingService().backfill_channel(db, channel)
```

Schemas file `backend/app/schemas.py` (complete):

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TikTokChannelCreate(BaseModel):
    username: str = Field(min_length=1)
    display_name: str | None = None


class TikTokChannelUpdate(BaseModel):
    display_name: str | None = None
    is_active: bool | None = None


class TikTokChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str | None
    last_checked_at: datetime | None
    backfill_anchor_video_id: str | None
    backfill_remaining: int
    is_active: bool
    pages: list[dict] = []


class FacebookPageCreate(BaseModel):
    page_id: str
    name: str
    access_token: str
    max_posts_per_day: int = 10
    min_interval_minutes: int = 10


class FacebookPageUpdate(BaseModel):
    name: str | None = None
    access_token: str | None = None
    max_posts_per_day: int | None = None
    min_interval_minutes: int | None = None
    is_active: bool | None = None


class FacebookPageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    page_id: str
    name: str
    max_posts_per_day: int
    min_interval_minutes: int
    is_active: bool
    channels: list[dict] = []


class MappingCreate(BaseModel):
    tiktok_channel_id: int
    facebook_page_id: int


class PostJobUpdate(BaseModel):
    title: str | None = None
    description: str | None = None


class PostJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    video_meta_id: int
    facebook_page_id: int
    status: str
    attempts: int
    error_message: str | None
    scheduled_at: datetime | None
    posted_at: datetime | None
    facebook_post_id: str | None
    facebook_url: str | None
    title: str
    description: str
    channel: str | None = None   # username (joined)
    page: str | None = None      # page name (joined)
```

Important: `TikTokChannelRead.pages` / `FacebookPageRead.channels` are not SQLModel fields, so `list_channels` must build them explicitly (see Task 9 routes) — `model_validate(ch)` alone yields empty lists. Fill them in the route:

```python
def _read_channel(db, ch) -> TikTokChannelRead:
    pages = db.exec(
        select(FacebookPage)
        .join(ChannelPageMapping, ChannelPageMapping.facebook_page_id == FacebookPage.id)
        .where(ChannelPageMapping.tiktok_channel_id == ch.id)
    ).all()
    return TikTokChannelRead(
        **{k: getattr(ch, k) for k in ("id", "username", "display_name", "last_checked_at", "backfill_anchor_video_id", "backfill_remaining", "is_active")},
        pages=[{"id": p.id, "name": p.name} for p in pages],
    )
```

- [ ] **Step: implement jobs routes (edit/delete with facebook sync):**

```python
# backend/app/api/routes/jobs.py
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.crypto import decrypt_token
from app.core.db import get_session
from app.models import FacebookPage, PostJob, TikTokChannel, VideoMeta
from app.schemas import PostJobRead, PostJobUpdate
from app.services.facebook_client import FacebookClient

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _to_read(db: Session, job: PostJob) -> PostJobRead:
    meta = db.get(VideoMeta, job.video_meta_id)
    page = db.get(FacebookPage, job.facebook_page_id)
    channel = db.get(TikTokChannel, meta.tiktok_channel_id) if meta else None
    read = PostJobRead.model_validate(job)
    read.channel = channel.username if channel else None
    read.page = page.name if page else None
    return read


@router.get("", response_model=list[PostJobRead])
def list_jobs(
    channel_id: int | None = None,
    page_id: int | None = None,
    status: str | None = None,
    date: str | None = None,
    db: Session = Depends(get_session),
):
    stmt = select(PostJob)
    if channel_id:
        stmt = stmt.join(VideoMeta).where(VideoMeta.tiktok_channel_id == channel_id)
    if page_id:
        stmt = stmt.where(PostJob.facebook_page_id == page_id)
    if status:
        stmt = stmt.where(PostJob.status == status)
    if date:
        day = datetime.fromisoformat(date)
        stmt = stmt.where(PostJob.posted_at >= day, PostJob.posted_at < day + timedelta(days=1))
    stmt = stmt.order_by(PostJob.scheduled_at.desc()).limit(100)
    jobs = db.exec(stmt).all()
    return [_to_read(db, job) for job in jobs]


@router.patch("/{job_id}", response_model=PostJobRead)
async def update_job(job_id: int, payload: PostJobUpdate, db: Session = Depends(get_session)):
    job = db.get(PostJob, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(job, k, v)
    job.updated_at = datetime.now(timezone.utc)
    db.add(job)
    if job.facebook_post_id and job.status == "posted":
        page = db.get(FacebookPage, job.facebook_page_id)
        if page:
            token = decrypt_token(page.access_token_encrypted)
            try:
                await FacebookClient().update_post(job.facebook_post_id, token, job.title, job.description)
            except Exception as exc:  # noqa: BLE001
                job.error_message = f"fb update failed: {exc}"
    db.commit()
    db.refresh(job)
    return _to_read(db, job)


@router.delete("/{job_id}")
async def delete_job(job_id: int, db: Session = Depends(get_session)):
    job = db.get(PostJob, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job.facebook_post_id and job.status == "posted":
        page = db.get(FacebookPage, job.facebook_page_id)
        if page:
            try:
                await FacebookClient().delete_post(job.facebook_post_id, decrypt_token(page.access_token_encrypted))
            except Exception as exc:  # noqa: BLE001
                job.error_message = f"fb delete failed: {exc}"
    job.status = "deleted"
    job.updated_at = datetime.now(timezone.utc)
    db.add(job)
    db.commit()
    return {"ok": True}
```

Notes:
- `update_job`/`delete_job` are `async def` because they `await` FacebookClient (SQLModel sync session inside async handler is an accepted MVP tradeoff).
- `/jobs` router only carries GET/PATCH/DELETE. `run-now` lives in scheduler.py.

- [ ] **Step: implement pages, mappings, stats, scheduler routers** (same pattern):

```python
# backend/app/api/routes/pages.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.crypto import encrypt_token
from app.core.db import get_session
from app.models import ChannelPageMapping, FacebookPage, TikTokChannel
from app.schemas import FacebookPageCreate, FacebookPageRead, FacebookPageUpdate

router = APIRouter(prefix="/facebook-pages", tags=["facebook-pages"])


def _read_page(db: Session, page: FacebookPage) -> FacebookPageRead:
    channels = db.exec(
        select(TikTokChannel)
        .join(ChannelPageMapping, ChannelPageMapping.tiktok_channel_id == TikTokChannel.id)
        .where(ChannelPageMapping.facebook_page_id == page.id)
    ).all()
    read = FacebookPageRead.model_validate(page)
    read.channels = [{"id": c.id, "username": c.username} for c in channels]
    return read


@router.get("", response_model=list[FacebookPageRead])
def list_pages(db: Session = Depends(get_session)):
    return [_read_page(db, p) for p in db.exec(select(FacebookPage)).all()]


@router.post("", response_model=FacebookPageRead)
def create_page(payload: FacebookPageCreate, db: Session = Depends(get_session)):
    if db.exec(select(FacebookPage).where(FacebookPage.page_id == payload.page_id)).first():
        raise HTTPException(409, "page already exists")
    page = FacebookPage(
        page_id=payload.page_id,
        name=payload.name,
        access_token_encrypted=encrypt_token(payload.access_token),
        max_posts_per_day=payload.max_posts_per_day,
        min_interval_minutes=payload.min_interval_minutes,
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    return _read_page(db, page)


@router.patch("/{page_id}", response_model=FacebookPageRead)
def update_page(page_id: int, payload: FacebookPageUpdate, db: Session = Depends(get_session)):
    page = db.get(FacebookPage, page_id)
    if not page:
        raise HTTPException(404, "page not found")
    data = payload.model_dump(exclude_unset=True)
    if "access_token" in data:
        data["access_token_encrypted"] = encrypt_token(data.pop("access_token"))
    for k, v in data.items():
        setattr(page, k, v)
    db.add(page)
    db.commit()
    db.refresh(page)
    return _read_page(db, page)


@router.delete("/{page_id}")
def delete_page(page_id: int, db: Session = Depends(get_session)):
    page = db.get(FacebookPage, page_id)
    if not page:
        raise HTTPException(404, "page not found")
    db.delete(page)
    db.commit()
    return {"ok": True}
```

```python
# backend/app/api/routes/mappings.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.db import get_session
from app.models import ChannelPageMapping
from app.schemas import MappingCreate

router = APIRouter(prefix="/mappings", tags=["mappings"])


@router.post("")
def create_mapping(payload: MappingCreate, db: Session = Depends(get_session)):
    exists = db.exec(
        select(ChannelPageMapping).where(
            ChannelPageMapping.tiktok_channel_id == payload.tiktok_channel_id,
            ChannelPageMapping.facebook_page_id == payload.facebook_page_id,
        )
    ).first()
    if exists:
        raise HTTPException(409, "mapping already exists")
    m = ChannelPageMapping(
        tiktok_channel_id=payload.tiktok_channel_id,
        facebook_page_id=payload.facebook_page_id,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"id": m.id}


@router.delete("/{mapping_id}")
def delete_mapping(mapping_id: int, db: Session = Depends(get_session)):
    m = db.get(ChannelPageMapping, mapping_id)
    if not m:
        raise HTTPException(404, "mapping not found")
    db.delete(m)
    db.commit()
    return {"ok": True}
```

```python
# backend/app/api/routes/stats.py
from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends
from sqlmodel import Session, func, select

from app.core.db import get_session
from app.models import PostJob, TikTokChannel
from app.services.scheduler_service import scheduler

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("")
def get_stats(db: Session = Depends(get_session)):
    now = datetime.now(timezone.utc)
    start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    today_posted = db.exec(
        select(func.count(PostJob.id)).where(
            PostJob.status == "posted", PostJob.posted_at >= start
        )
    ).one()
    today_pending = db.exec(
        select(func.count(PostJob.id)).where(PostJob.status == "pending")
    ).one()
    channels = len(db.exec(select(TikTokChannel)).all())
    return {
        "today_posted": today_posted,
        "today_pending": today_pending,
        "channels": channels,
        "scheduler": scheduler.status(),
    }
```

```python
# backend/app/api/routes/scheduler.py
from fastapi import APIRouter

from app.services.scheduler_service import scheduler

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.post("/run-now")
async def run_now():
    await scheduler.run_once()
    return {"queued": True}
```

Wire-in: `backend/app/services/scheduler_service.py` exports a module-level singleton `scheduler = SchedulerService()` (defined in Task 8); `app/main.py` starts/stops it via the FastAPI `lifespan` defined in Task 8, guarded by `settings.RUN_SCHEDULER`.

- [ ] **Step: satisfy tests, ruff, commit**

```bash
cd backend
uv run ruff check --fix . && uv run ruff format .
uv run pytest tests/api/test_routes.py -v
git add backend/app/api/routes backend/app/schemas.py backend/tests/api
git commit -m "feat: add API routes for channels, pages, mappings, jobs, stats, scheduler"
```

---

### Task 10: Frontend cleanup — strip auth/items, new layout

**Files:**
- Delete: `frontend/src/routes/{login,signup,recover-password,reset-password}.tsx`, `_layout/admin.tsx`, `_layout/settings.tsx`, `_layout/items.tsx`, `components/Items/`, `components/Admin/`, `components/UserSettings/`, `components/Pending/`, `hooks/useAuth.ts`
- Rewrite: `frontend/src/routes/_layout.tsx` (drop auth guard), `frontend/src/routes/_layout/index.tsx` (dashboard), `frontend/src/components/Sidebar/AppSidebar.tsx`, `frontend/src/components/Sidebar/User.tsx`, `frontend/src/components/Common/Footer.tsx`
- Modify: `frontend/src/routes/__root.tsx` (remove devtools if inconvenient) — optional
- Test: `bun run tsc --noEmit` passes; nav loads

**Interfaces:** produce layout with menu: Dashboard → `/`, Channels → `/channels`, Pages → `/pages`, Logs → `/logs`

- [ ] **Step 1: build script** after backend up: `bun run generate-client` (needs `frontend/openapi.json` — see hook `scripts/generate-client.sh`). Simplicity: run `./scripts/generate-client.sh` in custom).
  - Note: the generated client method names follow the backend operationIds (`custom_generate_unique_id` → `{tag}-{handler_name}`), so expect names like `TiktokChannelsService.listChannels` / `create`, `JobsService.updateJob`, `SchedulerService.runNow`. Verify the exact names in `frontend/src/client/` after generation and use those throughout Tasks 11–13 (referenced names below are illustrative).
- [ ] **Step 2: sidebar** map to new routes with icons `Home`, `Music2` (Channels), `Users` (Pages), `History` (Logs); remove `User` footer.
- [ ] **Step 3: delete auth/items modules**, TS + biome green
- [ ] **Step 4: create `_layout/channels.tsx`, `pages.tsx`, `logs.tsx` scaffolds** with `createFileRoute` + empty component (fill next tasks)
- [ ] **Step 5: commit** `git add -A`, message `feat: frontend layout for autoposter`

---

### Task 11: Frontend — Channels + Pages (mapping UI)

**Files:**
- Create: `frontend/src/routes/_layout/channels.tsx`, `_layout/pages.tsx`, `frontend/src/components/Channels/`, `frontend/src/components/Pages/`
- Reuse: `DataTable`, `Button`, `Dialog`, `Form`, `Input`, `Badge`, `useCustomToast`

**Functionality:**
- Channels list (reactive via TanStack Query), Add dialog (username), Delete, show mapped pages as badges + link to mapping dialog
- Pages list, Add dialog (page_id, name, access_token, quota), Delete, show channels feeding it
- Mapping dialog: pick FB page(s) for a channel; multi-select; use `MappingsService.create`

**Steps:** TDD not used — verify visually + `bun run tsc --noEmit` + `bun run lint`. Then **commit**.

---

### Task 12: Frontend — Logs page (today's posts, edit, delete)

**Files:**
- Create `frontend/src/routes/_layout/logs.tsx`, components `logs/JobsTable.tsx`, `logs/EditJobDialog.tsx`

**Features:**
- Filter: date (native `input type=date`, default today), channel select, page select, status select
- Table: thumbnail, title, channel, page, status badge, posted_at
- Edit: dialog with title/description → `JobsService.updateJob` → refetch + toast
- Delete: confirmation → `JobsService.deleteJob`

**Steps:** implement, typecheck, lint, **commit**.

---

### Task 13: Frontend — Dashboard

**Files:** `frontend/src/routes/_layout/index.tsx`, `components/dashboard/StatsCards.tsx`

**Features:**
- Cards: today posted count, pending count, failed count, active channels
- "Check now" button → `SchedulerService.runNow`
- Recent 5 failed jobs list

**Steps:** implement, typecheck, lint, **commit**.

---

### Task 14: E2E + verification pass

**Files:**
- Create `frontend/tests/smoke.spec.ts`
- Update `.env` dev: API, DB local
- Run full verify cascade

- [ ] **Step 1: Playwright smoke** — `frontend/tests/smoke.spec.ts`, mock network to avoid requiring real backend/proxies:

```ts
import { expect, test } from "@playwright/test"

test("dashboard shows and channels nav works", async ({ page }) => {
  await page.route("**/api/v1/tiktok-channels", (route) =>
    route.fulfill({ json: [{ id: 1, username: "demo", display_name: null, last_checked_at: null, backfill_remaining: 0, is_active: true, pages: [] }] }),
  )
  await page.route("**/api/v1/stats", (route) =>
    route.fulfill({ json: { today_posted: 3, today_pending: 1, channels: 1, scheduler: {} } }),
  )
  await page.goto("/")
  await expect(page.getByText("Channels")).toBeVisible()
  await page.getByRole("link", { name: "Channels" }).click()
  await expect(page).toHaveURL(/channels/)
  await expect(page.getByText("demo")).toBeVisible()
})
```

Run: `cd frontend && bun run test`. Requires a running backend OR just the frontend dev server — point `playwright.config.ts` `webServer` at `bun dev` (existing config already targets it; keep as-is).

- [ ] **Step 2: full verify:**

```bash
# backend
uv run ruff check --fix . && uv run ruff format .
uv run mypy .
uv run pytest
# frontend
cd frontend && bun run tsc --noEmit && bun run lint
# app boot
cd backend && uv run fastapi run --reload
```

- [ ] **Step 3: commit** final message `feat: complete TikTok-Facebook autoposter MVP`

---

## Post-implementation verification checklist

- [ ] Start channels, pages, mapping via UI
- [ ] Trigger "Check now" → jobs appear; quota re-schedules when hitting page limit
- [ ] Edit title/desc → posts updated; Delete → post removed
- [ ] `pytest` green; `mypy` strict clean; biome/ruff clean