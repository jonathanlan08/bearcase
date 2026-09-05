"""Provider interface and factory."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar

from pydantic import BaseModel

from bearcase.config import get_settings
from bearcase.schemas.ai_v1 import (
    SCHEMA_VERSION,
    ClassificationOutput,
    ExtractionOutput,
    ReportNarrativeOutput,
    VerificationOutput,
)

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class ChunkRef:
    index: int
    kind: str
    locator: dict[str, Any]
    text: str
    doc_type: str = ""
    document_name: str = ""


@dataclass(frozen=True)
class DocumentContext:
    display_name: str
    doc_type: str
    extension: str
    chunks: list[ChunkRef]


@dataclass(frozen=True)
class ClaimContext:
    claim_text: str
    claim_type: str
    claimed_value: str | None
    claimed_unit: str
    period_label: str | None
    claim_doc_type: str
    calculated_value: str | None = None
    calculated_label: str | None = None


@dataclass
class ProviderResult(Generic[T]):
    output: T | None
    raw: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    prompt_version: str = ""
    schema_version: str = SCHEMA_VERSION
    error: str | None = None
    input_hash: str = ""

    @property
    def ok(self) -> bool:
        return self.output is not None and self.error is None


class AIProvider(Protocol):
    name: str
    model: str

    def classify(self, doc: DocumentContext) -> ProviderResult[ClassificationOutput]: ...
    def extract_claims(self, doc: DocumentContext) -> ProviderResult[ExtractionOutput]: ...
    def verify_claim(self, claim: ClaimContext, candidates: list[ChunkRef]) -> ProviderResult[VerificationOutput]: ...
    def draft_narrative(self, material: dict[str, Any]) -> ProviderResult[ReportNarrativeOutput]: ...


def get_provider(name: str | None = None) -> AIProvider:
    settings = get_settings()
    chosen = name or settings.ai_provider
    if chosen == "anthropic":
        from bearcase.ai.anthropic_provider import AnthropicProvider

        return AnthropicProvider(model=settings.ai_model, api_key=settings.anthropic_api_key)
    from bearcase.ai.mock import MockProvider

    return MockProvider()


def render_chunks(chunks: list[ChunkRef], max_chars: int = 60000) -> str:
    lines: list[str] = []
    total = 0
    for c in chunks:
        loc = ", ".join(f"{k}={v}" for k, v in c.locator.items() if k in ("page", "paragraph", "sheet", "row", "record_index"))
        line = f"[{c.index}] ({c.kind}; {loc}) {c.text}"
        total += len(line)
        if total > max_chars:
            lines.append("[... truncated for length ...]")
            break
        lines.append(line)
    return "\n".join(lines)
