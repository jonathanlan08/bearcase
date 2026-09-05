from __future__ import annotations

import uuid

from fastapi import APIRouter, Response
from sqlalchemy import select

from bearcase.api.deps import DbDep, UserDep
from bearcase.api.routes.auth import set_cookie
from bearcase.api.schemas import DealOut
from bearcase.auth import create_session, get_or_create_demo_user
from bearcase.models import Deal
from bearcase.seed import seed_northstar

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/session", response_model=DealOut)
def start_demo(db: DbDep, response: Response) -> Deal:
    """Sign in as the demo analyst and return the seeded Northstar deal (seeding it if needed)."""
    user = get_or_create_demo_user(db)
    token = create_session(db, user)
    deal = db.scalar(select(Deal).where(Deal.owner_id == user.id, Deal.is_demo.is_(True)).order_by(Deal.created_at.desc()))
    if deal is None:
        deal = seed_northstar(db, user)
    db.commit()
    set_cookie(response, token)
    return deal


@router.post("/reset", response_model=DealOut)
def reset_demo(db: DbDep, user: UserDep) -> Deal:
    """Re-seed the demo deal for the current user (previous demo deals are removed)."""
    for old in db.scalars(select(Deal).where(Deal.owner_id == user.id, Deal.is_demo.is_(True))):
        db.delete(old)
    db.flush()
    deal = seed_northstar(db, user)
    db.commit()
    return deal


@router.get("/deal-id")
def demo_deal_id(db: DbDep, user: UserDep) -> dict[str, uuid.UUID | None]:
    deal = db.scalar(select(Deal.id).where(Deal.owner_id == user.id, Deal.is_demo.is_(True)).order_by(Deal.created_at.desc()))
    return {"deal_id": deal}
