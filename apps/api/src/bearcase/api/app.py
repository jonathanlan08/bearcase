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
    chat,
    claims,
    deals,
    demo,
    documents,
    financials,
    health,
    questions,
    reports,
    scenarios,
)
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
    log.info(
        "BearCase API %s starting (provider=%s, db=%s)",
        __version__,
        settings.ai_provider,
        "sqlite" if settings.is_sqlite else "postgresql",
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
        CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
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
        chat.router,
    ):
        app.include_router(router, prefix="/api")
    return app


app = create_app()
