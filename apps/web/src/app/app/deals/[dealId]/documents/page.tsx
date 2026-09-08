"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Dialog } from "radix-ui";
import { Upload, RefreshCw, Eye, ChevronDown, Trash2, GitCompare } from "lucide-react";
import { useVersionDiff } from "@/components/app/hooks";
import { api, ApiError, type DealSummary, type Doc, type Job } from "@/lib/api";
import { useDocs, useInvalidateDeal, useJobs, useProcessDeal, useSummary, qk } from "@/components/app/hooks";
import { PageHeader, useDealKicker } from "@/components/app/shell";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui/primitives";
import { Table, td, th } from "@/components/ui/table";
import { StatusChip, StatusGlyph, STATUS_LABEL } from "@/components/domain/status";
import { DOC_PURPOSE, docTypeName } from "@/components/domain/citation";
import { DocumentViewer, type ViewerTarget } from "@/components/domain/document-viewer";
import { useToast } from "@/components/ui/toast";
import { fmtBytes, fmtDateTime, fmtInt, fmtMoney, fmtPct } from "@/lib/format";

const RUNNING = new Set(["queued", "parsing", "extracting"]);
/** The documents a diligence review normally needs, in the order a buyer collects them. */
const EXPECTED = ["cim", "financial_statements", "acquisition_model", "customer_revenue", "debt_term_sheet", "customer_contract"] as const;

export default function DocumentsPage() {
  const { dealId } = useParams<{ dealId: string }>();
  const kicker = useDealKicker();
  const qc = useQueryClient();
  const { toast } = useToast();
  const jobs = useJobs(dealId);
  const live = jobs.data?.some((j) => j.status === "queued" || j.status === "running") ?? false;
  const docs = useDocs(dealId, live);
  const summary = useSummary(dealId);
  const process = useProcessDeal(dealId);
  const [viewer, setViewer] = useState<ViewerTarget | null>(null);
  const [drag, setDrag] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: (files: File[]) => { const fd = new FormData(); files.forEach((f) => fd.append("files", f)); return api.upload<Doc[]>(`/api/deals/${dealId}/documents`, fd); },
    onSuccess: (created) => { qc.invalidateQueries({ queryKey: qk.docs(dealId) }); qc.invalidateQueries({ queryKey: qk.jobs(dealId) }); toast({ title: `${created.length} file${created.length > 1 ? "s" : ""} uploaded`, description: "Reading has started. Run analysis once the files are ready.", tone: "success" }); },
    onError: (e) => { const d = e instanceof ApiError ? e.detail : null; const errs = d && typeof d === "object" && "errors" in d ? (d as { errors: Array<{ file: string; message: string }> }).errors : null; toast({ title: "Upload rejected", description: errs ? errs.map((x) => `${x.file}: ${x.message}`).join(" ") : String(e), tone: "error" }); },
  });
  const reprocess = useMutation({ mutationFn: (id: string) => api.post(`/api/deals/${dealId}/documents/${id}/reprocess`), onSuccess: () => { qc.invalidateQueries({ queryKey: qk.docs(dealId) }); qc.invalidateQueries({ queryKey: qk.jobs(dealId) }); } });
  // Deletion: a confirm step first, then the server removes the document, its evidence, and the claims that came from it.
  // Findings, metrics, and questions are not recomputed by the delete, so the reply's header asks for a re-run and the page keeps asking until one is queued.
  const [toDelete, setToDelete] = useState<Doc | null>(null);
  const [compare, setCompare] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const invalidateDeal = useInvalidateDeal(dealId);
  const runAgain = () => process.mutate(true, { onSuccess: () => { setStale(false); toast({ title: "Analysis queued", description: "Claims, findings, metrics, and questions will be rebuilt from the documents that remain." }); } });
  const remove = useMutation({
    mutationFn: (id: string) => api.del(`/api/deals/${dealId}/documents/${id}`),
    onSuccess: (headers) => {
      setToDelete(null);
      invalidateDeal();
      const reanalyse = headers.get("X-BearCase-Reanalyse") === "true";
      if (reanalyse) setStale(true);
      toast({ title: "Document deleted", description: reanalyse ? "Its evidence and claims are gone. Findings, metrics, and questions may now be out of date." : "Its evidence and claims are gone.", tone: "success", action: reanalyse ? { label: "Run analysis", onClick: runAgain } : undefined });
    },
    onError: (e) => toast({ title: "Could not delete the document", description: String(e), tone: "error" }),
  });
  const onFiles = (list: FileList | null) => { if (list && list.length) upload.mutate(Array.from(list)); };
  const jobFor = (doc: Doc): Job | undefined => jobs.data?.find((j) => j.document_id === doc.id);
  const anyReady = docs.data?.some((d) => d.status === "ready") ?? false;
  const analyzeJob = jobs.data?.find((j) => j.job_type === "analyze_deal");
  return (
    <div>
      <PageHeader kicker={kicker} title="Deal Room" actions={
        <>
          <Button variant="secondary" size="sm" icon={<Upload size={14} />} onClick={() => fileRef.current?.click()} loading={upload.isPending}>Upload</Button>
          <Button size="sm" onClick={() => process.mutate(false, { onSuccess: () => toast({ title: "Analysis queued", description: "Claims will be extracted and verified." }) })} loading={process.isPending} disabled={!anyReady && !(docs.data?.length)}>Run analysis</Button>
        </>
      }>
        <p className="mt-2 max-w-3xl text-sm text-fg-muted">Add the seller’s documents, let BearCase read them, then run analysis. Three questions below: what you uploaded, what we understood, and what is still missing.</p>
        {stale && (
          <div role="status" className="mt-3 flex flex-wrap items-center gap-3 rounded-[var(--radius-2)] border border-amber px-3 py-2 text-sm">
            <StatusGlyph status="review_required" />
            <span className="min-w-0 flex-1">A document was deleted. Findings, metrics, scenarios, and the questions for the seller may be out of date until analysis runs again.</span>
            <Button size="sm" variant="secondary" onClick={runAgain} loading={process.isPending}>Run analysis</Button>
          </div>
        )}
        <input ref={fileRef} type="file" accept=".pdf,.xlsx,.csv" multiple className="sr-only" aria-label="Upload documents" onChange={(e) => { onFiles(e.target.files); e.target.value = ""; }} />
      </PageHeader>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 p-4 md:p-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="flex flex-col gap-4">
          <div role="button" tabIndex={0} aria-label="Drop PDF, XLSX, or CSV files here, or press Enter to choose files" onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") fileRef.current?.click(); }} onClick={() => fileRef.current?.click()} onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={(e) => { e.preventDefault(); setDrag(false); onFiles(e.dataTransfer.files); }} className={`flex flex-col items-center justify-center rounded-[var(--radius-3)] border border-dashed px-6 py-8 text-center transition-colors duration-[120ms] ${drag ? "border-accent bg-accent/5" : "border-hairline"}`}>
            <Upload size={20} className="text-fg-muted" />
            <p className="mt-3 text-sm font-medium">Drop the sales memo, financial statements, acquisition model, customer revenue file, loan term sheet, or contracts</p>
            <p className="mt-1 text-xs text-fg-muted">PDF, XLSX, CSV · up to 25 MB each · files are checked by content, never executed, and duplicates are rejected</p>
          </div>
          <Panel title="What you uploaded" id="uploaded">
            {docs.isPending && <Skeleton className="h-48 w-full" />}
            {docs.isError && <ErrorState detail={String(docs.error)} onRetry={() => docs.refetch()} />}
            {docs.data && docs.data.length === 0 && <EmptyState title="No documents yet" body="Upload the deal documents to start. Reading extracts page, sheet, row, and cell-level evidence that every finding links back to." />}
            {docs.data && docs.data.length > 0 && (
              <Table caption="Documents in this deal">
                <thead><tr><th className={th}>Document</th><th className={th}>Type</th><th className={`${th} text-right`}>Size</th><th className={th}>Status</th><th className={th}><span className="sr-only">Actions</span></th></tr></thead>
                <tbody>
                  {docs.data.map((d) => {
                    const job = jobFor(d);
                    const running = RUNNING.has(d.status);
                    return (
                      <tr key={d.id} className="hover:bg-bg-muted/60">
                        <td className={td}>
                          <p className="font-medium">{d.display_name}</p>
                          <p className="text-xs text-fg-muted">{whatWasRead(d)}</p>
                          <TechnicalDetails d={d} />
                          {compare === d.id && <VersionChanges dealId={dealId} docId={d.id} onReanalyse={() => { process.mutate(true, { onSuccess: () => { setCompare(null); toast({ title: "Analysis queued", description: "Figures and findings will be rebuilt from the revised copy." }); } }); }} />}
                        </td>
                        <td className={td}><span className="text-sm">{docTypeName(d.doc_type)}</span>{d.classification_confidence !== null && Number(d.classification_confidence) < 0.6 && <p className="text-xs text-amber">Unsure; check the type</p>}</td>
                        <td className={`${td} num whitespace-nowrap text-right`}>{d.version ? fmtBytes(d.version.size_bytes) : "—"}</td>
                        <td className={td}>
                          <StatusChip status={d.status} />
                          {running && job && <div className="mt-1.5 h-1 w-28 rounded-[1px] bg-bg-muted" role="progressbar" aria-valuenow={job.progress} aria-valuemin={0} aria-valuemax={100} aria-label={job.step ?? "Processing"}><div className="h-1 bg-amber" style={{ width: `${job.progress}%` }} /></div>}
                          {d.status === "failed" && d.status_detail && <p className="mt-1 max-w-xs text-xs text-red">{d.status_detail}</p>}
                        </td>
                        <td className={`${td} whitespace-nowrap`}>
                          <button type="button" className="mr-1 inline-flex h-7 items-center gap-1 rounded-[var(--radius-1)] px-2 text-xs hover:bg-bg-muted disabled:opacity-40" onClick={() => setViewer({ documentId: d.id, documentName: d.display_name })} disabled={d.status !== "ready"}><Eye size={12} /> View</button>
                          <button type="button" className="mr-1 inline-flex h-7 items-center gap-1 rounded-[var(--radius-1)] px-2 text-xs hover:bg-bg-muted" onClick={() => reprocess.mutate(d.id)}><RefreshCw size={12} /> Read again</button>
                          <RevisedCopy dealId={dealId} doc={d} />
                          {(d.version?.version_no ?? 1) > 1 && <button type="button" className="mr-1 inline-flex h-7 items-center gap-1 rounded-[var(--radius-1)] px-2 text-xs hover:bg-bg-muted" onClick={() => setCompare(compare === d.id ? null : d.id)} aria-expanded={compare === d.id}><GitCompare size={12} /> {compare === d.id ? "Hide changes" : "What changed"}</button>}
                          <button type="button" className="inline-flex h-7 items-center gap-1 rounded-[var(--radius-1)] px-2 text-xs text-fg-muted hover:bg-bg-muted hover:text-red disabled:opacity-40" onClick={() => setToDelete(d)} disabled={running} aria-label={`Delete ${d.display_name}`}><Trash2 size={12} /> Delete</button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            )}
          </Panel>
          <Panel title="What we understood" id="understood">
            <Understood dealId={dealId} docs={docs.data ?? []} analyzeJob={analyzeJob} summary={summary.data ?? null} />
          </Panel>
          <Panel title="What is missing" id="missing">
            <Missing docs={docs.data ?? []} summary={summary.data ?? null} />
          </Panel>
        </div>
        <Panel title="Processing" actions={live && <span className="text-xs font-medium text-amber" aria-live="polite">running</span>}>
          {jobs.isPending && <Skeleton className="h-24" />}
          {jobs.data && jobs.data.length === 0 && <p className="text-sm text-fg-muted">Nothing has been processed yet.</p>}
          {analyzeJob?.status === "failed" && <p className="mb-3 rounded-[var(--radius-2)] border border-red/40 p-2 text-xs text-red">Analysis failed: {analyzeJob.error}</p>}
          <ul className="flex flex-col divide-y divide-hairline">
            {(jobs.data ?? []).slice(0, 12).map((j) => <JobRow key={j.id} job={j} name={docs.data?.find((d) => d.id === j.document_id)?.display_name} />)}
          </ul>
        </Panel>
      </div>
      <DocumentViewer dealId={dealId} target={viewer} onClose={() => setViewer(null)} />
      <DeleteDialog doc={toDelete} pending={remove.isPending} onCancel={() => setToDelete(null)} onConfirm={() => { if (toDelete) remove.mutate(toDelete.id); }} />
    </div>
  );
}

/** The confirm step before a document is deleted: what goes with it, in plain words, and what to do afterwards. */
/** Upload a revised copy of one document as its next version; the earlier file is kept for comparison. */
function RevisedCopy({ dealId, doc }: { dealId: string; doc: Doc }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const ref = useRef<HTMLInputElement>(null);
  const m = useMutation({
    mutationFn: (file: File) => { const fd = new FormData(); fd.append("file", file); return api.post<Doc>(`/api/deals/${dealId}/documents/${doc.id}/versions`, fd); },
    onSuccess: (d) => { qc.invalidateQueries({ queryKey: qk.docs(dealId) }); qc.invalidateQueries({ queryKey: qk.jobs(dealId) }); toast({ title: `Version ${d.version?.version_no ?? ""} uploaded`, description: "The new copy is being read. Findings computed from the old copy stay until you re-run analysis; open “What changed” to see what moved.", tone: "success" }); },
    onError: (e) => toast({ title: "Revised copy rejected", description: e instanceof ApiError ? e.message : String(e), tone: "error" }),
  });
  return (
    <>
      <button type="button" className="mr-1 inline-flex h-7 items-center gap-1 rounded-[var(--radius-1)] px-2 text-xs hover:bg-bg-muted" onClick={() => ref.current?.click()} disabled={m.isPending}><Upload size={12} /> Revised copy</button>
      <input ref={ref} type="file" accept=".pdf,.xlsx,.csv" className="sr-only" aria-label={`Upload a revised copy of ${doc.display_name}`} onChange={(e) => { const f = e.target.files?.[0]; if (f) m.mutate(f); e.target.value = ""; }} />
    </>
  );
}

const LINE_NAMES: Record<string, string> = { revenue: "Revenue", cost_of_goods_sold: "Cost of goods sold", gross_profit: "Gross profit", operating_expenses: "Total operating expenses", ebitda: "EBITDA", net_income: "Net income", depreciation: "Depreciation", amortization: "Amortization", interest_expense: "Interest expense", income_tax_expense: "Income tax expense", operating_income: "Operating income", income_before_tax: "Income before tax" };
const DEP_NAMES: Record<string, string> = { revenue_growth: "revenue growth", cagr: "revenue CAGR", gross_margin: "gross margin", operating_margin: "operating margin", customer_concentration_top1: "largest customer share", recurring_revenue_pct: "recurring revenue share", cfads_base: "CFADS", dscr_base: "DSCR", ebitda_reported: "reported EBITDA", ebitda_adjusted_verified: "checked adjusted EBITDA", ev_to_ebitda_verified: "EV / EBITDA", debt_to_ebitda_verified: "debt / EBITDA", gross_profit: "gross profit" };

/** What changed between the current version and the one before: every mapped figure that moved, what depends on it, and the claims that cite it. */
function VersionChanges({ dealId, docId, onReanalyse }: { dealId: string; docId: string; onReanalyse: () => void }) {
  const q = useVersionDiff(dealId, docId);
  if (q.isPending) return <p className="px-3 py-2 text-xs text-fg-muted">Comparing versions…</p>;
  if (q.isError || !q.data) return <p className="px-3 py-2 text-xs text-red">The versions could not be compared.</p>;
  const d = q.data;
  if (!d.comparable) return <p className="px-3 py-2 text-xs text-fg-muted">{d.reason}</p>;
  return (
    <div className="mx-3 mb-3 rounded-[var(--radius-2)] border border-hairline bg-bg-raised p-3 text-sm">
      <p className="text-xs text-fg-muted">Version {d.old_version} → version {d.new_version}{d.kind === "statement" && d.scale_before !== d.scale_after ? `; scale changed from ×${d.scale_before} to ×${d.scale_after}` : ""}{d.kind === "statement" && JSON.stringify(d.periods_before) !== JSON.stringify(d.periods_after) ? `; years ${d.periods_before?.join(", ")} → ${d.periods_after?.join(", ")}` : ""}.</p>
      {d.kind === "statement" && (d.changes?.length ?? 0) === 0 && <p className="mt-1">No mapped figure changed.</p>}
      {d.kind === "statement" && (d.changes?.length ?? 0) > 0 && (
        <ul className="mt-2 space-y-1.5">
          {d.changes!.map((c) => (
            <li key={`${c.period}|${c.line_key}`}>
              <span className="font-medium">{LINE_NAMES[c.line_key] ?? c.line_key}</span> <span className="text-fg-muted">{c.period}{c.cell ? `, cell ${c.cell}` : ""}</span>: <span className="num text-fg-muted line-through">{fmtMoney(c.before)}</span> <span className="num">{fmtMoney(c.after)}</span>
              {c.dependents.length > 0 && <span className="block text-xs text-fg-muted">Moves {c.dependents.map((k) => DEP_NAMES[k] ?? k).join(", ")}.</span>}
            </li>
          ))}
        </ul>
      )}
      {d.kind === "text" && <p className="mt-1">{d.added?.length ?? 0} passages added, {d.removed?.length ?? 0} removed ({d.chunks_before} → {d.chunks_after} read).</p>}
      {(d.claims_affected?.length ?? 0) > 0 && <p className="mt-2 text-xs text-fg-muted">Claims that cite these lines: {d.claims_affected!.map((c) => `“${c.text.slice(0, 60)}…”`).join("; ")}</p>}
      {d.stale && <div className="mt-2 flex flex-wrap items-center gap-2"><StatusGlyph status="review_required" size={12} /><span className="text-xs">The findings and figures were computed from the old copy.</span><Button size="sm" variant="secondary" onClick={onReanalyse}>Re-run analysis</Button></div>}
    </div>
  );
}

function DeleteDialog({ doc, pending, onCancel, onConfirm }: { doc: Doc | null; pending: boolean; onCancel: () => void; onConfirm: () => void }) {
  return (
    <Dialog.Root open={!!doc} onOpenChange={(o) => { if (!o && !pending) onCancel(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink-950/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(520px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-5 shadow-[var(--shadow-2)] outline-none">
          <Dialog.Title className="text-lg font-medium">Delete {doc?.display_name ?? "this document"}?</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-fg-muted">This cannot be undone. Deleting the document removes:</Dialog.Description>
          <ul className="mt-3 list-disc pl-5 text-sm text-fg-muted">
            <li>the file and every stored version of it;</li>
            <li>the evidence read from it, so citations that pointed at it will no longer open;</li>
            <li>the claims that came from it, with their evidence links and any reviewer decisions on them.</li>
          </ul>
          <p className="mt-3 text-sm text-fg-muted">Findings, metrics, scenarios, and the questions for the seller are not rebuilt by the delete. Run analysis again afterwards so they reflect the documents that remain. The audit history keeps a record that the document was deleted, without its contents.</p>
          <div className="mt-5 flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={onCancel} disabled={pending}>Cancel</Button>
            <Button type="button" variant="danger" onClick={onConfirm} loading={pending} icon={<Trash2 size={14} />}>Delete document</Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** "12 pages", "3 sheets, 214 rows", "1,204 rows": what the reader got out of the file, in the reader's own units. */
function whatWasRead(d: Doc): string {
  const v = d.version;
  if (!v) return "not read yet";
  if (v.page_count) return `${fmtInt(v.page_count)} page${v.page_count === 1 ? "" : "s"} read`;
  if (v.sheet_count) return `${fmtInt(v.sheet_count)} sheet${v.sheet_count === 1 ? "" : "s"}, ${fmtInt(v.row_count)} rows read`;
  if (v.row_count) return `${fmtInt(v.row_count)} rows read`;
  return d.status === "ready" ? "read" : STATUS_LABEL[d.status] ?? d.status;
}

/** Hashes, chunk counts, classification confidence, and MIME: kept for auditors, out of the way for everyone else. */
function TechnicalDetails({ d }: { d: Doc }) {
  return (
    <details className="mt-1 text-xs">
      <summary className="cursor-pointer text-fg-muted hover:text-fg">Technical details</summary>
      <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-[11px] text-fg-muted">
        <dt>SHA-256</dt><dd className="break-all font-mono">{d.version?.sha256 ?? "—"}</dd>
        <dt>Format</dt><dd className="font-mono">{d.version ? `${d.version.extension}${d.version.mime_detected ? ` (${d.version.mime_detected})` : ""}, version ${d.version.version_no}` : "—"}</dd>
        <dt>Evidence chunks</dt><dd className="num">{fmtInt(d.evidence_count)}</dd>
        <dt>Classified by</dt><dd>{d.classification_source}{d.classification_confidence !== null ? `, ${Math.round(Number(d.classification_confidence) * 100)}% confidence` : ""}</dd>
        <dt>Uploaded</dt><dd>{fmtDateTime(d.created_at)}</dd>
        {d.status_detail && d.status !== "failed" && <><dt>Note</dt><dd>{d.status_detail}</dd></>}
      </dl>
    </details>
  );
}

function Understood({ dealId, docs, analyzeJob, summary }: { dealId: string; docs: Doc[]; analyzeJob: Job | undefined; summary: DealSummary | null }) {
  const byType = useMemo(() => { const m = new Map<string, Doc[]>(); for (const d of docs) if (d.status === "ready") m.set(d.doc_type, [...(m.get(d.doc_type) ?? []), d]); return m; }, [docs]);
  if (byType.size === 0) return <p className="text-sm text-fg-muted">Nothing yet. Once a file is read, this section says what kind of document it is and what was found inside.</p>;
  const counts = summary?.claim_counts ?? {};
  const claims = Object.values(counts).reduce((a, b) => a + b, 0);
  const base = `/app/deals/${dealId}`;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div>
        <h3 className="text-xs font-semibold text-fg-muted">From the files</h3>
        <ul className="mt-2 flex flex-col gap-1.5 text-sm">
          {Array.from(byType.entries()).map(([type, list]) => (
            <li key={type} className="flex gap-2"><StatusGlyph status="ready" className="mt-1" /><div><p className="font-medium">{docTypeName(type)}{list.length > 1 ? ` (${list.length} files)` : ""}</p><p className="text-xs text-fg-muted">{list.map((d) => `${d.display_name}: ${whatWasRead(d)}`).join(" · ")}</p></div></li>
          ))}
        </ul>
      </div>
      <div>
        <h3 className="text-xs font-semibold text-fg-muted">From the analysis</h3>
        {analyzeJob?.status === "succeeded" || claims > 0 ? (
          <ul className="mt-2 flex flex-col gap-1.5 text-sm">
            <li><span className="num font-medium">{fmtInt(claims)}</span> claims found: <span className="num">{counts.supported ?? 0}</span> supported, <span className="num">{counts.contradicted ?? 0}</span> contradicted, <span className="num">{counts.unsupported ?? 0}</span> unsupported, <span className="num">{counts.review_required ?? 0}</span> need review. <Link href={`${base}/claims`} className="text-accent hover:underline">Review the claims</Link></li>
            {summary?.seller_adjusted_ebitda && <li>Seller’s adjusted EBITDA <span className="num">{fmtMoney(summary.seller_adjusted_ebitda)}</span>; verified <span className="num">{fmtMoney(summary.verified_adjusted_ebitda)}</span>. <Link href={`${base}/financials`} className="text-accent hover:underline">See what changed</Link></li>}
            {summary?.dscr_by_scenario?.length ? <li>Debt coverage by scenario: {summary.dscr_by_scenario.map((s) => `${s.name} ${s.dscr ? `${Number(s.dscr).toFixed(2)}x` : "n/a"}`).join(", ")}{summary.covenant_threshold ? ` (covenant ${Number(summary.covenant_threshold).toFixed(2)}x)` : ""}. <Link href={`${base}/scenarios`} className="text-accent hover:underline">Test a downside</Link></li> : null}
            {analyzeJob?.finished_at && <li className="text-xs text-fg-muted">Analysis completed {fmtDateTime(analyzeJob.finished_at)}{summary?.mode ? ` with ${summary.mode.provider === "mock" ? "the rule-based mock" : summary.mode.provider}` : ""}.</li>}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-fg-muted">{analyzeJob && (analyzeJob.status === "queued" || analyzeJob.status === "running") ? `Analysis is running${analyzeJob.step ? `: ${analyzeJob.step}` : ""}.` : analyzeJob?.status === "failed" ? "The last analysis failed; see Processing." : "Analysis has not run yet. Press Run analysis to extract and check the claims."}</p>
        )}
      </div>
    </div>
  );
}

function Missing({ docs, summary }: { docs: Doc[]; summary: DealSummary | null }) {
  const have = new Set(docs.filter((d) => d.status !== "failed").map((d) => d.doc_type));
  const absent = EXPECTED.filter((t) => !have.has(t));
  const findings = summary?.missing_documents ?? [];
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div>
        <h3 className="text-xs font-semibold text-fg-muted">Document checklist</h3>
        <ul className="mt-2 flex flex-col gap-1.5 text-sm">
          {EXPECTED.map((t) => { const ok = have.has(t); return (
            <li key={t} className="flex gap-2"><StatusGlyph status={ok ? "ready" : "unsupported"} className="mt-1" /><div><p className={ok ? "" : "font-medium"}>{docTypeName(t)} <span className="text-xs font-normal text-fg-muted">{ok ? "uploaded" : "not uploaded"}</span></p>{!ok && <p className="text-xs text-fg-muted">{DOC_PURPOSE[t]}</p>}</div></li>
          ); })}
        </ul>
        {absent.length === 0 && <p className="mt-2 text-xs text-fg-muted">Every expected document type is present.</p>}
      </div>
      <div>
        <h3 className="text-xs font-semibold text-fg-muted">Flagged by the analysis</h3>
        {findings.length === 0 ? <p className="mt-2 text-sm text-fg-muted">{summary ? "Nothing outstanding from the last analysis." : "Run analysis to see what the review still needs."}</p> : (
          <ul className="mt-2 flex flex-col gap-2 text-sm">{findings.map((f) => <li key={f.id} className="flex gap-2"><StatusGlyph status="review_required" className="mt-1" /><div><p className="font-medium">{f.title.replace("Missing: ", "")}</p><p className="text-xs text-fg-muted">{f.detail}</p></div></li>)}</ul>
        )}
        {summary?.documents && Object.keys(summary.documents).length > 0 && <p className="mt-3 text-xs text-fg-muted">Document status: {Object.entries(summary.documents).map(([k, v]) => `${v} ${STATUS_LABEL[k]?.toLowerCase() ?? k}`).join(", ")}{typeof summary.claim_counts.review_required === "number" && claimsTotal(summary.claim_counts) > 0 ? `; ${fmtPct((summary.claim_counts.review_required / claimsTotal(summary.claim_counts)) * 100, 0)} of claims need review` : ""}.</p>}
      </div>
    </div>
  );
}

function claimsTotal(counts: Record<string, number>): number {
  return Object.values(counts).reduce((a, b) => a + b, 0);
}

function JobRow({ job, name }: { job: Job; name?: string }) {
  const [open, setOpen] = useState(false);
  const title = job.job_type === "process_document" ? `Reading ${name ?? "document"}` : job.job_type === "analyze_deal" ? "Deal analysis" : "Report generation";
  return (
    <li className="py-2 text-sm">
      <button type="button" className="flex w-full items-center gap-2 text-left" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <StatusGlyph status={job.status === "running" ? "running" : job.status} />
        <span className="min-w-0 flex-1 truncate">{title}</span>
        <span className="num text-xs text-fg-muted">{job.status === "running" ? `${job.progress}%` : fmtDateTime(job.finished_at ?? job.created_at)}</span>
        <ChevronDown size={12} className={`text-fg-muted transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {job.step && job.status === "running" && <p className="mt-0.5 pl-6 text-xs text-fg-muted" aria-live="polite">{job.step}</p>}
      {open && (
        <ol className="mt-2 flex flex-col gap-0.5 pl-6 font-mono text-[11px] text-fg-muted" aria-label="Job log">
          {job.log.map((l, i) => <li key={i}>{String(l.at).slice(11, 19)} · {String(l.step)}{l.error ? ` · ${String(l.error)}` : ""}</li>)}
        </ol>
      )}
    </li>
  );
}
