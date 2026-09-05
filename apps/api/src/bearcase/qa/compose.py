"""Rule-based answer composer used by the mock provider. Every sentence with a number cites ids."""

from __future__ import annotations

from typing import Any

from bearcase.schemas.ai_v1 import NarrativeStatement


def _st(text: str, ev: list[str] | None = None, me: list[str] | None = None) -> NarrativeStatement:
    return NarrativeStatement(text=text, evidence_ids=list(dict.fromkeys(ev or [])), metric_ids=list(dict.fromkeys(me or [])))


def compose(material: dict[str, Any]) -> list[NarrativeStatement]:
    f = material["facts"]
    out: list[NarrativeStatement] = []
    if "ebitda" in f:
        e = f["ebitda"]
        rep, sel, ver = e.get("reported"), e.get("seller"), e.get("verified")
        if rep and sel and ver:
            out.append(
                _st(
                    f"Reported EBITDA is {rep['value']}; the seller adds back adjustments to reach {sel['value']}, while the verified figure is {ver['value']}.",
                    rep["evidence_ids"] + sel["evidence_ids"],
                    [rep["metric_id"], sel["metric_id"], ver["metric_id"]],
                )
            )
        for a in e["adjustments"]:
            verb = {
                "accepted": "was accepted",
                "rejected": "was rejected",
                "review_required": "needs human review",
                "unsupported": "is unsupported",
                "pending": "is pending",
            }[a["decision"]]
            who = " by a reviewer" if a["human"] else ""
            out.append(
                _st(
                    f"{a['label']} ({a['amount']}) {verb}{who}: {a['rationale'] or 'no rationale recorded'}",
                    a["evidence_ids"],
                    [ver["metric_id"]] if ver else [],
                )
            )
        if ver and sel and ver.get("raw") and sel.get("raw"):
            out.append(
                _st(
                    "The difference between the seller figure and the verified figure is the sum of the rejected, review-required, and unsupported add-backs, which stay visible but outside the total.",
                    [],
                    [ver["metric_id"], sel["metric_id"]],
                )
            )
    if "valuation" in f:
        v = f["valuation"]
        ev_, s, vv = v.get("enterprise_value"), v.get("ev_to_ebitda_seller"), v.get("ev_to_ebitda_verified")
        if ev_ and s and vv:
            out.append(
                _st(
                    f"Enterprise value is {ev_['value']}, which is {s['value']} the seller's adjusted EBITDA but {vv['value']} the verified figure.",
                    ev_["evidence_ids"],
                    [ev_["metric_id"], s["metric_id"], vv["metric_id"]],
                )
            )
        if v.get("debt_to_ebitda_verified") and v.get("annual_debt_service"):
            d, ads = v["debt_to_ebitda_verified"], v["annual_debt_service"]
            out.append(
                _st(
                    f"Funded debt is {d['value']} verified EBITDA, with annual debt service of {ads['value']}.",
                    d["evidence_ids"],
                    [d["metric_id"], ads["metric_id"]],
                )
            )
    if "growth" in f:
        g = f["growth"]
        if g.get("cagr") and g["revenue_by_period"]:
            series = ", ".join(f"{r['period']} {r['value']}" for r in g["revenue_by_period"])
            out.append(
                _st(
                    f"Revenue by period from the statements: {series}; the compound annual growth rate is {g['cagr']['value']}.",
                    [e for r in g["revenue_by_period"] for e in r["evidence_ids"]],
                    [g["cagr"]["metric_id"]] + [r["metric_id"] for r in g["revenue_by_period"]],
                )
            )
        for c in g["claims"]:
            out.append(
                _st(
                    f'The {c["source"]} states: "{c["text"]}" This claim is {c["status"].replace("_", " ")}: {c["rationale"] or "see the claim ledger"}',
                    ([c["source_evidence_id"]] if c["source_evidence_id"] else []) + c["contradicting_ids"] + c["supporting_ids"],
                    [c["metric_id"]] if c["metric_id"] else [],
                )
            )
    if "concentration" in f:
        k = f["concentration"]
        if k.get("metric"):
            out.append(
                _st(
                    f"The largest customer, {k['top_customer']}, represents {k['metric']['value']} of revenue according to the customer revenue file.",
                    k["metric"]["evidence_ids"],
                    [k["metric"]["metric_id"]],
                )
            )
        for c in k["claims"]:
            out.append(
                _st(
                    f'The {c["source"]} states: "{c["text"]}" This is {c["status"].replace("_", " ")}: {c["rationale"]}',
                    ([c["source_evidence_id"]] if c["source_evidence_id"] else []) + c["contradicting_ids"],
                    [c["metric_id"]] if c["metric_id"] else [],
                )
            )
        for fi in k["findings"]:
            out.append(_st(f"{fi['title']}: {fi['detail']}", fi["evidence_ids"], fi["metric_ids"]))
    if "recurring" in f:
        r = f["recurring"]
        if r.get("metric"):
            out.append(
                _st(
                    f"Contract-supported recurring revenue is {r['metric']['value']} of the total, counting only rows typed as maintenance agreements.",
                    r["metric"]["evidence_ids"],
                    [r["metric"]["metric_id"]],
                )
            )
        for c in r["claims"]:
            out.append(
                _st(
                    f'The {c["source"]} states: "{c["text"]}" This is {c["status"].replace("_", " ")}.',
                    ([c["source_evidence_id"]] if c["source_evidence_id"] else []) + c["contradicting_ids"],
                    [c["metric_id"]] if c["metric_id"] else [],
                )
            )
    if "covenant" in f:
        c = f["covenant"]
        for run in c["runs"]:
            dscr = run["dscr"]
            out.append(
                _st(
                    f"{run['scenario']} scenario: year-1 DSCR {float(dscr):.2f}x on CFADS of ${float(run['cfads']):,.0f} against a {c['threshold'] or 'n/a'}x covenant (assumptions: {', '.join(f'{k.replace("_pct", "").replace("_", " ")} {v}' for k, v in run['assumptions'].items())}).",
                    [],
                    [c["dscr_base"]["metric_id"]] if c.get("dscr_base") else [],
                )
                if dscr is not None
                else _st(f"{run['scenario']} scenario: DSCR is undefined because debt service is zero.", [], [])
            )
            for w in run["warnings"][:2]:
                out.append(_st(w, [], [c["dscr_base"]["metric_id"]] if c.get("dscr_base") else []))
        if c.get("cfads_base") and c.get("ads"):
            out.append(
                _st(
                    f"DSCR is CFADS divided by annual debt service ({c['ads']['value']}); the CFADS bridge subtracts maintenance capex, cash taxes, and working-capital investment from adjusted EBITDA.",
                    [],
                    [c["cfads_base"]["metric_id"], c["ads"]["metric_id"]],
                )
            )
    if "contract" in f:
        for c in f["contract"]["claims"]:
            out.append(
                _st(
                    f'{c["source"]}: "{c["text"]}" Status {c["status"].replace("_", " ")}: {c["rationale"]}',
                    ([c["source_evidence_id"]] if c["source_evidence_id"] else []) + c["supporting_ids"] + c["contradicting_ids"],
                    [],
                )
            )
        for fi in f["contract"]["findings"]:
            out.append(_st(f"{fi['title']}: {fi['detail']}", fi["evidence_ids"], fi["metric_ids"]))
    if "missing" in f:
        if not f["missing"]:
            out.append(_st("No missing documents are recorded for this deal.", [], []))
        for fi in f["missing"]:
            out.append(_st(f"{fi['title'].replace('Missing: ', '')}: {fi['detail']}", [], []))
    if "risks" in f:
        for fi in f["risks"][:6]:
            out.append(_st(f"[{fi['severity']}] {fi['title']}: {fi['detail']}", fi["evidence_ids"], fi["metric_ids"]))
    if "retrieved" in f:
        if not f["retrieved"]:
            out.append(
                _st(
                    "Nothing in the deal room matches that question. Try asking about EBITDA adjustments, growth, concentration, recurring revenue, DSCR, contracts, missing documents, or risks.",
                    [],
                    [],
                )
            )
        for r in f["retrieved"]:
            if r["kind"] == "claim":
                out.append(
                    _st(
                        f'Claim ({r["status"].replace("_", " ")}): "{r["text"]}" {r["rationale"] or ""}'.strip(),
                        ([r["source_evidence_id"]] if r["source_evidence_id"] else [])
                        + r["supporting_ids"]
                        + r["contradicting_ids"],
                        [r["metric_id"]] if r["metric_id"] else [],
                    )
                )
            elif r["kind"] == "finding":
                out.append(_st(f"Finding ({r['severity']}): {r['title']}. {r['detail']}", r["evidence_ids"], r["metric_ids"]))
            else:
                out.append(_st(f'{r["document"]}: "{r["text"]}"', [r["evidence_id"]], []))
    if not out:
        out.append(
            _st(
                "I could not find persisted evidence that answers this question. Ask about EBITDA adjustments, growth, concentration, recurring revenue, DSCR and scenarios, contracts, missing documents, or risks.",
                [],
                [],
            )
        )
    return out
