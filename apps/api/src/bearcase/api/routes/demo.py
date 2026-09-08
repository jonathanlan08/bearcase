"""Demo entry. Every visitor gets a private demo identity and their own copy of the Northstar deal."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Request, Response, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from bearcase.api.deps import DbDep, UserDep, token_from_request
from bearcase.api.ratelimit import rate_limited
from bearcase.api.routes.auth import set_cookie
from bearcase.api.schemas import DealOut
from bearcase.auth import create_demo_visitor, create_session, delete_deal_with_files, purge_stale_demo_users, resolve_session
from bearcase.config import get_settings
from bearcase.models import Deal
from bearcase.seed import seed_messy, seed_northstar

log = logging.getLogger("bearcase.demo")
router = APIRouter(prefix="/demo", tags=["demo"])


DEMO_DEALS = {"northstar": ("Northstar", seed_northstar), "messy": ("Tidewater", seed_messy)}


def _latest_demo_deal(db: Session, owner_id: uuid.UUID, which: str = "northstar") -> Deal | None:
    prefix = DEMO_DEALS[which][0]
    return db.scalar(
        select(Deal)
        .where(Deal.owner_id == owner_id, Deal.is_demo.is_(True), Deal.company_name.startswith(prefix))
        .order_by(Deal.created_at.desc())
    )


@router.post("/session", response_model=DealOut, dependencies=[Depends(rate_limited)])
def start_demo(db: DbDep, request: Request, response: Response, deal: str = "northstar") -> Deal:
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
    if deal not in DEMO_DEALS:
        raise HTTPException(400, "Unknown demo deal. Choose northstar or messy.")
    found = _latest_demo_deal(db, user.id, deal) or DEMO_DEALS[deal][1](db, user)
    db.commit()
    if token:
        set_cookie(response, token)
    return found


@router.post("/reset", response_model=DealOut)
def reset_demo(db: DbDep, user: UserDep, deal: str = "northstar") -> Deal:
    """Re-seed one demo deal for the current user (previous copies of that deal are removed)."""
    if deal not in DEMO_DEALS:
        raise HTTPException(400, "Unknown demo deal. Choose northstar or messy.")
    prefix, seeder = DEMO_DEALS[deal]
    for old in list(db.scalars(select(Deal).where(Deal.owner_id == user.id, Deal.is_demo.is_(True), Deal.company_name.startswith(prefix)))):
        delete_deal_with_files(db, old)
    fresh = seeder(db, user)
    db.commit()
    return fresh


@router.get("/deal-id")
def demo_deal_id(db: DbDep, user: UserDep) -> dict[str, uuid.UUID | None]:
    deal = db.scalar(select(Deal.id).where(Deal.owner_id == user.id, Deal.is_demo.is_(True)).order_by(Deal.created_at.desc()))
    return {"deal_id": deal}
