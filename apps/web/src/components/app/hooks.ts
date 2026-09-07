"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Claim, type ClaimDetail, type Deal, type DealListItem, type DealSummary, type Doc, type Financials, type Finding, type Job, type Report, type Scenario, type ScenarioFacts, type AuditEvent, type Evidence, type StatementMapping } from "@/lib/api";

export const qk = {
  me: ["me"] as const,
  deals: ["deals"] as const,
  deal: (id: string) => ["deal", id] as const,
  summary: (id: string) => ["summary", id] as const,
  docs: (id: string) => ["docs", id] as const,
  jobs: (id: string) => ["jobs", id] as const,
  claims: (id: string) => ["claims", id] as const,
  claim: (id: string, cid: string) => ["claim", id, cid] as const,
  financials: (id: string) => ["financials", id] as const,
  scenarios: (id: string) => ["scenarios", id] as const,
  facts: (id: string) => ["facts", id] as const,
  report: (id: string) => ["report", id] as const,
  findings: (id: string) => ["findings", id] as const,
  audit: (id: string) => ["audit", id] as const,
  evidence: (id: string, eid: string) => ["evidence", id, eid] as const,
  mapping: (id: string) => ["mapping", id] as const,
  docEvidence: (id: string, did: string) => ["docEvidence", id, did] as const,
};

const active = (jobs?: Job[]) => jobs?.some((j) => j.status === "queued" || j.status === "running") ?? false;

export const useDeals = () => useQuery({ queryKey: qk.deals, queryFn: () => api.get<DealListItem[]>("/api/deals") });
export const useDeal = (id: string) => useQuery({ queryKey: qk.deal(id), queryFn: () => api.get<Deal>(`/api/deals/${id}`) });
export const useSummary = (id: string) => useQuery({ queryKey: qk.summary(id), queryFn: () => api.get<DealSummary>(`/api/deals/${id}/summary`), refetchInterval: (q) => ((q.state.data?.active_jobs ?? 0) > 0 ? 1500 : false) });
export const useDocs = (id: string, live = false) => useQuery({ queryKey: qk.docs(id), queryFn: () => api.get<Doc[]>(`/api/deals/${id}/documents`), refetchInterval: live ? 1500 : false });
export const useJobs = (id: string) => useQuery({ queryKey: qk.jobs(id), queryFn: () => api.get<Job[]>(`/api/deals/${id}/jobs`), refetchInterval: (q) => (active(q.state.data) ? 1500 : false) });
export const useClaims = (id: string) => useQuery({ queryKey: qk.claims(id), queryFn: () => api.get<Claim[]>(`/api/deals/${id}/claims`) });
export const useClaim = (id: string, cid: string | null) => useQuery({ queryKey: qk.claim(id, cid ?? ""), queryFn: () => api.get<ClaimDetail>(`/api/deals/${id}/claims/${cid}`), enabled: !!cid });
export const useFinancials = (id: string) => useQuery({ queryKey: qk.financials(id), queryFn: () => api.get<Financials>(`/api/deals/${id}/financials`) });
export const useScenarios = (id: string) => useQuery({ queryKey: qk.scenarios(id), queryFn: () => api.get<Scenario[]>(`/api/deals/${id}/scenarios`) });
export const useFacts = (id: string) => useQuery({ queryKey: qk.facts(id), queryFn: () => api.get<ScenarioFacts>(`/api/deals/${id}/scenarios/facts`) });
export const useReport = (id: string) => useQuery({ queryKey: qk.report(id), queryFn: () => api.get<Report | null>(`/api/deals/${id}/report`) });
export const useFindings = (id: string) => useQuery({ queryKey: qk.findings(id), queryFn: () => api.get<Finding[]>(`/api/deals/${id}/findings`) });
export const useAudit = (id: string) => useQuery({ queryKey: qk.audit(id), queryFn: () => api.get<AuditEvent[]>(`/api/deals/${id}/audit`) });
export const useStatementMapping = (id: string) => useQuery({ queryKey: qk.mapping(id), queryFn: () => api.get<StatementMapping>(`/api/deals/${id}/financials/mapping`) });
export const useEvidence = (id: string, eid: string | null) => useQuery({ queryKey: qk.evidence(id, eid ?? ""), queryFn: () => api.get<Evidence>(`/api/deals/${id}/evidence/${eid}`), enabled: !!eid });
export const useDocEvidence = (id: string, did: string | null) => useQuery({ queryKey: qk.docEvidence(id, did ?? ""), queryFn: () => api.get<Evidence[]>(`/api/deals/${id}/documents/${did}/evidence?limit=2000`), enabled: !!did });

/** The viewer reports that a person opened this evidence; reading a row for a chip label is not an open. */
export const reportEvidenceOpened = (id: string, eid: string) => api.post<unknown>(`/api/deals/${id}/evidence/${eid}/opened`).catch(() => undefined);

export function useInvalidateDeal(id: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ predicate: (q) => Array.isArray(q.queryKey) && q.queryKey.includes(id) });
}

export function useProcessDeal(id: string) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (reprocess: boolean) => api.post<{ job_ids: string[] }>(`/api/deals/${id}/process?reprocess=${reprocess}`), onSuccess: () => qc.invalidateQueries({ predicate: (q) => Array.isArray(q.queryKey) && q.queryKey.includes(id) }) });
}
