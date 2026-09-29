"""Provider interface and factory."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar

from pydantic import BaseModel

from bearcase.config import get_settings
from bearcase.schemas.ai_v1 import (
    SCHEMA_VERSION,
    AnswerOutput,
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
    provider: str = ""
    """Provider that produced this result, when it differs from the configured one or is worth stating (a
    hybrid provider answers some calls with the rule-based fallback). Empty: the configured provider."""
    model: str = ""
    fallback_from: ProviderResult[Any] | None = None
    """The failed live result this one replaced. Recorded as its own run (see pipeline/runs.py)."""

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
    def answer_question(self, question: str, material: dict[str, Any]) -> ProviderResult[AnswerOutput]: ...


def provider_for_deal(deal: object) -> AIProvider:
    """The provider for work on one deal. Demo deals always use the rule-based reader: their fixtures are the
    ground truth the demo and the eval are built on, the result must not change between visitors, and a demo
    must never spend the operator's model quota. Real deals use the configured provider."""
    return get_provider("mock") if getattr(deal, "is_demo", False) else get_provider()


def get_provider(name: str | None = None) -> AIProvider:
    settings = get_settings()
    chosen = name or settings.ai_provider
    if chosen == "anthropic":
        from bearcase.ai.anthropic_provider import AnthropicProvider

        return AnthropicProvider(model=settings.ai_model, api_key=settings.anthropic_api_key)
    from bearcase.ai.mock import MockProvider

    if chosen in ("groq", "openai_compat"):
        from bearcase.ai.openai_compat_provider import FallbackProvider, OpenAICompatProvider, resolve_extraction_backend

        live = OpenAICompatProvider(resolve_extraction_backend(settings, chosen), settings)
        return FallbackProvider(live, MockProvider()) if settings.ai_fallback_to_mock else live
    return MockProvider()


def result_origin(provider: AIProvider, res: ProviderResult[Any]) -> tuple[str, str]:
    """(provider, model) that actually produced a result: the result's own stamp, else the provider's."""
    return (res.provider or provider.name, res.model or provider.model)


def fallback_note(res: ProviderResult[Any]) -> dict[str, Any] | None:
    """What a fallback result replaced, for audit payloads: provider, model, and the (redacted) reason."""
    failed = res.fallback_from
    if failed is None:
        return None
    return {"provider": failed.provider, "model": failed.model, "reason": failed.error}


def configured_extraction(settings: Any = None) -> tuple[str, str]:
    """(provider, model) the settings select for extraction, by name and model id only; no key, no network."""
    s = settings or get_settings()
    if s.ai_provider == "anthropic":
        return ("anthropic", s.ai_model)
    if s.ai_provider in ("groq", "openai_compat"):
        from bearcase.ai.openai_compat_provider import resolve_extraction_backend

        return (s.ai_provider, resolve_extraction_backend(s).model)
    return ("mock", "rules-v1")


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
