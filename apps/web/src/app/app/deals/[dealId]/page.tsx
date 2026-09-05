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

export default function OverviewPage() {
  const { dealId } = useParams<{ dealId: string }>();
  const s = useSummary(dealId);
  const kicker = useDealKicker();
  const process = useProcessDeal(dealId);
  const { toast } = useToast();
  const base = `/app/deals/${dealId}`;
  if (s.isPending) return <div className="p-6"><Skeleton className="h-8 w-64" /><div className="mt-6 grid gap-4 md:grid-cols-2"><Skeleton className="h-40" /><Skeleton className="h-40" /><Skeleton className="h-40" /><Skeleton className="h-40" /></div></div>;
  if (s.isError) return <div className="p-6"><ErrorState detail={String(s.error)} onRetry={() => s.refetch()} /></div>;
  const d = s.data;
  const total = Object.values(d.claim_counts).reduce((a, b) => a + b, 0);
  const order = ["supported", "contradicted", "review_required", "unsupported"] as const;
  const docsTotal = Object.values(d.documents).reduce((a, b) => a + b, 0);
  const noDocs = docsTotal === 0;
  return (
    <div>
      <PageHeader kicker={kicker} title="Deal overview" actions={
        <>
          {d.active_jobs > 0 && <span className="text-xs font-medium text-amber" aria-live="polite">{d.active_jobs} job{d.active_jobs > 1 ? "s" : ""} running…</span>}
          <Button variant="secondary" size="sm" onClick={() => process.mutate(true, { onSuccess: () => toast({ title: "Reprocessing queued", description: "Documents will be parsed and analysed again." }) })} loading={process.isPending} disabled={noDocs}>Re-run analysis</Button>
        </>
      } />
      <div className="grid gap-4 p-4 md:grid-cols-2 md:p-6 xl:grid-cols-3">
        <Panel title="Claim verification" actions={<Link href={`${base}/claims`} className="text-xs text-accent hover:underline">Open Claim Audit</Link>}>
          {total === 0 ? <p className="text-sm text-fg-muted">{noDocs ? "Upload documents in the Deal Room to begin." : "No claims yet. Run analysis to extract and verify claims."}</p> : (
            <>
              <div className="flex h-3 w-full overflow-hidden rounded-[var(--radius-1)] border border-hairline" role="img" aria-label={order.map((k) => `${STATUS_LABEL[k]} ${d.claim_counts[k] ?? 0}`).join(", ")}>
                {order.map((k) => <span key={k} style={{ width: `${((d.claim_counts[k] ?? 0) / total) * 100}%` }} className={k === "supported" ? "bg-accent" : k === "contradicted" ? "bg-red" : k === "review_required" ? "bg-amber" : "bg-graphite diag-hatch"} />)}
              </div>
              <ul className="mt-3 grid grid-cols-2 gap-2 text-sm">
                {order.map((k) => <li key={k} className="flex items-center gap-2"><StatusGlyph status={k} /><span className="flex-1">{STATUS_LABEL[k]}</span><span className="num">{d.claim_counts[k] ?? 0}</span></li>)}
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
        <Panel title="DSCR by scenario" actions={<Link href={`${base}/scenarios`} className="text-xs text-accent hover:underline">Open Scenario Lab</Link>}>
          {d.dscr_by_scenario.length === 0 ? <p className="text-sm text-fg-muted">Scenarios run after analysis.</p> : (
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
              {d.covenant_threshold && <li className="mt-1 flex items-center justify-between text-xs text-fg-muted"><span>Covenant threshold</span><span className="num">{fmtX(d.covenant_threshold)}</span></li>}
            </ul>
          )}
        </Panel>
        <Panel title="Top findings" className="md:col-span-2" actions={<Link href={`${base}/report`} className="text-xs text-accent hover:underline">Open Red-Team Report</Link>}>
          {d.top_findings.length === 0 ? <p className="text-sm text-fg-muted">No findings yet.</p> : (
            <ul className="divide-y divide-hairline">
              {d.top_findings.map((f) => (
                <li key={f.id} className="flex items-start gap-3 py-2 text-sm">
                  <SeverityChip severity={f.severity} />
                  <div className="min-w-0 flex-1"><p className="font-medium">{f.title}</p><p className="mt-0.5 line-clamp-2 text-fg-muted">{f.detail}</p></div>
                  <span className="shrink-0 text-[11px] text-fg-muted">{titleCase(f.kind)}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Missing information">
          {d.missing_documents.length === 0 ? <p className="text-sm text-fg-muted">Nothing outstanding.</p> : (
            <ul className="flex flex-col gap-2 text-sm">{d.missing_documents.map((f) => <li key={f.id} className="flex gap-2"><StatusGlyph status="review_required" className="mt-1" /><div><p className="font-medium">{f.title.replace("Missing: ", "")}</p><p className="text-fg-muted">{f.detail}</p></div></li>)}</ul>
          )}
        </Panel>
        <Panel title="Documents" actions={<Link href={`${base}/documents`} className="text-xs text-accent hover:underline">Open Deal Room</Link>}>
          {docsTotal === 0 ? <div><p className="text-sm text-fg-muted">No documents uploaded.</p><Link href={`${base}/documents`} className={buttonClass("primary", "sm", "mt-3")}>Upload documents</Link></div> : (
            <ul className="flex flex-col gap-1.5 text-sm">{Object.entries(d.documents).map(([k, v]) => <li key={k} className="flex items-center gap-2"><StatusGlyph status={k} /><span className="flex-1">{STATUS_LABEL[k] ?? k}</span><span className="num">{v}</span></li>)}</ul>
          )}
        </Panel>
        <Panel title="Latest report" actions={<Link href={`${base}/report`} className="text-xs text-accent hover:underline">Open</Link>}>
          {d.latest_report ? (
            <div className="text-sm">
              <p className="font-medium">{titleCase(d.latest_report.outcome)}</p>
              <p className="mt-1 text-fg-muted">v{d.latest_report.version_no} · {d.latest_report.status} · {fmtDate(d.latest_report.created_at)}</p>
            </div>
          ) : <p className="text-sm text-fg-muted">No report generated yet.</p>}
        </Panel>
      </div>
    </div>
  );
}
