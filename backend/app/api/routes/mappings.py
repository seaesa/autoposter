from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session, select

from app.core.db import get_session
from app.models import ChannelPageMapping, PostJob, TikTokChannel, VideoMeta
from app.schemas import MappingCreate
from app.services.posting_service import PostingService

router = APIRouter(prefix="/mappings", tags=["mappings"])


@router.post("")
def create_mapping(
    payload: MappingCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    exists = db.exec(
        select(ChannelPageMapping).where(
            ChannelPageMapping.tiktok_channel_id == payload.tiktok_channel_id,
            ChannelPageMapping.facebook_page_id == payload.facebook_page_id,
        )
    ).first()
    if exists:
        raise HTTPException(409, "mapping already exists")
    m = ChannelPageMapping(
        tiktok_channel_id=payload.tiktok_channel_id,
        facebook_page_id=payload.facebook_page_id,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    # lần đầu map page cho channel: backfill có thể đã chạy khi chưa có
    # page nào → 0 job enqueue, anchor set trước mọi video → poll bỏ qua
    # toàn bộ. Re-backfill để video đã upsert được xếp lịch đăng.
    channel = db.get(TikTokChannel, payload.tiktok_channel_id)
    if channel is not None and channel.id is not None:
        meta_ids = db.exec(
            select(VideoMeta.id).where(VideoMeta.tiktok_channel_id == channel.id)
        ).all()
        has_jobs = False
        for meta_id in meta_ids:
            if db.exec(
                select(PostJob.id)
                .where(PostJob.video_meta_id == meta_id)
                .limit(1)
            ).first():
                has_jobs = True
                break
        if not has_jobs:
            background.add_task(_run_backfill, channel.id)
    return {"id": m.id}


def _run_backfill(channel_id: int) -> None:
    from sqlmodel import Session as _Session

    from app.core.db import engine

    with _Session(engine) as db:
        channel = db.get(TikTokChannel, channel_id)
        if channel:
            PostingService().backfill_channel(db, channel)


@router.delete("/{mapping_id}")
def delete_mapping(
    mapping_id: int, db: Session = Depends(get_session)
) -> dict[str, Any]:
    m = db.get(ChannelPageMapping, mapping_id)
    if not m:
        raise HTTPException(404, "mapping not found")
    db.delete(m)
    db.commit()
    return {"ok": True}
