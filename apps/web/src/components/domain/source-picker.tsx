"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { CitationChip } from "@/components/domain/citation";

export interface SourceHit { id: string; document_id: string; document_name: string; doc_type: string; kind: string; locator: Record<string, unknown>; excerpt: string }

/** Attach evidence by searching its text: the same picker for notes, questions, and chat drafts. Selected sources
 *  render as citation chips; the excerpt shows what a chip will point at before it is attached. */
export function SourcePicker({ dealId, value, onChange }: { dealId: string; value: string[]; onChange: (ids: string[]) => void }) {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => { const t = window.setTimeout(() => setDebounced(q.trim()), 250); return () => window.clearTimeout(t); }, [q]);
  const hits = useQuery({ queryKey: ["evidence-search", dealId, debounced], queryFn: () => api.get<SourceHit[]>(`/api/deals/${dealId}/evidence-search?q=${encodeURIComponent(debounced)}`), enabled: debounced.length >= 2 });
  const [picked, setPicked] = useState<Record<string, SourceHit>>({});
  const add = (h: SourceHit) => { if (!value.includes(h.id)) { setPicked((p) => ({ ...p, [h.id]: h })); onChange([...value, h.id]); } };
  const remove = (id: string) => onChange(value.filter((x) => x !== id));
  return (
    <div className="rounded-[var(--radius-1)] border border-hairline p-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-fg-muted">Sources ({value.length})</span>
        {value.map((id) => { const h = picked[id]; return <span key={id} className="inline-flex items-center gap-1"><CitationChip docType={h?.doc_type ?? "unknown"} documentName={h?.document_name} locator={h?.locator ?? null} kind={h?.kind} label={h ? undefined : `source ${id.slice(0, 6)}`} /><button type="button" aria-label="Remove this source" className="text-xs text-fg-muted hover:text-red" onClick={() => remove(id)}>×</button></span>; })}
      </div>
      <input aria-label="Search the documents for a source" placeholder="Attach a source: search the documents (e.g. maintenance agreements, FY2024 revenue)" className="mt-2 h-8 w-full rounded-[var(--radius-1)] border border-hairline bg-bg px-2 text-sm" value={q} onChange={(e) => setQ(e.target.value)} />
      {debounced.length >= 2 && (
        <ul className="mt-1 max-h-44 overflow-y-auto text-sm" aria-label="Matching passages">
          {hits.isPending && <li className="px-1 py-1 text-xs text-fg-muted">Searching…</li>}
          {hits.data?.length === 0 && <li className="px-1 py-1 text-xs text-fg-muted">Nothing in the documents matches.</li>}
          {hits.data?.map((h) => (
            <li key={h.id}>
              <button type="button" onClick={() => add(h)} disabled={value.includes(h.id)} className="flex w-full flex-col items-start gap-0.5 rounded-[var(--radius-1)] px-1 py-1.5 text-left hover:bg-bg-muted disabled:opacity-50">
                <span className="text-[11px] text-fg-muted">{h.document_name}{h.locator?.page ? `, page ${String(h.locator.page)}` : h.locator?.sheet ? `, ${String(h.locator.sheet)} row ${String(h.locator.row ?? "")}` : ""}</span>
                <span className="line-clamp-2 text-[13px]">{h.excerpt}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
