"""The review inbox: what a person still has to decide, grouped, with the page that settles each item."""


def test_review_queue_groups_and_links(client, demo):
    r = client.get(f"/api/deals/{demo['id']}/review-queue")
    assert r.status_code == 200, r.text
    body = r.json()
    keys = [g["key"] for g in body["groups"]]
    assert keys == ["figures", "discrepancies", "adjustments", "missing"]
    by = {g["key"]: g for g in body["groups"]}
    assert by["figures"]["items"] == [], "the demo workbook maps cleanly"
    assert len(by["discrepancies"]["items"]) >= 6
    assert all(i["href_key"] == "claims" and i["claim_id"] for i in by["discrepancies"]["items"])
    assert by["discrepancies"]["items"][0]["status"] == "contradicted", "contradictions come first"
    assert any("rule said accepted" in i["title"] for i in by["adjustments"]["items"])
    assert len(by["missing"]["items"]) >= 1 and all(i["resolution"] for i in by["missing"]["items"])
    assert body["total"] == sum(len(g["items"]) for g in body["groups"])


def test_findings_carry_a_resolution(client, demo):
    r = client.get(f"/api/deals/{demo['id']}/findings")
    assert r.status_code == 200
    rows = r.json()
    contradictions = [f for f in rows if f["kind"] == "contradiction"]
    assert contradictions and all(f["resolution"] for f in contradictions)
    assert any("growth" in f["resolution"].lower() or "reconciliation" in f["resolution"].lower() for f in contradictions)
