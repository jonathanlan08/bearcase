"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useSummary, useProcessDeal } from "@/components/app/hooks";
import { PageHeader, useDealKicker } from "@/components/app/shell";
import { Button, buttonClass } from "@/components/ui/button";
import { ErrorState, Panel, Skeleton } from "@/components/ui/primitives";
import { SeverityChip, StatusGlyph, STATUS_LABEL } from "@/components/domain/status";
import { fmtMoney, fmtX, fmtDate, titleCase } from "@/lib/format";
import { useToast } from "@/components/ui/toast";
import type { Finding } from "@/lib/api";

const ORDER = ["supported", "contradicted", "review_required", "unsupported"] as const;
const KIND_LABEL: Record<string, string> = { contradiction: "Contradiction", unsupported_assumption: "Unsupported", covenant_warning: "Loan coverage", concentration: "Concentration", risk: "Risk", document_integrity: "Document integrity", missing_document: "Missing document" };
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const KIND_PREFIX = /^(?:Contradicted|Unsupported|Missing|Risk):\s*/i;

const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString("en-US")} ${n === 1 ? one : many}`;
const verb = (n: number, one: string, many: string) => (n === 1 ? one : many);

/** Engine text carries raw Decimals ("22.00772201", "10.00000000", "0E-8") and bare dollar amounts; round to two places and add separators. */
const trimDecimal = (n: number) => (Number.isFinite(n) ? n.toFixed(2).replace(/\.?0+$/, "") : "n/a");
function tidyNumbers(s: string): string {
  return s
    .replace(/\b\d+(?:\.\d+)?[Ee][-+]?\d+\b/g, (m) => trimDecimal(Number(m)))
    .replace(/\b\d+\.\d{3,}\b/g, (m) => trimDecimal(Number(m)))
    .replace(/\$(\d{4,})(?![\d,])/g, (_, n: string) => `$${Number(n).toLocaleString("en-US")}`);
}

/** Plain title: no kind prefix (the kind is shown beside it), no mid-word truncation, tidy numbers. */
function findingTitle(f: Finding): string {
  const raw = f.title.replace(KIND_PREFIX, "");
  // The API keeps the first 90 characters of a claim, often cutting a word in half (or ending on a space).
  const truncated = raw.length >= 90 && !/[.!?]\s*$/.test(raw);
  const text = raw.trim();
  const cut = truncated ? `${text.replace(/\s+\S*$/, "")}…` : text;
  return tidyNumbers(cut.replace(/\s\|\s/g, ", "));
}

/** Detail without database ids, without repeating the title, with tidy numbers; null when nothing useful remains. */
function findingDetail(f: Finding, title: string): string | null {
  const kept = f.detail.split(/(?<=[.!?])\s+/).filter((sentence) => !UUID.test(sentence)).join(" ");
  const detail = tidyNumbers(kept).trim();
  if (!detail) return null;
  const key = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
  return key(title).includes(key(detail)) || key(detail).includes(key(title)) ? null : detail;
}

function findingHref(base: string, f: Finding): string {
  if (f.claim_id) return `${base}/claims?claim=${f.claim_id}`;
  if (f.kind === "covenant_warning") return `${base}/scenarios`;
  if (f.kind === "document_integrity") return `${base}/documents`;
  return `${base}/report`;
}

export default function OverviewPage() {
  const { dealId } = useParams<{ dealId: string }>();
  const s = useSummary(dealId);
  const kicker = useDealKicker();
  const process = useProcessDeal(dealId);
  const { toast } = useToast();
  const base = `/app/deals/${dealId}`;
  if (s.isPending) return <div className="p-6"><Skeleton className="h-8 w-64" /><Skeleton className="mt-6 h-36" /><div className="mt-4 grid gap-4 md:grid-cols-2"><Skeleton className="h-40" /><Skeleton className="h-40" /><Skeleton className="h-40" /><Skeleton className="h-40" /></div></div>;
  if (s.isError) return <div className="p-6"><ErrorState detail={String(s.error)} onRetry={() => s.refetch()} /></div>;
  const d = s.data;
  const total = Object.values(d.claim_counts).reduce((a, b) => a + b, 0);
  const docsTotal = Object.values(d.documents).reduce((a, b) => a + b, 0);
  const noDocs = docsTotal === 0;
  const running = d.active_jobs > 0;
  const contradicted = d.claim_counts.contradicted ?? 0;
  const unsupported = d.claim_counts.unsupported ?? 0;
  const review = d.claim_counts.review_required ?? 0;
  const hasScenarios = d.dscr_by_scenario.length > 0;
  const belowMin = d.dscr_by_scenario.filter((sc) => sc.warnings.includes("covenant_breach")).length;
  const runAnalysis = (reprocess: boolean) => process.mutate(reprocess, { onSuccess: () => toast({ title: reprocess ? "Reprocessing queued" : "Analysis queued", description: "Documents will be parsed and analysed. This page refreshes on its own." }) });

  const start = noDocs
    ? {
        heading: "Start by adding the seller's documents",
        body: "Upload the financial statements, the sales memo (CIM), the customer list, the contracts, and the loan terms. Run analysis, then check what was found before relying on any number.",
        actions: <Link className={buttonClass("primary", "sm")} href={`${base}/documents`}>Add documents</Link>,
      }
    : total === 0 && running
      ? {
          heading: "Analysis is running",
          body: "The seller's claims, the recomputed numbers, and the scenarios appear here when processing finishes. This page refreshes on its own.",
          actions: <Link className={buttonClass("secondary", "sm")} href={`${base}/documents`}>Watch progress in the Deal Room</Link>,
        }
      : total === 0
        ? {
            heading: "Run analysis to check the claims",
            body: `${plural(docsTotal, "document")} uploaded. Analysis extracts the seller's claims, links each one to its source, recomputes the numbers, and seeds three scenarios.`,
            actions: <><Button size="sm" onClick={() => runAnalysis(false)} loading={process.isPending}>Run analysis</Button><Link className={buttonClass("secondary", "sm")} href={`${base}/documents`}>Open the Deal Room</Link></>,
          }
        : {
            heading: contradicted > 0 ? `Start with the ${plural(contradicted, "claim")} the documents disagree with` : unsupported + review > 0 ? "Start with the claims that need a closer look" : "Every claim checks out so far. Confirm them yourself.",
            body: `${contradicted} of ${plural(total, "claim")} ${verb(contradicted, "conflicts", "conflict")} with the documents, ${unsupported} ${verb(unsupported, "has", "have")} no evidence behind ${verb(unsupported, "it", "them")}, and ${review} ${verb(review, "needs", "need")} a human call. Open a claim, compare it with its source, then record your decision.${belowMin > 0 ? ` ${plural(belowMin, "scenario")} ${verb(belowMin, "falls", "fall")} below the lender's minimum.` : ""}`,
            actions: <><Link className={buttonClass("primary", "sm")} href={`${base}/claims`}>Review the claims</Link>{hasScenarios && <Link className={buttonClass("secondary", "sm")} href={`${base}/scenarios`}>Test a downside scenario</Link>}</>,
          };

  return (
    <div>
      <PageHeader kicker={kicker} title="Deal overview" actions={
        <>
          {running && <span className="text-xs font-medium text-amber" aria-live="polite">{d.active_jobs} job{d.active_jobs > 1 ? "s" : ""} running…</span>}
          <Button variant="secondary" size="sm" onClick={() => runAnalysis(true)} loading={process.isPending} disabled={noDocs}>Re-run analysis</Button>
        </>
      } />
      <div className="flex flex-col gap-4 p-4 md:p-6">
        <section aria-labelledby="start-heading" className="rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-5">
          <h2 id="start-heading" className="text-xl">{start.heading}</h2>
          <p className="mt-2 max-w-3xl text-sm text-fg-muted">{start.body}</p>
          <div className="mt-4 flex flex-wrap gap-2">{start.actions}</div>
          <details className="mt-4 text-sm">
            <summary className="cursor-pointer text-accent">New to these numbers?</summary>
            <dl className="mt-3 grid gap-3 md:grid-cols-2">
              <div><dt className="font-medium">Adjusted EBITDA</dt><dd className="mt-0.5 text-fg-muted">Earnings before interest, taxes, depreciation, and amortization, plus the costs the seller says will not recur; the verified figure keeps only the add-backs the statements support.</dd></div>
              <div><dt className="font-medium">Debt coverage (DSCR)</dt><dd className="mt-0.5 text-fg-muted">Cash available for loan payments divided by the payments due; below <span className="num">1.00x</span> the business does not cover its loan{d.covenant_threshold ? <>, and this lender requires at least <span className="num">{fmtX(d.covenant_threshold)}</span></> : ", and lenders usually require more"}.</dd></div>
            </dl>
          </details>
        </section>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <Panel title="Claims checked" actions={<Link href={`${base}/claims`} className="text-xs text-accent hover:underline">Open Claim Audit</Link>}>
            {total === 0 ? <p className="text-sm text-fg-muted">{noDocs ? "Add documents in the Deal Room to begin." : running ? "Analysis is running…" : "No claims yet. Run analysis to extract and check the claims."}</p> : (
              <>
                <div className="flex h-3 w-full overflow-hidden rounded-[var(--radius-1)] border border-hairline" role="img" aria-label={ORDER.map((k) => `${STATUS_LABEL[k]} ${d.claim_counts[k] ?? 0}`).join(", ")}>
                  {ORDER.map((k) => <span key={k} style={{ width: `${((d.claim_counts[k] ?? 0) / total) * 100}%` }} className={k === "supported" ? "bg-accent" : k === "contradicted" ? "bg-red" : k === "review_required" ? "bg-amber" : "bg-graphite diag-hatch"} />)}
                </div>
                <ul className="mt-3 grid grid-cols-2 gap-2 text-sm">
                  {ORDER.map((k) => <li key={k} className="flex items-center gap-2"><StatusGlyph status={k} /><span className="flex-1">{STATUS_LABEL[k]}</span><span className="num">{(d.claim_counts[k] ?? 0).toLocaleString("en-US")}</span></li>)}
                </ul>
              </>
            )}
          </Panel>
          <Panel title="Adjusted EBITDA" actions={<Link href={`${base}/financials`} className="text-xs text-accent hover:underline">Open Financial Verification</Link>}>
            {d.verified_adjusted_ebitda === null ? <p className="text-sm text-fg-muted">Financial statements not yet mapped.</p> : (
              <div className="flex flex-col gap-3">
                {[["Reported", d.reported_ebitda, "bg-graphite"], ["Seller adjusted", d.seller_adjusted_ebitda, "border border-graphite"], ["Verified adjusted", d.verified_adjusted_ebitda, "bg-accent"]].map(([label, v, cls]) => {
                  const max = Math.max(Number(d.seller_adjusted_ebitda ?? 0), Number(d.verified_adjusted_ebitda ?? 0), Number(d.reported_ebitda ?? 0)) || 1;
                  return (
                    <div key={label as string}>
                      <div className="flex justify-between text-sm"><span>{label as string}</span><span className="num">{fmtMoney(v as string | null)}</span></div>
                      <div className="mt-1 h-2 w-full rounded-[1px] bg-bg-muted"><div className={`h-2 rounded-[1px] ${cls}`} style={{ width: `${(Number(v ?? 0) / max) * 100}%` }} /></div>
                    </div>
                  );
                })}
              </div>
            )}
          </Panel>
          <Panel title="Debt coverage by scenario (DSCR)" actions={<Link href={`${base}/scenarios`} className="text-xs text-accent hover:underline">Open Scenario Lab</Link>}>
            {!hasScenarios ? <p className="text-sm text-fg-muted">Scenarios appear after analysis.</p> : (
              <ul className="flex flex-col gap-2 text-sm">
                {d.dscr_by_scenario.map((sc) => {
                  const breach = sc.warnings.includes("covenant_breach");
                  const warn = sc.warnings.includes("covenant_warning");
                  return (
                    <li key={sc.scenario_id} className="flex items-center gap-2">
                      <StatusGlyph status={breach ? "breach" : warn ? "warning" : "supported"} />
                      <span className="flex-1">{sc.name}</span>
                      <span className="num">{fmtX(sc.dscr)}</span>
                    </li>
                  );
                })}
                {d.covenant_threshold && <li className="mt-1 flex items-center justify-between text-xs text-fg-muted"><span>Lender&apos;s minimum (covenant)</span><span className="num">{fmtX(d.covenant_threshold)}</span></li>}
              </ul>
            )}
          </Panel>
          <Panel title="Top findings" className="md:col-span-2" actions={<Link href={`${base}/report`} className="text-xs text-accent hover:underline">Open Red-Team Report</Link>}>
            {d.top_findings.length === 0 ? <p className="text-sm text-fg-muted">No findings yet.</p> : (
              <ul className="divide-y divide-hairline">
                {d.top_findings.map((f) => {
                  const title = findingTitle(f);
                  const detail = findingDetail(f, title);
                  return (
                    <li key={f.id} className="flex items-start gap-3 py-2 text-sm">
                      <SeverityChip severity={f.severity} />
                      <div className="min-w-0 flex-1">
                        <Link href={findingHref(base, f)} className="font-medium hover:underline">{title}</Link>
                        {detail && <p className="mt-0.5 line-clamp-2 text-fg-muted">{detail}</p>}
                      </div>
                      <span className="shrink-0 text-[11px] text-fg-muted">{KIND_LABEL[f.kind] ?? titleCase(f.kind)}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </Panel>
          <Panel title="Missing information">
            {d.missing_documents.length === 0 ? <p className="text-sm text-fg-muted">Nothing outstanding.</p> : (
              <ul className="flex flex-col gap-2 text-sm">{d.missing_documents.map((f) => { const title = findingTitle(f); const detail = findingDetail(f, title); return <li key={f.id} className="flex gap-2"><StatusGlyph status="review_required" className="mt-1" /><div><p className="font-medium">{title}</p>{detail && <p className="text-fg-muted">{detail}</p>}</div></li>; })}</ul>
            )}
          </Panel>
          <Panel title="Documents" actions={<Link href={`${base}/documents`} className="text-xs text-accent hover:underline">Open Deal Room</Link>}>
            {noDocs ? <div><p className="text-sm text-fg-muted">No documents yet.</p><Link href={`${base}/documents`} className={buttonClass("primary", "sm", "mt-3")}>Add documents</Link></div> : (
              <ul className="flex flex-col gap-1.5 text-sm">{Object.entries(d.documents).map(([k, v]) => <li key={k} className="flex items-center gap-2"><StatusGlyph status={k} /><span className="flex-1">{STATUS_LABEL[k] ?? k}</span><span className="num">{v.toLocaleString("en-US")}</span></li>)}</ul>
            )}
          </Panel>
          <Panel title="Latest report" actions={<Link href={`${base}/report`} className="text-xs text-accent hover:underline">Open</Link>}>
            {d.latest_report ? (
              <div className="text-sm">
                <p className="font-medium">{titleCase(d.latest_report.outcome)}</p>
                <p className="mt-1 text-fg-muted">Version {d.latest_report.version_no} · {titleCase(d.latest_report.status)} · {fmtDate(d.latest_report.created_at)}</p>
              </div>
            ) : <p className="text-sm text-fg-muted">No report generated yet.</p>}
          </Panel>
        </div>
      </div>
    </div>
  );
}
