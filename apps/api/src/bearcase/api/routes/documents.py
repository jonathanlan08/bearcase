from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, UploadFile
from sqlalchemy import delete, func, select, update

from bearcase.api.deps import DbDep, DealDep, EditorDealDep, UserDep
from bearcase.api.schemas import DocumentOut, EvidenceOut, JobOut, ProcessResponse, VersionOut
from bearcase.audit import record
from bearcase.chat.brief import invalidate_brief
from bearcase.config import get_settings
from bearcase.ingest.storage import get_storage, make_object_key
from bearcase.ingest.validation import UploadRejected, validate_upload
from bearcase.models import (
    Adjustment,
    AuditEvent,
    Claim,
    ClaimEvidenceLink,
    Deal,
    Document,
    DocumentVersion,
    Evidence,
    ExtractionRun,
    FinancialPeriod,
    Finding,
    ProcessingJob,
    ReportCitation,
    ReviewDecision,
    ReviewerComment,
    User,
)
from bearcase.models.base import utcnow
from bearcase.models.enums import DocumentStatus, JobType, DocumentType
from bearcase.pipeline.jobs import dispatch, enqueue_job

log = logging.getLogger("bearcase.documents")
router = APIRouter(tags=["documents"])
# Sent with a 204 from the delete route: findings and metrics were computed with the document present and
# may now be stale, so the UI should offer "Run analysis".
REANALYSE_HEADER = "X-BearCase-Reanalyse"


def doc_out(db, doc: Document) -> DocumentOut:  # type: ignore[no-untyped-def]
    out = DocumentOut.model_validate(doc)
    version = db.get(DocumentVersion, doc.current_version_id) if doc.current_version_id else None
    out.version = VersionOut.model_validate(version) if version else None
    out.evidence_count = db.scalar(select(func.count(Evidence.id)).where(Evidence.document_id == doc.id)) or 0
    return out


def store_document(db, deal: Deal, user_id: uuid.UUID, filename: str, content_type: str | None, data: bytes) -> Document:  # type: ignore[no-untyped-def]
    """Validate, deduplicate, store, and register an uploaded document. Shared with the seed."""
    v = validate_upload(filename, content_type, data, get_settings().max_upload_bytes)
    dup = db.scalar(select(DocumentVersion).join(Document).where(Document.deal_id == deal.id, DocumentVersion.sha256 == v.sha256))
    if dup:
        raise UploadRejected("duplicate", f"This file was already uploaded as '{dup.document.display_name}'.")
    doc = Document(deal_id=deal.id, display_name=v.display_name, status=DocumentStatus.UPLOADED)
    db.add(doc)
    db.flush()
    key = make_object_key(deal.id, doc.id, 1, v.sha256, v.extension)
    get_storage().put(key, v.data)
    version = DocumentVersion(
        document_id=doc.id,
        version_no=1,
        storage_key=key,
        sha256=v.sha256,
        size_bytes=v.size_bytes,
        extension=v.extension,
        mime_declared=v.mime_declared,
        mime_detected=v.mime_detected,
    )
    db.add(version)
    db.flush()
    doc.current_version_id = version.id
    record(
        db,
        deal_id=deal.id,
        user_id=user_id,
        event_type="document.uploaded",
        object_type="document",
        object_id=doc.id,
        summary=f"Uploaded {doc.display_name} ({max(1, round(v.size_bytes / 1024))} KB)",
        payload={"sha256": v.sha256, "extension": v.extension},
    )
    return doc


@router.get("/deals/{deal_id}/documents", response_model=list[DocumentOut])
def list_documents(deal: DealDep, db: DbDep) -> list[DocumentOut]:
    return [doc_out(db, d) for d in db.scalars(select(Document).where(Document.deal_id == deal.id).order_by(Document.created_at))]


def user_storage_bytes(db, user_id: uuid.UUID) -> int:  # type: ignore[no-untyped-def]
    """Bytes stored across all of a user's deals, every document version counted."""
    total = db.scalar(
        select(func.coalesce(func.sum(DocumentVersion.size_bytes), 0))
        .join(Document, Document.id == DocumentVersion.document_id)
        .join(Deal, Deal.id == Document.deal_id)
        .where(Deal.owner_id == user_id)
    )
    return int(total or 0)


def _mb(n: int) -> str:
    value = n / (1024 * 1024)
    return f"{value:,.0f} MB" if value >= 10 or value == int(value) else f"{value:,.1f} MB"


# When every file in a request is refused, the status says why: too big for the size or storage limit, the deal
# is full, or (422) the files themselves were not acceptable.
_STATUS_BY_CODE = {"too_large": 413, "storage_limit": 413, "document_limit": 400}


@router.post("/deals/{deal_id}/documents", response_model=list[DocumentOut], status_code=201)
async def upload_documents(
    deal: EditorDealDep, db: DbDep, user: UserDep, files: list[UploadFile], process: bool = True
) -> list[DocumentOut]:
    s = get_settings()
    per_file_limit = f"{s.max_upload_bytes // (1024 * 1024)} MB"
    existing = db.scalar(select(func.count(Document.id)).where(Document.deal_id == deal.id)) or 0
    used = user_storage_bytes(db, user.id)
    created: list[Document] = []
    errors: list[dict[str, str]] = []
    for up in files:
        name = up.filename or "upload"
        # Read at most one byte past the limit: an oversized file is refused before it is hashed, validated, or
        # parsed, and never sits in memory whole.
        data = await up.read(s.max_upload_bytes + 1)
        if len(data) > s.max_upload_bytes:
            errors.append({"file": name, "code": "too_large", "message": f"{name} is larger than the {per_file_limit} limit."})
            continue
        if existing + len(created) >= s.max_documents_per_deal:
            errors.append(
                {
                    "file": name,
                    "code": "document_limit",
                    "message": f"This deal already holds {s.max_documents_per_deal:,} documents, the maximum. "
                    "Create another deal for more files.",
                }
            )
            continue
        if used + len(data) > s.max_storage_bytes_per_user:
            errors.append(
                {
                    "file": name,
                    "code": "storage_limit",
                    "message": f"Adding {name} ({_mb(len(data))}) would exceed your storage allowance of "
                    f"{_mb(s.max_storage_bytes_per_user)}; {_mb(used)} is in use across your deals.",
                }
            )
            continue
        try:
            created.append(store_document(db, deal, user.id, name, up.content_type, data))
            used += len(data)
        except UploadRejected as exc:
            errors.append({"file": name, "code": exc.code, "message": exc.message})
    if errors and not created:
        db.rollback()
        code = next((_STATUS_BY_CODE[e["code"]] for e in errors if e["code"] in _STATUS_BY_CODE), 422)
        raise HTTPException(code, {"errors": errors})
    job_ids = []
    if process:
        for doc in created:
            job_ids.append(enqueue_job(db, deal_id=deal.id, job_type=JobType.PROCESS_DOCUMENT, document_id=doc.id).id)
    db.commit()
    dispatch(job_ids)
    out = [doc_out(db, d) for d in created]
    if errors:
        # partial success: report rejected files in a header-free way the client can show
        for e in errors:
            record(
                db,
                deal_id=deal.id,
                user_id=user.id,
                event_type="document.rejected",
                object_type="document",
                summary=f"Rejected {e['file']}: {e['message']}",
                payload=e,
            )
        db.commit()
    return out


@router.get("/deals/{deal_id}/documents/{document_id}", response_model=DocumentOut)
def get_document(deal: DealDep, document_id: uuid.UUID, db: DbDep) -> DocumentOut:
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.deal_id == deal.id))
    if doc is None:
        raise HTTPException(404, "Document not found.")
    return doc_out(db, doc)


@router.get("/deals/{deal_id}/documents/{document_id}/evidence", response_model=list[EvidenceOut])
def document_evidence(
    deal: DealDep,
    document_id: uuid.UUID,
    db: DbDep,
    page: int | None = None,
    sheet: str | None = None,
    limit: int = Query(default=500, le=2000),
    offset: int = 0,
) -> list[EvidenceOut]:
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.deal_id == deal.id))
    if doc is None:
        raise HTTPException(404, "Document not found.")
    q = select(Evidence).where(Evidence.document_id == doc.id).order_by(Evidence.chunk_index)
    rows = db.scalars(q.offset(offset).limit(limit)).all()
    out = []
    for e in rows:
        if page is not None and e.locator.get("page") != page:
            continue
        if sheet is not None and e.locator.get("sheet") != sheet:
            continue
        eo = EvidenceOut.model_validate(e)
        eo.document_name, eo.doc_type = doc.display_name, doc.doc_type.value
        out.append(eo)
    return out


@router.post("/deals/{deal_id}/documents/{document_id}/reprocess", response_model=ProcessResponse, status_code=202)
def reprocess_document(deal: EditorDealDep, document_id: uuid.UUID, db: DbDep, user: UserDep) -> ProcessResponse:
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.deal_id == deal.id))
    if doc is None:
        raise HTTPException(404, "Document not found.")
    job = enqueue_job(db, deal_id=deal.id, job_type=JobType.PROCESS_DOCUMENT, document_id=doc.id)
    record(
        db,
        deal_id=deal.id,
        user_id=user.id,
        event_type="document.reprocess_requested",
        object_type="document",
        object_id=doc.id,
        summary=f"Reprocess {doc.display_name}",
    )
    db.commit()
    dispatch([job.id])
    return ProcessResponse(job_ids=[job.id], message="Queued.")


def _record_evidence_opened(db, deal: Deal, user: User, e: Evidence) -> None:  # type: ignore[no-untyped-def]
    """One `evidence.opened` audit row per evidence, user, and UTC day: enough for the workflow progress steps
    without turning the audit trail into a click log."""
    day_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    seen = db.scalar(
        select(AuditEvent.id)
        .where(
            AuditEvent.event_type == "evidence.opened",
            AuditEvent.object_id == e.id,
            AuditEvent.user_id == user.id,
            AuditEvent.created_at >= day_start,
        )
        .limit(1)
    )
    if seen is not None:
        return
    loc = e.locator or {}
    where = ", ".join(
        part
        for part in (
            f"sheet {loc['sheet']}" if loc.get("sheet") else "",
            f"page {loc['page']}" if loc.get("page") else "",
            f"row {loc['row']}" if loc.get("row") is not None else "",
        )
        if part
    )
    record(
        db,
        deal_id=deal.id,
        user_id=user.id,
        event_type="evidence.opened",
        object_type="evidence",
        object_id=e.id,
        summary=f"Opened evidence in {e.document.display_name}" + (f" ({where})" if where else ""),
        payload={"document_id": str(e.document_id), "locator": loc},
    )
    db.commit()


@router.get("/deals/{deal_id}/evidence/{evidence_id}", response_model=EvidenceOut)
def get_evidence(deal: DealDep, evidence_id: uuid.UUID, db: DbDep, user: UserDep) -> EvidenceOut:
    e = db.scalar(select(Evidence).where(Evidence.id == evidence_id, Evidence.deal_id == deal.id))
    if e is None:
        raise HTTPException(404, "Evidence not found.")
    eo = EvidenceOut.model_validate(e)
    eo.document_name, eo.doc_type = e.document.display_name, e.document.doc_type.value
    return eo


@router.post("/deals/{deal_id}/evidence/{evidence_id}/opened", status_code=204)
def evidence_opened(deal: DealDep, evidence_id: uuid.UUID, db: DbDep, user: UserDep) -> Response:
    """The document viewer reports that a person opened this evidence. Reading the row (GET) is not an open:
    citation chips fetch rows to render their labels, and that must not count as inspecting the source."""
    e = db.scalar(select(Evidence).where(Evidence.id == evidence_id, Evidence.deal_id == deal.id))
    if e is None:
        raise HTTPException(404, "Evidence not found.")
    _record_evidence_opened(db, deal, user, e)
    return Response(status_code=204)


@router.delete("/deals/{deal_id}/documents/{document_id}", status_code=204)
def delete_document(deal: EditorDealDep, document_id: uuid.UUID, db: DbDep, user: UserDep) -> Response:
    """Remove a document with everything derived from it: its versions and stored files, its evidence, the
    claims extracted from it (with their links, reviewer decisions, and findings), and the findings that cite
    its evidence. Children are deleted explicitly, in dependency order, so the result does not depend on the
    database enforcing ON DELETE. The response carries X-BearCase-Reanalyse: true because the remaining
    findings and metrics were computed with the document present."""
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.deal_id == deal.id))
    if doc is None:
        raise HTTPException(404, "Document not found.")
    keys = [v.storage_key for v in doc.versions]
    claim_ids = set(db.scalars(select(Claim.id).where(Claim.document_id == doc.id)).all())
    evidence_ids = {str(e) for e in db.scalars(select(Evidence.id).where(Evidence.document_id == doc.id)).all()}
    doc_claims = select(Claim.id).where(Claim.document_id == doc.id)
    doc_evidence = select(Evidence.id).where(Evidence.document_id == doc.id)

    findings_removed = 0
    for f in db.scalars(select(Finding).where(Finding.deal_id == deal.id)):
        if f.claim_id in claim_ids or any(str(e) in evidence_ids for e in f.evidence_ids):
            db.delete(f)
            findings_removed += 1
    db.flush()
    db.execute(delete(ReviewDecision).where(ReviewDecision.claim_id.in_(doc_claims)))
    db.execute(delete(ReviewerComment).where(ReviewerComment.claim_id.in_(doc_claims)))
    db.execute(update(Adjustment).where(Adjustment.claim_id.in_(doc_claims)).values(claim_id=None))
    db.execute(delete(ClaimEvidenceLink).where(ClaimEvidenceLink.claim_id.in_(doc_claims)))
    db.execute(delete(Claim).where(Claim.document_id == doc.id))
    # Evidence: links from other documents' claims that cited this evidence go too; citations in stored
    # reports keep their row and lose the pointer, the way the database would set them null.
    db.execute(delete(ClaimEvidenceLink).where(ClaimEvidenceLink.evidence_id.in_(doc_evidence)))
    db.execute(update(Claim).where(Claim.source_evidence_id.in_(doc_evidence)).values(source_evidence_id=None))
    db.execute(update(ReportCitation).where(ReportCitation.evidence_id.in_(doc_evidence)).values(evidence_id=None))
    db.execute(delete(Evidence).where(Evidence.document_id == doc.id))
    db.execute(update(FinancialPeriod).where(FinancialPeriod.source_document_id == doc.id).values(source_document_id=None))
    db.execute(delete(ExtractionRun).where(ExtractionRun.document_id == doc.id))
    db.execute(delete(ProcessingJob).where(ProcessingJob.document_id == doc.id))
    db.delete(doc)  # versions go through the relationship cascade
    db.flush()
    storage = get_storage()
    for key in keys:
        try:
            storage.delete(key)
        except Exception:  # a missing blob must not keep the rows alive
            log.warning("could not delete stored file %s", key, exc_info=True)
    record(
        db,
        deal_id=deal.id,
        user_id=user.id,
        event_type="document.deleted",
        object_type="document",
        object_id=doc.id,
        summary=f"Deleted {doc.display_name} with {len(claim_ids)} claim{'s' if len(claim_ids) != 1 else ''} drawn from it",
        payload={
            "display_name": doc.display_name,
            "doc_type": doc.doc_type.value,
            "versions": len(keys),
            "claims_removed": len(claim_ids),
            "evidence_removed": len(evidence_ids),
            "findings_removed": findings_removed,
        },
    )
    db.commit()
    invalidate_brief(deal.id)
    return Response(status_code=204, headers={REANALYSE_HEADER: "true"})


@router.get("/deals/{deal_id}/jobs", response_model=list[JobOut])
def list_jobs(deal: DealDep, db: DbDep, limit: int = Query(default=50, le=200)) -> list[ProcessingJob]:
    return list(
        db.scalars(
            select(ProcessingJob)
            .where(ProcessingJob.deal_id == deal.id)
            .order_by(ProcessingJob.created_at.desc(), ProcessingJob.sequence.desc())
            .limit(limit)
        ).all()
    )


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, db: DbDep, user: UserDep) -> ProcessingJob:
    job = db.scalar(
        select(ProcessingJob)
        .join(Deal, Deal.id == ProcessingJob.deal_id)
        .where(ProcessingJob.id == job_id, Deal.owner_id == user.id)
    )
    if job is None:
        raise HTTPException(404, "Job not found.")
    return job


@router.post("/deals/{deal_id}/documents/{document_id}/versions", response_model=DocumentOut, status_code=201)
async def upload_new_version(deal: EditorDealDep, document_id: uuid.UUID, db: DbDep, user: UserDep, file: UploadFile, process: bool = True) -> DocumentOut:
    """A revised copy of a document the seller already supplied (a restated statement, a corrected memo). Stored as
    the next version; the earlier file is kept so the two can be compared. Re-reading replaces the evidence, and the
    findings and metrics computed from the old copy stay until analysis is re-run, which the client should offer."""
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.deal_id == deal.id))
    if doc is None:
        raise HTTPException(404, "Document not found.")
    s = get_settings()
    data = await file.read(s.max_upload_bytes + 1)
    if len(data) > s.max_upload_bytes:
        raise HTTPException(413, f"The file is larger than {s.max_upload_bytes // (1024 * 1024)} MB.")
    try:
        v = validate_upload(file.filename or doc.display_name, file.content_type, data, s.max_upload_bytes)
    except UploadRejected as exc:
        raise HTTPException(422, str(exc)) from exc
    current = db.get(DocumentVersion, doc.current_version_id) if doc.current_version_id else None
    if current and current.sha256 == v.sha256:
        raise HTTPException(422, "That file is identical to the current version.")
    if current and current.extension != v.extension:
        raise HTTPException(422, f"A new version must be the same kind of file ({current.extension}).")
    version_no = (max((x.version_no for x in doc.versions), default=0)) + 1
    key = make_object_key(deal.id, doc.id, version_no, v.sha256, v.extension)
    get_storage().put(key, v.data)
    version = DocumentVersion(document_id=doc.id, version_no=version_no, storage_key=key, sha256=v.sha256, size_bytes=v.size_bytes, extension=v.extension, mime_declared=v.mime_declared, mime_detected=v.mime_detected)
    db.add(version)
    db.flush()
    doc.current_version_id = version.id
    doc.status = DocumentStatus.UPLOADED
    doc.status_detail = None
    record(db, deal_id=deal.id, user_id=user.id, event_type="document.version_uploaded", object_type="document", object_id=doc.id, summary=f"Uploaded version {version_no} of {doc.display_name}", payload={"version_no": version_no, "sha256": v.sha256})
    if process:
        enqueue_job(db, deal_id=deal.id, job_type=JobType.PROCESS_DOCUMENT, document_id=doc.id)
    db.commit()
    db.refresh(doc)
    return doc_out(db, doc)


# Lines whose change moves these derived figures; used to say which calculations a revision touches.
_DEPENDENTS: dict[str, list[str]] = {
    "revenue": ["revenue_growth", "cagr", "gross_margin", "operating_margin", "customer_concentration_top1", "recurring_revenue_pct", "cfads_base", "dscr_base"],
    "cost_of_goods_sold": ["gross_margin", "gross_profit"],
    "gross_profit": ["gross_margin"],
    "operating_expenses": ["operating_margin", "ebitda_reported"],
    "ebitda": ["ebitda_reported", "ebitda_adjusted_verified", "ev_to_ebitda_verified", "debt_to_ebitda_verified", "cfads_base", "dscr_base"],
    "net_income": ["ebitda_reported"],
    "interest_expense": ["ebitda_reported"],
    "income_tax_expense": ["ebitda_reported"],
    "depreciation": ["ebitda_reported"],
    "amortization": ["ebitda_reported"],
    "operating_income": ["operating_margin"],
}


@router.get("/deals/{deal_id}/documents/{document_id}/diff")
def diff_versions(deal: DealDep, document_id: uuid.UUID, db: DbDep, against: int | None = None) -> dict[str, Any]:
    """What changed between the current version of a document and an earlier one. For a statement workbook the two
    files are parsed and mapped the same way the pipeline maps them, and every mapped figure that differs is listed
    with the calculations that depend on it and the claims that cite that line. For other files the comparison is
    by page or row text. Nothing is written; re-running analysis is what refreshes the findings."""
    from bearcase.ingest.parsers import parse_csv, parse_pdf, parse_xlsx
    from bearcase.ingest.statement_mapper import map_income_statement

    doc = db.scalar(select(Document).where(Document.id == document_id, Document.deal_id == deal.id))
    if doc is None:
        raise HTTPException(404, "Document not found.")
    versions = sorted(doc.versions, key=lambda x: x.version_no)
    if len(versions) < 2:
        return {"document_id": str(doc.id), "versions": [x.version_no for x in versions], "comparable": False, "reason": "Only one version of this document exists."}
    new = versions[-1]
    old = next((x for x in versions if x.version_no == against), versions[-2]) if against else versions[-2]
    storage = get_storage()

    def parsed(v: DocumentVersion):  # type: ignore[no-untyped-def]
        data = storage.get(v.storage_key)
        if v.extension == "xlsx":
            return parse_xlsx(data)
        if v.extension == "csv":
            return parse_csv(data)
        return parse_pdf(data)

    p_old, p_new = parsed(old), parsed(new)
    out: dict[str, Any] = {"document_id": str(doc.id), "document_name": doc.display_name, "versions": [x.version_no for x in versions], "old_version": old.version_no, "new_version": new.version_no, "comparable": True}
    if doc.doc_type == DocumentType.FINANCIAL_STATEMENTS or new.extension == "xlsx":
        m_old, m_new = map_income_statement(p_old.chunks), map_income_statement(p_new.chunks)
        changes: list[dict[str, Any]] = []
        if m_old and m_new:
            periods = sorted(set(m_old.periods) | set(m_new.periods), key=lambda p: p)
            for period in periods:
                keys = set(m_old.lines.get(period, {})) | set(m_new.lines.get(period, {}))
                for key in sorted(keys):
                    a = m_old.lines.get(period, {}).get(key)
                    b = m_new.lines.get(period, {}).get(key)
                    if (a.value if a else None) != (b.value if b else None):
                        changes.append({"period": period, "line_key": key, "before": str(a.value) if a else None, "after": str(b.value) if b else None, "cell": b.cell if b else (a.cell if a else None), "dependents": _DEPENDENTS.get(key, [])})
            out.update({"kind": "statement", "periods_before": m_old.periods, "periods_after": m_new.periods, "scale_before": m_old.scale, "scale_after": m_new.scale, "changes": changes})
        else:
            out.update({"kind": "statement", "changes": [], "reason": "One of the versions could not be read as an income statement."})
        touched = {k for c in changes for k in (c["line_key"], *c["dependents"])}
        claims = db.scalars(select(Claim).where(Claim.deal_id == deal.id, Claim.metric_key.in_(sorted(touched)))).all() if touched else []
        out["claims_affected"] = [{"id": str(c.id), "text": c.claim_text[:140], "status": c.status.value, "metric_key": c.metric_key} for c in claims]
    else:
        old_text = [c.text for c in p_old.chunks]
        new_text = [c.text for c in p_new.chunks]
        added = [t for t in new_text if t not in set(old_text)]
        removed = [t for t in old_text if t not in set(new_text)]
        out.update({"kind": "text", "chunks_before": len(old_text), "chunks_after": len(new_text), "added": added[:40], "removed": removed[:40]})
    out["stale"] = bool(out.get("changes") or out.get("added") or out.get("removed"))
    return out


@router.get("/deals/{deal_id}/evidence-search")
def search_evidence(deal: DealDep, db: DbDep, q: str = "", limit: int = 20) -> list[dict[str, Any]]:
    """Find evidence rows by their text, for attaching a source to a note or a question. Case-insensitive
    substring match over this deal's evidence only; returns the document, the location, and an excerpt."""
    needle = q.strip()
    if len(needle) < 2:
        return []
    rows = db.scalars(
        select(Evidence)
        .where(Evidence.deal_id == deal.id, Evidence.text.ilike(f"%{needle}%"))
        .order_by(Evidence.document_id, Evidence.chunk_index)
        .limit(max(1, min(limit, 50)))
    ).all()
    out = []
    for e in rows:
        text = e.text or ""
        i = text.lower().find(needle.lower())
        start = max(0, i - 80)
        excerpt = ("…" if start > 0 else "") + text[start : start + 240] + ("…" if len(text) > start + 240 else "")
        out.append({"id": str(e.id), "document_id": str(e.document_id), "document_name": e.document.display_name, "doc_type": e.document.doc_type.value, "kind": e.kind.value, "locator": e.locator, "excerpt": excerpt})
    return out
