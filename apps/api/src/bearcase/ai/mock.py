"""Deterministic rule-based provider. Needs no API key; drives the demo and the evaluations.

It is honest about what it is: pattern extraction over real document text plus rule-based
comparison. It never fabricates evidence and it returns the same output for the same input.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any

from bearcase.ai.prompts import PROMPT_VERSION
from bearcase.ai.provider import ChunkRef, ClaimContext, DocumentContext, ProviderResult
from bearcase.ai.retrieval import LexicalRetriever, tokens
from bearcase.ingest.injection import contains_instruction_text
from bearcase.schemas.ai_v1 import (
    ClassificationOutput,
    EvidenceJudgement,
    ExtractedClaim,
    ExtractionOutput,
    NarrativeSection,
    NarrativeStatement,
    ReportNarrativeOutput,
    VerificationOutput,
)

_MONEY = r"\$\s?([0-9][0-9,]*(?:\.[0-9]+)?)\s*(million|thousand|k|m)?"
_PCT = r"([0-9]+(?:\.[0-9]+)?)\s?%"


def _money(m: str, scale: str | None) -> Decimal:
    v = Decimal(m.replace(",", ""))
    s = (scale or "").lower()
    if s in ("million", "m"):
        v *= 1_000_000
    elif s in ("thousand", "k"):
        v *= 1_000
    return v


def _period(text: str) -> str | None:
    m = re.search(r"\b(FY\s?20\d{2})\b", text, re.I)
    return m.group(1).upper().replace(" ", "") if m else None


# Each rule: (key, claim_type, metric_key, unit, regex, value_kind, comparator, base_confidence)
RULES: list[tuple[str, Any, Any, Any, re.Pattern[str], str, str | None, float]] = [
    (
        "revenue_fy",
        "revenue",
        "revenue",
        "usd",
        re.compile(r"(?:FY20\d{2}|annual|total) revenue of " + _MONEY, re.I),
        "money",
        None,
        0.9,
    ),
    (
        "revenue_growth_annual",
        "revenue_growth",
        "cagr",
        "pct",
        re.compile(
            r"revenue has grown (?:at )?(?:approximately |about |roughly )?" + _PCT + r" (?:annually|per year|a year)", re.I
        ),
        "pct",
        None,
        0.88,
    ),
    (
        "reported_ebitda",
        "adjusted_ebitda",
        "ebitda_reported",
        "usd",
        re.compile(r"reported EBITDA of " + _MONEY, re.I),
        "money",
        None,
        0.9,
    ),
    (
        "adjusted_ebitda",
        "adjusted_ebitda",
        "ebitda_adjusted_verified",
        "usd",
        re.compile(r"adjusted EBITDA of " + _MONEY, re.I),
        "money",
        None,
        0.9,
    ),
    ("gross_margin", "gross_margin", "gross_margin", "pct", re.compile(r"gross margin of " + _PCT, re.I), "pct", None, 0.9),
    (
        "no_customer_over",
        "customer_concentration",
        "customer_concentration_top1",
        "pct",
        re.compile(r"no (?:single )?customer (?:represents|accounts for|exceeds) (?:more than )?" + _PCT, re.I),
        "pct",
        "lte",
        0.9,
    ),
    (
        "recurring_share",
        "recurring_revenue",
        "recurring_revenue_pct",
        "pct",
        re.compile(r"(?:approximately |about )?" + _PCT + r" of revenue is recurring", re.I),
        "pct",
        None,
        0.88,
    ),
    ("churn_below", "churn", None, "pct", re.compile(r"churn is below " + _PCT, re.I), "pct", "lte", 0.8),
    (
        "contract_term_runs_through",
        "contract_term",
        None,
        "text",
        re.compile(r"agreement runs through [A-Z][a-z]+ \d{1,2}, \d{4}[^.]*", re.I),
        "text",
        None,
        0.8,
    ),
    (
        "temp_labor_one_time",
        "one_time_expense",
        "opex_temporary_labor_recurring",
        "usd",
        re.compile(r"temporary labor of " + _MONEY + r"[^.]*one-time", re.I),
        "money",
        None,
        0.85,
    ),
    ("integration_savings", "addback", None, "usd", re.compile(r"integration savings of " + _MONEY, re.I), "money", None, 0.8),
    ("forecast_revenue", "forecast", None, "usd", re.compile(r"revenue is forecast at " + _MONEY, re.I), "money", None, 0.85),
    (
        "margin_improvement",
        "margin_improvement",
        None,
        "pct",
        re.compile(r"margin improvement to " + _PCT, re.I),
        "pct",
        None,
        0.85,
    ),
    (
        "min_dscr",
        "debt_term",
        "covenant_dscr_threshold",
        "multiple",
        re.compile(r"minimum debt service coverage ratio of ([0-9]+(?:\.[0-9]+)?)x", re.I),
        "number",
        None,
        0.92,
    ),
    (
        "fixed_rate",
        "debt_term",
        "interest_rate_pct",
        "pct",
        re.compile(r"interest rate: " + _PCT + r" fixed", re.I),
        "pct",
        None,
        0.92,
    ),
    (
        "amortization_years",
        "debt_term",
        "amortization_years",
        "years",
        re.compile(r"amortization: ([0-9]+)-year amortization", re.I),
        "number",
        None,
        0.92,
    ),
    (
        "contract_initial_term",
        "contract_term",
        None,
        "text",
        re.compile(r"initial term of this agreement begins [^.]+ and ends [A-Z][a-z]+ \d{1,2}, \d{4}", re.I),
        "text",
        None,
        0.9,
    ),
]

SHEET_RULES: list[tuple[str, Any, Any, Any, re.Pattern[str], str | None, float]] = [
    (
        "model_growth_assumption",
        "forecast",
        "cagr",
        "pct",
        re.compile(r"revenue growth \(FY20\d{2}-FY20\d{2}\) \| " + _PCT, re.I),
        "forward",
        0.85,
    ),
    (
        "model_recurring_share",
        "recurring_revenue",
        "recurring_revenue_pct",
        "pct",
        re.compile(r"recurring revenue share \| " + _PCT, re.I),
        None,
        0.85,
    ),
]


def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


class MockProvider:
    name = "mock"
    model = "rules-v1"

    def classify(self, doc: DocumentContext) -> ProviderResult[ClassificationOutput]:
        text = " ".join(c.text for c in doc.chunks[:40]).lower()
        pick, conf, why = "other", 0.4, "no rule matched"
        for t, kw in (("cim", "information memorandum"), ("debt_term_sheet", "term sheet"), ("customer_contract", "agreement")):
            if kw in text:
                pick, conf, why = t, 0.8, f"contains '{kw}'"
                break
        out = ClassificationOutput(doc_type=pick, confidence=conf, rationale=why)  # type: ignore[arg-type]
        return ProviderResult(out, out.model_dump(), {}, PROMPT_VERSION, input_hash=_hash([c.text for c in doc.chunks]))

    def extract_claims(self, doc: DocumentContext) -> ProviderResult[ExtractionOutput]:
        claims: list[ExtractedClaim] = []
        seen: set[str] = set()
        for c in doc.chunks:
            if contains_instruction_text(c.text):
                continue  # instruction-like text is never a claim; it is flagged elsewhere
            if c.kind == "page_text":
                for key, ctype, metric, unit, rx, vkind, comparator, conf in RULES:
                    m = rx.search(c.text)
                    if not m:
                        continue
                    value: Decimal | None = None
                    if vkind == "money":
                        value = _money(m.group(1), m.group(2) if m.lastindex and m.lastindex >= 2 else None)
                    elif vkind in ("pct", "number"):
                        value = Decimal(m.group(1))
                    sentence = _sentence_around(c.text, m.start())
                    period = (
                        None
                        if metric in ("cagr", "customer_concentration_top1", "recurring_revenue_pct")
                        else (
                            _period(sentence)
                            or (
                                _period(c.text)
                                if metric in ("revenue", "ebitda_reported", "ebitda_adjusted_verified", "gross_margin")
                                else None
                            )
                        )
                    )
                    dedupe = f"{key}|{metric}|{value}|{period}"
                    if dedupe in seen:
                        continue
                    seen.add(dedupe)
                    ukey = f"{key}_{c.index}"
                    claims.append(
                        ExtractedClaim(
                            key=ukey,
                            claim_text=sentence,
                            claim_type=ctype,
                            metric_key=metric,
                            period_label=period,
                            claimed_value=value,
                            claimed_unit=unit,
                            source_chunk_index=c.index,
                            confidence=conf,
                        )
                    )  # type: ignore[arg-type]
                    if comparator:
                        claims[-1] = claims[-1].model_copy(update={"key": ukey + "__" + comparator})
            elif c.kind == "sheet_row":
                for key, ctype, metric, unit, rx, comparator, conf in SHEET_RULES:
                    m = rx.search(c.text)
                    if not m:
                        continue
                    ukey = f"{key}_{c.index}" + (f"__{comparator}" if comparator else "")
                    claims.append(
                        ExtractedClaim(
                            key=ukey,
                            claim_text=c.text.split(": ", 1)[-1],
                            claim_type=ctype,
                            metric_key=metric,
                            period_label="FY2025" if comparator == "forward" else "FY2024",
                            claimed_value=Decimal(m.group(1)),
                            claimed_unit=unit,
                            source_chunk_index=c.index,
                            confidence=conf,
                        )
                    )  # type: ignore[arg-type]
        out = ExtractionOutput(claims=claims)
        return ProviderResult(
            out, out.model_dump(mode="json"), {}, PROMPT_VERSION, input_hash=_hash([c.text for c in doc.chunks])
        )

    def verify_claim(self, claim: ClaimContext, candidates: list[ChunkRef]) -> ProviderResult[VerificationOutput]:
        """Rule-based comparison for non-numeric claims (numeric claims are settled by the engine)."""
        judgements: list[EvidenceJudgement] = []
        status = "unsupported"
        rationale = "No provided evidence addresses this claim."
        confidence = 0.7
        ct = claim.claim_type
        text = claim.claim_text.lower()
        if ct == "contract_term":
            for c in candidates:
                t = c.text.lower()
                if "initial term" in t and "ends" in t:
                    claimed_year = re.search(r"(20\d{2})", claim.claim_text)
                    ev_year = re.search(r"ends [a-z]+ \d{1,2}, (20\d{2})", t)
                    if claimed_year and ev_year and claimed_year.group(1) != ev_year.group(1):
                        judgements.append(
                            EvidenceJudgement(
                                chunk_index=c.index,
                                role="contradicting",
                                note=f"Contract initial term ends in {ev_year.group(1)}, not {claimed_year.group(1)}.",
                            )
                        )
                    else:
                        judgements.append(
                            EvidenceJudgement(
                                chunk_index=c.index, role="supporting", note="Contract term clause matches the stated term."
                            )
                        )
                    if "renews automatically" in t and "automatic" in text:
                        judgements.append(
                            EvidenceJudgement(chunk_index=c.index, role="supporting", note="Automatic renewal clause present.")
                        )
                if "terminate" in t and "convenience" in t and "runs through" in text:
                    judgements.append(
                        EvidenceJudgement(
                            chunk_index=c.index,
                            role="contradicting",
                            note="Customer may terminate for convenience on 60 days' notice; the stated term is not assured.",
                        )
                    )
                if c.kind == "csv_row" and "contract_end=" in t:
                    claimed_year = re.search(r"(20\d{2})(?!.*20\d{2})", claim.claim_text)
                    row_year = re.search(r"contract_end=(20\d{2})", t)
                    if claimed_year and row_year:
                        same = claimed_year.group(1) == row_year.group(1)
                        judgements.append(
                            EvidenceJudgement(
                                chunk_index=c.index,
                                role="supporting" if same else "contradicting",
                                note=f"Customer file records a contract end date in {row_year.group(1)}.",
                            )
                        )
            sup = sum(1 for j in judgements if j.role == "supporting")
            con = sum(1 for j in judgements if j.role == "contradicting")
            if sup and con:
                status, rationale, confidence = (
                    "review_required",
                    "Evidence is mixed: the contract confirms automatic renewal but its initial term and termination rights differ from the statement.",
                    0.75,
                )
            elif con:
                status, rationale, confidence = "contradicted", "The contract conflicts with the stated term.", 0.8
            elif sup:
                status, rationale, confidence = (
                    "supported",
                    "The contract clause and the customer file agree with the statement.",
                    0.85,
                )
        elif ct in ("churn", "forecast", "margin_improvement", "addback"):
            status, rationale = (
                "unsupported",
                f"No document in the deal room provides evidence for this {ct.replace('_', ' ')} statement.",
            )
        else:
            retriever = LexicalRetriever([c.text for c in candidates])
            hits = retriever.search(claim.claim_text, top_k=3)
            overlap = [h for h in hits if len(set(tokens(candidates[h.index].text)) & set(tokens(claim.claim_text))) >= 3]
            if overlap:
                for h in overlap[:2]:
                    judgements.append(
                        EvidenceJudgement(
                            chunk_index=candidates[h.index].index,
                            role="supporting",
                            note="Lexical overlap only; a reviewer must confirm.",
                        )
                    )
                status, rationale, confidence = (
                    "review_required",
                    "Related evidence was found but the rule-based provider cannot confirm the statement.",
                    0.5,
                )
        out = VerificationOutput(status=status, rationale=rationale, evidence=judgements, confidence=confidence)  # type: ignore[arg-type]
        return ProviderResult(
            out,
            out.model_dump(mode="json"),
            {},
            PROMPT_VERSION,
            input_hash=_hash([claim.claim_text, [c.text for c in candidates]]),
        )

    def draft_narrative(self, material: dict[str, Any]) -> ProviderResult[ReportNarrativeOutput]:
        """Template narrative. Every sentence with a number cites the evidence or metric it came from."""
        m = material
        sections: list[NarrativeSection] = []

        def st(text: str, ev: list[str] | None = None, met: list[str] | None = None) -> NarrativeStatement:
            return NarrativeStatement(text=text, evidence_ids=ev or [], metric_ids=met or [])

        exec_s: list[NarrativeStatement] = []
        for c in m.get("contradictions", []):
            exec_s.append(
                st(
                    f"The {c['source']} states {c['claimed']}; the evidence supports {c['verified']}.",
                    c.get("evidence_ids", []),
                    c.get("metric_ids", []),
                )
            )
        if m.get("dscr"):
            d = m["dscr"]
            exec_s.append(
                st(
                    f"Base-case DSCR is {d['base']}x against a {d['threshold']}x covenant; the downside case falls to {d['downside']}x.",
                    [],
                    d.get("metric_ids", []),
                )
            )
        exec_s.append(
            st(
                "The review outcome reflects contradictions between seller statements and primary evidence; it is not a recommendation to proceed or decline.",
                [],
                [],
            )
        )
        sections.append(NarrativeSection(key="executive_summary", statements=exec_s))

        q: list[NarrativeStatement] = []
        for c in m.get("contradictions", []):
            q.append(
                st(
                    f"Explain the basis for the statement that {c['claimed']} given that the {c['evidence_source']} shows {c['verified']}.",
                    c.get("evidence_ids", []),
                    c.get("metric_ids", []),
                )
            )
        for md in m.get("missing_documents", []):
            q.append(st(f"Provide the {md['title'].lower()}: {md['reason']}", [], []))
        sections.append(NarrativeSection(key="management_questions", statements=q))

        n: list[NarrativeStatement] = []
        if m.get("verified_ebitda"):
            v = m["verified_ebitda"]
            n.append(
                st(
                    f"Price the transaction on verified adjusted EBITDA of {v['value']} rather than the seller figure of {v['seller']}.",
                    [],
                    v.get("metric_ids", []),
                )
            )
        if m.get("concentration"):
            k = m["concentration"]
            n.append(
                st(
                    f"Condition closing on an executed extension of the {k['customer']} agreement, which represents {k['pct']} of revenue and may be terminated for convenience.",
                    k.get("evidence_ids", []),
                    k.get("metric_ids", []),
                )
            )
        n.append(st("Require a quality of earnings review of every add-back before final pricing.", [], []))
        sections.append(NarrativeSection(key="negotiation_conditions", statements=n))

        r: list[NarrativeStatement] = []
        for w in m.get("scenario_warnings", []):
            r.append(st(w["message"], [], w.get("metric_ids", [])))
        sections.append(NarrativeSection(key="risk_commentary", statements=r))
        out = ReportNarrativeOutput(sections=sections)
        return ProviderResult(out, out.model_dump(mode="json"), {}, PROMPT_VERSION, input_hash=_hash(material))


def _sentence_around(text: str, pos: int) -> str:
    prev = text.rfind(". ", 0, pos)
    start = prev + 2 if prev >= 0 else 0
    end = text.find(". ", pos)
    end = len(text) if end == -1 else end + 1
    return text[start:end].strip()
