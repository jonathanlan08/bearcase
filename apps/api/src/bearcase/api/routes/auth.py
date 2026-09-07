"""Accounts: registration with email verification, sign-in, password reset, and the current user.

Link tokens (verification, reset, invitation) are random urlsafe strings; only their SHA-256 is stored in
auth_tokens, each is single use, and each purpose has its own expiry. Every route that takes an address or a
token from an unauthenticated caller is rate limited by client address, like sign-in.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from bearcase.api.deps import DbDep, UserDep
from bearcase.api.ratelimit import rate_limited
from bearcase.api.schemas import LoginRequest, RegisterRequest, RequestResetRequest, ResetPasswordRequest, TokenRequest, UserOut
from bearcase.audit import record
from bearcase.auth import SESSION_COOKIE, create_session, hash_password, revoke_session, verify_password
from bearcase.config import get_settings
from bearcase.email import EmailDeliveryError, get_emailer
from bearcase.models import AuthToken, User, UserSession
from bearcase.models.base import utcnow
from bearcase.models.enums import TokenPurpose

log = logging.getLogger("bearcase.auth")
router = APIRouter(prefix="/auth", tags=["auth"])

TOKEN_TTL: dict[TokenPurpose, timedelta] = {
    TokenPurpose.VERIFY: timedelta(hours=24),
    TokenPurpose.RESET: timedelta(hours=1),
    TokenPurpose.INVITE: timedelta(days=7),
}
LINK_PATHS: dict[TokenPurpose, str] = {
    TokenPurpose.VERIFY: "/verify",
    TokenPurpose.RESET: "/reset",
    TokenPurpose.INVITE: "/invite",
}


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


# ---- link tokens ------------------------------------------------------------------------------------------


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(db: Session, user: User, purpose: TokenPurpose, payload: dict[str, Any] | None = None) -> str:
    """Create a single-use token for `user`. For verification and reset, earlier unused links of the same purpose
    are retired so only the newest one works; invitations carry their own payload and stay independent.
    Returns the token itself, which is never stored."""
    if purpose != TokenPurpose.INVITE:
        db.execute(
            update(AuthToken)
            .where(AuthToken.user_id == user.id, AuthToken.purpose == purpose, AuthToken.used_at.is_(None))
            .values(used_at=utcnow())
        )
    token = secrets.token_urlsafe(32)
    db.add(
        AuthToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=token_hash(token),
            expires_at=utcnow() + TOKEN_TTL[purpose],
            payload=payload or {},
        )
    )
    db.flush()
    return token


def link_for(purpose: TokenPurpose, token: str) -> str:
    return f"{get_settings().app_base_url.rstrip('/')}{LINK_PATHS[purpose]}?token={token}"


def consume_token(db: Session, token: str, purpose: TokenPurpose) -> AuthToken:
    """Look a token up, check purpose, expiry, and single use, and mark it used. Raises 400 with a plain reason."""
    row = db.scalar(select(AuthToken).where(AuthToken.token_hash == token_hash(token), AuthToken.purpose == purpose))
    if row is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This link is not valid. Request a new one.")
    if row.used_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This link has already been used. Request a new one.")
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if expires < utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This link has expired. Request a new one.")
    row.used_at = utcnow()
    db.flush()
    return row


# ---- emails -----------------------------------------------------------------------------------------------


def send_verification_email(db: Session, user: User) -> None:
    link = link_for(TokenPurpose.VERIFY, issue_token(db, user, TokenPurpose.VERIFY))
    text = (
        f"Hi {user.display_name},\n\nConfirm the email address for your BearCase account by opening this link "
        f"within 24 hours:\n\n{link}\n\nIf you did not create an account, ignore this message."
    )
    html = (
        f"<p>Hi {user.display_name},</p><p>Confirm the email address for your BearCase account by opening this link "
        f'within 24 hours:</p><p><a href="{link}">{link}</a></p><p>If you did not create an account, ignore this message.</p>'
    )
    try:
        get_emailer().send(user.email, "Confirm your BearCase email", text, html)
    except EmailDeliveryError:
        log.warning("could not send the verification email to %s", user.email, exc_info=True)


def send_reset_email(db: Session, user: User) -> None:
    link = link_for(TokenPurpose.RESET, issue_token(db, user, TokenPurpose.RESET))
    text = (
        f"Hi {user.display_name},\n\nSomeone asked to reset the password for this BearCase account. Open this link "
        f"within one hour to choose a new password:\n\n{link}\n\nIf that was not you, ignore this message; your "
        "password stays as it is."
    )
    html = (
        f"<p>Hi {user.display_name},</p><p>Someone asked to reset the password for this BearCase account. Open this "
        f'link within one hour to choose a new password:</p><p><a href="{link}">{link}</a></p>'
        "<p>If that was not you, ignore this message; your password stays as it is.</p>"
    )
    try:
        get_emailer().send(user.email, "Reset your BearCase password", text, html)
    except EmailDeliveryError:
        log.warning("could not send the reset email to %s", user.email, exc_info=True)


# ---- routes -----------------------------------------------------------------------------------------------


@router.post("/register", response_model=UserOut, status_code=201, dependencies=[Depends(rate_limited)])
def register(body: RegisterRequest, db: DbDep, response: Response) -> User:
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Enter an email address.")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists.")
    user = User(email=email, display_name=body.display_name, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    token = create_session(db, user)
    send_verification_email(db, user)
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
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
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


@router.post("/verify", dependencies=[Depends(rate_limited)])
def verify_email(body: TokenRequest, db: DbDep) -> dict[str, bool]:
    """Confirm an address from the link in the verification email. Single use, 24-hour expiry."""
    row = consume_token(db, body.token, TokenPurpose.VERIFY)
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This link is not valid. Request a new one.")
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
        record(
            db,
            user_id=user.id,
            event_type="user.email_verified",
            object_type="user",
            object_id=user.id,
            summary=f"Verified {user.email}",
        )
    db.commit()
    return {"verified": True}


@router.post("/resend-verification", dependencies=[Depends(rate_limited)])
def resend_verification(db: DbDep, user: UserDep) -> dict[str, bool]:
    if user.is_demo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Demo visitors have no mailbox; create an account to verify an email.")
    if user.email_verified_at is not None:
        return {"sent": False, "verified": True}
    send_verification_email(db, user)
    db.commit()
    return {"sent": True, "verified": False}


@router.post("/request-reset", dependencies=[Depends(rate_limited)])
def request_reset(body: RequestResetRequest, db: DbDep) -> dict[str, bool]:
    """Always 200: the response never says whether an address has an account."""
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if user is not None and not user.is_demo and user.password_hash:
        send_reset_email(db, user)
        db.commit()
    return {"ok": True}


@router.post("/reset", dependencies=[Depends(rate_limited)])
def reset_password(body: ResetPasswordRequest, db: DbDep, response: Response) -> dict[str, bool]:
    """Set a new password from a reset link and sign every session of that account out. One-hour expiry."""
    row = consume_token(db, body.token, TokenPurpose.RESET)
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This link is not valid. Request a new one.")
    user.password_hash = hash_password(body.password)
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()  # the link proved the mailbox
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.execute(
        update(AuthToken)
        .where(AuthToken.user_id == user.id, AuthToken.purpose == TokenPurpose.RESET, AuthToken.used_at.is_(None))
        .values(used_at=utcnow())
    )
    record(
        db,
        user_id=user.id,
        event_type="user.password_reset",
        object_type="user",
        object_id=user.id,
        summary=f"Password reset for {user.email}",
    )
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}
