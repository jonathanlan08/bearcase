"""Questions for the seller: the deterministic list a buyer takes into the next conversation, and its export.

The list is built by `reports.assemble.build_seller_questions`, the same function the report's "Management
questions" section uses, so the page, the file, and the report always agree. No model is involved."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response

from bearcase.api.deps import DbDep, DealDep, UserDep
from bearcase.audit import record
from bearcase.models import Deal
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


def to_markdown(deal: Deal, data: dict[str, Any]) -> str:
    lines = [f"# Questions for the seller: {deal.company_name}", "", _preamble(deal, data["generated_from"]), ""]
    n = 0
    for heading, rows in _grouped(data["questions"]):
        lines.extend([f"## {heading}", ""])
        for q in rows:
            n += 1
            lines.append(f"{n}. **{q['question']}**  ")
            lines.append(f"   {KIND_LABELS.get(q['kind'], q['kind'])}. {q['why']}  ")
            if q["document_names"]:
                lines.append(f"   Documents: {', '.join(q['document_names'])}")
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
def export_seller_questions(deal: DealDep, db: DbDep, user: UserDep, format: str = "md") -> Response:
    if format not in {"md", "txt"}:
        raise HTTPException(400, "format must be md or txt.")
    data = build_seller_questions(db, deal)
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
