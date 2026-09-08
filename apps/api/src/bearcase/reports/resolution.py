"""What would change this finding: the document or clarification that would settle it, one sentence per finding.

Derived from persisted rows only (finding kind and the claim type it hangs on); no model. Used by the findings
routes, the review queue, and the report so the same sentence appears everywhere."""

from __future__ import annotations

from bearcase.models import Claim, Finding
from bearcase.models.enums import FindingKind

_BY_CLAIM_TYPE: dict[str, str] = {
    "revenue_growth": "A reconciliation from the seller showing how the growth figure was calculated, and monthly revenue for the periods it covers.",
    "revenue": "A revenue ledger or tax return for the period, tying to the statement line.",
    "adjusted_ebitda": "A schedule of each add-back with the invoice, contract, or payroll record behind it.",
    "customer_concentration": "A customer-level revenue report for the last full year, with contract terms for the largest accounts.",
    "recurring_revenue": "The list of signed maintenance agreements with their annual value and term, tied to the revenue ledger.",
    "gross_margin": "Job-level cost data for the period, so the margin can be rebuilt from the underlying work.",
    "churn": "A customer roster for the last two years showing who left and when.",
    "contract_term": "The signed contract and any amendments, showing the current term and termination rights.",
}


def resolution_for(finding: Finding, claim: Claim | None) -> str | None:
    """One sentence on what would change the finding, or None when nothing short of a decision would."""
    kind = finding.kind
    if kind == FindingKind.MISSING_DOCUMENT:
        return "The document itself. Ask the seller for it; the checks that depend on it run when it is uploaded."
    if kind == FindingKind.CONTRADICTION:
        specific = _BY_CLAIM_TYPE.get(claim.claim_type) if claim else None
        return specific or "A source from the seller that reconciles the claim with the document that contradicts it."
    if kind == FindingKind.UNSUPPORTED_ASSUMPTION:
        specific = _BY_CLAIM_TYPE.get(claim.claim_type) if claim else None
        return specific or "Any document that states the figure; until one exists the claim stays unsupported."
    if kind == FindingKind.COVENANT_WARNING:
        return "Signed renewals, backlog, or cost commitments that would lift the downside cash flow, or a lender term sheet with a lower minimum."
    if kind == FindingKind.CONCENTRATION:
        return "The largest customer's contract, its remaining term, and any termination clause."
    if kind == FindingKind.DOCUMENT_INTEGRITY:
        return "A clean copy of the document from the seller; the flagged text is kept but never acted on."
    if kind == FindingKind.RISK:
        return "A decision by the reviewer; this finding records a risk, not a discrepancy a document would settle."
    return None
