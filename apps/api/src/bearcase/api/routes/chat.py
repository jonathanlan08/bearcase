from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from bearcase.api.deps import DbDep, DealDep, UserDep
from bearcase.chat.service import chat_provider_name, stream_reply
from bearcase.config import get_settings
from bearcase.models import ChatThread

router = APIRouter(tags=["chat"])

SUGGESTED = [
    "Why was adjusted EBITDA reduced?",
    "Where does the 18% growth claim come from?",
    "What happens to DSCR if we lose the largest customer?",
    "Which documents are missing?",
    "What are the biggest risks?",
]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    thread_id: uuid.UUID | None = None


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
        "citations": m.citations or {},
        "tool_calls": m.tool_calls or [],
        "grounded": m.grounded,
        "provider": m.provider,
        "model": m.model,
        "error": m.error,
        "created_at": m.created_at.isoformat(),
    }


@router.get("/deals/{deal_id}/chat/config")
def config(deal: DealDep) -> dict:
    _ = deal
    s = get_settings()
    provider = chat_provider_name()
    return {
        "provider": provider,
        "model": s.ai_model if provider == "anthropic" else "rules-v1",
        "suggested": SUGGESTED,
        "note": "Live model: answers are drafted by Claude from tool results over persisted rows and every citation is validated in code."
        if provider == "anthropic"
        else "No Anthropic key is configured, so answers come from the deterministic rule-based composer. Set ANTHROPIC_API_KEY (or BEARCASE_ANTHROPIC_API_KEY) and restart the API for a live model.",
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
    """Server-Sent Events: meta, tool, text, citations, done, error."""
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
    gen = stream_reply(db, deal, t, user.id, body.message.strip())
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
