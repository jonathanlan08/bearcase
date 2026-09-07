"""Application settings. Every value can be overridden with a BEARCASE_* environment variable; model
provider keys also accept their native names (ANTHROPIC_API_KEY, GEMINI_API_KEY, ...) from the environment
or the repo-root .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
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
    ai_timeout_seconds: float = 60.0
    ai_max_retries: int = 2
    ai_max_output_tokens: int = 4096

    # Deal chat. "auto" picks the first provider with a key (anthropic, openai, gemini, groq, openrouter,
    # ollama when OLLAMA_HOST is set) and otherwise the deterministic rule-based composer ("mock").
    chat_provider: Literal["auto", "mock", "anthropic", "openai", "gemini", "groq", "openrouter", "ollama", "custom"] = "auto"
    chat_model: str | None = Field(default=None, description="Overrides the provider's default chat model id.")
    chat_base_url: str | None = Field(
        default=None, description="OpenAI-compatible base URL for chat_provider=custom (or a proxy for a named provider)."
    )
    chat_api_key: str | None = Field(default=None, description="API key for chat_provider=custom.")

    # Provider keys: BEARCASE_-prefixed or native names, from the environment or .env. Never logged.
    anthropic_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("BEARCASE_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")
    )
    openai_api_key: str | None = Field(default=None, validation_alias=AliasChoices("BEARCASE_OPENAI_API_KEY", "OPENAI_API_KEY"))
    gemini_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("BEARCASE_GEMINI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")
    )
    groq_api_key: str | None = Field(default=None, validation_alias=AliasChoices("BEARCASE_GROQ_API_KEY", "GROQ_API_KEY"))
    openrouter_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("BEARCASE_OPENROUTER_API_KEY", "OPENROUTER_API_KEY")
    )
    ollama_host: str | None = Field(
        default=None,
        validation_alias=AliasChoices("BEARCASE_OLLAMA_HOST", "OLLAMA_HOST"),
        description="Ollama server URL; http://127.0.0.1:11434 when chat_provider=ollama is chosen without one.",
    )

    job_runner: Literal["thread", "sync", "poll"] = "thread"
    max_upload_bytes: int = 25 * 1024 * 1024
    max_pdf_pages: int = 300
    max_sheet_rows: int = 20_000
    max_csv_rows: int = 50_000

    # Storage quotas, enforced by the upload route. Documents cannot be deleted through the API yet, so a
    # full deal or a full allowance stays full until an operator intervenes.
    max_documents_per_deal: int = Field(default=50, ge=1, description="Files one deal may hold.")
    max_storage_bytes_per_user: int = Field(
        default=500 * 1024 * 1024, ge=1, description="Stored bytes across all of a user's deals, every version counted."
    )

    # Abuse limits. The token bucket lives in this process; a public deployment also needs limits at the
    # ingress (request body size, connections) and one shared limiter when several API processes run.
    rate_limit_enabled: bool = Field(default=True, description="Forced off under BEARCASE_ENV=test unless set explicitly.")
    rate_limit_per_minute: int = Field(
        default=60,
        ge=1,
        description="Requests per minute, per signed-in user (or client address before sign-in), for the routes that "
        "parse, analyse, seed, or call a model. See api/ratelimit.py for the list.",
    )
    trust_proxy_headers: bool = Field(
        default=False,
        description="Read the client address from X-Forwarded-For. Only enable behind a proxy that overwrites the header.",
    )

    cors_origins: list[str] = ["http://localhost:3000"]
    session_ttl_hours: int = 24 * 14
    demo_email: str = Field(
        default="analyst@bearcase.demo",
        description="Address of the legacy shared demo identity, still used by `bearcase seed` and the eval runner. "
        "Visitors never sign in as it: /api/demo/session gives each visitor a private demo identity.",
    )
    demo_retention_days: int = Field(
        default=14,
        ge=1,
        description="A visitor's demo identity, its deals, and its files are deleted this many days after the visitor's "
        "newest session expired. Cleanup runs lazily, a few users at a time, when a demo starts.",
    )
    fixtures_dir: Path = REPO_ROOT / "fixtures" / "northstar-hvac"

    @model_validator(mode="after")
    def _quiet_limiter_in_tests(self) -> Settings:
        # The test suite shares one client address and would exhaust any budget. A test that exercises the
        # limiter constructs Settings with rate_limit_enabled=True (or sets BEARCASE_RATE_LIMIT_ENABLED).
        if self.env == "test" and "rate_limit_enabled" not in self.model_fields_set:
            self.rate_limit_enabled = False
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
