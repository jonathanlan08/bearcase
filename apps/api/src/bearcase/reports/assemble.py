"""Assemble a red-team report from persisted rows. Deterministic sections come from the database;
narrative sections come from the provider and are validated before the report is stored.

Prose rules (tested in tests/test_prose.py): no raw ids in any statement or cell (objects are named,
ids live in evidence_ids/metric_ids), every number is formatted for a reader, and each section opens
with a plain-language sentence that carries no figures, so intros never become material statements."""

from __future__ import annotations

import re
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from bearcase import ENGINE_VERSION
from bearcase.ai.provider import AIProvider
from bearcase.engine.metrics import format_money, format_multiple, format_pct, format_plain, format_value
from bearcase.models import (
    Adjustment,
    Claim,
    Deal,
    Document,
    Evidence,
    FinancialMetric,
    FinancialPeriod,
    Finding,
    Report,
    ReportCitation,
    ReviewDecision,
    Scenario,
    ScenarioResult,
)
from bearcase.models.enums import (
    AdjustmentDecision,
    CitationKind,
    ClaimStatus,
    FindingKind,
    LinkRole,
    ReportStatus,
    ReviewOutcome,
)
from bearcase.reports.validate import validate_sections
from bearcase.schemas.ai_v1 import SCHEMA_VERSION

SECTION_TITLES = {
    "deal_overview": "Deal overview",
    "executive_summary": "Executive summary",
    "documents_reviewed": "Documents reviewed",
    "verified_financials": "Verified financials",
    "claim_table": "Claim ledger",
    "contradictions": "Contradictions",
    "unsupported_assumptions": "Unsupported assumptions",
    "customer_concentration": "Customer concentration",
    "ebitda_adjustments": "EBITDA adjustments",
    "scenarios": "Scenarios",
    "risk_register": "Risk register",
    "risk_commentary": "Risk commentary",
    "missing_information": "Missing information",
    "management_questions": "Management questions",
    "negotiation_conditions": "Negotiation conditions",
    "reviewer_decisions": "Reviewer decisions",
    "citations": "Citations",
}
SECTION_ORDER = list(SECTION_TITLES)

# One plain sentence a first-time buyer understands before the expert term. These carry no digit,
# "$" or "%" on purpose: the citation validator treats any figure as material.
SECTION_INTROS = {
    "deal_overview": "What is being bought and how the purchase is paid for.",
    "executive_summary": "What stood out when the seller's statements were checked against the primary documents.",
    "documents_reviewed": "The files in the deal room and whether each one was read successfully.",
    "verified_financials": (
        "Figures recalculated from the financial statements and other primary documents, not copied from the seller's "
        "summary. EBITDA is earnings before interest, taxes, depreciation and amortization, a rough measure of the cash "
        "the business generates."
    ),
    "claim_table": (
        "Every statement the seller made that could be tested, with what the evidence showed. Supported means the "
        "documents agree; contradicted means they disagree; unsupported means nothing in the deal room backs it up; "
        "review required means a person needs to decide."
    ),
    "contradictions": (
        "Seller statements that the primary documents do not bear out. Each one is a question to put to the seller "
        "before the price is agreed."
    ),
    "unsupported_assumptions": (
        "Statements with nothing in the deal room to back them up. That does not prove them wrong, but they should "
        "carry no weight in the price until the seller supports them."
    ),
    "customer_concentration": "How much revenue depends on a single customer, and how much is locked in by contract.",
    "ebitda_adjustments": (
        "The seller's adjusted EBITDA adds back costs described as one-off or personal to the owner. Each add-back was "
        "tested against the statement lines; only accepted add-backs count toward the verified figure."
    ),
    "scenarios": (
        "Cash flow projected under different assumptions. DSCR, the debt service coverage ratio, is the cash available "
        "for loan payments divided by the payments due; below the lender's minimum the loan is in breach."
    ),
    "risk_register": "Everything that could hurt the buyer, ranked by severity and linked to the evidence behind it.",
    "risk_commentary": "Warnings raised by the scenario engine, each tied to the scenario and run that produced it.",
    "missing_information": (
        "Documents a buyer would normally expect that were not in the deal room. Ask for them before relying on the "
        "numbers they would confirm."
    ),
    "management_questions": "Questions to put to the seller, each tied to a contradiction or gap above.",
    "negotiation_conditions": "Terms worth asking for, given what the evidence showed.",
    "reviewer_decisions": (
        "Decisions recorded by human reviewers. They sit alongside the original AI assessment, which is never overwritten."
    ),
    "citations": "Every piece of evidence and every calculation this report relies on, listed by section.",
}

DOC_TYPE_LABELS = {
    "cim": "CIM",
    "financial_statements": "financial statements",
    "acquisition_model": "acquisition model",
    "customer_revenue": "customer revenue file",
    "debt_term_sheet": "debt term sheet",
    "customer_contract": "customer contract",
}
FINDING_KIND_LABELS = {
    FindingKind.CONTRADICTION: "Contradiction",
    FindingKind.UNSUPPORTED_ASSUMPTION: "Unsupported assumption",
    FindingKind.MISSING_DOCUMENT: "Missing document",
    FindingKind.COVENANT_WARNING: "Covenant warning",
    FindingKind.DOCUMENT_INTEGRITY: "Document integrity",
    FindingKind.CONCENTRATION: "Customer concentration",
    FindingKind.RISK: "Contract risk",
}


def _stmt(text: str, ev: list[Any] | None = None, me: list[Any] | None = None, role: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "text": text,
        "evidence_ids": [str(e) for e in (ev or [])],
        "metric_ids": [str(m) for m in (me or [])],
    }
    if role:
        out["role"] = role
    return out


def _intro(key: str) -> dict[str, Any]:
    return _stmt(SECTION_INTROS[key], role="intro")


def _humanize(value: str | None) -> str:
    """'review_required' reads as 'Review required'; an acronym such as CIM keeps its case."""
    text = (value or "").replace("_", " ").strip()
    return text if text.isupper() else text[:1].upper() + text[1:]


def _lower_first(text: str) -> str:
    """Lower the first letter unless the word is an acronym (EBITDA, EV, CIM)."""
    return text if not text or text[:2] == text[:2].upper() else text[0].lower() + text[1:]


def _gist(text: str, limit: int = 220) -> str:
    """A model row 'label | value' reads as 'label of value'; trailing period goes; long text is cut at a word."""
    t = re.sub(r"\s+", " ", text).strip()
    t = re.sub(r"\s*\|\s*", " of ", t, count=1) if t.count("|") == 1 else t.replace(" | ", ", ")
    t = t.rstrip(".")
    if len(t) <= limit:
        return t
    return t[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _quote(text: str) -> str:
    return f"“{_gist(text)}”"


def _doc_label(doc: Document | None) -> str:
    """'CIM (northstar-cim.pdf)': the kind of document a reader recognises, then the file name."""
    if doc is None:
        return "seller document"
    kind = DOC_TYPE_LABELS.get(doc.doc_type.value, doc.doc_type.value.replace("_", " "))
    return f"{kind} ({doc.display_name})"


def _sentence(text: str | None, fallback: str) -> str:
    t = (text or "").strip() or fallback
    return t.rstrip(".") + "."


def _evidence_index(db: Session, deal_id: uuid.UUID) -> dict[str, Evidence]:
    rows = db.scalars(select(Evidence).where(Evidence.deal_id == deal_id).options(joinedload(Evidence.document)))
    return {str(e.id): e for e in rows}


def _doc_names(evidence_ids: list[Any], index: dict[str, Evidence], limit: int = 2) -> str:
    names: list[str] = []
    for eid in evidence_ids:
        e = index.get(str(eid))
        if e is not None and e.document is not None and e.document.display_name not in names:
            names.append(e.document.display_name)
        if len(names) == limit:
            break
    return " and ".join(names)


def _evidence_source(e: Evidence) -> str:
    """'northstar-cim.pdf, page 3, paragraph 2' or 'statements.xlsx, sheet Income Statement, row 12'."""
    loc = e.locator or {}
    parts: list[str] = []
    if loc.get("sheet"):
        parts.append(f"sheet {loc['sheet']}")
    if loc.get("page"):
        parts.append(f"page {loc['page']}")
    if loc.get("paragraph"):
        parts.append(f"paragraph {loc['paragraph']}")
    if loc.get("row") is not None:
        parts.append(f"row {loc['row']}")
    name = e.document.display_name if e.document is not None else "document"
    return ", ".join([name, *parts])


def _metric_map(db: Session, deal_id: uuid.UUID) -> dict[tuple[str, str | None], FinancialMetric]:
    periods = {p.id: p.label for p in db.scalars(select(FinancialPeriod).where(FinancialPeriod.deal_id == deal_id))}
    out: dict[tuple[str, str | None], FinancialMetric] = {}
    for m in db.scalars(select(FinancialMetric).where(FinancialMetric.deal_id == deal_id)):
        out[(m.key, periods.get(m.period_id) if m.period_id else None)] = m
    return out


def _latest_period_label(db: Session, deal_id: uuid.UUID) -> str | None:
    return db.scalar(
        select(FinancialPeriod.label).where(FinancialPeriod.deal_id == deal_id).order_by(FinancialPeriod.ordinal.desc()).limit(1)
    )


def _scenario_name(kind: str, run: ScenarioResult) -> str:
    return run.scenario.name if run.scenario is not None else kind.replace("_", " ").capitalize()


def determine_outcome(claims: list[Claim], findings: list[Finding]) -> ReviewOutcome:
    critical = {"revenue_growth", "adjusted_ebitda", "customer_concentration", "recurring_revenue"}
    if any(c.status == ClaimStatus.CONTRADICTED and c.claim_type.value in critical for c in claims):
        return ReviewOutcome.MATERIAL_CONCERNS_IDENTIFIED
    if any(f.kind == FindingKind.MISSING_DOCUMENT for f in findings):
        return ReviewOutcome.ADDITIONAL_DILIGENCE_REQUIRED
    if any(f.kind == FindingKind.UNSUPPORTED_ASSUMPTION for f in findings):
        return ReviewOutcome.ASSUMPTIONS_REQUIRE_REVISION
    return ReviewOutcome.READY_FOR_IC_REVIEW


def _verified_phrase(c: Claim, metric: FinancialMetric | None) -> str:
    """What the evidence shows, as a phrase that completes 'the evidence supports …'.

    Root cause of the old '3.00000000': a count-type verification (the expense recurs in N periods) was
    printed with str(Decimal). Counts are now spelled out, and every other unit goes through the shared
    formatter, with the metric's label in front so the number has a subject."""
    if c.status_rule == "expense_recurs_across_periods" and c.verified_value is not None:
        periods = list((metric.input_snapshot.get("periods") if metric is not None else None) or [])
        n = format_plain(c.verified_value)
        return f"the same expense in {n} consecutive periods" + (f" ({', '.join(periods)})" if periods else "")
    if c.verified_value is None:
        return "a different value"
    value = format_value(c.verified_value, (c.verified_unit or c.claimed_unit).value)
    if metric is not None and metric.label:
        label = _lower_first(metric.label)
        return f"{label} {'at' if ' of ' in label else 'of'} {value}"
    return value


def _verified_cell(c: Claim, metric: FinancialMetric | None) -> str:
    """Short form for the claim ledger: '$1,810,000', '10 years', '3 periods (FY2022, FY2023, FY2024)'."""
    if c.verified_value is None:
        return ""
    if c.status_rule == "expense_recurs_across_periods":
        periods = list((metric.input_snapshot.get("periods") if metric is not None else None) or [])
        return f"{format_plain(c.verified_value)} periods" + (f" ({', '.join(periods)})" if periods else "")
    return format_value(c.verified_value, (c.verified_unit or c.claimed_unit).value)


def build_material(
    db: Session,
    deal: Deal,
    claims: list[Claim],
    findings: list[Finding],
    metrics: dict,
    scenario_runs: dict[str, ScenarioResult],
    evidence_index: dict[str, Evidence] | None = None,
) -> dict[str, Any]:
    """Facts handed to the provider for narrative drafting. Every string here is reader-ready: the
    provider must never see a raw id or Decimal repr it could echo into prose."""
    index = evidence_index if evidence_index is not None else _evidence_index(db, deal.id)
    metric_by_id = {m.id: m for m in metrics.values()}
    contradictions = []
    for c in claims:
        if c.status != ClaimStatus.CONTRADICTED:
            continue
        ev_ids = [str(link.evidence_id) for link in c.links if link.role == LinkRole.CONTRADICTING]
        metric = metric_by_id.get(c.verified_metric_id) if c.verified_metric_id else None
        docs = _doc_names(ev_ids, index)
        contradictions.append(
            {
                "source": _doc_label(c.document),
                "claimed": _quote(c.claim_text),
                "verified": _verified_phrase(c, metric),
                "evidence_source": f"evidence in {docs}" if docs else "primary evidence",
                "evidence_ids": ev_ids,
                "metric_ids": [str(c.verified_metric_id)] if c.verified_metric_id else [],
            }
        )
    material: dict[str, Any] = {
        "company": deal.company_name,
        "contradictions": contradictions,
        "missing_documents": [
            {"title": f.title.removeprefix("Missing: "), "reason": f.detail}
            for f in findings
            if f.kind == FindingKind.MISSING_DOCUMENT
        ],
    }
    base, down = scenario_runs.get("base"), scenario_runs.get("downside")
    dscr_m = metrics.get(("dscr_base", None))
    if base and down and base.outputs.get("dscr") and down.outputs.get("dscr"):
        material["dscr"] = {
            "base": f"{Decimal(base.outputs['dscr']):.2f}",
            "downside": f"{Decimal(down.outputs['dscr']):.2f}",
            "threshold": f"{deal.covenant_dscr_threshold:.2f}" if deal.covenant_dscr_threshold else "n/a",
            "metric_ids": [str(dscr_m.id)] if dscr_m else [],
        }
    v = metrics.get(("ebitda_adjusted_verified", None))
    s = metrics.get(("ebitda_adjusted_seller", None))
    if v and s:
        material["verified_ebitda"] = {
            "value": format_money(v.value),
            "seller": format_money(s.value),
            "metric_ids": [str(v.id), str(s.id)],
        }
    top = metrics.get(("customer_concentration_top1", None))
    if top:
        material["concentration"] = {
            "customer": top.input_snapshot.get("top_customer_name", "the largest customer"),
            "pct": format_pct(top.value),
            "evidence_ids": [str(e) for e in top.evidence_ids[:3]],
            "metric_ids": [str(top.id)],
        }
    material["scenario_warnings"] = [
        {
            "message": f"{_scenario_name(kind, run)} scenario (run {run.run_no}): {w['message']}",
            "metric_ids": [str(dscr_m.id)] if dscr_m else [],
        }
        for kind, run in scenario_runs.items()
        for w in run.warnings
    ]
    return material


def assemble_report(db: Session, deal: Deal, provider: AIProvider, user_id: uuid.UUID | None) -> Report:
    claims = list(db.scalars(select(Claim).where(Claim.deal_id == deal.id).order_by(Claim.created_at)))
    findings = list(db.scalars(select(Finding).where(Finding.deal_id == deal.id).order_by(Finding.severity, Finding.created_at)))
    documents = list(db.scalars(select(Document).where(Document.deal_id == deal.id).order_by(Document.created_at)))
    adjustments = list(db.scalars(select(Adjustment).where(Adjustment.deal_id == deal.id).order_by(Adjustment.sort_order)))
    decisions = list(
        db.scalars(
            select(ReviewDecision)
            .where(ReviewDecision.deal_id == deal.id, ReviewDecision.is_current.is_(True))
            .order_by(ReviewDecision.created_at)
        )
    )
    metrics = _metric_map(db, deal.id)
    metric_by_id = {str(m.id): m for m in metrics.values()}
    latest_label = _latest_period_label(db, deal.id)
    scenarios = list(db.scalars(select(Scenario).where(Scenario.deal_id == deal.id).order_by(Scenario.sort_order)))
    scenario_runs: dict[str, ScenarioResult] = {}
    for sc in scenarios:
        if sc.results:
            scenario_runs[sc.kind.value] = sc.results[-1]
    ev_index = _evidence_index(db, deal.id)
    evidence_ids = set(ev_index)
    metric_ids = set(metric_by_id)

    sections: list[dict[str, Any]] = []

    def section(
        key: str,
        statements: list[dict[str, Any]],
        table: dict[str, Any] | None = None,
        derived_from: list[str] | None = None,
        kind: str = "narrative",
    ) -> None:
        sections.append(
            {
                "key": key,
                "title": SECTION_TITLES[key],
                "kind": kind,
                "statements": [_intro(key), *statements],
                "table": table or {},
                "derived_from": derived_from or [],
            }
        )

    ev_m = metrics.get(("enterprise_value", None))
    section(
        "deal_overview",
        [
            _stmt(f"{deal.company_name} operates in {deal.industry}."),
            _stmt(
                f"The proposed price is {format_money(deal.purchase_price)}, paid with {format_money(deal.debt_amount)} of "
                f"borrowed money (debt) and {format_money(deal.equity_amount)} from the buyer (equity). The loan carries "
                f"{format_pct(deal.interest_rate_pct)} interest and is repaid over {format_value(deal.amortization_years, 'years')}.",
                me=[ev_m.id] if ev_m else [],
            ),
        ],
        derived_from=["deal terms entered by the analyst"] if not ev_m else [],
    )

    section(
        "documents_reviewed",
        [_stmt(f"{len(documents)} documents were reviewed.", me=[])],
        table={
            "columns": ["Document", "Type", "Status"],
            "rows": [
                {
                    "label": d.display_name,
                    "cells": [
                        d.display_name,
                        _humanize(DOC_TYPE_LABELS.get(d.doc_type.value, d.doc_type.value)),
                        _humanize(d.status.value),
                    ],
                    "evidence_ids": [],
                }
                for d in documents
            ],
        },
        derived_from=["document register"],
        kind="table",
    )

    fin_rows = []
    for key, label, fmt in [
        ("revenue", "Revenue", format_money),
        ("gross_margin", "Gross margin", format_pct),
        ("ebitda_reported", "Reported EBITDA (reconciled)", format_money),
        ("revenue_growth", "Revenue growth", format_pct),
    ]:
        for (k, p), m in sorted(metrics.items(), key=lambda kv: kv[0][1] or ""):
            if k == key and p:
                fin_rows.append(
                    {
                        "label": f"{label} {p}",
                        "cells": [f"{label} {p}", fmt(m.value)],
                        "evidence_ids": [str(e) for e in m.evidence_ids[:4]],
                        "metric_ids": [str(m.id)],
                    }
                )
    for key, label, fmt in [
        ("cagr", "Revenue CAGR (average yearly growth)", format_pct),
        ("ebitda_adjusted_seller", "Seller adjusted EBITDA", format_money),
        ("ebitda_adjusted_verified", "Verified adjusted EBITDA", format_money),
        ("enterprise_value", "Enterprise value (proposed price)", format_money),
        ("ev_to_ebitda_seller", "Price / seller EBITDA", format_multiple),
        ("ev_to_ebitda_verified", "Price / verified EBITDA", format_multiple),
        ("debt_to_ebitda_verified", "Debt / verified EBITDA (leverage)", format_multiple),
        ("annual_debt_service", "Annual debt service (loan payments per year)", format_money),
        ("cfads_base", "Cash available for debt service (CFADS, base case, year 1)", format_money),
        ("dscr_base", "Debt service coverage (DSCR, base case, year 1)", format_multiple),
    ]:
        dm = next((mm for (k, _p), mm in metrics.items() if k == key), None)
        if dm:
            fin_rows.append(
                {
                    "label": label,
                    "cells": [label, fmt(dm.value)],
                    "evidence_ids": [str(e) for e in dm.evidence_ids[:4]],
                    "metric_ids": [str(dm.id)],
                }
            )
    section("verified_financials", [], table={"columns": ["Metric", "Value"], "rows": fin_rows}, kind="table")

    def metric_of(c: Claim) -> FinancialMetric | None:
        return metric_by_id.get(str(c.verified_metric_id)) if c.verified_metric_id else None

    claim_rows = [
        {
            "label": c.claim_text[:80],
            "cells": [c.claim_text, c.status.value, _verified_cell(c, metric_of(c))],
            "evidence_ids": [str(c.source_evidence_id)] if c.source_evidence_id else [],
            "metric_ids": [str(c.verified_metric_id)] if c.verified_metric_id else [],
            "claim_id": str(c.id),
            "status": c.status.value,
        }
        for c in claims
    ]
    section("claim_table", [], table={"columns": ["Claim", "Status", "Verified"], "rows": claim_rows}, kind="table")

    contradiction_stmts = []
    for c in claims:
        if c.status == ClaimStatus.CONTRADICTED:
            ev_ids = [link.evidence_id for link in c.links if link.role == LinkRole.CONTRADICTING][:4]
            rationale = _sentence(c.status_rationale, f"The evidence supports {_verified_phrase(c, metric_of(c))}")
            contradiction_stmts.append(
                _stmt(
                    f"The {_doc_label(c.document)} states {_quote(c.claim_text)}. {rationale}",
                    ev=ev_ids,
                    me=[c.verified_metric_id] if c.verified_metric_id else [],
                )
            )
    section("contradictions", contradiction_stmts or [_stmt("No contradictions were identified.")])

    unsupported_stmts = [
        _stmt(
            f"The {_doc_label(c.document)} states {_quote(c.claim_text)}. "
            f"{_sentence(c.status_rationale, 'No document in the deal room provides evidence for it')}",
            ev=[c.source_evidence_id] if c.source_evidence_id else [],
            me=[c.verified_metric_id] if c.verified_metric_id else [],
        )
        for c in claims
        if c.status == ClaimStatus.UNSUPPORTED
    ]
    section("unsupported_assumptions", unsupported_stmts or [_stmt("No unsupported assumptions were identified.")])

    top = metrics.get(("customer_concentration_top1", None))
    rec = metrics.get(("recurring_revenue_pct", None))
    conc_stmts = []
    if top:
        snap = top.input_snapshot
        conc_stmts.append(
            _stmt(
                f"The largest customer, {snap.get('top_customer_name', 'unknown')}, brings in {format_pct(top.value)} of revenue "
                f"({format_money(snap.get('top_customer_revenue'))} of {format_money(snap.get('total_revenue'))}).",
                ev=top.evidence_ids[:3],
                me=[top.id],
            )
        )
    if rec:
        conc_stmts.append(
            _stmt(
                f"Revenue backed by a signed contract is {format_pct(rec.value)} of the total; the rest must be re-won each year.",
                ev=rec.evidence_ids[:3],
                me=[rec.id],
            )
        )
    section("customer_concentration", conc_stmts or [_stmt("No customer-level revenue file was provided.")])

    adj_rows = [
        {
            "label": a.label,
            "cells": [a.label, a.decision.value, format_money(a.amount), a.decision_rationale or ""],
            "evidence_ids": [str(e) for e in a.evidence_ids[:4]],
            "adjustment_id": str(a.id),
            "decision": a.decision.value,
        }
        for a in adjustments
    ]
    # Reported EBITDA for the latest period: the verified figure is built on it, so the sentence must not
    # pick an earlier year by accident.
    rep: FinancialMetric | None = (
        (metrics.get(("ebitda_reported", latest_label)) if latest_label else None)
        or metrics.get(("ebitda_reported", None))
        or next((m for (k, _p), m in metrics.items() if k == "ebitda_reported"), None)
    )
    adj_stmts = []
    if rep and (v := metrics.get(("ebitda_adjusted_verified", None))):
        accepted = sum((a.amount for a in adjustments if a.decision == AdjustmentDecision.ACCEPTED), Decimal(0))
        period = f" for {latest_label}" if latest_label and metrics.get(("ebitda_reported", latest_label)) is rep else ""
        adj_stmts.append(
            _stmt(
                f"Reported EBITDA{period} of {format_money(rep.value)} plus {format_money(accepted)} of accepted add-backs "
                f"gives verified adjusted EBITDA of {format_money(v.value)}.",
                ev=rep.evidence_ids[:2],
                me=[rep.id, v.id],
            )
        )
    section(
        "ebitda_adjustments",
        adj_stmts,
        table={"columns": ["Adjustment", "Decision", "Amount", "Rationale"], "rows": adj_rows},
        kind="table",
    )

    sc_rows = []
    sc_stmts = []
    for sc in scenarios:
        run = scenario_runs.get(sc.kind.value)
        if not run:
            continue
        y1 = run.outputs.get("year1", {})
        sc_rows.append(
            {
                "label": sc.name,
                "cells": [
                    f"{sc.name} (run {run.run_no})",
                    format_money(y1.get("revenue")),
                    format_money(y1.get("ebitda")),
                    format_money(y1.get("cfads")),
                    format_multiple(y1.get("dscr")),
                    format_pct(run.outputs.get("cash_on_cash_pct")),
                    format_pct(run.outputs.get("irr_pct")),
                ],
                "evidence_ids": [],
                "scenario_id": str(sc.id),
                "result_id": str(run.id),
                "warnings": [w["code"] for w in run.warnings],
            }
        )
    dscr_m = metrics.get(("dscr_base", None))
    if dscr_m and scenario_runs:
        sc_stmts.append(
            _stmt(
                "Each scenario recomputes revenue, EBITDA, cash available for debt service and coverage from a saved set of "
                "inputs. The figures come from the calculation engine, not from a language model, and every run is kept so "
                "it can be reopened and compared.",
                me=[dscr_m.id],
            )
        )
    section(
        "scenarios",
        sc_stmts,
        table={
            "columns": [
                "Scenario",
                "Revenue (year 1)",
                "EBITDA (year 1)",
                "Cash for debt service (year 1)",
                "Debt coverage (year 1)",
                "Cash-on-cash return",
                "Equity IRR",
            ],
            "rows": sc_rows,
        },
        derived_from=["scenario input snapshots"],
        kind="table",
    )

    risk_rows = [
        {
            "label": f.title,
            "cells": [f.title, FINDING_KIND_LABELS.get(f.kind, _humanize(f.kind.value)), _humanize(f.severity.value), f.detail],
            "evidence_ids": [str(e) for e in f.evidence_ids[:4]],
            "finding_id": str(f.id),
            "severity": f.severity.value,
        }
        for f in findings
        if f.kind not in (FindingKind.MISSING_DOCUMENT,)
    ]
    section("risk_register", [], table={"columns": ["Risk", "Kind", "Severity", "Detail"], "rows": risk_rows}, kind="table")

    section(
        "missing_information",
        [_stmt(f"{f.title.removeprefix('Missing: ')}: {f.detail}") for f in findings if f.kind == FindingKind.MISSING_DOCUMENT]
        or [_stmt("No missing documents were identified.")],
        derived_from=["document register"],
        kind="list",
    )

    dec_rows = [
        {
            "label": d.action.value,
            "cells": [
                d.user.display_name if d.user else "",
                _humanize(d.action.value),
                _humanize(d.resulting_status),
                d.note or "",
            ],
            "evidence_ids": [],
            "claim_id": str(d.claim_id) if d.claim_id else None,
        }
        for d in decisions
    ]
    section(
        "reviewer_decisions",
        [],
        table={"columns": ["Reviewer", "Action", "Resulting status", "Note"], "rows": dec_rows},
        kind="table",
    )

    # Narrative from the provider
    material = build_material(db, deal, claims, findings, metrics, scenario_runs, ev_index)
    narrative = provider.draft_narrative(material)
    if narrative.ok and narrative.output is not None:
        for ns in narrative.output.sections:
            if ns.key in SECTION_TITLES:
                section(ns.key, [_stmt(s.text, s.evidence_ids, s.metric_ids) for s in ns.statements])
    else:
        section(
            "executive_summary", [_stmt(f"Narrative drafting failed ({narrative.error}); deterministic sections remain valid.")]
        )

    # Citation appendix: a reader-usable source per cited id (document and location, or calculation name).
    # The full ids stay on the row for the chips; the visible cell carries the short form used in exports.
    cit_rows = []
    seen: set[tuple[str, str]] = set()
    for s in sections:
        for st in s["statements"]:
            for e in st["evidence_ids"]:
                if (s["key"], e) in seen:
                    continue
                seen.add((s["key"], e))
                row = ev_index.get(e)
                cit_rows.append(
                    {
                        "label": f"E:{e[:8]}",
                        "cells": [s["title"], "Evidence", _evidence_source(row) if row else "Unresolved evidence", f"E:{e[:8]}"],
                        "evidence_ids": [e],
                    }
                )
            for m in st["metric_ids"]:
                if (s["key"], m) in seen:
                    continue
                seen.add((s["key"], m))
                mm = metric_by_id.get(m)
                cit_rows.append(
                    {
                        "label": f"M:{m[:8]}",
                        "cells": [s["title"], "Calculation", mm.label if mm else "Unresolved calculation", f"M:{m[:8]}"],
                        "evidence_ids": [],
                        "metric_ids": [m],
                    }
                )
    section("citations", [], table={"columns": ["Section", "Kind", "Source", "Id"], "rows": cit_rows}, kind="table")

    sections.sort(key=lambda s: SECTION_ORDER.index(s["key"]))
    validation = validate_sections(sections, evidence_ids, metric_ids)
    outcome = determine_outcome(claims, findings)
    version_no = (
        db.scalar(select(Report.version_no).where(Report.deal_id == deal.id).order_by(Report.version_no.desc())) or 0
    ) + 1
    report = Report(
        deal_id=deal.id,
        version_no=version_no,
        status=ReportStatus.VALIDATED if validation["valid"] else ReportStatus.FAILED_VALIDATION,
        outcome=outcome,
        sections=sections,
        validation=validation,
        provider=provider.name,
        model=provider.model,
        prompt_version=narrative.prompt_version or "n/a",
        schema_version=SCHEMA_VERSION,
        engine_version=ENGINE_VERSION,
        input_snapshot={
            "claim_ids": [str(c.id) for c in claims],
            "finding_ids": [str(f.id) for f in findings],
            "scenario_result_ids": [str(r.id) for r in scenario_runs.values()],
            "metric_ids": sorted(metric_ids),
            "narrative_input_hash": narrative.input_hash,
        },
        generated_by_user_id=user_id,
    )
    db.add(report)
    db.flush()
    for s in sections:
        for i, st in enumerate(s["statements"]):
            for e in st["evidence_ids"]:
                db.add(
                    ReportCitation(
                        report_id=report.id,
                        section_key=s["key"],
                        statement_index=i,
                        kind=CitationKind.EVIDENCE,
                        evidence_id=uuid.UUID(e) if e in evidence_ids else None,
                        resolved=e in evidence_ids,
                    )
                )
            for m in st["metric_ids"]:
                db.add(
                    ReportCitation(
                        report_id=report.id,
                        section_key=s["key"],
                        statement_index=i,
                        kind=CitationKind.CALCULATION,
                        metric_id=uuid.UUID(m) if m in metric_ids else None,
                        resolved=m in metric_ids,
                    )
                )
    db.flush()
    return report
