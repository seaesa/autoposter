from fastapi import APIRouter

from app.api.routes import channels, jobs, mappings, pages, scheduler, stats

api_router = APIRouter()
for router in (
    channels.router,
    pages.router,
    mappings.router,
    jobs.router,
    stats.router,
    scheduler.router,
):
    api_router.include_router(router)
