"""Parse one document version into evidence chunks with provenance."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from bearcase.ai.provider import ChunkRef, DocumentContext, get_provider
from bearcase.config import get_settings
from bearcase.ingest.classify import classify
from bearcase.ingest.injection import contains_instruction_text
from bearcase.ingest.parsers import ParseResult, parse_csv, parse_pdf, parse_xlsx
from bearcase.ingest.storage import get_storage
from bearcase.models import Document, DocumentVersion, Evidence, ExtractionRun, ProcessingJob
from bearcase.models.enums import ClassificationSource, DocumentStatus, DocumentType, EvidenceKind, RunStatus, RunType
from bearcase.pipeline.jobs import JobLog


def parse_bytes(extension: str, data: bytes) -> ParseResult:
    s = get_settings()
    if extension == "pdf":
        return parse_pdf(data, s.max_pdf_pages)
    if extension == "xlsx":
        return parse_xlsx(data, s.max_sheet_rows)
    if extension == "csv":
        return parse_csv(data, s.max_csv_rows)
    raise ValueError(f"unsupported extension {extension}")


def process_document(db: Session, job: ProcessingJob, jl: JobLog) -> None:
    doc = db.get(Document, job.document_id)
    if doc is None:
        raise ValueError("document not found")
    version = db.get(DocumentVersion, doc.current_version_id) if doc.current_version_id else None
    if version is None:
        raise ValueError("document has no stored version")
    doc.status = DocumentStatus.PARSING
    jl.step("Reading file", 10)
    data = get_storage().get(version.storage_key)
    parsed = parse_bytes(version.extension, data)
    version.page_count, version.sheet_count, version.row_count = parsed.page_count, parsed.sheet_count, parsed.row_count
    version.parse_meta = parsed.meta
    jl.step("Classifying", 35, pages=parsed.page_count, sheets=parsed.sheet_count, rows=parsed.row_count)
    if doc.classification_source != ClassificationSource.USER:
        cls = classify(version.extension, doc.display_name, parsed)
        doc.doc_type = DocumentType(cls.doc_type)
        doc.classification_source = ClassificationSource.RULE
        doc.classification_confidence = Decimal(str(cls.confidence))
        if cls.doc_type == "unknown":
            provider = get_provider()
            ctx = DocumentContext(
                doc.display_name,
                "unknown",
                version.extension,
                [ChunkRef(i, c.kind, c.locator, c.text) for i, c in enumerate(parsed.chunks[:80])],
            )
            res = provider.classify(ctx)
            db.add(
                ExtractionRun(
                    deal_id=doc.deal_id,
                    document_id=doc.id,
                    run_type=RunType.CLASSIFY,
                    status=RunStatus.SUCCEEDED if res.ok else RunStatus.FAILED,
                    provider=provider.name,
                    model=provider.model,
                    prompt_version=res.prompt_version,
                    schema_version=res.schema_version,
                    input_hash=res.input_hash,
                    raw_output=res.raw,
                    usage=res.usage,
                    error=res.error,
                )
            )
            if res.ok and res.output:
                doc.doc_type = DocumentType(res.output.doc_type)
                doc.classification_source = ClassificationSource.AI
                doc.classification_confidence = Decimal(str(res.output.confidence))
    doc.status = DocumentStatus.EXTRACTING
    jl.step("Creating evidence chunks", 55)
    db.execute(delete(Evidence).where(Evidence.document_id == doc.id))
    flagged = 0
    for i, chunk in enumerate(parsed.chunks):
        flag = contains_instruction_text(chunk.text)
        flagged += int(flag)
        db.add(
            Evidence(
                deal_id=doc.deal_id,
                document_id=doc.id,
                document_version_id=version.id,
                kind=EvidenceKind(chunk.kind),
                chunk_index=i,
                locator=chunk.locator,
                text=chunk.text,
                structured=chunk.structured,
                contains_instruction_text=flag,
            )
        )
    doc.status = DocumentStatus.READY
    doc.status_detail = None
    jl.step("Evidence stored", 95, chunks=len(parsed.chunks), instruction_like_chunks=flagged)
    db.commit()
    _ = select  # keep import for type checkers
