"""Request dependencies: database session, current user, deal scoping."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from bearcase.auth import SESSION_COOKIE, resolve_session
from bearcase.db import get_db
from bearcase.models import Deal, User

DbDep = Annotated[Session, Depends(get_db)]


def _token_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(SESSION_COOKIE)


def current_user(request: Request, db: DbDep) -> User:
    user = resolve_session(db, _token_from_request(request))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in or start a demo session.")
    return user


UserDep = Annotated[User, Depends(current_user)]


def get_deal(deal_id: uuid.UUID, user: UserDep, db: DbDep) -> Deal:
    deal = db.scalar(select(Deal).where(Deal.id == deal_id, Deal.owner_id == user.id))
    if deal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deal not found.")
    return deal


DealDep = Annotated[Deal, Depends(get_deal)]
