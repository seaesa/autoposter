from datetime import UTC, datetime

from sqlmodel import Session

from app.models import (
    TikTokChannel,
    VideoMeta,
)


def _utc() -> datetime:
    return datetime.now(UTC)


def test_channel_creation(db: Session) -> None:
    ch = TikTokChannel(username="user1", display_name="User One")
    db.add(ch)
    db.commit()
    assert ch.id is not None
    assert ch.is_active is True


def test_backfill_remaining_column_dropped() -> None:
    from sqlalchemy import inspect

    from app.core.db import engine

    inspector = inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("tiktokchannel")}
    assert "backfill_remaining" not in columns


def test_video_meta_unique_per_channel(db: Session) -> None:
    ch = TikTokChannel(username="user2")
    db.add(ch)
    db.commit()
    db.add(
        VideoMeta(
            tiktok_video_id="123", tiktok_channel_id=ch.id, title="t", description=""
        )
    )
    db.commit()
    db.add(
        VideoMeta(
            tiktok_video_id="123", tiktok_channel_id=ch.id, title="t2", description=""
        )
    )
    # second insert of same (channel, video) should raise IntegrityError
    try:
        db.commit()
        raise AssertionError("expected IntegrityError")
    except Exception:
        db.rollback()
