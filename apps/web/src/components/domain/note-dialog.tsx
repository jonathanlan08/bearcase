"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Dialog } from "radix-ui";
import { notes, type NoteKind } from "@/lib/api";
import { qk } from "@/components/app/hooks";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { SourcePicker } from "@/components/domain/source-picker";

export const NOTE_KIND_LABEL: Record<NoteKind, string> = { conclusion: "Conclusion", assumption: "Assumption", open_question: "Open question" };

/** Write a note into the reviewer's notebook with the sources it rests on. A note that states a figure must carry a
 *  source; the API refuses one that does not, and the dialog says so. */
export function NoteDialog({ dealId, draft = "", kind: initialKind = "conclusion", evidenceIds = [], metricIds = [], claimId = null, findingId = null, onClose }: { dealId: string; draft?: string; kind?: NoteKind; evidenceIds?: string[]; metricIds?: string[]; claimId?: string | null; findingId?: string | null; onClose: () => void }) {
  const [text, setText] = useState(draft);
  const [kind, setKind] = useState<NoteKind>(initialKind);
  const [evidence, setEvidence] = useState<string[]>(evidenceIds.slice(0, 20));
  const [include, setInclude] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const qc = useQueryClient();
  const { toast } = useToast();
  const sources = evidence.length + metricIds.length;
  const m = useMutation({
    mutationFn: () => notes.add(dealId, { kind, text: text.trim(), evidence_ids: evidence, metric_ids: metricIds, claim_id: claimId, finding_id: findingId, include_in_report: include }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: qk.notes(dealId) }); qc.invalidateQueries({ queryKey: qk.audit(dealId) }); toast({ title: "Added to the notebook", tone: "success" }); onClose(); },
    onError: (e) => setError(String(e)),
  });
  return (
    <Dialog.Root open onOpenChange={(o) => { if (!o) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[60] bg-black/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-[60] w-[min(92vw,520px)] -translate-x-1/2 -translate-y-1/2 rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-5 shadow-lg" aria-describedby="note-desc">
          <Dialog.Title className="text-lg font-semibold">Add to the notebook</Dialog.Title>
          <Dialog.Description id="note-desc" className="mt-1 text-sm text-fg-muted">Your words, first in the report. {sources > 0 ? `${sources} source${sources === 1 ? "" : "s"} attached.` : "Attach a source below if the note states a figure."}</Dialog.Description>
          <form className="mt-4 flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); if (text.trim().length >= 5) m.mutate(); }}>
            <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Kind of note">
              {(Object.keys(NOTE_KIND_LABEL) as NoteKind[]).map((k) => <button key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => setKind(k)} className={`rounded-full border px-3 py-1 text-xs ${kind === k ? "border-fg bg-fg text-bg" : "border-hairline text-fg-muted hover:text-fg"}`}>{NOTE_KIND_LABEL[k]}</button>)}
            </div>
            <label className="text-xs text-fg-muted" htmlFor="note-text">Note</label>
            <textarea id="note-text" autoFocus className="min-h-[110px] rounded-[var(--radius-1)] border border-hairline bg-bg px-2 py-1.5 text-sm" value={text} onChange={(e) => setText(e.target.value)} placeholder={kind === "open_question" ? "What still needs an answer, and from whom?" : kind === "assumption" ? "What you are taking as given, and why." : "What you concluded, and on what basis."} required />
            <SourcePicker dealId={dealId} value={evidence} onChange={setEvidence} />
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-[var(--accent)]" checked={include} onChange={(e) => setInclude(e.target.checked)} />Include in the report and the one-page summary <span className="text-xs text-fg-muted">(untick to keep it a private draft)</span></label>
            {error && <p role="alert" className="text-sm text-red">{error}</p>}
            <div className="flex justify-end gap-2"><Dialog.Close asChild><Button type="button" variant="secondary">Cancel</Button></Dialog.Close><Button type="submit" loading={m.isPending}>Save note</Button></div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
