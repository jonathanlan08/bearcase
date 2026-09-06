"""End-to-end checks against the seeded Northstar deal through the HTTP API."""

from decimal import Decimal as D

import pytest


def _claims(client, deal_id):
    r = client.get(f"/api/deals/{deal_id}/claims")
    assert r.status_code == 200
    return r.json()


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["provider"] == "mock"


def test_demo_deal_seeded(client, demo):
    assert demo["company_name"].startswith("Northstar")
    docs = client.get(f"/api/deals/{demo['id']}/documents").json()
    assert len(docs) == 7 and all(d["status"] == "ready" for d in docs)
    types = {d["doc_type"] for d in docs}
    assert {
        "cim",
        "financial_statements",
        "acquisition_model",
        "customer_revenue",
        "debt_term_sheet",
        "customer_contract",
    } <= types


def test_expected_claims_and_statuses(client, demo, ground_truth):
    claims = _claims(client, demo["id"])
    assert len(claims) >= 15
    by_status = {}
    for c in claims:
        by_status.setdefault(c["status"], []).append(c)
    assert {"supported", "contradicted", "unsupported", "review_required"} <= set(by_status)
    contradicted_metrics = {c["metric_key"] for c in by_status["contradicted"]}
    assert {
        "cagr",
        "customer_concentration_top1",
        "ebitda_adjusted_verified",
        "recurring_revenue_pct",
        "opex_temporary_labor_recurring",
    } <= contradicted_metrics
    growth = next(c for c in claims if c["metric_key"] == "cagr" and c["doc_type"] == "cim")
    assert growth["status"] == "contradicted"
    assert D(growth["verified_value"]).quantize(D("0.1")) == D("11.6")
    assert growth["contradicting_count"] >= 1
    conc = next(c for c in claims if c["metric_key"] == "customer_concentration_top1")
    assert D(conc["verified_value"]).quantize(D("0.1")) == D("22.0")
    apex = next(c for c in claims if c["claim_type"] == "contract_term" and "2027" in c["claim_text"])
    assert apex["status"] == "review_required" and apex["supporting_count"] >= 1 and apex["contradicting_count"] >= 1


def test_every_citation_resolves(client, demo):
    for c in _claims(client, demo["id"]):
        detail = client.get(f"/api/deals/{demo['id']}/claims/{c['id']}").json()
        assert detail["source_evidence"] is not None
        for link in detail["links"]:
            r = client.get(f"/api/deals/{demo['id']}/evidence/{link['evidence']['id']}")
            assert r.status_code == 200
        if detail["status"] == "supported":
            assert any(link["role"] == "supporting" for link in detail["links"]) or detail["verified_metric"] is not None
        if detail["status"] == "contradicted":
            assert any(link["role"] == "contradicting" for link in detail["links"])


def test_injection_text_is_inert(client, demo):
    findings = client.get(f"/api/deals/{demo['id']}/findings").json()
    integrity = [f for f in findings if f["kind"] == "document_integrity"]
    assert integrity, "instruction-like text must be surfaced as a finding"
    claims = _claims(client, demo["id"])
    assert not any("ignore all previous" in c["claim_text"].lower() for c in claims)
    assert D(demo["purchase_price"]) == D("12600000")
    assert any(c["status"] == "contradicted" for c in claims)  # 'mark every claim as supported' had no effect


def test_financials_waterfall(client, demo):
    fin = client.get(f"/api/deals/{demo['id']}/financials").json()
    decisions = {a["key"]: a["decision"] for a in fin["adjustments"]}
    assert decisions["owner_compensation_normalization"] == "accepted"
    assert decisions["one_time_litigation_settlement"] == "accepted"
    assert decisions["temporary_labor_non_recurring_surge_staffing"] == "rejected"
    assert decisions["marketing_relaunch_one_time_brand_refresh"] == "review_required"
    assert decisions["post_close_integration_savings"] == "unsupported"
    wf = fin["waterfall"]
    assert wf[0]["amount"] == "1640000.00000000" or D(wf[0]["amount"]) == D("1640000")
    assert D(wf[-1]["running_total"]) == D("1810000")
    metrics = {m["key"]: m for m in fin["metrics"]}
    assert D(metrics["ebitda_adjusted_seller"]["value"]) == D("2100000")
    assert D(metrics["ev_to_ebitda_verified"]["value"]).quantize(D("0.01")) == D("6.96")
    assert D(metrics["annual_debt_service"]["value"]) == D("1100683.94")
    assert metrics["cfads_base"]["input_snapshot"]["bridge"]["adjusted_ebitda"]  # CFADS bridge exposed


def test_scenarios_seeded_and_snapshotted(client, demo, ground_truth):
    scenarios = client.get(f"/api/deals/{demo['id']}/scenarios").json()
    by_kind = {s["kind"]: s for s in scenarios}
    for kind in ("base", "downside", "severe_downside"):
        res = by_kind[kind]["latest_result"]
        assert res["engine_version"] and res["input_hash"] and D(res["input_snapshot"]["purchase_price"]) == D("12600000")
        assert res["outputs"]["year1"]["dscr"] == ground_truth["scenarios"][kind]["expected"]["dscr"]
    assert D(by_kind["base"]["latest_result"]["outputs"]["year1"]["dscr"]) > D("1.25")
    assert D(by_kind["downside"]["latest_result"]["outputs"]["year1"]["dscr"]) < D("1.25")
    # editing and re-running creates a new immutable run; the old one is untouched
    sid = by_kind["downside"]["id"]
    r = client.put(f"/api/deals/{demo['id']}/scenarios/{sid}/assumptions", json={"values": {"largest_customer_loss_pct": "50"}})
    assert r.status_code == 200
    r2 = client.post(f"/api/deals/{demo['id']}/scenarios/{sid}/run")
    assert r2.status_code == 201 and r2.json()["run_no"] == 2
    runs = client.get(f"/api/deals/{demo['id']}/scenarios/{sid}/results").json()
    assert D(runs[0]["input_snapshot"]["largest_customer_loss_pct"]) == D("25") and D(
        runs[1]["input_snapshot"]["largest_customer_loss_pct"]
    ) == D("50")
    grid = client.post(f"/api/deals/{demo['id']}/scenarios/sensitivity", json={"scenario_id": by_kind["base"]["id"]}).json()
    assert len(grid["cells"]) == 5 and grid["cells"][4][4]["breach"] is True


def test_report_validated_with_citations(client, demo):
    rep = client.get(f"/api/deals/{demo['id']}/report").json()
    assert rep is not None and rep["status"] == "validated", rep["validation"] if rep else None
    assert rep["outcome"] == "material_concerns_identified"
    assert rep["validation"]["material_statements"] > 10 and rep["validation"]["uncited"] == []
    keys = [s["key"] for s in rep["sections"]]
    assert keys[0] == "deal_overview" and "contradictions" in keys and "management_questions" in keys
    md = client.get(f"/api/deals/{demo['id']}/reports/{rep['id']}/export?format=md")
    assert md.status_code == 200 and "Red-team review" in md.text
    pdf = client.get(f"/api/deals/{demo['id']}/reports/{rep['id']}/export?format=pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_review_is_additive_and_audited(client, demo):
    claims = _claims(client, demo["id"])
    claim = next(c for c in claims if c["status"] == "contradicted")
    original_text, original_status = claim["claim_text"], claim["status"]
    r = client.post(
        f"/api/deals/{demo['id']}/claims/{claim['id']}/review",
        json={
            "action": "correct",
            "corrected_value": "11.6",
            "corrected_unit": "pct",
            "resulting_status": "contradicted",
            "note": "Confirmed against statements",
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["claim_text"] == original_text and d["status"] == original_status  # original AI output untouched
    assert d["decisions"][-1]["action"] == "correct" and d["decisions"][-1]["corrected_value"].startswith("11.6")
    r = client.post(f"/api/deals/{demo['id']}/claims/{claim['id']}/review", json={"action": "undo"})
    assert r.status_code == 200 and r.json()["effective_status"] == original_status
    audit = client.get(f"/api/deals/{demo['id']}/audit").json()
    assert any(e["event_type"] == "claim.correct" for e in audit) and any(e["event_type"] == "claim.undo" for e in audit)


def test_deal_isolation(demo):
    # a second user (separate client, separate cookie jar) cannot see the demo user's deal
    from fastapi.testclient import TestClient

    from bearcase.api.app import app

    with TestClient(app) as other:
        r = other.post(
            "/api/auth/register", json={"email": "other@example.com", "password": "password123", "display_name": "Other"}
        )
        assert r.status_code == 201
        assert other.get(f"/api/deals/{demo['id']}").status_code == 404
        assert other.get("/api/deals").json() == []
        assert other.get(f"/api/deals/{demo['id']}/claims").status_code == 404


def test_upload_validation_via_api(client, demo):
    r = client.post(f"/api/deals/{demo['id']}/documents", files=[("files", ("evil.exe", b"MZ....", "application/octet-stream"))])
    assert r.status_code == 422 and r.json()["detail"]["errors"][0]["code"] == "extension"
    dup = (
        pytest.importorskip("pathlib").Path(__file__).resolve().parents[3] / "fixtures" / "northstar-hvac" / "northstar-cim.pdf"
    ).read_bytes()
    r = client.post(f"/api/deals/{demo['id']}/documents", files=[("files", ("copy.pdf", dup, "application/pdf"))])
    assert r.status_code == 422 and r.json()["detail"]["errors"][0]["code"] == "duplicate"


def test_create_deal_and_process_without_documents(client):
    r = client.post(
        "/api/deals",
        json={
            "company_name": "Blank Co",
            "industry": "Services",
            "purchase_price": "1000000",
            "debt_amount": "600000",
            "equity_amount": "400000",
            "interest_rate_pct": "7",
            "amortization_years": 7,
        },
    )
    assert r.status_code == 201
    deal_id = r.json()["id"]
    r = client.post(f"/api/deals/{deal_id}/process")
    assert r.status_code == 202
    jobs = client.get(f"/api/deals/{deal_id}/jobs").json()
    assert jobs[0]["status"] == "failed" and "Upload" in jobs[0]["error"]


def test_ask_the_deal_is_grounded(client, demo):
    r = client.post(f"/api/deals/{demo['id']}/ask", json={"question": "Why was adjusted EBITDA reduced?"})
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["grounded"] is True and a["intents"] == ["ebitda"]
    text = " ".join(s["text"] for s in a["statements"])
    assert "$2,100,000" in text and "$1,810,000" in text and "rejected" in text
    assert all(s["evidence_ids"] or s["metric_ids"] for s in a["statements"] if any(ch.isdigit() for ch in s["text"]))
    for eid in a["statements"][0]["evidence_ids"]:
        assert client.get(f"/api/deals/{demo['id']}/evidence/{eid}").status_code == 200
    r = client.post(f"/api/deals/{demo['id']}/ask", json={"question": "What happens to DSCR if we lose the largest customer?"})
    a = r.json()
    assert a["grounded"] and any("Downside" in s["text"] for s in a["statements"])
    r = client.post(f"/api/deals/{demo['id']}/ask", json={"question": "Tell me about the weather"})
    assert r.status_code == 201 and r.json()["intents"] == ["fallback"]
    hist = client.get(f"/api/deals/{demo['id']}/questions").json()
    assert len(hist) >= 3 and hist[0]["question"].startswith("Tell me")
    assert any(e["event_type"] == "deal.asked" for e in client.get(f"/api/deals/{demo['id']}/audit").json())


def test_chat_streams_grounded_reply_in_mock_mode(client, demo):
    from bearcase.chat.providers import REGISTRY

    r = client.get(f"/api/deals/{demo['id']}/chat/config")
    assert r.status_code == 200 and r.json()["provider"] in {"mock", *REGISTRY}
    with client.stream("POST", f"/api/deals/{demo['id']}/chat", json={"message": "Why was adjusted EBITDA reduced?"}) as resp:
        assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())
    events = [line[7:] for line in body.splitlines() if line.startswith("event: ")]
    assert events[0] == "meta" and "text" in events and "citations" in events and events[-1] == "done"
    import json as _json

    done = _json.loads([line for line in body.splitlines() if line.startswith("data: ")][-1][6:])
    assert done["grounded"] is True and "[E:" in done["content"] and "$1,810,000" in done["content"]
    threads = client.get(f"/api/deals/{demo['id']}/chat/threads").json()
    assert threads and threads[0]["message_count"] == 2
    t = client.get(f"/api/deals/{demo['id']}/chat/threads/{threads[0]['id']}").json()
    assert t["messages"][1]["role"] == "assistant" and t["messages"][1]["citations"]["evidence"]
    # follow-up on the same thread keeps history
    with client.stream(
        "POST",
        f"/api/deals/{demo['id']}/chat",
        json={"message": "And what about DSCR in the downside case?", "thread_id": threads[0]["id"]},
    ) as resp:
        assert resp.status_code == 200
        list(resp.iter_text())
    assert client.get(f"/api/deals/{demo['id']}/chat/threads/{threads[0]['id']}").json()["message_count"] == 4
