from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from app.core.db import engine
from app.main import app


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
    with Session(engine) as session:
        yield session
        session.rollback()
