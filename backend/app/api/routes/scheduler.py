from typing import Any

from fastapi import APIRouter

from app.services.scheduler_service import scheduler

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.post("/run-now")
async def run_now() -> dict[str, Any]:
    await scheduler.run_once()
    return {"queued": True}
