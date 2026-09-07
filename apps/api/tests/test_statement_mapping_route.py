"""The "check what we read" route: the mapper's interpretation of the demo workbook, with cells and coverage."""


def test_mapping_reports_periods_scale_lines_and_coverage(client, demo):
    r = client.get(f"/api/deals/{demo['id']}/financials/mapping")
    assert r.status_code == 200, r.text
    body = r.json()
    mapped = [s for s in body["statements"] if s["mapped"]]
    assert len(mapped) == 1
    s = mapped[0]
    assert [p["label"] for p in s["periods"]] == ["FY2022", "FY2023", "FY2024"]
    assert s["scale"] == 1 and s["header_row"] is not None
    revenue = next(line for line in s["lines"] if line["key"] == "revenue")
    assert revenue["cells"]["FY2024"]["value"] == "12950000" and revenue["cells"]["FY2024"]["evidence_id"]
    assert revenue["cells"]["FY2024"]["cell"].endswith(str(revenue["cells"]["FY2024"]["cell"][-1]))
    assert revenue["needs_review"] is False and revenue["components"] is None
    cov = body["coverage"]
    assert cov["documents_ready"] >= 5 and cov["statements_mapped"] == 1 and cov["statements_unmapped"] == 0
    assert set(cov["claims_by_status"]) == {"pending", "supported", "contradicted", "unsupported", "review_required"}
    assert isinstance(cov["unmapped_rows"], int) and isinstance(cov["metrics_requiring_review"], int)


def test_mapping_is_owner_scoped(client, demo):
    from fastapi.testclient import TestClient

    from bearcase.api.app import app

    stranger = TestClient(app)
    stranger.post("/api/demo/session")
    assert stranger.get(f"/api/deals/{demo['id']}/financials/mapping").status_code == 404
