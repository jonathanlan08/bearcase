from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from bearcase import ENGINE_VERSION, __version__
from bearcase.api.deps import DbDep
from bearcase.api.schemas import HealthOut
from bearcase.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health(db: DbDep) -> HealthOut:
    s = get_settings()
    db.execute(text("SELECT 1"))
    return HealthOut(
        status="ok",
        version=__version__,
        engine_version=ENGINE_VERSION,
        provider=s.ai_provider,
        model=s.ai_model if s.ai_provider == "anthropic" else "rules-v1",
        database="sqlite" if s.is_sqlite else "postgresql",
        storage=s.storage_backend,
    )
