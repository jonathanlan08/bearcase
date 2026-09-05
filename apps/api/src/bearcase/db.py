"""Database engine and session management."""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from bearcase.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        kwargs: dict = {"future": True, "pool_pre_ping": True}
        if settings.is_sqlite:
            if not url.endswith(":memory:"):
                db_path = url.replace("sqlite:///", "")
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **kwargs)
        if settings.is_sqlite:
            _configure_sqlite(_engine)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _session_factory


def reset_engine() -> None:
    """Used by tests to swap the database URL."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all() -> None:
    from bearcase import models  # noqa: F401  (register models)

    Base.metadata.create_all(get_engine())
