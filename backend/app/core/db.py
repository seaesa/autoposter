from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))


def init_db() -> None:
    # Tables are managed by Alembic; kept here only for tests via conftest.
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session]:
    with Session(engine) as session:
        yield session
