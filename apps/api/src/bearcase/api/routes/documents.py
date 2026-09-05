from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select

from bearcase.api.deps import DbDep, DealDep, UserDep
from bearcase.api.schemas import DocumentOut, EvidenceOut, JobOut, ProcessResponse, VersionOut
from bearcase.audit import record
from bearcase.config import get_settings
from bearcase.ingest.storage import get_storage, make_object_key
from bearcase.ingest.validation import UploadRejected, validate_upload
from bearcase.models import Deal, Document, DocumentVersion, Evidence, ProcessingJob
from bearcase.models.enums import DocumentStatus, JobType
from bearcase.pipeline.jobs import dispatch, enqueue_job

router = APIRouter(tags=["documents"])


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
        summary=f"Uploaded {doc.display_name} ({v.size_bytes} bytes)",
        payload={"sha256": v.sha256, "extension": v.extension},
    )
    return doc


@router.get("/deals/{deal_id}/documents", response_model=list[DocumentOut])
def list_documents(deal: DealDep, db: DbDep) -> list[DocumentOut]:
    return [doc_out(db, d) for d in db.scalars(select(Document).where(Document.deal_id == deal.id).order_by(Document.created_at))]


@router.post("/deals/{deal_id}/documents", response_model=list[DocumentOut], status_code=201)
async def upload_documents(
    deal: DealDep, db: DbDep, user: UserDep, files: list[UploadFile], process: bool = True
) -> list[DocumentOut]:
    created: list[Document] = []
    errors: list[dict[str, str]] = []
    for up in files:
        data = await up.read()
        try:
            created.append(store_document(db, deal, user.id, up.filename or "upload", up.content_type, data))
        except UploadRejected as exc:
            errors.append({"file": up.filename or "upload", "code": exc.code, "message": exc.message})
    if errors and not created:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"errors": errors})
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
def reprocess_document(deal: DealDep, document_id: uuid.UUID, db: DbDep, user: UserDep) -> ProcessResponse:
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


@router.get("/deals/{deal_id}/evidence/{evidence_id}", response_model=EvidenceOut)
def get_evidence(deal: DealDep, evidence_id: uuid.UUID, db: DbDep) -> EvidenceOut:
    e = db.scalar(select(Evidence).where(Evidence.id == evidence_id, Evidence.deal_id == deal.id))
    if e is None:
        raise HTTPException(404, "Evidence not found.")
    eo = EvidenceOut.model_validate(e)
    eo.document_name, eo.doc_type = e.document.display_name, e.document.doc_type.value
    return eo


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
