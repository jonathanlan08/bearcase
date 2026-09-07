"""Request dependencies: database session, current user, deal scoping with roles, and the per-user request budget."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, object_session

from bearcase.api.ratelimit import enforce, is_rate_limited_route, user_key
from bearcase.auth import SESSION_COOKIE, resolve_session
from bearcase.db import get_db
from bearcase.models import Deal, DealMember, User

DbDep = Annotated[Session, Depends(get_db)]

Role = Literal["owner", "editor", "viewer"]
# Owners can do everything; editors everything but delete the deal, manage members, or export the review
# dataset; viewers read, chat, and export seller questions. Ranks make "at least editor" a comparison.
ROLE_RANK: dict[str, int] = {"viewer": 1, "editor": 2, "owner": 3}
ROLE_MESSAGES: dict[str, str] = {
    "owner": "Only the deal owner can do this.",
    "editor": "Viewers can read and chat on this deal; ask the owner for editor access to make changes.",
    "viewer": "You do not have access to this deal.",
}


def token_from_request(request: Request) -> str | None:
    """The session token: an `Authorization: Bearer` header first, else the session cookie."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(SESSION_COOKIE)


def current_user(request: Request, db: DbDep) -> User:
    user = resolve_session(db, token_from_request(request))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in or start a demo session.")
    # The routes that parse, analyse, or call a model are budgeted per user here, in the one dependency every
    # authenticated route shares, so no route can forget the limit. The list lives in api/ratelimit.py.
    if is_rate_limited_route(request):
        enforce(request, user_key(user.id))
    return user


UserDep = Annotated[User, Depends(current_user)]


def accepted_membership_ids(user_id: uuid.UUID):  # type: ignore[no-untyped-def]
    """Subquery of the deal ids the user is an accepted member of."""
    return select(DealMember.deal_id).where(DealMember.user_id == user_id, DealMember.accepted_at.is_not(None))


def get_deal(deal_id: uuid.UUID, user: UserDep, db: DbDep) -> Deal:
    """A deal the user owns or is an accepted member of. Anyone else gets 404, never 403, so a deal id
    reveals nothing about whether the deal exists."""
    deal = db.scalar(
        select(Deal).where(Deal.id == deal_id, or_(Deal.owner_id == user.id, Deal.id.in_(accepted_membership_ids(user.id))))
    )
    if deal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deal not found.")
    return deal


DealDep = Annotated[Deal, Depends(get_deal)]


def deal_role(db: Session, deal: Deal, user: User) -> Role | None:
    """The user's role on the deal, or None for a stranger or a pending invitee."""
    if deal.owner_id == user.id:
        return "owner"
    member = db.scalar(
        select(DealMember).where(
            DealMember.deal_id == deal.id, DealMember.user_id == user.id, DealMember.accepted_at.is_not(None)
        )
    )
    if member is None:
        return None
    return "editor" if member.role.value == "editor" else "viewer"


def require_role(deal: Deal, user: User, role: Role) -> Role:
    """Raise 403 unless the user holds `role` or a stronger one on the deal; return the actual role."""
    db = object_session(deal)
    assert db is not None, "require_role needs a deal loaded from a session"
    actual = deal_role(db, deal, user)
    if actual is None or ROLE_RANK[actual] < ROLE_RANK[role]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, ROLE_MESSAGES[role])
    return actual


def editor_deal(deal: DealDep, user: UserDep) -> Deal:
    require_role(deal, user, "editor")
    return deal


def owner_deal(deal: DealDep, user: UserDep) -> Deal:
    require_role(deal, user, "owner")
    return deal


EditorDealDep = Annotated[Deal, Depends(editor_deal)]
OwnerDealDep = Annotated[Deal, Depends(owner_deal)]
