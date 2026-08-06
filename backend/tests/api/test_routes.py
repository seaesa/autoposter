import pytest
from fastapi.testclient import TestClient

from app.services.posting_service import PostingService
from app.services.scheduler_service import scheduler


@pytest.fixture(autouse=True)
def no_network_backfill(monkeypatch: pytest.MonkeyPatch) -> None:
    """Channel creation fires a BackgroundTasks backfill; never hit the network."""
    monkeypatch.setattr(
        PostingService, "backfill_channel", lambda _self, _db, _ch: None
    )


def test_create_and_list_channel(client: TestClient) -> None:
    r = client.post("/api/v1/tiktok-channels", json={"username": "newcreator"})
    assert r.status_code == 200
    data = r.json()
    assert data["username"] == "newcreator"
    lst = client.get("/api/v1/tiktok-channels")
    assert any(c["username"] == "newcreator" for c in lst.json())


def test_create_page(client: TestClient) -> None:
    r = client.post(
        "/api/v1/facebook-pages",
        json={"page_id": "1001", "name": "Fanpage", "access_token": "secret"},
    )
    assert r.status_code == 200
    assert r.json()["access_token_encrypted"]  # stored encrypted, never plaintext
    assert "access_token" not in r.json()


def test_create_mapping(client: TestClient) -> None:
    ch = client.post("/api/v1/tiktok-channels", json={"username": "c1"}).json()
    pg = client.post(
        "/api/v1/facebook-pages",
        json={"page_id": "2002", "name": "P", "access_token": "t"},
    ).json()
    r = client.post(
        "/api/v1/mappings",
        json={"tiktok_channel_id": ch["id"], "facebook_page_id": pg["id"]},
    )
    assert r.status_code == 200


def test_run_now(client: TestClient) -> None:
    assert client.post("/api/v1/scheduler/run-now").json() == {"queued": True}


def test_stats_shape(client: TestClient) -> None:
    body = client.get("/api/v1/stats").json()
    assert set(body) >= {"today_posted", "today_pending", "channels", "scheduler"}


def test_scheduler_not_running(client: TestClient) -> None:
    assert client.app is not None
    assert scheduler.status()["running"] is False
