from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from bearcase.api.deps import DbDep, DealDep, EditorDealDep, UserDep
from bearcase.api.schemas import AdjustmentDecisionRequest, AdjustmentOut, FinancialsOut, MetricOut, PeriodOut, WaterfallStep
from bearcase.audit import record
from bearcase.chat.brief import invalidate_brief
from bearcase.engine import formulas as f
from bearcase.ingest.statement_mapper import SYNONYMS, map_income_statement, period_year
from bearcase.models import Adjustment, Claim, Document, Evidence, FinancialMetric, FinancialPeriod
from bearcase.models.enums import AdjustmentDecision, AdjustmentDirection, ClaimStatus, DocumentStatus, DocumentType, EvidenceKind, MetricSource
from bearcase.pipeline.analyze import _chunks_from_evidence

router = APIRouter(tags=["financials"])


def _waterfall(reported: Decimal | None, adjustments: list[Adjustment]) -> list[WaterfallStep]:
    if reported is None:
        return []
    steps = [WaterfallStep(label="Reported EBITDA", amount=reported, decision="reported", included=True, running_total=reported)]
    total = reported
    for a in sorted(adjustments, key=lambda x: x.sort_order):
        included = a.decision == AdjustmentDecision.ACCEPTED
        signed = a.amount if a.direction == AdjustmentDirection.ADD_BACK else -a.amount
        if included:
            total += signed
        steps.append(
            WaterfallStep(
                label=a.label,
                amount=signed,
                decision=a.decision.value,
                included=included,
                running_total=total,
                adjustment_id=a.id,
            )
        )
    steps.append(
        WaterfallStep(label="Checked adjusted EBITDA", amount=total, decision="verified", included=True, running_total=total)
    )
    return steps


@router.get("/deals/{deal_id}/financials", response_model=FinancialsOut)
def get_financials(deal: DealDep, db: DbDep) -> FinancialsOut:
    periods = db.scalars(
        select(FinancialPeriod).where(FinancialPeriod.deal_id == deal.id).order_by(FinancialPeriod.ordinal)
    ).all()
    plabel = {p.id: p.label for p in periods}
    metrics = []
    for m in db.scalars(select(FinancialMetric).where(FinancialMetric.deal_id == deal.id).order_by(FinancialMetric.created_at)):
        mo = MetricOut.model_validate(m)
        mo.period_label = plabel.get(m.period_id) if m.period_id else None
        metrics.append(mo)
    adjustments = db.scalars(select(Adjustment).where(Adjustment.deal_id == deal.id).order_by(Adjustment.sort_order)).all()
    latest = periods[-1] if periods else None
    reported = db.scalar(
        select(FinancialMetric).where(
            FinancialMetric.deal_id == deal.id,
            FinancialMetric.key == "ebitda_reported",
            FinancialMetric.period_id == (latest.id if latest else None),
        )
    )
    return FinancialsOut(
        periods=[PeriodOut.model_validate(p) for p in periods],
        metrics=metrics,
        adjustments=[AdjustmentOut.model_validate(a) for a in adjustments],
        waterfall=_waterfall(reported.value if reported else None, list(adjustments)),
    )


@router.post("/deals/{deal_id}/adjustments/{adjustment_id}/decision", response_model=FinancialsOut)
def decide_adjustment(
    deal: EditorDealDep, adjustment_id: uuid.UUID, body: AdjustmentDecisionRequest, db: DbDep, user: UserDep
) -> FinancialsOut:
    """Human decision on an add-back. The rule-based decision stays in the audit payload; verified EBITDA is recomputed."""
    a = db.scalar(select(Adjustment).where(Adjustment.id == adjustment_id, Adjustment.deal_id == deal.id))
    if a is None:
        raise HTTPException(404, "Adjustment not found.")
    previous = {
        "decision": a.decision.value,
        "rationale": a.decision_rationale,
        "rule": a.decision_rule,
        "decided_by": str(a.decided_by_user_id) if a.decided_by_user_id else None,
    }
    a.decision = AdjustmentDecision(body.decision)
    a.decision_rationale = body.rationale
    a.decision_rule = "reviewer_decision"
    a.decided_by_user_id = user.id
    # recompute verified adjusted EBITDA and dependent multiples (new metric rows; old rows remain for history)
    adjustments = db.scalars(select(Adjustment).where(Adjustment.deal_id == deal.id)).all()
    reported = db.scalar(
        select(FinancialMetric)
        .where(
            FinancialMetric.deal_id == deal.id,
            FinancialMetric.key == "ebitda_reported",
            FinancialMetric.source == MetricSource.CALCULATED,
        )
        .order_by(FinancialMetric.created_at.desc())
    )
    if reported and reported.value is not None:
        from bearcase.pipeline.analyze import put_calc

        accepted = {
            x.label: x.amount
            for x in adjustments
            if x.decision == AdjustmentDecision.ACCEPTED and x.direction == AdjustmentDirection.ADD_BACK
        }
        downward = {
            x.label: x.amount
            for x in adjustments
            if x.decision == AdjustmentDecision.ACCEPTED and x.direction == AdjustmentDirection.DOWNWARD
        }
        for old in db.scalars(
            select(FinancialMetric).where(
                FinancialMetric.deal_id == deal.id,
                FinancialMetric.key.in_(["ebitda_adjusted_verified", "ev_to_ebitda_verified", "debt_to_ebitda_verified"]),
            )
        ):
            db.delete(old)
        db.flush()
        vm = put_calc(
            db,
            deal,
            f.adjusted_ebitda(reported.value, accepted, downward),
            evidence_ids=[uuid.UUID(x) for x in reported.evidence_ids]
            + [uuid.UUID(x) for y in adjustments if y.decision == AdjustmentDecision.ACCEPTED for x in y.evidence_ids],
            extra_snapshot={"decided_by": str(user.id), "reason": "reviewer adjustment decision"},
        )
        ev_calc = f.enterprise_value(deal.purchase_price, deal.purchase_price_basis.value, deal.debt_assumed, deal.cash_acquired)
        put_calc(
            db,
            deal,
            f.ev_to_ebitda(ev_calc.value, vm.value, key="ev_to_ebitda_verified"),
            evidence_ids=[uuid.UUID(x) for x in vm.evidence_ids][:6],
        )
        put_calc(
            db,
            deal,
            f.debt_to_ebitda(deal.debt_amount, vm.value, key="debt_to_ebitda_verified"),
            evidence_ids=[uuid.UUID(x) for x in vm.evidence_ids][:6],
        )
    record(
        db,
        deal_id=deal.id,
        user_id=user.id,
        event_type="adjustment.decided",
        object_type="adjustment",
        object_id=a.id,
        summary=f"{user.display_name} marked '{a.label}' as {body.decision}",
        payload={"previous": previous, "decision": body.decision, "rationale": body.rationale},
    )
    db.commit()
    invalidate_brief(deal.id)
    return get_financials(deal, db)


@router.get("/deals/{deal_id}/financials/mapping")
def statement_mapping(deal: DealDep, db: DbDep) -> dict[str, Any]:
    """"Check what we read": how each income-statement sheet was interpreted before anything was calculated, and what
    was not read at all. Re-runs the mapper over the persisted sheet rows (the same input the pipeline used), so the
    answer is the interpretation behind the stored metrics, with the cells to open. Nothing here is calculated by a
    model, and nothing is written."""
    statements: list[dict[str, Any]] = []
    unmapped_total = 0
    ambiguous_total = 0
    for doc in db.scalars(
        select(Document).where(Document.deal_id == deal.id, Document.doc_type == DocumentType.FINANCIAL_STATEMENTS)
    ):
        rows = db.scalars(
            select(Evidence)
            .where(Evidence.document_id == doc.id, Evidence.kind == EvidenceKind.SHEET_ROW)
            .order_by(Evidence.chunk_index)
        ).all()
        smap = map_income_statement(_chunks_from_evidence(rows))
        if smap is None:
            statements.append({"document_id": str(doc.id), "document_name": doc.display_name, "mapped": False, "reason": "No sheet named like an income statement with at least two year columns was found."})
            continue
        lines = []
        for key in SYNONYMS:
            cells = {}
            for period in smap.periods:
                mv = smap.lines[period].get(key)
                if mv is None:
                    continue
                cells[period] = {
                    "value": str(mv.value),
                    "raw": mv.raw,
                    "cell": mv.cell,
                    "confidence": mv.confidence,
                    "evidence_id": str(rows[mv.chunk_index].id) if mv.chunk_index < len(rows) else None,
                }
            if cells:
                lines.append({"key": key, "cells": cells, "components": smap.ambiguous.get(key), "needs_review": key in smap.ambiguous or any(c["confidence"] < 0.8 for c in cells.values())})
        unmapped_total += len(smap.unmapped_rows)
        ambiguous_total += len(smap.ambiguous)
        statements.append({
            "document_id": str(doc.id),
            "document_name": doc.display_name,
            "mapped": True,
            "sheet": smap.sheet,
            "header_row": smap.header_row,
            "scale": smap.scale,
            "currency": "USD (assumed; the sheet states no currency)" if smap.scale == 1 else "USD (assumed)",
            "periods": [{"label": p, "year": period_year(p)} for p in smap.periods],
            "lines": lines,
            "unmapped_rows": smap.unmapped_rows,
        })
    docs = db.scalars(select(Document).where(Document.deal_id == deal.id)).all()
    review_metrics = db.scalar(
        select(func.count(FinancialMetric.id)).where(FinancialMetric.deal_id == deal.id, FinancialMetric.requires_review.is_(True))
    ) or 0
    claims_by_status = {
        status.value: (db.scalar(select(func.count(Claim.id)).where(Claim.deal_id == deal.id, Claim.status == status)) or 0)
        for status in ClaimStatus
    }
    coverage = {
        "documents_ready": sum(1 for d in docs if d.status == DocumentStatus.READY),
        "documents_failed": sum(1 for d in docs if d.status == DocumentStatus.FAILED),
        "documents_pending": sum(1 for d in docs if d.status not in (DocumentStatus.READY, DocumentStatus.FAILED)),
        "statements_mapped": sum(1 for s in statements if s["mapped"]),
        "statements_unmapped": sum(1 for s in statements if not s["mapped"]),
        "unmapped_rows": unmapped_total,
        "ambiguous_lines": ambiguous_total,
        "metrics_requiring_review": int(review_metrics),
        "claims_by_status": claims_by_status,
    }
    return {"statements": statements, "coverage": coverage}
