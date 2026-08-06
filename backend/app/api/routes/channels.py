from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/tiktok-channels", tags=["tiktok-channels"])


@router.get("")
def list_channels_placeholder() -> list[dict[str, Any]]:
    return []
