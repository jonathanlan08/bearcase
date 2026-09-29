"""Read-only report share links: who may create them, what the public route reveals, and that only the token's hash
is stored. The owner, an editor, a viewer, and a stranger each use their own client; the public reader has no
cookie at all."""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from bearcase.api import ratelimit
from bearcase.api.app import app
from bearcase.config import get_settings
from bearcase.models import AuditEvent, Report, ReportShare
from bearcase.models.base import utcnow
from bearcase.models.enums import ReportStatus
from tests.test_accounts import _register, _seed_deal, _token_from, _verify

PRIVATE_NOTE = "Private draft: walk away if the seller will not open the ledger, marker zqxw"


def _join(owner: TestClient, deal_id: str, email: str, role: str) -> TestClient:
    r = owner.post(f"/api/deals/{deal_id}/members", json={"email": email, "role": role})
    assert r.status_code == 201, r.text
    member = _register(email, role.title())
    assert member.post("/api/invites/accept", json={"token": _token_from(email, "/invite")}).status_code == 200
    return member


@pytest.fixture(scope="module")
def setup() -> dict[str, Any]:
    owner = _register("report-share-owner@example.com", "Share Owner")
    _verify(owner, "report-share-owner@example.com")
    deal_id = _seed_deal(owner)
    report = owner.get(f"/api/deals/{deal_id}/report").json()
    assert report["status"] == "validated", report["validation"]
    return {
        "owner": owner,
        "deal_id": deal_id,
        "report_id": report["id"],
        "editor": _join(owner, deal_id, "report-share-editor@example.com", "editor"),
        "viewer": _join(owner, deal_id, "report-share-viewer@example.com", "viewer"),
        "stranger": _register("report-share-stranger@example.com", "Stranger"),
    }


def _share_url(s: dict[str, Any]) -> str:
    return f"/api/deals/{s['deal_id']}/reports/{s['report_id']}/share"


def _token(path: str) -> str:
    assert path.startswith("/r/")
    return path.removeprefix("/r/")


def test_editor_and_owner_create_viewer_forbidden_stranger_404(setup, db):
    r = setup["editor"].post(_share_url(setup))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["path"].startswith("/r/") and body["url"].endswith(body["path"]) and body["active"] is True
    assert body["expires_at"] is None and body["created_by"] == "Editor"

    r = setup["owner"].post(_share_url(setup), json={"expires_in_days": 7})
    assert r.status_code == 201 and r.json()["expires_at"] is not None

    r = setup["viewer"].post(_share_url(setup))
    assert r.status_code == 403 and "editor access" in r.json()["detail"]
    assert setup["viewer"].get(f"/api/deals/{setup['deal_id']}/reports/{setup['report_id']}/shares").status_code == 403
    assert setup["stranger"].post(_share_url(setup)).status_code == 404
    assert setup["stranger"].get(f"/api/deals/{setup['deal_id']}/reports/{setup['report_id']}/shares").status_code == 404
    # a report id from another deal is not found under this one
    assert setup["owner"].post(f"/api/deals/{setup['deal_id']}/reports/{uuid.uuid4()}/share").status_code == 404
    assert setup["owner"].post(_share_url(setup), json={"expires_in_days": 0}).status_code == 422

    # the list never carries a token or a path
    listing = setup["owner"].get(f"/api/deals/{setup['deal_id']}/reports/{setup['report_id']}/shares")
    assert listing.status_code == 200
    rows = listing.json()
    assert len(rows) >= 2 and all("path" not in row and "url" not in row and "token" not in row for row in rows)
    assert _token(body["path"]) not in listing.text

    events = db.scalars(
        select(AuditEvent.event_type).where(
            AuditEvent.deal_id == uuid.UUID(setup["deal_id"]), AuditEvent.event_type == "report.shared"
        )
    ).all()
    assert len(events) >= 2


def test_token_is_stored_only_as_its_hash(setup, db):
    r = setup["owner"].post(_share_url(setup))
    token = _token(r.json()["path"])
    row = db.get(ReportShare, uuid.UUID(r.json()["id"]))
    assert row is not None
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in {row.token_hash, str(row.id), str(row.report_id)}
    audit = db.scalars(select(AuditEvent).where(AuditEvent.event_type == "report.shared")).all()
    assert all(token not in (e.summary + str(e.payload)) for e in audit)


def test_unvalidated_report_cannot_be_shared(setup, db):
    latest = db.get(Report, uuid.UUID(setup["report_id"]))
    assert latest is not None
    failed = Report(
        deal_id=latest.deal_id,
        version_no=latest.version_no + 100,
        status=ReportStatus.FAILED_VALIDATION,
        outcome=latest.outcome,
        sections=latest.sections,
        validation={"valid": False},
        provider=latest.provider,
        model=latest.model,
        prompt_version=latest.prompt_version,
        schema_version=latest.schema_version,
        engine_version=latest.engine_version,
    )
    db.add(failed)
    db.commit()
    r = setup["owner"].post(f"/api/deals/{setup['deal_id']}/reports/{failed.id}/share")
    assert r.status_code == 409 and "validated" in r.json()["detail"]


def test_public_fetch_without_a_cookie_and_nothing_private_leaks(setup):
    owner, deal_id = setup["owner"], setup["deal_id"]
    claim = owner.get(f"/api/deals/{deal_id}/claims").json()[0]
    r = owner.post(f"/api/deals/{deal_id}/notes", json={"kind": "assumption", "text": PRIVATE_NOTE, "include_in_report": False})
    assert r.status_code == 201, r.text
    token = _token(owner.post(_share_url(setup)).json()["path"])

    public = TestClient(app)  # no session cookie, no Authorization header
    r = public.get(f"/api/shared/reports/{token}")
    assert r.status_code == 200, r.text
    assert r.headers["x-robots-tag"].startswith("noindex") and r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["company_name"].startswith("Northstar") and body["is_demo"] is True
    assert body["validation"]["valid"] is True and body["sections"]
    assert set(body) == {
        "company_name",
        "is_demo",
        "version_no",
        "generated_at",
        "outcome",
        "validation",
        "provenance",
        "sections",
        "evidence",
        "metrics",
    }
    # citations resolve to a document name, a location, and a short passage
    assert body["evidence"], "evidence citations resolve"
    ev = next(iter(body["evidence"].values()))
    assert set(ev) == {"document_name", "locator", "snippet"} and ev["document_name"] and len(ev["snippet"]) <= 240
    cited = {e for s in body["sections"] for st in s["statements"] for e in st["evidence_ids"]}
    cited |= {e for s in body["sections"] for row in s["table"]["rows"] for e in row["evidence_ids"]}
    assert cited == set(body["evidence"]), "every cited passage resolves, and nothing uncited is sent"
    assert body["metrics"] and all(m["label"] for m in body["metrics"].values())

    text = r.text
    for secret in (
        PRIVATE_NOTE,
        deal_id,
        setup["report_id"],
        claim["id"],
        "report-share-owner@example.com",
        "storage_key",
        "claim_id",
        "input_snapshot",
    ):
        assert secret not in text, secret

    # the token opens only this report: the rest of the deal still needs a session
    assert public.get(f"/api/deals/{deal_id}").status_code == 401
    assert public.get(f"/api/deals/{deal_id}/documents").status_code == 401


def test_included_notes_appear_because_they_are_in_the_report(setup):
    owner, deal_id = setup["owner"], setup["deal_id"]
    note = "Conclusion for the lender: the backlog story is the seller's, not the statements'."
    assert owner.post(f"/api/deals/{deal_id}/notes", json={"kind": "open_question", "text": note}).status_code == 201
    assert owner.post(f"/api/deals/{deal_id}/report").status_code == 202
    fresh = owner.get(f"/api/deals/{deal_id}/report").json()
    assert fresh["status"] == "validated"
    r = owner.post(f"/api/deals/{deal_id}/reports/{fresh['id']}/share")
    assert r.status_code == 201
    body = TestClient(app).get(f"/api/shared/reports/{_token(r.json()['path'])}").json()
    assert body["sections"][0]["key"] == "reviewer_memo"
    assert any(note in st["text"] for st in body["sections"][0]["statements"])
    assert PRIVATE_NOTE not in str(body)


def test_revoked_unknown_and_expired_links_are_404(setup, db):
    owner = setup["owner"]
    created = owner.post(_share_url(setup)).json()
    token = _token(created["path"])
    public = TestClient(app)
    assert public.get(f"/api/shared/reports/{token}").status_code == 200

    shares = f"/api/deals/{setup['deal_id']}/reports/{setup['report_id']}/shares"
    assert setup["viewer"].delete(f"{shares}/{created['id']}").status_code == 403
    assert setup["stranger"].delete(f"{shares}/{created['id']}").status_code == 404
    assert owner.delete(f"{shares}/{uuid.uuid4()}").status_code == 404
    assert setup["editor"].delete(f"{shares}/{created['id']}").status_code == 204
    assert owner.delete(f"{shares}/{created['id']}").status_code == 204  # idempotent
    r = public.get(f"/api/shared/reports/{token}")
    assert r.status_code == 404 and "revoked" in r.json()["detail"]
    row = next(s for s in owner.get(shares).json() if s["id"] == created["id"])
    assert row["active"] is False and row["revoked_at"] is not None
    revoked_events = db.scalars(
        select(AuditEvent).where(
            AuditEvent.event_type == "report.share_revoked", AuditEvent.object_id == uuid.UUID(setup["report_id"])
        )
    ).all()
    assert len(revoked_events) == 1  # the second DELETE did not write another row

    assert public.get("/api/shared/reports/" + "A" * 43).status_code == 404
    assert public.get("/api/shared/reports/short").status_code == 404

    expiring = owner.post(_share_url(setup), json={"expires_in_days": 1}).json()
    row_db = db.get(ReportShare, uuid.UUID(expiring["id"]))
    assert row_db is not None
    row_db.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    assert public.get(f"/api/shared/reports/{_token(expiring['path'])}").status_code == 404


def test_public_route_is_rate_limited_by_client_address(setup, monkeypatch):
    token = _token(setup["owner"].post(_share_url(setup)).json()["path"])
    monkeypatch.setattr(
        ratelimit,
        "get_settings",
        lambda: get_settings().model_copy(update={"rate_limit_enabled": True, "rate_limit_per_minute": 2}),
    )
    ratelimit.limiter.reset()
    try:
        public = TestClient(app)
        assert public.get(f"/api/shared/reports/{token}").status_code == 200
        assert public.get(f"/api/shared/reports/{token}").status_code == 200
        r = public.get(f"/api/shared/reports/{token}")
        assert r.status_code == 429 and r.headers["retry-after"].isdigit()
        # its own bucket: reading a shared report does not spend the address's demo-start budget
        assert public.post("/api/demo/session").status_code == 200
    finally:
        ratelimit.limiter.reset()
