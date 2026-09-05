"""Versioned AI output schemas. Provider output must validate against these before persistence.

SCHEMA_VERSION changes whenever a field is added, removed, or re-typed."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"

ClaimTypeLiteral = Literal[
    "revenue",
    "revenue_growth",
    "customer_concentration",
    "recurring_revenue",
    "churn",
    "adjusted_ebitda",
    "addback",
    "gross_margin",
    "operating_margin",
    "margin_improvement",
    "forecast",
    "contract_term",
    "debt_term",
    "one_time_expense",
    "other",
]
UnitLiteral = Literal["usd", "pct", "multiple", "months", "years", "count", "text"]
StatusLiteral = Literal["supported", "contradicted", "unsupported", "review_required"]
DocTypeLiteral = Literal[
    "cim", "financial_statements", "acquisition_model", "customer_revenue", "debt_term_sheet", "customer_contract", "other"
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClassificationOutput(Strict):
    doc_type: DocTypeLiteral
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(max_length=500)


class ExtractedClaim(Strict):
    key: str = Field(description="stable snake_case slug, unique within the document", max_length=120)
    claim_text: str = Field(description="verbatim text of the claim from the document", max_length=1000)
    claim_type: ClaimTypeLiteral
    metric_key: str | None = Field(default=None, description="engine metric this claim asserts, if numeric", max_length=80)
    period_label: str | None = Field(default=None, max_length=20)
    claimed_value: Decimal | None = None
    claimed_unit: UnitLiteral = "text"
    source_chunk_index: int = Field(ge=0, description="index of the evidence chunk the claim was read from")
    confidence: float = Field(ge=0, le=1)


class ExtractionOutput(Strict):
    claims: list[ExtractedClaim]


class EvidenceJudgement(Strict):
    chunk_index: int = Field(ge=0)
    role: Literal["supporting", "contradicting"]
    note: str = Field(max_length=300)


class VerificationOutput(Strict):
    status: StatusLiteral
    rationale: str = Field(max_length=1200)
    evidence: list[EvidenceJudgement]
    confidence: float = Field(ge=0, le=1)


class NarrativeStatement(Strict):
    text: str = Field(max_length=1200)
    evidence_ids: list[str] = Field(default_factory=list)
    metric_ids: list[str] = Field(default_factory=list)


class NarrativeSection(Strict):
    key: str = Field(max_length=80)
    statements: list[NarrativeStatement]


class ReportNarrativeOutput(Strict):
    sections: list[NarrativeSection]


class AnswerOutput(Strict):
    statements: list[NarrativeStatement]
    confidence: float = Field(ge=0, le=1)
