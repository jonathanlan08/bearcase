from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from bearcase.api.deps import DbDep, DealDep
from bearcase.api.schemas import AuditOut
from bearcase.models import AuditEvent, User

router = APIRouter(tags=["audit"])


@router.get("/deals/{deal_id}/audit", response_model=list[AuditOut])
def deal_audit(
    deal: DealDep, db: DbDep, event_type: str | None = None, limit: int = Query(default=200, le=1000)
) -> list[AuditOut]:
    q = select(AuditEvent).where(AuditEvent.deal_id == deal.id).order_by(AuditEvent.created_at.desc()).limit(limit)
    if event_type:
        q = q.where(AuditEvent.event_type.like(f"{event_type}%"))
    users = {u.id: u.display_name for u in db.scalars(select(User))}
    out = []
    for e in db.scalars(q):
        ao = AuditOut.model_validate(e)
        ao.user_name = users.get(e.user_id, "system") if e.user_id else "system"
        out.append(ao)
    return out
