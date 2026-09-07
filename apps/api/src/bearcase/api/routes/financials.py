from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from bearcase.api.deps import DbDep, DealDep, UserDep
from bearcase.api.schemas import AdjustmentDecisionRequest, AdjustmentOut, FinancialsOut, MetricOut, PeriodOut, WaterfallStep
from bearcase.audit import record
from bearcase.chat.brief import invalidate_brief
from bearcase.engine import formulas as f
from bearcase.models import Adjustment, FinancialMetric, FinancialPeriod
from bearcase.models.enums import AdjustmentDecision, AdjustmentDirection, MetricSource

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
        WaterfallStep(label="Verified adjusted EBITDA", amount=total, decision="verified", included=True, running_total=total)
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
    deal: DealDep, adjustment_id: uuid.UUID, body: AdjustmentDecisionRequest, db: DbDep, user: UserDep
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
