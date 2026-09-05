"""Seed the fictional Northstar HVAC deal: upload fixtures, process, analyze, and generate a report."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from bearcase.audit import record
from bearcase.config import get_settings
from bearcase.engine.scenarios import ASSUMPTION_SPECS
from bearcase.fixtures import northstar_facts as N
from bearcase.models import Deal, ProcessingJob, Scenario, ScenarioAssumption, User
from bearcase.models.enums import ClaimUnit, JobType, PurchasePriceBasis, ScenarioKind
from bearcase.pipeline.jobs import JobLog, enqueue_job

log = logging.getLogger("bearcase.seed")


def _run_inline(db: Session, job: ProcessingJob) -> None:
    """Execute a queued job synchronously inside the caller's session (used by the seed)."""
    from bearcase.models.base import utcnow
    from bearcase.models.enums import JobStatus
    from bearcase.pipeline.analyze import analyze_deal, generate_report
    from bearcase.pipeline.process_document import process_document

    job.status = JobStatus.RUNNING
    job.started_at = utcnow()
    db.flush()
    jl = JobLog(db, job)
    if job.job_type == JobType.PROCESS_DOCUMENT:
        process_document(db, job, jl)
    elif job.job_type == JobType.ANALYZE_DEAL:
        analyze_deal(db, job, jl)
    else:
        generate_report(db, job, jl)
    job.status = JobStatus.SUCCEEDED
    job.progress = 100
    job.finished_at = utcnow()
    db.flush()


def seed_northstar(db: Session, user: User, fixtures_dir: Path | None = None, generate_report_too: bool = True) -> Deal:
    from bearcase.api.routes.documents import store_document

    fixtures_dir = fixtures_dir or get_settings().fixtures_dir
    if not (fixtures_dir / N.FILES["cim"]).exists():
        from bearcase.fixtures.generate import generate

        generate(fixtures_dir)
    deal = Deal(
        owner_id=user.id,
        company_name=N.COMPANY,
        industry=N.INDUSTRY,
        purchase_price=N.ENTERPRISE_VALUE,
        purchase_price_basis=PurchasePriceBasis.ENTERPRISE_VALUE,
        purchase_date=date.fromisoformat(N.PURCHASE_DATE),
        debt_amount=N.FUNDED_DEBT,
        equity_amount=N.EQUITY,
        interest_rate_pct=N.INTEREST_RATE_PCT,
        amortization_years=N.AMORTIZATION_YEARS,
        payments_per_year=N.PAYMENTS_PER_YEAR,
        covenant_dscr_threshold=N.COVENANT_DSCR,
        is_demo=True,
    )
    db.add(deal)
    db.flush()
    record(
        db,
        deal_id=deal.id,
        user_id=user.id,
        event_type="deal.seeded",
        object_type="deal",
        object_id=deal.id,
        summary="Seeded the fictional Northstar HVAC demonstration deal",
    )
    # Seed scenarios with the documented Northstar assumptions (created before analysis so they are used).
    for i, (kind, key) in enumerate(
        [(ScenarioKind.BASE, "base"), (ScenarioKind.DOWNSIDE, "downside"), (ScenarioKind.SEVERE_DOWNSIDE, "severe_downside")]
    ):
        spec = N.SCENARIOS[key]
        sc = Scenario(deal_id=deal.id, name=spec["name"], kind=kind, description=spec["description"], is_seed=True, sort_order=i)
        db.add(sc)
        db.flush()
        for j, aspec in enumerate(ASSUMPTION_SPECS):
            db.add(
                ScenarioAssumption(
                    scenario_id=sc.id,
                    key=aspec["key"],
                    label=aspec["label"],
                    value=Decimal(spec["assumptions"][aspec["key"]]),
                    unit=ClaimUnit(aspec["unit"]),
                    sort_order=j,
                )
            )
    jobs: list[ProcessingJob] = []
    for key in (
        "cim",
        "financial_statements",
        "acquisition_model",
        "customer_revenue",
        "debt_term_sheet",
        "contract_apex",
        "contract_harbor",
    ):
        path = fixtures_dir / N.FILES[key]
        doc = store_document(db, deal, user.id, path.name, None, path.read_bytes())
        jobs.append(enqueue_job(db, deal_id=deal.id, job_type=JobType.PROCESS_DOCUMENT, document_id=doc.id))
    jobs.append(enqueue_job(db, deal_id=deal.id, job_type=JobType.ANALYZE_DEAL))
    if generate_report_too:
        jobs.append(enqueue_job(db, deal_id=deal.id, job_type=JobType.GENERATE_REPORT))
    db.flush()
    for job in jobs:
        _run_inline(db, job)
    db.flush()
    return deal


def seed_for_demo_user(db: Session) -> Deal:
    from bearcase.auth import get_or_create_demo_user

    user = get_or_create_demo_user(db)
    existing = db.scalar(select(Deal).where(Deal.owner_id == user.id, Deal.is_demo.is_(True)))
    if existing:
        db.delete(existing)
        db.flush()
    return seed_northstar(db, user)
