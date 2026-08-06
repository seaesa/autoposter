from datetime import UTC, datetime, time, timedelta

from sqlalchemy import cast
from sqlalchemy.types import DateTime
from sqlmodel import Session, func, select

from app.models import FacebookPage, PostJob


class QuotaGuard:
    def daily_posts(self, db: Session, page_id: int, now: datetime) -> int:
        start = datetime.combine(now.date(), time.min, tzinfo=UTC)
        stmt = select(func.count(PostJob.id)).where(  # type: ignore[arg-type]
            PostJob.facebook_page_id == page_id,
            PostJob.status == "posted",
            cast(PostJob.posted_at, DateTime) >= start,
        )
        result = db.exec(stmt).one()
        return int(result) if result is not None else 0

    def last_posted(self, db: Session, page_id: int) -> datetime | None:
        stmt = (
            select(PostJob.posted_at)
            .where(PostJob.facebook_page_id == page_id, PostJob.status == "posted")
            .order_by(cast(PostJob.posted_at, DateTime).desc())
            .limit(1)
        )
        result = db.exec(stmt).first()
        return result if isinstance(result, datetime) else None

    def next_allowed(self, db: Session, page: FacebookPage, now: datetime) -> datetime:
        if page.id is None:
            raise ValueError("page must be persisted before quota check")
        candidates = [now]
        last = self.last_posted(db, page.id)
        if last and (now - last).total_seconds() < page.min_interval_minutes * 60:
            candidates.append(last + timedelta(minutes=page.min_interval_minutes))
        if self.daily_posts(db, page.id, now) >= page.max_posts_per_day:
            start = datetime.combine(now.date(), time.min, tzinfo=UTC)
            candidates.append(start + timedelta(days=1))
        return max(candidates)
