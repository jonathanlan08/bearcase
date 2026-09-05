"""Status guardrails enforced in code regardless of provider.

- Supported requires at least one resolvable supporting citation.
- Contradicted requires at least one resolvable contradicting citation.
- No citations at all -> Unsupported (absence of evidence is not contradiction).
- Low confidence or mixed evidence -> Review required.
"""

from __future__ import annotations

from dataclasses import dataclass

REVIEW_CONFIDENCE_FLOOR = 0.6


@dataclass(frozen=True)
class GuardedStatus:
    status: str
    rule: str
    rationale_suffix: str = ""


def apply_guardrails(proposed: str, supporting: int, contradicting: int, confidence: float) -> GuardedStatus:
    if supporting == 0 and contradicting == 0:
        if proposed == "unsupported":
            return GuardedStatus("unsupported", "no_evidence_retrieved")
        return GuardedStatus("unsupported", "no_citations_downgrade", "Status downgraded: no resolvable citations were provided.")
    if proposed == "supported" and supporting == 0:
        return GuardedStatus(
            "review_required",
            "supported_without_support",
            "Provider proposed Supported without supporting evidence; sent to review.",
        )
    if proposed == "contradicted" and contradicting == 0:
        return GuardedStatus(
            "review_required",
            "contradicted_without_conflict",
            "Provider proposed Contradicted without contradicting evidence; sent to review.",
        )
    if confidence < REVIEW_CONFIDENCE_FLOOR and proposed in {"supported", "contradicted"}:
        return GuardedStatus(
            "review_required",
            "low_confidence",
            f"Provider confidence {confidence:.2f} is below the {REVIEW_CONFIDENCE_FLOOR:.2f} floor.",
        )
    if proposed == "supported" and contradicting > 0 and supporting > 0 and confidence < 0.85:
        return GuardedStatus("review_required", "mixed_evidence", "Both supporting and contradicting evidence were cited.")
    return GuardedStatus(proposed, "provider_status_accepted")
