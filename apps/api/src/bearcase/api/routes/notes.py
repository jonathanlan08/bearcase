"""The reviewer's notebook: conclusions, assumptions, and open questions a person writes down with the sources they
rest on. Notes become the first section of the report and the top of the one-page summary, so the same citation rule
applies to them as to every other material statement: a note that states a figure must cite evidence or a
calculation, and the route refuses one that does not."""

from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from bearcase.api.deps import DbDep, DealDep, EditorDealDep, UserDep
from bearcase.api.schemas import NoteUpdateRequest, ReviewNoteRequest
from bearcase.audit import record
from bearcase.models import Claim, Evidence, FinancialMetric, Finding, ReviewNote

router = APIRouter(tags=["notes"])
_FIGURE = re.compile(r"\d|\$|%")
KIND_LABEL = {"conclusion": "Conclusion", "assumption": "Assumption", "open_question": "Open question"}


def note_out(n: ReviewNote) -> dict[str, Any]:
    return {
        "id": str(n.id),
        "kind": n.kind,
        "text": n.text,
        "evidence_ids": [str(e) for e in (n.evidence_ids or [])],
        "metric_ids": [str(m) for m in (n.metric_ids or [])],
        "claim_id": str(n.claim_id) if n.claim_id else None,
        "finding_id": str(n.finding_id) if n.finding_id else None,
        "include_in_report": bool(n.include_in_report),
        "by": n.user.display_name if n.user else None,
        "created_at": n.created_at.isoformat(),
    }


def notes_for(db: Session, deal_id: uuid.UUID) -> list[ReviewNote]:
    return list(db.scalars(select(ReviewNote).where(ReviewNote.deal_id == deal_id).order_by(ReviewNote.created_at)))


@router.get("/deals/{deal_id}/notes")
def list_notes(deal: DealDep, db: DbDep) -> dict[str, Any]:
    rows = notes_for(db, deal.id)
    return {"notes": [note_out(n) for n in rows], "counts": {k: sum(1 for n in rows if n.kind == k) for k in KIND_LABEL}}


@router.post("/deals/{deal_id}/notes", status_code=201)
def add_note(deal: EditorDealDep, body: ReviewNoteRequest, db: DbDep, user: UserDep) -> dict[str, Any]:
    if _FIGURE.search(body.text) and not (body.evidence_ids or body.metric_ids):
        raise HTTPException(422, "A note that states a figure must cite a source. Attach the evidence or calculation it rests on, or leave the figure out.")
    if body.evidence_ids:
        owned = {e for e in db.scalars(select(Evidence.id).where(Evidence.deal_id == deal.id, Evidence.id.in_(body.evidence_ids)))}
        if owned != set(body.evidence_ids):
            raise HTTPException(422, "An evidence id does not belong to this deal.")
    if body.metric_ids:
        owned_m = {m for m in db.scalars(select(FinancialMetric.id).where(FinancialMetric.deal_id == deal.id, FinancialMetric.id.in_(body.metric_ids)))}
        if owned_m != set(body.metric_ids):
            raise HTTPException(422, "A metric id does not belong to this deal.")
    if body.claim_id and db.scalar(select(Claim.id).where(Claim.id == body.claim_id, Claim.deal_id == deal.id)) is None:
        raise HTTPException(422, "The claim does not belong to this deal.")
    if body.finding_id and db.scalar(select(Finding.id).where(Finding.id == body.finding_id, Finding.deal_id == deal.id)) is None:
        raise HTTPException(422, "The finding does not belong to this deal.")
    n = ReviewNote(deal_id=deal.id, user_id=user.id, kind=body.kind, text=body.text.strip(), evidence_ids=[str(e) for e in body.evidence_ids], metric_ids=[str(m) for m in body.metric_ids], claim_id=body.claim_id, finding_id=body.finding_id, include_in_report=body.include_in_report)
    db.add(n)
    db.flush()
    record(db, deal_id=deal.id, user_id=user.id, event_type="note.added", object_type="review_note", object_id=n.id, summary=f"{KIND_LABEL[n.kind]} recorded: {n.text[:90]}", payload={"kind": n.kind, "evidence": len(n.evidence_ids), "metrics": len(n.metric_ids)})
    db.commit()
    return note_out(n)


@router.patch("/deals/{deal_id}/notes/{note_id}")
def update_note(deal: EditorDealDep, note_id: uuid.UUID, body: NoteUpdateRequest, db: DbDep, user: UserDep) -> dict[str, Any]:
    """Include a draft in the report, or pull a note back to a private draft. The text is never edited in place."""
    n = db.scalar(select(ReviewNote).where(ReviewNote.id == note_id, ReviewNote.deal_id == deal.id))
    if n is None:
        raise HTTPException(404, "Note not found.")
    n.include_in_report = body.include_in_report
    record(db, deal_id=deal.id, user_id=user.id, event_type="note.included" if body.include_in_report else "note.drafted", object_type="review_note", object_id=n.id, summary=("Included in the report: " if body.include_in_report else "Kept as a private draft: ") + n.text[:90])
    db.commit()
    return note_out(n)


@router.delete("/deals/{deal_id}/notes/{note_id}", status_code=204)
def remove_note(deal: EditorDealDep, note_id: uuid.UUID, db: DbDep, user: UserDep) -> Response:
    n = db.scalar(select(ReviewNote).where(ReviewNote.id == note_id, ReviewNote.deal_id == deal.id))
    if n is None:
        raise HTTPException(404, "Note not found.")
    record(db, deal_id=deal.id, user_id=user.id, event_type="note.removed", object_type="review_note", object_id=n.id, summary=f"{KIND_LABEL.get(n.kind, 'Note')} removed: {n.text[:90]}")
    db.delete(n)
    db.commit()
    return Response(status_code=204)
