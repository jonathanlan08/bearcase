"""Regression tests for the findings of the independent (Astra) review: per-visitor demo isolation and cleanup,
upload and storage limits, the request budget, statement-sheet aliases, chat grounding, and deal-creation
validation. Fixtures: `client` (a session-wide TestClient with its own cookie jar), `demo` (that client's demo
deal), `db` (a plain session)."""

from __future__ import annotations

import json
import re
import uuid
import zipfile
from datetime import timedelta
from io import BytesIO
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from bearcase.api import ratelimit
from bearcase.api.app import app
from bearcase.api.routes import documents as documents_route
from bearcase.auth import (
    LEGACY_DEMO_USER_ID,
    create_demo_visitor,
    create_session,
    get_or_create_demo_user,
    purge_stale_demo_users,
    resolve_session,
)
from bearcase.chat import service as chat_service
from bearcase.config import Settings, get_settings
from bearcase.ingest.parsers.common import ParsedChunk
from bearcase.ingest.statement_mapper import map_income_statement
from bearcase.ingest.storage import get_storage
from bearcase.ingest.validation import UploadRejected, detect_type
from bearcase.models import ChatThread, Deal, Document, DocumentVersion, Evidence, User, UserSession
from bearcase.models.base import utcnow
from bearcase.seed import seed_northstar

DEAL_BODY: dict[str, Any] = {
    "company_name": "Audit Co",
    "industry": "Services",
    "purchase_price": "1000000",
    "debt_amount": "500000",
    "equity_amount": "500000",
    "interest_rate_pct": "8",
    "amortization_years": 10,
}
CSV = b"customer_name,revenue_type,revenue\nA,maintenance,100\n"


def _events(body: str) -> list[tuple[str, Any]]:
    lines = body.splitlines()
    return [(line[7:], json.loads(lines[i + 1][6:])) for i, line in enumerate(lines) if line.startswith("event: ")]


def _settings(**overrides: Any) -> Settings:
    return get_settings().model_copy(update=overrides)


def _user_row(db, user_id: uuid.UUID) -> User | None:  # type: ignore[no-untyped-def]
    return db.scalar(select(User).where(User.id == user_id))  # a query, so a deleted row is seen as gone


# ---- demo isolation (finding 1) ---------------------------------------------------------------------------


def test_demo_visitors_cannot_see_each_others_deals(demo):
    a, b = TestClient(app), TestClient(app)
    deal_a, deal_b = a.post("/api/demo/session").json(), b.post("/api/demo/session").json()
    assert deal_a["id"] != deal_b["id"] != demo["id"] and deal_a["is_demo"] and deal_b["is_demo"]
    me_a, me_b = a.get("/api/auth/me").json(), b.get("/api/auth/me").json()
    assert me_a["id"] != me_b["id"] and me_a["is_demo"] and me_b["is_demo"]
    assert me_a["email"].endswith("@demo.bearcase.invalid") and me_a["email"] != me_b["email"]
    r = a.post("/api/deals", json={**DEAL_BODY, "company_name": "AUDIT confidential acquisition"})
    assert r.status_code == 201, r.text
    private = r.json()["id"]
    assert b.get(f"/api/deals/{private}").status_code == 404
    assert b.get(f"/api/deals/{deal_a['id']}/claims").status_code == 404
    assert a.get(f"/api/deals/{private}").status_code == 200
    assert {d["id"] for d in b.get("/api/deals").json()} == {deal_b["id"]}


def test_demo_session_is_reused_by_the_same_visitor(db):
    c = TestClient(app)
    first, second = c.post("/api/demo/session"), c.post("/api/demo/session")
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert "set-cookie" in first.headers and "set-cookie" not in second.headers  # the live cookie is kept
    owner = uuid.UUID(c.get("/api/auth/me").json()["id"])
    assert db.scalar(select(func.count(Deal.id)).where(Deal.owner_id == owner)) == 1  # seeded once


def test_legacy_shared_demo_session_is_rejected(db):
    legacy = get_or_create_demo_user(db)
    assert legacy.id == LEGACY_DEMO_USER_ID
    token = create_session(db, legacy)
    db.commit()
    assert resolve_session(db, token) is None
    # presenting the old token to the demo route yields a fresh private visitor, not the shared account
    c = TestClient(app)
    deal = c.post("/api/demo/session", headers={"authorization": f"Bearer {token}"}).json()
    me = c.get("/api/auth/me").json()
    assert me["id"] != str(LEGACY_DEMO_USER_ID) and me["is_demo"] is True
    assert db.scalar(select(Deal.owner_id).where(Deal.id == uuid.UUID(deal["id"]))) == uuid.UUID(me["id"])
    assert c.get(f"/api/deals/{deal['id']}", headers={"authorization": f"Bearer {token}"}).status_code == 401


def test_signed_in_user_keeps_identity_when_opening_the_demo(db):
    c = TestClient(app)
    r = c.post("/api/auth/register", json={"email": "owner@example.com", "password": "password123", "display_name": "Owner"})
    assert r.status_code == 201, r.text
    me = r.json()
    assert me["is_demo"] is False
    deal = c.post("/api/demo/session").json()
    assert c.get("/api/auth/me").json() == me
    assert db.scalar(select(Deal.owner_id).where(Deal.id == uuid.UUID(deal["id"]))) == uuid.UUID(me["id"])
    assert c.post("/api/demo/session").json()["id"] == deal["id"]


def test_stale_demo_visitors_are_purged_with_their_deals_and_files(db):
    old = utcnow() - timedelta(days=20)
    stale = create_demo_visitor(db)
    db.add(UserSession(user_id=stale.id, token_hash=f"stale-{stale.id.hex}", expires_at=old))
    seed_northstar(db, stale, generate_report_too=False)
    keys = db.scalars(select(DocumentVersion.storage_key).join(Document).join(Deal).where(Deal.owner_id == stale.id)).all()
    fresh = create_demo_visitor(db)
    db.add(UserSession(user_id=fresh.id, token_hash=f"fresh-{fresh.id.hex}", expires_at=utcnow() + timedelta(days=1)))
    never = create_demo_visitor(db)  # no session and created just now: kept
    db.commit()
    storage = get_storage()
    assert len(keys) == 7 and all(storage.exists(k) for k in keys)
    assert purge_stale_demo_users(db, retention_days=14) == 1
    db.commit()
    assert _user_row(db, stale.id) is None and _user_row(db, fresh.id) is not None and _user_row(db, never.id) is not None
    assert db.scalar(select(func.count(Deal.id)).where(Deal.owner_id == stale.id)) == 0
    assert db.scalar(select(func.count(Evidence.id)).join(Deal).where(Deal.owner_id == stale.id)) == 0
    assert not any(storage.exists(k) for k in keys)
    # a demo identity that never had a session ages from its creation, and the demo route runs the cleanup
    db.execute(update(User).where(User.id == never.id).values(created_at=old))
    db.commit()
    assert TestClient(app).post("/api/demo/session").status_code == 200
    assert _user_row(db, never.id) is None and _user_row(db, fresh.id) is not None


# ---- upload and resource limits (finding 3) -------------------------------------------------------------


def _workbook_archive(entries: int, size_each: int = 0) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/workbook.xml", "<workbook/>")
        for i in range(entries):
            z.writestr(f"xl/worksheets/sheet{i}.xml", b"\0" * size_each)
    return buf.getvalue()


def test_xlsx_entry_count_budget():
    assert detect_type(_workbook_archive(3)) == "xlsx"
    with pytest.raises(UploadRejected) as exc:
        detect_type(_workbook_archive(10_001))
    assert exc.value.code == "archive_entries" and "10,000" in exc.value.message


def test_xlsx_expanded_size_budget():
    with pytest.raises(UploadRejected) as exc:
        detect_type(_workbook_archive(entries=11, size_each=10 * 1024 * 1024))
    assert exc.value.code == "expanded_size" and "100 MB" in exc.value.message


def test_oversized_upload_is_refused_before_validation(client, demo, monkeypatch):
    monkeypatch.setattr(documents_route, "get_settings", lambda: _settings(max_upload_bytes=64))

    def never(*_args: Any, **_kw: Any) -> None:
        raise AssertionError("an oversized file must be refused before validation")

    monkeypatch.setattr(documents_route, "validate_upload", never)
    files = [("files", ("big.pdf", b"%PDF-" + b"0" * 200, "application/pdf"))]
    r = client.post(f"/api/deals/{demo['id']}/documents", files=files)
    assert r.status_code == 413, r.text
    err = r.json()["detail"]["errors"][0]
    assert err["code"] == "too_large" and err["file"] == "big.pdf" and "larger than" in err["message"]


def test_per_deal_document_limit(client, demo, monkeypatch):
    docs = client.get(f"/api/deals/{demo['id']}/documents").json()
    monkeypatch.setattr(documents_route, "get_settings", lambda: _settings(max_documents_per_deal=len(docs)))
    r = client.post(f"/api/deals/{demo['id']}/documents", files=[("files", ("extra.csv", CSV, "text/csv"))])
    assert r.status_code == 400, r.text
    err = r.json()["detail"]["errors"][0]
    assert err["code"] == "document_limit" and f"{len(docs)} documents" in err["message"]
    assert len(client.get(f"/api/deals/{demo['id']}/documents").json()) == len(docs)


def test_per_user_aggregate_storage_limit(client, demo, db, monkeypatch):
    owner = uuid.UUID(client.get("/api/auth/me").json()["id"])
    used = documents_route.user_storage_bytes(db, owner)
    assert used > 0
    monkeypatch.setattr(documents_route, "get_settings", lambda: _settings(max_storage_bytes_per_user=used + 5))
    r = client.post(f"/api/deals/{demo['id']}/documents", files=[("files", ("extra.csv", CSV, "text/csv"))])
    assert r.status_code == 413, r.text
    err = r.json()["detail"]["errors"][0]
    assert err["code"] == "storage_limit" and "storage allowance" in err["message"]
    assert documents_route.user_storage_bytes(db, owner) == used


def test_token_bucket_refills_over_time():
    now = [0.0]
    lim = ratelimit.TokenBucketLimiter(clock=lambda: now[0])
    assert [lim.acquire("k", 2) for _ in range(2)] == [None, None]
    wait = lim.acquire("k", 2)
    assert wait is not None and 29.9 < wait <= 30.0  # two per minute: one token every 30 s
    assert lim.acquire("other", 2) is None  # buckets are per key
    now[0] += 30
    assert lim.acquire("k", 2) is None and lim.acquire("k", 2) is not None


def test_rate_limiter_is_off_under_the_test_env_unless_enabled(monkeypatch):
    assert Settings(_env_file=None).env == "test" and Settings(_env_file=None).rate_limit_enabled is False
    assert Settings(_env_file=None, rate_limit_enabled=True).rate_limit_enabled is True
    monkeypatch.setenv("BEARCASE_RATE_LIMIT_ENABLED", "true")
    assert Settings(_env_file=None).rate_limit_enabled is True
    monkeypatch.delenv("BEARCASE_RATE_LIMIT_ENABLED")
    assert Settings(_env_file=None, env="development").rate_limit_enabled is True


def test_rate_limited_routes_return_429_with_retry_after(client, demo, monkeypatch):
    monkeypatch.setattr(ratelimit, "get_settings", lambda: _settings(rate_limit_enabled=True, rate_limit_per_minute=2))
    ratelimit.limiter.reset()
    try:
        ask = f"/api/deals/{demo['id']}/ask"
        assert client.post(ask, json={"question": "Which documents are missing?"}).status_code == 201
        assert client.post(ask, json={"question": "Which documents are missing?"}).status_code == 201
        r = client.post(ask, json={"question": "Which documents are missing?"})
        assert r.status_code == 429 and r.headers["retry-after"].isdigit() and "Try again" in r.json()["detail"]
        # reads are never budgeted
        assert client.get(f"/api/deals/{demo['id']}").status_code == 200
        # the demo start is budgeted by client address, separately from any user's budget
        other = TestClient(app)
        assert other.post("/api/demo/session").status_code == 200
        assert other.post("/api/demo/session").status_code == 200
        assert other.post("/api/demo/session").status_code == 429
    finally:
        ratelimit.limiter.reset()


# ---- statement mapping (finding 5) ------------------------------------------------------------------------


def _sheet(title: str, rows: list[list[str]]) -> list[ParsedChunk]:
    return [
        ParsedChunk(kind="sheet_row", locator={"sheet": title, "row": i + 1}, text=" | ".join(r), structured={"values": r})
        for i, r in enumerate(rows)
    ]


@pytest.mark.parametrize("title", ["P&L", "Profit and Loss", "Profit & Loss", "Income Statement", "FY P & L summary"])
def test_statement_sheet_aliases_map(title):
    chunks = _sheet(title, [["Line item", "FY2023", "FY2024"], ["Revenue", "100", "200"], ["Net income", "10", "20"]])
    mapped = map_income_statement(chunks)
    assert mapped is not None and mapped.sheet == title and mapped.periods == ["FY2023", "FY2024"]
    assert mapped.as_periods()["FY2024"]["revenue"] == 200 and mapped.lines["FY2024"]["revenue"].cell == "C2"


def test_statement_sheets_are_never_merged():
    first = _sheet("P&L", [["", "FY2023", "FY2024"], ["Revenue", "100", "200"]])
    prior = _sheet("P&L (prior year)", [["", "FY2022", "FY2023"], ["Revenue", "900", "950"], ["Net income", "1", "2"]])
    mapped = map_income_statement(first + prior)
    assert mapped is not None and mapped.sheet == "P&L" and mapped.periods == ["FY2023", "FY2024"]
    assert mapped.as_periods()["FY2023"]["revenue"] == 100 and mapped.as_periods()["FY2023"]["net_income"] is None
    # a matching sheet without period columns is skipped in favour of the next one
    cover = _sheet("P&L summary", [["Adjusted EBITDA", "up"], ["Notes", "see next sheet"]])
    mapped = map_income_statement(cover + prior)
    assert mapped is not None and mapped.sheet == "P&L (prior year)" and mapped.as_periods()["FY2023"]["revenue"] == 950
    assert map_income_statement(_sheet("Balance sheet", [["", "FY2023", "FY2024"], ["Cash", "1", "2"]])) is None


# ---- chat honesty (finding 2) -----------------------------------------------------------------------------


def _fake_stream(reply: str):  # type: ignore[no-untyped-def]
    def stream(db, deal, question, text_parts, tool_calls):  # type: ignore[no-untyped-def]
        tool_calls.append({"name": "get_findings", "input": {}, "result_chars": 42})
        yield chat_service.sse("tool", {"name": "get_findings", "status": "done"})
        for piece in re.findall(r"\S+\s*", reply):
            text_parts.append(piece)
            yield chat_service.sse("text", {"delta": piece})

    return stream


def _reply(db, deal: Deal, text: str, monkeypatch) -> list[tuple[str, Any]]:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(chat_service, "_mock_stream", _fake_stream(text))
    thread = ChatThread(deal_id=deal.id, user_id=deal.owner_id)
    db.add(thread)
    db.commit()
    return _events("".join(chat_service.stream_reply(db, deal, thread, deal.owner_id, "What are the biggest risks?")))


def test_tool_backed_reply_without_a_citation_is_not_grounded(db, demo, monkeypatch):
    deal = db.get(Deal, uuid.UUID(demo["id"]))
    events = _reply(db, deal, "There are several findings, including customer concentration.", monkeypatch)
    citations = next(d for e, d in events if e == "citations")
    done = events[-1][1]
    assert citations["material_sentences"] == 0 and citations["evidence"] == [] and citations["metrics"] == []
    assert done["grounded"] is False and done["scope"] == "deal" and done["error"] is None
    # the same reply with one resolved citation is grounded
    evidence = db.scalar(select(Evidence.id).where(Evidence.deal_id == deal.id))
    events = _reply(db, deal, f"There are several findings, including customer concentration. [E:{evidence}]", monkeypatch)
    done = events[-1][1]
    assert done["grounded"] is True and done["scope"] == "deal" and f"[E:{evidence}]" in done["content"]


def test_system_prompt_states_real_or_fictional_by_deal(db, demo):
    demo_deal = db.get(Deal, uuid.UUID(demo["id"]))
    assert demo_deal.is_demo
    for_demo = chat_service.system_prompt(demo_deal)
    for_real = chat_service.system_prompt(Deal(company_name="Harbor Real Co", is_demo=False))
    assert "fictional" in for_demo and "Northstar" in for_demo
    assert "fictional" not in for_real and "Harbor Real Co" in for_real and "real" in for_real
    assert for_demo.count("\n8. ") == for_real.count("\n8. ") == 1
    assert "fictional" not in chat_service.SYSTEM and "{demo_note}" in chat_service.SYSTEM
    assert "Lead with the direct answer" in for_real
    assert chat_service.demo_note(demo_deal) != chat_service.demo_note(Deal(company_name="x", is_demo=False))


def test_mock_reply_does_not_repeat_metric_chips(client, demo):
    with client.stream("POST", f"/api/deals/{demo['id']}/chat", json={"message": "Why was adjusted EBITDA reduced?"}) as resp:
        body = "".join(resp.iter_text())
    done = _events(body)[-1][1]
    assert done["grounded"] is True and "[E:" in done["content"] and "$1,810,000" in done["content"]
    paragraphs = [p for p in done["content"].split("\n\n") if p.strip()]
    assert len(paragraphs) >= 5
    marker = re.compile(r"\[M:([0-9a-f-]{36})\]")
    on_evidence_paragraphs = [m for p in paragraphs if "[E:" in p for m in marker.findall(p)]
    assert len(on_evidence_paragraphs) == len(set(on_evidence_paragraphs))  # no metric chip repeats where evidence exists
    assert len(set(marker.findall(done["content"]))) >= 2
    for p in paragraphs:  # every paragraph that states a figure still carries a marker
        if re.search(r"\d|\$|%", p):
            assert "[E:" in p or "[M:" in p, p


# ---- deal creation (walkthrough item 12) ------------------------------------------------------------------


def test_deal_creation_rejects_blank_amounts_instead_of_zero(client):
    for blank in ("", "   ", None):
        r = client.post("/api/deals", json={**DEAL_BODY, "debt_amount": blank})
        assert r.status_code == 422, r.text
        errs = r.json()["detail"]
        assert [e for e in errs if e["loc"][-1] == "debt_amount" and "blank" in e["msg"]], errs
    r = client.post("/api/deals", json={k: v for k, v in DEAL_BODY.items() if k != "equity_amount"})
    assert r.status_code == 422 and any(e["loc"][-1] == "equity_amount" for e in r.json()["detail"])
    assert client.post("/api/deals", json={**DEAL_BODY, "purchase_price": "NaN"}).status_code == 422
    assert client.post("/api/deals", json={**DEAL_BODY, "debt_amount": "-1"}).status_code == 422
    assert client.post("/api/deals", json={**DEAL_BODY, "interest_rate_pct": ""}).status_code == 422
    assert client.post("/api/deals", json={**DEAL_BODY, "amortization_years": None}).status_code == 422


def test_deal_creation_requires_funding_to_match_price(client):
    r = client.post("/api/deals", json={**DEAL_BODY, "debt_amount": "0", "equity_amount": "0"})
    assert r.status_code == 422, r.text
    err = next(e for e in r.json()["detail"] if e["loc"][-1] == "equity_amount")
    assert "$0" in err["msg"] and "$1,000,000" in err["msg"] and "1%" in err["msg"]
    # within 1% is accepted; thousands separators and a dollar sign are stripped
    body = {**DEAL_BODY, "purchase_price": "$1,000,000", "debt_amount": "505,000", "equity_amount": "500,000"}
    r = client.post("/api/deals", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["purchase_price"].startswith("1000000") and r.json()["debt_amount"].startswith("505000")


def test_contradiction_detail_is_neutral_when_the_seller_understated() -> None:
    from decimal import Decimal

    from bearcase.models import Claim
    from bearcase.models.enums import ClaimType
    from bearcase.pipeline.analyze import _CONTRADICTION_DEFAULT, _contradiction_detail

    under = Claim(claim_type=ClaimType.REVENUE_GROWTH, claimed_value=Decimal("8"), verified_value=Decimal("12"), normalized={})
    assert "slower" not in _contradiction_detail(under, "") and _contradiction_detail(under, "") == _CONTRADICTION_DEFAULT
    over = Claim(claim_type=ClaimType.REVENUE_GROWTH, claimed_value=Decimal("18"), verified_value=Decimal("11.6"), normalized={})
    assert "slower" in _contradiction_detail(over, "")
    churn_under = Claim(claim_type=ClaimType.CHURN, claimed_value=Decimal("10"), verified_value=Decimal("4"), normalized={})
    assert "More customers leave" not in _contradiction_detail(churn_under, "")
    missing = Claim(claim_type=ClaimType.CHURN, claimed_value=None, verified_value=None, normalized={})
    assert _contradiction_detail(missing, "") == _CONTRADICTION_DEFAULT


def test_replacing_a_deal_removes_its_stored_files(client, demo, db):  # type: ignore[no-untyped-def]
    from pathlib import Path

    from sqlalchemy import select

    from bearcase.auth import delete_deal_with_files
    from bearcase.config import get_settings
    from bearcase.models import Deal

    root = Path(get_settings().storage_local_dir)
    r = client.post(
        "/api/deals",
        json={
            "company_name": "Blob cleanup test",
            "industry": "Test",
            "purchase_price": 1000000,
            "debt_amount": 600000,
            "equity_amount": 400000,
            "interest_rate_pct": 8,
            "amortization_years": 10,
        },
    )
    assert r.status_code == 201, r.text
    deal_id = r.json()["id"]
    before = {p for p in root.rglob("*") if p.is_file()}
    up = client.post(
        f"/api/deals/{deal_id}/documents",
        files=[("files", ("customers.csv", b"customer,fy2024_revenue\nAcme,100\nBeta,50\n", "text/csv"))],
    )
    assert up.status_code == 201, up.text
    with_blob = {p for p in root.rglob("*") if p.is_file()}
    assert len(with_blob) == len(before) + 1
    deal = db.scalar(select(Deal).where(Deal.id == __import__("uuid").UUID(deal_id)))
    assert deal is not None
    delete_deal_with_files(db, deal)
    db.commit()
    after = {p for p in root.rglob("*") if p.is_file()}
    assert after == before
