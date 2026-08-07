from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_settings_present() -> None:
    assert settings.POLL_INTERVAL_MINUTES > 0
    assert settings.BACKFILL_INTERVAL_HOURS > 0
    assert settings.MAX_ATTEMPTS == 3


def test_app_has_api_prefix() -> None:
    client = TestClient(app)
    assert client.get("/api/v1/tiktok-channels").status_code == 200
