"""Demo entry. Every visitor gets a private demo identity and their own copy of the Northstar deal."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from bearcase.api.deps import DbDep, UserDep, token_from_request
from bearcase.api.ratelimit import rate_limited
from bearcase.api.routes.auth import set_cookie
from bearcase.api.schemas import DealOut
from bearcase.auth import create_demo_visitor, create_session, delete_deal_with_files, purge_stale_demo_users, resolve_session
from bearcase.config import get_settings
from bearcase.models import Deal
from bearcase.seed import seed_northstar

log = logging.getLogger("bearcase.demo")
router = APIRouter(prefix="/demo", tags=["demo"])


def _latest_demo_deal(db: Session, owner_id: uuid.UUID) -> Deal | None:
    return db.scalar(select(Deal).where(Deal.owner_id == owner_id, Deal.is_demo.is_(True)).order_by(Deal.created_at.desc()))


@router.post("/session", response_model=DealOut, dependencies=[Depends(rate_limited)])
def start_demo(db: DbDep, request: Request, response: Response) -> Deal:
    """Open the caller's own demo.

    A caller with a live session, whether a returning demo visitor or a signed-in account, keeps that identity
    and gets back their existing demo deal, or a fresh Northstar copy seeded under it (about a tenth of a second).
    Anyone else becomes a new demo visitor with a new session cookie. The shared demo identity of earlier builds
    is never resumed: its sessions no longer resolve, so an old cookie also yields a new visitor. Because every
    deal query is owner-scoped, nothing one visitor uploads or creates is visible to another.
    """
    settings = get_settings()
    try:
        purged = purge_stale_demo_users(db, retention_days=settings.demo_retention_days)
        db.commit()
        if purged:
            log.info("removed %d demo visitors idle for more than %d days", purged, settings.demo_retention_days)
    except Exception:  # cleanup must never stop a demo from starting
        db.rollback()
        log.exception("demo cleanup failed")
    user = resolve_session(db, token_from_request(request))
    token: str | None = None
    if user is None:
        user = create_demo_visitor(db)
        token = create_session(db, user)
    deal = _latest_demo_deal(db, user.id) or seed_northstar(db, user)
    db.commit()
    if token:
        set_cookie(response, token)
    return deal


@router.post("/reset", response_model=DealOut)
def reset_demo(db: DbDep, user: UserDep) -> Deal:
    """Re-seed the demo deal for the current user (previous demo deals are removed)."""
    for old in list(db.scalars(select(Deal).where(Deal.owner_id == user.id, Deal.is_demo.is_(True)))):
        delete_deal_with_files(db, old)
    deal = seed_northstar(db, user)
    db.commit()
    return deal


@router.get("/deal-id")
def demo_deal_id(db: DbDep, user: UserDep) -> dict[str, uuid.UUID | None]:
    deal = db.scalar(select(Deal.id).where(Deal.owner_id == user.id, Deal.is_demo.is_(True)).order_by(Deal.created_at.desc()))
    return {"deal_id": deal}
