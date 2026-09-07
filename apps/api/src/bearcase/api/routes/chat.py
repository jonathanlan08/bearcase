from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bearcase.api.deps import DbDep, DealDep, UserDep
from bearcase.chat.providers import (
    MOCK_BACKEND,
    REGISTRY,
    models_for,
    public_options,
    resolve_chat_backend,
    validate_model_id,
)
from bearcase.chat.service import stream_reply
from bearcase.config import get_settings
from bearcase.models import ChatMessage, ChatThread
from bearcase.models.base import utcnow

router = APIRouter(tags=["chat"])

# A mix of deal questions and general ones: the assistant answers both, and the labels differ by scope.
SUGGESTED = [
    "Why was adjusted EBITDA reduced?",
    "What are the biggest risks?",
    "Explain DSCR like I'm new to this",
    "Draft five questions for the seller about customer concentration",
    "What happens to DSCR if we lose the largest customer?",
    "Which documents are missing?",
]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    thread_id: uuid.UUID | None = None
    model: str | None = Field(
        default=None,
        description="Model id for this request: one of the ids the chat config endpoint lists for the connected provider.",
    )


def month_window(now: datetime | None = None) -> tuple[datetime, date]:
    """Start of the current calendar month (UTC) and the first day of the next one."""
    now = now or utcnow()
    start = datetime(now.year, now.month, 1, tzinfo=UTC)
    resets = date(now.year + 1, 1, 1) if now.month == 12 else date(now.year, now.month + 1, 1)
    return start, resets


def chat_budget(db: Session, user_id: uuid.UUID, limit: int) -> dict:
    """Assistant answers the user has received this month across every deal they asked in (demo visitors count
    too), the limit, and the date the count resets."""
    start, resets = month_window()
    used = (
        db.scalar(
            select(func.count(ChatMessage.id))
            .join(ChatThread, ChatThread.id == ChatMessage.thread_id)
            .where(
                ChatThread.user_id == user_id,
                ChatMessage.role == "assistant",
                ChatMessage.created_at >= start,
                ChatMessage.error.is_(None),  # a failed or stopped reply is not an answer
            )
        )
        or 0
    )
    return {"limit": limit, "used": used, "resets_on": resets.isoformat()}


def budget_exhausted_detail(budget: dict) -> str:
    resets = date.fromisoformat(budget["resets_on"])
    return f"You have used this month's {budget['limit']} assistant answers. The budget resets on {resets:%B} {resets.day}, {resets.year}."


def _thread_out(t: ChatThread) -> dict:
    return {
        "id": str(t.id),
        "title": t.title or "New conversation",
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
        "message_count": len(t.messages),
    }


def _message_out(m) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": str(m.id),
        "role": m.role,
        "content": m.content,
        "citations": {"evidence": [], "metrics": [], **(m.citations or {})},
        "tool_calls": m.tool_calls or [],
        "grounded": m.grounded,
        "provider": m.provider,
        "model": m.model,
        "label": REGISTRY[m.provider].label if m.provider in REGISTRY else MOCK_BACKEND.label,
        "error": m.error,
        "created_at": m.created_at.isoformat(),
    }


@router.get("/deals/{deal_id}/chat/config")
def config(deal: DealDep, db: DbDep, user: UserDep) -> dict:
    """Which backend answers chat and why, the providers a user could connect, and the user's monthly budget.
    Never includes keys."""
    _ = deal
    s = get_settings()
    resolved = resolve_chat_backend(s)
    backend = resolved if resolved.ready else MOCK_BACKEND
    if not resolved.ready:
        note = (
            f"{resolved.label} was requested but is not ready: {resolved.reason}. "
            "Answers come from the rule-based composer until this is fixed."
        )
    elif backend.kind == "mock":
        note = (
            "The rule-based composer is selected (BEARCASE_CHAT_PROVIDER=mock). "
            "Set it to auto and add one model key to .env to connect a model."
            if s.chat_provider == "mock"
            else "No model key is configured, so answers come from the deterministic rule-based composer. "
            "Add one key to .env and restart the API to connect a model."
        )
    else:
        note = (
            f"Live model: answers are drafted by {backend.label} ({backend.model}) from tool results over persisted rows, "
            "and every citation is validated in code."
        )
    # With the picker off (the default) the panel gets one model and no choice: the configured default answers
    # everyone. models_for still validates an explicit override on POST, so a script can name an offered id.
    return {
        "provider": backend.name,
        "label": backend.label,
        "model": backend.model,
        "live": backend.kind != "mock",
        "note": note,
        "suggested": SUGGESTED,
        "models": models_for(backend, s) if s.chat_model_picker else [backend.model],
        "picker": s.chat_model_picker,
        "options": public_options(),
        "budget": chat_budget(db, user.id, s.chat_monthly_request_limit),
    }


@router.get("/deals/{deal_id}/chat/threads")
def threads(deal: DealDep, db: DbDep, user: UserDep) -> list[dict]:
    rows = db.scalars(
        select(ChatThread)
        .where(ChatThread.deal_id == deal.id, ChatThread.user_id == user.id)
        .order_by(ChatThread.updated_at.desc())
        .limit(30)
    ).all()
    return [_thread_out(t) for t in rows]


@router.get("/deals/{deal_id}/chat/threads/{thread_id}")
def thread(deal: DealDep, thread_id: uuid.UUID, db: DbDep, user: UserDep) -> dict:
    t = db.scalar(
        select(ChatThread).where(ChatThread.id == thread_id, ChatThread.deal_id == deal.id, ChatThread.user_id == user.id)
    )
    if t is None:
        raise HTTPException(404, "Thread not found.")
    return {**_thread_out(t), "messages": [_message_out(m) for m in t.messages]}


@router.delete("/deals/{deal_id}/chat/threads/{thread_id}", status_code=204)
def delete_thread(deal: DealDep, thread_id: uuid.UUID, db: DbDep, user: UserDep) -> None:
    t = db.scalar(
        select(ChatThread).where(ChatThread.id == thread_id, ChatThread.deal_id == deal.id, ChatThread.user_id == user.id)
    )
    if t is None:
        raise HTTPException(404, "Thread not found.")
    db.delete(t)
    db.commit()


@router.post("/deals/{deal_id}/chat")
def chat(deal: DealDep, body: ChatRequest, db: DbDep, user: UserDep) -> StreamingResponse:
    """Server-Sent Events: meta, tool, text, switch, citations, done, error (see chat/service.py)."""
    budget = chat_budget(db, user.id, get_settings().chat_monthly_request_limit)
    if budget["used"] >= budget["limit"]:
        raise HTTPException(429, budget_exhausted_detail(budget))
    if body.model is not None:
        if not validate_model_id(body.model):
            raise HTTPException(400, "Unknown model id.")
        s = get_settings()
        resolved = resolve_chat_backend(s)
        backend = resolved if resolved.ready else MOCK_BACKEND
        # A live backend only ever runs an id the config endpoint offered, so a request cannot bill the
        # operator's key for an arbitrary model. The rule-based composer ignores the field.
        if backend.kind != "mock" and body.model not in models_for(backend, s):
            raise HTTPException(400, "Model is not offered for the connected provider.")
    if body.thread_id:
        t = db.scalar(
            select(ChatThread).where(
                ChatThread.id == body.thread_id, ChatThread.deal_id == deal.id, ChatThread.user_id == user.id
            )
        )
        if t is None:
            raise HTTPException(404, "Thread not found.")
    else:
        t = ChatThread(deal_id=deal.id, user_id=user.id)
        db.add(t)
        db.commit()
    gen = stream_reply(db, deal, t, user.id, body.message.strip(), model=body.model)
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
