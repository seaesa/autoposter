import os
from collections.abc import Generator

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

import app.core.db as core_db
from app.core.config import settings
from app.main import app

# never start the scheduler loop under tests (would poll TikTok over the network)
settings.RUN_SCHEDULER = False

_TEST_DB = f"{settings.POSTGRES_DB}_test"


def _ensure_test_db() -> None:
    with psycopg.connect(
        host=settings.POSTGRES_SERVER,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        dbname="postgres",
        autocommit=True,
    ) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (_TEST_DB,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{_TEST_DB}"')


_ensure_test_db()

# point the app engine at the dedicated test database so the dev DB is never touched
core_db.engine = create_engine(
    f"postgresql+psycopg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@"
    f"{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{_TEST_DB}"
)
engine = core_db.engine

# make any module that imported the engine lazily see the test engine
os.environ["POSTGRES_DB"] = _TEST_DB


@pytest.fixture(scope="session", autouse=True)
def _create_tables() -> Generator[None]:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(scope="module")
def client() -> Generator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function")
def db() -> Generator[Session]:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
        session.rollback()
