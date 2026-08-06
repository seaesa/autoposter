import asyncio

import pytest
from sqlmodel import Session

from app.core.db import engine
from app.models import TikTokChannel
from app.services.posting_service import PostingService
from app.services.scheduler_service import SchedulerService


def test_status_default() -> None:
    s = SchedulerService(run_interval_seconds=60)
    info = s.status()
    assert "last_poll" in info and "last_run" in info and "running" in info
    assert info["running"] is False


@pytest.mark.anyio
async def test_run_once_polls_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(engine) as db:
        db.add(TikTokChannel(username="creator"))
        db.commit()

    s = SchedulerService(run_interval_seconds=60)

    async def fake_process_due_jobs(
        _self: PostingService, _db: Session
    ) -> dict[str, int]:
        return {"posted": 0, "failed": 0, "rescheduled": 0, "skipped": 0}

    def fake_poll(_self: PostingService, _db: Session, _channel: TikTokChannel) -> None:
        return None

    monkeypatch.setattr(PostingService, "poll_new_videos", fake_poll)
    monkeypatch.setattr(PostingService, "process_due_jobs", fake_process_due_jobs)

    counts = await s.run_once()

    assert counts["channels"] >= 1
    assert "posted" in counts and "failed" in counts
    assert s.status()["last_run"] is not None


def test_run_now_calls_run_once(monkeypatch: pytest.MonkeyPatch) -> None:
    s = SchedulerService(run_interval_seconds=60)
    ran: list[dict[str, int]] = []

    async def fake_run_once(_posting: PostingService | None = None) -> dict[str, int]:
        ran.append({})
        return {"channels": 1, "posted": 0, "failed": 0}

    monkeypatch.setattr(s, "run_once", fake_run_once)
    asyncio.run(s.run_now())
    assert len(ran) == 1
