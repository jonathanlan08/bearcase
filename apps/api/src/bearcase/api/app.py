"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from bearcase import __version__
from bearcase.api.routes import (
    audit,
    auth,
    billing,
    chat,
    claims,
    deals,
    demo,
    documents,
    financials,
    health,
    insights,
    members,
    notes,
    questions,
    questions_seller,
    reports,
    scenarios,
    summary_pdf,
)
from bearcase.chat.providers import effective_backend
from bearcase.config import get_settings

log = logging.getLogger("bearcase")
API_ROOT = Path(__file__).resolve().parents[3]


def run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    settings = get_settings()
    if settings.env != "production":
        run_migrations()
    chat_backend = effective_backend(settings)  # label and model id only; never a key
    log.info(
        "BearCase API %s starting (env=%s, db=%s, storage=%s, jobs=%s, extraction=%s, chat=%s/%s, rate_limit=%s)",
        __version__,
        settings.env,
        "sqlite" if settings.is_sqlite else "postgresql",
        settings.storage_backend,
        settings.job_runner,
        settings.ai_provider,
        chat_backend.label,
        chat_backend.model,
        f"{settings.rate_limit_per_minute}/min" if settings.rate_limit_enabled else "off",
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="BearCase AI API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Downloads name their file and the delete route flags stale analysis; a cross-origin browser client
        # only sees these headers when they are exposed (the Next.js rewrite is same-origin and needs nothing).
        expose_headers=["Content-Disposition", "X-BearCase-Reanalyse"],
    )

    @app.exception_handler(ValueError)
    async def _value_error(_request: Request, exc: ValueError) -> JSONResponse:
        if isinstance(exc, ValidationError):  # a serialization bug, not a client error
            log.exception("response validation failed")
            return JSONResponse(status_code=500, content={"detail": "Internal serialization error", "errors": exc.errors()[:3]})
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    for router in (
        health.router,
        auth.router,
        demo.router,
        deals.router,
        documents.router,
        claims.router,
        financials.router,
        scenarios.router,
        reports.router,
        audit.router,
        questions.router,
        questions_seller.router,
        summary_pdf.router,
        notes.router,
        insights.router,
        chat.router,
        members.router,
        billing.router,
    ):
        app.include_router(router, prefix="/api")
    return app


app = create_app()
