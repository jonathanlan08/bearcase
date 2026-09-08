"""Measurement routes for one deal: where the buyer is in the workflow, what the deal has cost so far, and the
reviewed claims as a dataset. Everything is read from persisted rows; nothing here calls a model."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from bearcase.api.deps import DbDep, DealDep, OwnerDealDep, UserDep
from bearcase.audit import record
from bearcase.chat.providers import PRICING_NOTE, estimate_cost
from bearcase.models import (
    AuditEvent,
    ChatMessage,
    ChatThread,
    Claim,
    Deal,
    Document,
    DocumentVersion,
    ReviewDecision,
)
from bearcase.ingest.statement_mapper import map_income_statement
from bearcase.models import Adjustment, Evidence, Finding, FinancialMetric
from bearcase.models.enums import AdjustmentDecision, ClaimStatus, DocumentStatus, DocumentType, EvidenceKind, FindingKind, FindingStatus, LinkRole
from bearcase.pipeline.analyze import _chunks_from_evidence
from bearcase.reports.resolution import resolution_for

router = APIRouter(tags=["insights"])

# The four steps of the one workflow the product is built around. The key is fixed by the contract with the web
# app; href_key names the page that completes the step (documents, overview, claims, questions).
PROGRESS_STEPS: tuple[tuple[str, str, str], ...] = (
    ("documents", "Upload the seller's documents", "documents"),
    ("findings", "Review the important discrepancies", "overview"),
    ("evidence", "Inspect the evidence behind one", "claims"),
    ("questions", "Export questions for the seller", "questions"),
)


def _any(db: Session, stmt: Any) -> bool:
    return db.scalar(select(stmt.exists())) is True


@router.get("/deals/{deal_id}/progress")
def progress(deal: DealDep, db: DbDep) -> dict[str, Any]:
    """Which workflow steps this deal has completed. Findings count as reviewed when a person recorded a claim
    decision or received an answer from the assistant (views and failed replies are not counted); evidence when
    the viewer reported an open (fetching a row for a label does not count); questions when the seller
    questions were copied or downloaded."""
    done = {
        "documents": _any(db, select(Document.id).where(Document.deal_id == deal.id, Document.status == DocumentStatus.READY)),
        "findings": _any(db, select(ReviewDecision.id).where(ReviewDecision.deal_id == deal.id))
        or _any(
            db,
            select(ChatMessage.id)
            .join(ChatThread)
            .where(ChatThread.deal_id == deal.id, ChatMessage.role == "assistant", ChatMessage.error.is_(None)),
        ),
        "evidence": _any(
            db, select(AuditEvent.id).where(AuditEvent.deal_id == deal.id, AuditEvent.event_type == "evidence.opened")
        ),
        "questions": _any(
            db,
            select(AuditEvent.id).where(AuditEvent.deal_id == deal.id, AuditEvent.event_type == "seller_questions.exported"),
        ),
    }
    return {"steps": [{"key": key, "label": label, "done": done[key], "href_key": href} for key, label, href in PROGRESS_STEPS]}


@router.get("/deals/{deal_id}/usage")
def usage(deal: DealDep, db: DbDep) -> dict[str, Any]:
    """What this deal has consumed: chat replies with their tokens and an estimated cost from the price table in
    chat/providers.py, the documents processed, and the bytes stored. Messages and by_model count assistant
    replies, the rows that carry usage."""
    replies = db.scalars(
        select(ChatMessage)
        .join(ChatThread, ChatThread.id == ChatMessage.thread_id)
        .where(ChatThread.deal_id == deal.id, ChatMessage.role == "assistant")
        .order_by(ChatMessage.created_at)
    ).all()
    by_model: dict[str, int] = {}
    input_tokens = output_tokens = tool_calls = 0
    cost = 0.0
    unknown: set[str] = set()
    for m in replies:
        by_model[m.model] = by_model.get(m.model, 0) + 1
        u = m.usage or {}
        i, o = int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0)
        input_tokens += i
        output_tokens += o
        tool_calls += len(m.tool_calls or [])
        c = estimate_cost(m.provider, m.model, i, o)
        if c is None:
            unknown.add(f"{m.provider}/{m.model}")
        else:
            cost += c
    versions = db.scalars(
        select(DocumentVersion).join(Document, Document.id == DocumentVersion.document_id).where(Document.deal_id == deal.id)
    ).all()
    current = {d.current_version_id for d in db.scalars(select(Document).where(Document.deal_id == deal.id))}
    current_versions = [v for v in versions if v.id in current]
    note = PRICING_NOTE
    if unknown:
        note += f" No price is known for {', '.join(sorted(unknown))}, so no estimate is shown."
    return {
        "chat": {
            "messages": len(replies),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "tool_calls": tool_calls,
            "by_model": by_model,
        },
        "documents": {
            "count": len(current),
            "bytes": sum(v.size_bytes for v in current_versions),
            "pages": sum(v.page_count or 0 for v in current_versions),
            "rows": sum(v.row_count or 0 for v in current_versions),
        },
        "storage_bytes": sum(v.size_bytes for v in versions),
        "cost_estimate_usd": None if unknown else round(cost, 6),
        "pricing_note": note,
    }


def _num(value: Any) -> str | None:
    return None if value is None else str(value)


def review_dataset_rows(db: Session, deal: Deal) -> list[dict[str, Any]]:
    """One row per claim with at least one reviewer decision: the immutable AI assessment beside the reviewer's
    current decision (or the latest one, an undo, when nothing is current) and the evidence the claim cites.
    Shared by the API export and the `bearcase export-reviews` command."""
    claims = db.scalars(select(Claim).where(Claim.deal_id == deal.id).order_by(Claim.created_at, Claim.id)).all()
    rows: list[dict[str, Any]] = []
    for c in claims:
        if not c.review_decisions:
            continue
        current = next((d for d in reversed(c.review_decisions) if d.is_current), None)
        decision = current or c.review_decisions[-1]
        evidence = []
        for link in sorted(c.links, key=lambda x: (x.role != LinkRole.SOURCE, x.created_at, str(x.id))):
            e = link.evidence
            evidence.append(
                {
                    "id": str(e.id),
                    "role": link.role.value,
                    "document": e.document.display_name if e.document is not None else "",
                    "locator": e.locator or {},
                    "text": e.text[:200],
                }
            )
        rows.append(
            {
                "deal_id": str(deal.id),
                "claim_id": str(c.id),
                "claim_type": c.claim_type.value,
                "claim_text": c.claim_text,
                "claimed_value": _num(c.claimed_value),
                "claimed_unit": c.claimed_unit.value,
                "ai_status": c.status.value,
                "ai_rule": c.status_rule,
                "ai_rationale": c.status_rationale,
                "verified_value": _num(c.verified_value),
                "reviewer_action": decision.action.value,
                "reviewer_status": decision.resulting_status if current is not None else None,
                "reviewer_value": _num(decision.corrected_value),
                "reviewer_note": decision.note,
                "evidence": evidence,
            }
        )
    return rows


def to_jsonl(rows: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


@router.get("/deals/{deal_id}/review-dataset")
def review_dataset(deal: OwnerDealDep, db: DbDep, user: UserDep) -> Response:
    rows = review_dataset_rows(db, deal)
    record(
        db,
        deal_id=deal.id,
        user_id=user.id,
        event_type="review_dataset.exported",
        object_type="deal",
        object_id=deal.id,
        summary=f"Exported {len(rows)} reviewed claim{'s' if len(rows) != 1 else ''} as a dataset",
        payload={"count": len(rows)},
    )
    db.commit()
    slug = "".join(ch if ch.isalnum() else "-" for ch in deal.company_name.lower()).strip("-")[:40] or "deal"
    return Response(
        to_jsonl(rows),
        media_type="application/x-ndjson; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="bearcase-{slug}-reviews.jsonl"'},
    )


@router.get("/deals/{deal_id}/review-queue")
def review_queue(deal: DealDep, db: DbDep) -> dict[str, Any]:
    """The review inbox: everything a person still has to decide, in the order to do it. Four groups, each an
    ordered list of items with the page that settles them. Read from persisted rows; empty groups are still
    returned so the page can say "nothing here"."""
    # 1. Imported figures to confirm: lines the mapper was unsure about, and metrics the pipeline flagged.
    figures: list[dict[str, Any]] = []
    for doc in db.scalars(select(Document).where(Document.deal_id == deal.id, Document.doc_type == DocumentType.FINANCIAL_STATEMENTS)):
        rows = db.scalars(select(Evidence).where(Evidence.document_id == doc.id, Evidence.kind == EvidenceKind.SHEET_ROW).order_by(Evidence.chunk_index)).all()
        smap = map_income_statement(_chunks_from_evidence(rows))
        if smap is None:
            figures.append({"id": f"unmapped:{doc.id}", "title": f"{doc.display_name} was not read as a statement", "detail": "No sheet with an income-statement name and two year columns.", "href_key": "documents"})
            continue
        for key, components in smap.ambiguous.items():
            figures.append({"id": f"sum:{doc.id}:{key}", "title": f"{key.replace('opex_', '').replace('_', ' ').capitalize()} was summed from {len(components)} rows", "detail": " + ".join(components), "href_key": "financials"})
        if smap.scale != 1:
            figures.append({"id": f"scale:{doc.id}", "title": f"Values were multiplied by {smap.scale:,} from the sheet title", "detail": f"Sheet {smap.sheet}: confirm the scale is right before relying on any figure.", "href_key": "financials"})
    for m in db.scalars(select(FinancialMetric).where(FinancialMetric.deal_id == deal.id, FinancialMetric.requires_review.is_(True)).order_by(FinancialMetric.created_at)):
        figures.append({"id": f"metric:{m.id}", "title": f"{m.label} needs a look", "detail": "; ".join(m.notes) if getattr(m, "notes", None) else (m.formula or "Flagged by the pipeline."), "href_key": "financials"})
    # 2. Discrepancies to review: claims the documents contradict, leave open, or that need a human call, with no decision yet.
    discrepancies: list[dict[str, Any]] = []
    order = {ClaimStatus.CONTRADICTED: 0, ClaimStatus.REVIEW_REQUIRED: 1, ClaimStatus.UNSUPPORTED: 2}
    claims = db.scalars(select(Claim).where(Claim.deal_id == deal.id, Claim.status.in_(list(order)))).all()
    decided = {d.claim_id for d in db.scalars(select(ReviewDecision).where(ReviewDecision.deal_id == deal.id, ReviewDecision.is_current.is_(True)))}
    for c in sorted(claims, key=lambda c: (order[c.status], c.created_at)):
        if c.id in decided:
            continue
        discrepancies.append({"id": str(c.id), "title": c.claim_text[:140], "detail": c.status_rationale or "", "status": c.status.value, "href_key": "claims", "claim_id": str(c.id)})
    # 3. Add-back decisions the rules made and nobody has confirmed.
    adjustments: list[dict[str, Any]] = []
    for a in db.scalars(select(Adjustment).where(Adjustment.deal_id == deal.id).order_by(Adjustment.sort_order)):
        if a.decided_by_user_id is None and a.decision in (AdjustmentDecision.ACCEPTED, AdjustmentDecision.REVIEW_REQUIRED):
            adjustments.append({"id": str(a.id), "title": f"{a.label}: rule said {a.decision.value.replace('_', ' ')}", "detail": a.decision_rationale or "", "href_key": "financials", "adjustment_id": str(a.id)})
    # 4. Missing documents to request.
    missing: list[dict[str, Any]] = []
    for f in db.scalars(select(Finding).where(Finding.deal_id == deal.id, Finding.kind == FindingKind.MISSING_DOCUMENT, Finding.status == FindingStatus.OPEN).order_by(Finding.created_at)):
        missing.append({"id": str(f.id), "title": f.title, "detail": f.detail, "resolution": resolution_for(f, None), "href_key": "questions"})
    groups = [
        {"key": "figures", "title": "Confirm these imported figures", "items": figures},
        {"key": "discrepancies", "title": "Review these discrepancies", "items": discrepancies},
        {"key": "adjustments", "title": "Confirm these add-back decisions", "items": adjustments},
        {"key": "missing", "title": "Resolve these missing documents", "items": missing},
    ]
    return {"groups": groups, "total": sum(len(g["items"]) for g in groups)}
