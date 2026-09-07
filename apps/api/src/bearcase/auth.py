"""Password hashing, opaque session tokens, and demo identities. Sessions are stored hashed; cookies are httpOnly."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import UTC, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from bearcase.config import get_settings
from bearcase.ingest.storage import get_storage
from bearcase.models import Deal, Document, DocumentVersion, User, UserSession
from bearcase.models.base import utcnow

log = logging.getLogger("bearcase.auth")
_hasher = PasswordHasher()
SESSION_COOKIE = "bearcase_session"

# The single demo account every visitor used to share. It still exists for `bearcase seed` and the eval runner,
# but it is never served to a visitor again: resolve_session refuses its sessions, so an old cookie gets a fresh
# private visitor instead of someone else's uploads.
LEGACY_DEMO_USER_ID = uuid.uuid5(uuid.NAMESPACE_URL, "bearcase:demo-user")
# RFC 2606 reserves .invalid, so a visitor address can never reach a mailbox or collide with a real account.
DEMO_VISITOR_DOMAIN = "demo.bearcase.invalid"


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
    if sess.user_id == LEGACY_DEMO_USER_ID:
        return None  # retired shared identity; see LEGACY_DEMO_USER_ID
    return db.get(User, sess.user_id)


def revoke_session(db: Session, token: str | None) -> None:
    if not token:
        return
    sess = db.scalar(select(UserSession).where(UserSession.token_hash == _token_hash(token)))
    if sess:
        db.delete(sess)
        db.flush()


def create_demo_visitor(db: Session) -> User:
    """A private demo identity for one visitor. Its deals are visible to nobody else, and it is deleted with
    them by purge_stale_demo_users once the visitor has been away long enough."""
    visitor_id = uuid.uuid4()
    user = User(
        id=visitor_id,
        email=f"visitor-{visitor_id.hex}@{DEMO_VISITOR_DOMAIN}",
        display_name="Demo analyst",
        is_demo=True,
    )
    db.add(user)
    db.flush()
    return user


def purge_stale_demo_users(db: Session, *, retention_days: int, limit: int = 20) -> int:
    """Delete demo identities whose newest session expired more than `retention_days` ago, together with their
    deals (database cascades) and stored files. A demo identity that never had a session ages from its creation.
    At most `limit` users go per call so the cost on the request path stays bounded; the rest wait for the next
    demo start. Returns the number of users removed."""
    cutoff = utcnow() - timedelta(days=retention_days)
    stale = db.scalars(
        select(User.id)
        .outerjoin(UserSession, UserSession.user_id == User.id)
        .where(User.is_demo.is_(True))
        .group_by(User.id, User.created_at)
        .having(func.coalesce(func.max(UserSession.expires_at), User.created_at) < cutoff)
        .order_by(User.created_at)
        .limit(limit)
    ).all()
    if not stale:
        return 0
    storage = get_storage()
    for user_id in stale:
        keys = db.scalars(
            select(DocumentVersion.storage_key)
            .join(Document, Document.id == DocumentVersion.document_id)
            .join(Deal, Deal.id == Document.deal_id)
            .where(Deal.owner_id == user_id)
        ).all()
        for key in keys:
            try:
                storage.delete(key)
            except Exception:  # a missing blob must not keep the rows alive
                log.warning("could not delete stored file %s", key, exc_info=True)
        db.execute(delete(Deal).where(Deal.owner_id == user_id))
        db.execute(delete(User).where(User.id == user_id))
    db.flush()
    return len(stale)


def delete_deal_with_files(db: Session, deal: Deal) -> None:
    """Remove a deal and the stored files behind its documents, so replacing a demo deal never leaves blobs behind."""
    storage = get_storage()
    keys = db.scalars(
        select(DocumentVersion.storage_key)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(Document.deal_id == deal.id)
    ).all()
    for key in keys:
        try:
            storage.delete(key)
        except Exception:  # a missing blob must not keep the rows alive
            log.warning("could not delete stored file %s", key, exc_info=True)
    db.delete(deal)
    db.flush()


def get_or_create_demo_user(db: Session) -> User:
    """The legacy shared demo identity, used by `bearcase seed` and the eval runner. Never a visitor's login:
    /api/demo/session creates a private identity per visitor (create_demo_visitor)."""
    email = get_settings().demo_email
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(id=LEGACY_DEMO_USER_ID, email=email, display_name="Demo analyst", is_demo=True)
        db.add(user)
        db.flush()
    return user
