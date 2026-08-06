from datetime import UTC, datetime

from sqlmodel import Session

from app.models import (
    TikTokChannel,
    VideoMeta,
)


def _utc() -> datetime:
    return datetime.now(UTC)


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
        assert False, "expected IntegrityError"
    except Exception:
        db.rollback()
