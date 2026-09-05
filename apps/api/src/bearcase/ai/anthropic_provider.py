"""Anthropic provider. Structured outputs via messages.parse; document text is data, never instructions."""

from __future__ import annotations

import hashlib
import json
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from bearcase.ai.prompts import ANSWER, CLASSIFY, EXTRACT, NARRATIVE, PROMPT_VERSION, SYSTEM_BASE, VERIFY
from bearcase.ai.provider import ChunkRef, ClaimContext, DocumentContext, ProviderResult, render_chunks
from bearcase.config import get_settings
from bearcase.schemas.ai_v1 import AnswerOutput, ClassificationOutput, ExtractionOutput, ReportNarrativeOutput, VerificationOutput

T = TypeVar("T", bound=BaseModel)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str, api_key: str | None = None):
        s = get_settings()
        self.model = model
        # api_key=None lets the SDK resolve ANTHROPIC_API_KEY / an `ant auth login` profile.
        self.client = anthropic.Anthropic(api_key=api_key, timeout=s.ai_timeout_seconds, max_retries=s.ai_max_retries)
        self.max_output_tokens = s.ai_max_output_tokens

    def _call(self, prompt: str, schema: type[T], *, invalid_retry: bool = True) -> ProviderResult[T]:
        input_hash = hashlib.sha256(prompt.encode()).hexdigest()
        attempts = 2 if invalid_retry else 1
        last_error = "unknown"
        for _ in range(attempts):
            try:
                response = self.client.messages.parse(
                    model=self.model,
                    max_tokens=self.max_output_tokens,
                    system=SYSTEM_BASE,
                    messages=[{"role": "user", "content": prompt}],
                    output_format=schema,
                )
            except anthropic.RateLimitError as exc:
                return ProviderResult(
                    None, error=f"rate_limited: {exc.message}", prompt_version=PROMPT_VERSION, input_hash=input_hash
                )
            except anthropic.APIStatusError as exc:
                return ProviderResult(
                    None,
                    error=f"api_error_{exc.status_code}: {exc.message}",
                    prompt_version=PROMPT_VERSION,
                    input_hash=input_hash,
                )
            except anthropic.APIConnectionError as exc:
                return ProviderResult(
                    None, error=f"connection_error: {exc}", prompt_version=PROMPT_VERSION, input_hash=input_hash
                )
            if response.stop_reason == "refusal":
                return ProviderResult(None, error="refusal", prompt_version=PROMPT_VERSION, input_hash=input_hash)
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "request_id": getattr(response, "_request_id", None),
            }
            parsed = response.parsed_output
            if parsed is None:
                last_error = f"invalid_output: stop_reason={response.stop_reason}"
                continue
            try:
                validated = schema.model_validate(parsed.model_dump() if isinstance(parsed, BaseModel) else parsed)
            except ValidationError as exc:
                last_error = f"invalid_output: {exc.errors()[:3]}"
                continue
            return ProviderResult(validated, validated.model_dump(mode="json"), usage, PROMPT_VERSION, input_hash=input_hash)
        return ProviderResult(None, error=last_error, prompt_version=PROMPT_VERSION, input_hash=input_hash)

    def classify(self, doc: DocumentContext) -> ProviderResult[ClassificationOutput]:
        excerpt = "\n".join(c.text for c in doc.chunks[:60])[:12000]
        return self._call(CLASSIFY.format(display_name=doc.display_name, excerpt=excerpt), ClassificationOutput)

    def extract_claims(self, doc: DocumentContext) -> ProviderResult[ExtractionOutput]:
        return self._call(EXTRACT.format(doc_type=doc.doc_type, chunks=render_chunks(doc.chunks)), ExtractionOutput)

    def verify_claim(self, claim: ClaimContext, candidates: list[ChunkRef]) -> ProviderResult[VerificationOutput]:
        calc_line = (
            f"Calculated by BearCase from primary sources: {claim.calculated_label} = {claim.calculated_value}."
            if claim.calculated_value
            else "No calculated value is available for this claim."
        )
        prompt = VERIFY.format(
            claim_doc_type=claim.claim_doc_type,
            claim_text=claim.claim_text,
            claim_type=claim.claim_type,
            claimed_value=claim.claimed_value or "n/a",
            claimed_unit=claim.claimed_unit,
            period=claim.period_label or "n/a",
            calculated_line=calc_line,
            chunks=render_chunks(candidates),
        )
        return self._call(prompt, VerificationOutput)

    def answer_question(self, question: str, material: dict[str, Any]) -> ProviderResult[AnswerOutput]:
        prompt = ANSWER.format(question=question[:1000], material=json.dumps(material, indent=1, default=str)[:60000])
        return self._call(prompt, AnswerOutput)

    def draft_narrative(self, material: dict[str, Any]) -> ProviderResult[ReportNarrativeOutput]:
        return self._call(NARRATIVE.format(material=json.dumps(material, indent=1, default=str)[:80000]), ReportNarrativeOutput)
