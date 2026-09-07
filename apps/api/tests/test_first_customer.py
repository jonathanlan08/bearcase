"""The first-customer workflow through the API: questions for the seller (page, export, report section),
document deletion, workflow progress, usage and cost, and the review dataset with its CLI.

These tests use private signed-in users with their own Northstar copies, so the shared `demo` deal that
other modules read stays untouched (the delete test removes the CIM)."""

from __future__ import annotations

import json
import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from bearcase.api.app import app
from bearcase.chat.providers import estimate_cost, price_for
from bearcase.cli import main as cli_main
from bearcase.db import get_session_factory
from bearcase.ingest.storage import get_storage
from bearcase.models import (
    AuditEvent,
    ChatMessage,
    ChatThread,
    Claim,
    ClaimEvidenceLink,
    Document,
    DocumentVersion,
    Evidence,
    Finding,
    ReviewDecision,
    User,
)
from bearcase.seed import seed_northstar

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
DECIMAL_REPR_RE = re.compile(r"\d\.\d{4,}|\d+E[+-]\d+|\bDecimal\(")
QUESTION_KEYS = {
    "id",
    "question",
    "why",
    "kind",
    "severity",
    "evidence_ids",
    "metric_ids",
    "claim_id",
    "finding_id",
    "document_names",
}
KINDS = {"contradiction", "unsupported", "missing_document", "covenant", "concentration", "risk", "integrity"}
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
DEAL_BODY = {
    "company_name": "Progress Co",
    "industry": "Services",
    "purchase_price": "1000000",
    "debt_amount": "500000",
    "equity_amount": "500000",
    "interest_rate_pct": "8",
    "amortization_years": 10,
}
CSV = b"customer_name,revenue_type,revenue\nA,maintenance,100\nB,project,50\n"


def _seed_for(email: str, display_name: str) -> tuple[TestClient, str]:
    """A signed-in user (the client keeps its session cookie) with a private Northstar copy."""
    c = TestClient(app)
    r = c.post("/api/auth/register", json={"email": email, "password": "password123", "display_name": display_name})
    assert r.status_code == 201, r.text
    session = get_session_factory()()
    try:
        user = session.get(User, uuid.UUID(r.json()["id"]))
        assert user is not None
        deal_id = str(seed_northstar(session, user).id)
        session.commit()
    finally:
        session.close()
    return c, deal_id


@pytest.fixture(scope="module")
def owner() -> tuple[TestClient, str]:
    return _seed_for("buyer@example.com", "Buyer")


@pytest.fixture(scope="module")
def stranger() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/register", json={"email": "stranger@example.com", "password": "password123", "display_name": "S"})
    assert r.status_code == 201, r.text
    return c


def _progress(c: TestClient, deal_id: str) -> dict[str, bool]:
    r = c.get(f"/api/deals/{deal_id}/progress")
    assert r.status_code == 200, r.text
    steps = r.json()["steps"]
    assert [s["key"] for s in steps] == ["documents", "findings", "evidence", "questions"]
    assert all(set(s) == {"key", "label", "done", "href_key"} and s["label"] and s["href_key"] for s in steps)
    return {s["key"]: s["done"] for s in steps}


def _events(c: TestClient, deal_id: str, event_type: str) -> list[dict]:
    return [e for e in c.get(f"/api/deals/{deal_id}/audit").json() if e["event_type"] == event_type]


# ---------- price table ----------------------------------------------------------------------


def test_price_table_is_explicit_about_what_it_does_not_know():
    assert price_for("anthropic", "claude-haiku-4-5") == (1.0, 5.0)
    assert estimate_cost("anthropic", "claude-sonnet-5", 1_000_000, 1_000_000) == 12.0
    assert estimate_cost("openai", "gpt-5.6-luna", 1_000_000, 0) == pytest.approx(0.2)
    assert estimate_cost("gemini", "gemini-3.8-flash", 5_000, 2_000) == 0.0
    assert estimate_cost("groq", "openai/gpt-oss-120b", 5_000, 2_000) == 0.0
    assert estimate_cost("openrouter", "z-ai/glm-5.2:free", 5_000, 2_000) == 0.0
    assert estimate_cost("mock", "rules-v1", 0, 0) == 0.0 and estimate_cost("ollama", "qwen3:8b", 10, 10) == 0.0
    assert estimate_cost("openrouter", "anthropic/claude-sonnet-5", 10, 10) is None
    assert estimate_cost("anthropic", "claude-opus-5", 10, 10) is None and estimate_cost("custom", "mystery", 1, 1) is None


# ---------- questions for the seller -----------------------------------------------------------


def test_seller_questions_are_deterministic_and_reader_ready(owner):
    c, deal_id = owner
    first = c.get(f"/api/deals/{deal_id}/seller-questions")
    second = c.get(f"/api/deals/{deal_id}/seller-questions")
    assert first.status_code == 200 and first.json() == second.json()
    data = first.json()
    qs = data["questions"]
    assert len(qs) >= 8 and data["generated_from"]["findings"] >= 8 and data["generated_from"]["claims"] >= 5
    assert len(qs) == 21, "the landing page states this count (apps/web/src/app/page.tsx DEMO.questions); update both"
    for q in qs:
        assert set(q) == QUESTION_KEYS, q
        assert q["kind"] in KINDS and q["severity"] in SEVERITY_RANK
        assert q["question"].endswith("?") or q["question"].endswith("."), q["question"]
        assert q["why"].endswith((".", "”")), q["why"]
        for text in (q["question"], q["why"]):
            assert not UUID_RE.search(text) and not DECIMAL_REPR_RE.search(text), text
        assert (q["claim_id"] is not None) or (q["finding_id"] is not None)
        assert all(isinstance(e, str) for e in q["evidence_ids"]) and all(isinstance(m, str) for m in q["metric_ids"])
    ranks = [SEVERITY_RANK[q["severity"]] for q in qs]
    assert ranks == sorted(ranks), "questions are ordered by severity"
    kinds = {q["kind"] for q in qs}
    assert {"contradiction", "missing_document", "concentration", "covenant", "integrity"} <= kinds
    growth = next(q for q in qs if q["kind"] == "contradiction" and "18%" in q["question"])
    assert "11.6%" in growth["question"] and growth["question"].endswith("What explains the difference?")
    assert growth["claim_id"] and growth["finding_id"] and growth["evidence_ids"] and growth["metric_ids"]
    assert "northstar-cim.pdf" in growth["document_names"] and "northstar-financial-statements.xlsx" in growth["document_names"]
    for eid in growth["evidence_ids"]:
        assert c.get(f"/api/deals/{deal_id}/evidence/{eid}").status_code == 200
    assert any(q["question"].startswith("Please provide the ") for q in qs if q["kind"] == "missing_document")
    covenant = next(q for q in qs if q["kind"] == "covenant")
    assert not re.search(r"\d", covenant["question"]) and covenant["metric_ids"], "figures live in the reason and the metric"
    assert "1.25x" in covenant["why"]


def test_seller_questions_match_the_report_section(owner):
    c, deal_id = owner
    qs = c.get(f"/api/deals/{deal_id}/seller-questions").json()["questions"]
    assert c.post(f"/api/deals/{deal_id}/report").status_code == 202  # the sync runner builds it inline
    rep = c.get(f"/api/deals/{deal_id}/report").json()
    assert rep["status"] == "validated" and rep["validation"]["uncited"] == [], rep["validation"]
    section = next(s for s in rep["sections"] if s["key"] == "management_questions")
    stmts = [st for st in section["statements"] if st.get("role") != "intro"]
    assert [st["text"] for st in stmts] == [q["question"] for q in qs]
    assert [st["evidence_ids"] for st in stmts] == [q["evidence_ids"] for q in qs]
    assert [st["metric_ids"] for st in stmts] == [q["metric_ids"] for q in qs]


def test_seller_questions_export_is_a_download_and_audited(owner, stranger):
    c, deal_id = owner
    qs = c.get(f"/api/deals/{deal_id}/seller-questions").json()["questions"]
    assert _progress(c, deal_id)["questions"] is False
    md = c.get(f"/api/deals/{deal_id}/seller-questions/export?format=md")
    assert md.status_code == 200, md.text
    assert md.headers["content-disposition"] == 'attachment; filename="bearcase-northstar-hvac-services--llc-seller-questions.md"'
    assert md.headers["content-type"].startswith("text/markdown")
    assert md.text.startswith("# Questions for the seller: Northstar HVAC Services, LLC")
    assert "## High priority" in md.text and all(q["question"] in md.text for q in qs)
    assert "Fictional demonstration data." in md.text and not UUID_RE.search(md.text)
    txt = c.get(f"/api/deals/{deal_id}/seller-questions/export?format=txt")
    assert txt.status_code == 200 and txt.headers["content-type"].startswith("text/plain")
    assert txt.headers["content-disposition"].endswith('seller-questions.txt"') and "High priority\n-------------" in txt.text
    assert c.get(f"/api/deals/{deal_id}/seller-questions/export?format=pdf").status_code == 400
    events = _events(c, deal_id, "seller_questions.exported")
    assert len(events) == 2 and {e["payload"]["format"] for e in events} == {"md", "txt"}
    assert all(e["payload"]["count"] == len(qs) for e in events)
    assert _progress(c, deal_id)["questions"] is True
    assert stranger.get(f"/api/deals/{deal_id}/seller-questions").status_code == 404
    assert stranger.get(f"/api/deals/{deal_id}/seller-questions/export").status_code == 404


# ---------- progress -------------------------------------------------------------------------


def test_progress_transitions_upload_decision_evidence_export(db):
    c, deal_id = _seed_for("progress@example.com", "Progress")
    empty = c.post("/api/deals", json=DEAL_BODY).json()["id"]
    assert _progress(c, empty) == {"documents": False, "findings": False, "evidence": False, "questions": False}
    r = c.post(f"/api/deals/{empty}/documents", files=[("files", ("customers.csv", CSV, "text/csv"))])
    assert r.status_code == 201, r.text
    assert c.get(f"/api/deals/{empty}/documents").json()[0]["status"] == "ready"
    assert _progress(c, empty) == {"documents": True, "findings": False, "evidence": False, "questions": False}

    assert _progress(c, deal_id) == {"documents": True, "findings": False, "evidence": False, "questions": False}
    claim = c.get(f"/api/deals/{deal_id}/claims").json()[0]
    assert c.post(f"/api/deals/{deal_id}/claims/{claim['id']}/review", json={"action": "accept"}).status_code == 200
    assert _progress(c, deal_id)["findings"] is True and _progress(c, deal_id)["evidence"] is False

    detail = c.get(f"/api/deals/{deal_id}/claims/{claim['id']}").json()
    eid = detail["source_evidence"]["id"]
    # Reading the row (what a citation chip does for its label) is not an open; the viewer reports one.
    assert c.get(f"/api/deals/{deal_id}/evidence/{eid}").status_code == 200
    assert _progress(c, deal_id)["evidence"] is False
    assert c.post(f"/api/deals/{deal_id}/evidence/{eid}/opened").status_code == 204
    assert c.post(f"/api/deals/{deal_id}/evidence/{eid}/opened").status_code == 204
    opened = db.scalars(
        select(AuditEvent).where(AuditEvent.deal_id == uuid.UUID(deal_id), AuditEvent.event_type == "evidence.opened")
    ).all()
    assert len(opened) == 1 and opened[0].object_id == uuid.UUID(eid), "one row per evidence, user, and day"
    assert opened[0].summary.startswith("Opened evidence in northstar-")
    assert _progress(c, deal_id) == {"documents": True, "findings": True, "evidence": True, "questions": False}

    assert c.get(f"/api/deals/{deal_id}/seller-questions/export").status_code == 200
    assert _progress(c, deal_id) == {"documents": True, "findings": True, "evidence": True, "questions": True}


def test_progress_counts_a_chat_message_as_reviewing_findings(owner, db):
    c, deal_id = owner
    assert _progress(c, deal_id)["findings"] is False
    thread = ChatThread(deal_id=uuid.UUID(deal_id), user_id=None, title="usage")
    db.add(thread)
    db.flush()
    db.add(ChatMessage(thread_id=thread.id, role="user", content="hi", provider="mock", model="rules-v1", prompt_version="v0"))
    failed = ChatMessage(thread_id=thread.id, role="assistant", content="", provider="mock", model="rules-v1", prompt_version="v0")
    failed.error = "Groq rejected the API key."
    db.add(failed)
    db.commit()
    assert _progress(c, deal_id)["findings"] is False, "a question with no answer, or a failed answer, is not reviewing"
    ok = ChatMessage(thread_id=thread.id, role="assistant", content="The add-backs…", provider="mock", model="rules-v1", prompt_version="v0")
    db.add(ok)
    db.commit()
    assert _progress(c, deal_id)["findings"] is True
    # leave the thread for the usage test below, without the assistant rows it does not expect
    db.delete(failed)
    db.delete(ok)
    db.commit()


# ---------- usage ----------------------------------------------------------------------------


def test_usage_totals_with_fake_chat_rows(owner, db):
    c, deal_id = owner
    thread = db.scalar(select(ChatThread).where(ChatThread.deal_id == uuid.UUID(deal_id)))
    assert thread is not None
    db.add(
        ChatMessage(
            thread_id=thread.id,
            role="assistant",
            content="…",
            provider="anthropic",
            model="claude-haiku-4-5",
            prompt_version="v0",
            usage={"input_tokens": 1000, "output_tokens": 500, "model": "claude-haiku-4-5"},
            tool_calls=[{"name": "get_findings"}, {"name": "get_claim"}],
        )
    )
    db.add(
        ChatMessage(
            thread_id=thread.id, role="assistant", content="…", provider="mock", model="rules-v1", prompt_version="v0", usage={}
        )
    )
    db.commit()
    r = c.get(f"/api/deals/{deal_id}/usage")
    assert r.status_code == 200, r.text
    u = r.json()
    assert set(u) == {"chat", "documents", "storage_bytes", "cost_estimate_usd", "pricing_note"}
    assert u["chat"] == {
        "messages": 2,
        "input_tokens": 1000,
        "output_tokens": 500,
        "tool_calls": 2,
        "by_model": {"claude-haiku-4-5": 1, "rules-v1": 1},
    }
    assert u["cost_estimate_usd"] == pytest.approx(0.0035)
    assert u["documents"]["count"] == 7 and u["documents"]["pages"] > 0 and u["documents"]["rows"] > 0
    assert u["documents"]["bytes"] > 0 and u["storage_bytes"] == u["documents"]["bytes"]
    assert "free tier" in u["pricing_note"] and "No price is known" not in u["pricing_note"]
    db.add(
        ChatMessage(
            thread_id=thread.id,
            role="assistant",
            content="…",
            provider="custom",
            model="mystery-9",
            prompt_version="v0",
            usage={"input_tokens": 10, "output_tokens": 10},
        )
    )
    db.commit()
    u = c.get(f"/api/deals/{deal_id}/usage").json()
    assert u["cost_estimate_usd"] is None and "custom/mystery-9" in u["pricing_note"]
    assert u["chat"]["messages"] == 3 and u["chat"]["input_tokens"] == 1010


# ---------- review dataset ------------------------------------------------------------------


def test_review_dataset_lines(owner, stranger):
    c, deal_id = owner
    claims = c.get(f"/api/deals/{deal_id}/claims").json()
    supported = next(x for x in claims if x["status"] == "supported")
    growth = next(x for x in claims if x["metric_key"] == "cagr" and x["doc_type"] == "cim")
    assert c.post(f"/api/deals/{deal_id}/claims/{supported['id']}/review", json={"action": "accept"}).status_code == 200
    r = c.post(
        f"/api/deals/{deal_id}/claims/{growth['id']}/review",
        json={
            "action": "correct",
            "corrected_value": "11.6",
            "corrected_unit": "pct",
            "resulting_status": "contradicted",
            "note": "Confirmed against statements",
        },
    )
    assert r.status_code == 200, r.text
    r = c.get(f"/api/deals/{deal_id}/review-dataset")
    assert r.status_code == 200, r.text
    assert r.headers["content-disposition"] == 'attachment; filename="bearcase-northstar-hvac-services--llc-reviews.jsonl"'
    assert r.headers["content-type"].startswith("application/x-ndjson")
    rows = [json.loads(line) for line in r.text.splitlines() if line.strip()]
    assert len(rows) == 2 and r.text.endswith("\n")
    by_claim = {row["claim_id"]: row for row in rows}
    assert set(by_claim) == {supported["id"], growth["id"]}
    for row in rows:
        assert set(row) == {
            "deal_id",
            "claim_id",
            "claim_type",
            "claim_text",
            "claimed_value",
            "claimed_unit",
            "ai_status",
            "ai_rule",
            "ai_rationale",
            "verified_value",
            "reviewer_action",
            "reviewer_status",
            "reviewer_value",
            "reviewer_note",
            "evidence",
        }
        assert row["evidence"] and all(set(e) == {"id", "role", "document", "locator", "text"} for e in row["evidence"])
        assert all(len(e["text"]) <= 200 and e["document"].startswith("northstar-") for e in row["evidence"])
        assert row["evidence"][0]["role"] == "source"
    g = by_claim[growth["id"]]
    assert g["ai_status"] == "contradicted" and g["reviewer_action"] == "correct" and g["reviewer_status"] == "contradicted"
    assert g["reviewer_value"].startswith("11.6") and g["reviewer_note"] == "Confirmed against statements"
    assert g["verified_value"].startswith("11.5") and g["claimed_value"].startswith("18") and g["ai_rule"]
    assert any(e["role"] == "contradicting" for e in g["evidence"])
    s = by_claim[supported["id"]]
    assert s["reviewer_action"] == "accept" and s["reviewer_status"] == "supported" and s["reviewer_value"] is None
    events = _events(c, deal_id, "review_dataset.exported")
    assert len(events) == 1 and events[0]["payload"]["count"] == 2
    assert stranger.get(f"/api/deals/{deal_id}/review-dataset").status_code == 404


def test_cli_export_reviews_and_eval(owner, tmp_path, capsys):
    c, deal_id = owner
    out = tmp_path / "reviews.jsonl"
    assert cli_main(["export-reviews", "--deal", deal_id, "--out", str(out)]) == 0
    assert f"wrote 2 reviewed claims from deal {deal_id}" in capsys.readouterr().out
    lines = [json.loads(line) for line in out.read_text().splitlines()]
    api_rows = [json.loads(line) for line in c.get(f"/api/deals/{deal_id}/review-dataset").text.splitlines()]
    assert lines == api_rows

    assert cli_main(["eval", "--reviews", str(out)]) == 0
    text = capsys.readouterr().out
    assert "Reviewer agreement over 2 reviewed claims" in text
    assert "overall: 2/2 (100%)" in text and "revenue_growth: 1/1 (100%)" in text
    assert "corrections: 1 claim corrected by a reviewer" in text

    assert cli_main(["eval", "--reviews", str(out), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["rows"] == 2 and data["judged"] == 2 and data["agreement_rate"] == 1.0 and data["corrections"] == 1
    assert data["by_claim_type"]["revenue_growth"] == {"judged": 1, "agreed": 1} and data["disagreements"] == []

    # a rejection is a disagreement; an undone decision is not judged
    rows = [
        *api_rows,
        {
            **api_rows[0],
            "claim_id": "x",
            "reviewer_action": "reject",
            "reviewer_status": "review_required",
            "reviewer_note": "no",
        },
        {**api_rows[0], "claim_id": "y", "reviewer_action": "undo", "reviewer_status": None},
    ]
    mixed = tmp_path / "mixed.jsonl"
    mixed.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert cli_main(["eval", "--reviews", str(mixed), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["rows"] == 4 and data["judged"] == 3 and data["agreed"] == 2 and len(data["disagreements"]) == 1

    everything = tmp_path / "all.jsonl"
    assert cli_main(["export-reviews", "--out", str(everything)]) == 0
    assert len(everything.read_text().splitlines()) >= 2
    with pytest.raises(SystemExit):
        cli_main(["export-reviews", "--deal", str(uuid.uuid4()), "--out", str(tmp_path / "none.jsonl")])


# ---------- document deletion -----------------------------------------------------------------


def test_delete_document_removes_derived_rows_and_file(owner, stranger, db):
    c, deal_id = owner
    did = uuid.UUID(deal_id)
    docs = c.get(f"/api/deals/{deal_id}/documents").json()
    cim = next(d for d in docs if d["doc_type"] == "cim")
    cim_id = uuid.UUID(cim["id"])
    cim_claims = c.get(f"/api/deals/{deal_id}/claims?document_id={cim['id']}").json()
    assert len(cim_claims) >= 5
    assert c.post(f"/api/deals/{deal_id}/claims/{cim_claims[0]['id']}/review", json={"action": "accept"}).status_code == 200
    claim_ids = [uuid.UUID(x["id"]) for x in cim_claims]
    keys = db.scalars(select(DocumentVersion.storage_key).where(DocumentVersion.document_id == cim_id)).all()
    assert keys and all(get_storage().exists(k) for k in keys)
    assert db.scalar(select(func.count(Evidence.id)).where(Evidence.document_id == cim_id)) > 0
    assert db.scalar(select(func.count(ReviewDecision.id)).where(ReviewDecision.claim_id.in_(claim_ids))) >= 1
    assert db.scalar(select(func.count(ClaimEvidenceLink.id)).where(ClaimEvidenceLink.claim_id.in_(claim_ids))) >= len(claim_ids)
    assert db.scalar(select(func.count(Finding.id)).where(Finding.claim_id.in_(claim_ids))) >= 1
    other_evidence_before = db.scalar(
        select(func.count(Evidence.id)).where(Evidence.deal_id == did, Evidence.document_id != cim_id)
    )
    other_claims_before = db.scalar(select(func.count(Claim.id)).where(Claim.deal_id == did, Claim.document_id != cim_id))

    assert stranger.delete(f"/api/deals/{deal_id}/documents/{cim['id']}").status_code == 404
    r = c.delete(f"/api/deals/{deal_id}/documents/{cim['id']}")
    assert r.status_code == 204, r.text
    assert r.headers["x-bearcase-reanalyse"] == "true" and r.content == b""

    db.expire_all()
    assert c.get(f"/api/deals/{deal_id}/documents/{cim['id']}").status_code == 404
    assert c.delete(f"/api/deals/{deal_id}/documents/{cim['id']}").status_code == 404
    remaining = c.get(f"/api/deals/{deal_id}/documents").json()
    assert len(remaining) == 6 and all(d["status"] == "ready" and d["evidence_count"] > 0 for d in remaining)
    assert db.scalar(select(func.count(Document.id)).where(Document.id == cim_id)) == 0
    assert db.scalar(select(func.count(DocumentVersion.id)).where(DocumentVersion.document_id == cim_id)) == 0
    assert db.scalar(select(func.count(Evidence.id)).where(Evidence.document_id == cim_id)) == 0
    assert db.scalar(select(func.count(Claim.id)).where(Claim.id.in_(claim_ids))) == 0
    assert db.scalar(select(func.count(ClaimEvidenceLink.id)).where(ClaimEvidenceLink.claim_id.in_(claim_ids))) == 0
    assert db.scalar(select(func.count(ReviewDecision.id)).where(ReviewDecision.claim_id.in_(claim_ids))) == 0
    assert db.scalar(select(func.count(Finding.id)).where(Finding.claim_id.in_(claim_ids))) == 0
    assert db.scalar(select(func.count(Evidence.id)).where(Evidence.deal_id == did)) == other_evidence_before
    assert db.scalar(select(func.count(Claim.id)).where(Claim.deal_id == did)) == other_claims_before
    assert not any(get_storage().exists(k) for k in keys)
    events = _events(c, deal_id, "document.deleted")
    assert len(events) == 1 and events[0]["object_id"] == cim["id"]
    payload = events[0]["payload"]
    assert payload["display_name"] == "northstar-cim.pdf" and payload["claims_removed"] == len(claim_ids)
    assert payload["evidence_removed"] > 0 and payload["findings_removed"] >= 1 and payload["versions"] == 1
    assert c.get(f"/api/deals/{deal_id}/claims?document_id={cim['id']}").json() == []
    # the rest of the workflow keeps working on what is left
    qs = c.get(f"/api/deals/{deal_id}/seller-questions").json()["questions"]
    assert qs and all(q["claim_id"] not in {str(x) for x in claim_ids} for q in qs)
    assert _progress(c, deal_id)["documents"] is True
