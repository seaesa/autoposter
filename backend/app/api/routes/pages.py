from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.crypto import encrypt_token
from app.core.db import get_session
from app.models import ChannelPageMapping, FacebookPage, TikTokChannel
from app.schemas import FacebookPageCreate, FacebookPageRead, FacebookPageUpdate

router = APIRouter(prefix="/facebook-pages", tags=["facebook-pages"])


def _read_page(db: Session, page: FacebookPage) -> FacebookPageRead:
    query = (
        select(TikTokChannel)
        .select_from(TikTokChannel, ChannelPageMapping)
        .where(
            TikTokChannel.id == ChannelPageMapping.tiktok_channel_id,
            ChannelPageMapping.facebook_page_id == page.id,
        )
    )
    channels = db.exec(query).all()
    read = FacebookPageRead.model_validate(page)
    read.channels = [{"id": c.id, "username": c.username} for c in channels]
    return read


@router.get("", response_model=list[FacebookPageRead])
def list_pages(db: Session = Depends(get_session)) -> list[FacebookPageRead]:
    return [_read_page(db, p) for p in db.exec(select(FacebookPage)).all()]


@router.post("", response_model=FacebookPageRead)
def create_page(
    payload: FacebookPageCreate, db: Session = Depends(get_session)
) -> FacebookPageRead:
    if db.exec(
        select(FacebookPage).where(FacebookPage.page_id == payload.page_id)
    ).first():
        raise HTTPException(409, "page already exists")
    page = FacebookPage(
        page_id=payload.page_id,
        name=payload.name,
        access_token_encrypted=encrypt_token(payload.access_token),
        max_posts_per_day=payload.max_posts_per_day,
        min_interval_minutes=payload.min_interval_minutes,
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    return _read_page(db, page)


@router.patch("/{page_id}", response_model=FacebookPageRead)
def update_page(
    page_id: int,
    payload: FacebookPageUpdate,
    db: Session = Depends(get_session),
) -> FacebookPageRead:
    page = db.get(FacebookPage, page_id)
    if not page:
        raise HTTPException(404, "page not found")
    data = payload.model_dump(exclude_unset=True)
    if "access_token" in data:
        data["access_token_encrypted"] = encrypt_token(data.pop("access_token"))
    for k, v in data.items():
        setattr(page, k, v)
    db.add(page)
    db.commit()
    db.refresh(page)
    return _read_page(db, page)


@router.delete("/{page_id}")
def delete_page(page_id: int, db: Session = Depends(get_session)) -> dict[str, Any]:
    page = db.get(FacebookPage, page_id)
    if not page:
        raise HTTPException(404, "page not found")
    db.delete(page)
    db.commit()
    return {"ok": True}
