"""Read-only share links for a validated report.

An editor or the owner creates a link; the response carries its path (`/r/{token}`) once, and only the SHA-256
of the token is stored, like the email link tokens in `auth_tokens`. Anyone holding the URL can read that one
report version through `GET /api/shared/reports/{token}` without an account: the report's sections, its
citations resolved to a document name, a location, and a short passage, the company name, and whether the deal is
fictional. Nothing else about the deal is reachable from a token (no documents, chat, notes, members, or other
reports). Unknown, revoked, and expired tokens all answer the same 404.

The management routes go through `get_deal` and the editor role check like every other deal route (invariant 5);
the public route is the single deliberate exception and is rate-limited by client address.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from bearcase.api.deps import DbDep, EditorDealDep, UserDep
from bearcase.api.ratelimit import client_key, enforce
from bearcase.api.schemas import (
    ReportShareCreate,
    ReportShareCreated,
    ReportShareOut,
    SharedEvidence,
    SharedMetric,
    SharedReportOut,
    SharedRow,
    SharedSection,
    SharedStatement,
    SharedTable,
)
from bearcase.audit import record
from bearcase.config import get_settings
from bearcase.models import Deal, Evidence, FinancialMetric, Report, ReportShare, User
from bearcase.models.base import utcnow
from bearcase.models.enums import ReportStatus

router = APIRouter(tags=["report-shares"])

MAX_ACTIVE_SHARES = 10  # per report; revoke one to make another
SNIPPET_CHARS = 240
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-]{20,200}$")
_NOT_FOUND = "This link does not work. It may have been revoked or expired; ask the sender for a new one."


def share_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite hands timestamps back naive; they are stored in UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _is_active(share: ReportShare, now: datetime) -> bool:
    expires = _aware(share.expires_at)
    return share.revoked_at is None and (expires is None or expires > now)


def _share_out(share: ReportShare, names: dict[uuid.UUID, str], now: datetime) -> ReportShareOut:
    out = ReportShareOut.model_validate(share)
    out.created_by = names.get(share.created_by_user_id) if share.created_by_user_id else None
    out.active = _is_active(share, now)
    return out


def _report_in_deal(db: DbDep, deal: Deal, report_id: uuid.UUID) -> Report:
    report = db.scalar(select(Report).where(Report.id == report_id, Report.deal_id == deal.id))
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found.")
    return report


# ---- management (editors and the owner) -------------------------------------------------------------------


@router.post("/deals/{deal_id}/reports/{report_id}/share", response_model=ReportShareCreated, status_code=status.HTTP_201_CREATED)
def create_share(
    deal: EditorDealDep, report_id: uuid.UUID, db: DbDep, user: UserDep, body: ReportShareCreate | None = None
) -> ReportShareCreated:
    report = _report_in_deal(db, deal, report_id)
    if report.status != ReportStatus.VALIDATED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a validated report can be shared. Fix the uncited statements first.")
    now = utcnow()
    active = [s for s in db.scalars(select(ReportShare).where(ReportShare.report_id == report.id)) if _is_active(s, now)]
    if len(active) >= MAX_ACTIVE_SHARES:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"This report already has {MAX_ACTIVE_SHARES} active links. Revoke one to make another."
        )
    days = body.expires_in_days if body else None
    token = secrets.token_urlsafe(32)
    share = ReportShare(
        report_id=report.id,
        deal_id=deal.id,
        created_by_user_id=user.id,
        token_hash=share_token_hash(token),
        expires_at=now + timedelta(days=days) if days else None,
    )
    db.add(share)
    db.flush()
    record(
        db,
        deal_id=deal.id,
        user_id=user.id,
        event_type="report.shared",
        object_type="report",
        object_id=report.id,
        summary=f"Created a read-only link to report version {report.version_no}"
        + (f", expiring in {days} day{'s' if days != 1 else ''}" if days else ""),
        payload={"share_id": str(share.id), "version_no": report.version_no, "expires_in_days": days},
    )
    db.commit()
    db.refresh(share)
    path = f"/r/{token}"
    out = _share_out(share, {user.id: user.display_name}, now)
    return ReportShareCreated(**out.model_dump(), path=path, url=f"{get_settings().app_base_url.rstrip('/')}{path}")


@router.get("/deals/{deal_id}/reports/{report_id}/shares", response_model=list[ReportShareOut])
def list_shares(deal: EditorDealDep, report_id: uuid.UUID, db: DbDep) -> list[ReportShareOut]:
    report = _report_in_deal(db, deal, report_id)
    shares = list(
        db.scalars(select(ReportShare).where(ReportShare.report_id == report.id).order_by(ReportShare.created_at.desc()))
    )
    ids = {s.created_by_user_id for s in shares if s.created_by_user_id}
    names = dict(db.execute(select(User.id, User.display_name).where(User.id.in_(ids))).tuples().all()) if ids else {}
    now = utcnow()
    return [_share_out(s, names, now) for s in shares]


@router.delete("/deals/{deal_id}/reports/{report_id}/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share(deal: EditorDealDep, report_id: uuid.UUID, share_id: uuid.UUID, db: DbDep, user: UserDep) -> Response:
    report = _report_in_deal(db, deal, report_id)
    share = db.scalar(
        select(ReportShare).where(ReportShare.id == share_id, ReportShare.report_id == report.id, ReportShare.deal_id == deal.id)
    )
    if share is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share link not found.")
    if share.revoked_at is None:  # revoking twice is a no-op, not an error
        share.revoked_at = utcnow()
        record(
            db,
            deal_id=deal.id,
            user_id=user.id,
            event_type="report.share_revoked",
            object_type="report",
            object_id=report.id,
            summary=f"Revoked a read-only link to report version {report.version_no}",
            payload={"share_id": str(share.id), "version_no": report.version_no},
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- public read ------------------------------------------------------------------------------------------


def _locator_label(loc: dict[str, Any] | None) -> str:
    """'sheet Income Statement, row 12' or 'page 3, paragraph 2', the same words the report's citation table uses."""
    loc = loc or {}
    if loc.get("aggregate"):
        return f"aggregate ({str(loc['aggregate']).replace('_', ' ')})"
    parts: list[str] = []
    if loc.get("sheet"):
        parts.append(f"sheet {loc['sheet']}")
    if loc.get("page"):
        parts.append(f"page {loc['page']}")
    if loc.get("paragraph"):
        parts.append(f"paragraph {loc['paragraph']}")
    if loc.get("row") is not None:
        parts.append(f"row {loc['row']}")
    return ", ".join(parts)


def _snippet(text: str) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= SNIPPET_CHARS else flat[: SNIPPET_CHARS - 1].rstrip() + "…"


def _ids(values: Any) -> list[str]:
    return [str(v) for v in (values or []) if v]


def _clean_sections(raw: list[dict[str, Any]]) -> list[SharedSection]:
    """Copy only the presentational fields of each stored section; internal ids (claim ids and the like) stay home."""
    out: list[SharedSection] = []
    for s in raw or []:
        table = s.get("table") or {}
        out.append(
            SharedSection(
                key=str(s.get("key", "")),
                title=str(s.get("title", "")),
                kind=str(s.get("kind", "narrative")),
                derived_from=[str(d) for d in s.get("derived_from") or []],
                statements=[
                    SharedStatement(
                        text=str(st.get("text", "")),
                        role=st.get("role"),
                        evidence_ids=_ids(st.get("evidence_ids")),
                        metric_ids=_ids(st.get("metric_ids")),
                    )
                    for st in s.get("statements") or []
                ],
                table=SharedTable(
                    columns=[str(c) for c in table.get("columns") or []],
                    rows=[
                        SharedRow(
                            label=str(r.get("label", "")),
                            cells=[str(c) for c in r.get("cells") or []],
                            evidence_ids=_ids(r.get("evidence_ids")),
                            metric_ids=_ids(r.get("metric_ids")),
                            status=r.get("status"),
                            decision=r.get("decision"),
                            severity=r.get("severity"),
                        )
                        for r in table.get("rows") or []
                    ],
                ),
            )
        )
    return out


def _cited(sections: list[SharedSection]) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    ev: set[uuid.UUID] = set()
    me: set[uuid.UUID] = set()

    def add(target: set[uuid.UUID], values: list[str]) -> None:
        for v in values:
            try:
                target.add(uuid.UUID(v))
            except ValueError:
                continue

    for s in sections:
        for st in s.statements:
            add(ev, st.evidence_ids)
            add(me, st.metric_ids)
        for r in s.table.rows:
            add(ev, r.evidence_ids)
            add(me, r.metric_ids)
    return ev, me


def _public_share(db: DbDep, token: str) -> ReportShare:
    if not _TOKEN_RE.match(token):
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
    share = db.scalar(select(ReportShare).where(ReportShare.token_hash == share_token_hash(token)))
    if share is None or not _is_active(share, utcnow()):
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
    return share


@router.get("/shared/reports/{token}", response_model=SharedReportOut)
def shared_report(token: str, request: Request, response: Response, db: DbDep) -> SharedReportOut:
    # Keyed apart from demo start so reading a shared report never spends a visitor's demo budget.
    enforce(request, f"share:{client_key(request)}")
    share = _public_share(db, token)
    report = db.scalar(select(Report).where(Report.id == share.report_id, Report.deal_id == share.deal_id))
    deal = db.get(Deal, share.deal_id)
    if report is None or deal is None or report.status != ReportStatus.VALIDATED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)

    sections = _clean_sections(report.sections)
    ev_ids, metric_ids = _cited(sections)
    evidence: dict[str, SharedEvidence] = {}
    if ev_ids:
        rows = db.scalars(select(Evidence).where(Evidence.deal_id == deal.id, Evidence.id.in_(ev_ids)))
        for e in rows:
            evidence[str(e.id)] = SharedEvidence(
                document_name=e.document.display_name if e.document is not None else "Document",
                locator=_locator_label(e.locator),
                snippet=_snippet(e.text),
            )
    metrics: dict[str, SharedMetric] = {}
    if metric_ids:
        for m in db.scalars(
            select(FinancialMetric).where(FinancialMetric.deal_id == deal.id, FinancialMetric.id.in_(metric_ids))
        ):
            metrics[str(m.id)] = SharedMetric(label=m.label, period=m.period.label if m.period else None, formula=m.formula)

    validation = report.validation or {}
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Cache-Control"] = "no-store"  # a revoked link must stop working at once, not after a cache expires
    response.headers["Referrer-Policy"] = "no-referrer"
    return SharedReportOut(
        company_name=deal.company_name,
        is_demo=deal.is_demo,
        version_no=report.version_no,
        generated_at=_aware(report.created_at) or report.created_at,
        outcome=report.outcome.value,
        validation={
            "valid": bool(validation.get("valid")),
            "material_statements": int(validation.get("material_statements") or 0),
            "material_cited": int(validation.get("material_cited") or 0),
        },
        provenance={
            "provider": report.provider,
            "model": report.model,
            "prompt_version": report.prompt_version,
            "schema_version": report.schema_version,
            "engine_version": report.engine_version,
        },
        sections=sections,
        evidence=evidence,
        metrics=metrics,
    )
