"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Check, X, Pencil, ExternalLink, Undo2, MessageSquareText, NotebookPen } from "lucide-react";
import { NoteDialog } from "@/components/domain/note-dialog";
import { useQueryClient } from "@tanstack/react-query";
import { qk, useClaim, useClaims } from "@/components/app/hooks";
import { PageHeader, useDealKicker } from "@/components/app/shell";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Kbd, Skeleton } from "@/components/ui/primitives";
import { ConfidenceMeter, StatusChip, StatusGlyph, STATUS_LABEL } from "@/components/domain/status";
import { CitationChip } from "@/components/domain/citation";
import { DocumentViewer, type ViewerTarget } from "@/components/domain/document-viewer";
import { ACTION_VERB, CorrectionDialog, useReview } from "@/components/domain/review-dialog";
import { fmtLocator, fmtValue, fmtDateTime, titleCase } from "@/lib/format";
import { useMediaQuery } from "@/lib/hooks";
import { askTheDeal } from "@/lib/chat-bus";
import { api, type Claim, type ClaimDetail, type Link as EvLink, type Metric } from "@/lib/api";

const STATUSES = ["supported", "contradicted", "review_required", "unsupported"] as const;

/** One plain sentence per status so a first-time buyer knows what confirming it means. */
const STATUS_MEANING: Record<string, string> = {
  supported: "the evidence backs the seller's claim",
  contradicted: "the documents disagree with the seller's claim",
  unsupported: "no evidence was found either way",
  review_required: "the evidence is mixed or the extractor was unsure",
  pending: "the claim has not been checked yet",
};

type DialogMode = "correct" | "reject" | null;

export default function ClaimsPage() {
  const { dealId } = useParams<{ dealId: string }>();
  const kicker = useDealKicker();
  const router = useRouter();
  const search = useSearchParams();
  const claims = useClaims(dealId);
  const [status, setStatus] = useState<string>("all");
  const [type, setType] = useState<string>("all");
  const [q, setQ] = useState("");
  const [chosen, setSelected] = useState<string | null>(search.get("claim"));
  const [viewer, setViewer] = useState<ViewerTarget | null>(null);
  const [noting, setNoting] = useState(false);
  const [dialog, setDialog] = useState<DialogMode>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const review = useReview(dealId);

  const list = useMemo(() => (claims.data ?? []).filter((c) => (status === "all" || c.effective_status === status) && (type === "all" || c.claim_type === type) && (!q || c.claim_text.toLowerCase().includes(q.toLowerCase()))), [claims.data, status, type, q]);
  const counts = useMemo(() => { const m: Record<string, number> = {}; for (const c of claims.data ?? []) m[c.effective_status] = (m[c.effective_status] ?? 0) + 1; return m; }, [claims.data]);
  const types = useMemo(() => Array.from(new Set((claims.data ?? []).map((c) => c.claim_type))).sort(), [claims.data]);

  const desktop = useMediaQuery("(min-width: 1024px)");
  const selected = chosen && (claims.data ?? []).some((c) => c.id === chosen) ? chosen : desktop ? (list[0]?.id ?? null) : null;
  const detail = useClaim(dealId, selected);
  useEffect(() => { const url = new URL(window.location.href); if (selected) url.searchParams.set("claim", selected); else url.searchParams.delete("claim"); router.replace(url.pathname + url.search, { scroll: false }); }, [selected, router]);

  const move = useCallback((delta: number) => { const i = list.findIndex((c) => c.id === selected); const next = list[Math.max(0, Math.min(list.length - 1, i + delta))]; if (next) { setSelected(next.id); (listRef.current?.querySelector(`[data-id="${next.id}"]`) as HTMLElement | null)?.focus(); } }, [list, selected]);
  const jumpToSource = useCallback((d: ClaimDetail | undefined) => { if (d?.source_evidence) setViewer({ documentId: d.source_evidence.document_id, documentName: d.source_evidence.document_name, evidenceId: d.source_evidence.id, locator: d.source_evidence.locator, highlightIds: d.links.map((l) => l.evidence.id) }); }, []);
  const decide = useCallback((action: "accept" | "undo") => { if (selected) review.mutate({ claimId: selected, body: { action } }); }, [review, selected]);
  const qc = useQueryClient();
  // The shortcut reads through the query cache, so it works even when the detail for a freshly selected claim has not rendered yet.
  const jumpToSelected = useCallback(() => {
    if (!selected) return;
    qc.fetchQuery({ queryKey: qk.claim(dealId, selected), queryFn: () => api.get<ClaimDetail>(`/api/deals/${dealId}/claims/${selected}`), staleTime: 30_000 }).then(jumpToSource).catch(() => undefined);
  }, [qc, dealId, selected, jumpToSource]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable || viewer || dialog) return;
      if (t.closest?.('[role="dialog"]')) return; // the chat panel or any other modal owns the keyboard while open
      if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); move(1); }
      else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); move(-1); }
      else if (e.key === "a") decide("accept");
      else if (e.key === "c") setDialog("correct");
      else if (e.key === "r") setDialog("reject");
      else if (e.key === "e") jumpToSelected();
      else if (e.key === "u") decide("undo");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [move, decide, jumpToSelected, viewer, dialog]);

  const d = detail.data;
  const current = d?.decisions.find((x) => x.is_current);
  // The continuous review: after this claim, the next one in the list that still needs a person (disputed and undecided).
  const nextUnresolved = useMemo(() => {
    const i = list.findIndex((c) => c.id === selected);
    const needs = (c: Claim) => ["contradicted", "review_required", "unsupported"].includes(c.effective_status) && !c.decisions.some((x) => x.is_current);
    return [...list.slice(i + 1), ...list.slice(0, Math.max(0, i))].find(needs) ?? null;
  }, [list, selected]);
  return (
    <div className="flex min-h-[calc(100svh-0px)] flex-col">
      <PageHeader kicker={kicker} title="Claim Audit" className={selected && d ? "hidden lg:block" : ""}>
        <p className="mt-2 max-w-3xl text-sm text-fg-muted">The factual claims the reader found in the seller’s documents, each checked against the other documents. It can miss claims and misread others, so open a claim, read the evidence, then record what you decide.</p>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap gap-1" role="group" aria-label="Filter by status">
            <FilterChip active={status === "all"} onClick={() => setStatus("all")}>All <span className="num">{claims.data?.length ?? 0}</span></FilterChip>
            {STATUSES.map((s) => <FilterChip key={s} active={status === s} onClick={() => setStatus(s)}><StatusGlyph status={s} size={11} />{STATUS_LABEL[s]} <span className="num">{counts[s] ?? 0}</span></FilterChip>)}
          </div>
          <select aria-label="Filter by claim type" className="h-8 rounded-[var(--radius-1)] border border-hairline bg-bg-raised px-2 text-sm" value={type} onChange={(e) => setType(e.target.value)}><option value="all">All types</option>{types.map((t) => <option key={t} value={t}>{titleCase(t)}</option>)}</select>
          <input aria-label="Search claims" placeholder="Search claim text" className="h-8 w-52 rounded-[var(--radius-1)] border border-hairline bg-bg-raised px-2 text-sm" value={q} onChange={(e) => setQ(e.target.value)} />
          <p className="ml-auto hidden items-center gap-1.5 text-xs text-fg-muted lg:flex"><Kbd>J</Kbd><Kbd>K</Kbd> move <Kbd>A</Kbd> confirm <Kbd>C</Kbd> correct <Kbd>R</Kbd> reject <Kbd>E</Kbd> evidence <Kbd>U</Kbd> undo</p>
        </div>
      </PageHeader>
      <div className="grid flex-1 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div ref={listRef} className={`border-hairline lg:border-r ${selected && d ? "hidden lg:block" : ""}`} role="listbox" aria-label="Claims" aria-activedescendant={selected ?? undefined}>
          {claims.isPending && <div className="p-4"><Skeleton className="h-16" /><Skeleton className="mt-2 h-16" /><Skeleton className="mt-2 h-16" /></div>}
          {claims.isError && <div className="p-4"><ErrorState detail={String(claims.error)} onRetry={() => claims.refetch()} /></div>}
          {claims.data && claims.data.length === 0 && <div className="p-4"><EmptyState title="No claims yet" body="Process the documents in the Deal Room, then run analysis to extract claims." /></div>}
          {list.map((c) => <ClaimRow key={c.id} claim={c} active={c.id === selected} onSelect={() => setSelected(c.id)} />)}
          {claims.data && claims.data.length > 0 && list.length === 0 && <p className="p-4 text-sm text-fg-muted">No claims match these filters.</p>}
        </div>
        <div className={`min-w-0 ${!selected || !d ? "hidden lg:block" : ""}`}>
          {selected && detail.isPending && <div className="p-4"><Skeleton className="h-40" /></div>}
          {d && (
            <div className="flex flex-col gap-5 p-4 pb-28 md:p-6 md:pb-6">
              <div className="flex items-center gap-2 lg:hidden">
                <button type="button" className="flex items-center gap-1 text-sm text-fg-muted" onClick={() => setSelected(null)}><ArrowLeft size={14} /> List</button>
                <span className="num ml-auto text-xs text-fg-muted">{list.findIndex((c) => c.id === selected) + 1} of {list.length}</span>
                <Button size="sm" variant="secondary" onClick={() => move(-1)} aria-label="Previous claim">Prev</Button>
                <Button size="sm" variant="secondary" onClick={() => move(1)} aria-label="Next claim">Next</Button>
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2"><StatusChip status={d.effective_status} />{current && d.effective_status !== d.status && <span className="text-xs text-fg-muted">reviewer decision (AI said <StatusChip status={d.status} size="sm" />)</span>}<span className="ml-auto text-xs text-fg-muted">{titleCase(d.claim_type)}{d.period_label ? `, ${d.period_label}` : ""}</span></div>
                <p className="mt-3 text-lg leading-snug">{d.claim_text}</p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  {d.source_evidence && <CitationChip docType={d.doc_type} documentName={d.document_name} locator={d.source_evidence.locator} kind={d.source_evidence.kind} onClick={() => jumpToSource(d)} />}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 rounded-[var(--radius-3)] border border-hairline p-3 md:grid-cols-4">
                <Stat label="Seller says" value={d.claimed_value !== null ? fmtValue(d.claimed_value, d.claimed_unit) : "—"} />
                <Stat label="Documents show" value={d.verified_value !== null ? fmtValue(d.verified_value, d.verified_unit ?? d.claimed_unit) : "—"} tone={d.status === "contradicted" ? "text-red" : d.status === "supported" ? "text-accent" : ""} />
                <Stat label="Difference" value={d.claimed_value !== null && d.verified_value !== null ? delta(d) : "—"} />
                <Stat label="Rule applied" value={d.status_rule ? d.status_rule.replace(/_/g, " ") : "—"} mono />
              </div>
              <AnswerTrace d={d} onOpen={(eid) => setViewer({ documentId: "", evidenceId: eid })} onSource={() => jumpToSource(d)} />
              <details className="rounded-[var(--radius-2)] border border-hairline p-3 text-sm">
                <summary className="cursor-pointer text-sm font-medium">How this claim was extracted</summary>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <ConfidenceMeter value={d.confidence} />
                  {d.extraction_run && <span className="font-mono text-[11px] text-fg-muted">{String(d.extraction_run.provider)}/{String(d.extraction_run.model)} · prompt {String(d.extraction_run.prompt_version)} · schema {String(d.extraction_run.schema_version)}</span>}
                </div>
                <p className="mt-2 text-xs text-fg-muted">Confidence is how confident the extractor was that this sentence is a claim. It is not a measure of whether the claim is true; the status above is.</p>
              </details>
              <EvidenceGroup title="Supporting evidence" role="supporting" links={d.links} onOpen={(l) => setViewer({ documentId: l.evidence.document_id, documentName: l.evidence.document_name, evidenceId: l.evidence.id, locator: l.evidence.locator, highlightIds: d.links.map((x) => x.evidence.id) })} />
              <EvidenceGroup title="Contradicting evidence" role="contradicting" links={d.links} onOpen={(l) => setViewer({ documentId: l.evidence.document_id, documentName: l.evidence.document_name, evidenceId: l.evidence.id, locator: l.evidence.locator, highlightIds: d.links.map((x) => x.evidence.id) })} />
              <section className="rounded-[var(--radius-3)] border border-hairline p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-sm font-medium">Your review</h2>
                  <div className="ml-auto flex flex-wrap gap-2">
                    <Button size="sm" variant="secondary" icon={<Check size={14} />} onClick={() => decide("accept")} loading={review.isPending} disabled={current?.action === "accept"}>Confirm assessment</Button>
                    <Button size="sm" variant="secondary" icon={<Pencil size={14} />} onClick={() => setDialog("correct")}>Correct…</Button>
                    <Button size="sm" variant="danger" icon={<X size={14} />} onClick={() => setDialog("reject")}>Reject…</Button>
                    {current && <Button size="sm" variant="ghost" icon={<Undo2 size={14} />} onClick={() => decide("undo")}>Undo</Button>}
                    {nextUnresolved && <Button size="sm" variant="primary" onClick={() => setSelected(nextUnresolved.id)}>Next unresolved</Button>}
                  </div>
                </div>
                <p className="mt-2 text-xs text-fg-muted">Confirm records that you agree with the AI&apos;s assessment, <span className="font-medium text-fg">{STATUS_LABEL[d.status]}</span> ({STATUS_MEANING[d.status] ?? "see the rationale above"}). Correct or reject when you disagree; each adds an entry under your name and the original AI output stays unchanged.</p>
                <div className="mt-3 flex flex-wrap gap-2 border-t border-hairline pt-3">
                  <Button size="sm" variant="ghost" icon={<ExternalLink size={14} />} onClick={() => jumpToSource(d)} disabled={!d.source_evidence}>Jump to source</Button>
                  <Button size="sm" variant="ghost" icon={<MessageSquareText size={14} />} onClick={() => askTheDeal(askPrompt(d), { context: `Claim: ${d.claim_text.slice(0, 80)}` })}>Ask about this claim</Button>
                  <Button size="sm" variant="ghost" icon={<NotebookPen size={14} />} onClick={() => setNoting(true)}>Add to notebook</Button>
                </div>
                <div className="mt-2 flex flex-wrap gap-2" aria-label="Questions about this claim">
                  {CONTEXT_PROMPTS.map(([label, build]) => <Button key={label} size="sm" variant="secondary" onClick={() => askTheDeal(build(d), { send: true, context: `Claim: ${d.claim_text.slice(0, 80)}` })}>{label}</Button>)}
                </div>
                {d.decisions.length > 0 && (
                  <ol className="mt-3 flex flex-col gap-1.5 border-t border-hairline pt-3 text-sm" aria-label="Decision history">
                    {d.decisions.map((x) => <li key={x.id} className={x.is_current ? "" : "text-fg-muted line-through"}><span className="font-medium">{x.user_name}</span> {ACTION_VERB[x.action] ?? x.action}{x.resulting_status ? ` → ${STATUS_LABEL[x.resulting_status] ?? x.resulting_status}` : ""}{x.corrected_value ? ` · ${fmtValue(x.corrected_value, x.corrected_unit)}` : ""}{x.note ? ` — ${x.note}` : ""} <span className="num text-xs text-fg-muted">{fmtDateTime(x.created_at)}</span></li>)}
                  </ol>
                )}
                <p className="mt-3 text-xs text-fg-muted">Original extraction (immutable): status <span className="font-medium">{STATUS_LABEL[d.status]}</span>, claimed {d.claimed_value !== null ? fmtValue(d.claimed_value, d.claimed_unit) : "text"}.</p>
              </section>
            </div>
          )}
          {!selected && claims.data && claims.data.length > 0 && <p className="p-6 text-sm text-fg-muted">Select a claim to see its evidence.</p>}
        </div>
      </div>
      <DocumentViewer dealId={dealId} target={viewer} onClose={() => setViewer(null)} />
      {noting && d && <NoteDialog dealId={dealId} claimId={d.id} evidenceIds={[...(d.source_evidence ? [d.source_evidence.id] : []), ...d.links.map((l) => l.evidence.id)].slice(0, 20)} metricIds={d.verified_metric_id ? [d.verified_metric_id] : []} draft={`${STATUS_LABEL[d.effective_status]}: "${d.claim_text}". `} onClose={() => setNoting(false)} />}
      <CorrectionDialog key={dialog ?? "closed"} open={!!dialog} defaultMode={dialog ?? "correct"} onOpenChange={(o) => { if (!o) setDialog(null); }} claim={d ?? null} pending={review.isPending} onSubmit={(body) => { if (selected) review.mutate({ claimId: selected, body }, { onSuccess: () => setDialog(null) }); }} />
    </div>
  );
}

/** The prompt handed to "Ask the deal": the claim text, its status, and both numbers, so the user never retypes context. */
/** One-click questions that carry the selected claim into the assistant, so the reader never retypes what is on screen. */
const CONTEXT_PROMPTS: Array<[string, (d: ClaimDetail) => string]> = [
  ["Explain this discrepancy", (d) => `In plain English, for a first-time buyer: what is the discrepancy in this claim and why does it matter?\nClaim: "${d.claim_text}"\nStatus: ${STATUS_LABEL[d.effective_status]}.${d.claimed_value !== null ? ` Seller says ${fmtValue(d.claimed_value, d.claimed_unit)}${d.verified_value !== null ? `; the documents show ${fmtValue(d.verified_value, d.verified_unit ?? d.claimed_unit)}` : ""}.` : ""} Cite the evidence.`],
  ["Show the calculation", (d) => `Show how the checked figure for this claim was calculated: the formula, each input, and the cell or line each input came from. Do not recompute anything; describe the stored calculation.\nClaim: "${d.claim_text}"`],
  ["What would resolve this?", (d) => `What document or figure from the seller would settle this claim one way or the other, and how should I word the request?\nClaim: "${d.claim_text}"\nStatus: ${STATUS_LABEL[d.effective_status]}.`],
];

const INPUT_LABEL: Record<string, string> = { first_period_revenue: "Starting revenue", last_period_revenue: "Ending revenue", years: "Elapsed time", current_period_revenue: "This year's revenue", prior_period_revenue: "Prior year's revenue", revenue: "Revenue", cost_of_goods_sold: "Cost of goods sold", operating_income: "Operating income", net_income: "Net income", interest_expense: "Interest expense", income_tax_expense: "Income tax", depreciation: "Depreciation", amortization: "Amortization", ebitda: "EBITDA", reported_ebitda: "Reported EBITDA", accepted_addbacks: "Accepted add-backs", top_customer_revenue: "Largest customer's revenue", total_revenue: "Total revenue", recurring_revenue: "Recurring revenue" };

/** A figure from a calculation's snapshot, formatted for a reader: years as years, percentages as percentages, everything else as money. */
function fmtInput(key: string, v: string | number, unit: string): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  if (/year/.test(key)) return `${n} ${n === 1 ? "year" : "years"}`;
  if (/pct|margin|share|rate/.test(key)) return fmtValue(String(v), "pct");
  if (unit === "pct" || unit === "usd" || unit === "multiple" || unit === "ratio") return fmtValue(String(v), "usd");
  return fmtValue(String(v), unit as never);
}

/** One sentence that substitutes the inputs into the formula, for the calculations a buyer meets first. */
function workedExample(m: Metric, inputs: Array<[string, string | number]>): string | null {
  const get = (k: string) => inputs.find(([kk]) => kk === k)?.[1];
  const money = (v: string | number | undefined) => (v === undefined ? "?" : fmtValue(String(v), "usd"));
  const out = fmtValue(m.value, m.unit);
  switch (m.key) {
    case "cagr": return `${money(get("first_period_revenue"))} starting revenue → ${money(get("last_period_revenue"))} ending revenue over ${get("years") ?? "?"} years → ${out} a year.`;
    case "revenue_growth": return `${money(get("prior_period_revenue"))} last year → ${money(get("current_period_revenue"))} this year → ${out} growth.`;
    case "gross_margin": return `(${money(get("revenue"))} revenue − ${money(get("cost_of_goods_sold"))} cost of goods sold) ÷ revenue → ${out}.`;
    case "operating_margin": return `${money(get("operating_income"))} operating income ÷ ${money(get("revenue"))} revenue → ${out}.`;
    case "ebitda_reported": return `${money(get("net_income"))} net income + interest, taxes, depreciation, and amortization → ${out}.`;
    case "customer_concentration_top1": return `${money(get("top_customer_revenue"))} from the largest customer ÷ ${money(get("total_revenue"))} total → ${out}.`;
    case "recurring_revenue_pct": return `${money(get("recurring_revenue"))} under contract ÷ ${money(get("total_revenue"))} total → ${out}.`;
    default: return m.formula ? `${m.formula.replace(/_/g, " ")} → ${out}.` : null;
  }
}

/** The answer trace: source → extracted value → calculation → conclusion, each step openable. The one interaction that
 *  shows a reader where a status came from without reading the whole page. */
function AnswerTrace({ d, onOpen, onSource }: { d: ClaimDetail; onOpen: (eid: string) => void; onSource: () => void }) {
  const m = d.verified_metric;
  const contradicting = d.links.filter((l) => l.role === "contradicting");
  const supporting = d.links.filter((l) => l.role === "supporting");
  const inputs = m ? Object.entries(m.input_snapshot).filter(([k, v]) => !["sheet", "cell", "row", "document_id", "scale", "components", "corrected", "correction_id", "mapped_value", "correction_note", "scenario_result_id"].includes(k) && (typeof v === "string" || typeof v === "number")) : [];
  const worked = m ? workedExample(m, inputs as Array<[string, string | number]>) : null;
  const steps: Array<{ label: string; body: React.ReactNode }> = [
    { label: "Source", body: <>{d.source_evidence ? <>The claim is a sentence in <button type="button" className="text-accent hover:underline" onClick={onSource}>{d.document_name}{fmtLocator(d.source_evidence.locator) ? `, ${fmtLocator(d.source_evidence.locator)}` : ""}</button>.</> : "No source location was recorded for this claim."}{d.claimed_value !== null && <> The seller&apos;s figure: <span className="num font-medium">{fmtValue(d.claimed_value, d.claimed_unit)}</span>.</>}</> },
    { label: "What the documents hold", body: (contradicting.length + supporting.length) === 0 ? "No document in the deal room speaks to this claim, which is why it cannot be supported." : <ul className="space-y-1">{[...contradicting, ...supporting].slice(0, 4).map((l) => <li key={l.evidence.id}><button type="button" className="text-left hover:underline" onClick={() => onOpen(l.evidence.id)}><span className="font-medium">{l.evidence.document_name}</span>{fmtLocator(l.evidence.locator) ? `, ${fmtLocator(l.evidence.locator)}` : ""}</button>{l.role === "contradicting" && <span className="ml-2 text-xs text-red">contradicts</span>}{l.note && <span className="block text-xs text-fg-muted">{l.note}</span>}</li>)}</ul> },
    { label: "Calculation", body: m ? <>{worked ? <p>{worked}</p> : <p>Read directly from the cell; no arithmetic.</p>}{inputs.length > 0 && <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm">{inputs.map(([k, v]) => <Fragment key={k}><dt className="text-fg-muted">{INPUT_LABEL[k] ?? k.replace(/_/g, " ")}</dt><dd className="num">{fmtInput(k, v as string | number, m.unit)}</dd></Fragment>)}</dl>}<p className="mt-1 text-xs text-fg-muted">Result: <span className="num font-medium text-fg">{fmtValue(m.value, m.unit)}</span>. Computed by code from the mapped statements, never by the model.</p><details className="mt-1 text-xs text-fg-muted"><summary className="cursor-pointer">Technical details</summary>{m.formula && <p className="mt-1 font-mono">{m.formula}</p>}<pre className="mt-1 overflow-x-auto rounded-[var(--radius-1)] bg-bg-muted p-2 font-mono text-[11px]">{JSON.stringify(m.input_snapshot, null, 1)}</pre></details></> : "No calculation is involved; the status rests on the documents above." },
    { label: "Conclusion", body: <><span className="font-medium">{STATUS_LABEL[d.status]}</span>{d.status_rule && <span className="ml-2 font-mono text-[11px] text-fg-muted">rule {d.status_rule.replace(/_/g, " ")}</span>}<p className="mt-1">{d.status_rationale ?? "No rationale recorded."}</p></> },
  ];
  return (
    <section aria-label="How this answer was reached" className="rounded-[var(--radius-3)] border border-hairline p-3">
      <h2 className="text-sm font-semibold">How this answer was reached</h2>
      <ol className="mt-3 flex flex-col">
        {steps.map((s, i) => (
          <li key={s.label} className="relative flex gap-3 pb-4 last:pb-0">
            {i < steps.length - 1 && <span aria-hidden className="absolute left-[9px] top-5 h-full w-px bg-hairline" />}
            <span className="num relative z-[1] flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-hairline bg-bg-raised text-[11px]">{i + 1}</span>
            <div className="min-w-0 text-sm"><p className="micro text-fg-muted">{s.label}</p><div className="mt-0.5">{s.body}</div></div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function askPrompt(d: ClaimDetail): string {
  const numbers = d.claimed_value !== null ? ` Seller says ${fmtValue(d.claimed_value, d.claimed_unit)}${d.verified_value !== null ? `; the documents show ${fmtValue(d.verified_value, d.verified_unit ?? d.claimed_unit)}` : ""}.` : "";
  return `Explain this claim and the evidence behind it, then suggest what I should ask the seller.\nClaim: "${d.claim_text}"\nStatus: ${STATUS_LABEL[d.effective_status]}.${numbers}`;
}

function delta(d: ClaimDetail): string {
  const a = Number(d.claimed_value), b = Number(d.verified_value);
  const unit = d.verified_unit ?? d.claimed_unit;
  if (unit === "usd") return `${b - a >= 0 ? "+" : "−"}${fmtValue(Math.abs(b - a), "usd")}`;
  if (unit === "pct") return `${b - a >= 0 ? "+" : "−"}${Math.abs(b - a).toFixed(1)} pts`;
  return `${b - a >= 0 ? "+" : "−"}${Math.abs(b - a).toFixed(2)}`;
}

function Stat({ label, value, tone = "", mono = false }: { label: string; value: string; tone?: string; mono?: boolean }) {
  return <div><p className="text-xs text-fg-muted">{label}</p><p className={`mt-1 ${mono ? "font-mono text-xs" : "num text-base"} ${tone}`}>{value}</p></div>;
}

function FilterChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" aria-pressed={active} onClick={onClick} className={`inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-2)] border px-3 text-xs ${active ? "border-fg bg-fg text-bg" : "border-hairline hover:bg-bg-muted"}`}>{children}</button>;
}

function ClaimRow({ claim, active, onSelect }: { claim: Claim; active: boolean; onSelect: () => void }) {
  return (
    <div role="option" aria-selected={active} data-id={claim.id} tabIndex={active ? 0 : -1} onClick={onSelect} onKeyDown={(e) => { if (e.key === "Enter") onSelect(); }} className={`cursor-pointer border-b border-hairline px-4 py-3 outline-none transition-colors duration-[120ms] focus-visible:bg-bg-muted ${active ? "bg-bg-muted" : "hover:bg-bg-muted/60"}`}>
      <div className="flex items-start gap-3">
        <StatusGlyph status={claim.effective_status} className="mt-1" />
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 text-sm">{claim.claim_text}</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-fg-muted">
            <span>{titleCase(claim.claim_type)}</span>
            <span className="num">{claim.claimed_value !== null ? fmtValue(claim.claimed_value, claim.claimed_unit) : ""}{claim.verified_value !== null ? ` → ${fmtValue(claim.verified_value, claim.verified_unit ?? claim.claimed_unit)}` : ""}</span>
            <CitationChip docType={claim.doc_type} documentName={claim.document_name} locator={claim.source_locator} />
            {claim.decisions.some((x) => x.is_current) && <span className="text-[11px] font-medium text-accent">reviewed</span>}
          </div>
        </div>
      </div>
    </div>
  );
}

function EvidenceGroup({ title, role, links, onOpen }: { title: string; role: "supporting" | "contradicting"; links: EvLink[]; onOpen: (l: EvLink) => void }) {
  const rows = links.filter((l) => l.role === role);
  return (
    <section>
      <h2 className="flex items-center gap-2 text-sm font-semibold">{title} <span className="num font-normal text-fg-muted">({rows.length})</span></h2>
      {rows.length === 0 ? <p className="mt-2 text-sm text-fg-muted">{role === "supporting" ? "No supporting evidence was retrieved." : "No contradicting evidence."}</p> : (
        <ul className="mt-2 flex flex-col gap-2">
          {rows.map((l, i) => (
            <li key={`${l.evidence.id}-${i}`} className={`rounded-[var(--radius-2)] border-l-2 border border-hairline p-3 ${role === "supporting" ? "border-l-accent" : "border-l-red"}`}>
              <div className="flex flex-wrap items-center gap-2">
                <CitationChip docType={l.evidence.doc_type} documentName={l.evidence.document_name} locator={l.evidence.locator} kind={l.evidence.kind} onClick={() => onOpen(l)} />
                {l.note && <span className="text-xs text-fg-muted">{l.note}</span>}
              </div>
              <p className="mt-2 line-clamp-4 text-sm">{l.evidence.text}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
