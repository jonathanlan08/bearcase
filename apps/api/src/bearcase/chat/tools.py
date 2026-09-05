"""Tools the chat model can call. Each returns compact JSON built only from persisted rows and
carries the ids the model must cite. Nothing here calculates new numbers."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from bearcase.ai.retrieval import LexicalRetriever
from bearcase.models import Adjustment, Claim, Deal, Evidence, FinancialMetric, FinancialPeriod, Finding, Scenario
from bearcase.models.enums import LinkRole

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_claims",
        "description": "List extracted claims with their verification status, claimed and verified values, and the ids of supporting/contradicting evidence. Filter by status (supported, contradicted, unsupported, review_required), claim type, or a text query.",
        "input_schema": {
            "type": "object",
            "properties": {"status": {"type": "string"}, "claim_type": {"type": "string"}, "query": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_claim",
        "description": "Get one claim in full: text, status, rationale, rule, source evidence, and every linked evidence chunk with its text.",
        "input_schema": {
            "type": "object",
            "properties": {"claim_id": {"type": "string"}},
            "required": ["claim_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_financials",
        "description": "Get the mapped income statement by period and every calculated metric (growth, CAGR, margins, reported and adjusted EBITDA, multiples, debt service, CFADS, DSCR, returns) with formulas and metric ids.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_adjustments",
        "description": "Get the seller add-back schedule with the decision on each item (accepted, rejected, review_required, unsupported), the rationale, the rule, and evidence ids.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_scenarios",
        "description": "Get the base, downside, and severe scenarios: assumptions, year-1 outputs (revenue, EBITDA, CFADS, debt service, DSCR), warnings, and the covenant threshold. Results are persisted engine outputs.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_findings",
        "description": "Get findings: contradictions, unsupported assumptions, concentration, contract risks, covenant warnings, document-integrity flags, and missing documents, with severity and evidence ids.",
        "input_schema": {"type": "object", "properties": {"kind": {"type": "string"}}, "additionalProperties": False},
    },
    {
        "name": "search_evidence",
        "description": "Full-text search over every evidence chunk (CIM paragraphs, spreadsheet rows, contract clauses, customer rows). Returns chunk text with document, locator, and evidence id.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 12}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_evidence",
        "description": "Get one evidence chunk by id with its full text and locator.",
        "input_schema": {
            "type": "object",
            "properties": {"evidence_id": {"type": "string"}},
            "required": ["evidence_id"],
            "additionalProperties": False,
        },
    },
]

TOOL_LABELS = {
    "list_claims": "Reading the claim ledger",
    "get_claim": "Opening a claim",
    "get_financials": "Reading verified financials",
    "get_adjustments": "Reading add-back decisions",
    "get_scenarios": "Reading scenario results",
    "get_findings": "Reading findings",
    "search_evidence": "Searching the documents",
    "get_evidence": "Opening evidence",
}


def _fmt(v: Decimal | None, unit: str) -> str | None:
    if v is None:
        return None
    if unit == "usd":
        return f"${v:,.0f}"
    if unit == "pct":
        return f"{v:.1f}%"
    if unit == "multiple":
        return f"{v:.2f}x"
    return f"{v:g}"


def _claim_row(c: Claim) -> dict[str, Any]:
    return {
        "claim_id": str(c.id),
        "text": c.claim_text,
        "type": c.claim_type.value,
        "status": c.status.value,
        "claimed": _fmt(c.claimed_value, c.claimed_unit.value),
        "verified": _fmt(c.verified_value, (c.verified_unit or c.claimed_unit).value),
        "source": c.document.display_name,
        "source_evidence_id": str(c.source_evidence_id) if c.source_evidence_id else None,
        "supporting_evidence_ids": [str(link.evidence_id) for link in c.links if link.role == LinkRole.SUPPORTING][:4],
        "contradicting_evidence_ids": [str(link.evidence_id) for link in c.links if link.role == LinkRole.CONTRADICTING][:4],
        "metric_id": str(c.verified_metric_id) if c.verified_metric_id else None,
        "rationale": c.status_rationale,
        "rule": c.status_rule,
    }


def _evidence_row(e: Evidence, full: bool = False) -> dict[str, Any]:
    return {
        "evidence_id": str(e.id),
        "document": e.document.display_name,
        "doc_type": e.document.doc_type.value,
        "locator": e.locator,
        "text": e.text if full else e.text[:400],
        "instruction_like_text": e.contains_instruction_text,
    }


def run_tool(db: Session, deal: Deal, name: str, args: dict[str, Any]) -> str:
    try:
        return json.dumps(_run(db, deal, name, args), default=str)
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})


def _run(db: Session, deal: Deal, name: str, args: dict[str, Any]) -> Any:
    if name == "list_claims":
        rows = list(db.scalars(select(Claim).where(Claim.deal_id == deal.id).order_by(Claim.created_at)))
        if args.get("status"):
            rows = [c for c in rows if c.status.value == args["status"]]
        if args.get("claim_type"):
            rows = [c for c in rows if c.claim_type.value == args["claim_type"]]
        if args.get("query"):
            q = str(args["query"]).lower()
            rows = [c for c in rows if q in c.claim_text.lower() or q in (c.metric_key or "")]
        return {"claims": [_claim_row(c) for c in rows[:30]], "total": len(rows)}
    if name == "get_claim":
        c = db.scalar(select(Claim).where(Claim.id == uuid.UUID(args["claim_id"]), Claim.deal_id == deal.id))
        if c is None:
            return {"error": "claim not found"}
        row = _claim_row(c)
        row["source_evidence"] = _evidence_row(c.source_evidence, full=True) if c.source_evidence else None
        row["evidence"] = [
            {"role": link.role.value, "note": link.note, **_evidence_row(link.evidence, full=True)}
            for link in c.links
            if link.role != LinkRole.SOURCE
        ]
        row["review_decisions"] = [
            {"action": d.action.value, "resulting_status": d.resulting_status, "note": d.note, "is_current": d.is_current}
            for d in c.review_decisions
        ]
        return row
    if name == "get_financials":
        periods = {p.id: p.label for p in db.scalars(select(FinancialPeriod).where(FinancialPeriod.deal_id == deal.id))}
        out: dict[str, Any] = {"periods": sorted(periods.values()), "statement": {}, "metrics": []}
        for m in db.scalars(
            select(FinancialMetric).where(FinancialMetric.deal_id == deal.id).order_by(FinancialMetric.created_at)
        ):
            entry = {
                "metric_id": str(m.id),
                "key": m.key,
                "label": m.label,
                "value": _fmt(m.value, m.unit.value),
                "unit": m.unit.value,
                "period": periods.get(m.period_id) if m.period_id else None,
                "source": m.source.value,
                "formula": m.formula,
                "evidence_ids": list(m.evidence_ids[:3]),
                "requires_review": m.requires_review,
            }
            if m.source.value == "extracted" and m.period_id:
                out["statement"].setdefault(periods.get(m.period_id), {})[m.key] = {
                    "value": entry["value"],
                    "metric_id": entry["metric_id"],
                    "evidence_ids": entry["evidence_ids"],
                }
            else:
                out["metrics"].append(entry)
        out["deal_terms"] = {
            "purchase_price": str(deal.purchase_price),
            "basis": deal.purchase_price_basis.value,
            "debt": str(deal.debt_amount),
            "equity": str(deal.equity_amount),
            "interest_rate_pct": str(deal.interest_rate_pct),
            "amortization_years": deal.amortization_years,
            "covenant_dscr_threshold": str(deal.covenant_dscr_threshold) if deal.covenant_dscr_threshold else None,
        }
        return out
    if name == "get_adjustments":
        adjs = list(db.scalars(select(Adjustment).where(Adjustment.deal_id == deal.id).order_by(Adjustment.sort_order)))
        metrics = {
            m.key: m
            for m in db.scalars(
                select(FinancialMetric)
                .where(
                    FinancialMetric.deal_id == deal.id,
                    FinancialMetric.key.in_(["ebitda_reported", "ebitda_adjusted_seller", "ebitda_adjusted_verified"]),
                )
                .order_by(FinancialMetric.created_at)
            )
        }
        return {
            "adjustments": [
                {
                    "adjustment_id": str(a.id),
                    "label": a.label,
                    "amount": _fmt(a.amount, "usd"),
                    "direction": a.direction.value,
                    "decision": a.decision.value,
                    "rationale": a.decision_rationale,
                    "rule": a.decision_rule,
                    "seller_rationale": a.seller_rationale,
                    "decided_by_reviewer": a.decided_by_user_id is not None,
                    "evidence_ids": list(a.evidence_ids[:4]),
                }
                for a in adjs
            ],
            "ebitda": {
                k: {"value": _fmt(m.value, "usd"), "metric_id": str(m.id), "evidence_ids": list(m.evidence_ids[:3])}
                for k, m in metrics.items()
            },
        }
    if name == "get_scenarios":
        scen: list[dict[str, Any]] = []
        dscr_m = db.scalar(
            select(FinancialMetric)
            .where(FinancialMetric.deal_id == deal.id, FinancialMetric.key == "dscr_base")
            .order_by(FinancialMetric.created_at.desc())
        )
        for sc in db.scalars(select(Scenario).where(Scenario.deal_id == deal.id).order_by(Scenario.sort_order)):
            r = sc.results[-1] if sc.results else None
            scen.append(
                {
                    "scenario_id": str(sc.id),
                    "name": sc.name,
                    "kind": sc.kind.value,
                    "assumptions": {a.key: str(a.value) for a in sc.assumptions},
                    "result_id": str(r.id) if r else None,
                    "year1": r.outputs.get("year1") if r else None,
                    "cfads_bridge": r.outputs.get("cfads_bridge") if r else None,
                    "cash_on_cash_pct": r.outputs.get("cash_on_cash_pct") if r else None,
                    "irr_pct": r.outputs.get("irr_pct") if r else None,
                    "warnings": [w["message"] for w in r.warnings] if r else [],
                    "input_hash": r.input_hash if r else None,
                }
            )
        return {
            "covenant_dscr_threshold": str(deal.covenant_dscr_threshold) if deal.covenant_dscr_threshold else None,
            "dscr_metric_id": str(dscr_m.id) if dscr_m else None,
            "scenarios": scen,
        }
    if name == "get_findings":
        finds = list(db.scalars(select(Finding).where(Finding.deal_id == deal.id)))
        if args.get("kind"):
            finds = [f for f in finds if f.kind.value == args["kind"]]
        rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        finds.sort(key=lambda f: rank[f.severity.value])
        return {
            "findings": [
                {
                    "finding_id": str(f.id),
                    "kind": f.kind.value,
                    "severity": f.severity.value,
                    "title": f.title,
                    "detail": f.detail,
                    "evidence_ids": list(f.evidence_ids[:4]),
                    "metric_ids": list(f.metric_ids[:2]),
                }
                for f in finds
            ]
        }
    if name == "search_evidence":
        evs = list(db.scalars(select(Evidence).where(Evidence.deal_id == deal.id)))
        hits = LexicalRetriever([e.text for e in evs]).search(str(args["query"]), top_k=int(args.get("limit") or 8))
        return {"results": [_evidence_row(evs[h.index]) for h in hits]}
    if name == "get_evidence":
        e = db.scalar(select(Evidence).where(Evidence.id == uuid.UUID(args["evidence_id"]), Evidence.deal_id == deal.id))
        return _evidence_row(e, full=True) if e else {"error": "evidence not found"}
    return {"error": f"unknown tool {name}"}
