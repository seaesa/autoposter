from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yt_dlp as youtube_dl  # type: ignore[import-untyped]

_BASE_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "socket_timeout": 30,
}


@dataclass
class TikTokVideo:
    video_id: str
    title: str
    description: str
    thumbnail_url: str | None
    create_time: datetime | None
    download_url: str | None


class TikTokProvider:
    def list_channel_videos(self, username: str, limit: int) -> list[TikTokVideo]:
        url = f"https://www.tiktok.com/@{username}"
        opts: dict[str, Any] = {
            **_BASE_OPTS,
            "extract_flat": "in_playlist",
            "playlistend": limit,
            "playlist_items": f"1-{limit}",
        }
        with youtube_dl.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        entries = (info or {}).get("entries") or []
        out: list[TikTokVideo] = []
        for e in entries:
            if not e:
                continue
            ts = e.get("timestamp")
            out.append(
                TikTokVideo(
                    video_id=str(e.get("id", "")),
                    title=e.get("title") or "",
                    description=e.get("description") or "",
                    thumbnail_url=e.get("thumbnail"),
                    create_time=datetime.fromtimestamp(ts, tz=UTC) if ts else None,
                    download_url=e.get("webpage_url"),
                )
            )
        return out

    def get_video_download_url(self, video_id_or_url: str) -> str | None:
        # yt-dlp exposes the 'url' of the best format when not flat
        return (
            video_id_or_url  # MVP: use webpage_url; direct stream handled in download
        )

    def download_video(self, video_url: str, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        opts: dict[str, Any] = {
            **_BASE_OPTS,
            "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
            "format": "best[ext=mp4]/best",
        }
        with youtube_dl.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
        ext = info.get("ext", "mp4")
        return dest_dir / f"{info.get('id')}.{ext}"
