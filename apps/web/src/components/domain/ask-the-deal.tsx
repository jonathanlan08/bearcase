"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Dialog } from "radix-ui";
import { MessageSquareText, Send, X } from "lucide-react";
import { api, type Evidence } from "@/lib/api";
import { qk, useEvidence } from "@/components/app/hooks";
import { Button } from "@/components/ui/button";
import { Kbd, Skeleton } from "@/components/ui/primitives";
import { StatusGlyph } from "@/components/domain/status";
import { CitationChip } from "@/components/domain/citation";
import { DocumentViewer, type ViewerTarget } from "@/components/domain/document-viewer";
import { fmtDate } from "@/lib/format";

interface Statement { text: string; evidence_ids: string[]; metric_ids: string[] }
interface Answer { id: string; question: string; intents: string[]; statements: Statement[]; grounded: boolean; validation: { material_statements: number; material_cited: number; dropped_uncited?: number }; provider: string; model: string; prompt_version: string; error: string | null; created_at: string }

const qkq = (id: string) => ["questions", id] as const;

export function AskTheDeal({ dealId }: { dealId: string }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key === "/") { e.preventDefault(); setOpen((o) => !o); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button type="button" className="fixed bottom-20 right-4 z-40 inline-flex h-11 items-center gap-2 rounded-full border border-hairline bg-fg px-4 text-sm font-medium text-bg shadow-[var(--shadow-2)] hover:opacity-90 md:bottom-5 md:right-5" aria-label="Ask the Deal (Cmd+/)">
          <MessageSquareText size={16} /> Ask the Deal
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink-950/30" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[560px] flex-col bg-bg-raised shadow-[var(--shadow-2)] outline-none md:w-[48vw]" aria-describedby="ask-desc">
          {open && <AskPanel dealId={dealId} onClose={() => setOpen(false)} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function AskPanel({ dealId, onClose }: { dealId: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [viewer, setViewer] = useState<ViewerTarget | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const suggested = useQuery({ queryKey: ["suggested", dealId], queryFn: () => api.get<string[]>(`/api/deals/${dealId}/questions/suggested`) });
  const history = useQuery({ queryKey: qkq(dealId), queryFn: () => api.get<Answer[]>(`/api/deals/${dealId}/questions`) });
  const ask = useMutation({ mutationFn: (question: string) => api.post<Answer>(`/api/deals/${dealId}/ask`, { question }), onSuccess: () => { qc.invalidateQueries({ queryKey: qkq(dealId) }); qc.invalidateQueries({ queryKey: qk.audit(dealId) }); setQ(""); } });
  useEffect(() => { inputRef.current?.focus(); }, []);
  const submit = (question: string) => { const t = question.trim(); if (t.length >= 3 && !ask.isPending) ask.mutate(t); };
  const answers = history.data ?? [];
  return (
    <>
      <div className="flex h-14 items-center gap-3 border-b border-hairline px-4">
        <MessageSquareText size={16} className="text-fg-muted" />
        <div className="min-w-0 flex-1">
          <Dialog.Title className="text-sm font-medium">Ask the Deal</Dialog.Title>
          <Dialog.Description id="ask-desc" className="truncate text-[11px] text-fg-muted">Answers come only from persisted, verified rows. Every factual sentence cites evidence or a calculation.</Dialog.Description>
        </div>
        <Kbd>⌘/</Kbd>
        <Dialog.Close className="rounded-[var(--radius-1)] p-1.5 text-fg-muted hover:bg-bg-muted" aria-label="Close" onClick={onClose}><X size={16} /></Dialog.Close>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {history.isPending && <Skeleton className="h-24" />}
        {answers.length === 0 && !history.isPending && (
          <div className="rounded-[var(--radius-3)] border border-dashed border-hairline p-4 text-sm text-fg-muted">
            <p>Try a question about the review. The answer is assembled from the claim ledger, verified metrics, add-back decisions, scenario runs, and findings; nothing is calculated on the fly.</p>
          </div>
        )}
        {ask.isPending && <div className="mb-3 rounded-[var(--radius-3)] border border-hairline p-3 text-sm" aria-live="polite"><p className="font-medium">{ask.variables}</p><Skeleton className="mt-2 h-14" /></div>}
        <ol className="flex flex-col gap-3">
          {answers.map((a) => <AnswerCard key={a.id} a={a} dealId={dealId} onOpen={setViewer} />)}
        </ol>
      </div>
      <div className="border-t border-hairline p-3">
        {suggested.data && answers.length < 3 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {suggested.data.map((s) => <button key={s} type="button" className="rounded-full border border-hairline px-2.5 py-1 text-xs hover:bg-bg-muted" onClick={() => submit(s)}>{s}</button>)}
          </div>
        )}
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); submit(q); }}>
          <input ref={inputRef} aria-label="Question" placeholder="Why was adjusted EBITDA reduced?" className="h-10 min-w-0 flex-1 rounded-[var(--radius-1)] border border-hairline bg-bg-raised px-3 text-sm" value={q} onChange={(e) => setQ(e.target.value)} maxLength={1000} />
          <Button type="submit" icon={<Send size={14} />} loading={ask.isPending} disabled={q.trim().length < 3}>Ask</Button>
        </form>
        {ask.isError && <p role="alert" className="mt-2 text-xs text-red">{String(ask.error)}</p>}
      </div>
      <DocumentViewer dealId={dealId} target={viewer} onClose={() => setViewer(null)} />
    </>
  );
}

function AnswerCard({ a, dealId, onOpen }: { a: Answer; dealId: string; onOpen: (t: ViewerTarget) => void }) {
  return (
    <li className="rounded-[var(--radius-3)] border border-hairline p-3">
      <p className="text-sm font-medium">{a.question}</p>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-fg-muted">
        <span className="inline-flex items-center gap-1"><StatusGlyph status={a.grounded ? "supported" : "review_required"} size={11} />{a.grounded ? "Fully grounded" : `${a.validation.material_cited}/${a.validation.material_statements} material sentences cited${a.validation.dropped_uncited ? `, ${a.validation.dropped_uncited} removed` : ""}`}</span>
        <span className="font-mono">{a.provider}/{a.model} · prompt {a.prompt_version}</span>
        <span>{fmtDate(a.created_at)}</span>
      </div>
      {a.error && <p className="mt-2 text-xs text-red">Provider error: {a.error}</p>}
      <ul className="mt-3 flex flex-col gap-2 text-sm leading-relaxed">
        {a.statements.map((s, i) => (
          <li key={i}>
            {s.text}
            <span className="ml-1 inline-flex flex-wrap gap-1 align-middle">
              {s.evidence_ids.slice(0, 4).map((e) => <EvidenceCite key={e} dealId={dealId} id={e} onOpen={onOpen} />)}
              {s.metric_ids.slice(0, 3).map((m) => <span key={m} className="inline-flex h-[18px] items-center rounded-[var(--radius-1)] border border-hairline bg-bg-muted px-1 font-mono text-[10px] text-fg-muted" title="Calculation (deterministic engine)">M:{m.slice(0, 6)}</span>)}
            </span>
          </li>
        ))}
      </ul>
    </li>
  );
}

function EvidenceCite({ dealId, id, onOpen }: { dealId: string; id: string; onOpen: (t: ViewerTarget) => void }) {
  const ev = useEvidence(dealId, id);
  const e: Evidence | undefined = ev.data;
  if (!e) return <span className="font-mono text-[10px] text-fg-muted">E:{id.slice(0, 6)}</span>;
  return <CitationChip docType={e.doc_type} documentName={e.document_name} locator={e.locator} kind={e.kind} onClick={() => onOpen({ documentId: e.document_id, documentName: e.document_name, evidenceId: e.id, locator: e.locator })} />;
}
