from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from bearcase.api.deps import DbDep, DealDep, UserDep
from bearcase.api.routes.deals import effective_status
from bearcase.api.schemas import ClaimDetailOut, ClaimOut, DecisionOut, EvidenceOut, LinkOut, MetricOut, ReviewRequest
from bearcase.audit import record
from bearcase.models import Claim, ExtractionRun, FinancialMetric, ReviewDecision
from bearcase.models.enums import ClaimUnit, LinkRole, ReviewAction

router = APIRouter(tags=["claims"])


def _evidence_out(e) -> EvidenceOut:  # type: ignore[no-untyped-def]
    eo = EvidenceOut.model_validate(e)
    eo.document_name, eo.doc_type = e.document.display_name, e.document.doc_type.value
    return eo


def _claim_out(c: Claim, detail: bool = False) -> ClaimOut | ClaimDetailOut:
    base = ClaimOut.model_validate(c, from_attributes=True)
    base.document_name, base.doc_type = c.document.display_name, c.document.doc_type.value
    base.effective_status = effective_status(c)
    base.source_locator = c.source_evidence.locator if c.source_evidence else {}
    base.supporting_count = sum(1 for link in c.links if link.role == LinkRole.SUPPORTING)
    base.contradicting_count = sum(1 for link in c.links if link.role == LinkRole.CONTRADICTING)
    decs = []
    for d in c.review_decisions:
        do = DecisionOut.model_validate(d)
        do.user_name = d.user.display_name if d.user else ""
        decs.append(do)
    base.decisions = decs
    if not detail:
        return base
    return ClaimDetailOut(
        **base.model_dump(),
        source_evidence=_evidence_out(c.source_evidence) if c.source_evidence else None,
        links=[
            LinkOut(role=link.role.value, note=link.note, evidence=_evidence_out(link.evidence))
            for link in c.links
            if link.role != LinkRole.SOURCE
        ],
    )


@router.get("/deals/{deal_id}/claims", response_model=list[ClaimOut])
def list_claims(
    deal: DealDep,
    db: DbDep,
    status: str | None = None,
    claim_type: str | None = None,
    q: str | None = None,
    document_id: uuid.UUID | None = None,
) -> list[ClaimOut]:
    rows = db.scalars(select(Claim).where(Claim.deal_id == deal.id).order_by(Claim.created_at)).all()
    out = []
    for c in rows:
        if document_id and c.document_id != document_id:
            continue
        if claim_type and c.claim_type.value != claim_type:
            continue
        co = _claim_out(c)
        if status and co.effective_status != status:
            continue
        if q and q.lower() not in c.claim_text.lower():
            continue
        out.append(co)
    return out


@router.get("/deals/{deal_id}/claims/{claim_id}", response_model=ClaimDetailOut)
def get_claim(deal: DealDep, claim_id: uuid.UUID, db: DbDep) -> ClaimDetailOut:
    c = db.scalar(select(Claim).where(Claim.id == claim_id, Claim.deal_id == deal.id))
    if c is None:
        raise HTTPException(404, "Claim not found.")
    out = _claim_out(c, detail=True)
    assert isinstance(out, ClaimDetailOut)
    if c.verified_metric_id:
        m = db.get(FinancialMetric, c.verified_metric_id)
        if m:
            mo = MetricOut.model_validate(m)
            mo.period_label = m.period.label if m.period else None
            out.verified_metric = mo
    if c.extraction_run_id:
        run = db.get(ExtractionRun, c.extraction_run_id)
        if run:
            out.extraction_run = {
                "id": str(run.id),
                "provider": run.provider,
                "model": run.model,
                "prompt_version": run.prompt_version,
                "schema_version": run.schema_version,
                "status": run.status.value,
                "created_at": run.created_at.isoformat(),
            }
    return out


@router.post("/deals/{deal_id}/claims/{claim_id}/review", response_model=ClaimDetailOut)
def review_claim(deal: DealDep, claim_id: uuid.UUID, body: ReviewRequest, db: DbDep, user: UserDep) -> ClaimDetailOut:
    c = db.scalar(select(Claim).where(Claim.id == claim_id, Claim.deal_id == deal.id))
    if c is None:
        raise HTTPException(404, "Claim not found.")
    if body.action in ("reject", "correct") and not body.note:
        raise HTTPException(422, "A note is required to reject or correct a claim.")
    previous = next((d for d in reversed(c.review_decisions) if d.is_current), None)
    if body.action == "undo" and previous is None:
        raise HTTPException(409, "Nothing to undo.")
    for d in c.review_decisions:
        d.is_current = False
    if body.action == "accept":
        resulting = c.status.value
    elif body.action == "reject":
        resulting = "review_required"
    elif body.action == "correct":
        resulting = body.resulting_status or "review_required"
    else:
        resulting = None
    decision = ReviewDecision(
        deal_id=deal.id,
        claim_id=c.id,
        user_id=user.id,
        action=ReviewAction(body.action),
        resulting_status=resulting,
        corrected_value=body.corrected_value,
        corrected_unit=ClaimUnit(body.corrected_unit) if body.corrected_unit else None,
        note=body.note,
        supersedes_id=previous.id if previous else None,
        is_current=body.action != "undo",
    )
    db.add(decision)
    db.flush()
    record(
        db,
        deal_id=deal.id,
        user_id=user.id,
        event_type=f"claim.{body.action}",
        object_type="claim",
        object_id=c.id,
        summary=f"{user.display_name} {body.action}ed claim: {c.claim_text[:80]}"
        if body.action != "undo"
        else f"{user.display_name} undid the previous decision on: {c.claim_text[:80]}",
        payload={
            "ai_status": c.status.value,
            "resulting_status": resulting,
            "corrected_value": str(body.corrected_value) if body.corrected_value is not None else None,
            "corrected_unit": body.corrected_unit,
            "note": body.note,
            "decision_id": str(decision.id),
        },
    )
    db.commit()
    db.refresh(c)
    return get_claim(deal, claim_id, db)


_ = Decimal
