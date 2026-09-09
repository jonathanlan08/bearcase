"""The reviewer's notebook: notes with sources, refused without them when they state a figure, first in the report."""

from fastapi.testclient import TestClient

from bearcase.api.app import app


def _own_demo():
    c = TestClient(app)
    return c, c.post("/api/demo/session").json()["id"]


def test_notes_round_trip_and_citation_rule():
    c, deal = _own_demo()
    claim = c.get(f"/api/deals/{deal}/claims").json()[1]
    detail = c.get(f"/api/deals/{deal}/claims/{claim['id']}").json()
    ev = [l["evidence"]["id"] for l in detail["links"]][:2]
    metric = detail["verified_metric_id"]
    # a figure without a source is refused
    r = c.post(f"/api/deals/{deal}/notes", json={"kind": "conclusion", "text": "Growth is really 11.6%, not 18%."})
    assert r.status_code == 422 and "cite a source" in r.json()["detail"]
    r = c.post(f"/api/deals/{deal}/notes", json={"kind": "conclusion", "text": "Growth is really 11.6%, not 18%; price on the statements, not the memo.", "evidence_ids": ev, "metric_ids": [metric], "claim_id": claim["id"]})
    assert r.status_code == 201, r.text
    nid = r.json()["id"]
    r2 = c.post(f"/api/deals/{deal}/notes", json={"kind": "open_question", "text": "Why does the memo use a different base year than the statements?"})
    assert r2.status_code == 201
    listed = c.get(f"/api/deals/{deal}/notes").json()
    assert listed["counts"] == {"conclusion": 1, "assumption": 0, "open_question": 1}
    assert c.post(f"/api/deals/{deal}/notes", json={"text": "x" * 10, "evidence_ids": ["00000000-0000-0000-0000-000000000000"]}).status_code == 422
    # the report opens with the memo and still validates
    assert c.post(f"/api/deals/{deal}/report").status_code in (200, 201, 202)
    report = c.get(f"/api/deals/{deal}/report").json()
    assert report["sections"][0]["key"] == "reviewer_memo"
    memo = report["sections"][0]
    assert any("Conclusion: Growth is really" in s["text"] and s["metric_ids"] for s in memo["statements"])
    assert report["validation"]["valid"] is True
    pdf = c.get(f"/api/deals/{deal}/summary.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert c.delete(f"/api/deals/{deal}/notes/{nid}").status_code == 204
    assert c.get(f"/api/deals/{deal}/notes").json()["counts"]["conclusion"] == 0


def test_drafts_stay_out_of_the_report_and_search_finds_sources():
    c, deal = _own_demo()
    hits = c.get(f"/api/deals/{deal}/evidence-search?q=maintenance agreements").json()
    assert hits and all(h["id"] and h["document_name"] and "maintenance" in h["excerpt"].lower() for h in hits)
    assert c.get(f"/api/deals/{deal}/evidence-search?q=a").json() == []
    r = c.post(f"/api/deals/{deal}/notes", json={"kind": "assumption", "text": "The seller's growth story leans on maintenance agreements.", "evidence_ids": [hits[0]["id"]], "include_in_report": False})
    assert r.status_code == 201 and r.json()["include_in_report"] is False
    nid = r.json()["id"]
    c.post(f"/api/deals/{deal}/report")
    report = c.get(f"/api/deals/{deal}/report").json()
    assert report["sections"][0]["key"] != "reviewer_memo", "a draft is private"
    assert c.patch(f"/api/deals/{deal}/notes/{nid}", json={"include_in_report": True}).json()["include_in_report"] is True
    c.post(f"/api/deals/{deal}/report")
    assert c.get(f"/api/deals/{deal}/report").json()["sections"][0]["key"] == "reviewer_memo"


def test_emphasised_markers_still_resolve():
    from bearcase.chat.service import normalize_markers

    assert normalize_markers("see **[E:abcdef12]**") == "see [E:abcdef12]"
    assert normalize_markers("see __[M:abcdef12]__.") == "see [M:abcdef12]."
    # a marker inside a code span is a literal and stays one (invariant 9: code regions are verbatim)
    assert normalize_markers("a marker looks like `[M:abcdef12]`") == "a marker looks like `[M:abcdef12]`"
