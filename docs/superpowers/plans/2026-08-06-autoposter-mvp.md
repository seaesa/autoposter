# Auto-Poster MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the TikTok→Facebook auto-poster MVP: automatic backfill of all old TikTok videos (one post per 6h), config-driven via env, cookie-based anti-ban, `.env.example` with real values, and template leftover cleanup.

**Architecture:** Keep the existing asyncio scheduler loop + DB-as-queue (`PostJob.scheduled_at`). No Celery. Backfill becomes automatic on channel creation: enqueue all old videos oldest-first with `scheduled_at` spaced `BACKFILL_INTERVAL_HOURS` apart, newest video (anchor) last; `poll_new_videos` only picks up videos newer than the anchor and posts them immediately.

**Tech Stack:** FastAPI, SQLModel, yt-dlp (git master), uv, React/TanStack (frontend), Pytest, Ruff, MyPy.

## Global Constraints

- Backend Ruff: `uv run ruff check --fix . && uv run ruff format .` must pass; MyPy strict: `uv run mypy .` must pass
- Frontend: `bun run tsc --noEmit` and `bun run lint` must pass
- All commands run from `backend/` for backend tasks (alembic.ini is relative)
- Tests hit the isolated `autoposter_test` DB only (conftest), never the dev DB
- Config values live in `backend/app/core/config.py`, overridable via root `.env`
- No comments in code unless they explain *why*
- `BACKFILL_INTERVAL_HOURS` default = 6 (per approved design)
- Spec: `docs/superpowers/specs/2026-08-06-autoposter-mvp-design.md`

---

### Task 1: Config changes — add backfill/cookie settings, remove dead config

**Files:**
- Modify: `backend/app/core/config.py:63-70`
- Test: `backend/tests/test_config.py` (create)

**Interfaces:**
- Produces: `settings.BACKFILL_INTERVAL_HOURS: int` (default 6), `settings.TIKTOK_COOKIES_FILE: str` (default ""). Removes `MAX_BACKFILL_VIDEOS` and `JOB_SCAN_SECONDS`. Later tasks consume these two new names.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_config.py
from app.core.config import settings


def test_backfill_interval_default() -> None:
    assert settings.BACKFILL_INTERVAL_HOURS == 6


def test_cookies_file_default() -> None:
    assert settings.TIKTOK_COOKIES_FILE == ""


def test_dead_settings_removed() -> None:
    assert not hasattr(settings, "MAX_BACKFILL_VIDEOS")
    assert not hasattr(settings, "JOB_SCAN_SECONDS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'BACKFILL_INTERVAL_HOURS'`

- [ ] **Step 3: Edit config.py**

Replace lines 64-66 with:

```python
    POLL_INTERVAL_MINUTES: int = 30
    BACKFILL_INTERVAL_HOURS: int = 6
    MAX_ATTEMPTS: int = 3
    GRAPH_VERSION: str = "v21.0"
    RUN_SCHEDULER: bool = True
    ENCRYPTION_KEY: str = ""
    TIKTOK_COOKIES_FILE: str = ""
```

(Delete `MAX_BACKFILL_VIDEOS` and `JOB_SCAN_SECONDS`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_config.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Verify no other code references the removed settings**

Run: `cd backend && rg "MAX_BACKFILL_VIDEOS|JOB_SCAN_SECONDS" app/ tests/`
Expected: no output (posting_service.py still references `MAX_BACKFILL_VIDEOS` — that is expected; it will be fixed in Task 3. If other references exist, note them for Task 3.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config.py backend/tests/test_config.py
git commit -m "feat: add backfill interval + cookies config, drop dead settings"
```

---

### Task 2: TikTokProvider — support listing all videos and cookies

**Files:**
- Modify: `backend/app/services/tiktok_provider.py:29-55`
- Modify: `backend/tests/services/test_tiktok_provider.py`

**Interfaces:**
- Consumes: `settings.TIKTOK_COOKIES_FILE` (Task 1)
- Produces: `list_channel_videos(username: str, limit: int | None) -> list[TikTokVideo]` — `limit=None` means "all videos" (no `playlistend`); `cookiefile` injected into yt-dlp opts when configured.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/services/test_tiktok_provider.py`:

```python
@patch("app.services.tiktok_provider.youtube_dl.YoutubeDL")
def test_list_channel_videos_no_limit(MockYDL: MagicMock) -> None:
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value.extract_info.return_value = {"entries": []}
    MockYDL.return_value = mock_ydl

    TikTokProvider().list_channel_videos("demo", limit=None)

    opts = MockYDL.call_args.args[0]
    assert "playlistend" not in opts
    assert "playlist_items" not in opts


@patch("app.services.tiktok_provider.youtube_dl.YoutubeDL")
def test_list_channel_videos_uses_cookies(
    MockYDL: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "TIKTOK_COOKIES_FILE", "/tmp/tiktok-cookies.txt")
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value.extract_info.return_value = {"entries": []}
    MockYDL.return_value = mock_ydl

    TikTokProvider().list_channel_videos("demo", limit=10)

    opts = MockYDL.call_args.args[0]
    assert opts["cookiefile"] == "/tmp/tiktok-cookies.txt"
```

(Add `from app.core.config import settings` and `import pytest` to the imports.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/services/test_tiktok_provider.py -v`
Expected: FAIL — "playlistend" is in opts; "cookiefile" not in opts

- [ ] **Step 3: Edit tiktok_provider.py**

- Import settings: `from app.core.config import settings`
- Change signature to `def list_channel_videos(self, username: str, limit: int | None) -> list[TikTokVideo]:`
- Build opts conditionally:

```python
    opts: dict[str, Any] = {
        **_BASE_OPTS,
        "extract_flat": "in_playlist",
    }
    if limit is not None:
        opts["playlistend"] = limit
        opts["playlist_items"] = f"1-{limit}"
    if settings.TIKTOK_COOKIES_FILE:
        opts["cookiefile"] = settings.TIKTOK_COOKIES_FILE
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/services/test_tiktok_provider.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Lint and typecheck**

Run: `cd backend && uv run ruff check --fix . && uv run ruff format . && uv run mypy app/services/tiktok_provider.py`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/tiktok_provider.py backend/tests/services/test_tiktok_provider.py
git commit -m "feat: list all channel videos + cookie support in TikTokProvider"
```

---

### Task 3: Automatic backfill — all videos, 6h spacing, anchor last

**Files:**
- Modify: `backend/app/services/posting_service.py:90-125` (`backfill_channel`), `:128-157` (`poll_new_videos`)
- Test: `backend/tests/services/test_posting_service.py` (append)

**Interfaces:**
- Consumes: `settings.BACKFILL_INTERVAL_HOURS` (Task 1), `list_channel_videos(username, limit=None)` (Task 2)
- Produces: `backfill_channel(db, channel)` — unchanged signature; now enqueues ALL videos, oldest first, `scheduled_at = now + i*BACKFILL_INTERVAL_HOURS`, newest (anchor) last. `poll_new_videos` unchanged behavior (still only posts videos newer than anchor).
- Note: `backfill_channel` no longer sets `channel.backfill_remaining` (column removed in Task 4).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/services/test_posting_service.py` (add `timedelta` to the existing `datetime` import and `select` to the `sqlmodel` import):

```python
from app.services.tiktok_provider import TikTokVideo


def _fake_video(vid: str, ts: datetime) -> TikTokVideo:
    return TikTokVideo(
        video_id=vid,
        title=f"title {vid}",
        description="",
        thumbnail_url=None,
        create_time=ts,
        download_url=f"https://tiktok.com/v/{vid}",
    )


def _seed_page(db: Session) -> FacebookPage:
    page = FacebookPage(
        page_id="P1",
        name="Page one",
        access_token_encrypted=crypto.encrypt_token("tok"),
        max_posts_per_day=10,
        min_interval_minutes=10,
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


def test_backfill_enqueues_all_videos_oldest_first(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    ch = TikTokChannel(username="creator")
    db.add(ch)
    db.commit()
    db.refresh(ch)
    page = _seed_page(db)
    db.add(ChannelPageMapping(tiktok_channel_id=ch.id, facebook_page_id=page.id))
    db.commit()

    now = datetime.now(UTC)
    videos = [
        _fake_video("V3", now),
        _fake_video("V2", now - timedelta(days=1)),
        _fake_video("V1", now - timedelta(days=2)),
    ]

    service = PostingService()
    monkeypatch.setattr(service.provider, "list_channel_videos", lambda _u, limit: videos)

    service.backfill_channel(db, ch)

    db.refresh(ch)
    assert ch.backfill_anchor_video_id == "V3"
    jobs = db.exec(select(PostJob).order_by(PostJob.scheduled_at)).all()
    metas = {m.id: m.tiktok_video_id for m in db.exec(select(VideoMeta)).all()}
    assert len(jobs) == 3
    assert [metas[j.video_meta_id] for j in jobs] == ["V1", "V2", "V3"]
    spacing = jobs[1].scheduled_at - jobs[0].scheduled_at
    assert spacing == timedelta(hours=6)


def test_poll_skips_anchor_and_older(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    ch = TikTokChannel(username="creator", backfill_anchor_video_id="V2")
    db.add(ch)
    db.commit()
    db.refresh(ch)

    now = datetime.now(UTC)
    videos = [
        _fake_video("V3", now + timedelta(hours=1)),
        _fake_video("V2", now),  # anchor — must be skipped
    ]
    service = PostingService()
    monkeypatch.setattr(service.provider, "list_channel_videos", lambda _u, limit: videos)

    service.poll_new_videos(db, ch)

    metas = db.exec(select(VideoMeta)).all()
    assert [m.tiktok_video_id for m in metas] == ["V3"]
    # no pages mapped → post jobs not created, only metadata
    assert db.exec(select(PostJob)).all() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/services/test_posting_service.py -v`
Expected: FAIL — backfill still limited to 50 / 10-minute spacing / `backfill_remaining` attribute error later

- [ ] **Step 3: Rewrite `backfill_channel`**

```python
    def backfill_channel(self, db: Session, channel: TikTokChannel) -> None:
        videos = self.provider.list_channel_videos(channel.username, limit=None)
        if not videos or channel.id is None:
            return
        # newest-first from provider; newest video is "#0" — use as anchor
        newest = videos[0]
        if newest.create_time is None:
            newest = max(
                videos,
                key=lambda v: v.create_time or datetime(1970, 1, 1, tzinfo=UTC),
            )
        channel.backfill_anchor_video_id = newest.video_id
        pages = self.active_pages_for_channel(db, channel.id)
        now = datetime.now(UTC)
        interval = timedelta(hours=settings.BACKFILL_INTERVAL_HOURS)
        # oldest first, newest (anchor) last; anchor must be enqueued or it
        # is never posted (poll only picks up videos newer than the anchor)
        older = [v for v in videos if v.video_id != newest.video_id]
        queue_order = list(reversed(older)) + [newest]
        for i, vid in enumerate(queue_order):
            meta = self._upsert_meta(db, channel, vid, is_backfill=True)
            if not meta:
                continue
            self.enqueue_video(
                db,
                channel,
                meta,
                pages,
                scheduled_at=now + interval * i,
            )
        db.add(channel)
        db.commit()
```

- [ ] **Step 4: Remove the `backfill_remaining` set in `poll_new_videos`**

In `poll_new_videos`, the line `channel.backfill_remaining = max(0, ...)` lives in `backfill_channel` (removed above). Verify `poll_new_videos` has no `backfill_remaining` reference (it doesn't — it was only in `backfill_channel`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/services/test_posting_service.py -v`
Expected: PASS (4 existing + 2 new)

- [ ] **Step 6: Lint and typecheck**

Run: `cd backend && uv run ruff check --fix . && uv run ruff format . && uv run mypy .`
Expected: clean (note: `schemas.py` still references `backfill_remaining` — fixed in Task 4; run mypy only on services if needed)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/posting_service.py backend/tests/services/test_posting_service.py
git commit -m "feat: auto-backfill all videos with 6h spacing, anchor enqueued last"
```

---

### Task 4: Remove `backfill_remaining` — model, migration, schema, API, frontend

**Files:**
- Modify: `backend/app/models.py:16` (remove `backfill_remaining: int = 0`)
- Create: `backend/app/alembic/versions/<new>_drop_backfill_remaining.py`
- Modify: `backend/app/schemas.py:17-26` (`TikTokChannelRead`)
- Modify: `backend/app/api/routes/channels.py:27-35` (`_read_channel` tuple)
- Modify: `frontend/src/client/types.gen.ts:74`, `frontend/src/client/schemas.gen.ts:389,408` (generated — edit by hand after regenerating)
- Modify: `frontend/src/routes/_layout/channels.tsx:160-164` (remove Backfill column)
- Test: `backend/tests/test_models.py`, `backend/tests/api/test_routes.py`

**Interfaces:**
- Consumes: Task 3 removed the only writer of `backfill_remaining`.
- Produces: `TikTokChannel` without `backfill_remaining`; `TikTokChannelRead` without `backfill_remaining`; DB column dropped.

- [ ] **Step 1: Update model + schema + API**

- `models.py`: delete `backfill_remaining: int = 0`
- `schemas.py` `TikTokChannelRead`: delete `backfill_remaining: int` line
- `channels.py` `_read_channel`: remove `"backfill_remaining"` from the field tuple

- [ ] **Step 2: Write failing migration test**

Append to `backend/tests/test_models.py`:

```python
def test_backfill_remaining_column_dropped() -> None:
    from sqlalchemy import inspect
    from app.core.db import engine

    inspector = inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("tiktokchannel")}
    assert "backfill_remaining" not in columns
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_models.py -v`
Expected: FAIL — column still exists

- [ ] **Step 4: Generate the migration**

Run: `cd backend && uv run alembic revision --autogenerate -m "drop backfill_remaining"`
Expected: new file under `app/alembic/versions/` with `op.drop_column("tiktokchannel", "backfill_remaining")` in upgrade()

Verify the generated file contains only the drop (no spurious changes). If autogenerate reports model table diffs, inspect `env.py` / model changes.

- [ ] **Step 5: Apply migration to test DB and re-run test**

Run: `cd backend && uv run alembic upgrade head && uv run pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 6: Update frontend**

- Regenerate client: `cd frontend && bun run generate-client` (after ensuring backend openapi dump works: `bash ../scripts/generate-client.sh`)
- If regeneration is impractical in this environment, hand-edit:
  - `types.gen.ts`: remove `backfill_remaining: number;` and the `backfill_remaining` required entry
  - `schemas.gen.ts`: remove the `backfill_remaining` property object and its required entry
- `channels.tsx`: delete the column definition at lines 160-164 (the `accessorKey: "backfill_remaining"` block)

- [ ] **Step 7: Typecheck frontend**

Run: `cd frontend && bun run tsc --noEmit`
Expected: clean

- [ ] **Step 8: Full backend test + lint run**

Run: `cd backend && uv run pytest && uv run ruff check --fix . && uv run ruff format . && uv run mypy .`
Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add backend/app/models.py backend/app/schemas.py backend/app/api/routes/channels.py backend/app/alembic/versions/ frontend/src/client/ frontend/src/routes/_layout/channels.tsx backend/tests/test_models.py
git commit -m "refactor: drop backfill_remaining column and field"
```

---

### Task 5: Create `.env.example` with real values

**Files:**
- Create: `.env.example` (repo root)

**Interfaces:**
- Consumes: `.env` (existing local values), config.py keys
- Produces: `.env.example` — copy-paste-runnable; README will reference it (Task 7).

- [ ] **Step 1: Write `.env.example`**

Copy the current `.env` (real working local values) and append the new app settings:

```bash
# --- autoposter ---
# Domain / environment (used by Traefik + CORS)
DOMAIN=localhost
FRONTEND_HOST=http://localhost:5173
ENVIRONMENT=local
PROJECT_NAME=AutoPoster
STACK_NAME=autoposter

# Backend
BACKEND_CORS_ORIGINS="http://localhost,http://localhost:5173"
SECRET_KEY=changethis
FIRST_SUPERUSER=admin@example.com
FIRST_SUPERUSER_PASSWORD=changethis

# SMTP (leave empty for local; mailcatcher at :1080)
SMTP_HOST=
SMTP_USER=
SMTP_PASSWORD=
EMAILS_FROM_EMAIL=info@example.com
SMTP_TLS=True
SMTP_SSL=False
SMTP_PORT=587

# Postgres (local dev values — change for production)
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_DB=autoposter
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# App behavior
POLL_INTERVAL_MINUTES=30          # how often the scheduler checks TikTok for new videos
BACKFILL_INTERVAL_HOURS=6         # spacing between backfill posts (old videos)
MAX_ATTEMPTS=3                    # retries per failed post
RUN_SCHEDULER=true                # start the background scheduler with the API
GRAPH_VERSION=v21.0               # Facebook Graph API version

# TikTok anti-ban: export cookies from your browser (Netscape format,
# e.g. extension "Get cookies.txt") and point here. Empty = no cookies.
TIKTOK_COOKIES_FILE=

# Fernet key for encrypting Facebook access tokens (generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
ENCRYPTION_KEY=

# Docker images
DOCKER_IMAGE_BACKEND=backend
```

- [ ] **Step 2: Verify keys match config.py**

Run: `cd backend && uv run python -c "from app.core.config import settings; print(settings.model_dump().keys())"`
Expected: every key in `.env.example` either appears in the output or is a compose-only var (POSTGRES_*, SMTP_*, FIRST_SUPERUSER*, DOMAIN, FRONTEND_HOST, ENVIRONMENT, PROJECT_NAME, STACK_NAME, BACKEND_CORS_ORIGINS, SECRET_KEY, DOCKER_IMAGE_BACKEND)

- [ ] **Step 3: Verify app boots with `.env.example` as the env file**

Run: `cd backend && cp ../.env /tmp/env.bak && cp ../.env.example ../.env && uv run python -c "import app.main; print('ok')" && mv /tmp/env.bak ../.env`
Expected: prints ok (restores the real `.env` afterward)

- [ ] **Step 4: Commit**

```bash
git add .env.example
git commit -m "chore: add .env.example with working local values"
```

---

### Task 6: Delete template leftovers

**Files:**
- Delete: `backend/app/models.py.bak`
- Delete: `backend/app/frontend/` (stale build assets — already gitignored, delete from disk)
- Delete: `copier.yml` (copier template metadata)
- Delete: `frontend/src/components/Common/AuthLayout.tsx`
- Delete: `frontend/src/components/ui/password-input.tsx`

**Interfaces:**
- Consumes: design decision to remove template files not used by any route.

- [ ] **Step 1: Verify nothing imports the to-be-deleted frontend files**

Run: `cd frontend && rg "AuthLayout|password-input" src --include="*.tsx" --include="*.ts" -l | grep -v "AuthLayout.tsx\|password-input.tsx"`
Expected: no output

- [ ] **Step 2: Verify main.py doesn't serve `backend/app/frontend` in a way that breaks**

`backend/app/main.py:45-46` mounts `FRONTEND_DIR` only if it exists (`if FRONTEND_DIR.is_dir()`), so deleting the dir is safe; the Docker build copies fresh assets via `COPY --from=frontend-build` (backend/Dockerfile:54).

- [ ] **Step 3: Delete the files**

```bash
rm backend/app/models.py.bak
rm -rf backend/app/frontend
rm copier.yml
rm frontend/src/components/Common/AuthLayout.tsx
rm frontend/src/components/ui/password-input.tsx
```

- [ ] **Step 4: Verify nothing breaks**

Run: `cd backend && uv run pytest -q && uv run ruff check . && uv run mypy .`
Run: `cd frontend && bun run tsc --noEmit && bun run lint`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove template leftovers (models.py.bak, stale build, copier.yml, unused auth UI)"
```

---

### Task 7: README — cookie guide, env docs, backfill explanation

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: `.env.example` (Task 5), design decisions.

- [ ] **Step 1: Add an "Environment" section** after the setup instructions, documenting:
  - `.env` is the real config file; `.env.example` ships working local values
  - Table of app-specific vars: `POLL_INTERVAL_MINUTES`, `BACKFILL_INTERVAL_HOURS`, `MAX_ATTEMPTS`, `RUN_SCHEDULER`, `GRAPH_VERSION`, `TIKTOK_COOKIES_FILE`, `ENCRYPTION_KEY` (with generation one-liner)
- [ ] **Step 2: Add a "Chống chặn TikTok" section** (in Vietnamese, matching README language):
  - How the scheduler works (auto every `POLL_INTERVAL_MINUTES`, no manual button needed)
  - Backfill: auto on channel add, all old videos, one every `BACKFILL_INTERVAL_HOURS`
  - Cookies: install "Get cookies.txt" extension → export for tiktok.com → save as `backend/cookies/tiktok.txt` (or any path) → set `TIKTOK_COOKIES_FILE` in `.env`
  - Warnings: using logged-in cookies means TikTok may flag the account; keep poll interval ≥ 30 min; a Slardar WAF block (`Unable to extract secondary user ID`) resolves by waiting or switching IP/proxy
- [ ] **Step 3: Verify markdown renders (no broken links)**

Run: `grep -c "TIKTOK_COOKIES_FILE" README.md && grep -c "BACKFILL_INTERVAL_HOURS" README.md`
Expected: ≥1 each

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: env vars, cookie setup, backfill explanation in README"
```

---

### Task 8: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Backend full suite + lint + types**

Run: `cd backend && uv run pytest && uv run ruff check --fix . && uv run ruff format . && uv run mypy .`
Expected: all pass

- [ ] **Step 2: Frontend typecheck + lint**

Run: `cd frontend && bun run tsc --noEmit && bun run lint`
Expected: clean

- [ ] **Step 3: Smoke test — boot app and hit health/API**

Run: `cd backend && uv run python -c "from fastapi.testclient import TestClient; from app.main import app; c = TestClient(app); print(c.get('/api/v1/tiktok-channels').status_code)"`
Expected: 200 (empty list)

- [ ] **Step 4: Verify git history**

Run: `git log --oneline -8`
Expected: the 7 commits from Tasks 1-7

---

## Self-Review Notes

- **Spec coverage:** backfill (T3), anti-ban cookies (T2), `.env.example` (T5), config-in-env (T1), template cleanup (T6), README (T7). Design's "no Celery" decision is documented in the Goal/Architecture — no code task needed.
- **`is_backfill` kept:** per spec, remains on `VideoMeta`, no task needed.
- **Frontend client regeneration:** Task 4 prefers `bun run generate-client`; hand-edit fallback documented because the generator needs a live backend/DB.
- **`utils.ts` merge:** checked — `src/utils.ts` (handleError) and `src/lib/utils.ts` (cn) are distinct, both used; no merge.
