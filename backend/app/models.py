from datetime import UTC, datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class TikTokChannel(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    display_name: str | None = None
    last_checked_at: datetime | None = None
    backfill_anchor_video_id: str | None = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class FacebookPage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    page_id: str = Field(index=True, unique=True)
    name: str
    access_token_encrypted: str
    max_posts_per_day: int = 10
    min_interval_minutes: int = 10
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class ChannelPageMapping(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "tiktok_channel_id", "facebook_page_id", name="uq_mapping_pair"
        ),
    )
    id: int | None = Field(default=None, primary_key=True)
    tiktok_channel_id: int = Field(foreign_key="tiktokchannel.id", index=True)
    facebook_page_id: int = Field(foreign_key="facebookpage.id", index=True)
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class VideoMeta(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "tiktok_channel_id", "tiktok_video_id", name="uq_video_channel"
        ),
    )
    id: int | None = Field(default=None, primary_key=True)
    tiktok_video_id: str = Field(index=True)
    tiktok_channel_id: int = Field(foreign_key="tiktokchannel.id", index=True)
    title: str = ""
    description: str = ""
    thumbnail_url: str | None = None
    create_time: datetime | None = None
    download_url: str | None = None
    is_backfill: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class PostJob(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("video_meta_id", "facebook_page_id", name="uq_job_video_page"),
    )
    id: int | None = Field(default=None, primary_key=True)
    video_meta_id: int = Field(foreign_key="videometa.id", index=True)
    facebook_page_id: int = Field(foreign_key="facebookpage.id", index=True)
    status: str = Field(
        default="pending"
    )  # pending|processing|posted|failed|skipped|deleted
    attempts: int = 0
    error_message: str | None = None
    scheduled_at: datetime = Field(default_factory=utcnow)
    posted_at: datetime | None = None
    facebook_post_id: str | None = None
    facebook_url: str | None = None
    title: str = ""  # editable copy at enqueue time
    description: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
