from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.core import crypto
from app.models import (
    ChannelPageMapping,
    FacebookPage,
    PostJob,
    TikTokChannel,
    VideoMeta,
)
from app.services.posting_service import PostingService
from app.services.tiktok_provider import TikTokVideo


def _seed(db: Session) -> tuple[TikTokChannel, FacebookPage]:
    page = FacebookPage(
        page_id="P1",
        name="Page one",
        access_token_encrypted=crypto.encrypt_token("tok"),
        max_posts_per_day=10,
        min_interval_minutes=10,
    )
    ch = TikTokChannel(username="creator")
    db.add_all([page, ch])
    db.commit()
    db.refresh(page)
    db.refresh(ch)
    db.add(ChannelPageMapping(tiktok_channel_id=ch.id, facebook_page_id=page.id))
    db.commit()
    return ch, page


def _upsert_raw(db: Session, ch: TikTokChannel) -> VideoMeta:
    meta = VideoMeta(
        tiktok_video_id="V1",
        tiktok_channel_id=ch.id,
        title="T",
        description="D",
        create_time=datetime.now(UTC),
        download_url="https://tiktok.com/@c/video/1",
    )
    db.add(meta)
    db.commit()
    db.refresh(meta)
    return meta


def test_enqueue_deduplicates(db: Session) -> None:
    ch, page = _seed(db)
    meta = _upsert_raw(db, ch)
    service = PostingService()
    jobs = service.enqueue_video(db, ch, meta, [page])
    assert len(jobs) == 1
    jobs2 = service.enqueue_video(db, ch, meta, [page])
    assert jobs2 == []
    assert db.get(PostJob, jobs[0].id).status == "pending"  # type: ignore[union-attr]


def _write_fake_mp4(dest_dir: Path) -> Path:
    p = dest_dir / "v.mp4"
    p.write_bytes(b"x")
    return p


@pytest.mark.anyio
async def test_process_due_jobs_posts(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    ch, page = _seed(db)
    meta = _upsert_raw(db, ch)
    service = PostingService()

    job = service.enqueue_video(db, ch, meta, [page])[0]

    def fake_download(_url: str, dest_dir: Path) -> Path:
        return _write_fake_mp4(dest_dir)

    async def fake_upload(
        _page_id: str,
        _token: str,
        _file_path: Path,
        _title: str,
        _description: str,
    ) -> str:
        return "fb_post_1"

    monkeypatch.setattr(service.provider, "download_video", fake_download)
    monkeypatch.setattr(service.facebook, "upload_video", fake_upload)

    result = await service.process_due_jobs(db)
    assert result["posted"] == 1
    row = db.get(PostJob, job.id)
    assert row is not None
    assert row.status == "posted"
    assert row.facebook_post_id == "fb_post_1"


def _fake_video(vid: str, ts: datetime) -> TikTokVideo:
    return TikTokVideo(
        video_id=vid,
        title=f"title {vid}",
        description="",
        thumbnail_url=None,
        create_time=ts,
        download_url=f"https://tiktok.com/v/{vid}",
    )


def _seed_page(db: Session) -> FacebookPage:
    page = FacebookPage(
        page_id="P1",
        name="Page one",
        access_token_encrypted=crypto.encrypt_token("tok"),
        max_posts_per_day=10,
        min_interval_minutes=10,
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


def test_backfill_enqueues_all_videos_oldest_first(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    ch = TikTokChannel(username="creator")
    db.add(ch)
    db.commit()
    db.refresh(ch)
    page = _seed_page(db)
    db.add(ChannelPageMapping(tiktok_channel_id=ch.id, facebook_page_id=page.id))
    db.commit()

    now = datetime.now(UTC)
    videos = [
        _fake_video("V3", now),
        _fake_video("V2", now - timedelta(days=1)),
        _fake_video("V1", now - timedelta(days=2)),
    ]

    service = PostingService()
    monkeypatch.setattr(
        service.provider, "list_channel_videos", lambda _u, limit: videos
    )

    service.backfill_channel(db, ch)

    db.refresh(ch)
    assert ch.backfill_anchor_video_id == "V3"
    jobs = db.exec(select(PostJob).order_by(PostJob.scheduled_at)).all()
    metas = {m.id: m.tiktok_video_id for m in db.exec(select(VideoMeta)).all()}
    assert len(jobs) == 3
    assert [metas[j.video_meta_id] for j in jobs] == ["V1", "V2", "V3"]
    spacing = jobs[1].scheduled_at - jobs[0].scheduled_at
    assert spacing == timedelta(hours=6)


def test_poll_skips_anchor_and_older(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    ch = TikTokChannel(username="creator", backfill_anchor_video_id="V2")
    db.add(ch)
    db.commit()
    db.refresh(ch)

    now = datetime.now(UTC)
    videos = [
        _fake_video("V3", now + timedelta(hours=1)),
        _fake_video("V2", now),  # anchor — must be skipped
    ]
    service = PostingService()
    monkeypatch.setattr(
        service.provider, "list_channel_videos", lambda _u, limit: videos
    )

    service.poll_new_videos(db, ch)

    metas = db.exec(select(VideoMeta)).all()
    assert [m.tiktok_video_id for m in metas] == ["V3"]
    # no pages mapped → post jobs not created, only metadata
    assert db.exec(select(PostJob)).all() == []
