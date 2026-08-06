from datetime import UTC, datetime, time
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import DateTime, cast
from sqlmodel import Session, func, select

from app.core.db import get_session
from app.models import PostJob, TikTokChannel
from app.services.scheduler_service import scheduler

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("")
def get_stats(db: Session = Depends(get_session)) -> dict[str, Any]:
    now = datetime.now(UTC)
    start = datetime.combine(now.date(), time.min, tzinfo=UTC)
    today_posted = db.exec(
        select(func.count(PostJob.id)).where(  # type: ignore[arg-type]
            PostJob.status == "posted", cast(PostJob.posted_at, DateTime) >= start
        )
    ).one()
    today_pending = db.exec(
        select(func.count(PostJob.id)).where(  # type: ignore[arg-type]
            PostJob.status == "pending"
        )
    ).one()
    channels = len(db.exec(select(TikTokChannel)).all())
    return {
        "today_posted": today_posted,
        "today_pending": today_pending,
        "channels": channels,
        "scheduler": scheduler.status(),
    }
