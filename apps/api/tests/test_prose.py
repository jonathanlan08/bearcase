"""Prose quality of findings and the assembled report for the Northstar deal.

Readers never see raw ids or Decimal repr; a finding's detail explains what it means and names the
document it was checked against rather than repeating the title; every section opens with a plain
sentence that carries no figures; and material statements stay fully cited."""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from bearcase.engine.metrics import format_money, format_multiple, format_pct, format_plain, format_value
from bearcase.reports.assemble import SECTION_INTROS, SECTION_TITLES

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
# "3.00000000", "22.00772201", "0E-8", "1E+2": what str(Decimal) leaks when a value skips the formatter.
DECIMAL_REPR_RE = re.compile(r"\d\.\d{4,}|\d+E[+-]\d+|\bDecimal\(")
MATERIAL_RE = re.compile(r"\d|\$|%")  # mirrors reports/validate.py
# Baseline recorded in HANDOFF.md; change deliberately, never by accident. 36 while the provider drafted the
# management questions; 43 when that section became the deterministic seller-question list; 41 since repeated
# claim issues merge into one question (reports/assemble.py).
NORTHSTAR_MATERIAL_STATEMENTS = 41


def _report(client, demo) -> dict:
    rep = client.get(f"/api/deals/{demo['id']}/report").json()
    assert rep is not None
    return rep


def _texts(report: dict) -> list[tuple[str, str]]:
    """Every reader-visible string: statements and table cells in every section, citations included."""
    out: list[tuple[str, str]] = []
    for s in report["sections"]:
        for st in s["statements"]:
            out.append((s["key"], st["text"]))
        for row in (s.get("table") or {}).get("rows", []):
            for cell in row["cells"]:
                out.append((s["key"], str(cell)))
    return out


def _section(report: dict, key: str) -> dict:
    return next(s for s in report["sections"] if s["key"] == key)


# ---------- shared formatter -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (Decimal("3.00000000"), "count", "3"),
        (Decimal("0E-8"), "count", "0"),
        (Decimal("10.00000000"), "years", "10 years"),
        (Decimal("1"), "years", "1 year"),
        (Decimal("6.5"), "months", "6.5 months"),
        (Decimal("1810000.00000000"), "usd", "$1,810,000"),
        (Decimal("-3366.4"), "usd", "-$3,366"),
        (Decimal("11.58818520"), "pct", "11.6%"),
        (Decimal("1.3415"), "multiple", "1.34x"),
        ("12950000", "usd", "$12,950,000"),
        (None, "usd", "n/a"),
        (Decimal("22.00772201"), "text", "22.01"),
    ],
)
def test_format_value_never_leaks_decimal_repr(value, unit, expected):
    out = format_value(value, unit)
    assert out == expected
    assert not DECIMAL_REPR_RE.search(out)


def test_format_helpers():
    assert format_money(Decimal("-0.2")) == "$0"
    assert format_pct("68") == "68.0%"
    assert format_multiple(0.24) == "0.24x"
    assert format_plain(Decimal("12345.678")) == "12,345.68"
    assert format_plain(Decimal("2.50")) == "2.5"


# ---------- section intros -------------------------------------------------------------------


def test_every_section_has_a_plain_non_material_intro():
    assert set(SECTION_INTROS) == set(SECTION_TITLES)
    for key, text in SECTION_INTROS.items():
        assert text.endswith("."), key
        assert not MATERIAL_RE.search(text), f"intro for {key} carries a figure and would need a citation"
        assert not UUID_RE.search(text)


def test_report_sections_open_with_their_intro(client, demo):
    rep = _report(client, demo)
    for s in rep["sections"]:
        first = s["statements"][0]
        assert first.get("role") == "intro" and first["text"] == SECTION_INTROS[s["key"]], s["key"]
        assert first["evidence_ids"] == [] and first["metric_ids"] == []


# ---------- report prose ---------------------------------------------------------------------


def test_report_prose_has_no_raw_ids_or_decimal_repr(client, demo):
    rep = _report(client, demo)
    texts = _texts(rep)
    assert len(texts) > 100
    offenders = [(k, t) for k, t in texts if UUID_RE.search(t) or DECIMAL_REPR_RE.search(t)]
    assert offenders == []
    assert all("3.00000000" not in t for _, t in texts)
    summary = " ".join(st["text"] for st in _section(rep, "executive_summary")["statements"])
    assert "3 consecutive periods (FY2022, FY2023, FY2024)" in summary
    assert "“" in summary and "”" in summary, "seller statements are quoted, not spliced mid-sentence"


def test_report_refers_to_objects_by_name(client, demo):
    rep = _report(client, demo)
    commentary = [st["text"] for st in _section(rep, "risk_commentary")["statements"] if st.get("role") != "intro"]
    assert commentary and all(re.match(r"^(Base|Downside|Severe downside) scenario \(run \d+\): ", t) for t in commentary)
    scenario_rows = _section(rep, "scenarios")["table"]["rows"]
    assert [r["cells"][0] for r in scenario_rows] == ["Base (run 1)", "Downside (run 1)", "Severe downside (run 1)"]
    risk_rows = _section(rep, "risk_register")["table"]["rows"]
    covenant = [r for r in risk_rows if r["cells"][1] == "Covenant warning"]
    assert covenant and all("(run 1)" in r["cells"][3] and "northstar-debt-term-sheet.pdf" in r["cells"][3] for r in covenant)
    assert all(r["cells"][2] in {"Critical", "High", "Medium", "Low"} for r in risk_rows)


def test_report_numbers_are_reader_formatted(client, demo):
    rep = _report(client, demo)
    overview = _section(rep, "deal_overview")["statements"][2]["text"]
    assert "$12,600,000" in overview and "8.0% interest" in overview and "over 10 years" in overview
    ledger = {r["cells"][0]: r["cells"][2] for r in _section(rep, "claim_table")["table"]["rows"]}
    assert ledger["Amortization: 10-year amortization with level monthly payments of principal and interest."] == "10 years"
    assert ledger["Temporary labor of $130,000 in FY2024 was a one-time cost associated with an unusually hot summer."] == (
        "3 periods (FY2022, FY2023, FY2024)"
    )
    adj = _section(rep, "ebitda_adjustments")
    assert adj["table"]["columns"] == ["Adjustment", "Decision", "Amount", "Rationale"]
    assert all(
        r["cells"][1] == r["decision"] and r["cells"][2].startswith("$") and "," in r["cells"][2] for r in adj["table"]["rows"]
    )
    bridge = adj["statements"][1]["text"]
    assert bridge.startswith("Reported EBITDA for FY2024 of $1,640,000 plus $170,000"), (
        "the bridge must start from the latest period"
    )


def test_citation_appendix_names_sources_without_raw_ids(client, demo):
    rep = _report(client, demo)
    cit = _section(rep, "citations")["table"]
    assert cit["columns"] == ["Section", "Kind", "Source", "Id"]
    assert cit["rows"]
    for r in cit["rows"]:
        assert r["cells"][0] in SECTION_TITLES.values()
        assert r["cells"][1] in ("Evidence", "Calculation")
        assert re.fullmatch(r"[EM]:[0-9a-f]{8}", r["cells"][3])
        if r["cells"][1] == "Evidence":
            assert r["evidence_ids"] and r["cells"][2].startswith("northstar-")
        else:
            assert r["metric_ids"] and "Unresolved" not in r["cells"][2]


def test_material_statement_count_and_citation_validity_unchanged(client, demo):
    rep = _report(client, demo)
    v = rep["validation"]
    assert rep["status"] == "validated" and v["valid"] is True
    assert v["uncited"] == [] and v["unresolved"] == []
    assert v["material_statements"] == v["material_cited"] == NORTHSTAR_MATERIAL_STATEMENTS
    recount = sum(1 for s in rep["sections"] for st in s["statements"] if MATERIAL_RE.search(st["text"]))
    assert recount == v["material_statements"]


def test_export_renders_intros_as_paragraphs(client, demo):
    rep = _report(client, demo)
    md = client.get(f"/api/deals/{demo['id']}/reports/{rep['id']}/export?format=md").text
    intro = SECTION_INTROS["contradictions"]
    assert f"\n{intro}\n" in md and f"- {intro}" not in md
    assert not UUID_RE.search(md.split("## Citations")[0])


# ---------- findings and rationales ---------------------------------------------------------


def test_findings_explain_rather_than_repeat(client, demo):
    findings = client.get(f"/api/deals/{demo['id']}/findings").json()
    docs = {d["display_name"] for d in client.get(f"/api/deals/{demo['id']}/documents").json()}
    assert findings and docs
    for f in findings:
        text = f"{f['title']} {f['detail']}"
        assert not UUID_RE.search(text) and not DECIMAL_REPR_RE.search(text), f["key"]
        assert f["detail"] != f["title"] and not f["detail"].startswith(f["title"]), f["key"]
        assert len(f["title"]) <= 255 and f["detail"].rstrip().endswith((".", "”")), f["key"]
        if f["kind"] != "missing_document":
            assert any(name in f["detail"] for name in docs), f"{f['key']} does not name its evidence document"
    titles = [f["title"] for f in findings]
    assert len(titles) == len(set(titles)), "two findings must not read identically"
    by_key = {f["key"]: f for f in findings}
    assert by_key["covenant:downside"]["title"] == "Downside scenario breaks the debt coverage covenant (1.00x against 1.25x)"
    assert by_key["contradiction:temp_labor_one_time_36"]["title"] == (
        "Temporary labor recurs across 3 consecutive periods; it is not a one-time cost"
    )
    assert (
        "in the CIM" in by_key["contradiction:cim_revenue_growth_18pct"]["title"]
        if "contradiction:cim_revenue_growth_18pct" in by_key
        else True
    )
    concentration = by_key["concentration:top1"]
    assert concentration["title"].startswith("Apex Logistics Park is 22.0% of revenue")
    assert "northstar-customer-revenue.csv" in concentration["detail"]


def test_claim_rationales_are_plain_language(client, demo):
    claims = client.get(f"/api/deals/{demo['id']}/claims").json()
    assert claims
    for c in claims:
        r = c["status_rationale"] or ""
        assert not UUID_RE.search(r) and not DECIMAL_REPR_RE.search(r), c["claim_text"]
        for jargon in ("vs tolerance", "absolute difference", "relative difference", "computed from primary sources"):
            assert jargon not in r, c["claim_text"]
    by_text = {c["claim_text"]: c["status_rationale"] for c in claims}
    growth = by_text[
        "Revenue has grown at approximately 18% annually since FY2022, driven by new maintenance agreements and price increases."
    ]
    assert growth == (
        "Revenue CAGR calculated from northstar-financial-statements.xlsx is 11.6% against the 18.0% claimed; "
        "the gap is 6.4 percentage points, beyond the 1.0 percentage points allowed for rounding."
    )
    ceiling = by_text["The base is diversified across end markets, and no single customer represents more than 10% of revenue."]
    assert ceiling.endswith("the claim allows at most 10.0% and the verified figure of 22.0% is above that ceiling.")
