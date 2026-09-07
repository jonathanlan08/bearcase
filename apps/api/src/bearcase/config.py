"""Application settings. Every value can be overridden with a BEARCASE_* environment variable; model
provider keys also accept their native names (ANTHROPIC_API_KEY, GEMINI_API_KEY, ...) from the environment
or the repo-root .env file."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]
log = logging.getLogger("bearcase.config")


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
    # Chat speed and resilience. Free tiers are slow and rate limited, so one reply should cost as few
    # provider requests as possible and a busy model should hand over to the next one instead of retrying.
    chat_model_picker: bool = Field(
        default=False,
        description="Offer a model picker in the chat panel. Off: the configured default model answers everyone.",
    )
    chat_max_output_tokens: int = Field(default=2048, ge=64, description="Output cap per chat request.")
    chat_reasoning_effort: Literal["none", "low", "medium", "high"] = Field(
        default="low", description="Thinking effort sent to providers that accept it (gemini, openai, groq)."
    )
    chat_model_fallback: bool = Field(
        default=True,
        description="When the first request of a reply fails with a 5xx or an overloaded message, answer with the next "
        "model in the provider's fallback chain (chat/providers.py). A 429 never switches: the quota is shared.",
    )
    chat_brief_ttl_seconds: int = Field(
        default=300,
        ge=0,
        description="How long a cached deal brief (chat/brief.py) is trusted before its version stamp is rechecked.",
    )

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

    # Transactional email (verification, password reset, deal invitations). "console" logs each message and
    # keeps the last fifty in memory for tests; "resend" posts to the Resend API. Links point at app_base_url.
    email_provider: Literal["console", "resend"] = "console"
    email_from: str = Field(default="BearCase <no-reply@bearcase.invalid>", description="From header for every message.")
    resend_api_key: str | None = Field(default=None, validation_alias=AliasChoices("BEARCASE_RESEND_API_KEY", "RESEND_API_KEY"))
    app_base_url: str = Field(default="http://localhost:3000", description="Public origin of the web app; used in email links.")

    # Per-user chat budget: assistant answers per calendar month (UTC), across every deal the user asked in.
    chat_monthly_request_limit: int = Field(default=300, ge=1, description="Assistant answers per user per month.")

    # Bounded paid pilot through Stripe Checkout. Unset keys leave /api/billing/checkout answering 503.
    stripe_secret_key: str | None = Field(
        default=None, validation_alias=AliasChoices("BEARCASE_STRIPE_SECRET_KEY", "STRIPE_SECRET_KEY")
    )
    stripe_webhook_secret: str | None = Field(
        default=None, validation_alias=AliasChoices("BEARCASE_STRIPE_WEBHOOK_SECRET", "STRIPE_WEBHOOK_SECRET")
    )
    pilot_price_cents: int = Field(default=50000, ge=50, description="Price of the pilot in the smallest currency unit.")
    pilot_currency: str = Field(default="usd", min_length=3, max_length=3)

    @model_validator(mode="after")
    def _quiet_limiter_in_tests(self) -> Settings:
        # The test suite shares one client address and would exhaust any budget. A test that exercises the
        # limiter constructs Settings with rate_limit_enabled=True (or sets BEARCASE_RATE_LIMIT_ENABLED).
        if self.env == "test" and "rate_limit_enabled" not in self.model_fields_set:
            self.rate_limit_enabled = False
        return self

    @model_validator(mode="after")
    def _normalize_database_url(self) -> Settings:
        # Hosted PostgreSQL (Render, Neon, Supabase, Heroku-style) hands out postgres:// or postgresql:// URLs.
        # SQLAlchemy dropped the first and maps the second to psycopg2, which is not installed; the supported
        # driver is psycopg 3 (the `postgres` extra), so both are rewritten to its dialect name.
        for prefix in ("postgres://", "postgresql://"):
            if self.database_url.startswith(prefix):
                self.database_url = "postgresql+psycopg://" + self.database_url[len(prefix) :]
        return self

    @model_validator(mode="after")
    def _refuse_unsafe_production(self) -> Settings:
        # A production process must not sign sessions with the string that is in this repository. The other
        # soft spots (see production_warnings) are logged so a deployment that chose them on purpose still starts.
        if self.env != "production":
            return self
        if self.secret_key == type(self).model_fields["secret_key"].default:
            raise ValueError(
                "BEARCASE_SECRET_KEY is the development default; BEARCASE_ENV=production needs a long random value, "
                "for example the output of: python -c 'import secrets; print(secrets.token_urlsafe(48))'"
            )
        for message in production_warnings(self):
            log.warning(message)
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


def has_chat_credentials(settings: Settings) -> bool:
    """True when at least one chat provider could be connected from these settings (a key, an Ollama host, or
    the Anthropic auth token the SDK reads on its own). Mirrors the auto-order check in chat/providers.py."""
    keys = (
        settings.anthropic_api_key,
        settings.openai_api_key,
        settings.gemini_api_key,
        settings.groq_api_key,
        settings.openrouter_api_key,
        settings.ollama_host,
    )
    return any(keys) or bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def production_warnings(settings: Settings) -> list[str]:
    """Settings a production deployment should look at twice. The production validator logs them at start and
    `bearcase doctor` reports them; none of them stops the API, because each can be a deliberate choice."""
    warnings: list[str] = []
    local = [o for o in settings.cors_origins if "localhost" in o or "127.0.0.1" in o]
    if local:
        warnings.append(
            f"BEARCASE_CORS_ORIGINS still lists {', '.join(local)}; set it to the web app's public origin "
            "(a JSON list, no trailing slash)"
        )
    if settings.is_sqlite:
        warnings.append(
            "BEARCASE_DATABASE_URL is SQLite: it serves one process, and most hosts replace the filesystem on every "
            "deploy; use PostgreSQL (postgresql+psycopg://...)"
        )
    if settings.storage_backend == "local":
        warnings.append(
            "BEARCASE_STORAGE_BACKEND=local keeps uploads on this instance's disk; on an ephemeral filesystem they "
            "are gone after the next deploy (use s3 or a persistent disk)"
        )
    if settings.chat_provider == "auto" and not has_chat_credentials(settings):
        warnings.append(
            "BEARCASE_CHAT_PROVIDER=auto found no provider key, so the chat answers from the rule-based composer; "
            "add a key (GEMINI_API_KEY for the free tier) or set BEARCASE_CHAT_PROVIDER=mock to make that deliberate"
        )
    if not settings.rate_limit_enabled:
        warnings.append("BEARCASE_RATE_LIMIT_ENABLED is off: upload, processing, and model-calling routes are unmetered")
    if len(settings.secret_key) < 32:
        warnings.append("BEARCASE_SECRET_KEY is shorter than 32 characters; use 32 or more")
    if settings.email_provider == "console":
        warnings.append(
            "BEARCASE_EMAIL_PROVIDER=console prints verification, reset, and invitation emails to the log instead of "
            "delivering them; set it to resend with RESEND_API_KEY"
        )
    if "localhost" in settings.app_base_url or "127.0.0.1" in settings.app_base_url:
        warnings.append(f"BEARCASE_APP_BASE_URL is {settings.app_base_url}; links in emails will point at a local address")
    return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()
