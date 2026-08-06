from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

from app.services.facebook_client import FacebookClient


def test_upload_video_returns_post_id(tmp_path: Any) -> None:
    client = FacebookClient()
    file_path = tmp_path / "v.mp4"
    file_path.write_bytes(b"bytes")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"id": "12345"}
    mock_resp.raise_for_status.return_value = None

    async def fake_post(_url: str, **_kwargs: Any) -> MagicMock:
        return mock_resp

    with patch.object(client, "_post", fake_post):
        post_id = asyncio.run(
            client.upload_video("page123", "token", file_path, "t", "d")
        )
    assert post_id == "12345"
