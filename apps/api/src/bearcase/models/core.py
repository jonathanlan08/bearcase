"""Domain model. Twenty-four tables; every deal-owned row is reached through Deal.owner_id or an accepted deal_members row."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bearcase.db import Base
from bearcase.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from bearcase.models.enums import (
    AdjustmentDecision,
    AdjustmentDirection,
    CitationKind,
    ClaimStatus,
    ClaimType,
    ClaimUnit,
    ClassificationSource,
    DealStatus,
    DocumentStatus,
    DocumentType,
    EvidenceKind,
    FindingKind,
    FindingStatus,
    JobStatus,
    JobType,
    LinkRole,
    MemberRole,
    MetricSource,
    PurchaseKind,
    PurchasePriceBasis,
    PurchaseStatus,
    ReportStatus,
    ReviewAction,
    ReviewOutcome,
    RunStatus,
    RunType,
    ScenarioKind,
    Severity,
    TokenPurpose,
)

Money = Numeric(20, 2)
Ratio = Numeric(20, 8)


def _enum(enum_cls, name: str):  # type: ignore[no-untyped-def]
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e], native_enum=False, length=40)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    deals: Mapped[list[Deal]] = relationship(back_populates="owner")

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None


class UserSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_sessions"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user: Mapped[User] = relationship()


class AuthToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single-use link token (email verification, password reset, deal invitation). Only the SHA-256 of the
    random token is stored; the token itself travels once, in the email link."""

    __tablename__ = "auth_tokens"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[TokenPurpose] = mapped_column(_enum(TokenPurpose, "token_purpose"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    user: Mapped[User] = relationship()


class Deal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deals"
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str] = mapped_column(String(120), nullable=False)
    purchase_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    purchase_price_basis: Mapped[PurchasePriceBasis] = mapped_column(
        _enum(PurchasePriceBasis, "purchase_price_basis"), nullable=False
    )
    purchase_date: Mapped[date | None] = mapped_column(Date)
    debt_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    equity_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    debt_assumed: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    cash_acquired: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    interest_rate_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    amortization_years: Mapped[int] = mapped_column(Integer, nullable=False)
    payments_per_year: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    covenant_dscr_threshold: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    status: Mapped[DealStatus] = mapped_column(_enum(DealStatus, "deal_status"), default=DealStatus.DRAFT)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fiscal_year_end_month: Mapped[int] = mapped_column(Integer, default=12, nullable=False)

    owner: Mapped[User] = relationship(back_populates="deals")
    documents: Mapped[list[Document]] = relationship(back_populates="deal", cascade="all, delete-orphan")
    claims: Mapped[list[Claim]] = relationship(back_populates="deal", cascade="all, delete-orphan")
    scenarios: Mapped[list[Scenario]] = relationship(back_populates="deal", cascade="all, delete-orphan")


class DealMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A collaborator on a deal. user_id stays empty until the invitation is accepted by an account whose
    email matches invited_email; get_deal only resolves accepted rows."""

    __tablename__ = "deal_members"
    __table_args__ = (UniqueConstraint("deal_id", "invited_email", name="uq_deal_member_email"),)
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    invited_email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[MemberRole] = mapped_column(_enum(MemberRole, "member_role"), nullable=False)
    invited_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    deal: Mapped[Deal] = relationship()
    user: Mapped[User | None] = relationship(foreign_keys=[user_id])


class StatementCorrection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A person's correction of one mapped statement figure. Additive: the extracted metric row is never edited;
    the correction is applied when the deal is re-analysed, the original value is kept here, and `impact` records
    what changed as a result so the correction stays explainable."""

    __tablename__ = "statement_corrections"
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    line_key: Mapped[str] = mapped_column(String(64), nullable=False)
    period_label: Mapped[str] = mapped_column(String(32), nullable=False)
    original_value: Mapped[Decimal | None] = mapped_column(Ratio)
    corrected_value: Mapped[Decimal] = mapped_column(Ratio, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    impact: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    user: Mapped[User] = relationship(foreign_keys=[user_id])


class SellerReply(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """What the seller said back to one exported question, recorded by the buyer. Additive per question: the latest
    row is the current state. `question_id` is the export's stable id ("finding:<uuid>" or "claim:<uuid>")."""

    __tablename__ = "seller_replies"
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    question_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    reply_text: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)  # answered | dodged | needs_document
    user: Mapped[User] = relationship(foreign_keys=[user_id])


class CustomQuestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A question for the seller written or edited by a person (often drafted with the assistant), saved beside the
    generated ones and exported with them. Removing one is a delete of the person's own row; generated questions are
    never stored, so nothing generated is ever edited in place."""

    __tablename__ = "custom_questions"
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    why: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chat_messages.id", ondelete="SET NULL"))
    user: Mapped[User] = relationship(foreign_keys=[user_id])


class Purchase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A Stripe Checkout purchase. Created pending when the session is opened; the webhook marks it paid."""

    __tablename__ = "purchases"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[PurchaseKind] = mapped_column(_enum(PurchaseKind, "purchase_kind"), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[PurchaseStatus] = mapped_column(
        _enum(PurchaseStatus, "purchase_status"), default=PurchaseStatus.PENDING, nullable=False
    )
    stripe_session_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    stripe_payment_intent: Mapped[str | None] = mapped_column(String(255))
    deal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deals.id", ondelete="SET NULL"))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    doc_type: Mapped[DocumentType] = mapped_column(_enum(DocumentType, "document_type"), default=DocumentType.UNKNOWN)
    classification_source: Mapped[ClassificationSource] = mapped_column(
        _enum(ClassificationSource, "classification_source"), default=ClassificationSource.RULE
    )
    classification_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    status: Mapped[DocumentStatus] = mapped_column(_enum(DocumentStatus, "document_status"), default=DocumentStatus.UPLOADED)
    status_detail: Mapped[str | None] = mapped_column(Text)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    deal: Mapped[Deal] = relationship(back_populates="documents")
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentVersion.version_no"
    )


class DocumentVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_no", name="uq_document_version"),)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    extension: Mapped[str] = mapped_column(String(10), nullable=False)
    mime_declared: Mapped[str | None] = mapped_column(String(120))
    mime_detected: Mapped[str | None] = mapped_column(String(120))
    page_count: Mapped[int | None] = mapped_column(Integer)
    sheet_count: Mapped[int | None] = mapped_column(Integer)
    row_count: Mapped[int | None] = mapped_column(Integer)
    parse_meta: Mapped[dict] = mapped_column(JSON, default=dict)

    document: Mapped[Document] = relationship(back_populates="versions")


class ProcessingJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "processing_jobs"
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    job_type: Mapped[JobType] = mapped_column(_enum(JobType, "job_type"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(_enum(JobStatus, "job_status"), default=JobStatus.QUEUED, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    step: Mapped[str | None] = mapped_column(String(120))
    error: Mapped[str | None] = mapped_column(Text)
    log: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sequence: Mapped[int] = mapped_column(Integer, default=0)


class ExtractionRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One provider invocation. raw_output is immutable once written."""

    __tablename__ = "extraction_runs"
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    run_type: Mapped[RunType] = mapped_column(_enum(RunType, "run_type"), nullable=False)
    status: Mapped[RunStatus] = mapped_column(_enum(RunStatus, "run_status"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_output: Mapped[dict] = mapped_column(JSON, default=dict)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)


class Evidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evidence"
    __table_args__ = (Index("ix_evidence_doc_chunk", "document_id", "chunk_index"),)
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    document_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"))
    kind: Mapped[EvidenceKind] = mapped_column(_enum(EvidenceKind, "evidence_kind"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    locator: Mapped[dict] = mapped_column(JSON, default=dict)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    structured: Mapped[dict | None] = mapped_column(JSON)
    contains_instruction_text: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    document: Mapped[Document] = relationship()


class Claim(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "claims"
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    extraction_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("extraction_runs.id", ondelete="SET NULL"))
    verification_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("extraction_runs.id", ondelete="SET NULL"))
    source_evidence_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence.id", ondelete="SET NULL"))
    key: Mapped[str] = mapped_column(String(120), nullable=False)  # stable slug for eval matching
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)  # original, immutable
    claim_type: Mapped[ClaimType] = mapped_column(_enum(ClaimType, "claim_type"), nullable=False)
    metric_key: Mapped[str | None] = mapped_column(String(80), index=True)
    period_label: Mapped[str | None] = mapped_column(String(20))
    claimed_value: Mapped[Decimal | None] = mapped_column(Ratio)
    claimed_unit: Mapped[ClaimUnit] = mapped_column(_enum(ClaimUnit, "claim_unit"), default=ClaimUnit.TEXT)
    normalized: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("0.5"))
    status: Mapped[ClaimStatus] = mapped_column(_enum(ClaimStatus, "claim_status"), default=ClaimStatus.PENDING, index=True)
    status_rationale: Mapped[str | None] = mapped_column(Text)
    status_rule: Mapped[str | None] = mapped_column(String(120))
    verified_value: Mapped[Decimal | None] = mapped_column(Ratio)
    verified_unit: Mapped[ClaimUnit | None] = mapped_column(_enum(ClaimUnit, "claim_unit_verified"))
    verified_metric_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    deal: Mapped[Deal] = relationship(back_populates="claims")
    document: Mapped[Document] = relationship()
    source_evidence: Mapped[Evidence | None] = relationship(foreign_keys=[source_evidence_id])
    links: Mapped[list[ClaimEvidenceLink]] = relationship(back_populates="claim", cascade="all, delete-orphan")
    review_decisions: Mapped[list[ReviewDecision]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", order_by="ReviewDecision.created_at"
    )


class ClaimEvidenceLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "claim_evidence_links"
    __table_args__ = (UniqueConstraint("claim_id", "evidence_id", "role", name="uq_claim_evidence_role"),)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    evidence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence.id", ondelete="CASCADE"), index=True)
    role: Mapped[LinkRole] = mapped_column(_enum(LinkRole, "link_role"), nullable=False)
    relevance: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("1.0"))
    note: Mapped[str | None] = mapped_column(Text)

    claim: Mapped[Claim] = relationship(back_populates="links")
    evidence: Mapped[Evidence] = relationship()


class Finding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "findings"
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[FindingKind] = mapped_column(_enum(FindingKind, "finding_kind"), nullable=False)
    severity: Mapped[Severity] = mapped_column(_enum(Severity, "severity"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    metric_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[FindingStatus] = mapped_column(_enum(FindingStatus, "finding_status"), default=FindingStatus.OPEN)


class FinancialPeriod(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "financial_periods"
    __table_args__ = (UniqueConstraint("deal_id", "label", name="uq_period_label"),)
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    source_sheet: Mapped[str | None] = mapped_column(String(80))


class FinancialMetric(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "financial_metrics"
    __table_args__ = (Index("ix_metric_deal_key", "deal_id", "key", "period_id", "source"),)
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    period_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("financial_periods.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Ratio)
    raw_value: Mapped[str | None] = mapped_column(String(80))
    unit: Mapped[ClaimUnit] = mapped_column(_enum(ClaimUnit, "metric_unit"), nullable=False)
    source: Mapped[MetricSource] = mapped_column(_enum(MetricSource, "metric_source"), nullable=False)
    formula: Mapped[str | None] = mapped_column(Text)
    input_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("1.0"))
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    missing_inputs: Mapped[list] = mapped_column(JSON, default=list)

    period: Mapped[FinancialPeriod | None] = relationship()


class Adjustment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "adjustments"
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claims.id", ondelete="SET NULL"))
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    direction: Mapped[AdjustmentDirection] = mapped_column(_enum(AdjustmentDirection, "adjustment_direction"), nullable=False)
    period_label: Mapped[str] = mapped_column(String(20), nullable=False)
    seller_rationale: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[AdjustmentDecision] = mapped_column(
        _enum(AdjustmentDecision, "adjustment_decision"), default=AdjustmentDecision.PENDING
    )
    decision_rationale: Mapped[str | None] = mapped_column(Text)
    decision_rule: Mapped[str | None] = mapped_column(String(120))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Scenario(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scenarios"
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[ScenarioKind] = mapped_column(_enum(ScenarioKind, "scenario_kind"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    deal: Mapped[Deal] = relationship(back_populates="scenarios")
    assumptions: Mapped[list[ScenarioAssumption]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan", order_by="ScenarioAssumption.sort_order"
    )
    results: Mapped[list[ScenarioResult]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan", order_by="ScenarioResult.run_no"
    )


class ScenarioAssumption(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scenario_assumptions"
    __table_args__ = (UniqueConstraint("scenario_id", "key", name="uq_scenario_assumption"),)
    scenario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    value: Mapped[Decimal] = mapped_column(Ratio, nullable=False)
    unit: Mapped[ClaimUnit] = mapped_column(_enum(ClaimUnit, "assumption_unit"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    scenario: Mapped[Scenario] = relationship(back_populates="assumptions")


class ScenarioResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable: a run persists its complete input snapshot and outputs."""

    __tablename__ = "scenario_results"
    __table_args__ = (UniqueConstraint("scenario_id", "run_no", name="uq_scenario_run"),)
    scenario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    run_no: Mapped[int] = mapped_column(Integer, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    outputs: Mapped[dict] = mapped_column(JSON, nullable=False)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    run_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    scenario: Mapped[Scenario] = relationship(back_populates="results")


class Report(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("deal_id", "version_no", name="uq_report_version"),)
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ReportStatus] = mapped_column(_enum(ReportStatus, "report_status"), nullable=False)
    outcome: Mapped[ReviewOutcome] = mapped_column(_enum(ReviewOutcome, "review_outcome"), nullable=False)
    sections: Mapped[list] = mapped_column(JSON, nullable=False)
    validation: Mapped[dict] = mapped_column(JSON, default=dict)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    generated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    citations: Mapped[list[ReportCitation]] = relationship(back_populates="report", cascade="all, delete-orphan")


class ReportCitation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "report_citations"
    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    section_key: Mapped[str] = mapped_column(String(80), nullable=False)
    statement_index: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[CitationKind] = mapped_column(_enum(CitationKind, "citation_kind"), nullable=False)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence.id", ondelete="SET NULL"))
    metric_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("financial_metrics.id", ondelete="SET NULL"))
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    report: Mapped[Report] = relationship(back_populates="citations")


class ReviewDecision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Additive: never mutates Claim.claim_text/claimed_value; supersedes earlier decisions."""

    __tablename__ = "review_decisions"
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    adjustment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("adjustments.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    action: Mapped[ReviewAction] = mapped_column(_enum(ReviewAction, "review_action"), nullable=False)
    resulting_status: Mapped[str | None] = mapped_column(String(40))
    corrected_value: Mapped[Decimal | None] = mapped_column(Ratio)
    corrected_unit: Mapped[ClaimUnit | None] = mapped_column(_enum(ClaimUnit, "corrected_unit"))
    note: Mapped[str | None] = mapped_column(Text)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("review_decisions.id", ondelete="SET NULL"))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    claim: Mapped[Claim | None] = relationship(back_populates="review_decisions")
    user: Mapped[User] = relationship()


class ReviewerComment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reviewer_comments"
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    body: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped[User] = relationship()


class DealQuestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ask the Deal: a question and its citation-validated answer."""

    __tablename__ = "deal_questions"
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    intents: Mapped[list] = mapped_column(JSON, default=list)
    statements: Mapped[list] = mapped_column(JSON, default=list)
    grounded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    validation: Mapped[dict] = mapped_column(JSON, default=dict)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)


class ChatThread(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chat_threads"
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str | None] = mapped_column(String(120))

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="thread", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


class ChatMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chat_messages"
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_threads.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    citations: Mapped[dict] = mapped_column(JSON, default=dict)
    tool_calls: Mapped[list] = mapped_column(JSON, default=list)
    grounded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)

    thread: Mapped[ChatThread] = relationship(back_populates="messages")


class AuditEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_deal_created", "deal_id", "created_at"),)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(40), nullable=False)
    object_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
