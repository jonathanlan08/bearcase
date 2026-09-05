"use client";

import { useParams } from "next/navigation";
import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload, RefreshCw, Eye, ChevronDown } from "lucide-react";
import { api, ApiError, type Doc, type Job } from "@/lib/api";
import { useDocs, useJobs, useProcessDeal, qk } from "@/components/app/hooks";
import { PageHeader, useDealKicker } from "@/components/app/shell";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui/primitives";
import { Table, td, th } from "@/components/ui/table";
import { StatusChip, StatusGlyph } from "@/components/domain/status";
import { DocumentViewer, type ViewerTarget } from "@/components/domain/document-viewer";
import { useToast } from "@/components/ui/toast";
import { fmtDate, fmtInt, titleCase } from "@/lib/format";

const RUNNING = new Set(["queued", "parsing", "extracting"]);

export default function DocumentsPage() {
  const { dealId } = useParams<{ dealId: string }>();
  const kicker = useDealKicker();
  const qc = useQueryClient();
  const { toast } = useToast();
  const jobs = useJobs(dealId);
  const live = jobs.data?.some((j) => j.status === "queued" || j.status === "running") ?? false;
  const docs = useDocs(dealId, live);
  const process = useProcessDeal(dealId);
  const [viewer, setViewer] = useState<ViewerTarget | null>(null);
  const [drag, setDrag] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: (files: File[]) => { const fd = new FormData(); files.forEach((f) => fd.append("files", f)); return api.upload<Doc[]>(`/api/deals/${dealId}/documents`, fd); },
    onSuccess: (created) => { qc.invalidateQueries({ queryKey: qk.docs(dealId) }); qc.invalidateQueries({ queryKey: qk.jobs(dealId) }); toast({ title: `${created.length} file${created.length > 1 ? "s" : ""} uploaded`, description: "Parsing has started.", tone: "success" }); },
    onError: (e) => { const d = e instanceof ApiError ? e.detail : null; const errs = d && typeof d === "object" && "errors" in d ? (d as { errors: Array<{ file: string; message: string }> }).errors : null; toast({ title: "Upload rejected", description: errs ? errs.map((x) => `${x.file}: ${x.message}`).join(" ") : String(e), tone: "error" }); },
  });
  const reprocess = useMutation({ mutationFn: (id: string) => api.post(`/api/deals/${dealId}/documents/${id}/reprocess`), onSuccess: () => { qc.invalidateQueries({ queryKey: qk.docs(dealId) }); qc.invalidateQueries({ queryKey: qk.jobs(dealId) }); } });
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
        <input ref={fileRef} type="file" accept=".pdf,.xlsx,.csv" multiple className="sr-only" aria-label="Upload documents" onChange={(e) => { onFiles(e.target.files); e.target.value = ""; }} />
      </PageHeader>
      <div className="grid gap-4 p-4 md:p-6 xl:grid-cols-[1fr_360px]">
        <div className="flex flex-col gap-4">
          <div role="button" tabIndex={0} aria-label="Drop PDF, XLSX, or CSV files here, or press Enter to choose files" onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") fileRef.current?.click(); }} onClick={() => fileRef.current?.click()} onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={(e) => { e.preventDefault(); setDrag(false); onFiles(e.dataTransfer.files); }} className={`flex flex-col items-center justify-center rounded-[var(--radius-3)] border border-dashed px-6 py-8 text-center transition-colors duration-[120ms] ${drag ? "border-accent bg-accent/5" : "border-hairline"}`}>
            <Upload size={20} className="text-fg-muted" />
            <p className="mt-3 text-sm font-medium">Drop a CIM, financial statements, acquisition model, customer revenue file, term sheet, or contracts</p>
            <p className="mt-1 text-xs text-fg-muted">PDF, XLSX, CSV · up to 25 MB each · files are validated by content, never executed, and duplicates are rejected</p>
          </div>
          {docs.isPending && <Skeleton className="h-48 w-full" />}
          {docs.isError && <ErrorState detail={String(docs.error)} onRetry={() => docs.refetch()} />}
          {docs.data && docs.data.length === 0 && <EmptyState title="No documents yet" body="Upload the deal documents to start. Processing extracts page, sheet, row, and cell-level evidence." />}
          {docs.data && docs.data.length > 0 && (
            <Table caption="Documents in this deal">
              <thead><tr><th className={th}>Document</th><th className={th}>Type</th><th className={`${th} text-right`}>Size</th><th className={th}>Status</th><th className={th}>Hash</th><th className={th}><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {docs.data.map((d) => {
                  const job = jobFor(d);
                  const running = RUNNING.has(d.status);
                  return (
                    <tr key={d.id} className="hover:bg-bg-muted/60">
                      <td className={td}><p className="font-medium">{d.display_name}</p><p className="text-xs text-fg-muted">{d.version?.page_count ? `${d.version.page_count} pages` : d.version?.sheet_count ? `${d.version.sheet_count} sheets · ${fmtInt(d.version.row_count)} rows` : d.version?.row_count ? `${fmtInt(d.version.row_count)} rows` : "—"} · {fmtInt(d.evidence_count)} chunks</p></td>
                      <td className={td}><span className="text-sm">{titleCase(d.doc_type)}</span><p className="text-xs text-fg-muted">{d.classification_source}{d.classification_confidence ? ` · ${Math.round(Number(d.classification_confidence) * 100)}%` : ""}</p></td>
                      <td className={`${td} num text-right`}>{d.version ? `${(d.version.size_bytes / 1024).toFixed(0)} KB` : "—"}</td>
                      <td className={td}>
                        <StatusChip status={d.status} />
                        {running && job && <div className="mt-1.5 h-1 w-28 rounded-[1px] bg-bg-muted" role="progressbar" aria-valuenow={job.progress} aria-valuemin={0} aria-valuemax={100} aria-label={job.step ?? "Processing"}><div className="h-1 bg-amber" style={{ width: `${job.progress}%` }} /></div>}
                        {d.status === "failed" && d.status_detail && <p className="mt-1 max-w-xs font-mono text-[11px] text-red">{d.status_detail}</p>}
                      </td>
                      <td className={`${td} font-mono text-xs text-fg-muted`} title={d.version?.sha256}>{d.version?.sha256.slice(0, 10)}</td>
                      <td className={`${td} whitespace-nowrap`}>
                        <button type="button" className="mr-1 inline-flex h-7 items-center gap-1 rounded-[var(--radius-1)] px-2 text-xs hover:bg-bg-muted disabled:opacity-40" onClick={() => setViewer({ documentId: d.id, documentName: d.display_name })} disabled={d.status !== "ready"}><Eye size={12} /> View</button>
                        <button type="button" className="inline-flex h-7 items-center gap-1 rounded-[var(--radius-1)] px-2 text-xs hover:bg-bg-muted" onClick={() => reprocess.mutate(d.id)}><RefreshCw size={12} /> Reprocess</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </div>
        <Panel title="Processing" actions={live && <span className="micro text-amber" aria-live="polite">running…</span>}>
          {jobs.isPending && <Skeleton className="h-24" />}
          {jobs.data && jobs.data.length === 0 && <p className="text-sm text-fg-muted">No jobs yet.</p>}
          {analyzeJob?.status === "failed" && <p className="mb-3 rounded-[var(--radius-2)] border border-red/40 p-2 text-xs text-red">Analysis failed: {analyzeJob.error}</p>}
          <ul className="flex flex-col divide-y divide-hairline">
            {(jobs.data ?? []).slice(0, 12).map((j) => <JobRow key={j.id} job={j} name={docs.data?.find((d) => d.id === j.document_id)?.display_name} />)}
          </ul>
        </Panel>
      </div>
      <DocumentViewer dealId={dealId} target={viewer} onClose={() => setViewer(null)} />
    </div>
  );
}

function JobRow({ job, name }: { job: Job; name?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="py-2 text-sm">
      <button type="button" className="flex w-full items-center gap-2 text-left" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <StatusGlyph status={job.status === "running" ? "running" : job.status} />
        <span className="min-w-0 flex-1 truncate">{job.job_type === "process_document" ? name ?? "Document" : job.job_type === "analyze_deal" ? "Deal analysis" : "Report generation"}</span>
        <span className="num text-xs text-fg-muted">{job.status === "running" ? `${job.progress}%` : fmtDate(job.finished_at ?? job.created_at)}</span>
        <ChevronDown size={12} className={`text-fg-muted transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {job.step && job.status === "running" && <p className="mt-0.5 pl-6 text-xs text-fg-muted" aria-live="polite">{job.step}</p>}
      {open && (
        <ol className="mt-2 flex flex-col gap-0.5 pl-6 font-mono text-[11px] text-fg-muted">
          {job.log.map((l, i) => <li key={i}>{String(l.at).slice(11, 19)} · {String(l.step)}{l.error ? ` · ${String(l.error)}` : ""}</li>)}
        </ol>
      )}
    </li>
  );
}
