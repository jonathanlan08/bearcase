"""Application settings. Every value can be overridden with a BEARCASE_* environment variable."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BEARCASE_", env_file=(".env", REPO_ROOT / ".env"), extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    secret_key: str = Field(
        default="dev-only-secret-change-me",
        description="Used to derive session token hashes. Set a long random value in production.",
    )
    database_url: str = Field(
        default=f"sqlite:///{(REPO_ROOT / 'data' / 'bearcase.db').as_posix()}",
        description="SQLAlchemy URL. SQLite by default; postgresql+psycopg://... is supported.",
    )
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_dir: Path = REPO_ROOT / "data" / "storage"
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    s3_region: str | None = None

    ai_provider: Literal["mock", "anthropic"] = "mock"
    ai_model: str = "claude-opus-5"
    anthropic_api_key: str | None = None
    ai_timeout_seconds: float = 60.0
    ai_max_retries: int = 2
    ai_max_output_tokens: int = 4096

    job_runner: Literal["thread", "sync", "poll"] = "thread"
    max_upload_bytes: int = 25 * 1024 * 1024
    max_pdf_pages: int = 300
    max_sheet_rows: int = 20_000
    max_csv_rows: int = 50_000

    cors_origins: list[str] = ["http://localhost:3000"]
    session_ttl_hours: int = 24 * 14
    demo_email: str = "analyst@bearcase.demo"
    fixtures_dir: Path = REPO_ROOT / "fixtures" / "northstar-hvac"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
