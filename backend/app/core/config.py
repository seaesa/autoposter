import secrets
from typing import Literal

from pydantic import PostgresDsn, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    SECRET_KEY: str = ""

    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    # --- poster settings ---
    POLL_INTERVAL_MINUTES: int = 30
    MAX_BACKFILL_VIDEOS: int = 50
    JOB_SCAN_SECONDS: int = 60
    MAX_ATTEMPTS: int = 3
    GRAPH_VERSION: str = "v21.0"
    RUN_SCHEDULER: bool = True
    ENCRYPTION_KEY: str = ""

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def _default_encryption_key(cls, v: str) -> str:
        return v or f"CHANGE_ME_{secrets.token_urlsafe(16)}"


settings = Settings()  # type: ignore
