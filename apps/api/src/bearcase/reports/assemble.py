"""Assemble a red-team report from persisted rows. Deterministic sections come from the database;
narrative sections come from the provider and are validated before the report is stored."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from bearcase import ENGINE_VERSION
from bearcase.ai.provider import AIProvider
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


def _fmt_money(v: Decimal | str | None) -> str:
    if v is None:
        return "n/a"
    return f"${Decimal(v):,.0f}"


def _fmt_pct(v: Decimal | str | None) -> str:
    return "n/a" if v is None else f"{Decimal(v):.1f}%"


def _fmt_x(v: Decimal | str | None) -> str:
    return "n/a" if v is None else f"{Decimal(v):.2f}x"


def _stmt(text: str, ev: list[Any] | None = None, me: list[Any] | None = None) -> dict[str, Any]:
    return {"text": text, "evidence_ids": [str(e) for e in (ev or [])], "metric_ids": [str(m) for m in (me or [])]}


def _metric_map(db: Session, deal_id: uuid.UUID) -> dict[tuple[str, str | None], FinancialMetric]:
    periods = {p.id: p.label for p in db.scalars(select(FinancialPeriod).where(FinancialPeriod.deal_id == deal_id))}
    out: dict[tuple[str, str | None], FinancialMetric] = {}
    for m in db.scalars(select(FinancialMetric).where(FinancialMetric.deal_id == deal_id)):
        out[(m.key, periods.get(m.period_id) if m.period_id else None)] = m
    return out


def determine_outcome(claims: list[Claim], findings: list[Finding]) -> ReviewOutcome:
    critical = {"revenue_growth", "adjusted_ebitda", "customer_concentration", "recurring_revenue"}
    if any(c.status == ClaimStatus.CONTRADICTED and c.claim_type.value in critical for c in claims):
        return ReviewOutcome.MATERIAL_CONCERNS_IDENTIFIED
    if any(f.kind == FindingKind.MISSING_DOCUMENT for f in findings):
        return ReviewOutcome.ADDITIONAL_DILIGENCE_REQUIRED
    if any(f.kind == FindingKind.UNSUPPORTED_ASSUMPTION for f in findings):
        return ReviewOutcome.ASSUMPTIONS_REQUIRE_REVISION
    return ReviewOutcome.READY_FOR_IC_REVIEW


def build_material(
    db: Session, deal: Deal, claims: list[Claim], findings: list[Finding], metrics: dict, scenario_runs: dict[str, ScenarioResult]
) -> dict[str, Any]:
    contradictions = []
    for c in claims:
        if c.status != ClaimStatus.CONTRADICTED:
            continue
        ev_ids = [str(link.evidence_id) for link in c.links if link.role == LinkRole.CONTRADICTING]
        contradictions.append(
            {
                "source": f"{c.document.doc_type.value.replace('_', ' ')} ({c.document.display_name})",
                "claimed": c.claim_text.rstrip("."),
                "verified": _verified_phrase(c),
                "evidence_source": "primary evidence",
                "evidence_ids": ev_ids,
                "metric_ids": [str(c.verified_metric_id)] if c.verified_metric_id else [],
            }
        )
    material: dict[str, Any] = {
        "company": deal.company_name,
        "contradictions": contradictions,
        "missing_documents": [{"title": f.title, "reason": f.detail} for f in findings if f.kind == FindingKind.MISSING_DOCUMENT],
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
            "value": _fmt_money(v.value),
            "seller": _fmt_money(s.value),
            "metric_ids": [str(v.id), str(s.id)],
        }
    top = metrics.get(("customer_concentration_top1", None))
    if top:
        material["concentration"] = {
            "customer": top.input_snapshot.get("top_customer_name", "the largest customer"),
            "pct": _fmt_pct(top.value),
            "evidence_ids": [str(e) for e in top.evidence_ids[:3]],
            "metric_ids": [str(top.id)],
        }
    material["scenario_warnings"] = [
        {"message": w["message"], "metric_ids": [str(dscr_m.id)] if dscr_m else []}
        for run in scenario_runs.values()
        for w in run.warnings
    ]
    return material


def _verified_phrase(c: Claim) -> str:
    if c.verified_value is None:
        return "a different value"
    unit = c.verified_unit.value if c.verified_unit else c.claimed_unit.value
    if unit == "usd":
        return _fmt_money(c.verified_value)
    if unit == "pct":
        return _fmt_pct(c.verified_value)
    if unit == "multiple":
        return _fmt_x(c.verified_value)
    return str(c.verified_value)


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
    scenarios = list(db.scalars(select(Scenario).where(Scenario.deal_id == deal.id).order_by(Scenario.sort_order)))
    scenario_runs: dict[str, ScenarioResult] = {}
    for sc in scenarios:
        if sc.results:
            scenario_runs[sc.kind.value] = sc.results[-1]
    evidence_ids = {str(e) for e in db.scalars(select(Evidence.id).where(Evidence.deal_id == deal.id))}
    metric_ids = {str(m.id) for m in metrics.values()}

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
                "statements": statements,
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
                f"The proposed enterprise value is {_fmt_money(deal.purchase_price)} financed with {_fmt_money(deal.debt_amount)} of debt and {_fmt_money(deal.equity_amount)} of equity at {deal.interest_rate_pct:.2f}% over {deal.amortization_years} years.",
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
                {"label": d.display_name, "cells": [d.display_name, d.doc_type.value, d.status.value], "evidence_ids": []}
                for d in documents
            ],
        },
        derived_from=["document register"],
        kind="table",
    )

    fin_rows = []
    for key, label, fmt in [
        ("revenue", "Revenue", _fmt_money),
        ("gross_margin", "Gross margin", _fmt_pct),
        ("ebitda_reported", "Reported EBITDA (reconciled)", _fmt_money),
        ("revenue_growth", "Revenue growth", _fmt_pct),
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
        ("cagr", "Revenue CAGR", _fmt_pct),
        ("ebitda_adjusted_seller", "Seller adjusted EBITDA", _fmt_money),
        ("ebitda_adjusted_verified", "Verified adjusted EBITDA", _fmt_money),
        ("enterprise_value", "Enterprise value", _fmt_money),
        ("ev_to_ebitda_seller", "EV / seller EBITDA", _fmt_x),
        ("ev_to_ebitda_verified", "EV / verified EBITDA", _fmt_x),
        ("debt_to_ebitda_verified", "Debt / verified EBITDA", _fmt_x),
        ("annual_debt_service", "Annual debt service", _fmt_money),
        ("cfads_base", "CFADS (base, year 1)", _fmt_money),
        ("dscr_base", "DSCR (base, year 1)", _fmt_x),
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

    claim_rows = [
        {
            "label": c.claim_text[:80],
            "cells": [c.claim_text, c.status.value, _verified_phrase(c) if c.verified_value is not None else ""],
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
            contradiction_stmts.append(
                _stmt(
                    f"{c.claim_text.rstrip('.')} — the evidence supports {_verified_phrase(c)}. {c.status_rationale or ''}".strip(),
                    ev=ev_ids,
                    me=[c.verified_metric_id] if c.verified_metric_id else [],
                )
            )
    section("contradictions", contradiction_stmts or [_stmt("No contradictions were identified.")])

    unsupported_stmts = [
        _stmt(
            f"{c.claim_text.rstrip('.')} — {c.status_rationale or 'no evidence provided'}.",
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
        conc_stmts.append(
            _stmt(
                f"The largest customer, {top.input_snapshot.get('top_customer_name', 'unknown')}, represents {_fmt_pct(top.value)} of revenue ({_fmt_money(top.input_snapshot.get('top_customer_revenue'))} of {_fmt_money(top.input_snapshot.get('total_revenue'))}).",
                ev=top.evidence_ids[:3],
                me=[top.id],
            )
        )
    if rec:
        conc_stmts.append(
            _stmt(
                f"Contract-supported recurring revenue is {_fmt_pct(rec.value)} of the total.",
                ev=rec.evidence_ids[:3],
                me=[rec.id],
            )
        )
    section("customer_concentration", conc_stmts or [_stmt("No customer-level revenue file was provided.")])

    adj_rows = [
        {
            "label": a.label,
            "cells": [a.label, _fmt_money(a.amount), a.decision.value, a.decision_rationale or ""],
            "evidence_ids": [str(e) for e in a.evidence_ids[:4]],
            "adjustment_id": str(a.id),
            "decision": a.decision.value,
        }
        for a in adjustments
    ]
    rep: FinancialMetric | None = metrics.get(("ebitda_reported", None)) or next(
        (m for (k, _p), m in metrics.items() if k == "ebitda_reported"), None
    )
    adj_stmts = []
    if rep and (v := metrics.get(("ebitda_adjusted_verified", None))):
        accepted = sum((a.amount for a in adjustments if a.decision == AdjustmentDecision.ACCEPTED), Decimal(0))
        adj_stmts.append(
            _stmt(
                f"Reported EBITDA of {_fmt_money(rep.value)} plus {_fmt_money(accepted)} of accepted add-backs gives verified adjusted EBITDA of {_fmt_money(v.value)}.",
                ev=rep.evidence_ids[:2],
                me=[rep.id, v.id],
            )
        )
    section(
        "ebitda_adjustments",
        adj_stmts,
        table={"columns": ["Adjustment", "Amount", "Decision", "Rationale"], "rows": adj_rows},
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
                    sc.name,
                    _fmt_money(y1.get("revenue")),
                    _fmt_money(y1.get("ebitda")),
                    _fmt_money(y1.get("cfads")),
                    _fmt_x(y1.get("dscr")),
                    _fmt_pct(run.outputs.get("cash_on_cash_pct")),
                    _fmt_pct(run.outputs.get("irr_pct")),
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
                "Scenario outputs are computed by the deterministic engine from persisted input snapshots; each row links to its immutable result.",
                me=[dscr_m.id],
            )
        )
    section(
        "scenarios",
        sc_stmts,
        table={"columns": ["Scenario", "Revenue Y1", "EBITDA Y1", "CFADS Y1", "DSCR Y1", "Cash-on-cash", "IRR"], "rows": sc_rows},
        derived_from=["scenario input snapshots"],
        kind="table",
    )

    risk_rows = [
        {
            "label": f.title,
            "cells": [f.title, f.kind.value, f.severity.value, f.detail],
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
        [_stmt(f"{f.title}: {f.detail}") for f in findings if f.kind == FindingKind.MISSING_DOCUMENT]
        or [_stmt("No missing documents were identified.")],
        derived_from=["document register"],
        kind="list",
    )

    dec_rows = [
        {
            "label": d.action.value,
            "cells": [d.user.display_name if d.user else "", d.action.value, (d.resulting_status or ""), d.note or ""],
            "evidence_ids": [],
            "claim_id": str(d.claim_id) if d.claim_id else None,
        }
        for d in decisions
    ]
    section(
        "reviewer_decisions",
        [_stmt("Reviewer decisions are additive; the original AI output is preserved on each claim.")],
        table={"columns": ["Reviewer", "Action", "Resulting status", "Note"], "rows": dec_rows},
        kind="table",
    )

    # Narrative from the provider
    material = build_material(db, deal, claims, findings, metrics, scenario_runs)
    narrative = provider.draft_narrative(material)
    if narrative.ok and narrative.output is not None:
        for ns in narrative.output.sections:
            if ns.key in SECTION_TITLES:
                section(ns.key, [_stmt(s.text, s.evidence_ids, s.metric_ids) for s in ns.statements])
    else:
        section(
            "executive_summary", [_stmt(f"Narrative drafting failed ({narrative.error}); deterministic sections remain valid.")]
        )

    cit_rows = []
    for s in sections:
        for st in s["statements"]:
            for e in st["evidence_ids"]:
                cit_rows.append({"label": e, "cells": [s["key"], "evidence", e], "evidence_ids": [e]})
            for m in st["metric_ids"]:
                cit_rows.append({"label": m, "cells": [s["key"], "calculation", m], "evidence_ids": []})
    section("citations", [], table={"columns": ["Section", "Kind", "Id"], "rows": cit_rows}, kind="table")

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
