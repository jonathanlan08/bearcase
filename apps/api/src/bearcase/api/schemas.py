"""API response and request schemas."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator("*", mode="after")
    @classmethod
    def _utc(cls, v: Any) -> Any:
        """Rows are stored in UTC; SQLite hands them back naive. Serialise them with an offset so a browser
        does not read a UTC time as local (the audit trail and the chat thread must agree on when a reply
        happened)."""
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v


class UserOut(Out):
    id: uuid.UUID
    email: str
    display_name: str
    is_demo: bool
    email_verified: bool = False


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=200)


class RegisterRequest(LoginRequest):
    display_name: str = Field(min_length=1, max_length=120)


class TokenRequest(BaseModel):
    """A link token from an email (verification or invitation)."""

    token: str = Field(min_length=16, max_length=200)


class RequestResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class ResetPasswordRequest(TokenRequest):
    password: str = Field(min_length=8, max_length=200)


class MemberInvite(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Literal["viewer", "editor"] = "viewer"

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or v.startswith("@") or v.endswith("@"):
            raise PydanticCustomError("email", "Enter an email address.")
        return v


class MemberOut(BaseModel):
    id: uuid.UUID
    email: str
    role: Literal["viewer", "editor"]
    accepted: bool
    display_name: str | None = None


class MembersOut(BaseModel):
    owner: dict[str, str]
    members: list[MemberOut]
    role: Literal["owner", "editor", "viewer"]
    limit: int


class CheckoutRequest(BaseModel):
    deal_id: uuid.UUID | None = None


def _money(value: Decimal) -> str:
    return f"${value:,.2f}".removesuffix(".00")


class DealCreate(BaseModel):
    """Transaction terms. Every amount must be given: a blank is an error, never zero. Debt plus equity must add
    up to the purchase price, because the engine sizes debt service from purchase_price and debt_amount together
    (`analyze.py` derives debt_pct = debt_amount / price; the scenario engine splits the price by that share)."""

    company_name: str = Field(min_length=1, max_length=200)
    industry: str = Field(min_length=1, max_length=120)
    # Money columns are Numeric(20, 2); rates and ratios are Numeric(8, 4).
    purchase_price: Decimal = Field(gt=0, max_digits=20, decimal_places=2)
    purchase_price_basis: Literal["enterprise_value", "equity_price"] = "enterprise_value"
    purchase_date: date | None = None
    debt_amount: Decimal = Field(ge=0, max_digits=20, decimal_places=2)
    equity_amount: Decimal = Field(ge=0, max_digits=20, decimal_places=2)
    debt_assumed: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=2)
    cash_acquired: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=2)
    interest_rate_pct: Decimal = Field(ge=0, le=40, max_digits=8, decimal_places=4)
    amortization_years: int = Field(ge=1, le=40)
    payments_per_year: int = Field(default=12, ge=1, le=12)
    covenant_dscr_threshold: Decimal | None = Field(default=Decimal("1.25"), ge=0, le=10, max_digits=8, decimal_places=4)

    @field_validator("company_name", "industry")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator(
        "purchase_price",
        "debt_amount",
        "equity_amount",
        "debt_assumed",
        "cash_acquired",
        "interest_rate_pct",
        "amortization_years",
        "payments_per_year",
        mode="before",
    )
    @classmethod
    def _blank_is_an_error(cls, v: Any) -> Any:
        """A blank or null number is reported on its field, never read as zero. A typed string may carry
        thousands separators and a leading dollar sign ("$1,250,000")."""
        if v is None or (isinstance(v, str) and not v.strip()):
            raise PydanticCustomError("missing", "Enter a value; this field cannot be blank.")
        if isinstance(v, str):
            return v.strip().replace(",", "").removeprefix("$").strip()
        return v

    @field_validator("covenant_dscr_threshold", mode="before")
    @classmethod
    def _blank_threshold_means_none(cls, v: Any) -> Any:
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("equity_amount")
    @classmethod
    def _funding_matches_price(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        price, debt = info.data.get("purchase_price"), info.data.get("debt_amount")
        if price is None or debt is None:
            return v  # those fields already carry their own error
        total = debt + v
        if abs(total - price) > price * Decimal("0.01"):
            raise PydanticCustomError(
                "funding_mismatch",
                f"Debt plus equity is {_money(total)}, but the purchase price is {_money(price)}. "
                "The funding must add up to the price (within 1%); adjust the debt, the equity, or the price.",
            )
        return v


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
    role: Literal["owner", "editor", "viewer"] = "owner"
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


class ReviewNoteRequest(BaseModel):
    kind: Literal["conclusion", "assumption", "open_question"] = "conclusion"
    text: str = Field(min_length=5, max_length=4000)
    evidence_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    metric_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    claim_id: uuid.UUID | None = None
    finding_id: uuid.UUID | None = None
    include_in_report: bool = True


class NoteUpdateRequest(BaseModel):
    include_in_report: bool


class CustomQuestionRequest(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
    why: str | None = Field(default=None, max_length=2000)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    evidence_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    source_message_id: uuid.UUID | None = None


class SellerReplyRequest(BaseModel):
    question_id: str = Field(min_length=1, max_length=80)
    question_text: str = Field(min_length=1, max_length=2000)
    reply_text: str = Field(min_length=1, max_length=8000)
    outcome: Literal["answered", "dodged", "needs_document"]


class CorrectionRequest(BaseModel):
    line_key: str = Field(min_length=1, max_length=64)
    period_label: str = Field(min_length=1, max_length=32)
    value: Decimal
    note: str | None = Field(default=None, max_length=2000)


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
    resolution: str | None = None  # what would change this finding (reports/resolution.py)


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
    # The confidence budget: how many claims rest on a person's decision, on rules alone, or on nothing.
    confidence: dict[str, int] = Field(default_factory=dict)


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
