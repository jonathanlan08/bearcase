from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from bearcase.api.deps import DbDep, DealDep, UserDep
from bearcase.api.schemas import ProcessResponse, ReportOut
from bearcase.audit import record
from bearcase.models import Report
from bearcase.models.enums import JobType
from bearcase.pipeline.jobs import dispatch, enqueue_job
from bearcase.reports.export import to_markdown, to_pdf

router = APIRouter(tags=["reports"])


@router.post("/deals/{deal_id}/report", response_model=ProcessResponse, status_code=202)
def generate(deal: DealDep, db: DbDep, user: UserDep) -> ProcessResponse:
    job = enqueue_job(db, deal_id=deal.id, job_type=JobType.GENERATE_REPORT)
    record(
        db,
        deal_id=deal.id,
        user_id=user.id,
        event_type="report.requested",
        object_type="deal",
        object_id=deal.id,
        summary="Report generation requested",
    )
    db.commit()
    dispatch([job.id])
    return ProcessResponse(job_ids=[job.id], message="Report generation queued.")


@router.get("/deals/{deal_id}/report", response_model=ReportOut | None)
def latest(deal: DealDep, db: DbDep) -> Report | None:
    return db.scalar(select(Report).where(Report.deal_id == deal.id).order_by(Report.version_no.desc()))


@router.get("/deals/{deal_id}/reports", response_model=list[ReportOut])
def history(deal: DealDep, db: DbDep) -> list[Report]:
    return list(db.scalars(select(Report).where(Report.deal_id == deal.id).order_by(Report.version_no.desc())).all())


@router.get("/deals/{deal_id}/reports/{report_id}", response_model=ReportOut)
def get_report(deal: DealDep, report_id: uuid.UUID, db: DbDep) -> Report:
    r = db.scalar(select(Report).where(Report.id == report_id, Report.deal_id == deal.id))
    if r is None:
        raise HTTPException(404, "Report not found.")
    return r


@router.get("/deals/{deal_id}/reports/{report_id}/export")
def export(deal: DealDep, report_id: uuid.UUID, db: DbDep, format: str = "md") -> Response:
    r = db.scalar(select(Report).where(Report.id == report_id, Report.deal_id == deal.id))
    if r is None:
        raise HTTPException(404, "Report not found.")
    if r.status.value != "validated":
        raise HTTPException(409, "Only validated reports can be exported.")
    slug = "".join(ch if ch.isalnum() else "-" for ch in deal.company_name.lower()).strip("-")[:40]
    if format == "pdf":
        return Response(
            to_pdf(r, deal.company_name, deal.is_demo),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="bearcase-{slug}-v{r.version_no}.pdf"'},
        )
    return Response(
        to_markdown(r, deal.company_name, deal.is_demo),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="bearcase-{slug}-v{r.version_no}.md"'},
    )
