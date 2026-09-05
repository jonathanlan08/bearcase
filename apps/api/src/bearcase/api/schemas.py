"""API response and request schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(Out):
    id: uuid.UUID
    email: str
    display_name: str
    is_demo: bool


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=200)


class RegisterRequest(LoginRequest):
    display_name: str = Field(min_length=1, max_length=120)


class DealCreate(BaseModel):
    company_name: str = Field(min_length=1, max_length=200)
    industry: str = Field(min_length=1, max_length=120)
    purchase_price: Decimal = Field(gt=0)
    purchase_price_basis: Literal["enterprise_value", "equity_price"] = "enterprise_value"
    purchase_date: date | None = None
    debt_amount: Decimal = Field(ge=0)
    equity_amount: Decimal = Field(ge=0)
    debt_assumed: Decimal = Field(default=Decimal("0"), ge=0)
    cash_acquired: Decimal = Field(default=Decimal("0"), ge=0)
    interest_rate_pct: Decimal = Field(ge=0, le=40)
    amortization_years: int = Field(ge=1, le=40)
    payments_per_year: int = Field(default=12, ge=1, le=12)
    covenant_dscr_threshold: Decimal | None = Field(default=Decimal("1.25"), ge=0, le=10)

    @field_validator("company_name", "industry")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class DealOut(Out):
    id: uuid.UUID
    company_name: str
    industry: str
    purchase_price: Decimal
    purchase_price_basis: str
    purchase_date: date | None
    debt_amount: Decimal
    equity_amount: Decimal
    debt_assumed: Decimal
    cash_acquired: Decimal
    interest_rate_pct: Decimal
    amortization_years: int
    payments_per_year: int
    covenant_dscr_threshold: Decimal | None
    status: str
    is_demo: bool
    created_at: datetime
    updated_at: datetime


class DealListItem(DealOut):
    document_count: int = 0
    documents_ready: int = 0
    claim_counts: dict[str, int] = Field(default_factory=dict)


class VersionOut(Out):
    id: uuid.UUID
    version_no: int
    sha256: str
    size_bytes: int
    extension: str
    mime_detected: str | None
    page_count: int | None
    sheet_count: int | None
    row_count: int | None


class DocumentOut(Out):
    id: uuid.UUID
    deal_id: uuid.UUID
    display_name: str
    doc_type: str
    classification_source: str
    classification_confidence: Decimal | None
    status: str
    status_detail: str | None
    version: VersionOut | None = None
    evidence_count: int = 0
    created_at: datetime
    updated_at: datetime


class JobOut(Out):
    id: uuid.UUID
    deal_id: uuid.UUID
    document_id: uuid.UUID | None
    job_type: str
    status: str
    progress: int
    step: str | None
    error: str | None
    log: list[dict[str, Any]]
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class EvidenceOut(Out):
    id: uuid.UUID
    document_id: uuid.UUID
    document_name: str = ""
    doc_type: str = ""
    kind: str
    chunk_index: int
    locator: dict[str, Any]
    text: str
    structured: dict[str, Any] | None
    contains_instruction_text: bool


class LinkOut(BaseModel):
    role: str
    note: str | None
    evidence: EvidenceOut


class DecisionOut(Out):
    id: uuid.UUID
    action: str
    resulting_status: str | None
    corrected_value: Decimal | None
    corrected_unit: str | None
    note: str | None
    user_name: str = ""
    is_current: bool
    created_at: datetime


class ClaimOut(Out):
    id: uuid.UUID
    key: str
    document_id: uuid.UUID
    document_name: str = ""
    doc_type: str = ""
    claim_text: str
    claim_type: str
    metric_key: str | None
    period_label: str | None
    claimed_value: Decimal | None
    claimed_unit: str
    normalized: dict[str, Any]
    confidence: Decimal
    status: str
    effective_status: str = ""
    status_rationale: str | None
    status_rule: str | None
    verified_value: Decimal | None
    verified_unit: str | None
    verified_metric_id: uuid.UUID | None
    source_locator: dict[str, Any] = Field(default_factory=dict)
    source_evidence_id: uuid.UUID | None
    supporting_count: int = 0
    contradicting_count: int = 0
    decisions: list[DecisionOut] = Field(default_factory=list)
    created_at: datetime


class ClaimDetailOut(ClaimOut):
    source_evidence: EvidenceOut | None = None
    links: list[LinkOut] = Field(default_factory=list)
    verified_metric: MetricOut | None = None
    extraction_run: dict[str, Any] | None = None


class ReviewRequest(BaseModel):
    action: Literal["accept", "reject", "correct", "undo"]
    corrected_value: Decimal | None = None
    corrected_unit: Literal["usd", "pct", "multiple", "months", "years", "count", "text"] | None = None
    resulting_status: Literal["supported", "contradicted", "unsupported", "review_required"] | None = None
    note: str | None = Field(default=None, max_length=2000)


class MetricOut(Out):
    id: uuid.UUID
    key: str
    label: str
    value: Decimal | None
    raw_value: str | None
    unit: str
    source: str
    period_label: str | None = None
    formula: str | None
    input_snapshot: dict[str, Any]
    evidence_ids: list[str]
    confidence: Decimal
    requires_review: bool
    missing_inputs: list[str]


class PeriodOut(Out):
    id: uuid.UUID
    label: str
    ordinal: int
    start_date: date | None
    end_date: date | None
    source_sheet: str | None


class AdjustmentOut(Out):
    id: uuid.UUID
    key: str
    label: str
    amount: Decimal
    direction: str
    period_label: str
    seller_rationale: str | None
    decision: str
    decision_rationale: str | None
    decision_rule: str | None
    evidence_ids: list[str]
    decided_by_user_id: uuid.UUID | None
    sort_order: int


class AdjustmentDecisionRequest(BaseModel):
    decision: Literal["accepted", "rejected", "review_required", "unsupported"]
    rationale: str = Field(min_length=1, max_length=2000)


class WaterfallStep(BaseModel):
    label: str
    amount: Decimal
    decision: str
    included: bool
    running_total: Decimal
    adjustment_id: uuid.UUID | None = None


class FinancialsOut(BaseModel):
    periods: list[PeriodOut]
    metrics: list[MetricOut]
    adjustments: list[AdjustmentOut]
    waterfall: list[WaterfallStep]


class AssumptionOut(Out):
    key: str
    label: str
    value: Decimal
    unit: str


class ScenarioResultOut(Out):
    id: uuid.UUID
    run_no: int
    engine_version: str
    input_snapshot: dict[str, Any]
    outputs: dict[str, Any]
    warnings: list[dict[str, Any]]
    input_hash: str
    created_at: datetime


class ScenarioOut(Out):
    id: uuid.UUID
    name: str
    kind: str
    description: str | None
    is_seed: bool
    sort_order: int
    assumptions: list[AssumptionOut]
    latest_result: ScenarioResultOut | None = None
    result_count: int = 0


class ScenarioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    base_on_scenario_id: uuid.UUID | None = None


class AssumptionsUpdate(BaseModel):
    values: dict[str, Decimal]


class ScenarioFactsOut(BaseModel):
    facts: dict[str, Any]
    missing: list[str]
    specs: list[dict[str, Any]]


class SensitivityRequest(BaseModel):
    scenario_id: uuid.UUID
    row_key: str = "largest_customer_loss_pct"
    row_values: list[Decimal] = Field(default_factory=lambda: [Decimal(v) for v in (0, 25, 50, 75, 100)])
    col_key: str = "gross_margin_change_bps"
    col_values: list[Decimal] = Field(default_factory=lambda: [Decimal(v) for v in (0, -100, -200, -300, -400)])
    output: Literal["dscr", "cfads", "ebitda", "fcfe"] = "dscr"


class FindingOut(Out):
    id: uuid.UUID
    key: str
    kind: str
    severity: str
    title: str
    detail: str
    evidence_ids: list[str]
    metric_ids: list[str]
    status: str
    claim_id: uuid.UUID | None
    created_at: datetime


class ReportOut(Out):
    id: uuid.UUID
    deal_id: uuid.UUID
    version_no: int
    status: str
    outcome: str
    sections: list[dict[str, Any]]
    validation: dict[str, Any]
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    engine_version: str
    input_snapshot: dict[str, Any]
    created_at: datetime


class AuditOut(Out):
    id: uuid.UUID
    event_type: str
    object_type: str
    object_id: uuid.UUID | None
    summary: str
    payload: dict[str, Any]
    user_name: str = ""
    created_at: datetime


class DealSummary(BaseModel):
    deal: DealOut
    documents: dict[str, int]
    claim_counts: dict[str, int]
    findings_by_severity: dict[str, int]
    seller_adjusted_ebitda: Decimal | None
    verified_adjusted_ebitda: Decimal | None
    reported_ebitda: Decimal | None
    dscr_by_scenario: list[dict[str, Any]]
    covenant_threshold: Decimal | None
    missing_documents: list[FindingOut]
    top_findings: list[FindingOut]
    latest_report: dict[str, Any] | None
    active_jobs: int
    mode: dict[str, str]


class ProcessResponse(BaseModel):
    job_ids: list[uuid.UUID]
    message: str


class HealthOut(BaseModel):
    status: str
    version: str
    engine_version: str
    provider: str
    model: str
    database: str
    storage: str
