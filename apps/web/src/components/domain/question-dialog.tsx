"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Dialog } from "radix-ui";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { SourcePicker } from "@/components/domain/source-picker";

/** A question for the seller is a request, not a verdict: this turns a claim or an explanation into one. */
export function draftSellerQuestion(claim: string | null | undefined, documents: string[] = []): string {
  const docs = documents.length ? documents.slice(0, 2).join(" and ") : "the financial statements";
  if (!claim) return "Could you walk us through how this figure was calculated, and share the documents it rests on?";
  const c = claim.replace(/\s+/g, " ").trim().replace(/[.]$/, "");
  return `Could you reconcile the statement that “${c}” with ${docs}, and share the calculation and the source documents used?`;
}

/** Write or edit a question for the seller, with why it is asked and the sources attached, then save it to Seller
 *  Questions. Nothing is sent anywhere; the reviewer edits before saving. */
export function QuestionDialog({ dealId, draft, why: initialWhy = "", evidenceIds = [], sourceMessageId, onClose }: { dealId: string; draft: string; why?: string; evidenceIds?: string[]; sourceMessageId?: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [question, setQuestion] = useState(draft);
  const [why, setWhy] = useState(initialWhy);
  const [severity, setSeverity] = useState("medium");
  const [evidence, setEvidence] = useState<string[]>(evidenceIds.slice(0, 20));
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const m = useMutation({
    mutationFn: () => api.post<{ id: string }>(`/api/deals/${dealId}/seller-questions/custom`, { question: question.trim(), why: why.trim() || undefined, severity, evidence_ids: evidence, source_message_id: sourceMessageId && /^[0-9a-f-]{36}$/.test(sourceMessageId) ? sourceMessageId : undefined }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["sellerQuestions", dealId] }); setDone(true); },
    onError: (e) => setError(String(e)),
  });
  return (
    <Dialog.Root open onOpenChange={(o) => { if (!o) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[60] bg-black/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-[60] w-[min(92vw,560px)] -translate-x-1/2 -translate-y-1/2 rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-5 shadow-lg" aria-describedby="q-desc">
          <Dialog.Title className="text-lg font-semibold">Question for the seller</Dialog.Title>
          <Dialog.Description id="q-desc" className="mt-1 text-sm text-fg-muted">Ask for something the seller can hand over: a reconciliation, a calculation, a document. It joins Seller Questions under “Written by the reviewer”. Nothing is sent.</Dialog.Description>
          {done ? (
            <div className="mt-4 text-sm"><p>Saved to Seller Questions.</p><div className="mt-3 flex justify-end"><Button type="button" onClick={onClose}>Done</Button></div></div>
          ) : (
            <form className="mt-4 flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); if (question.trim().length >= 5) m.mutate(); }}>
              <label className="text-xs text-fg-muted" htmlFor="q-text">The question</label>
              <textarea id="q-text" autoFocus className="min-h-[88px] rounded-[var(--radius-1)] border border-hairline bg-bg px-2 py-1.5 text-sm" value={question} onChange={(e) => setQuestion(e.target.value)} required />
              <label className="text-xs text-fg-muted" htmlFor="q-why">Why we ask (stays with the question, for you)</label>
              <input id="q-why" className="h-9 rounded-[var(--radius-1)] border border-hairline bg-bg px-2 text-sm" value={why} onChange={(e) => setWhy(e.target.value)} placeholder="The memo's growth figure does not match the statements." />
              <SourcePicker dealId={dealId} value={evidence} onChange={setEvidence} />
              <div className="flex items-center gap-2">
                <label className="text-xs text-fg-muted" htmlFor="q-sev">Priority</label>
                <select id="q-sev" className="h-8 rounded-[var(--radius-1)] border border-hairline bg-bg px-2 text-sm" value={severity} onChange={(e) => setSeverity(e.target.value)}>{["critical", "high", "medium", "low"].map((s) => <option key={s} value={s}>{s}</option>)}</select>
              </div>
              {error && <p role="alert" className="text-sm text-red">{error}</p>}
              <div className="flex justify-end gap-2"><Dialog.Close asChild><Button type="button" variant="secondary">Cancel</Button></Dialog.Close><Button type="submit" loading={m.isPending}>Save to Seller Questions</Button></div>
            </form>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
