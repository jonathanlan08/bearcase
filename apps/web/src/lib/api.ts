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

/** The API's error body is `{detail}`; anything else (a proxy's HTML page, plain text) is kept as the detail itself. */
function parseBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return text;
  }
}

async function fail(res: Response): Promise<never> {
  const body = parseBody(await res.text());
  const detail = body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : body;
  throw new ApiError(res.status, detail);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, { credentials: "include", ...init, headers: { ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...(init.headers ?? {}) } });
  if (!res.ok) return fail(res);
  if (res.status === 204) return undefined as T;
  return parseBody(await res.text()) as T;
}

/** A 204 reply's headers, for routes that answer with advice in a header (document deletion says whether to re-run analysis). */
async function requestHeaders(path: string, init: RequestInit): Promise<Headers> {
  const res = await fetch(path, { credentials: "include", ...init });
  if (!res.ok) return fail(res);
  return res.headers;
}

/** File name from a Content-Disposition header; the fallback is used when the server sent none. */
export function attachmentName(disposition: string | null, fallback: string): string {
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposition ?? "");
  if (utf8) { try { return decodeURIComponent(utf8[1]); } catch { /* fall through */ } }
  const plain = /filename="?([^";]+)"?/i.exec(disposition ?? "");
  return plain?.[1]?.trim() || fallback;
}

/** Fetch an export as a file: the blob plus the name the server gave it. The caller hands it to the browser's save. */
async function download(path: string, fallbackName: string): Promise<{ blob: Blob; filename: string }> {
  const res = await fetch(path, { credentials: "include" });
  if (!res.ok) return fail(res);
  return { blob: await res.blob(), filename: attachmentName(res.headers.get("Content-Disposition"), fallbackName) };
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: "POST", body: form }),
  del: (path: string) => requestHeaders(path, { method: "DELETE" }),
  download,
};

/* ---------- API types (mirror apps/api/src/bearcase/api/schemas.py) ---------- */

export type ClaimStatus = "pending" | "supported" | "contradicted" | "unsupported" | "review_required";
export type Unit = "usd" | "pct" | "multiple" | "months" | "years" | "count" | "text";

/** `email_verified` is false until the link in the verification email is opened; demo identities are never verified. */
export interface User { id: string; email: string; display_name: string; is_demo: boolean; email_verified: boolean }

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
/** "Check what we read": how each statement sheet was interpreted (api/routes/financials.py statement_mapping). */
export interface CorrectionImpact { metrics: { key: string; period: string; label: string; unit: Unit; before: string | null; after: string | null }[]; findings_added: { key: string; title: string; severity: string }[]; findings_removed: { key: string; title: string; severity: string }[]; findings_changed: { key: string; title: string; before: string; after: string }[]; claims_changed: { key: string; text: string; before: string; after: string }[] }
/** A person's correction of one mapped figure (api/routes/financials.py correct_figure). Additive; the original stays. */
export interface Correction { id: string; line_key: string; period_label: string; original_value: string | null; corrected_value: string; note: string | null; by: string | null; created_at: string; impact: CorrectionImpact }
export interface MappedCell { value: string; raw: string; cell: string; confidence: number; evidence_id: string | null; correction: Correction | null }
export interface MappedLine { key: string; cells: Record<string, MappedCell>; components: string[] | null; needs_review: boolean }
export interface MappedStatement { document_id: string; document_name: string; mapped: boolean; reason?: string; sheet?: string; header_row?: number | null; scale?: number; currency?: string; currency_stated?: boolean; periods?: { label: string; year: number | null }[]; lines?: MappedLine[]; unmapped_rows?: { row: number; label: string }[] }
export interface Coverage { documents_ready: number; documents_failed: number; documents_pending: number; statements_mapped: number; statements_unmapped: number; unmapped_rows: number; ambiguous_lines: number; metrics_requiring_review: number; claims_by_status: Record<string, number> }
export interface StatementMapping { statements: MappedStatement[]; coverage: Coverage }
/** The review inbox (api/routes/insights.py review_queue): what a person still has to decide, grouped. */
export interface QueueItem { id: string; title: string; detail: string; href_key: "documents" | "financials" | "claims" | "questions"; status?: string; claim_id?: string; adjustment_id?: string; resolution?: string | null }
export interface ReviewQueue { groups: { key: string; title: string; items: QueueItem[] }[]; total: number }

export interface Assumption { key: string; label: string; value: string; unit: Unit }
export interface YearRow { year: number; revenue: string; gross_profit: string; labor_opex: string; other_opex: string; addbacks: string; ebitda: string; depreciation_amortization: string; interest: string; principal: string; taxable_income: string; cash_taxes: string; working_capital_investment: string; cfads: string; debt_service: string; dscr: string | null; fcfe: string; closing_debt: string }
export interface ScenarioOutputs { engine_version: string; years: YearRow[]; enterprise_value: string; funded_debt: string; equity: string; annual_debt_service: string; year1: Record<string, string | null>; cfads_bridge: Record<string, string>; dscr: string | null; cash_on_cash_pct: string | null; irr_pct: string | null; irr_cashflows: string[]; exit: Record<string, string>; break_even_revenue: string | null; warnings: Warning[]; calcs: Record<string, unknown> }
export interface Warning { code: string; severity: string; year?: number; message: string; value?: string; threshold?: string }
export interface ScenarioResult { id: string; run_no: number; engine_version: string; input_snapshot: Record<string, string | number | null>; outputs: ScenarioOutputs; warnings: Warning[]; input_hash: string; created_at: string }
export interface Scenario { id: string; name: string; kind: string; description: string | null; is_seed: boolean; sort_order: number; assumptions: Assumption[]; latest_result: ScenarioResult | null; result_count: number }
export interface AssumptionSpec { key: string; label: string; unit: Unit; min: number; max: number; step: number }
export interface ScenarioFacts { facts: Record<string, string | number | null>; missing: string[]; specs: AssumptionSpec[] }
export interface Sensitivity { row_key: string; col_key: string; row_values: string[]; col_values: string[]; output: string; threshold: string | null; cells: Array<Array<{ row: string; col: string; value: string | null; breach: boolean }>> }

export interface Finding { id: string; key: string; kind: string; severity: string; title: string; detail: string; evidence_ids: string[]; metric_ids: string[]; status: string; claim_id: string | null; created_at: string; resolution: string | null }
export interface ReportStatement { text: string; evidence_ids: string[]; metric_ids: string[] }
export interface ReportSection { key: string; title: string; kind: string; statements: ReportStatement[]; table: { columns?: string[]; rows?: Array<{ label: string; cells: string[]; evidence_ids: string[]; metric_ids?: string[]; [k: string]: unknown }> }; derived_from: string[] }
export interface Report { id: string; deal_id: string; version_no: number; status: string; outcome: string; sections: ReportSection[]; validation: { valid: boolean; statements_total: number; material_statements: number; material_cited: number; uncited: Array<{ section: string; index: number; text: string }>; unresolved: unknown[] }; provider: string; model: string; prompt_version: string; schema_version: string; engine_version: string; input_snapshot: Record<string, unknown>; created_at: string }
export interface AuditEvent { id: string; event_type: string; object_type: string; object_id: string | null; summary: string; payload: Record<string, unknown>; user_name: string; created_at: string }
export interface DealSummary { deal: Deal; documents: Record<string, number>; claim_counts: Record<string, number>; findings_by_severity: Record<string, number>; seller_adjusted_ebitda: string | null; verified_adjusted_ebitda: string | null; reported_ebitda: string | null; dscr_by_scenario: Array<{ scenario_id: string; name: string; kind: string; dscr: string | null; warnings: string[] }>; covenant_threshold: string | null; missing_documents: Finding[]; top_findings: Finding[]; latest_report: { id: string; version_no: number; status: string; outcome: string; created_at: string } | null; active_jobs: number; mode: { provider: string; model: string }; confidence: Record<string, number> }
export interface Health { status: string; version: string; engine_version: string; provider: string; model: string; database: string; storage: string }

/* ---------- Buyer workflow: questions for the seller, progress, usage (see the routes in apps/api) ---------- */

/** Where a question came from. Mirrors the API's seller-question kinds, which collapse the finding kinds to plain groups. */
export type SellerQuestionKind = "contradiction" | "unsupported" | "missing_document" | "covenant" | "concentration" | "risk" | "integrity";
export interface SellerQuestion { id: string; question: string; why: string; kind: SellerQuestionKind | string; severity: string; evidence_ids: string[]; metric_ids: string[]; claim_id: string | null; finding_id: string | null; document_names: string[] }
/** Deterministic: the same function assembles the report's "Management questions" section, so the page and the report agree. */
export interface SellerQuestions { questions: SellerQuestion[]; generated_from: { findings: number; claims: number } }

export type ProgressKey = "documents" | "findings" | "evidence" | "questions";
export interface ProgressStep { key: ProgressKey; label: string; done: boolean; href_key: string }
export interface Progress { steps: ProgressStep[] }

export interface Usage {
  chat: { messages: number; input_tokens: number; output_tokens: number; tool_calls: number; by_model: Record<string, number> };
  documents: { count: number; bytes: number; pages: number; rows: number };
  storage_bytes: number;
  /** Null when a model has no entry in the price table; `pricing_note` says so. */
  cost_estimate_usd: number | null;
  pricing_note: string;
}

/* ---------- Accounts, sharing, chat budget, billing (see api/routes/auth.py, deals members, billing.py) ---------- */

export type MemberRole = "viewer" | "editor";
/** `accepted` is false while the invite email has not been opened by a signed-in account with that address. */
export interface DealMember { id: string; email: string; role: MemberRole; accepted: boolean }
export interface DealMembers { owner: { email: string; display_name: string }; members: DealMember[] }

/** Assistant answers counted per calendar month (UTC) across every deal the user asked in; the API refuses with 429 at the limit. */
export interface ChatBudget { limit: number; used: number; resets_on: string }

export type PurchaseStatus = "pending" | "paid" | "failed";
export interface Purchase { id: string; kind: string; amount_cents: number; currency: string; status: PurchaseStatus; deal_id: string | null; created_at: string; paid_at: string | null }
/** `configured` is false when the API has no Stripe keys; the page then offers a mailto instead of checkout. */
export interface BillingOffer { configured: boolean; pilot: { amount_cents: number; currency: string; description: string } }
export interface BillingStatus extends BillingOffer { purchases: Purchase[] }

export const auth = {
  verify: (token: string) => api.post<{ verified: boolean }>("/api/auth/verify", { token }),
  resendVerification: () => api.post<unknown>("/api/auth/resend-verification"),
  requestReset: (email: string) => api.post<unknown>("/api/auth/request-reset", { email }),
  reset: (token: string, password: string) => api.post<unknown>("/api/auth/reset", { token, password }),
};

export const members = {
  list: (dealId: string) => api.get<DealMembers>(`/api/deals/${dealId}/members`),
  invite: (dealId: string, email: string, role: MemberRole) => api.post<DealMember>(`/api/deals/${dealId}/members`, { email, role }),
  remove: (dealId: string, memberId: string) => api.del(`/api/deals/${dealId}/members/${memberId}`),
  accept: (token: string) => api.post<{ deal_id: string }>("/api/invites/accept", { token }),
};

export type ReplyOutcome = "answered" | "dodged" | "needs_document";
export interface SellerReply { id: string; question_id: string; reply_text: string; outcome: ReplyOutcome; by: string | null; created_at: string }
export interface SellerReplies { replies: Record<string, SellerReply>; totals: Record<ReplyOutcome, number> }
export const sellerReplies = {
  list: (dealId: string) => api.get<SellerReplies>(`/api/deals/${dealId}/seller-replies`),
  record: (dealId: string, body: { question_id: string; question_text: string; reply_text: string; outcome: ReplyOutcome }) => api.post<SellerReply>(`/api/deals/${dealId}/seller-replies`, body),
};
/** What changed between two versions of a document (documents.py diff_versions). */
export interface VersionDiff { document_id: string; document_name?: string; versions: number[]; comparable: boolean; reason?: string; old_version?: number; new_version?: number; kind?: "statement" | "text"; periods_before?: string[]; periods_after?: string[]; scale_before?: number; scale_after?: number; changes?: { period: string; line_key: string; before: string | null; after: string | null; cell: string | null; dependents: string[] }[]; claims_affected?: { id: string; text: string; status: string; metric_key: string | null }[]; added?: string[]; removed?: string[]; chunks_before?: number; chunks_after?: number; stale?: boolean }

export type NoteKind = "conclusion" | "assumption" | "open_question";
export interface ReviewNote { id: string; kind: NoteKind; text: string; evidence_ids: string[]; metric_ids: string[]; claim_id: string | null; finding_id: string | null; include_in_report: boolean; by: string | null; created_at: string }
export interface ReviewNotes { notes: ReviewNote[]; counts: Record<NoteKind, number> }
export const notes = {
  list: (dealId: string) => api.get<ReviewNotes>(`/api/deals/${dealId}/notes`),
  add: (dealId: string, body: { kind: NoteKind; text: string; evidence_ids?: string[]; metric_ids?: string[]; claim_id?: string | null; finding_id?: string | null; include_in_report?: boolean }) => api.post<ReviewNote>(`/api/deals/${dealId}/notes`, body),
  setIncluded: (dealId: string, id: string, include: boolean) => api.patch<ReviewNote>(`/api/deals/${dealId}/notes/${id}`, { include_in_report: include }),
  remove: (dealId: string, id: string) => api.del(`/api/deals/${dealId}/notes/${id}`),
};

export const financials = {
  corrections: (dealId: string) => api.get<Correction[]>(`/api/deals/${dealId}/financials/corrections`),
  correct: (dealId: string, body: { line_key: string; period_label: string; value: string; note?: string }) => api.post<Correction>(`/api/deals/${dealId}/financials/corrections`, body),
};

export const billing = {
  /** Public: price and whether checkout is enabled. No session needed. */
  offer: () => api.get<BillingOffer>("/api/billing/offer"),
  /** Signed in: the offer plus this account's purchases. */
  status: () => api.get<BillingStatus>("/api/billing/status"),
  checkout: (dealId?: string) => api.post<{ url: string }>("/api/billing/checkout", dealId ? { deal_id: dealId } : {}),
};

/** Whole units with the currency's symbol when Intl knows it ("$500.00"); the amount is the server's minor units. */
export function fmtPrice(amountCents: number, currency: string): string {
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: currency.toUpperCase() }).format(amountCents / 100);
  } catch {
    return `${(amountCents / 100).toFixed(2)} ${currency.toUpperCase()}`;
  }
}

/** The API's `{detail}` string, or a fallback when the failure was not one of its own replies. */
export function errorDetail(e: unknown, fallback: string): string {
  if (e instanceof ApiError && typeof e.detail === "string" && e.detail) return e.detail;
  return fallback;
}
