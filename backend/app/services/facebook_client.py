from __future__ import annotations

from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

BASE = "https://graph.facebook.com"
GRAPH_VERSION = getattr(settings, "GRAPH_VERSION", "v21.0")


class FacebookClient:
    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None

    async def _http_session(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(120))
        return self._http

    async def upload_video(
        self, page_id: str, token: str, file_path: Path, title: str, description: str
    ) -> str:
        url = f"{BASE}/{GRAPH_VERSION}/{page_id}/videos"
        with open(file_path, "rb") as f:
            files = {"source": (file_path.name, f, "video/mp4")}
            data = {
                "access_token": token,
                "title": title,
                "description": description,
            }
            response = await self._post(url, files=files, data=data)
        payload = response.json()
        return payload.get("id") or payload.get("post_id") or ""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=8))
    async def _post(self, url: str, **kwargs) -> httpx.Response:
        http = await self._http_session()
        r = await http.post(url, **kwargs)
        r.raise_for_status()
        return r

    async def update_post(
        self, post_id: str, token: str, title: str, description: str
    ) -> None:
        url = f"{BASE}/{GRAPH_VERSION}/{post_id}"
        data = {
            "access_token": token,
            "title": title,
            "description": description,
        }
        r = await self._post(url, data=data)
        r.raise_for_status()

    async def delete_post(self, post_id: str, token: str) -> None:
        url = f"{BASE}/{GRAPH_VERSION}/{post_id}"
        http = await self._http_session()
        r = await http.delete(url, params={"access_token": token})
        r.raise_for_status()
