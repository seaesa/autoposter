from datetime import UTC, datetime

from sqlmodel import Session

from app.models import FacebookPage
from app.services.quota import QuotaGuard


def _now() -> datetime:
    return datetime.now(UTC)


def test_daily_posts_count(db: Session) -> None:
    page = FacebookPage(
        page_id="P1",
        name="Page",
        access_token="t",
        max_posts_per_day=10,
        min_interval_minutes=10,
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    assert page.id is not None

    guard = QuotaGuard()
    now = _now()
    assert guard.daily_posts(db, page.id, now) == 0
    assert guard.last_posted(db, page.id) is None
    assert guard.next_allowed(db, page, now) == now
