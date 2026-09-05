"""Explicit enums for every state machine in the domain."""

from __future__ import annotations

from enum import StrEnum


class PurchasePriceBasis(StrEnum):
    ENTERPRISE_VALUE = "enterprise_value"
    EQUITY_PRICE = "equity_price"


class DealStatus(StrEnum):
    DRAFT = "draft"
    PROCESSING = "processing"
    VERIFIED = "verified"
    REPORTED = "reported"


class DocumentType(StrEnum):
    CIM = "cim"
    FINANCIAL_STATEMENTS = "financial_statements"
    ACQUISITION_MODEL = "acquisition_model"
    CUSTOMER_REVENUE = "customer_revenue"
    DEBT_TERM_SHEET = "debt_term_sheet"
    CUSTOMER_CONTRACT = "customer_contract"
    OTHER = "other"
    UNKNOWN = "unknown"


class ClassificationSource(StrEnum):
    RULE = "rule"
    AI = "ai"
    USER = "user"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PARSING = "parsing"
    EXTRACTING = "extracting"
    READY = "ready"
    FAILED = "failed"


DOCUMENT_TRANSITIONS: dict[DocumentStatus, set[DocumentStatus]] = {
    DocumentStatus.UPLOADED: {DocumentStatus.QUEUED, DocumentStatus.FAILED},
    DocumentStatus.QUEUED: {DocumentStatus.PARSING, DocumentStatus.FAILED},
    DocumentStatus.PARSING: {DocumentStatus.EXTRACTING, DocumentStatus.FAILED},
    DocumentStatus.EXTRACTING: {DocumentStatus.READY, DocumentStatus.FAILED},
    DocumentStatus.READY: {DocumentStatus.QUEUED},
    DocumentStatus.FAILED: {DocumentStatus.QUEUED},
}


class JobType(StrEnum):
    PROCESS_DOCUMENT = "process_document"
    ANALYZE_DEAL = "analyze_deal"
    GENERATE_REPORT = "generate_report"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunType(StrEnum):
    CLASSIFY = "classify"
    EXTRACT = "extract"
    VERIFY = "verify"
    REPORT = "report"


class RunStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INVALID_OUTPUT = "invalid_output"


class EvidenceKind(StrEnum):
    PAGE_TEXT = "page_text"
    TABLE_CELL = "table_cell"
    SHEET_CELL = "sheet_cell"
    SHEET_ROW = "sheet_row"
    CSV_ROW = "csv_row"
    CSV_AGGREGATE = "csv_aggregate"


class ClaimType(StrEnum):
    REVENUE = "revenue"
    REVENUE_GROWTH = "revenue_growth"
    CUSTOMER_CONCENTRATION = "customer_concentration"
    RECURRING_REVENUE = "recurring_revenue"
    CHURN = "churn"
    ADJUSTED_EBITDA = "adjusted_ebitda"
    ADDBACK = "addback"
    GROSS_MARGIN = "gross_margin"
    OPERATING_MARGIN = "operating_margin"
    MARGIN_IMPROVEMENT = "margin_improvement"
    FORECAST = "forecast"
    CONTRACT_TERM = "contract_term"
    DEBT_TERM = "debt_term"
    ONE_TIME_EXPENSE = "one_time_expense"
    OTHER = "other"


class ClaimUnit(StrEnum):
    USD = "usd"
    PCT = "pct"
    MULTIPLE = "multiple"
    MONTHS = "months"
    YEARS = "years"
    COUNT = "count"
    TEXT = "text"


class ClaimStatus(StrEnum):
    PENDING = "pending"
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNSUPPORTED = "unsupported"
    REVIEW_REQUIRED = "review_required"


class LinkRole(StrEnum):
    SOURCE = "source"
    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"


class FindingKind(StrEnum):
    CONTRADICTION = "contradiction"
    UNSUPPORTED_ASSUMPTION = "unsupported_assumption"
    MISSING_DOCUMENT = "missing_document"
    COVENANT_WARNING = "covenant_warning"
    DOCUMENT_INTEGRITY = "document_integrity"
    CONCENTRATION = "concentration"
    RISK = "risk"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class MetricSource(StrEnum):
    EXTRACTED = "extracted"
    CALCULATED = "calculated"
    VERIFIED = "verified"
    SCENARIO = "scenario"


class AdjustmentDirection(StrEnum):
    ADD_BACK = "add_back"
    DOWNWARD = "downward"


class AdjustmentDecision(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REVIEW_REQUIRED = "review_required"
    UNSUPPORTED = "unsupported"


class ScenarioKind(StrEnum):
    BASE = "base"
    DOWNSIDE = "downside"
    SEVERE_DOWNSIDE = "severe_downside"
    CUSTOM = "custom"


class ReportStatus(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    FAILED_VALIDATION = "failed_validation"


class ReviewOutcome(StrEnum):
    ADDITIONAL_DILIGENCE_REQUIRED = "additional_diligence_required"
    MATERIAL_CONCERNS_IDENTIFIED = "material_concerns_identified"
    ASSUMPTIONS_REQUIRE_REVISION = "assumptions_require_revision"
    READY_FOR_IC_REVIEW = "ready_for_ic_review"


class CitationKind(StrEnum):
    EVIDENCE = "evidence"
    CALCULATION = "calculation"


class ReviewAction(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    CORRECT = "correct"
    UNDO = "undo"
