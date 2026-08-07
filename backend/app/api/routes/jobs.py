from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import DateTime, cast
from sqlmodel import Session, select

from app.core.db import get_session
from app.models import FacebookPage, PostJob, TikTokChannel, VideoMeta
from app.schemas import PostJobRead, PostJobUpdate
from app.services.facebook_client import FacebookClient

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _to_read(db: Session, job: PostJob) -> PostJobRead:
    meta = db.get(VideoMeta, job.video_meta_id)
    page = db.get(FacebookPage, job.facebook_page_id)
    channel = db.get(TikTokChannel, meta.tiktok_channel_id) if meta else None
    read = PostJobRead.model_validate(job)
    read.channel = channel.username if channel else None
    read.page = page.name if page else None
    return read


@router.get("", response_model=list[PostJobRead])
def list_jobs(
    channel_id: int | None = None,
    page_id: int | None = None,
    status: str | None = None,
    date: str | None = None,
    db: Session = Depends(get_session),
) -> list[PostJobRead]:
    stmt = select(PostJob)
    if channel_id:
        stmt = stmt.join(VideoMeta).where(VideoMeta.tiktok_channel_id == channel_id)
    if page_id:
        stmt = stmt.where(PostJob.facebook_page_id == page_id)
    if status:
        stmt = stmt.where(PostJob.status == status)
    if date:
        day = datetime.fromisoformat(date)
        stmt = stmt.where(
            cast(PostJob.posted_at, DateTime) >= day,
            cast(PostJob.posted_at, DateTime) < day + timedelta(days=1),
        )
    stmt = stmt.order_by(PostJob.scheduled_at.desc())  # type: ignore[attr-defined]
    jobs = db.exec(stmt).all()
    return [_to_read(db, job) for job in jobs]


@router.patch("/{job_id}", response_model=PostJobRead)
async def update_job(
    job_id: int, payload: PostJobUpdate, db: Session = Depends(get_session)
) -> PostJobRead:
    job = db.get(PostJob, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(job, k, v)
    job.updated_at = datetime.now(UTC)
    db.add(job)
    if job.facebook_post_id and job.status == "posted":
        page = db.get(FacebookPage, job.facebook_page_id)
        if page:
            token = page.access_token
            try:
                await FacebookClient().update_post(
                    job.facebook_post_id, token, job.title, job.description
                )
            except Exception as exc:  # noqa: BLE001
                job.error_message = f"fb update failed: {exc}"
    db.commit()
    db.refresh(job)
    return _to_read(db, job)


@router.delete("/{job_id}")
async def delete_job(job_id: int, db: Session = Depends(get_session)) -> dict[str, Any]:
    job = db.get(PostJob, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job.facebook_post_id and job.status == "posted":
        page = db.get(FacebookPage, job.facebook_page_id)
        if page:
            try:
                await FacebookClient().delete_post(
                    job.facebook_post_id,
                    page.access_token,
                )
            except Exception as exc:  # noqa: BLE001
                job.error_message = f"fb delete failed: {exc}"
    job.status = "deleted"
    job.updated_at = datetime.now(UTC)
    db.add(job)
    db.commit()
    return {"ok": True}
