from datetime import datetime

from sqlmodel import Field, SQLModel


class TikTokChannel(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    display_name: str | None = None
    last_checked: datetime | None = Field(default=None)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FacebookPage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    page_id: str = Field(index=True, unique=True)
    name: str
    access_token_encrypted: str = Field(description="Encrypted long-lived access token")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChannelPageMapping(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    tiktok_channel_id: int = Field(foreign_key="tiktokchannel.id")
    facebook_page_id: int = Field(foreign_key="facebookpage.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        # Unique constraint to prevent duplicate mappings
        unique_together = [("tiktok_channel_id", "facebook_page_id")]


class PostedVideo(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    tiktok_video_id: str = Field(index=True, unique=True)
    facebook_post_id: str | None = Field(default=None, index=True)
    tiktok_channel_id: int = Field(foreign_key="tiktokchannel.id")
    facebook_page_id: int = Field(foreign_key="facebookpage.id")
    title: str
    description: str
    posted_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="success")  # success/failed/deleted
    error_message: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FailedPost(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    tiktok_video_id: str = Field(index=True)
    facebook_page_id: int = Field(foreign_key="facebookpage.id")
    title: str
    description: str
    error_message: str
    attempt_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
