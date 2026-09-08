"""The messy demo (Tidewater Plumbing): BearCase stops and asks instead of producing a confident number."""

from fastapi.testclient import TestClient

from bearcase.api.app import app


def _start():
    c = TestClient(app)
    r = c.post("/api/demo/session?deal=messy")
    assert r.status_code == 200, r.text
    return c, r.json()


def test_messy_package_is_read_with_its_problems_visible():
    c, deal = _start()
    assert deal["company_name"].startswith("Tidewater")
    mapping = c.get(f"/api/deals/{deal['id']}/financials/mapping").json()
    s = next(x for x in mapping["statements"] if x["mapped"])
    assert [p["label"] for p in s["periods"]] == ["FY2022", "FY2024"], "years sorted, the missing one visible"
    assert s["scale"] == 1000
    revenue = next(line for line in s["lines"] if line["key"] == "revenue")
    assert revenue["needs_review"] and revenue["components"] == ["Revenue - service", "Revenue - installation"]
    assert revenue["cells"]["FY2024"]["value"] == "5200000", "components summed and scaled to dollars"
    fin = c.get(f"/api/deals/{deal['id']}/financials").json()
    growth = [m for m in fin["metrics"] if m["key"] == "revenue_growth"]
    assert growth and growth[0]["requires_review"], "growth across a two-year gap is flagged"
    cagr = next(m for m in fin["metrics"] if m["key"] == "cagr")
    assert cagr["value"].startswith("12.6"), "12.6% a year over the two elapsed years, not 26.8% over one"


def test_messy_claims_and_queue():
    c, deal = _start()
    claims = c.get(f"/api/deals/{deal['id']}/claims").json()
    by_type = {cl["claim_type"]: cl for cl in claims}
    assert by_type["revenue_growth"]["status"] == "contradicted"
    # The figure it would match was summed from two rows, so the claim waits for a person instead of passing.
    assert by_type["revenue"]["status"] == "review_required"
    assert by_type["customer_concentration"]["status"] == "unsupported", "no customer file in the package"
    queue = c.get(f"/api/deals/{deal['id']}/review-queue").json()
    groups = {g["key"]: g["items"] for g in queue["groups"]}
    assert any("summed" in i["title"] for i in groups["figures"])
    assert any("multiplied by 1,000" in i["title"] for i in groups["figures"])
    assert len(groups["missing"]) >= 2, "quality of earnings and tax returns are promised but absent"
    assert queue["total"] >= 6


def test_demo_choice_is_validated_and_deals_are_separate():
    c = TestClient(app)
    assert c.post("/api/demo/session?deal=nope").status_code == 400
    a = c.post("/api/demo/session").json()
    b = c.post("/api/demo/session?deal=messy").json()
    assert a["id"] != b["id"] and a["company_name"].startswith("Northstar") and b["company_name"].startswith("Tidewater")
    assert c.post("/api/demo/session").json()["id"] == a["id"], "the tidy deal is reused, not reseeded"
