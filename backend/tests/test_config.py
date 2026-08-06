from app.core.config import settings


def test_backfill_interval_default() -> None:
    assert settings.BACKFILL_INTERVAL_HOURS == 6


def test_cookies_file_default() -> None:
    assert settings.TIKTOK_COOKIES_FILE == ""


def test_dead_settings_removed() -> None:
    assert not hasattr(settings, "MAX_BACKFILL_VIDEOS")
    assert not hasattr(settings, "JOB_SCAN_SECONDS")
