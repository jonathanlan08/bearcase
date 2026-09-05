from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from bearcase.ai.provider import get_provider
from bearcase.api.deps import DbDep, DealDep, UserDep
from bearcase.api.schemas import Out
from bearcase.audit import record
from bearcase.models import DealQuestion
from bearcase.qa.material import build_material, evidence_and_metric_ids
from bearcase.reports.validate import validate_sections
from bearcase.schemas.ai_v1 import SCHEMA_VERSION

router = APIRouter(tags=["questions"])

SUGGESTED = [
    "Why was adjusted EBITDA reduced?",
    "Where does the 18% growth claim come from, and what do the statements show?",
    "What happens to DSCR if we lose the largest customer?",
    "Which documents are missing from the deal room?",
    "What are the biggest risks in this deal?",
]


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class QuestionOut(Out):
    id: str
    question: str
    intents: list[str]
    statements: list[dict]
    grounded: bool
    validation: dict
    provider: str
    model: str
    prompt_version: str
    error: str | None
    created_at: str


def _out(q: DealQuestion) -> QuestionOut:
    return QuestionOut(
        id=str(q.id),
        question=q.question,
        intents=q.intents,
        statements=q.statements,
        grounded=q.grounded,
        validation=q.validation,
        provider=q.provider,
        model=q.model,
        prompt_version=q.prompt_version,
        error=q.error,
        created_at=q.created_at.isoformat(),
    )


@router.get("/deals/{deal_id}/questions/suggested")
def suggested(deal: DealDep) -> list[str]:
    _ = deal
    return SUGGESTED


@router.get("/deals/{deal_id}/questions", response_model=list[QuestionOut])
def history(deal: DealDep, db: DbDep, limit: int = Query(default=20, le=100)) -> list[QuestionOut]:
    rows = db.scalars(
        select(DealQuestion).where(DealQuestion.deal_id == deal.id).order_by(DealQuestion.created_at.desc()).limit(limit)
    ).all()
    return [_out(q) for q in rows]


@router.post("/deals/{deal_id}/ask", response_model=QuestionOut, status_code=201)
def ask(deal: DealDep, body: AskRequest, db: DbDep, user: UserDep) -> QuestionOut:
    """Citation-first Q&A. Material comes only from persisted rows; the provider drafts; code validates.
    Uncited material statements are removed and the answer is marked not fully grounded."""
    provider = get_provider()
    material = build_material(db, deal, body.question)
    res = provider.answer_question(body.question, material)
    ev_ids, me_ids = evidence_and_metric_ids(db, deal.id)
    statements: list[dict] = []
    if res.ok and res.output is not None:
        statements = [
            {
                "text": s.text,
                "evidence_ids": [e for e in s.evidence_ids if e in ev_ids],
                "metric_ids": [m for m in s.metric_ids if m in me_ids],
            }
            for s in res.output.statements
        ]
    validation = validate_sections([{"key": "answer", "statements": statements, "derived_from": []}], ev_ids, me_ids)
    dropped = 0
    if not validation["valid"]:
        bad = {u["index"] for u in validation["uncited"]}
        statements = [s for i, s in enumerate(statements) if i not in bad]
        dropped = len(bad)
        validation = validate_sections([{"key": "answer", "statements": statements, "derived_from": []}], ev_ids, me_ids)
        validation["dropped_uncited"] = dropped
    q = DealQuestion(
        deal_id=deal.id,
        user_id=user.id,
        question=body.question,
        intents=material["intents"],
        statements=statements,
        grounded=bool(validation["valid"] and statements and dropped == 0),
        validation=validation,
        provider=provider.name,
        model=provider.model,
        prompt_version=res.prompt_version or "n/a",
        schema_version=SCHEMA_VERSION,
        input_hash=res.input_hash,
        error=res.error,
    )
    db.add(q)
    db.flush()
    record(
        db,
        deal_id=deal.id,
        user_id=user.id,
        event_type="deal.asked",
        object_type="deal_question",
        object_id=q.id,
        summary=f"Asked: {body.question[:120]}",
        payload={
            "intents": material["intents"],
            "grounded": q.grounded,
            "statements": len(statements),
            "dropped_uncited": dropped,
            "provider": provider.name,
        },
    )
    db.commit()
    return _out(q)
