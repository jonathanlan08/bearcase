"""Deal analysis: statement mapping, customer aggregation, adjustment review, verified metrics,
claim extraction, claim verification, findings, scenarios, and report generation."""

from __future__ import annotations

import re
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from bearcase import ENGINE_VERSION
from bearcase.ai.guardrails import apply_guardrails
from bearcase.ai.provider import AIProvider, ChunkRef, ClaimContext, DocumentContext, get_provider
from bearcase.ai.retrieval import LexicalRetriever
from bearcase.audit import record
from bearcase.engine import formulas as f
from bearcase.engine.metrics import LABOR_LINE_KEYS, LINE_KEYS, format_multiple, format_plain, format_value, period_metrics
from bearcase.engine.money import Calc, D
from bearcase.engine.scenarios import ScenarioInputs, project
from bearcase.ingest.customers import aggregate_customers
from bearcase.ingest.parsers.common import ParsedChunk
from bearcase.ingest.statement_mapper import map_income_statement
from bearcase.models import (
    Adjustment,
    Claim,
    ClaimEvidenceLink,
    Deal,
    Document,
    Evidence,
    ExtractionRun,
    FinancialMetric,
    FinancialPeriod,
    Finding,
    ProcessingJob,
    Scenario,
    ScenarioAssumption,
    ScenarioResult,
)
from bearcase.models.enums import (
    AdjustmentDecision,
    AdjustmentDirection,
    ClaimStatus,
    ClaimType,
    ClaimUnit,
    DealStatus,
    DocumentStatus,
    DocumentType,
    EvidenceKind,
    FindingKind,
    FindingStatus,
    LinkRole,
    MetricSource,
    ReportStatus,
    RunStatus,
    RunType,
    ScenarioKind,
    Severity,
)
from bearcase.pipeline.jobs import JobLog
from bearcase.reports.assemble import DOC_TYPE_LABELS, assemble_report

NARRATIVE_TYPES = {DocumentType.CIM, DocumentType.DEBT_TERM_SHEET, DocumentType.CUSTOMER_CONTRACT, DocumentType.ACQUISITION_MODEL}
PRIMARY_TYPES = {
    DocumentType.FINANCIAL_STATEMENTS,
    DocumentType.CUSTOMER_REVENUE,
    DocumentType.CUSTOMER_CONTRACT,
    DocumentType.DEBT_TERM_SHEET,
}
TOLERANCE = {
    "pct": Decimal("1.0"),
    "usd": Decimal("0.02"),
    "multiple": Decimal("0.05"),
    "years": Decimal("0"),
    "count": Decimal("0"),
    "months": Decimal("0"),
}
METRIC_LABELS = {
    "revenue": "Revenue",
    "cagr": "Revenue CAGR",
    "revenue_growth": "Revenue growth",
    "gross_margin": "Gross margin",
    "operating_margin": "Operating margin",
    "ebitda_reported": "Reported EBITDA (reconciled)",
    "ebitda_adjusted_verified": "Verified adjusted EBITDA",
    "ebitda_adjusted_seller": "Seller adjusted EBITDA",
    "customer_concentration_top1": "Largest customer share of revenue",
    "recurring_revenue_pct": "Contract-supported recurring revenue",
    "covenant_dscr_threshold": "Covenant DSCR threshold (deal terms)",
    "interest_rate_pct": "Interest rate (acquisition model)",
    "amortization_years": "Amortization years (acquisition model)",
    "opex_temporary_labor_recurring": "Temporary labor recurrence (periods present)",
}


# ---------- helpers -------------------------------------------------------------------------


def _chunks_from_evidence(rows: list[Evidence]) -> list[ParsedChunk]:
    return [ParsedChunk(kind=e.kind.value, locator=e.locator, text=e.text, structured=e.structured) for e in rows]


def put_metric(
    db: Session,
    deal: Deal,
    *,
    key: str,
    label: str,
    value: Decimal | None,
    unit: str,
    source: MetricSource,
    period: FinancialPeriod | None = None,
    evidence_ids: list[uuid.UUID] | None = None,
    formula: str | None = None,
    input_snapshot: dict[str, Any] | None = None,
    confidence: Decimal | float = 1,
    requires_review: bool = False,
    missing: list[str] | None = None,
    raw_value: str | None = None,
) -> FinancialMetric:
    unique_ev = list(dict.fromkeys(str(e) for e in (evidence_ids or [])))
    m = FinancialMetric(
        deal_id=deal.id,
        period_id=period.id if period else None,
        key=key,
        label=label,
        value=value,
        raw_value=raw_value,
        unit=ClaimUnit(unit),
        source=source,
        formula=formula,
        input_snapshot=input_snapshot or {},
        evidence_ids=unique_ev,
        confidence=Decimal(str(confidence)),
        requires_review=requires_review,
        missing_inputs=missing or [],
    )
    db.add(m)
    db.flush()
    return m


def put_calc(
    db: Session,
    deal: Deal,
    calc: Calc,
    *,
    key: str | None = None,
    label: str | None = None,
    period: FinancialPeriod | None = None,
    evidence_ids: list[uuid.UUID] | None = None,
    extra_snapshot: dict[str, Any] | None = None,
    requires_review: bool = False,
) -> FinancialMetric:
    snap = calc.as_snapshot()
    snap.update(extra_snapshot or {})
    k = key or calc.key
    return put_metric(
        db,
        deal,
        key=k,
        label=label or METRIC_LABELS.get(k, k.replace("_", " ").capitalize()),
        value=calc.value,
        unit=calc.unit if calc.unit in ("usd", "pct", "multiple", "years", "count") else "count",
        source=MetricSource.CALCULATED,
        period=period,
        evidence_ids=evidence_ids,
        formula=calc.formula,
        input_snapshot=snap,
        requires_review=requires_review or (not calc.ok),
        missing=list(calc.missing),
    )


def _clear_analysis(db: Session, deal: Deal) -> None:
    db.execute(delete(Finding).where(Finding.deal_id == deal.id))
    db.execute(delete(FinancialMetric).where(FinancialMetric.deal_id == deal.id))
    db.execute(delete(FinancialPeriod).where(FinancialPeriod.deal_id == deal.id))
    db.execute(delete(Evidence).where(Evidence.deal_id == deal.id, Evidence.kind == EvidenceKind.CSV_AGGREGATE))
    db.flush()


# ---------- statements ----------------------------------------------------------------------


def build_statement_metrics(
    db: Session, deal: Deal, docs: list[Document], ev: dict[uuid.UUID, list[Evidence]]
) -> dict[str, FinancialPeriod]:
    periods: dict[str, FinancialPeriod] = {}
    for doc in docs:
        if doc.doc_type != DocumentType.FINANCIAL_STATEMENTS:
            continue
        rows = ev.get(doc.id, [])
        smap = map_income_statement(_chunks_from_evidence(rows))
        if smap is None:
            continue
        for ordinal, label in enumerate(smap.periods):
            period = FinancialPeriod(
                deal_id=deal.id, label=label, ordinal=ordinal, source_document_id=doc.id, source_sheet=smap.sheet
            )
            year = re.search(r"(20\d{2})", label)
            if year:
                from datetime import date

                y = int(year.group(1))
                period.start_date, period.end_date = date(y, 1, 1), date(y, 12, 31)
            db.add(period)
            db.flush()
            periods[label] = period
            for key, mv in smap.lines[label].items():
                put_metric(
                    db,
                    deal,
                    key=key,
                    label=key.replace("opex_", "").replace("_", " ").capitalize(),
                    value=mv.value,
                    unit="usd",
                    source=MetricSource.EXTRACTED,
                    period=period,
                    evidence_ids=[rows[mv.chunk_index].id],
                    input_snapshot={"sheet": mv.sheet, "cell": mv.cell, "row": mv.row, "document_id": str(doc.id)},
                    confidence=mv.confidence,
                    requires_review=mv.confidence < 0.8,
                    raw_value=mv.raw,
                )
        # calculated per-period metrics
        pdict = smap.as_periods()
        for pc in period_metrics(pdict):
            pc_period = periods.get(pc.period_label or "")
            inputs = [k for k in pc.calc.inputs if k in LINE_KEYS or k.endswith("_revenue")]
            ev_ids: list[uuid.UUID] = []
            for k in pc.calc.inputs:
                line = {
                    "current_period_revenue": "revenue",
                    "prior_period_revenue": "revenue",
                    "first_period_revenue": "revenue",
                    "last_period_revenue": "revenue",
                    "cost_of_goods_sold": "cost_of_goods_sold",
                    "revenue": "revenue",
                    "operating_income": "operating_income",
                    "net_income": "net_income",
                    "interest_expense": "interest_expense",
                    "income_tax_expense": "income_tax_expense",
                    "depreciation": "depreciation",
                    "amortization": "amortization",
                }.get(k)
                if not line:
                    continue
                for plabel in smap.periods:
                    mv_opt = smap.lines[plabel].get(line)
                    if mv_opt and (plabel == pc.period_label or k.startswith(("prior", "first")) or pc.calc.key == "cagr"):
                        ev_ids.append(rows[mv_opt.chunk_index].id)
            put_calc(
                db,
                deal,
                pc.calc,
                period=pc_period,
                evidence_ids=sorted(set(ev_ids), key=str),
                requires_review=bool(pc.calc.notes and "review" in " ".join(pc.calc.notes)),
            )
            _ = inputs
        # temporary-labor recurrence metric
        present = [p for p in smap.periods if smap.lines[p].get("opex_temporary_labor")]
        if present:
            latest = periods[smap.periods[-1]]
            put_metric(
                db,
                deal,
                key="opex_temporary_labor_recurring",
                label=METRIC_LABELS["opex_temporary_labor_recurring"],
                value=Decimal(len(present)),
                unit="count",
                source=MetricSource.CALCULATED,
                period=latest,
                evidence_ids=[rows[smap.lines[p]["opex_temporary_labor"].chunk_index].id for p in present],
                formula="count(periods where temporary labor line is present)",
                input_snapshot={
                    "periods": present,
                    "values": {p: str(smap.lines[p]["opex_temporary_labor"].value) for p in present},
                },
            )
    return periods


# ---------- customers -----------------------------------------------------------------------


def build_customer_metrics(
    db: Session, deal: Deal, docs: list[Document], ev: dict[uuid.UUID, list[Evidence]], latest: FinancialPeriod | None
) -> None:
    for doc in docs:
        if doc.doc_type != DocumentType.CUSTOMER_REVENUE:
            continue
        rows = ev.get(doc.id, [])
        agg = aggregate_customers(_chunks_from_evidence(rows))
        if agg is None or agg.total == 0:
            continue
        top = agg.top
        version_id = rows[0].document_version_id if rows else None
        # aggregate evidence chunks (derived, but they are what a reviewer wants to click)
        top_ev = Evidence(
            deal_id=deal.id,
            document_id=doc.id,
            document_version_id=version_id,
            kind=EvidenceKind.CSV_AGGREGATE,
            chunk_index=100000,
            locator={"aggregate": "customer_totals", "rows": [rows[i].locator["row"] for i in (top[2] if top else [])]},
            text=f"Customer totals ({agg.revenue_column}): top customer {top[0] if top else 'n/a'} = {top[1] if top else 0:,.0f} of {agg.total:,.0f} total across {agg.customer_count} customers.",
            structured={
                "top": [(n, str(t)) for n, t, _ in agg.customer_totals[:10]],
                "total": str(agg.total),
                "customer_count": agg.customer_count,
            },
        )
        rec_ev = Evidence(
            deal_id=deal.id,
            document_id=doc.id,
            document_version_id=version_id,
            kind=EvidenceKind.CSV_AGGREGATE,
            chunk_index=100001,
            locator={"aggregate": "recurring_revenue", "rows": [rows[i].locator["row"] for i in agg.recurring_chunks[:200]]},
            text=f"Revenue under maintenance agreements ({agg.revenue_column}): {agg.recurring:,.0f} of {agg.total:,.0f} total.",
            structured={"recurring": str(agg.recurring), "total": str(agg.total), "recurring_rows": len(agg.recurring_chunks)},
        )
        db.add_all([top_ev, rec_ev])
        db.flush()
        if top:
            calc = f.customer_concentration(top[1], agg.total)
            put_calc(
                db,
                deal,
                calc,
                evidence_ids=[top_ev.id, *[rows[i].id for i in top[2][:5]]],
                extra_snapshot={
                    "top_customer_name": top[0],
                    "top_customer_revenue": str(top[1]),
                    "total_revenue": str(agg.total),
                    "customer_count": agg.customer_count,
                    "document_id": str(doc.id),
                },
            )
        calc = f.recurring_revenue_share(agg.recurring, agg.total)
        put_calc(
            db,
            deal,
            calc,
            evidence_ids=[rec_ev.id, *[rows[i].id for i in agg.recurring_chunks[:5]]],
            extra_snapshot={"recurring_rows": len(agg.recurring_chunks), "document_id": str(doc.id)},
        )
        put_metric(
            db,
            deal,
            key="customer_count",
            label="Customers in revenue file",
            value=Decimal(agg.customer_count),
            unit="count",
            source=MetricSource.CALCULATED,
            evidence_ids=[top_ev.id],
            input_snapshot={"document_id": str(doc.id)},
        )
        _ = latest


# ---------- acquisition model: terms and adjustments ----------------------------------------

MODEL_TERM_SYNONYMS = {
    "interest_rate_pct": ["interest rate"],
    "amortization_years": ["amortization (years)", "amortization"],
    "funded_debt_model": ["senior debt", "debt"],
    "enterprise_value_model": ["enterprise value", "purchase price"],
    "ebitda_adjusted_seller": ["adjusted ebitda fy2024", "adjusted ebitda"],
}


def _num_from_cell(v: Any) -> Decimal | None:
    if v is None:
        return None
    if isinstance(v, int | float):
        return Decimal(str(v))
    s = str(v).replace(",", "").replace("$", "").replace("x", "").strip()
    pct = s.endswith("%")
    s = s.rstrip("%")
    try:
        return Decimal(s)
    except Exception:
        return None
    finally:
        _ = pct


def build_model_metrics_and_adjustments(
    db: Session, deal: Deal, docs: list[Document], ev: dict[uuid.UUID, list[Evidence]], latest: FinancialPeriod | None
) -> None:
    for doc in docs:
        if doc.doc_type != DocumentType.ACQUISITION_MODEL:
            continue
        rows = ev.get(doc.id, [])
        for e in rows:
            if e.kind != EvidenceKind.SHEET_ROW or not e.structured:
                continue
            values = e.structured.get("values", [])
            if len(values) < 2 or not values[0]:
                continue
            label = values[0].strip().lower()
            sheet = e.locator.get("sheet", "").lower()
            if sheet.startswith("assumption"):
                for key, syns in MODEL_TERM_SYNONYMS.items():
                    if any(label == s or label.startswith(s) for s in syns):
                        val = _num_from_cell(values[1])
                        if val is None:
                            continue
                        unit = "pct" if "%" in str(values[1]) else "years" if key == "amortization_years" else "usd"
                        if (
                            db.scalar(
                                select(FinancialMetric.id).where(FinancialMetric.deal_id == deal.id, FinancialMetric.key == key)
                            )
                            is None
                        ):
                            put_metric(
                                db,
                                deal,
                                key=key,
                                label=METRIC_LABELS.get(key, values[0]),
                                value=val,
                                unit=unit,
                                source=MetricSource.EXTRACTED,
                                period=latest if key == "ebitda_adjusted_seller" else None,
                                evidence_ids=[e.id],
                                input_snapshot={
                                    "sheet": e.locator.get("sheet"),
                                    "row": e.locator.get("row"),
                                    "document_id": str(doc.id),
                                },
                                raw_value=str(values[1]),
                            )
                        break
            elif sheet.startswith("adjust"):
                amount = _num_from_cell(values[1])
                if amount is None or label.startswith(("total", "reported ebitda", "adjusted ebitda", "adjustment")):
                    continue
                key = re.sub(r"[^a-z0-9]+", "_", label).strip("_")[:120]
                existing = db.scalar(select(Adjustment).where(Adjustment.deal_id == deal.id, Adjustment.key == key))
                if existing is None:
                    existing = Adjustment(
                        deal_id=deal.id,
                        key=key,
                        label=values[0].strip(),
                        amount=amount,
                        direction=AdjustmentDirection.ADD_BACK,
                        period_label=latest.label if latest else "FY",
                        seller_rationale=values[2] if len(values) > 2 else None,
                        sort_order=e.locator.get("row", 0),
                    )
                    db.add(existing)
                existing.evidence_ids = [str(e.id)]
                db.flush()


def review_adjustments(db: Session, deal: Deal, periods: dict[str, FinancialPeriod]) -> None:
    """Deterministic add-back review against statement lines. Human decisions are never overwritten."""
    ordered = sorted(periods.values(), key=lambda p: p.ordinal)
    if not ordered:
        return
    latest = ordered[-1]
    lines: dict[str, dict[str, FinancialMetric]] = {}
    for m in db.scalars(
        select(FinancialMetric).where(FinancialMetric.deal_id == deal.id, FinancialMetric.source == MetricSource.EXTRACTED)
    ):
        if m.period_id:
            lines.setdefault(m.key, {})[str(m.period_id)] = m
    notes = {
        e.id: e
        for e in db.scalars(select(Evidence).where(Evidence.deal_id == deal.id, Evidence.kind == EvidenceKind.SHEET_ROW))
        if "notes" in e.locator.get("sheet", "").lower()
    }

    def line(key: str, p: FinancialPeriod) -> FinancialMetric | None:
        return lines.get(key, {}).get(str(p.id))

    def note_for(*words: str) -> list[uuid.UUID]:
        return [e.id for e in notes.values() if all(w in e.text.lower() for w in words)]

    for adj in db.scalars(select(Adjustment).where(Adjustment.deal_id == deal.id)):
        if adj.decided_by_user_id is not None:
            continue
        label = adj.label.lower()
        ev: list[uuid.UUID] = []
        if "owner" in label and "comp" in label:
            m_owner = line("opex_owner_compensation", latest)
            if m_owner and m_owner.value is not None and adj.amount < m_owner.value:
                ev = [uuid.UUID(x) for x in m_owner.evidence_ids] + note_for("owner")
                adj.decision, adj.decision_rule = AdjustmentDecision.ACCEPTED, "supported_by_statement_line"
                adj.decision_rationale = f"The {latest.label} owner compensation line of ${m_owner.value:,.0f} supports a normalization of ${adj.amount:,.0f}; the residual salary remains above zero."
            else:
                adj.decision, adj.decision_rule, adj.decision_rationale = (
                    AdjustmentDecision.REVIEW_REQUIRED,
                    "line_not_found",
                    "No owner compensation line was found in the statements.",
                )
        elif any(w in label for w in ("litigation", "settlement", "legal")):
            m_legal = line("opex_legal_professional", latest)
            priors = [line("opex_legal_professional", p) for p in ordered[:-1]]
            prior_vals = [pm.value for pm in priors if pm and pm.value is not None]
            if m_legal and m_legal.value is not None and prior_vals:
                avg = sum(prior_vals, Decimal(0)) / len(prior_vals)
                excess = m_legal.value - avg
                ev = (
                    [uuid.UUID(x) for x in m_legal.evidence_ids]
                    + [uuid.UUID(x) for pm in priors if pm for x in pm.evidence_ids]
                    + note_for("settlement")
                )
                if excess >= adj.amount * Decimal("0.9"):
                    adj.decision, adj.decision_rule = AdjustmentDecision.ACCEPTED, "supported_by_statement_note"
                    adj.decision_rationale = f"{latest.label} legal and professional fees of ${m_legal.value:,.0f} exceed the prior-year average of ${avg:,.0f} by ${excess:,.0f}, consistent with a one-time ${adj.amount:,.0f} item disclosed in the notes."
                else:
                    adj.decision, adj.decision_rule = AdjustmentDecision.REVIEW_REQUIRED, "excess_below_claimed"
                    adj.decision_rationale = f"Legal fees exceed the prior-year average by only ${excess:,.0f}, less than the ${adj.amount:,.0f} claimed."
            else:
                adj.decision, adj.decision_rule, adj.decision_rationale = (
                    AdjustmentDecision.REVIEW_REQUIRED,
                    "line_not_found",
                    "Insufficient legal-fee history to assess the item.",
                )
        elif "temporary" in label or "temp labor" in label or "contract labor" in label:
            ms = [line("opex_temporary_labor", p) for p in ordered]
            vals = [(p.label, pm.value) for p, pm in zip(ordered, ms, strict=True) if pm and pm.value is not None]
            if len(vals) >= 2:
                ev = [uuid.UUID(x) for pm in ms if pm for x in pm.evidence_ids] + note_for("temporary")
                adj.decision, adj.decision_rule = AdjustmentDecision.REJECTED, "recurs_across_periods"
                adj.decision_rationale = (
                    "Temporary labor appears in every period presented ("
                    + ", ".join(f"{p} ${v:,.0f}" for p, v in vals)
                    + "); it is a recurring operating cost, not a one-time item."
                )
            else:
                adj.decision, adj.decision_rule, adj.decision_rationale = (
                    AdjustmentDecision.REVIEW_REQUIRED,
                    "insufficient_history",
                    "Only one period of temporary labor is available.",
                )
        elif "marketing" in label or "brand" in label or "advertis" in label:
            m_mkt = line("opex_marketing", latest)
            priors = [line("opex_marketing", p) for p in ordered[:-1]]
            prior_vals = [pm.value for pm in priors if pm and pm.value is not None]
            if m_mkt and m_mkt.value is not None and prior_vals:
                prior = prior_vals[-1]
                excess = m_mkt.value - prior
                ev = (
                    [uuid.UUID(x) for x in m_mkt.evidence_ids]
                    + [uuid.UUID(x) for pm in priors if pm for x in pm.evidence_ids]
                    + note_for("brand")
                )
                adj.decision, adj.decision_rule = AdjustmentDecision.REVIEW_REQUIRED, "partially_above_trend"
                adj.decision_rationale = f"{latest.label} marketing of ${m_mkt.value:,.0f} is only ${excess:,.0f} above the prior year (${prior:,.0f}) while spending continues; at most the excess, not ${adj.amount:,.0f}, may be non-recurring."
            else:
                adj.decision, adj.decision_rule, adj.decision_rationale = (
                    AdjustmentDecision.REVIEW_REQUIRED,
                    "line_not_found",
                    "No marketing line history to assess the item.",
                )
        elif any(w in label for w in ("integration", "synerg", "savings", "post-close")):
            adj.decision, adj.decision_rule = AdjustmentDecision.UNSUPPORTED, "no_evidence"
            adj.decision_rationale = (
                "No executed plan, contract, or statement line supports the savings; buyer synergies are not historical earnings."
            )
        else:
            adj.decision, adj.decision_rule, adj.decision_rationale = (
                AdjustmentDecision.REVIEW_REQUIRED,
                "no_rule",
                "No deterministic rule applies; a reviewer must assess the item.",
            )
        adj.evidence_ids = sorted({*(adj.evidence_ids or []), *[str(e) for e in ev]})
    db.flush()


# ---------- deal-level metrics --------------------------------------------------------------


def _metric(db: Session, deal: Deal, key: str, period: FinancialPeriod | None = None) -> FinancialMetric | None:
    q = select(FinancialMetric).where(FinancialMetric.deal_id == deal.id, FinancialMetric.key == key)
    q = q.where(FinancialMetric.period_id == period.id) if period else q.order_by(FinancialMetric.created_at.desc())
    return db.scalar(q)


def build_deal_metrics(db: Session, deal: Deal, periods: dict[str, FinancialPeriod]) -> None:
    ordered = sorted(periods.values(), key=lambda p: p.ordinal)
    latest = ordered[-1] if ordered else None
    reported = _metric(db, deal, "ebitda_reported", latest) if latest else None
    adjustments = list(db.scalars(select(Adjustment).where(Adjustment.deal_id == deal.id)))
    accepted = {
        a.label: a.amount
        for a in adjustments
        if a.decision == AdjustmentDecision.ACCEPTED and a.direction == AdjustmentDirection.ADD_BACK
    }
    downward = {
        a.label: a.amount
        for a in adjustments
        if a.decision == AdjustmentDecision.ACCEPTED and a.direction == AdjustmentDirection.DOWNWARD
    }
    adj_ev = [uuid.UUID(x) for a in adjustments if a.decision == AdjustmentDecision.ACCEPTED for x in a.evidence_ids]
    verified = f.adjusted_ebitda(reported.value if reported else None, accepted, downward)
    vm = put_calc(
        db,
        deal,
        verified,
        evidence_ids=([uuid.UUID(x) for x in reported.evidence_ids] if reported else []) + adj_ev,
        extra_snapshot={
            "reported_metric_id": str(reported.id) if reported else None,
            "accepted_adjustment_ids": [str(a.id) for a in adjustments if a.decision == AdjustmentDecision.ACCEPTED],
        },
    )
    seller_total = sum((a.amount for a in adjustments if a.direction == AdjustmentDirection.ADD_BACK), Decimal(0))
    if reported and reported.value is not None and adjustments and _metric(db, deal, "ebitda_adjusted_seller") is None:
        put_calc(
            db,
            deal,
            f.adjusted_ebitda(reported.value, {a.label: a.amount for a in adjustments}, {}, key="ebitda_adjusted_seller"),
            evidence_ids=[uuid.UUID(x) for x in reported.evidence_ids]
            + [uuid.UUID(x) for a in adjustments for x in a.evidence_ids],
        )
    _ = seller_total
    ev_calc = f.enterprise_value(deal.purchase_price, deal.purchase_price_basis.value, deal.debt_assumed, deal.cash_acquired)
    evm = put_calc(db, deal, ev_calc, extra_snapshot={"source": "deal terms entered by the analyst"})
    seller = _metric(db, deal, "ebitda_adjusted_seller")
    put_calc(
        db,
        deal,
        f.ev_to_ebitda(ev_calc.value, vm.value, key="ev_to_ebitda_verified"),
        evidence_ids=[uuid.UUID(x) for x in vm.evidence_ids][:6],
        extra_snapshot={"metric_ids": [str(evm.id), str(vm.id)]},
    )
    if seller:
        put_calc(
            db,
            deal,
            f.ev_to_ebitda(ev_calc.value, seller.value, key="ev_to_ebitda_seller"),
            evidence_ids=[uuid.UUID(x) for x in seller.evidence_ids][:6],
            extra_snapshot={"metric_ids": [str(evm.id), str(seller.id)]},
        )
        put_calc(
            db,
            deal,
            f.debt_to_ebitda(deal.debt_amount, seller.value, key="debt_to_ebitda_seller"),
            evidence_ids=[uuid.UUID(x) for x in seller.evidence_ids][:6],
        )
    put_calc(
        db,
        deal,
        f.debt_to_ebitda(deal.debt_amount, vm.value, key="debt_to_ebitda_verified"),
        evidence_ids=[uuid.UUID(x) for x in vm.evidence_ids][:6],
        extra_snapshot={"metric_ids": [str(vm.id)]},
    )
    put_calc(
        db,
        deal,
        f.annual_debt_service(deal.debt_amount, deal.interest_rate_pct, deal.amortization_years, deal.payments_per_year),
        extra_snapshot={"source": "deal terms entered by the analyst"},
    )
    put_metric(
        db,
        deal,
        key="covenant_dscr_threshold",
        label=METRIC_LABELS["covenant_dscr_threshold"],
        value=deal.covenant_dscr_threshold,
        unit="multiple",
        source=MetricSource.EXTRACTED,
        input_snapshot={"source": "deal terms entered by the analyst"},
        requires_review=deal.covenant_dscr_threshold is None,
    )
    if _metric(db, deal, "interest_rate_pct") is None:
        put_metric(
            db,
            deal,
            key="interest_rate_pct",
            label="Interest rate (deal terms)",
            value=deal.interest_rate_pct,
            unit="pct",
            source=MetricSource.EXTRACTED,
            input_snapshot={"source": "deal terms entered by the analyst"},
        )
    if _metric(db, deal, "amortization_years") is None:
        put_metric(
            db,
            deal,
            key="amortization_years",
            label="Amortization years (deal terms)",
            value=Decimal(deal.amortization_years),
            unit="years",
            source=MetricSource.EXTRACTED,
            input_snapshot={"source": "deal terms entered by the analyst"},
        )


# ---------- claims --------------------------------------------------------------------------


def _run(db: Session, deal: Deal, doc: Document | None, run_type: RunType, provider: AIProvider, res: Any) -> ExtractionRun:
    run = ExtractionRun(
        deal_id=deal.id,
        document_id=doc.id if doc else None,
        run_type=run_type,
        status=RunStatus.SUCCEEDED
        if res.ok
        else (RunStatus.INVALID_OUTPUT if (res.error or "").startswith("invalid_output") else RunStatus.FAILED),
        provider=provider.name,
        model=provider.model,
        prompt_version=res.prompt_version,
        schema_version=res.schema_version,
        input_hash=res.input_hash,
        raw_output=res.raw,
        usage=res.usage,
        error=res.error,
    )
    db.add(run)
    db.flush()
    return run


def extract_claims(
    db: Session,
    deal: Deal,
    docs: list[Document],
    ev: dict[uuid.UUID, list[Evidence]],
    provider: AIProvider,
    jl: JobLog | None = None,
) -> list[Claim]:
    claims: list[Claim] = []
    existing = {(c.document_id, c.key): c for c in db.scalars(select(Claim).where(Claim.deal_id == deal.id))}
    seen_keys: set[tuple[uuid.UUID, str]] = set()
    for doc in docs:
        if doc.doc_type not in NARRATIVE_TYPES:
            continue
        rows = ev.get(doc.id, [])
        if not rows:
            continue
        ctx = DocumentContext(
            doc.display_name,
            doc.doc_type.value,
            "",
            [ChunkRef(i, e.kind.value, e.locator, e.text, doc.doc_type.value, doc.display_name) for i, e in enumerate(rows)],
        )
        res = provider.extract_claims(ctx)
        run = _run(db, deal, doc, RunType.EXTRACT, provider, res)
        if not res.ok or res.output is None:
            if jl:
                jl.step(f"Extraction failed for {doc.display_name}: {res.error}", jl.job.progress)
            continue
        for ec in res.output.claims:
            if ec.source_chunk_index >= len(rows):
                continue  # citation does not resolve; drop the claim rather than invent a source
            key = ec.key
            comparator = key.rsplit("__", 1)[1] if "__" in key else None
            seen_keys.add((doc.id, key))
            claim = existing.get((doc.id, key))
            if claim is None:
                claim = Claim(
                    deal_id=deal.id,
                    document_id=doc.id,
                    key=key,
                    claim_text=ec.claim_text,
                    claim_type=ClaimType(ec.claim_type),
                    metric_key=ec.metric_key,
                    period_label=ec.period_label,
                    claimed_value=ec.claimed_value,
                    claimed_unit=ClaimUnit(ec.claimed_unit),
                    normalized={"comparator": comparator} if comparator else {},
                    confidence=Decimal(str(round(ec.confidence, 3))),
                    source_evidence_id=rows[ec.source_chunk_index].id,
                )
                db.add(claim)
                db.flush()
                db.add(ClaimEvidenceLink(claim_id=claim.id, evidence_id=rows[ec.source_chunk_index].id, role=LinkRole.SOURCE))
            claim.extraction_run_id = run.id
            claims.append(claim)
    for (doc_id, key), claim in existing.items():
        if (doc_id, key) not in seen_keys and not claim.review_decisions:
            db.delete(claim)
    db.flush()
    return claims


def _gap(diff: Decimal, unit: str) -> str:
    """A difference expressed in the claim's own unit, in words a reader can follow."""
    if unit == "pct":
        return f"{diff:.1f} percentage points"
    return _fmt(diff, unit)


def _compare(claimed: Decimal, verified: Decimal, unit: str, comparator: str | None) -> tuple[bool, str]:
    """Settle a numeric claim against the engine's figure and explain the outcome in plain words.

    The explanation never shows Decimal repr; every number is formatted for the claim's unit."""
    tol = TOLERANCE.get(unit, Decimal("0"))
    if comparator == "lte":
        ok = verified <= claimed
        return (
            ok,
            f"the claim allows at most {_fmt(claimed, unit)} and the verified figure of {_fmt(verified, unit)} is "
            f"{'within' if ok else 'above'} that ceiling",
        )
    if unit == "usd":
        diff = abs(claimed - verified) / (abs(verified) if verified else Decimal(1))
        ok = diff <= tol
        if diff == 0:
            return True, "the figures match exactly"
        return (
            ok,
            f"the gap is {_fmt(diff * 100, 'pct')} of the verified figure, {'within' if ok else 'beyond'} the "
            f"{_fmt(tol * 100, 'pct')} allowed for rounding",
        )
    diff = abs(claimed - verified)
    ok = diff <= tol
    if diff == 0:
        return True, "the figures match exactly"
    if tol == 0:
        return ok, f"the figures differ by {_gap(diff, unit)} and no rounding allowance applies"
    return ok, f"the gap is {_gap(diff, unit)}, {'within' if ok else 'beyond'} the {_gap(tol, unit)} allowed for rounding"


def verify_claims(
    db: Session,
    deal: Deal,
    docs: list[Document],
    ev: dict[uuid.UUID, list[Evidence]],
    provider: AIProvider,
    periods: dict[str, FinancialPeriod],
) -> None:
    doc_by_id = {d.id: d for d in docs}
    doc_of_evidence = {e.id: doc_by_id[d] for d in ev for e in ev[d] if d in doc_by_id}
    ordered = sorted(periods.values(), key=lambda p: p.ordinal)
    latest = ordered[-1] if ordered else None
    primary_chunks: list[tuple[Evidence, Document]] = [
        (e, doc_by_id[d]) for d in ev for e in ev[d] if doc_by_id[d].doc_type in PRIMARY_TYPES
    ]
    for claim in db.scalars(select(Claim).where(Claim.deal_id == deal.id)):
        if claim.review_decisions:
            continue  # never re-verify a claim a human has decided on
        db.execute(
            delete(ClaimEvidenceLink).where(ClaimEvidenceLink.claim_id == claim.id, ClaimEvidenceLink.role != LinkRole.SOURCE)
        )
        comparator = claim.normalized.get("comparator") if claim.normalized else None
        metric: FinancialMetric | None = None
        if claim.metric_key:
            period = periods.get(claim.period_label or "") or latest
            metric = _metric(db, deal, claim.metric_key, period) or _metric(db, deal, claim.metric_key)
        if (
            metric is not None
            and claim.claimed_value is not None
            and comparator != "forward"
            and not (claim.metric_key or "").endswith("_recurring")
        ):
            claim.verified_metric_id = metric.id
            claim.verified_value, claim.verified_unit = metric.value, metric.unit
            if metric.value is None or metric.requires_review:
                claim.status, claim.status_rule = ClaimStatus.REVIEW_REQUIRED, "metric_requires_review"
                claim.status_rationale = f"The calculated value for {metric.label} is unavailable or flagged for review ({', '.join(metric.missing_inputs) or 'see notes'})."
            else:
                ok, detail = _compare(claim.claimed_value, metric.value, metric.unit.value, comparator)
                role = LinkRole.SUPPORTING if ok else LinkRole.CONTRADICTING
                for eid in dict.fromkeys(metric.evidence_ids[:8]):
                    db.add(
                        ClaimEvidenceLink(
                            claim_id=claim.id,
                            evidence_id=uuid.UUID(eid),
                            role=role,
                            note=f"{metric.label}: {metric.formula or 'extracted value'}",
                        )
                    )
                claim.status = ClaimStatus.SUPPORTED if ok else ClaimStatus.CONTRADICTED
                claim.status_rule = "numeric_match_within_tolerance" if ok else "numeric_mismatch_beyond_tolerance"
                claim.status_rationale = (
                    f"{metric.label} calculated from {_source_names(metric.evidence_ids, doc_of_evidence) or 'the primary documents'} "
                    f"is {_fmt(metric.value, metric.unit.value)} against the {_fmt(claim.claimed_value, claim.claimed_unit.value)} claimed; {detail}."
                )
        elif metric is not None and claim.metric_key and claim.metric_key.endswith("_recurring"):
            claim.verified_metric_id = metric.id
            claim.verified_value, claim.verified_unit = metric.value, metric.unit
            n = int(metric.value or 0)
            if n >= 2:
                for eid in dict.fromkeys(metric.evidence_ids[:6]):
                    db.add(
                        ClaimEvidenceLink(
                            claim_id=claim.id,
                            evidence_id=uuid.UUID(eid),
                            role=LinkRole.CONTRADICTING,
                            note="Line present in this period",
                        )
                    )
                claim.status, claim.status_rule = ClaimStatus.CONTRADICTED, "expense_recurs_across_periods"
                claim.status_rationale = (
                    f"The expense described as one-time appears in {n} consecutive periods "
                    f"({', '.join(metric.input_snapshot.get('periods', []))}) in "
                    f"{_source_names(metric.evidence_ids, doc_of_evidence) or 'the financial statements'}."
                )
            else:
                claim.status, claim.status_rule, claim.status_rationale = (
                    ClaimStatus.REVIEW_REQUIRED,
                    "insufficient_history",
                    "Only one period is available to test recurrence.",
                )
        elif metric is not None and comparator == "forward" and claim.claimed_value is not None and metric.value is not None:
            claim.verified_metric_id = metric.id
            claim.verified_value, claim.verified_unit = metric.value, metric.unit
            claim.status, claim.status_rule = ClaimStatus.UNSUPPORTED, "forward_assumption_exceeds_history"
            claim.status_rationale = (
                f"No document supports a forward growth rate of {_fmt(claim.claimed_value, 'pct')}; historical {metric.label} "
                f"calculated from {_source_names(metric.evidence_ids, doc_of_evidence) or 'the statements'} is {_fmt(metric.value, 'pct')}."
            )
        else:
            candidates_src = [(e, d) for e, d in primary_chunks if d.id != claim.document_id]
            if not candidates_src:
                claim.status, claim.status_rule, claim.status_rationale = (
                    ClaimStatus.UNSUPPORTED,
                    "no_primary_sources",
                    "No primary-source documents are available to test this statement.",
                )
            else:
                retriever = LexicalRetriever([e.text for e, _ in candidates_src])
                hits = {h.index for h in retriever.search(claim.claim_text, top_k=10)}
                if claim.claim_type == ClaimType.CONTRACT_TERM:
                    kw = re.compile(r"initial term|terminat|renew|contract_end", re.I)
                    name = _customer_name(claim.claim_text)
                    for i, (e, d) in enumerate(candidates_src):
                        if (
                            d.doc_type == DocumentType.CUSTOMER_CONTRACT
                            and kw.search(e.text)
                            and (not name or name.lower() in " ".join(x.text for x in ev[d.id][:3]).lower())
                        ):
                            hits.add(i)
                        if e.kind == EvidenceKind.CSV_ROW and "contract_end=" in e.text:
                            years = set(re.findall(r"20\d{2}", claim.claim_text))
                            title = " ".join(x.text for x in ev[claim.document_id][:3]).lower()
                            row_name = re.search(r"customer_name=([^;]+)", e.text)
                            if (name and name.lower() in e.text.lower()) or (
                                row_name and row_name.group(1).strip().lower() in title and years
                            ):
                                hits.add(i)
                if claim.claim_type == ClaimType.CONTRACT_TERM:
                    # Only customer-file rows about this contract's counterparty can corroborate a contract term.
                    title = " ".join(x.text for x in ev[claim.document_id][:3]).lower() + " " + claim.claim_text.lower()
                    keep: set[int] = set()
                    for i in hits:
                        e = candidates_src[i][0]
                        if e.kind != EvidenceKind.CSV_ROW:
                            keep.add(i)
                            continue
                        row_name = re.search(r"customer_name=([^;]+)", e.text)
                        if row_name and row_name.group(1).strip().lower() in title:
                            keep.add(i)
                    hits = keep
                candidates = [
                    ChunkRef(
                        i,
                        candidates_src[i][0].kind.value,
                        candidates_src[i][0].locator,
                        candidates_src[i][0].text,
                        candidates_src[i][1].doc_type.value,
                        candidates_src[i][1].display_name,
                    )
                    for i in sorted(hits)
                ]
                ctx = ClaimContext(
                    claim.claim_text,
                    claim.claim_type.value,
                    str(claim.claimed_value) if claim.claimed_value is not None else None,
                    claim.claimed_unit.value,
                    claim.period_label,
                    doc_by_id[claim.document_id].doc_type.value,
                )
                res = provider.verify_claim(ctx, candidates)
                run = _run(db, deal, None, RunType.VERIFY, provider, res)
                claim.verification_run_id = run.id
                if not res.ok or res.output is None:
                    claim.status, claim.status_rule, claim.status_rationale = (
                        ClaimStatus.REVIEW_REQUIRED,
                        "provider_failure",
                        f"Verification did not complete ({res.error}); a reviewer must assess this claim.",
                    )
                else:
                    out = res.output
                    valid = [j for j in out.evidence if j.chunk_index < len(candidates_src)]
                    sup = sum(1 for j in valid if j.role == "supporting")
                    con = sum(1 for j in valid if j.role == "contradicting")
                    g = apply_guardrails(out.status, sup, con, out.confidence)
                    seen: set[tuple[uuid.UUID, str]] = set()
                    for j in valid:
                        e = candidates_src[j.chunk_index][0]
                        if (e.id, j.role) in seen:
                            continue
                        seen.add((e.id, j.role))
                        db.add(ClaimEvidenceLink(claim_id=claim.id, evidence_id=e.id, role=LinkRole(j.role), note=j.note[:300]))
                    claim.status, claim.status_rule = ClaimStatus(g.status), g.rule
                    claim.status_rationale = (out.rationale + (" " + g.rationale_suffix if g.rationale_suffix else "")).strip()
        db.flush()


def _customer_name(text: str) -> str | None:
    m = re.search(r"The ([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+){0,3}) (?:master service agreement|agreement)", text)
    return m.group(1) if m else None


def _fmt(v: Decimal | None, unit: str) -> str:
    """Reader-facing number in the claim's unit; shared engine formatter, never Decimal repr."""
    return format_value(v, unit)


def _source_names(evidence_ids: list[Any], doc_of_evidence: dict[uuid.UUID, Document], limit: int = 2) -> str:
    """Display names of the documents behind a list of evidence ids ("a.xlsx and b.csv"), or ""."""
    names: list[str] = []
    for eid in evidence_ids:
        try:
            doc = doc_of_evidence.get(uuid.UUID(str(eid)))
        except ValueError:
            doc = None
        if doc is not None and doc.display_name not in names:
            names.append(doc.display_name)
        if len(names) == limit:
            break
    return " and ".join(names)


def gist(text: str, limit: int = 100) -> str:
    """Seller text shortened for a title: a model row 'label | value' reads as 'label of value', the
    trailing period goes, and a long sentence is cut at a word boundary with an ellipsis."""
    t = re.sub(r"\s+", " ", text).strip()
    t = re.sub(r"\s*\|\s*", " of ", t, count=1) if t.count("|") == 1 else t.replace(" | ", ", ")
    t = t.rstrip(".")
    if len(t) <= limit:
        return t
    return t[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


# ---------- findings ------------------------------------------------------------------------

MISSING_CHECKLIST = [
    ("quality of earnings", "Quality of earnings report", "Needed to validate the seller add-back schedule and reported EBITDA."),
    (
        "aging",
        "Accounts receivable aging",
        "Required to assess working-capital assumptions and the collectability of the largest customer balance.",
    ),
    ("tax return", "Tax returns", "Needed to reconcile reported net income to filed returns."),
]


CLAIM_TYPE_LABELS: dict[ClaimType, str] = {
    ClaimType.REVENUE: "revenue claim",
    ClaimType.REVENUE_GROWTH: "growth claim",
    ClaimType.CUSTOMER_CONCENTRATION: "customer concentration claim",
    ClaimType.RECURRING_REVENUE: "recurring revenue claim",
    ClaimType.CHURN: "churn claim",
    ClaimType.ADJUSTED_EBITDA: "adjusted EBITDA claim",
    ClaimType.ADDBACK: "add-back",
    ClaimType.GROSS_MARGIN: "gross margin claim",
    ClaimType.OPERATING_MARGIN: "operating margin claim",
    ClaimType.MARGIN_IMPROVEMENT: "margin improvement",
    ClaimType.FORECAST: "forecast",
    ClaimType.CONTRACT_TERM: "contract term",
    ClaimType.DEBT_TERM: "debt term",
    ClaimType.ONE_TIME_EXPENSE: "one-time expense",
}

# What a contradicted claim means for the buyer, in plain words. The title already carries the
# numbers, so these sentences never repeat them.
CONTRADICTION_MEANING: dict[ClaimType, str] = {
    ClaimType.REVENUE_GROWTH: (
        "Growth slower than presented means the forecast, and any price built on it, rests on a weaker trend than the seller describes."
    ),
    ClaimType.ADJUSTED_EBITDA: (
        "The seller's earnings figure includes add-backs the statements do not support, so a price set as a multiple of that figure would be too high."
    ),
    ClaimType.CUSTOMER_CONCENTRATION: (
        "Relying on one customer for a large share of revenue puts cash flow at risk if that customer leaves; the downside scenarios model that loss."
    ),
    ClaimType.RECURRING_REVENUE: (
        "Less revenue is locked in by contract than presented, so future cash flow is less predictable than the seller suggests."
    ),
    ClaimType.ADDBACK: "A cost that repeats every year is a normal running cost, not a one-off, and should not be added back to earnings.",
    ClaimType.ONE_TIME_EXPENSE: (
        "A cost that repeats every year is a normal running cost, not a one-off, and should not be added back to earnings."
    ),
    ClaimType.REVENUE: "The revenue in the seller's summary does not match the statements; ask which figure the price is based on.",
    ClaimType.GROSS_MARGIN: (
        "The margin in the seller's summary does not match the statements, which changes how much cash the business keeps from each sale."
    ),
    ClaimType.OPERATING_MARGIN: (
        "The margin in the seller's summary does not match the statements, which changes how much cash the business keeps from each sale."
    ),
    ClaimType.CHURN: "More customers leave each year than presented, so revenue has to be replaced faster than the seller suggests.",
    ClaimType.FORECAST: "The forecast is inconsistent with the documents provided; treat it as the seller's aspiration, not a basis for price.",
    ClaimType.MARGIN_IMPROVEMENT: (
        "The projected margin gains are inconsistent with the documents provided; do not pay for improvements that have not happened."
    ),
    ClaimType.CONTRACT_TERM: "The signed contract does not say what the seller's summary says it does; rely on the document, not the summary.",
    ClaimType.DEBT_TERM: "The financing terms differ from what was presented; recheck the debt payments and coverage in the scenarios.",
}
_CONTRADICTION_DEFAULT = (
    "The seller's figure differs from what the primary documents show; ask the seller to reconcile the two before relying on it."
)

# What an unsupported claim means for the buyer. Absence of evidence is not proof the claim is wrong.
UNSUPPORTED_MEANING: dict[ClaimType, str] = {
    ClaimType.CHURN: (
        "No document in the deal room supports this churn figure; a customer list with renewal history by year would let it be "
        "checked. Ask the seller for churn by year."
    ),
    ClaimType.FORECAST: (
        "A forecast with no pipeline, contracts, or plan behind it is the seller's expectation, not a fact; do not pay for it until "
        "the seller shows how it will be achieved."
    ),
    ClaimType.MARGIN_IMPROVEMENT: (
        "Margin gains that depend on future pricing or efficiency have not happened yet; price the business on the margins it earns today."
    ),
    ClaimType.ADDBACK: (
        "No statement line or contract supports this add-back. If it depends on what a buyer would do after closing, it is not part "
        "of historical earnings and should stay out of the price."
    ),
}
_UNSUPPORTED_DEFAULT = (
    "Nothing in the deal room backs this statement up; treat it as the seller's view until they provide support."
)


def _contradiction_title(c: Claim, metric: FinancialMetric | None, source: Document | None) -> str:
    """'Revenue CAGR is 11.6%, not the 18.0% in the CIM': the figure, the gap, and which seller document
    said it, so two claims about the same metric from different documents get distinct titles."""
    if c.status_rule == "expense_recurs_across_periods" and metric is not None and metric.value is not None:
        subject = metric.label.split(" recurrence")[0]
        return f"{subject} recurs across {format_plain(metric.value)} consecutive periods; it is not a one-time cost"
    if metric is not None and c.verified_value is not None and c.claimed_value is not None:
        verified = _fmt(c.verified_value, (c.verified_unit or c.claimed_unit).value)
        claimed = _fmt(c.claimed_value, c.claimed_unit.value)
        where = (
            f" in the {DOC_TYPE_LABELS.get(source.doc_type.value, source.doc_type.value.replace('_', ' '))}"
            if source is not None
            else " claimed"
        )
        if (c.normalized or {}).get("comparator") == "lte":
            return f"{metric.label} is {verified}, above the {claimed} ceiling{where}"
        return f"{metric.label} is {verified}, not the {claimed}{where}"
    return f"Contradicted: {gist(c.claim_text)}"


# Meanings that assume the seller's figure was the more favourable one. For these the sentence is used only
# when the numbers show that direction; an understated figure gets the neutral default instead.
_DIRECTIONAL = {
    ClaimType.REVENUE_GROWTH,
    ClaimType.ADJUSTED_EBITDA,
    ClaimType.RECURRING_REVENUE,
    ClaimType.CHURN,
    ClaimType.CUSTOMER_CONCENTRATION,
    ClaimType.MARGIN_IMPROVEMENT,
}
_LOWER_IS_FAVOURABLE = {ClaimType.CHURN, ClaimType.CUSTOMER_CONCENTRATION}


def _seller_overstated(c: Claim) -> bool | None:
    """True when the seller's figure is the more flattering one, None when the values are missing."""
    if c.claimed_value is None or c.verified_value is None:
        return None
    if (c.normalized or {}).get("comparator") == "lte":
        return True  # the documents exceed a ceiling the seller promised
    diff = c.claimed_value - c.verified_value
    return diff < 0 if c.claim_type in _LOWER_IS_FAVOURABLE else diff > 0


def _contradiction_detail(c: Claim, sources: str) -> str:
    meaning = CONTRADICTION_MEANING.get(c.claim_type, _CONTRADICTION_DEFAULT)
    if c.claim_type in _DIRECTIONAL and _seller_overstated(c) is not True:
        meaning = _CONTRADICTION_DEFAULT
    return f"{meaning} Checked against {sources}." if sources else meaning


def _unsupported_title(c: Claim, metric: FinancialMetric | None) -> str:
    if c.status_rule == "forward_assumption_exceeds_history" and c.verified_value is not None and c.claimed_value is not None:
        claimed = _fmt(c.claimed_value, c.claimed_unit.value)
        verified = _fmt(c.verified_value, (c.verified_unit or c.claimed_unit).value)
        return f"Model assumes {claimed} growth; history shows {verified}"
    return f"Unsupported {CLAIM_TYPE_LABELS.get(c.claim_type, 'claim')}: \u201c{gist(c.claim_text, 90)}\u201d"


def _unsupported_detail(c: Claim, source_name: str, history_sources: str) -> str:
    if c.status_rule == "forward_assumption_exceeds_history":
        faster = c.claimed_value is not None and c.verified_value is not None and c.claimed_value > c.verified_value
        text = (
            "The projections in the acquisition model, and any price derived from them, assume faster growth than the company "
            "has achieved. Ask what supports the step-up."
            if faster
            else "The growth rate in the acquisition model is an assumption, not a documented result; ask what supports it."
        )
        history = f"; history from {history_sources}" if history_sources else ""
        return f"{text} Stated in {source_name}{history}."
    return f"{UNSUPPORTED_MEANING.get(c.claim_type, _UNSUPPORTED_DEFAULT)} Stated in {source_name}."


def _share_words(pct: Decimal) -> str:
    if pct >= 55:
        return "More than half"
    if pct >= 45:
        return "About half"
    if pct >= 28:
        return "Roughly a third"
    if pct >= 22:
        return "Roughly a quarter"
    if pct >= 17:
        return "Roughly a fifth"
    return "A sizeable share"


def build_findings(db: Session, deal: Deal, docs: list[Document], ev: dict[uuid.UUID, list[Evidence]]) -> None:
    """Findings are the reader's entry point: the title says what is wrong (with formatted figures), the
    detail says what it means for the buyer and names the document it was checked against. Ids stay in
    evidence_ids and metric_ids, never in the text."""
    doc_by_id = {d.id: d for d in docs}
    doc_of_evidence = {e.id: doc_by_id[d] for d in ev for e in ev[d] if d in doc_by_id}
    metric_by_id = {m.id: m for m in db.scalars(select(FinancialMetric).where(FinancialMetric.deal_id == deal.id))}
    cim_doc = next((d for d in docs if d.doc_type == DocumentType.CIM), None)

    def add(
        key: str,
        kind: FindingKind,
        sev: Severity,
        title: str,
        detail: str,
        evidence: list[Any] | None = None,
        metrics: list[Any] | None = None,
        claim_id: uuid.UUID | None = None,
    ) -> None:
        db.add(
            Finding(
                deal_id=deal.id,
                claim_id=claim_id,
                key=key,
                kind=kind,
                severity=sev,
                title=title[:255],
                detail=detail,
                evidence_ids=[str(e) for e in (evidence or [])][:10],
                metric_ids=[str(m) for m in (metrics or [])],
                status=FindingStatus.OPEN,
            )
        )

    high = {ClaimType.REVENUE_GROWTH, ClaimType.ADJUSTED_EBITDA, ClaimType.CUSTOMER_CONCENTRATION, ClaimType.RECURRING_REVENUE}
    for c in db.scalars(select(Claim).where(Claim.deal_id == deal.id)):
        con = [link.evidence_id for link in c.links if link.role == LinkRole.CONTRADICTING]
        metric = metric_by_id.get(c.verified_metric_id) if c.verified_metric_id else None
        source_doc = doc_by_id.get(c.document_id)
        source_name = source_doc.display_name if source_doc else "the seller's document"
        history = _source_names(metric.evidence_ids, doc_of_evidence) if metric is not None else ""
        if c.status == ClaimStatus.CONTRADICTED:
            add(
                f"contradiction:{c.key}",
                FindingKind.CONTRADICTION,
                Severity.HIGH if c.claim_type in high else Severity.MEDIUM,
                _contradiction_title(c, metric, source_doc),
                _contradiction_detail(c, _source_names(con, doc_of_evidence) or history),
                con,
                [c.verified_metric_id] if c.verified_metric_id else [],
                c.id,
            )
        elif c.status == ClaimStatus.UNSUPPORTED and c.claim_type in {
            ClaimType.FORECAST,
            ClaimType.MARGIN_IMPROVEMENT,
            ClaimType.ADDBACK,
            ClaimType.CHURN,
        }:
            add(
                f"unsupported:{c.key}",
                FindingKind.UNSUPPORTED_ASSUMPTION,
                Severity.MEDIUM,
                _unsupported_title(c, metric),
                _unsupported_detail(c, source_name, history),
                [c.source_evidence_id] if c.source_evidence_id else [],
                [c.verified_metric_id] if c.verified_metric_id else [],
                c.id,
            )
    top = _metric(db, deal, "customer_concentration_top1")
    top_name = top.input_snapshot.get("top_customer_name") if top else None
    if top and top.value is not None and top.value > 15:
        snap = top.input_snapshot
        source = _source_names(top.evidence_ids, doc_of_evidence) or "the customer revenue file"
        add(
            "concentration:top1",
            FindingKind.CONCENTRATION,
            Severity.HIGH,
            f"{top_name or 'The largest customer'} is {_fmt(top.value, 'pct')} of revenue",
            f"{_share_words(top.value)} of revenue comes from a single customer "
            f"({_fmt(D(snap.get('top_customer_revenue')), 'usd')} of {_fmt(D(snap.get('total_revenue')), 'usd')}), according to {source}. "
            "If that customer leaves, the cash available for debt payments falls sharply; the downside scenarios model that loss.",
            [uuid.UUID(x) for x in top.evidence_ids],
            [top.id],
        )
    notice_re = re.compile(r"((?:[A-Za-z]+|\d+)(?:\s*\(\d+\))?\s+days'?(?:\s+(?:prior|written|advance))*\s+notice)", re.I)
    for doc in docs:
        for e in ev.get(doc.id, []):
            if doc.doc_type == DocumentType.CUSTOMER_CONTRACT and re.search(r"terminat\w+ .*for convenience", e.text, re.I):
                who = (
                    top_name
                    if top_name and top_name.lower() in " ".join(x.text for x in ev[doc.id][:3]).lower()
                    else "a customer"
                )
                notice = notice_re.search(e.text)
                when = notice.group(1) if notice else "notice"
                penalty = " and without penalty" if re.search(r"without (?:any )?penalty|no penalty", e.text, re.I) else ""
                add(
                    f"risk:termination:{doc.id}",
                    FindingKind.RISK,
                    Severity.HIGH if who == top_name else Severity.MEDIUM,
                    f"{who[0].upper() + who[1:]} can end its contract early without cause",
                    f"The agreement lets the customer cancel on {when}{penalty} (termination for convenience), so this "
                    f"revenue is not locked in for the stated term. Clause in {doc.display_name}: \u201c{gist(e.text, 160)}\u201d",
                    [e.id],
                )
            if e.contains_instruction_text:
                page = e.locator.get("page")
                where = f"Page {page} of {doc.display_name}" if page else doc.display_name
                add(
                    f"integrity:{e.id}",
                    FindingKind.DOCUMENT_INTEGRITY,
                    Severity.LOW,
                    f"Text addressed to automated readers in {doc.display_name}",
                    f"{where} contains wording aimed at software rather than a reader: \u201c{gist(e.text, 160)}\u201d. BearCase treats "
                    "document text as data only, so it changed no result; it is worth asking the seller why it is there.",
                    [e.id],
                )
    names = " ".join(d.display_name.lower() for d in docs)
    cim_text = " ".join(e.text.lower() for d in docs if d.doc_type == DocumentType.CIM for e in ev.get(d.id, []))
    for kw, title, reason in MISSING_CHECKLIST:
        if kw.replace(" ", "") in names.replace(" ", "").replace("-", "") or kw in names:
            continue
        referenced = kw in cim_text
        cim_name = f" ({cim_doc.display_name})" if cim_doc else ""
        detail = reason + (f" The CIM{cim_name} refers to it but it was not provided." if referenced else "")
        add(
            f"missing:{kw}",
            FindingKind.MISSING_DOCUMENT,
            Severity.MEDIUM if referenced else Severity.LOW,
            f"Missing: {title}",
            detail,
        )
    db.flush()


# ---------- scenarios -----------------------------------------------------------------------


def scenario_facts(db: Session, deal: Deal) -> tuple[dict[str, Any], list[str]]:
    ordered = list(
        db.scalars(select(FinancialPeriod).where(FinancialPeriod.deal_id == deal.id).order_by(FinancialPeriod.ordinal))
    )
    missing: list[str] = []
    latest = ordered[-1] if ordered else None
    if latest is None:
        return {}, ["financial statements (no periods mapped)"]

    def val(key: str) -> Decimal | None:
        m = _metric(db, deal, key, latest)
        return m.value if m else None

    revenue = val("revenue")
    gm = val("gross_margin")
    labor = sum((val(k) or Decimal(0) for k in LABOR_LINE_KEYS), Decimal(0))
    opex = val("operating_expenses")
    da = (val("depreciation") or Decimal(0)) + (val("amortization") or Decimal(0))
    verified = _metric(db, deal, "ebitda_adjusted_verified")
    top = _metric(db, deal, "customer_concentration_top1")
    for name, v in [("revenue", revenue), ("gross_margin", gm), ("operating_expenses", opex)]:
        if v is None:
            missing.append(name)
    if verified is None or verified.value in (None, 0):
        missing.append("verified adjusted EBITDA")
    if missing:
        return {}, missing
    ev_calc = f.enterprise_value(deal.purchase_price, deal.purchase_price_basis.value, deal.debt_assumed, deal.cash_acquired)
    facts = {
        "base_revenue": revenue,
        "largest_customer_revenue": D(top.input_snapshot.get("top_customer_revenue")) if top else Decimal(0),
        "gross_margin_pct": gm,
        "labor_opex": labor,
        "other_opex": opex - labor,  # type: ignore[operator]
        "depreciation_amortization": da,
        "amortization_years": deal.amortization_years,
        "payments_per_year": deal.payments_per_year,
        "covenant_dscr_threshold": deal.covenant_dscr_threshold,
        "exit_multiple": f.ev_to_ebitda(ev_calc.value, verified.value).value,  # type: ignore[union-attr]
        "hold_years": 5,
    }
    return facts, []


def default_assumptions(db: Session, deal: Deal, kind: ScenarioKind) -> dict[str, Decimal]:
    accepted = sum(
        (
            a.amount
            for a in db.scalars(select(Adjustment).where(Adjustment.deal_id == deal.id))
            if a.decision == AdjustmentDecision.ACCEPTED
        ),
        Decimal(0),
    )
    latest_rev = _metric(db, deal, "revenue")
    capex = (
        (latest_rev.value * Decimal("0.015")).quantize(Decimal("1000")) if latest_rev and latest_rev.value else Decimal("100000")
    )
    ev_calc = f.enterprise_value(deal.purchase_price, deal.purchase_price_basis.value, deal.debt_assumed, deal.cash_acquired)
    debt_pct = (deal.debt_amount / ev_calc.value * 100).quantize(Decimal("0.1")) if ev_calc.value else Decimal("50")
    base = {
        "revenue_growth_pct": Decimal("3.0"),
        "largest_customer_loss_pct": Decimal("0"),
        "gross_margin_change_bps": Decimal("0"),
        "labor_cost_growth_pct": Decimal("3.0"),
        "other_opex_growth_pct": Decimal("2.0"),
        "interest_rate_pct": deal.interest_rate_pct,
        "purchase_price": ev_calc.value or deal.purchase_price,
        "debt_pct": debt_pct,
        "accepted_addbacks": accepted,
        "cash_tax_rate_pct": Decimal("21"),
        "maintenance_capex": capex,
        "nwc_pct_of_revenue_change": Decimal("8"),
    }
    if kind == ScenarioKind.DOWNSIDE:
        base.update(
            {
                "revenue_growth_pct": Decimal("0"),
                "largest_customer_loss_pct": Decimal("25"),
                "gross_margin_change_bps": Decimal("-100"),
                "labor_cost_growth_pct": Decimal("5.0"),
                "interest_rate_pct": deal.interest_rate_pct + Decimal("0.5"),
            }
        )
    elif kind == ScenarioKind.SEVERE_DOWNSIDE:
        base.update(
            {
                "revenue_growth_pct": Decimal("-5.0"),
                "largest_customer_loss_pct": Decimal("100"),
                "gross_margin_change_bps": Decimal("-300"),
                "labor_cost_growth_pct": Decimal("8.0"),
                "interest_rate_pct": deal.interest_rate_pct + Decimal("1.5"),
            }
        )
    return base


def ensure_scenarios(db: Session, deal: Deal) -> list[Scenario]:
    from bearcase.engine.scenarios import ASSUMPTION_SPECS

    existing = list(db.scalars(select(Scenario).where(Scenario.deal_id == deal.id).order_by(Scenario.sort_order)))
    if existing:
        return existing
    out = []
    for i, (kind, name, desc) in enumerate(
        [
            (ScenarioKind.BASE, "Base", "Verified run-rate with modest growth and accepted add-backs only."),
            (
                ScenarioKind.DOWNSIDE,
                "Downside",
                "Flat revenue, partial loss of the largest customer, margin compression, higher labor and rate.",
            ),
            (
                ScenarioKind.SEVERE_DOWNSIDE,
                "Severe downside",
                "Loss of the largest customer, revenue decline, deeper margin compression, labor inflation, higher rate.",
            ),
        ]
    ):
        sc = Scenario(deal_id=deal.id, name=name, kind=kind, description=desc, is_seed=True, sort_order=i)
        db.add(sc)
        db.flush()
        for j, spec in enumerate(ASSUMPTION_SPECS):
            db.add(
                ScenarioAssumption(
                    scenario_id=sc.id,
                    key=spec["key"],
                    label=spec["label"],
                    value=default_assumptions(db, deal, kind)[spec["key"]],
                    unit=ClaimUnit(spec["unit"]),
                    sort_order=j,
                )
            )
        out.append(sc)
    db.flush()
    return out


def run_scenario(db: Session, deal: Deal, scenario: Scenario, user_id: uuid.UUID | None) -> ScenarioResult:
    facts, missing = scenario_facts(db, deal)
    if missing:
        raise ValueError("Scenario inputs missing: " + ", ".join(missing))
    kwargs: dict[str, Any] = {**facts, **{a.key: a.value for a in scenario.assumptions}}
    inp = ScenarioInputs(**kwargs)
    out = project(inp)
    run_no = (
        db.scalar(
            select(ScenarioResult.run_no).where(ScenarioResult.scenario_id == scenario.id).order_by(ScenarioResult.run_no.desc())
        )
        or 0
    ) + 1
    result = ScenarioResult(
        scenario_id=scenario.id,
        run_no=run_no,
        engine_version=ENGINE_VERSION,
        input_snapshot=inp.snapshot(),
        outputs=out.to_dict(),
        warnings=out.warnings,
        input_hash=inp.hash(),
        run_by_user_id=user_id,
    )
    db.add(result)
    db.flush()
    record(
        db,
        deal_id=deal.id,
        user_id=user_id,
        event_type="scenario.run",
        object_type="scenario_result",
        object_id=result.id,
        summary=f"Ran scenario '{scenario.name}' (run {run_no}); year-1 DSCR {format_multiple(out.dscr) if out.dscr is not None else 'n/a'}",
        payload={"scenario_id": str(scenario.id), "input_hash": inp.hash(), "warnings": [w["code"] for w in out.warnings]},
    )
    return result


def record_scenario_metrics(db: Session, deal: Deal, results: dict[ScenarioKind, ScenarioResult]) -> None:
    base = results.get(ScenarioKind.BASE)
    if base:
        y1 = base.outputs["year1"]
        calcs = base.outputs.get("calcs", {})
        put_metric(
            db,
            deal,
            key="cfads_base",
            label="CFADS (base case, year 1)",
            value=D(y1["cfads"]),
            unit="usd",
            source=MetricSource.SCENARIO,
            formula=calcs.get("cfads", {}).get("formula"),
            input_snapshot={
                "scenario_result_id": str(base.id),
                "bridge": base.outputs["cfads_bridge"],
                "input_hash": base.input_hash,
            },
        )
        put_metric(
            db,
            deal,
            key="dscr_base",
            label="DSCR (base case, year 1)",
            value=D(y1["dscr"]) if y1.get("dscr") else None,
            unit="multiple",
            source=MetricSource.SCENARIO,
            formula=calcs.get("dscr", {}).get("formula"),
            input_snapshot={"scenario_result_id": str(base.id), "input_hash": base.input_hash},
            requires_review=y1.get("dscr") is None,
        )
        put_metric(
            db,
            deal,
            key="cash_on_cash_base",
            label="Cash-on-cash return (base, year 1)",
            value=D(base.outputs.get("cash_on_cash_pct")),
            unit="pct",
            source=MetricSource.SCENARIO,
            input_snapshot={"scenario_result_id": str(base.id)},
        )
        put_metric(
            db,
            deal,
            key="irr_base",
            label="Equity IRR (base, 5-year)",
            value=D(base.outputs.get("irr_pct")),
            unit="pct",
            source=MetricSource.SCENARIO,
            input_snapshot={"scenario_result_id": str(base.id), "method": "periodic IRR"},
            requires_review=base.outputs.get("irr_pct") is None,
        )
    debt_doc = db.scalar(select(Document).where(Document.deal_id == deal.id, Document.doc_type == DocumentType.DEBT_TERM_SHEET))
    threshold = (
        _fmt(deal.covenant_dscr_threshold, "multiple") if deal.covenant_dscr_threshold is not None else "the lender's minimum"
    )
    # The threshold is entered on the deal form; the term sheet only confirms it when a supported debt-term claim says so.
    confirmed = (
        db.scalar(
            select(Claim).where(
                Claim.deal_id == deal.id,
                Claim.claim_type == ClaimType.DEBT_TERM,
                Claim.status == ClaimStatus.SUPPORTED,
                (Claim.claim_text.ilike("%coverage%") | Claim.claim_text.ilike("%DSCR%")),
            )
        )
        if debt_doc
        else None
    )
    set_in = (
        f", entered in the deal terms and confirmed in {debt_doc.display_name}"
        if confirmed and debt_doc
        else ", entered in the deal terms"
    )
    for kind, res in results.items():
        dscr_m = _metric(db, deal, "dscr_base")
        name = res.scenario.name if res.scenario is not None else kind.value.replace("_", " ").capitalize()
        for w in res.warnings:
            if w["code"] in ("covenant_breach", "covenant_warning") and w.get("year") == 1:
                breach = w["code"] == "covenant_breach"
                sev = (
                    Severity.CRITICAL
                    if (breach and kind == ScenarioKind.DOWNSIDE)
                    else Severity.HIGH
                    if breach
                    else Severity.MEDIUM
                )
                raw = res.outputs.get("year1", {}).get("dscr")
                dscr = _fmt(D(raw), "multiple") if raw is not None else "n/a"
                title = (
                    f"{name} scenario breaks the debt coverage covenant ({dscr} against {threshold})"
                    if breach
                    else f"{name} scenario is close to the debt coverage covenant ({dscr} against {threshold})"
                )
                consequence = (
                    "Below the minimum the lender can call a default, demand more equity, or block distributions to the owner."
                    if breach
                    else "The cushion is thin: a small shortfall in cash flow would put the loan in breach."
                )
                db.add(
                    Finding(
                        deal_id=deal.id,
                        key=f"covenant:{kind.value}",
                        kind=FindingKind.COVENANT_WARNING,
                        severity=sev,
                        title=title[:255],
                        detail=(
                            f"In the {name.lower()} scenario (run {res.run_no}), year-one cash available for debt payments covers "
                            f"the payments due {dscr}; the lender's minimum is {threshold}{set_in}. {consequence} "
                            "The run keeps every input it used, so it can be reopened and compared."
                        ),
                        evidence_ids=[],
                        metric_ids=[str(dscr_m.id)] if dscr_m else [],
                        status=FindingStatus.OPEN,
                    )
                )
                break
    db.flush()


# ---------- orchestration -------------------------------------------------------------------


def load_evidence(db: Session, deal: Deal) -> tuple[list[Document], dict[uuid.UUID, list[Evidence]]]:
    docs = list(
        db.scalars(
            select(Document)
            .where(Document.deal_id == deal.id, Document.status == DocumentStatus.READY)
            .order_by(Document.created_at)
        )
    )
    ev: dict[uuid.UUID, list[Evidence]] = {}
    for d in docs:
        ev[d.id] = list(
            db.scalars(
                select(Evidence)
                .where(Evidence.document_id == d.id, Evidence.kind != EvidenceKind.CSV_AGGREGATE)
                .order_by(Evidence.chunk_index)
            )
        )
    return docs, ev


def analyze_deal(db: Session, job: ProcessingJob, jl: JobLog, provider: AIProvider | None = None) -> None:
    provider = provider or get_provider()
    deal = db.get(Deal, job.deal_id)
    if deal is None:
        raise ValueError("deal not found")
    deal.status = DealStatus.PROCESSING
    jl.step("Loading evidence", 5)
    _clear_analysis(db, deal)
    docs, ev = load_evidence(db, deal)
    if not docs:
        raise ValueError("No processed documents. Upload and process documents before analysis.")
    jl.step("Mapping financial statements", 15)
    periods = build_statement_metrics(db, deal, docs, ev)
    ordered = sorted(periods.values(), key=lambda p: p.ordinal)
    latest = ordered[-1] if ordered else None
    jl.step("Aggregating customer revenue", 25)
    build_customer_metrics(db, deal, docs, ev, latest)
    jl.step("Reviewing seller adjustments", 35)
    build_model_metrics_and_adjustments(db, deal, docs, ev, latest)
    review_adjustments(db, deal, periods)
    jl.step("Calculating verified metrics", 45)
    build_deal_metrics(db, deal, periods)
    jl.step(f"Extracting claims ({provider.name})", 55)
    extract_claims(db, deal, docs, ev, provider, jl)
    jl.step("Verifying claims", 70)
    verify_claims(db, deal, docs, ev, provider, periods)
    jl.step("Running scenarios", 85)
    results: dict[ScenarioKind, ScenarioResult] = {}
    scenario_error: str | None = None
    try:
        for sc in ensure_scenarios(db, deal):
            results[sc.kind] = run_scenario(db, deal, sc, None)
        record_scenario_metrics(db, deal, results)
    except ValueError as exc:
        scenario_error = str(exc)
    jl.step("Recording findings", 92, scenario_error=scenario_error)
    build_findings(db, deal, docs, ev)
    deal.status = DealStatus.VERIFIED
    record(
        db,
        deal_id=deal.id,
        event_type="deal.analyzed",
        object_type="deal",
        object_id=deal.id,
        summary=f"Analysis completed with {provider.name}/{provider.model}",
        payload={"documents": len(docs), "scenario_error": scenario_error, "job_id": str(job.id)},
    )
    db.commit()


def generate_report(
    db: Session, job: ProcessingJob, jl: JobLog, provider: AIProvider | None = None, user_id: uuid.UUID | None = None
) -> None:
    provider = provider or get_provider()
    deal = db.get(Deal, job.deal_id)
    if deal is None:
        raise ValueError("deal not found")
    jl.step("Assembling report", 30)
    report = assemble_report(db, deal, provider, user_id)
    jl.step("Validating citations", 80, valid=report.validation.get("valid"))
    if report.status == ReportStatus.VALIDATED:
        deal.status = DealStatus.REPORTED
    record(
        db,
        deal_id=deal.id,
        user_id=user_id,
        event_type="report.generated",
        object_type="report",
        object_id=report.id,
        summary=f"Report v{report.version_no} {report.status.value} ({report.validation.get('material_cited', 0)}/{report.validation.get('material_statements', 0)} material statements cited)",
        payload={"outcome": report.outcome.value, "job_id": str(job.id)},
    )
    db.commit()
