from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.services.posting_service import PostingService


class SchedulerService:
    def __init__(self, run_interval_seconds: int | None = None) -> None:
        self.run_interval = run_interval_seconds or settings.POLL_INTERVAL_MINUTES * 60
        self._task: asyncio.Task[None] | None = None
        self._state: dict[str, Any] = {
            "running": False,
            "last_poll": None,
            "last_run": None,
        }

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._state["running"] = False
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def run_now(self) -> None:
        await self.run_once()

    async def _loop(self) -> None:
        posting = PostingService()
        self._state["running"] = True
        while True:
            try:
                await self.run_once(posting)
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(self.run_interval)

    async def run_once(self, posting: PostingService | None = None) -> dict[str, int]:
        from sqlmodel import Session, select

        from app.core.db import engine
        from app.models import TikTokChannel

        posting = posting or PostingService()
        counts: dict[str, int] = {"channels": 0, "posted": 0, "failed": 0}
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
        self._state["last_poll"] = datetime.now(UTC)
        self._state["last_run"] = datetime.now(UTC)
        return counts

    def status(self) -> dict[str, Any]:
        return dict(self._state)


# module-level singleton consumed by API routes (scheduler.py, stats.py)
scheduler = SchedulerService()
