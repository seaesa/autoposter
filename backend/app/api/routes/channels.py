from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session, select

from app.core.db import get_session
from app.models import ChannelPageMapping, FacebookPage, TikTokChannel
from app.schemas import TikTokChannelCreate, TikTokChannelRead, TikTokChannelUpdate
from app.services.posting_service import PostingService

router = APIRouter(prefix="/tiktok-channels", tags=["tiktok-channels"])


def _read_channel(db: Session, ch: TikTokChannel) -> TikTokChannelRead:
    query = (
        select(FacebookPage)
        .select_from(FacebookPage, ChannelPageMapping)
        .where(
            FacebookPage.id == ChannelPageMapping.facebook_page_id,
            ChannelPageMapping.tiktok_channel_id == ch.id,
        )
    )
    pages = db.exec(query).all()
    return TikTokChannelRead(
        **{
            k: getattr(ch, k)
            for k in (
                "id",
                "username",
                "display_name",
                "last_checked_at",
                "backfill_anchor_video_id",
                "backfill_remaining",
                "is_active",
            )
        },
        pages=[{"id": p.id, "name": p.name} for p in pages],
    )


@router.get("", response_model=list[TikTokChannelRead])
def list_channels(db: Session = Depends(get_session)) -> list[TikTokChannelRead]:
    return [_read_channel(db, ch) for ch in db.exec(select(TikTokChannel)).all()]


@router.post("", response_model=TikTokChannelRead)
def create_channel(
    payload: TikTokChannelCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_session),
) -> TikTokChannelRead:
    if db.exec(
        select(TikTokChannel).where(TikTokChannel.username == payload.username)
    ).first():
        raise HTTPException(409, "channel already exists")
    ch = TikTokChannel(username=payload.username, display_name=payload.display_name)
    db.add(ch)
    db.commit()
    db.refresh(ch)
    if ch.id is not None:
        background.add_task(_run_backfill, ch.id)
    return _read_channel(db, ch)


@router.patch("/{channel_id}", response_model=TikTokChannelRead)
def update_channel(
    channel_id: int,
    payload: TikTokChannelUpdate,
    db: Session = Depends(get_session),
) -> TikTokChannelRead:
    ch = db.get(TikTokChannel, channel_id)
    if not ch:
        raise HTTPException(404, "channel not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(ch, k, v)
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return _read_channel(db, ch)


@router.delete("/{channel_id}")
def delete_channel(
    channel_id: int, db: Session = Depends(get_session)
) -> dict[str, Any]:
    ch = db.get(TikTokChannel, channel_id)
    if not ch:
        raise HTTPException(404, "channel not found")
    db.delete(ch)
    db.commit()
    return {"ok": True}


def _run_backfill(channel_id: int) -> None:
    from sqlmodel import Session

    from app.core.db import engine

    with Session(engine) as db:
        channel = db.get(TikTokChannel, channel_id)
        if channel:
            PostingService().backfill_channel(db, channel)
