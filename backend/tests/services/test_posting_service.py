from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlmodel import Session

from app.core import crypto
from app.models import (
    ChannelPageMapping,
    FacebookPage,
    PostJob,
    TikTokChannel,
    VideoMeta,
)
from app.services.posting_service import PostingService


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
