"""Questions for the seller: the deterministic list a buyer takes into the next conversation, and its export.

The list is built by `reports.assemble.build_seller_questions`, the same function the report's "Management
questions" section uses, so the page, the file, and the report always agree. No model is involved."""

from __future__ import annotations

import uuid

from typing import Any

from fastapi import APIRouter, HTTPException, Response

from bearcase.api.deps import EditorDealDep, DbDep, DealDep, UserDep
from bearcase.api.schemas import CustomQuestionRequest, SellerReplyRequest
from sqlalchemy import select
from sqlalchemy.orm import Session

from bearcase.audit import record
from bearcase.models import Deal, SellerReply, CustomQuestion, Evidence
from bearcase.reports.assemble import build_seller_questions

router = APIRouter(tags=["seller-questions"])

SEVERITY_HEADINGS = {
    "critical": "Ask first",
    "high": "High priority",
    "medium": "Medium priority",
    "low": "Low priority",
}
KIND_LABELS = {
    "contradiction": "Contradiction",
    "unsupported": "Unsupported statement",
    "missing_document": "Missing document",
    "covenant": "Debt coverage",
    "concentration": "Customer concentration",
    "risk": "Contract risk",
    "integrity": "Document integrity",
}


def _slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")[:40] or "deal"


def _grouped(questions: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    for severity, heading in SEVERITY_HEADINGS.items():
        rows = [q for q in questions if q["severity"] == severity]
        if rows:
            groups.append((heading, rows))
    return groups


def _preamble(deal: Deal, generated_from: dict[str, int]) -> str:
    fictional = "Fictional demonstration data. " if deal.is_demo else ""
    return (
        f"{fictional}BearCase checked the seller's documents for {deal.company_name} and drew these questions from "
        f"{generated_from['findings']} findings and {generated_from['claims']} seller statements. Each question says which "
        "document it comes from; the note under it says what an answer would settle. Sources are documents in the deal "
        "room, not opinions. BearCase does not provide financial, legal, tax, or investment advice."
    )


OUTCOME_LABEL = {"answered": "Answered", "dodged": "Not answered", "needs_document": "Document requested"}


def to_markdown(deal: Deal, data: dict[str, Any]) -> str:
    lines = [f"# Questions for the seller: {deal.company_name}", "", _preamble(deal, data["generated_from"]), ""]
    replies = data.get("replies", {})
    n = 0
    for heading, rows in _grouped(data["questions"]):
        lines.extend([f"## {heading}", ""])
        for q in rows:
            n += 1
            lines.append(f"{n}. **{q['question']}**  ")
            lines.append(f"   {KIND_LABELS.get(q['kind'], q['kind'])}. {q['why']}  ")
            if q["document_names"]:
                lines.append(f"   Documents: {', '.join(q['document_names'])}")
            rep = replies.get(q["id"])
            if rep:
                lines.append(f"   Seller's reply ({OUTCOME_LABEL.get(rep['outcome'], rep['outcome'])}): {rep['reply_text']}")
            lines.append("")
    if n == 0:
        lines.extend(["No open questions: every seller statement was supported and no document was missing.", ""])
    return "\n".join(lines)


def to_text(deal: Deal, data: dict[str, Any]) -> str:
    lines = [f"Questions for the seller: {deal.company_name}", "", _preamble(deal, data["generated_from"]), ""]
    n = 0
    for heading, rows in _grouped(data["questions"]):
        lines.extend([heading, "-" * len(heading), ""])
        for q in rows:
            n += 1
            lines.append(f"{n}. {q['question']}")
            lines.append(f"   {KIND_LABELS.get(q['kind'], q['kind'])}. {q['why']}")
            if q["document_names"]:
                lines.append(f"   Documents: {', '.join(q['document_names'])}")
            lines.append("")
    if n == 0:
        lines.extend(["No open questions: every seller statement was supported and no document was missing.", ""])
    return "\n".join(lines)


@router.get("/deals/{deal_id}/seller-questions")
def seller_questions(deal: DealDep, db: DbDep) -> dict[str, Any]:
    return build_seller_questions(db, deal)


@router.get("/deals/{deal_id}/seller-questions/export")
def export_seller_questions(
    deal: DealDep, db: DbDep, user: UserDep, format: str = "md", ids: str | None = None
) -> Response:
    """The questions as a file. `ids` (comma-separated question ids from the list) limits the export to the
    ticked questions, so what leaves the workspace is exactly what the page shows as selected."""
    if format not in {"md", "txt"}:
        raise HTTPException(400, "format must be md or txt.")
    data = build_seller_questions(db, deal)
    data = {**data, "replies": latest_replies(db, deal.id)}
    if ids is not None:
        wanted = {i.strip() for i in ids.split(",") if i.strip()}
        data = {**data, "questions": [q for q in data["questions"] if q["id"] in wanted]}
    count = len(data["questions"])
    record(
        db,
        deal_id=deal.id,
        user_id=user.id,
        event_type="seller_questions.exported",
        object_type="deal",
        object_id=deal.id,
        summary=f"Exported {count} question{'s' if count != 1 else ''} for the seller ({format})",
        payload={"count": count, "format": format, "generated_from": data["generated_from"]},
    )
    db.commit()
    filename = f"bearcase-{_slug(deal.company_name)}-seller-questions.{format}"
    body = to_markdown(deal, data) if format == "md" else to_text(deal, data)
    return Response(
        body,
        media_type="text/markdown; charset=utf-8" if format == "md" else "text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def latest_replies(db: Session, deal_id: uuid.UUID) -> dict[str, dict[str, Any]]:
    """The current reply per question id (the newest row wins)."""
    out: dict[str, dict[str, Any]] = {}
    for r in db.scalars(select(SellerReply).where(SellerReply.deal_id == deal_id).order_by(SellerReply.created_at)):
        out[r.question_id] = {
            "id": str(r.id),
            "question_id": r.question_id,
            "reply_text": r.reply_text,
            "outcome": r.outcome,
            "by": r.user.display_name if r.user else None,
            "created_at": r.created_at.isoformat(),
        }
    return out


@router.get("/deals/{deal_id}/seller-replies")
def list_seller_replies(deal: DealDep, db: DbDep) -> dict[str, Any]:
    """What the seller has said back so far, keyed by question id, plus totals by outcome."""
    replies = latest_replies(db, deal.id)
    totals = {"answered": 0, "dodged": 0, "needs_document": 0}
    for r in replies.values():
        totals[r["outcome"]] = totals.get(r["outcome"], 0) + 1
    return {"replies": replies, "totals": totals}


@router.post("/deals/{deal_id}/seller-replies", status_code=201)
def record_seller_reply(deal: EditorDealDep, body: SellerReplyRequest, db: DbDep, user: UserDep) -> dict[str, Any]:
    """Record what the seller replied to one question and how the buyer reads it. Additive: a later reply to the
    same question supersedes without deleting. The question's text is stored with it, so the record survives a
    re-analysis that renumbers or drops the question."""
    if not (body.question_id.startswith("finding:") or body.question_id.startswith("claim:")):
        raise HTTPException(422, "question_id must be a finding:<id> or claim:<id> from the questions list.")
    row = SellerReply(deal_id=deal.id, user_id=user.id, question_id=body.question_id, question_text=body.question_text, reply_text=body.reply_text, outcome=body.outcome)
    db.add(row)
    db.flush()
    record(
        db,
        deal_id=deal.id,
        user_id=user.id,
        event_type="seller_reply.recorded",
        object_type="seller_reply",
        object_id=row.id,
        summary=f"Recorded the seller's reply ({OUTCOME_LABEL.get(body.outcome, body.outcome)}) to: {body.question_text[:90]}",
        payload={"question_id": body.question_id, "outcome": body.outcome},
    )
    db.commit()
    return latest_replies(db, deal.id)[body.question_id]


@router.post("/deals/{deal_id}/seller-questions/custom", status_code=201)
def add_custom_question(deal: EditorDealDep, body: CustomQuestionRequest, db: DbDep, user: UserDep) -> dict[str, Any]:
    """Save a question a person wrote or edited (often drafted with the assistant). It joins the generated list and
    the export under "Written by the reviewer"; cited evidence must belong to this deal."""
    if body.evidence_ids:
        owned = {e for e in db.scalars(select(Evidence.id).where(Evidence.deal_id == deal.id, Evidence.id.in_(body.evidence_ids)))}
        if owned != set(body.evidence_ids):
            raise HTTPException(422, "An evidence id does not belong to this deal.")
    row = CustomQuestion(deal_id=deal.id, user_id=user.id, question=body.question.strip(), why=(body.why or "").strip() or None, severity=body.severity, evidence_ids=[str(e) for e in body.evidence_ids], source_message_id=body.source_message_id)
    db.add(row)
    db.flush()
    record(db, deal_id=deal.id, user_id=user.id, event_type="seller_question.added", object_type="custom_question", object_id=row.id, summary=f"Added a question for the seller: {row.question[:90]}", payload={"severity": row.severity, "from_chat": row.source_message_id is not None})
    db.commit()
    return {"id": f"custom:{row.id}", "question": row.question, "why": row.why, "severity": row.severity}


@router.delete("/deals/{deal_id}/seller-questions/custom/{question_id}", status_code=204)
def remove_custom_question(deal: EditorDealDep, question_id: uuid.UUID, db: DbDep, user: UserDep) -> Response:
    row = db.scalar(select(CustomQuestion).where(CustomQuestion.id == question_id, CustomQuestion.deal_id == deal.id))
    if row is None:
        raise HTTPException(404, "Question not found.")
    record(db, deal_id=deal.id, user_id=user.id, event_type="seller_question.removed", object_type="custom_question", object_id=row.id, summary=f"Removed the reviewer's question: {row.question[:90]}")
    db.delete(row)
    db.commit()
    return Response(status_code=204)
