"""Build the grounded material for a question. Every fact carries the ids that cite it.

Intent detection is keyword-based and deliberately simple; the fallback is lexical retrieval over
claims, findings, and evidence. Nothing here calls a model."""

from __future__ import annotations

import re
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from bearcase.ai.retrieval import LexicalRetriever
from bearcase.models import Adjustment, Claim, Deal, Evidence, FinancialMetric, FinancialPeriod, Finding, Scenario
from bearcase.models.enums import ClaimStatus, FindingKind, LinkRole

INTENTS: list[tuple[str, re.Pattern[str]]] = [
    (
        "ebitda",
        re.compile(
            r"ebitda|add[- ]?back|adjust|normaliz|reduc|one[- ]time|owner comp|litigation|temporary labor|marketing|integration",
            re.I,
        ),
    ),
    ("growth", re.compile(r"growth|cagr|grown|revenue trend|18\s?%", re.I)),
    ("concentration", re.compile(r"concentrat|largest customer|top customer|apex|10\s?%|22\s?%", re.I)),
    ("recurring", re.compile(r"recurring|maintenance agreement|85\s?%|68\s?%|contract[- ]supported", re.I)),
    (
        "covenant",
        re.compile(r"dscr|covenant|debt service|downside|scenario|leverage|coverage|lender|breach|cash flow|cfads|irr", re.I),
    ),
    ("contract", re.compile(r"contract|term\b|renew|terminat|convenience|harbor", re.I)),
    ("missing", re.compile(r"missing|not provided|quality of earnings|qoe|aging|tax return|need|request", re.I)),
    ("risks", re.compile(r"risk|concern|red flag|worr|issue|problem|wrong|contradict|disagree", re.I)),
    ("valuation", re.compile(r"valuation|multiple|purchase price|enterprise value|\bev\b|price", re.I)),
]


def detect_intents(question: str) -> list[str]:
    found = (
        [name for name, rx in INTENTS.items() if rx.search(question)]
        if isinstance(INTENTS, dict)
        else [name for name, rx in INTENTS if rx.search(question)]
    )
    return found or ["fallback"]


def _fmt(v: Decimal | None, unit: str) -> str:
    if v is None:
        return "n/a"
    if unit == "usd":
        return f"${v:,.0f}"
    if unit == "pct":
        return f"{v:.1f}%"
    if unit == "multiple":
        return f"{v:.2f}x"
    return f"{v:g}"


def build_material(db: Session, deal: Deal, question: str) -> dict[str, Any]:
    intents = detect_intents(question)
    periods = {p.id: p.label for p in db.scalars(select(FinancialPeriod).where(FinancialPeriod.deal_id == deal.id))}
    metrics = list(
        db.scalars(select(FinancialMetric).where(FinancialMetric.deal_id == deal.id).order_by(FinancialMetric.created_at))
    )
    latest_by_key: dict[str, FinancialMetric] = {}
    for m in metrics:
        latest_by_key[m.key] = m  # last write wins = latest
    claims = list(db.scalars(select(Claim).where(Claim.deal_id == deal.id).order_by(Claim.created_at)))
    findings = list(db.scalars(select(Finding).where(Finding.deal_id == deal.id)))
    adjustments = list(db.scalars(select(Adjustment).where(Adjustment.deal_id == deal.id).order_by(Adjustment.sort_order)))
    scenarios = list(db.scalars(select(Scenario).where(Scenario.deal_id == deal.id).order_by(Scenario.sort_order)))

    def metric_fact(key: str) -> dict[str, Any] | None:
        m = latest_by_key.get(key)
        if not m:
            return None
        return {
            "key": key,
            "label": m.label,
            "value": _fmt(m.value, m.unit.value),
            "raw": None if m.value is None else str(m.value),
            "unit": m.unit.value,
            "period": periods.get(m.period_id) if m.period_id else None,
            "formula": m.formula,
            "metric_id": str(m.id),
            "evidence_ids": list(m.evidence_ids[:4]),
            "requires_review": m.requires_review,
        }

    def claim_fact(c: Claim) -> dict[str, Any]:
        return {
            "claim_id": str(c.id),
            "text": c.claim_text,
            "status": c.status.value,
            "type": c.claim_type.value,
            "claimed": _fmt(c.claimed_value, c.claimed_unit.value) if c.claimed_value is not None else None,
            "verified": _fmt(c.verified_value, (c.verified_unit or c.claimed_unit).value)
            if c.verified_value is not None
            else None,
            "rationale": c.status_rationale,
            "rule": c.status_rule,
            "source": c.document.display_name,
            "source_evidence_id": str(c.source_evidence_id) if c.source_evidence_id else None,
            "supporting_ids": [str(link.evidence_id) for link in c.links if link.role == LinkRole.SUPPORTING][:4],
            "contradicting_ids": [str(link.evidence_id) for link in c.links if link.role == LinkRole.CONTRADICTING][:4],
            "metric_id": str(c.verified_metric_id) if c.verified_metric_id else None,
        }

    def finding_fact(f: Finding) -> dict[str, Any]:
        return {
            "finding_id": str(f.id),
            "kind": f.kind.value,
            "severity": f.severity.value,
            "title": f.title,
            "detail": f.detail,
            "evidence_ids": list(f.evidence_ids[:4]),
            "metric_ids": list(f.metric_ids[:2]),
        }

    material: dict[str, Any] = {"question": question, "intents": intents, "company": deal.company_name, "facts": {}}
    facts = material["facts"]
    if "ebitda" in intents or "valuation" in intents:
        facts["ebitda"] = {
            "reported": metric_fact("ebitda_reported"),
            "seller": metric_fact("ebitda_adjusted_seller"),
            "verified": metric_fact("ebitda_adjusted_verified"),
            "adjustments": [
                {
                    "adjustment_id": str(a.id),
                    "label": a.label,
                    "amount": _fmt(a.amount, "usd"),
                    "decision": a.decision.value,
                    "rationale": a.decision_rationale,
                    "rule": a.decision_rule,
                    "seller_rationale": a.seller_rationale,
                    "evidence_ids": list(a.evidence_ids[:4]),
                    "human": a.decided_by_user_id is not None,
                }
                for a in adjustments
            ],
        }
    if "valuation" in intents:
        facts["valuation"] = {
            k: metric_fact(k)
            for k in (
                "enterprise_value",
                "ev_to_ebitda_seller",
                "ev_to_ebitda_verified",
                "debt_to_ebitda_verified",
                "annual_debt_service",
            )
        }
    if "growth" in intents:
        facts["growth"] = {
            "cagr": metric_fact("cagr"),
            "revenue_by_period": [
                {
                    "period": periods.get(m.period_id),
                    "value": _fmt(m.value, "usd"),
                    "metric_id": str(m.id),
                    "evidence_ids": list(m.evidence_ids[:2]),
                }
                for m in metrics
                if m.key == "revenue" and m.period_id
            ],
            "growth_by_period": [
                {
                    "period": periods.get(m.period_id),
                    "value": _fmt(m.value, "pct"),
                    "metric_id": str(m.id),
                    "evidence_ids": list(m.evidence_ids[:2]),
                }
                for m in metrics
                if m.key == "revenue_growth" and m.period_id
            ],
            "claims": [claim_fact(c) for c in claims if c.claim_type.value in ("revenue_growth", "forecast")],
        }
    if "concentration" in intents:
        top = latest_by_key.get("customer_concentration_top1")
        facts["concentration"] = {
            "metric": metric_fact("customer_concentration_top1"),
            "top_customer": top.input_snapshot.get("top_customer_name") if top else None,
            "top_revenue": top.input_snapshot.get("top_customer_revenue") if top else None,
            "claims": [claim_fact(c) for c in claims if c.claim_type.value == "customer_concentration"],
            "findings": [finding_fact(f) for f in findings if f.kind in (FindingKind.CONCENTRATION, FindingKind.RISK)],
        }
    if "recurring" in intents:
        facts["recurring"] = {
            "metric": metric_fact("recurring_revenue_pct"),
            "claims": [claim_fact(c) for c in claims if c.claim_type.value == "recurring_revenue"],
        }
    if "covenant" in intents:
        runs = []
        for sc in scenarios:
            if sc.results:
                r = sc.results[-1]
                y1 = r.outputs.get("year1", {})
                runs.append(
                    {
                        "scenario": sc.name,
                        "kind": sc.kind.value,
                        "result_id": str(r.id),
                        "dscr": y1.get("dscr"),
                        "cfads": y1.get("cfads"),
                        "ebitda": y1.get("ebitda"),
                        "revenue": y1.get("revenue"),
                        "warnings": [w["message"] for w in r.warnings],
                        "assumptions": {
                            a.key: str(a.value)
                            for a in sc.assumptions
                            if a.key
                            in ("revenue_growth_pct", "largest_customer_loss_pct", "gross_margin_change_bps", "interest_rate_pct")
                        },
                    }
                )
        facts["covenant"] = {
            "threshold": str(deal.covenant_dscr_threshold) if deal.covenant_dscr_threshold else None,
            "dscr_base": metric_fact("dscr_base"),
            "cfads_base": metric_fact("cfads_base"),
            "ads": metric_fact("annual_debt_service"),
            "runs": runs,
            "findings": [finding_fact(f) for f in findings if f.kind == FindingKind.COVENANT_WARNING],
        }
    if "contract" in intents:
        facts["contract"] = {
            "claims": [claim_fact(c) for c in claims if c.claim_type.value == "contract_term"],
            "findings": [finding_fact(f) for f in findings if f.kind == FindingKind.RISK],
        }
    if "missing" in intents:
        facts["missing"] = [finding_fact(f) for f in findings if f.kind == FindingKind.MISSING_DOCUMENT]
    if "risks" in intents:
        rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        facts["risks"] = [finding_fact(f) for f in sorted(findings, key=lambda x: rank[x.severity.value])[:8]]
        facts["contradicted_claims"] = [claim_fact(c) for c in claims if c.status == ClaimStatus.CONTRADICTED]
    if intents == ["fallback"]:
        docs: list[tuple[str, Any]] = [("claim", c) for c in claims] + [("finding", f) for f in findings]
        evidence = list(db.scalars(select(Evidence).where(Evidence.deal_id == deal.id)).all())
        docs += [("evidence", e) for e in evidence]
        texts = [x.claim_text if k == "claim" else f"{x.title} {x.detail}" if k == "finding" else x.text for k, x in docs]
        hits = LexicalRetriever(texts).search(question, top_k=6)
        matched: list[dict[str, Any]] = []
        for h in hits:
            kind, obj = docs[h.index]
            if kind == "claim":
                matched.append({"kind": "claim", **claim_fact(obj)})
            elif kind == "finding":
                matched.append({"kind": "finding", **finding_fact(obj)})
            else:
                matched.append(
                    {
                        "kind": "evidence",
                        "evidence_id": str(obj.id),
                        "document": obj.document.display_name,
                        "locator": obj.locator,
                        "text": obj.text[:400],
                    }
                )
        facts["retrieved"] = matched
    return material


def evidence_and_metric_ids(db: Session, deal_id: uuid.UUID) -> tuple[set[str], set[str]]:
    ev = {str(e) for e in db.scalars(select(Evidence.id).where(Evidence.deal_id == deal_id))}
    me = {str(m) for m in db.scalars(select(FinancialMetric.id).where(FinancialMetric.deal_id == deal_id))}
    return ev, me
