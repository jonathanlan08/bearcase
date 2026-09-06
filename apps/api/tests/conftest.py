"""Test configuration: temporary SQLite database, in-memory storage, synchronous job runner."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="bearcase-tests-")
os.environ["BEARCASE_ENV"] = "test"
os.environ["BEARCASE_DATABASE_URL"] = f"sqlite:///{Path(_TMP) / 'test.db'}"
os.environ["BEARCASE_STORAGE_LOCAL_DIR"] = str(Path(_TMP) / "storage")
os.environ["BEARCASE_JOB_RUNNER"] = "sync"
os.environ["BEARCASE_AI_PROVIDER"] = "mock"
os.environ["BEARCASE_CHAT_PROVIDER"] = "mock"  # a key in the repo-root .env must never make tests call a provider
os.environ["BEARCASE_SECRET_KEY"] = "test-secret"

from fastapi.testclient import TestClient  # noqa: E402

from bearcase.api.app import app, run_migrations  # noqa: E402
from bearcase.config import get_settings  # noqa: E402
from bearcase.db import get_session_factory, reset_engine  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "northstar-hvac"


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    get_settings.cache_clear()
    reset_engine()
    run_migrations()
    yield


@pytest.fixture
def db():  # type: ignore[no-untyped-def]
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def demo(client: TestClient) -> dict:
    """Start a demo session (seeds Northstar once per test session) and return the deal."""
    r = client.post("/api/demo/session")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="session")
def ground_truth() -> dict:
    import json

    return json.loads((FIXTURES / "northstar-ground-truth.json").read_text())
