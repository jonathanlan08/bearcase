"""OpenAI-compatible extraction provider: Groq by default, or any /v1/chat/completions endpoint that accepts
JSON mode (ai_provider=openai_compat with ai_base_url, ai_extraction_model, ai_api_key).

It mirrors the Anthropic provider: the same prompt templates, the same pydantic output schemas, the same
status guardrails downstream (pipeline/analyze.py applies ai/guardrails.py to every provider). Differences:

- The reply is requested as a JSON object (response_format json_object) with the schema in the system prompt,
  then parsed and validated in code. Unknown keys are dropped before validation; claims that fail validation
  are dropped one by one and counted, never repaired into something the model did not say.
- Document text is untrusted data: it sits between <document> tags, and any document tag inside it is
  neutralised so a document cannot close the delimiter and speak with the prompt's authority.
- An extracted claim must quote its source: claim_text has to appear in the cited chunk (or another chunk of the
  same document, which then becomes the source). Anything else is dropped as unquoted.
- A verification may only cite chunks the model was shown; other citations are dropped before the guardrails.
- Numbers the model returns are claims to be checked by the engine, never computed results.
- Free-tier robustness: a per-request timeout, bounded retries with backoff on 429, 5xx, timeouts, and
  connection errors (Retry-After honoured up to a cap), a per-request character budget (documents longer than
  it are split into several extraction requests within render_chunks' 60,000-character budget), and one re-ask
  when the reply is not valid JSON for the schema.
- FallbackProvider answers a failed call with the rule-based provider and stamps the result with who produced it
  and what it replaced, so the run record stays honest (pipeline/runs.py writes both runs).

The key is never logged, returned, or stored: error text is redacted before it leaves this module."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from typing import Any, TypeVar
from urllib.parse import urlsplit

import openai
from pydantic import BaseModel, ValidationError

from bearcase.ai.prompts import (
    ANSWER,
    CLASSIFY,
    EXTRACT,
    JSON_OUTPUT,
    JSON_OUTPUT_VERSION,
    NARRATIVE,
    PROMPT_VERSION,
    SYSTEM_BASE,
    VERIFY,
)
from bearcase.ai.provider import AIProvider, ChunkRef, ClaimContext, DocumentContext, ProviderResult, render_chunks
from bearcase.chat.providers import CUSTOM_LABEL, REGISTRY, ChatBackend, _is_private_host, validate_base_url
from bearcase.config import Settings, get_settings
from bearcase.schemas.ai_v1 import (
    AnswerOutput,
    ClassificationOutput,
    ExtractedClaim,
    ExtractionOutput,
    ReportNarrativeOutput,
    VerificationOutput,
)

T = TypeVar("T", bound=BaseModel)
log = logging.getLogger("bearcase.ai")

GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"
"""Groq documents JSON object mode for this model; it is also the model the chat already uses on Groq."""
RENDER_BUDGET_CHARS = 60000
"""Total document characters one extraction may send, the same budget render_chunks applies for Anthropic."""
RETRY_CAP_SECONDS = 20.0
INVALID_OUTPUT_ATTEMPTS = 2
"""One re-ask when the reply is not valid JSON for the schema, as the Anthropic provider does."""
_DROPPABLE_PARAMS = ("reasoning_effort", "temperature", "response_format")


# ---- backend resolution (settings only, no network) ------------------------------------------------------


def _not_ready(name: str, label: str, model: str, reason: str) -> ChatBackend:
    return ChatBackend(
        name=name,
        label=label,
        kind="openai_compat",
        model=model,
        base_url=None,
        api_key=None,
        ready=False,
        reason=reason,
        free_tier=name == "groq",
    )


def resolve_extraction_backend(settings: Settings | None = None, name: str | None = None) -> ChatBackend:
    """The endpoint, model, and key for ai_provider=groq or openai_compat. A backend that is not ready carries a
    plain reason and no key; the provider then fails every call without a request (and the hybrid falls back)."""
    s = settings or get_settings()
    chosen = name or s.ai_provider
    if chosen == "groq":
        spec = REGISTRY["groq"]
        model = s.ai_extraction_model or GROQ_DEFAULT_MODEL
        if s.ai_base_url:
            problem = validate_base_url(s.ai_base_url)
            if problem:
                return _not_ready("groq", spec.label, model, f"BEARCASE_AI_BASE_URL is not usable: {problem}")
        if not s.groq_api_key:
            return _not_ready("groq", spec.label, model, "set GROQ_API_KEY (or BEARCASE_GROQ_API_KEY)")
        return ChatBackend(
            name="groq",
            label=spec.label,
            kind="openai_compat",
            model=model,
            base_url=s.ai_base_url or spec.base_url,
            api_key=s.groq_api_key,
            ready=True,
            reason=None,
            free_tier=True,
        )
    if chosen == "openai_compat":
        model = s.ai_extraction_model or ""
        if not s.ai_base_url:
            return _not_ready(chosen, CUSTOM_LABEL, model, "set BEARCASE_AI_BASE_URL to the server's OpenAI-compatible base URL")
        problem = validate_base_url(s.ai_base_url)
        if problem:
            return _not_ready(chosen, CUSTOM_LABEL, model, problem)
        if not model:
            return _not_ready(chosen, CUSTOM_LABEL, model, "set BEARCASE_AI_EXTRACTION_MODEL to the model id the server expects")
        # Only the dedicated key: another provider's key must never be sent to an operator-chosen host.
        key = s.ai_api_key
        if not key:
            if not _is_private_host(urlsplit(s.ai_base_url).hostname or ""):
                return _not_ready(chosen, CUSTOM_LABEL, model, "set BEARCASE_AI_API_KEY")
            key = "local"  # local servers such as Ollama or LM Studio accept any key
        return ChatBackend(
            name=chosen,
            label=CUSTOM_LABEL,
            kind="openai_compat",
            model=model,
            base_url=s.ai_base_url,
            api_key=key,
            ready=True,
            reason=None,
            free_tier=False,
        )
    raise ValueError(f"not an OpenAI-compatible extraction provider: {chosen}")


# ---- parsing and grounding (pure functions) --------------------------------------------------------------

_DOC_TAG = re.compile(r"<(\s*/?\s*document)", re.I)
_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$")
_SCALE = {"thousand": 1_000, "k": 1_000, "million": 1_000_000, "m": 1_000_000, "mm": 1_000_000, "billion": 10**9, "bn": 10**9}
_NUMBER = re.compile(r"^(-?[0-9]+(?:\.[0-9]+)?)\s*([a-z]*)$")


def neutralize(text: str) -> str:
    """Defuse <document> and </document> inside untrusted text so it cannot close the prompt's delimiter."""
    return _DOC_TAG.sub(lambda m: "‹" + m.group(1), text)


def json_object(text: str | None) -> dict[str, Any] | None:
    """The first JSON object in a reply: plain, fenced, or with stray text around it. None when there is none."""
    if not text:
        return None
    body = _FENCE.sub("", text.strip())
    try:
        value = json.loads(body)
    except json.JSONDecodeError:
        start, end = body.find("{"), body.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(body[start : end + 1])
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def _resolve(node: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    ref = node.get("$ref")
    return defs.get(ref.rsplit("/", 1)[-1], {}) if isinstance(ref, str) else node


def prune(value: Any, node: dict[str, Any], defs: dict[str, Any]) -> Any:
    """Drop keys the schema does not define (a model adding "reasoning" must not sink a valid reply). Values are
    never changed; validation still decides whether what remains is acceptable."""
    node = _resolve(node, defs)
    for combo in ("anyOf", "oneOf", "allOf"):
        for option in node.get(combo, []):
            option = _resolve(option, defs)
            if "properties" in option and isinstance(value, dict):
                return prune(value, option, defs)
            if "items" in option and isinstance(value, list):
                return prune(value, option, defs)
    if isinstance(value, dict) and "properties" in node:
        props = node["properties"]
        return {k: prune(v, props[k], defs) for k, v in value.items() if k in props}
    if isinstance(value, list) and isinstance(node.get("items"), dict):
        return [prune(v, node["items"], defs) for v in value]
    return value


def _schema_parts(schema: type[BaseModel]) -> tuple[dict[str, Any], dict[str, Any]]:
    js = schema.model_json_schema()
    return js, js.get("$defs", {})


def parse_output[M: BaseModel](text: str | None, schema: type[M]) -> tuple[M | None, str | None, dict[str, Any]]:
    """Validate a reply against a schema. Returns (output, error, notes)."""
    data = json_object(text)
    if data is None:
        return None, "invalid_output: the reply is not a JSON object", {}
    js, defs = _schema_parts(schema)
    try:
        return schema.model_validate(prune(data, js, defs)), None, {}
    except ValidationError as exc:
        return None, f"invalid_output: {_brief_errors(exc)}", {}


def _brief_errors(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in e.get('loc', ()))}: {e.get('msg', '')}" for e in exc.errors()[:3])


def clean_number(value: Any) -> Any:
    """A stated figure as a plain number: "$4,200,000", "18%", "4.2 million" become 4200000, 18, 4200000. This is
    parsing what the document says, not calculating; anything else is left for validation to judge."""
    if not isinstance(value, str):
        return value
    text = value.strip().lower().replace(",", "").replace("$", "").replace("%", "").replace("usd", "").strip()
    m = _NUMBER.match(text)
    if not m:
        return value
    try:
        number = Decimal(m.group(1))
    except InvalidOperation:
        return value
    suffix = m.group(2)
    if suffix and suffix not in _SCALE and suffix not in ("x", "pct", "percent"):
        return value
    return number * _SCALE.get(suffix, 1)


_STATED_AMOUNT = re.compile(r"\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(thousand|million|billion|mm|bn|k|m)\b", re.IGNORECASE)


def restore_stated_scale(value: Any, unit: Any, claim_text: Any) -> Any:
    """Models often copy "$12.95 million" as 12.95. When a dollar value equals a figure the quoted sentence states
    with a scale word next to it, return the figure at that scale. This reads the sentence, it does not estimate:
    a value that matches no stated figure is returned unchanged for validation and verification to judge."""
    if unit != "usd" or not isinstance(claim_text, str) or not isinstance(value, (int, float, Decimal)):
        return value
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return value
    for m in _STATED_AMOUNT.finditer(claim_text):
        try:
            stated = Decimal(m.group(1).replace(",", ""))
        except InvalidOperation:
            continue
        if stated == number:
            return number * _SCALE[m.group(2).lower()]
    return value


def parse_extraction(text: str | None) -> tuple[ExtractionOutput | None, str | None, dict[str, Any]]:
    """Extraction is validated claim by claim: one malformed claim is dropped and counted instead of discarding
    every claim in the reply. A reply whose claims all fail is invalid output."""
    data = json_object(text)
    if data is None or not isinstance(data.get("claims"), list):
        return None, "invalid_output: the reply is not a JSON object with a claims list", {}
    js, defs = _schema_parts(ExtractedClaim)
    kept: list[ExtractedClaim] = []
    errors: list[str] = []
    for item in data["claims"]:
        if not isinstance(item, dict):
            errors.append("claim is not an object")
            continue
        item = prune(item, js, defs)
        if "claimed_value" in item:
            item["claimed_value"] = restore_stated_scale(
                clean_number(item["claimed_value"]), item.get("claimed_unit"), item.get("claim_text")
            )
        try:
            kept.append(ExtractedClaim.model_validate(item))
        except ValidationError as exc:
            errors.append(_brief_errors(exc))
    if data["claims"] and not kept:
        return None, f"invalid_output: no claim validated ({errors[0]})", {}
    return ExtractionOutput(claims=kept), None, {"dropped_invalid": len(errors)} if errors else {}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.translate({0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"', 0x2013: "-", 0x2014: "-"})
    return re.sub(r"\s+", " ", text).strip().strip(" .;:\"'")


def ground_claims(claims: list[ExtractedClaim], chunks: list[ChunkRef]) -> tuple[list[ExtractedClaim], dict[str, int]]:
    """Keep a claim only when its claim_text is a quotation from the document: from the cited chunk, or else from
    another chunk, which then becomes the source. Duplicate keys get a numeric suffix (before a __comparator)."""
    by_index = {c.index: _norm(c.text) for c in chunks}
    kept: list[ExtractedClaim] = []
    keys: set[str] = set()
    seen: set[tuple[str, int]] = set()
    notes = {"dropped_unquoted": 0, "repointed": 0, "duplicates": 0}
    for claim in claims:
        quote = _norm(claim.claim_text)
        if len(quote) < 8:
            notes["dropped_unquoted"] += 1
            continue
        source = claim.source_chunk_index
        if quote not in by_index.get(source, ""):
            found = next((i for i, text in by_index.items() if quote in text), None)
            if found is None:
                notes["dropped_unquoted"] += 1
                continue
            source = found
            notes["repointed"] += 1
        if (quote, source) in seen:
            notes["duplicates"] += 1
            continue
        seen.add((quote, source))
        key = claim.key
        if key in keys:
            base, sep, comparator = key.rpartition("__") if "__" in key else (key, "", "")
            n = 2
            while (key := f"{base}_{n}{sep}{comparator}") in keys:
                n += 1
        keys.add(key)
        kept.append(claim.model_copy(update={"source_chunk_index": source, "key": key}))
    return kept, {k: v for k, v in notes.items() if v}


def _line_chars(chunk: ChunkRef) -> int:
    return len(render_chunks([chunk], max_chars=10**9))


def segment_chunks(
    chunks: list[ChunkRef], per_request: int, total: int = RENDER_BUDGET_CHARS
) -> tuple[list[list[ChunkRef]], bool]:
    """Split chunks into request-sized groups, keeping their original indexes so citations stay global. Stops at
    the total budget (returns truncated=True); a single chunk longer than a request is cut to fit."""
    segments: list[list[ChunkRef]] = [[]]
    size = used = 0
    for chunk in chunks:
        chars = _line_chars(chunk)
        if chars > per_request:
            chunk = replace(chunk, text=chunk.text[: max(0, len(chunk.text) - (chars - per_request))])
            chars = per_request
        if used + chars > total:
            return [s for s in segments if s], True
        if segments[-1] and size + chars > per_request:
            segments.append([])
            size = 0
        segments[-1].append(chunk)
        size += chars + 1
        used += chars
    return [s for s in segments if s], False


def _fit(chunks: list[ChunkRef], budget: int) -> list[ChunkRef]:
    shown: list[ChunkRef] = []
    used = 0
    for chunk in chunks:
        chars = _line_chars(chunk)
        if shown and used + chars > budget:
            break
        if chars > budget:
            chunk = replace(chunk, text=chunk.text[: max(0, len(chunk.text) - (chars - budget))])
            chars = budget
        shown.append(chunk)
        used += chars + 1
    return shown


def _add_usage(total: dict[str, Any], usage: dict[str, Any]) -> None:
    for key in ("input_tokens", "output_tokens", "requests", "retries"):
        if key in usage:
            total[key] = total.get(key, 0) + int(usage[key] or 0)
    if usage.get("request_id"):
        total.setdefault("request_ids", []).append(usage["request_id"])


# ---- the provider ----------------------------------------------------------------------------------------


class OpenAICompatProvider:
    """Live provider over an OpenAI-compatible endpoint. Every result is stamped with this provider and model."""

    def __init__(
        self,
        backend: ChatBackend,
        settings: Settings | None = None,
        *,
        client: Any = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        s = settings or get_settings()
        self.backend = backend
        self.name = backend.name
        self.model = backend.model
        self.timeout = s.ai_timeout_seconds
        self.max_retries = s.ai_max_retries
        self.max_output_tokens = s.ai_max_output_tokens
        self.request_chars = s.ai_request_chars
        self.prompt_version = f"{PROMPT_VERSION}/{JSON_OUTPUT_VERSION}"
        self._client = client
        self._sleep = sleep

    @property
    def client(self) -> Any:
        if self._client is None:
            # Retries are ours (bounded, with Retry-After), so the SDK's own ladder is off.
            self._client = openai.OpenAI(
                api_key=self.backend.api_key, base_url=self.backend.base_url, timeout=self.timeout, max_retries=0
            )
        return self._client

    # -- plumbing --

    def _redact(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text).strip()
        key = self.backend.api_key or ""
        if len(key) >= 8:
            text = text.replace(key, "[redacted]")
        return text[:300]

    def _result(
        self,
        output: Any,
        input_hash: str,
        *,
        raw: dict[str, Any] | None = None,
        usage: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ProviderResult[Any]:
        return ProviderResult(
            output,
            raw or {},
            usage or {},
            self.prompt_version,
            error=error,
            input_hash=input_hash,
            provider=self.name,
            model=self.model,
        )

    def _params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "max_tokens": self.max_output_tokens,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        if self.name == "groq" and self.model.startswith("openai/gpt-oss"):
            params["reasoning_effort"] = "low"  # reasoning tokens count against the free tier's per-minute budget
        return params

    def _delay(self, exc: BaseException, attempt: int) -> float:
        response = getattr(exc, "response", None)
        header = response.headers.get("retry-after") if response is not None else None
        try:
            wait = float(header) if header is not None else 2.0**attempt
        except ValueError:
            wait = 2.0**attempt
        return max(0.0, min(RETRY_CAP_SECONDS, wait))

    def _complete(self, system: str, prompt: str) -> tuple[str | None, dict[str, Any], str | None]:
        """One logical request: bounded retries on 429, 5xx, timeouts, and connection errors; a 400 that names
        an optional parameter is retried once without it. Returns (content, usage, error)."""
        if not self.backend.ready:
            return None, {}, f"not_configured: {self.backend.reason}"
        params = self._params()
        attempt = 0
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        while True:
            try:
                response = self.client.chat.completions.create(model=self.model, messages=messages, **params)
            except openai.BadRequestError as exc:
                text = f"{exc.message} {exc.body}".lower()
                if "json_validate_failed" in text or "failed to generate json" in text:
                    # Groq checks JSON mode server-side; treat it like any invalid reply so the call is re-asked.
                    return None, {"retries": attempt}, "invalid_output: the provider could not produce valid JSON"
                dropped = [p for p in _DROPPABLE_PARAMS if p in params and p in text]
                if dropped:
                    for p in dropped:
                        params.pop(p)
                    continue
                return None, {}, f"api_error_400: {self._redact(exc.message)}"
            except openai.APIStatusError as exc:
                status = exc.status_code
                if (status == 429 or status == 408 or status >= 500) and attempt < self.max_retries:
                    self._sleep(self._delay(exc, attempt))
                    attempt += 1
                    continue
                prefix = "rate_limited" if status == 429 else f"api_error_{status}"
                return None, {"retries": attempt}, f"{prefix}: {self._redact(exc.message)}"
            except openai.APIConnectionError as exc:  # includes APITimeoutError
                if attempt < self.max_retries:
                    self._sleep(self._delay(exc, attempt))
                    attempt += 1
                    continue
                kind = "timeout" if isinstance(exc, openai.APITimeoutError) else "connection_error"
                return None, {"retries": attempt}, f"{kind}: {self._redact(str(exc))}"
            usage: dict[str, Any] = {"requests": 1, "retries": attempt}
            u = getattr(response, "usage", None)
            if u is not None:
                usage["input_tokens"] = int(getattr(u, "prompt_tokens", 0) or 0)
                usage["output_tokens"] = int(getattr(u, "completion_tokens", 0) or 0)
            if getattr(response, "id", None):
                usage["request_id"] = str(response.id)
            choices = getattr(response, "choices", None) or []
            content = choices[0].message.content if choices else None
            if not content:
                finish = getattr(choices[0], "finish_reason", None) if choices else None
                return None, usage, f"invalid_output: empty reply ({finish or 'no choices'})"
            return content, usage, None

    def _call(
        self,
        prompt: str,
        schema: type[T],
        parse: Callable[[str | None], tuple[Any, str | None, dict[str, Any]]] | None = None,
    ) -> ProviderResult[Any]:
        js, _ = _schema_parts(schema)
        system = SYSTEM_BASE + JSON_OUTPUT.format(schema=json.dumps(js, separators=(",", ":")))
        input_hash = hashlib.sha256(f"{self.model}\n{system}\n{prompt}".encode()).hexdigest()
        usage: dict[str, Any] = {}
        last_error = "invalid_output: no reply"
        invalid_text = ""
        for _ in range(INVALID_OUTPUT_ATTEMPTS):
            content, call_usage, error = self._complete(system, prompt)
            _add_usage(usage, call_usage)
            if error and not error.startswith("invalid_output"):
                return self._result(None, input_hash, usage=usage, error=error)
            if error:
                last_error = error
                continue
            output, error, notes = (parse or (lambda t: parse_output(t, schema)))(content)
            if output is None:
                last_error, invalid_text = error or last_error, content or ""
                continue
            usage.update(notes)
            return self._result(output, input_hash, raw=output.model_dump(mode="json"), usage=usage)
        # The unparseable reply is kept (truncated) as the record of what the model said.
        return self._result(None, input_hash, raw={"invalid_text": invalid_text[:2000]}, usage=usage, error=last_error)

    # -- AIProvider --

    def classify(self, doc: DocumentContext) -> ProviderResult[ClassificationOutput]:
        excerpt = "\n".join(c.text for c in doc.chunks[:60])[: min(12000, self.request_chars)]
        prompt = CLASSIFY.format(display_name=neutralize(doc.display_name), excerpt=neutralize(excerpt))
        return self._call(prompt, ClassificationOutput)

    def extract_claims(self, doc: DocumentContext) -> ProviderResult[ExtractionOutput]:
        segments, truncated = segment_chunks(doc.chunks, self.request_chars)
        claims: list[ExtractedClaim] = []
        usage: dict[str, Any] = {"segments": len(segments)}
        if truncated:
            usage["truncated"] = True
        hashes: list[str] = []
        model_output: list[dict[str, Any]] = []
        dropped_invalid = 0
        for n, segment in enumerate(segments, start=1):
            prompt = EXTRACT.format(doc_type=doc.doc_type, chunks=neutralize(render_chunks(segment, max_chars=10**9)))
            res = self._call(prompt, ExtractionOutput, parse=parse_extraction)
            _add_usage(usage, res.usage)
            hashes.append(res.input_hash)
            if not res.ok or res.output is None:
                where = f" (request {n} of {len(segments)})" if len(segments) > 1 else ""
                return self._result(None, _combine(hashes), raw=res.raw, usage=usage, error=f"{res.error}{where}")
            dropped_invalid += int(res.usage.get("dropped_invalid", 0))
            model_output.append(res.raw)
            claims.extend(res.output.claims)
        grounded, notes = ground_claims(claims, doc.chunks)
        usage.update(notes)
        if dropped_invalid:
            usage["dropped_invalid"] = dropped_invalid
        out = ExtractionOutput(claims=grounded)
        raw = {**out.model_dump(mode="json"), "model_output": model_output}
        return self._result(out, _combine(hashes), raw=raw, usage=usage)

    def verify_claim(self, claim: ClaimContext, candidates: list[ChunkRef]) -> ProviderResult[VerificationOutput]:
        shown = _fit(candidates, self.request_chars)
        calc_line = (
            f"Calculated by BearCase from primary sources: {claim.calculated_label} = {claim.calculated_value}."
            if claim.calculated_value
            else "No calculated value is available for this claim."
        )
        prompt = VERIFY.format(
            claim_doc_type=claim.claim_doc_type,
            claim_text=neutralize(claim.claim_text),
            claim_type=claim.claim_type,
            claimed_value=claim.claimed_value or "n/a",
            claimed_unit=claim.claimed_unit,
            period=claim.period_label or "n/a",
            calculated_line=calc_line,
            chunks=neutralize(render_chunks(shown, max_chars=10**9)),
        )
        res = self._call(prompt, VerificationOutput)
        if res.ok and res.output is not None:
            allowed = {c.index for c in shown}
            kept = [j for j in res.output.evidence if j.chunk_index in allowed]
            if len(kept) != len(res.output.evidence):
                res.usage["dropped_citations"] = len(res.output.evidence) - len(kept)
                res.output = res.output.model_copy(update={"evidence": kept})
        if len(shown) < len(candidates):
            res.usage["candidates_not_shown"] = len(candidates) - len(shown)
        return res

    def answer_question(self, question: str, material: dict[str, Any]) -> ProviderResult[AnswerOutput]:
        body = json.dumps(material, indent=1, default=str)[: self.request_chars]
        return self._call(ANSWER.format(question=neutralize(question[:1000]), material=neutralize(body)), AnswerOutput)

    def draft_narrative(self, material: dict[str, Any]) -> ProviderResult[ReportNarrativeOutput]:
        body = json.dumps(material, indent=1, default=str)[: self.request_chars]
        return self._call(NARRATIVE.format(material=neutralize(body)), ReportNarrativeOutput)


def _combine(hashes: list[str]) -> str:
    """One input hash for a multi-request extraction (the hash of the per-request hashes)."""
    return hashes[0] if len(hashes) == 1 else hashlib.sha256("\n".join(hashes).encode()).hexdigest()


class FallbackProvider:
    """Hybrid: the live provider answers; when a call fails (not configured, rate limited after retries, 5xx,
    timeout, invalid JSON) the rule-based provider answers that call instead. The returned result names the
    provider that produced it and carries the failed live result in fallback_from, so both runs are recorded."""

    def __init__(self, primary: AIProvider, fallback: AIProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name
        self.model = primary.model
        self.fallback_count = 0

    def _run(self, op: str, *args: Any) -> ProviderResult[Any]:
        res: ProviderResult[Any] = getattr(self.primary, op)(*args)
        if res.ok:
            return res
        backup: ProviderResult[Any] = getattr(self.fallback, op)(*args)
        if not backup.ok:
            return res
        self.fallback_count += 1
        res.provider = res.provider or self.primary.name
        res.model = res.model or self.primary.model
        log.warning("%s/%s %s failed (%s); the rule-based provider answered this call", res.provider, res.model, op, res.error)
        backup.provider = backup.provider or self.fallback.name
        backup.model = backup.model or self.fallback.model
        backup.fallback_from = res
        backup.usage = {
            **backup.usage,
            "fallback_from": {"provider": res.provider, "model": res.model, "reason": res.error},
        }
        return backup

    def classify(self, doc: DocumentContext) -> ProviderResult[ClassificationOutput]:
        return self._run("classify", doc)

    def extract_claims(self, doc: DocumentContext) -> ProviderResult[ExtractionOutput]:
        return self._run("extract_claims", doc)

    def verify_claim(self, claim: ClaimContext, candidates: list[ChunkRef]) -> ProviderResult[VerificationOutput]:
        return self._run("verify_claim", claim, candidates)

    def draft_narrative(self, material: dict[str, Any]) -> ProviderResult[ReportNarrativeOutput]:
        return self._run("draft_narrative", material)

    def answer_question(self, question: str, material: dict[str, Any]) -> ProviderResult[AnswerOutput]:
        return self._run("answer_question", question, material)
