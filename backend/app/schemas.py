from datetime import datetime
from typing import Any

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
    pages: list[dict[str, Any]] = []


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
    access_token_encrypted: str | None = None
    max_posts_per_day: int
    min_interval_minutes: int
    is_active: bool
    channels: list[dict[str, Any]] = []


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
    channel: str | None = None  # username (joined)
    page: str | None = None  # page name (joined)
