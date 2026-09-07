from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from bearcase.api.deps import DbDep, UserDep
from bearcase.api.ratelimit import rate_limited
from bearcase.api.schemas import LoginRequest, RegisterRequest, UserOut
from bearcase.audit import record
from bearcase.auth import SESSION_COOKIE, create_session, hash_password, revoke_session, verify_password
from bearcase.config import get_settings
from bearcase.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


def set_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=s.env == "production",
        max_age=s.session_ttl_hours * 3600,
        path="/",
    )


@router.post("/register", response_model=UserOut, status_code=201, dependencies=[Depends(rate_limited)])
def register(body: RegisterRequest, db: DbDep, response: Response) -> User:
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists.")
    user = User(email=body.email.lower(), display_name=body.display_name, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    token = create_session(db, user)
    record(
        db,
        user_id=user.id,
        event_type="user.registered",
        object_type="user",
        object_id=user.id,
        summary=f"Registered {user.email}",
    )
    db.commit()
    set_cookie(response, token)
    return user


@router.post("/login", response_model=UserOut, dependencies=[Depends(rate_limited)])
def login(body: LoginRequest, db: DbDep, response: Response) -> User:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    token = create_session(db, user)
    db.commit()
    set_cookie(response, token)
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, db: DbDep, response: Response) -> None:
    revoke_session(db, request.cookies.get(SESSION_COOKIE))
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
def me(user: UserDep) -> User:
    return user
