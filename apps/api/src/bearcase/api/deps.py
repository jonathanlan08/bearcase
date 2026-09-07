"""Request dependencies: database session, current user, deal scoping, and the per-user request budget."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from bearcase.api.ratelimit import enforce, is_rate_limited_route, user_key
from bearcase.auth import SESSION_COOKIE, resolve_session
from bearcase.db import get_db
from bearcase.models import Deal, User

DbDep = Annotated[Session, Depends(get_db)]


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


def get_deal(deal_id: uuid.UUID, user: UserDep, db: DbDep) -> Deal:
    deal = db.scalar(select(Deal).where(Deal.id == deal_id, Deal.owner_id == user.id))
    if deal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deal not found.")
    return deal


DealDep = Annotated[Deal, Depends(get_deal)]
