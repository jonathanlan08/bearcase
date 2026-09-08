from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import func, select

from bearcase.api.deps import DbDep, DealDep, EditorDealDep, OwnerDealDep, UserDep, accepted_membership_ids
from bearcase.api.schemas import DealCreate, DealListItem, DealOut, DealSummary, FindingOut, ProcessResponse
from bearcase.reports.resolution import resolution_for
from bearcase.audit import record
from bearcase.auth import delete_deal_with_files
from bearcase.config import get_settings
from bearcase.models import (
    Claim,
    Deal,
    DealMember,
    Document,
    FinancialMetric,
    Finding,
    ProcessingJob,
    Report,
    ReviewDecision,
    Scenario,
)
from bearcase.models.enums import DocumentStatus, FindingKind, JobStatus, JobType, PurchasePriceBasis, ClaimStatus
from bearcase.pipeline.jobs import dispatch, enqueue_job

router = APIRouter(prefix="/deals", tags=["deals"])


def effective_status(claim: Claim) -> str:
    current = next((d for d in reversed(claim.review_decisions) if d.is_current), None)
    if current and current.resulting_status:
        return current.resulting_status
    return claim.status.value


@router.get("", response_model=list[DealListItem])
def list_deals(db: DbDep, user: UserDep) -> list[DealListItem]:
    out: list[DealListItem] = []
    roles: dict[uuid.UUID, str] = {
        m.deal_id: m.role.value
        for m in db.scalars(select(DealMember).where(DealMember.user_id == user.id, DealMember.accepted_at.is_not(None)))
    }
    for deal in db.scalars(
        select(Deal)
        .where((Deal.owner_id == user.id) | Deal.id.in_(accepted_membership_ids(user.id)))
        .order_by(Deal.updated_at.desc())
    ):
        docs = db.scalars(select(Document.status).where(Document.deal_id == deal.id)).all()
        counts: dict[str, int] = {}
        for c in db.scalars(select(Claim).where(Claim.deal_id == deal.id)):
            s = effective_status(c)
            counts[s] = counts.get(s, 0) + 1
        item = DealListItem.model_validate(deal)
        item.document_count = len(docs)
        item.documents_ready = sum(1 for s in docs if s == DocumentStatus.READY)
        item.claim_counts = counts
        item.role = "owner" if deal.owner_id == user.id else ("editor" if roles.get(deal.id) == "editor" else "viewer")
        out.append(item)
    return out


@router.post("", response_model=DealOut, status_code=201)
def create_deal(body: DealCreate, db: DbDep, user: UserDep) -> Deal:
    deal = Deal(
        owner_id=user.id,
        purchase_price_basis=PurchasePriceBasis(body.purchase_price_basis),
        **body.model_dump(exclude={"purchase_price_basis"}),
    )
    db.add(deal)
    db.flush()
    record(
        db,
        deal_id=deal.id,
        user_id=user.id,
        event_type="deal.created",
        object_type="deal",
        object_id=deal.id,
        summary=f"Created deal {deal.company_name}",
        payload={"purchase_price": str(deal.purchase_price)},
    )
    db.commit()
    return deal


@router.get("/{deal_id}", response_model=DealOut)
def get_deal_route(deal: DealDep) -> Deal:
    return deal


@router.get("/{deal_id}/summary", response_model=DealSummary)
def deal_summary(deal: DealDep, db: DbDep) -> DealSummary:
    s = get_settings()
    docs: dict[str, int] = {}
    for st in db.scalars(select(Document.status).where(Document.deal_id == deal.id)):
        docs[st.value] = docs.get(st.value, 0) + 1
    counts: dict[str, int] = {}
    for c in db.scalars(select(Claim).where(Claim.deal_id == deal.id)):
        es = effective_status(c)
        counts[es] = counts.get(es, 0) + 1
    findings = list(db.scalars(select(Finding).where(Finding.deal_id == deal.id)))
    sev: dict[str, int] = {}
    for fnd in findings:
        sev[fnd.severity.value] = sev.get(fnd.severity.value, 0) + 1

    def metric(key: str) -> Decimal | None:
        m = db.scalar(
            select(FinancialMetric)
            .where(FinancialMetric.deal_id == deal.id, FinancialMetric.key == key)
            .order_by(FinancialMetric.created_at.desc())
        )
        return m.value if m else None

    dscr = []
    for sc in db.scalars(select(Scenario).where(Scenario.deal_id == deal.id).order_by(Scenario.sort_order)):
        res = sc.results[-1] if sc.results else None
        dscr.append(
            {
                "scenario_id": str(sc.id),
                "name": sc.name,
                "kind": sc.kind.value,
                "dscr": res.outputs.get("year1", {}).get("dscr") if res else None,
                "warnings": [w["code"] for w in res.warnings] if res else [],
            }
        )
    report = db.scalar(select(Report).where(Report.deal_id == deal.id).order_by(Report.version_no.desc()))
    active = (
        db.scalar(
            select(func.count(ProcessingJob.id)).where(
                ProcessingJob.deal_id == deal.id, ProcessingJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])
            )
        )
        or 0
    )
    sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    top = sorted(
        [fnd for fnd in findings if fnd.kind != FindingKind.MISSING_DOCUMENT],
        key=lambda x: (sev_rank[x.severity.value], x.created_at),
    )[:6]
    decided_ids = {d.claim_id for d in db.scalars(select(ReviewDecision).where(ReviewDecision.deal_id == deal.id, ReviewDecision.is_current.is_(True)))}
    all_claims = db.scalars(select(Claim).where(Claim.deal_id == deal.id)).all()
    confidence = {
        "decided": sum(1 for c in all_claims if c.id in decided_ids),
        "rules_only": sum(1 for c in all_claims if c.id not in decided_ids and c.status in (ClaimStatus.SUPPORTED, ClaimStatus.CONTRADICTED)),
        "needs_person": sum(1 for c in all_claims if c.id not in decided_ids and c.status in (ClaimStatus.REVIEW_REQUIRED, ClaimStatus.PENDING)),
        "no_evidence": sum(1 for c in all_claims if c.id not in decided_ids and c.status == ClaimStatus.UNSUPPORTED),
        "total": len(all_claims),
    }
    return DealSummary(
        confidence=confidence,
        deal=DealOut.model_validate(deal),
        documents=docs,
        claim_counts=counts,
        findings_by_severity=sev,
        seller_adjusted_ebitda=metric("ebitda_adjusted_seller"),
        verified_adjusted_ebitda=metric("ebitda_adjusted_verified"),
        reported_ebitda=metric("ebitda_reported"),
        dscr_by_scenario=dscr,
        covenant_threshold=deal.covenant_dscr_threshold,
        missing_documents=[_finding_out(db, x) for x in findings if x.kind == FindingKind.MISSING_DOCUMENT],
        top_findings=[_finding_out(db, x) for x in top],
        latest_report={
            "id": str(report.id),
            "version_no": report.version_no,
            "status": report.status.value,
            "outcome": report.outcome.value,
            "created_at": report.created_at.isoformat(),
        }
        if report
        else None,
        active_jobs=active,
        mode={"provider": s.ai_provider, "model": s.ai_model if s.ai_provider == "anthropic" else "rules-v1"},
    )


@router.post("/{deal_id}/process", response_model=ProcessResponse, status_code=202)
def process_deal(deal: EditorDealDep, db: DbDep, user: UserDep, reprocess: bool = False) -> ProcessResponse:
    """Queue document processing for every document that is not ready (or all, with reprocess), then deal analysis."""
    job_ids: list[uuid.UUID] = []
    for doc in db.scalars(select(Document).where(Document.deal_id == deal.id).order_by(Document.created_at)):
        if reprocess or doc.status != DocumentStatus.READY:
            job_ids.append(enqueue_job(db, deal_id=deal.id, job_type=JobType.PROCESS_DOCUMENT, document_id=doc.id).id)
    job_ids.append(enqueue_job(db, deal_id=deal.id, job_type=JobType.ANALYZE_DEAL).id)
    record(
        db,
        deal_id=deal.id,
        user_id=user.id,
        event_type="deal.process_requested",
        object_type="deal",
        object_id=deal.id,
        summary=f"Queued {len(job_ids)} processing jobs",
        payload={"reprocess": reprocess},
    )
    db.commit()
    dispatch(job_ids)
    return ProcessResponse(job_ids=job_ids, message=f"Queued {len(job_ids)} jobs.")


@router.delete("/{deal_id}", status_code=204)
def delete_deal(deal: OwnerDealDep, db: DbDep, user: UserDep) -> None:
    """Remove a deal with its documents, stored files, and memberships. Owner only."""
    record(
        db,
        user_id=user.id,
        event_type="deal.deleted",
        object_type="deal",
        object_id=deal.id,
        summary=f"Deleted deal {deal.company_name}",
    )
    delete_deal_with_files(db, deal)
    db.commit()


@router.get("/{deal_id}/findings", response_model=list[FindingOut])
def list_findings(deal: DealDep, db: DbDep) -> list[Finding]:
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    rows = sorted(
        db.scalars(select(Finding).where(Finding.deal_id == deal.id)).all(), key=lambda x: (rank[x.severity.value], x.created_at)
    )
    return [_finding_out(db, x) for x in rows]


def _finding_out(db: Session, f: Finding) -> FindingOut:
    """A finding with the one sentence on what would change it."""
    out = FindingOut.model_validate(f)
    claim = db.get(Claim, f.claim_id) if f.claim_id else None
    out.resolution = resolution_for(f, claim)
    return out


_ = ReviewDecision
