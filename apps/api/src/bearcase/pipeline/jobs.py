"""Job runner. Default: a single in-process worker thread executing queued jobs FIFO.
`poll` mode leaves execution to an external worker (`bearcase worker`) for multi-process deployments."""

from __future__ import annotations

import logging
import queue
import threading
import traceback
import uuid
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from bearcase.config import get_settings
from bearcase.db import session_scope
from bearcase.models import Document, ProcessingJob
from bearcase.models.base import utcnow
from bearcase.models.enums import DocumentStatus, JobStatus, JobType

log = logging.getLogger("bearcase.jobs")


class JobRunner(Protocol):
    def submit(self, job_id: uuid.UUID) -> None: ...


class SyncRunner:
    def submit(self, job_id: uuid.UUID) -> None:
        run_job(job_id)


class ThreadRunner:
    def __init__(self) -> None:
        self.q: queue.Queue[uuid.UUID] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def _ensure(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, name="bearcase-jobs", daemon=True)
                self._thread.start()

    def _loop(self) -> None:
        while True:
            job_id = self.q.get()
            try:
                run_job(job_id)
            except Exception:
                log.exception("job %s crashed", job_id)
            finally:
                self.q.task_done()

    def submit(self, job_id: uuid.UUID) -> None:
        self._ensure()
        self.q.put(job_id)


class NoopRunner:
    def submit(self, job_id: uuid.UUID) -> None:
        return None


_runner: JobRunner | None = None


def get_runner() -> JobRunner:
    global _runner
    if _runner is None:
        mode = get_settings().job_runner
        _runner = SyncRunner() if mode == "sync" else NoopRunner() if mode == "poll" else ThreadRunner()
    return _runner


def set_runner(runner: JobRunner | None) -> None:
    global _runner
    _runner = runner


def enqueue_job(db: Session, *, deal_id: uuid.UUID, job_type: JobType, document_id: uuid.UUID | None = None) -> ProcessingJob:
    seq = (
        db.scalar(select(ProcessingJob.sequence).where(ProcessingJob.deal_id == deal_id).order_by(ProcessingJob.sequence.desc()))
        or 0
    ) + 1
    job = ProcessingJob(
        deal_id=deal_id,
        document_id=document_id,
        job_type=job_type,
        status=JobStatus.QUEUED,
        sequence=seq,
        log=[{"at": utcnow().isoformat(), "step": "queued"}],
    )
    db.add(job)
    if document_id:
        doc = db.get(Document, document_id)
        if doc:
            doc.status = DocumentStatus.QUEUED
    db.flush()
    return job


def dispatch(job_ids: list[uuid.UUID]) -> None:
    runner = get_runner()
    for jid in job_ids:
        runner.submit(jid)


class JobLog:
    """Progress writer that commits so pollers see live status."""

    def __init__(self, db: Session, job: ProcessingJob):
        self.db, self.job = db, job

    def step(self, name: str, progress: int, **extra: Any) -> None:
        self.job.step = name
        self.job.progress = max(self.job.progress, min(progress, 100))
        entries = list(self.job.log or [])
        entries.append({"at": utcnow().isoformat(), "step": name, "progress": self.job.progress, **extra})
        self.job.log = entries
        self.db.commit()


def run_job(job_id: uuid.UUID) -> None:
    from bearcase.pipeline.analyze import analyze_deal, generate_report
    from bearcase.pipeline.process_document import process_document

    with session_scope() as db:
        job = db.get(ProcessingJob, job_id)
        if job is None or job.status != JobStatus.QUEUED:
            return
        job.status = JobStatus.RUNNING
        job.started_at = utcnow()
        db.commit()
        jl = JobLog(db, job)
        try:
            if job.job_type == JobType.PROCESS_DOCUMENT:
                process_document(db, job, jl)
            elif job.job_type == JobType.ANALYZE_DEAL:
                analyze_deal(db, job, jl)
            elif job.job_type == JobType.GENERATE_REPORT:
                generate_report(db, job, jl)
            job.status = JobStatus.SUCCEEDED
            job.progress = 100
            job.finished_at = utcnow()
            jl.step("done", 100)
        except Exception as exc:
            db.rollback()
            job = db.get(ProcessingJob, job_id)
            if job is not None:
                job.status = JobStatus.FAILED
                job.error = f"{type(exc).__name__}: {exc}"[:2000]
                job.finished_at = utcnow()
                entries = list(job.log or [])
                entries.append(
                    {"at": utcnow().isoformat(), "step": "failed", "error": job.error, "trace": traceback.format_exc()[-1500:]}
                )
                job.log = entries
                if job.document_id:
                    doc = db.get(Document, job.document_id)
                    if doc:
                        doc.status = DocumentStatus.FAILED
                        doc.status_detail = job.error
                db.commit()
            log.warning("job %s failed: %s", job_id, exc)


def poll_once() -> bool:
    """Run the oldest queued job. Returns False when the queue is empty. Used by `bearcase worker`."""
    with session_scope() as db:
        job = db.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.status == JobStatus.QUEUED)
            .order_by(ProcessingJob.created_at, ProcessingJob.sequence)
            .limit(1)
        )
        job_id = job.id if job else None
    if job_id is None:
        return False
    run_job(job_id)
    return True
