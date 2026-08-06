from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.db import get_session
from app.models import ChannelPageMapping
from app.schemas import MappingCreate

router = APIRouter(prefix="/mappings", tags=["mappings"])


@router.post("")
def create_mapping(
    payload: MappingCreate, db: Session = Depends(get_session)
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
    return {"id": m.id}


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
