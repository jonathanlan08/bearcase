"use client";

import { useParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, RefreshCw } from "lucide-react";
import { api, type Evidence } from "@/lib/api";
import { useEvidence, useJobs, useReport, qk } from "@/components/app/hooks";
import { useSummary } from "@/components/app/hooks";
import { ConfidenceLine, SummaryPdfButton } from "../page";
import { PageHeader, useDealKicker } from "@/components/app/shell";
import { Button, buttonClass } from "@/components/ui/button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { StatusGlyph } from "@/components/domain/status";
import { OUTCOME_LABEL, ReportBody, ReportToc, outcomeStatus } from "@/components/domain/report-view";
import { ReportShareButton } from "@/components/domain/report-share";
import { DocumentViewer, type ViewerTarget } from "@/components/domain/document-viewer";
import { StatementKindsLegend } from "@/components/domain/statement-kinds";
import { fmtDateTime, titleCase } from "@/lib/format";
import { useToast } from "@/components/ui/toast";

export default function ReportPage() {
  const { dealId } = useParams<{ dealId: string }>();
  const kicker = useDealKicker();
  const qc = useQueryClient();
  const { toast } = useToast();
  const report = useReport(dealId);
  const summary = useSummary(dealId);
  const jobs = useJobs(dealId);
  const running = jobs.data?.some((j) => j.job_type === "generate_report" && (j.status === "queued" || j.status === "running")) ?? false;
  const generate = useMutation({ mutationFn: () => api.post(`/api/deals/${dealId}/report`), onSuccess: () => { qc.invalidateQueries({ queryKey: qk.jobs(dealId) }); toast({ title: "Report generation queued" }); window.setTimeout(() => qc.invalidateQueries({ queryKey: qk.report(dealId) }), 2500); } });
  const [peek, setPeek] = useState<string | null>(null);
  const [viewer, setViewer] = useState<ViewerTarget | null>(null);
  const ev = useEvidence(dealId, peek);
  // Click on any citation chip, at every breakpoint, opens the document at the cited location; the peek stays hover/focus only.
  const openEvidence = useCallback((id: string) => {
    qc.fetchQuery({ queryKey: qk.evidence(dealId, id), queryFn: () => api.get<Evidence>(`/api/deals/${dealId}/evidence/${id}`) })
      .then((e) => setViewer({ documentId: e.document_id, documentName: e.document_name, evidenceId: e.id, locator: e.locator }))
      .catch(() => toast({ title: "Could not open the source", description: "Please try again.", tone: "error" }));
  }, [dealId, qc, toast]);
  const r = report.data;
  const toc = useMemo(() => (r?.sections ?? []).map((s) => ({ key: s.key, title: s.title })), [r]);
  return (
    <div>
      <PageHeader kicker={kicker} title="Red-Team Report" actions={
        <>
          <SummaryPdfButton dealId={dealId} />
          <Button variant="secondary" size="sm" icon={<RefreshCw size={14} />} onClick={() => generate.mutate()} loading={generate.isPending || running}>{r ? "Regenerate" : "Generate report"}</Button>
          {r && r.status === "validated" && (<><a className={buttonClass("secondary", "sm")} href={`/api/deals/${dealId}/reports/${r.id}/export?format=md`}><Download size={14} /> Markdown</a><a className={buttonClass("secondary", "sm")} href={`/api/deals/${dealId}/reports/${r.id}/export?format=pdf`}><Download size={14} /> PDF</a><ReportShareButton dealId={dealId} reportId={r.id} versionNo={r.version_no} /></>)}
        </>
      }>
        {r && (
          <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
            <span className="inline-flex items-center gap-2 rounded-[var(--radius-1)] border border-hairline px-3 py-1 font-medium"><StatusGlyph status={outcomeStatus(r.outcome)} />{OUTCOME_LABEL[r.outcome] ?? titleCase(r.outcome)}</span>
            <span className="inline-flex items-center gap-1.5"><StatusGlyph status={r.validation.valid ? "supported" : "contradicted"} size={12} /><span className="num">{r.validation.material_cited}/{r.validation.material_statements}</span> material statements cited</span>
            <span className="text-fg-muted">Version {r.version_no}, {fmtDateTime(r.created_at)}</span>
            <span className="text-xs text-fg-muted">{r.provider}/{r.model}, prompt {r.prompt_version}, schema {r.schema_version}, engine {r.engine_version}</span>
          </div>
        )}
        {r && (
          <div className="mt-3 max-w-3xl">
            {summary.data && <ConfidenceLine c={summary.data.confidence} className="mt-0 mb-2" />}
            <StatementKindsLegend />
            <p className="mt-1.5 text-xs text-fg-muted">A citation shows where a statement came from, not that the statement is correct. Open the source before you rely on it.</p>
          </div>
        )}
      </PageHeader>
      {report.isPending && <div className="p-6"><Skeleton className="h-6 w-1/2" /><Skeleton className="mt-4 h-64" /></div>}
      {report.isError && <div className="p-6"><ErrorState detail={String(report.error)} onRetry={() => report.refetch()} /></div>}
      {report.data === null && <div className="p-6"><EmptyState title="No report yet" body="Generate the investment-committee red-team review from the checked claims, financials, scenarios, and reviewer decisions." action={<Button onClick={() => generate.mutate()} loading={generate.isPending || running}>Generate report</Button>} /></div>}
      {r && (
        <div className="grid gap-6 p-4 md:p-6 lg:grid-cols-[180px_minmax(0,1fr)] 2xl:grid-cols-[180px_minmax(0,1fr)_260px]">
          <ReportToc sections={toc} />
          <article className="min-w-0 max-w-[76ch]">
            {!r.validation.valid && (
              <div role="alert" className="mb-6 rounded-[var(--radius-3)] border border-red/40 bg-bg-raised p-4 text-sm">
                <p className="font-medium text-red">Validation failed: export is disabled until every material statement is cited.</p>
                <ul className="mt-2 list-disc pl-5 text-fg-muted">{r.validation.uncited.slice(0, 8).map((u, i) => <li key={i}><span className="font-mono text-xs">{u.section}</span>: {u.text}</li>)}</ul>
              </div>
            )}
            <ReportBody sections={r.sections} cite={(kind, id) => <Cite id={id} kind={kind} onPeek={setPeek} onOpen={openEvidence} active={kind === "E" && peek === id} />} />
          </article>
          <aside className="hidden 2xl:sticky 2xl:top-4 2xl:block 2xl:self-start">
            <div className="rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-3 text-sm">
              <p className="micro">Evidence peek</p>
              {!peek && <p className="mt-2 text-fg-muted">Hover or focus a citation chip to preview its evidence here. Click a chip to open the document.</p>}
              {peek && ev.isPending && <Skeleton className="mt-2 h-20" />}
              {ev.data && (
                <div className="mt-2">
                  <p className="font-mono text-[11px] text-fg-muted">{ev.data.document_name}</p>
                  <p className="mt-1 line-clamp-[8]">{ev.data.text}</p>
                  <button type="button" className="mt-2 text-xs text-accent hover:underline" onClick={() => setViewer({ documentId: ev.data.document_id, documentName: ev.data.document_name, evidenceId: ev.data.id, locator: ev.data.locator })}>Open in document</button>
                </div>
              )}
            </div>
          </aside>
        </div>
      )}
      <DocumentViewer dealId={dealId} target={viewer} onClose={() => setViewer(null)} />
    </div>
  );
}

function Cite({ id, kind, onPeek, onOpen, active }: { id: string; kind: "E" | "M"; onPeek: (id: string | null) => void; onOpen: (id: string) => void; active: boolean }) {
  const label = `${kind}:${id.slice(0, 6)}`;
  if (kind === "M") return <span className="inline-flex h-[18px] items-center rounded-[var(--radius-1)] border border-hairline bg-bg-muted px-1 font-mono text-[10.5px] text-fg-muted" title="Calculation citation: computed by the deterministic engine">{label}</span>;
  return <button type="button" onMouseEnter={() => onPeek(id)} onFocus={() => onPeek(id)} onClick={() => onOpen(id)} aria-pressed={active} className={`inline-flex h-[18px] items-center rounded-[var(--radius-1)] border px-1 font-mono text-[10.5px] ${active ? "border-accent bg-accent/10" : "border-hairline bg-bg-muted hover:border-accent"}`} title="Evidence citation: click to open the document at this spot">{label}</button>;
}
