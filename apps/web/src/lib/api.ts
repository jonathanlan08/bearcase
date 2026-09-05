/** Typed client for the BearCase API (same-origin via Next.js rewrite). */

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `Request failed (${status})`);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, { credentials: "include", ...init, headers: { ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...(init.headers ?? {}) } });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let body: unknown = text;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    /* keep text */
  }
  if (!res.ok) {
    const detail = body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : body;
    throw new ApiError(res.status, detail);
  }
  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: "POST", body: form }),
};

/* ---------- API types (mirror apps/api/src/bearcase/api/schemas.py) ---------- */

export type ClaimStatus = "pending" | "supported" | "contradicted" | "unsupported" | "review_required";
export type Unit = "usd" | "pct" | "multiple" | "months" | "years" | "count" | "text";

export interface User { id: string; email: string; display_name: string; is_demo: boolean }

export interface Deal {
  id: string; company_name: string; industry: string; purchase_price: string; purchase_price_basis: string; purchase_date: string | null;
  debt_amount: string; equity_amount: string; debt_assumed: string; cash_acquired: string; interest_rate_pct: string; amortization_years: number;
  payments_per_year: number; covenant_dscr_threshold: string | null; status: string; is_demo: boolean; created_at: string; updated_at: string;
}
export interface DealListItem extends Deal { document_count: number; documents_ready: number; claim_counts: Record<string, number> }

export interface Version { id: string; version_no: number; sha256: string; size_bytes: number; extension: string; mime_detected: string | null; page_count: number | null; sheet_count: number | null; row_count: number | null }
export interface Doc { id: string; deal_id: string; display_name: string; doc_type: string; classification_source: string; classification_confidence: string | null; status: string; status_detail: string | null; version: Version | null; evidence_count: number; created_at: string; updated_at: string }
export interface Job { id: string; deal_id: string; document_id: string | null; job_type: string; status: string; progress: number; step: string | null; error: string | null; log: Array<Record<string, unknown>>; started_at: string | null; finished_at: string | null; created_at: string }

export interface Evidence { id: string; document_id: string; document_name: string; doc_type: string; kind: string; chunk_index: number; locator: Record<string, unknown>; text: string; structured: Record<string, unknown> | null; contains_instruction_text: boolean }
export interface Link { role: "supporting" | "contradicting"; note: string | null; evidence: Evidence }
export interface Decision { id: string; action: string; resulting_status: string | null; corrected_value: string | null; corrected_unit: string | null; note: string | null; user_name: string; is_current: boolean; created_at: string }

export interface Claim {
  id: string; key: string; document_id: string; document_name: string; doc_type: string; claim_text: string; claim_type: string; metric_key: string | null; period_label: string | null;
  claimed_value: string | null; claimed_unit: Unit; normalized: Record<string, unknown>; confidence: string; status: ClaimStatus; effective_status: ClaimStatus; status_rationale: string | null; status_rule: string | null;
  verified_value: string | null; verified_unit: Unit | null; verified_metric_id: string | null; source_locator: Record<string, unknown>; source_evidence_id: string | null; supporting_count: number; contradicting_count: number; decisions: Decision[]; created_at: string;
}
export interface ClaimDetail extends Claim { source_evidence: Evidence | null; links: Link[]; verified_metric: Metric | null; extraction_run: Record<string, unknown> | null }

export interface Metric { id: string; key: string; label: string; value: string | null; raw_value: string | null; unit: Unit; source: string; period_label: string | null; formula: string | null; input_snapshot: Record<string, unknown>; evidence_ids: string[]; confidence: string; requires_review: boolean; missing_inputs: string[] }
export interface Period { id: string; label: string; ordinal: number; start_date: string | null; end_date: string | null; source_sheet: string | null }
export interface Adjustment { id: string; key: string; label: string; amount: string; direction: string; period_label: string; seller_rationale: string | null; decision: string; decision_rationale: string | null; decision_rule: string | null; evidence_ids: string[]; decided_by_user_id: string | null; sort_order: number }
export interface WaterfallStep { label: string; amount: string; decision: string; included: boolean; running_total: string; adjustment_id: string | null }
export interface Financials { periods: Period[]; metrics: Metric[]; adjustments: Adjustment[]; waterfall: WaterfallStep[] }

export interface Assumption { key: string; label: string; value: string; unit: Unit }
export interface YearRow { year: number; revenue: string; gross_profit: string; labor_opex: string; other_opex: string; addbacks: string; ebitda: string; depreciation_amortization: string; interest: string; principal: string; taxable_income: string; cash_taxes: string; working_capital_investment: string; cfads: string; debt_service: string; dscr: string | null; fcfe: string; closing_debt: string }
export interface ScenarioOutputs { engine_version: string; years: YearRow[]; enterprise_value: string; funded_debt: string; equity: string; annual_debt_service: string; year1: Record<string, string | null>; cfads_bridge: Record<string, string>; dscr: string | null; cash_on_cash_pct: string | null; irr_pct: string | null; irr_cashflows: string[]; exit: Record<string, string>; break_even_revenue: string | null; warnings: Warning[]; calcs: Record<string, unknown> }
export interface Warning { code: string; severity: string; year?: number; message: string; value?: string; threshold?: string }
export interface ScenarioResult { id: string; run_no: number; engine_version: string; input_snapshot: Record<string, string | number | null>; outputs: ScenarioOutputs; warnings: Warning[]; input_hash: string; created_at: string }
export interface Scenario { id: string; name: string; kind: string; description: string | null; is_seed: boolean; sort_order: number; assumptions: Assumption[]; latest_result: ScenarioResult | null; result_count: number }
export interface AssumptionSpec { key: string; label: string; unit: Unit; min: number; max: number; step: number }
export interface ScenarioFacts { facts: Record<string, string | number | null>; missing: string[]; specs: AssumptionSpec[] }
export interface Sensitivity { row_key: string; col_key: string; row_values: string[]; col_values: string[]; output: string; threshold: string | null; cells: Array<Array<{ row: string; col: string; value: string | null; breach: boolean }>> }

export interface Finding { id: string; key: string; kind: string; severity: string; title: string; detail: string; evidence_ids: string[]; metric_ids: string[]; status: string; claim_id: string | null; created_at: string }
export interface ReportStatement { text: string; evidence_ids: string[]; metric_ids: string[] }
export interface ReportSection { key: string; title: string; kind: string; statements: ReportStatement[]; table: { columns?: string[]; rows?: Array<{ label: string; cells: string[]; evidence_ids: string[]; metric_ids?: string[]; [k: string]: unknown }> }; derived_from: string[] }
export interface Report { id: string; deal_id: string; version_no: number; status: string; outcome: string; sections: ReportSection[]; validation: { valid: boolean; statements_total: number; material_statements: number; material_cited: number; uncited: Array<{ section: string; index: number; text: string }>; unresolved: unknown[] }; provider: string; model: string; prompt_version: string; schema_version: string; engine_version: string; input_snapshot: Record<string, unknown>; created_at: string }
export interface AuditEvent { id: string; event_type: string; object_type: string; object_id: string | null; summary: string; payload: Record<string, unknown>; user_name: string; created_at: string }
export interface DealSummary { deal: Deal; documents: Record<string, number>; claim_counts: Record<string, number>; findings_by_severity: Record<string, number>; seller_adjusted_ebitda: string | null; verified_adjusted_ebitda: string | null; reported_ebitda: string | null; dscr_by_scenario: Array<{ scenario_id: string; name: string; kind: string; dscr: string | null; warnings: string[] }>; covenant_threshold: string | null; missing_documents: Finding[]; top_findings: Finding[]; latest_report: { id: string; version_no: number; status: string; outcome: string; created_at: string } | null; active_jobs: number; mode: { provider: string; model: string } }
export interface Health { status: string; version: string; engine_version: string; provider: string; model: string; database: string; storage: string }
