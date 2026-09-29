"""ExtractionRun rows: one per provider invocation, stamped with the provider and model that produced it.

A hybrid call that fell back to the rule-based provider was two invocations, so it writes two rows: the failed
live run (status failed or invalid_output, its error, whatever it returned) and the run that answered, whose
usage names the run it replaced. Claims link to the run that answered."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from bearcase.ai.provider import AIProvider, ProviderResult, result_origin
from bearcase.models import ExtractionRun
from bearcase.models.enums import RunStatus, RunType


def run_status(res: ProviderResult[Any]) -> RunStatus:
    if res.ok:
        return RunStatus.SUCCEEDED
    return RunStatus.INVALID_OUTPUT if (res.error or "").startswith("invalid_output") else RunStatus.FAILED


def _row(
    deal_id: uuid.UUID,
    document_id: uuid.UUID | None,
    run_type: RunType,
    provider: AIProvider,
    res: ProviderResult[Any],
    usage: dict[str, Any],
) -> ExtractionRun:
    name, model = result_origin(provider, res)
    return ExtractionRun(
        deal_id=deal_id,
        document_id=document_id,
        run_type=run_type,
        status=run_status(res),
        provider=name[:40],
        model=model[:80],
        prompt_version=res.prompt_version or "n/a",
        schema_version=res.schema_version,
        input_hash=res.input_hash,
        raw_output=res.raw,
        usage=usage,
        error=res.error,
    )


def record_run(
    db: Session,
    *,
    deal_id: uuid.UUID,
    document_id: uuid.UUID | None,
    run_type: RunType,
    provider: AIProvider,
    res: ProviderResult[Any],
) -> ExtractionRun:
    """Write the run for a result (and first the failed live run it replaced, if any); return the answering run."""
    usage = dict(res.usage)
    failed = res.fallback_from
    if failed is not None:
        failed_run = _row(deal_id, document_id, run_type, provider, failed, dict(failed.usage))
        db.add(failed_run)
        db.flush()
        usage["fallback_from"] = {
            **usage.get("fallback_from", {}),
            "provider": failed_run.provider,
            "model": failed_run.model,
            "run_id": str(failed_run.id),
            "reason": failed.error,
        }
    run = _row(deal_id, document_id, run_type, provider, res, usage)
    db.add(run)
    db.flush()
    return run
