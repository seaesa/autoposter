from __future__ import annotations

import asyncio
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlmodel import Session, select

from app.core.config import settings
from app.core.logging import get_logger
from app.models import (
    ChannelPageMapping,
    FacebookPage,
    PostJob,
    TikTokChannel,
    VideoMeta,
)
from app.services.facebook_client import FacebookClient
from app.services.quota import QuotaGuard
from app.services.tiktok_provider import TikTokProvider, TikTokVideo

logger = get_logger(__name__)


def _unwrap_error(exc: Exception) -> str:
    # tenacity's RetryError hides the underlying HTTPStatusError from httpx
    from tenacity import RetryError  # noqa: PLC0415

    while isinstance(exc, RetryError):
        last = exc.last_attempt.exception()
        if last is None or not isinstance(last, Exception):
            break
        exc = last
    return str(exc)


class PostingService:
    def __init__(self) -> None:
        self.provider = TikTokProvider()
        self.facebook = FacebookClient()
        self.quota = QuotaGuard()

    # ---- enqueue ----
    def enqueue_video(
        self,
        db: Session,
        channel: TikTokChannel,
        meta: VideoMeta,
        pages: list[FacebookPage],
        scheduled_at: datetime | None = None,
    ) -> list[PostJob]:
        jobs: list[PostJob] = []
        for page in pages:
            exists = db.exec(
                select(PostJob).where(
                    PostJob.video_meta_id == meta.id,
                    PostJob.facebook_page_id == page.id,
                )
            ).first()
            if exists:
                continue
            job = PostJob(
                video_meta_id=meta.id,
                facebook_page_id=page.id,
                title=meta.title,
                description=meta.description,
                status="pending",
                scheduled_at=scheduled_at or datetime.now(UTC),
            )
            db.add(job)
            jobs.append(job)
        if jobs:
            logger.debug(
                "enqueued {} new job(s) for video {} (channel {})",
                len(jobs),
                meta.id,
                channel.id,
            )
        db.commit()
        return jobs

    def active_pages_for_channel(
        self, db: Session, channel_id: int
    ) -> list[FacebookPage]:
        stmt = (
            select(FacebookPage)
            .select_from(FacebookPage, ChannelPageMapping)
            .where(
                FacebookPage.id == ChannelPageMapping.facebook_page_id,
                ChannelPageMapping.tiktok_channel_id == channel_id,
                ChannelPageMapping.is_active == True,  # noqa: E712
                FacebookPage.is_active == True,  # noqa: E712
            )
        )
        return list(db.exec(stmt).all())

    # ---- backfill ----
    def backfill_channel(self, db: Session, channel: TikTokChannel) -> None:
        logger.info("backfill start: channel={} (id={})", channel.username, channel.id)
        videos = self.provider.list_channel_videos(channel.username, limit=None)
        if not videos or channel.id is None:
            logger.warning(
                "backfill aborted: no videos fetched for channel={}", channel.username
            )
            return
        # newest-first from provider; newest video is "#0" — use as anchor
        newest = videos[0]
        if newest.create_time is None:
            newest = max(
                videos,
                key=lambda v: v.create_time or datetime(1970, 1, 1, tzinfo=UTC),
            )
        channel.backfill_anchor_video_id = newest.video_id
        pages = self.active_pages_for_channel(db, channel.id)
        now = datetime.now(UTC)
        interval = timedelta(hours=settings.BACKFILL_INTERVAL_HOURS)
        # oldest first, newest (anchor) last; anchor must be enqueued or it
        # is never posted (poll only picks up videos newer than the anchor)
        older = [v for v in videos if v.video_id != newest.video_id]
        queue_order = list(reversed(older)) + [newest]
        enqueued = 0
        for i, vid in enumerate(queue_order):
            meta = self._upsert_meta(db, channel, vid, is_backfill=True)
            if not meta:
                continue
            jobs = self.enqueue_video(
                db,
                channel,
                meta,
                pages,
                scheduled_at=now + interval * i,
            )
            enqueued += len(jobs)
        db.add(channel)
        db.commit()
        logger.info(
            "backfill done: channel={} videos={} enqueued={} anchor={} interval={}h",
            channel.username,
            len(videos),
            enqueued,
            newest.video_id,
            settings.BACKFILL_INTERVAL_HOURS,
        )

    # ---- poll ----
    def poll_new_videos(self, db: Session, channel: TikTokChannel) -> None:
        videos = self.provider.list_channel_videos(channel.username, limit=30)
        if not videos:
            channel.last_checked_at = datetime.now(UTC)
            db.add(channel)
            db.commit()
            logger.debug("poll: no videos for channel={}", channel.username)
            return
        if channel.id is None:
            return
        pages = self.active_pages_for_channel(db, channel.id)
        last_checked = channel.last_checked_at
        # DB trả datetime naive; create_time từ yt-dlp là aware (UTC)
        if last_checked is not None and last_checked.tzinfo is None:
            last_checked = last_checked.replace(tzinfo=UTC)
        for vid in videos:
            # skip anything older than the backfill anchor (already backfilled)
            if (
                channel.backfill_anchor_video_id
                and vid.video_id == channel.backfill_anchor_video_id
            ):
                break
            if (
                not channel.backfill_anchor_video_id
                and vid.create_time
                and last_checked
                and vid.create_time <= last_checked
            ):
                break
            meta = self._upsert_meta(db, channel, vid, is_backfill=False)
            if meta:
                self.enqueue_video(db, channel, meta, pages)
        channel.last_checked_at = datetime.now(UTC)
        db.add(channel)
        db.commit()
        logger.debug(
            "poll: channel={} videos={} last_checked={}",
            channel.username,
            len(videos),
            channel.last_checked_at,
        )

    # ---- worker ----
    async def process_due_jobs(self, db: Session) -> dict[str, int]:
        now = datetime.now(UTC)
        jobs = db.exec(
            select(PostJob)
            .where(PostJob.status == "pending", PostJob.scheduled_at <= now)
            .order_by(PostJob.scheduled_at)  # type: ignore[arg-type]
            .limit(5)
        ).all()
        logger.info("worker: {} due job(s) found", len(jobs))
        counts: dict[str, int] = {
            "posted": 0,
            "failed": 0,
            "rescheduled": 0,
            "skipped": 0,
        }
        for job in jobs:
            page = db.get(FacebookPage, job.facebook_page_id)
            meta = db.get(VideoMeta, job.video_meta_id)
            if page is None or not page.is_active:
                job.status = "skipped"
                db.add(job)
                db.commit()
                counts["skipped"] += 1
                logger.warning("worker: job {} skipped (page inactive/missing)", job.id)
                continue
            if meta is None:
                job.status = "skipped"
                job.error_message = "video metadata missing"
                db.add(job)
                db.commit()
                counts["skipped"] += 1
                logger.warning("worker: job {} skipped (meta missing)", job.id)
                continue
            next_at = self.quota.next_allowed(db, page, now)
            if next_at > now:
                job.status = "pending"
                job.scheduled_at = next_at
                db.add(job)
                db.commit()
                counts["rescheduled"] += 1
                logger.info(
                    "worker: job {} rescheduled to {} (quota on page {})",
                    job.id,
                    next_at,
                    page.page_id,
                )
                continue
            job.status = "processing"
            db.add(job)
            db.commit()
            try:
                if not meta.download_url:
                    raise ValueError("download URL missing for video")
                with tempfile.TemporaryDirectory() as tmp:
                    logger.debug(
                        "worker: job {} downloading {}", job.id, meta.download_url
                    )
                    fpath = await asyncio.to_thread(
                        self.provider.download_video, meta.download_url or "", Path(tmp)
                    )
                    token = page.access_token
                    post_id = await self.facebook.upload_video(
                        page.page_id,
                        token,
                        fpath,
                        job.title or meta.title,
                        job.description or meta.description,
                    )
                job.status = "posted"
                job.posted_at = datetime.now(UTC)
                job.facebook_post_id = post_id
                job.facebook_url = (
                    f"https://www.facebook.com/{page.page_id}/posts/{post_id}"
                )
                job.attempts = 0
                db.add(job)
                db.commit()
                counts["posted"] += 1
                logger.info(
                    "worker: job {} posted to page {} (facebook post {})",
                    job.id,
                    page.page_id,
                    post_id,
                )
            except Exception as exc:  # noqa: BLE001
                job.attempts += 1
                job.error_message = _unwrap_error(exc)
                job.status = (
                    "failed" if job.attempts >= settings.MAX_ATTEMPTS else "pending"
                )
                job.scheduled_at = now + timedelta(seconds=2 ** (job.attempts - 1))
                db.add(job)
                db.commit()
                counts["failed" if job.status == "failed" else "rescheduled"] += 1
                logger.error(
                    "worker: job {} attempt {}/{} failed (will {}): {}",
                    job.id,
                    job.attempts,
                    settings.MAX_ATTEMPTS,
                    "give up" if job.status == "failed" else "retry",
                    job.error_message,
                )
            finally:
                job.updated_at = datetime.now(UTC)
                db.add(job)
                db.commit()
        return counts

    def _upsert_meta(
        self,
        db: Session,
        channel: TikTokChannel,
        vid: TikTokVideo,
        is_backfill: bool,
    ) -> VideoMeta | None:
        if not vid.video_id:
            return None
        meta = db.exec(
            select(VideoMeta).where(
                VideoMeta.tiktok_channel_id == channel.id,
                VideoMeta.tiktok_video_id == vid.video_id,
            )
        ).first()
        if meta is None:
            meta = VideoMeta(
                tiktok_video_id=vid.video_id,
                tiktok_channel_id=channel.id,
                title=vid.title or "",
                description=vid.description or "",
                thumbnail_url=vid.thumbnail_url,
                create_time=vid.create_time,
                download_url=vid.download_url,
                is_backfill=is_backfill,
            )
            db.add(meta)
            db.commit()
            db.refresh(meta)
        elif vid.download_url and not meta.download_url:
            meta.download_url = vid.download_url
            db.add(meta)
            db.commit()
            db.refresh(meta)
        return meta
