"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNotes, qk } from "@/components/app/hooks";
import { PageHeader, useDealKicker } from "@/components/app/shell";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { CitationChip } from "@/components/domain/citation";
import { DocumentViewer, type ViewerTarget } from "@/components/domain/document-viewer";
import { NoteDialog, NOTE_KIND_LABEL } from "@/components/domain/note-dialog";
import { notes as notesApi, type NoteKind, type ReviewNote } from "@/lib/api";
import { fmtDate } from "@/lib/format";

const ORDER: NoteKind[] = ["conclusion", "assumption", "open_question"];
const HINT: Record<NoteKind, string> = {
  conclusion: "What you decided, in your words, with the sources it rests on. These open the report and the one-page summary.",
  assumption: "What you are taking as given. Each one is a thing the seller or the lender could later disagree with.",
  open_question: "What still needs an answer before you rely on the review.",
};

/** The reviewer's notebook: the only page whose every sentence a person wrote. */
export default function NotebookPage() {
  const { dealId } = useParams<{ dealId: string }>();
  const kicker = useDealKicker();
  const q = useNotes(dealId);
  const qc = useQueryClient();
  const { toast } = useToast();
  const [adding, setAdding] = useState<NoteKind | null>(null);
  const [viewer, setViewer] = useState<ViewerTarget | null>(null);
  const base = `/app/deals/${dealId}`;
  const remove = useMutation({ mutationFn: (id: string) => notesApi.remove(dealId, id), onSuccess: () => { qc.invalidateQueries({ queryKey: qk.notes(dealId) }); toast({ title: "Note removed", tone: "success" }); } });
  const total = q.data?.notes.length ?? 0;
  return (
    <div>
      <PageHeader kicker={kicker} title="Notebook" actions={<Button size="sm" onClick={() => setAdding("conclusion")}>Add a note</Button>}>
        <p className="mt-2 max-w-3xl text-sm text-fg-muted">Your conclusions, assumptions, and open questions, each with the evidence it rests on. Nothing here is generated. The notebook is the first section of the report, so a note that states a figure has to cite a source.</p>
      </PageHeader>
      <div className="flex flex-col gap-4 p-4 md:p-6">
        {q.isPending && <Skeleton className="h-40" />}
        {q.isError && <ErrorState detail={String(q.error)} onRetry={() => q.refetch()} />}
        {q.data && total === 0 && <EmptyState title="Nothing written yet" body="Open a claim and choose “Add to notebook”, or save a chat answer as a note. The first conclusion you write becomes the first line of the report." action={<Button size="sm" onClick={() => setAdding("conclusion")}>Write the first note</Button>} />}
        {q.data && total > 0 && ORDER.map((kind) => {
          const rows = q.data.notes.filter((n) => n.kind === kind);
          return (
            <section key={kind} aria-labelledby={`nb-${kind}`} className="rounded-[var(--radius-3)] border border-hairline bg-bg-raised">
              <div className="flex flex-wrap items-baseline gap-2 px-5 py-3">
                <h2 id={`nb-${kind}`} className="text-sm font-medium">{NOTE_KIND_LABEL[kind]}s</h2>
                <span className="num text-xs text-fg-muted">{rows.length}</span>
                <button type="button" className="ml-auto text-xs text-accent hover:underline" onClick={() => setAdding(kind)}>Add</button>
              </div>
              <p className="px-5 pb-3 text-xs text-fg-muted">{HINT[kind]}</p>
              {rows.length === 0 ? <p className="border-t border-hairline px-5 py-3 text-sm text-fg-muted">None yet.</p> : (
                <ol className="divide-y divide-hairline border-t border-hairline">
                  {rows.map((n) => <NoteRow key={n.id} n={n} dealId={dealId} base={base} onOpen={(eid) => setViewer({ documentId: "", evidenceId: eid })} onRemove={() => remove.mutate(n.id)} />)}
                </ol>
              )}
            </section>
          );
        })}
      </div>
      {adding && <NoteDialog dealId={dealId} kind={adding} onClose={() => setAdding(null)} />}
      <DocumentViewer dealId={dealId} target={viewer} onClose={() => setViewer(null)} />
    </div>
  );
}

function NoteRow({ n, dealId, base, onOpen, onRemove }: { n: ReviewNote; dealId: string; base: string; onOpen: (eid: string) => void; onRemove: () => void }) {
  void dealId;
  return (
    <li className="px-5 py-3 text-sm">
      <p className="text-[15px] leading-relaxed">{n.text}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-fg-muted">
        <span>{n.by ?? "reviewer"}, {fmtDate(n.created_at)}</span>
        {n.evidence_ids.map((e) => <CitationChip key={e} docType="unknown" locator={null} label={`source ${e.slice(0, 6)}`} onClick={() => onOpen(e)} />)}
        {n.metric_ids.length > 0 && <span>{n.metric_ids.length} calculation{n.metric_ids.length === 1 ? "" : "s"}</span>}
        {n.claim_id && <Link href={`${base}/claims?claim=${n.claim_id}`} className="text-accent hover:underline">Open the claim</Link>}
        <button type="button" className="ml-auto text-red hover:underline" onClick={onRemove}>Remove</button>
      </div>
    </li>
  );
}
