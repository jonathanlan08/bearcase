"""The correction loop: a person fixes one mapped figure, the deal recomputes, and what changed is recorded."""

import uuid

from sqlalchemy import select

from decimal import Decimal

from bearcase.models import StatementCorrection


def _own_demo():
    """A fresh demo visitor with its own Northstar copy: a correction re-analyses the deal, and the shared session
    fixture is used by tests that assume the seeded findings."""
    from fastapi.testclient import TestClient

    from bearcase.api.app import app

    c = TestClient(app)
    return c, c.post("/api/demo/session").json()["id"]


def test_correcting_revenue_recomputes_and_records_impact(db):
    client, deal_id = _own_demo()
    before = client.get(f"/api/deals/{deal_id}/financials").json()
    cagr_before = next(m for m in before["metrics"] if m["key"] == "cagr")["value"]
    def statuses() -> dict[str, str]:
        return {c["claim_type"]: c["status"] for c in client.get(f"/api/deals/{deal_id}/claims").json()}

    claims_before = statuses()
    try:
        _check(client, deal_id, db, cagr_before, claims_before, statuses)
    finally:
        r2 = client.post(f"/api/deals/{deal_id}/financials/corrections", json={"line_key": "revenue", "period_label": "FY2024", "value": "12950000", "note": "revert"})
        assert r2.status_code == 201
    assert statuses()["revenue"] == "supported"


def _check(client, deal_id, db, cagr_before, claims_before, statuses):
    r = client.post(
        f"/api/deals/{deal_id}/financials/corrections",
        json={"line_key": "revenue", "period_label": "FY2024", "value": "13500000", "note": "Tax return shows 13.5M; the workbook cell is stale."},
    )
    assert r.status_code == 201, r.text
    c = r.json()
    assert Decimal(c["original_value"]) == Decimal("12950000") and Decimal(c["corrected_value"]) == Decimal("13500000")
    impact = c["impact"]
    changed = {(m["key"], m["period"]) for m in impact["metrics"]}
    assert ("revenue", "FY2024") in changed and ("cagr", "FY2024") in changed and ("revenue_growth", "FY2024") in changed
    after = client.get(f"/api/deals/{deal_id}/financials").json()
    assert next(m for m in after["metrics"] if m["key"] == "cagr")["value"] != cagr_before
    rev = next(m for m in after["metrics"] if m["key"] == "revenue" and m["period_label"] == "FY2024")
    assert Decimal(rev["value"]) == Decimal("13500000") and rev["input_snapshot"]["corrected"] is True
    assert rev["input_snapshot"]["mapped_value"] == "12950000", "the mapper's value stays beside the correction"
    assert rev["raw_value"] == "12950000", "the cell text is untouched"
    # the revenue claim said $12.95M; it no longer matches the corrected figure
    claims_after = statuses()
    assert claims_before["revenue"] == "supported" and claims_after["revenue"] == "contradicted"
    assert any(x["after"] == "contradicted" and "12.95" in x["text"] for x in impact["claims_changed"])
    # additive: the correction row exists with the original, and the mapping route shows it on the cell
    row = db.scalar(select(StatementCorrection).where(StatementCorrection.id == uuid.UUID(c["id"])))
    assert row is not None and Decimal(row.original_value) == Decimal("12950000")
    mapping = client.get(f"/api/deals/{deal_id}/financials/mapping").json()
    line = next(x for s in mapping["statements"] if s["mapped"] for x in s["lines"] if x["key"] == "revenue")
    assert Decimal(line["cells"]["FY2024"]["correction"]["corrected_value"]) == Decimal("13500000")
    assert client.get(f"/api/deals/{deal_id}/financials/corrections").json()[0]["id"] == c["id"]
    # the audit trail names it
    audit = client.get(f"/api/deals/{deal_id}/audit").json()
    assert any(e["event_type"] == "statement.corrected" for e in audit)


def test_correction_validation(client, demo):
    deal_id = demo["id"]
    assert client.post(f"/api/deals/{deal_id}/financials/corrections", json={"line_key": "nope", "period_label": "FY2024", "value": "1"}).status_code == 422
    assert client.post(f"/api/deals/{deal_id}/financials/corrections", json={"line_key": "revenue", "period_label": "FY1999", "value": "1"}).status_code == 422


def test_summary_carries_the_confidence_budget(client, demo):
    s = client.get(f"/api/deals/{demo['id']}/summary").json()
    c = s["confidence"]
    assert set(c) == {"decided", "rules_only", "needs_person", "no_evidence", "total"}
    assert c["total"] == c["decided"] + c["rules_only"] + c["needs_person"] + c["no_evidence"] and c["total"] >= 15
