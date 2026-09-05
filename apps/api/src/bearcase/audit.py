"""Audit trail helper. Every state-changing action records an AuditEvent."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from bearcase.models import AuditEvent


def record(
    db: Session,
    *,
    event_type: str,
    object_type: str,
    summary: str,
    deal_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    object_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditEvent:
    ev = AuditEvent(
        deal_id=deal_id,
        user_id=user_id,
        event_type=event_type,
        object_type=object_type,
        object_id=object_id,
        summary=summary[:500],
        payload=payload or {},
    )
    db.add(ev)
    db.flush()
    return ev
