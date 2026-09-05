"""Password hashing and opaque session tokens. Sessions are stored hashed; cookies are httpOnly."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.orm import Session

from bearcase.config import get_settings
from bearcase.models import User, UserSession
from bearcase.models.base import utcnow

_hasher = PasswordHasher()
SESSION_COOKIE = "bearcase_session"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _token_hash(token: str) -> str:
    return hmac.new(get_settings().secret_key.encode(), token.encode(), hashlib.sha256).hexdigest()


def create_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=_token_hash(token),
            expires_at=utcnow() + timedelta(hours=get_settings().session_ttl_hours),
        )
    )
    db.flush()
    return token


def resolve_session(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    sess = db.scalar(select(UserSession).where(UserSession.token_hash == _token_hash(token)))
    if sess is None:
        return None
    expires = sess.expires_at if sess.expires_at.tzinfo else sess.expires_at.replace(tzinfo=UTC)
    if expires < utcnow():
        return None
    return db.get(User, sess.user_id)


def revoke_session(db: Session, token: str | None) -> None:
    if not token:
        return
    sess = db.scalar(select(UserSession).where(UserSession.token_hash == _token_hash(token)))
    if sess:
        db.delete(sess)
        db.flush()


def get_or_create_demo_user(db: Session) -> User:
    email = get_settings().demo_email
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            id=uuid.uuid5(uuid.NAMESPACE_URL, "bearcase:demo-user"), email=email, display_name="Demo analyst", is_demo=True
        )
        db.add(user)
        db.flush()
    return user
