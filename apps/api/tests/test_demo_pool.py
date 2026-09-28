"""The spare demo pool: built ahead of visitors, handed out once, refilled after each hand-out; /api/ping."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from bearcase.api.app import create_app
from bearcase.auth import SPARE_PREFIX, claim_spare_demo, spare_demo_count
from bearcase.config import get_settings
from bearcase.db import get_session_factory
from bearcase.demo_pool import refill_demo_pool
from bearcase.models import Deal, User


@pytest.fixture
def pool_on(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BEARCASE_DEMO_POOL_SIZE", "1")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("BEARCASE_DEMO_POOL_SIZE", raising=False)
    get_settings.cache_clear()
    # leave no spare behind for other tests
    with get_session_factory()() as db:
        ids = [u.id for u in _spares(db)]
        if ids:
            db.execute(delete(Deal).where(Deal.owner_id.in_(ids)))
            db.execute(delete(User).where(User.id.in_(ids)))
        db.commit()


def _spares(db) -> list[User]:  # type: ignore[no-untyped-def]
    return list(db.scalars(select(User).where(User.email.startswith(SPARE_PREFIX))))


def test_refill_builds_one_ready_spare_and_stops(pool_on) -> None:  # type: ignore[no-untyped-def]
    assert refill_demo_pool() == 1
    assert refill_demo_pool() == 0  # already full
    with get_session_factory()() as db:
        spares = _spares(db)
        assert len(spares) == 1
        deals = list(db.scalars(select(Deal).where(Deal.owner_id == spares[0].id)))
        assert len(deals) == 1 and deals[0].company_name.startswith("Northstar") and deals[0].is_demo


def test_new_visitor_gets_the_spare_and_the_pool_refills(pool_on) -> None:  # type: ignore[no-untyped-def]
    refill_demo_pool()
    with get_session_factory()() as db:
        spare = _spares(db)[0]
        spare_id = spare.id
        spare_deal = db.scalar(select(Deal.id).where(Deal.owner_id == spare_id))
    with TestClient(create_app()) as c:  # a fresh client: no session cookie
        r = c.post("/api/demo/session")
        assert r.status_code == 200
        assert r.json()["id"] == str(spare_deal)  # handed the prebuilt deal, not a new seed
        assert c.get("/api/auth/me").json()["id"] == str(spare_id)
    with get_session_factory()() as db:
        claimed = db.get(User, spare_id)
        assert claimed is not None and claimed.email.startswith("visitor-")
        assert spare_demo_count(db) == 1  # the background task built a replacement
        assert _spares(db)[0].id != spare_id


def test_a_spare_is_never_claimed_twice(pool_on) -> None:  # type: ignore[no-untyped-def]
    refill_demo_pool()
    factory = get_session_factory()
    with factory() as a, factory() as b:
        first = claim_spare_demo(a)
        a.commit()
        second = claim_spare_demo(b)
        assert first is not None and second is None


def test_pool_off_seeds_on_the_request(client: TestClient) -> None:
    assert get_settings().demo_pool_size == 0
    with get_session_factory()() as db:
        before = spare_demo_count(db)
    with TestClient(create_app()) as c:
        assert c.post("/api/demo/session").status_code == 200
    with get_session_factory()() as db:
        assert spare_demo_count(db) == before == 0


def test_ping_answers_without_the_database(client: TestClient) -> None:
    r = client.get("/api/ping")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
