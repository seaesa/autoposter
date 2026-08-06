from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.services.tiktok_provider import TikTokProvider


def _fake_entry(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "7321",
        "title": "My video",
        "description": "desc",
        "thumbnail": "http://x/th.jpg",
        "timestamp": 1_700_000_000,
        "webpage_url": "https://www.tiktok.com/@u/video/7321",
    }
    base.update(overrides)
    return base


@patch("app.services.tiktok_provider.youtube_dl.YoutubeDL")
def test_list_channel_videos(MockYDL: MagicMock) -> None:
    fake_entries = [_fake_entry()]
    mock_info = {"entries": fake_entries}
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value.extract_info.return_value = mock_info
    MockYDL.return_value = mock_ydl

    provider = TikTokProvider()
    videos = provider.list_channel_videos("demo", limit=10)

    assert len(videos) == 1
    v = videos[0]
    assert v.video_id == "7321"
    assert v.title == "My video"
    assert isinstance(v.create_time, datetime)


@patch("app.services.tiktok_provider.youtube_dl.YoutubeDL")
def test_empty_channel(MockYDL: MagicMock) -> None:
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value.extract_info.return_value = {"entries": None}
    MockYDL.return_value = mock_ydl

    provider = TikTokProvider()
    assert provider.list_channel_videos("empty", limit=10) == []


@patch("app.services.tiktok_provider.youtube_dl.YoutubeDL")
def test_list_channel_videos_no_limit(MockYDL: MagicMock) -> None:
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value.extract_info.return_value = {"entries": []}
    MockYDL.return_value = mock_ydl

    TikTokProvider().list_channel_videos("demo", limit=None)

    opts = MockYDL.call_args.args[0]
    assert "playlistend" not in opts
    assert "playlist_items" not in opts


@patch("app.services.tiktok_provider.youtube_dl.YoutubeDL")
def test_list_channel_videos_uses_cookies(
    MockYDL: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "TIKTOK_COOKIES_FILE", "/tmp/tiktok-cookies.txt")
    mock_ydl = MagicMock()
    mock_ydl.__enter__.return_value.extract_info.return_value = {"entries": []}
    MockYDL.return_value = mock_ydl

    TikTokProvider().list_channel_videos("demo", limit=10)

    opts = MockYDL.call_args.args[0]
    assert opts["cookiefile"] == "/tmp/tiktok-cookies.txt"
