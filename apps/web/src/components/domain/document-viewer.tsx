"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Dialog } from "radix-ui";
import { X } from "lucide-react";
import { useDocEvidence } from "@/components/app/hooks";
import { Skeleton } from "@/components/ui/primitives";
import { fmtLocator } from "@/lib/format";
import type { Evidence } from "@/lib/api";

export interface ViewerTarget { documentId: string; documentName?: string; evidenceId?: string | null; locator?: Record<string, unknown> | null; highlightIds?: string[] }

/** Page/sheet/row viewer with locator-driven scrolling and highlight. */
export function DocumentViewer({ dealId, target, onClose }: { dealId: string; target: ViewerTarget | null; onClose: () => void }) {
  return (
    <Dialog.Root open={!!target} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink-950/40" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[720px] flex-col bg-bg-raised shadow-[var(--shadow-2)] outline-none md:w-[60vw]" aria-describedby={undefined}>
          {target && <ViewerBody key={`${target.documentId}:${target.evidenceId ?? ""}`} dealId={dealId} target={target} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function ViewerBody({ dealId, target }: { dealId: string; target: ViewerTarget }) {
  const q = useDocEvidence(dealId, target.documentId);
  const [filter, setFilter] = useState<string>("all");
  const targetRef = useRef<HTMLDivElement | null>(null);
  const groups = useMemo(() => {
    const rows = (q.data ?? []).filter((e) => e.kind !== "csv_aggregate" || target.evidenceId === e.id);
    const map = new Map<string, Evidence[]>();
    for (const e of rows) {
      const key = e.locator.page ? `Page ${e.locator.page}` : e.locator.sheet ? String(e.locator.sheet) : e.locator.aggregate ? "Aggregates" : "Rows";
      map.set(key, [...(map.get(key) ?? []), e]);
    }
    return map;
  }, [q.data, target.evidenceId]);
  const keys = Array.from(groups.keys());
  useEffect(() => {
    const t = window.setTimeout(() => targetRef.current?.scrollIntoView({ block: "center", behavior: "auto" }), 60);
    return () => window.clearTimeout(t);
  }, [q.data]);
  const highlight = new Set([...(target.highlightIds ?? []), ...(target.evidenceId ? [target.evidenceId] : [])]);
  return (
    <>
          <div className="flex h-14 items-center gap-3 border-b border-hairline px-4">
            <div className="min-w-0 flex-1">
              <Dialog.Title className="truncate text-sm font-medium">{target.documentName ?? "Document"}</Dialog.Title>
              <p className="micro text-[10px]">{target.locator ? `Locator: ${fmtLocator(target.locator)}` : "Source document"}</p>
            </div>
            {keys.length > 1 && (
              <label className="flex items-center gap-2 text-xs text-fg-muted">Section
                <select className="h-8 rounded-[var(--radius-1)] border border-hairline bg-bg-raised px-2 text-sm text-fg" value={filter} onChange={(e) => setFilter(e.target.value)}>
                  <option value="all">All</option>
                  {keys.map((k) => <option key={k} value={k}>{k}</option>)}
                </select>
              </label>
            )}
            <Dialog.Close className="rounded-[var(--radius-1)] p-1.5 text-fg-muted hover:bg-bg-muted" aria-label="Close viewer"><X size={16} /></Dialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {q.isPending && <Skeleton className="h-40 w-full" />}
            {q.isError && <p className="text-sm text-red">Could not load the document.</p>}
            {keys.filter((k) => filter === "all" || k === filter).map((k) => (
              <section key={k} className="mb-6">
                <h3 className="micro mb-2">{k}</h3>
                <div className="flex flex-col gap-1.5">
                  {(groups.get(k) ?? []).map((e) => {
                    const hit = highlight.has(e.id);
                    const isTarget = e.id === target.evidenceId;
                    return (
                      <div key={e.id} ref={isTarget ? targetRef : undefined} className={`rounded-[var(--radius-2)] border px-3 py-2 text-sm ${hit ? "border-accent bg-accent/10" : "border-hairline"}`} aria-current={isTarget ? "true" : undefined}>
                        <div className="mb-1 flex flex-wrap items-center gap-2">
                          <span className="font-mono text-[11px] text-fg-muted">{fmtLocator(e.locator, e.kind)}</span>
                          {e.contains_instruction_text && <span className="rounded-[var(--radius-1)] border border-amber px-1.5 font-mono text-[10px] uppercase tracking-wider text-amber">inert instruction text</span>}
                          {hit && <span className="micro text-[10px] text-accent">cited</span>}
                        </div>
                        {e.kind === "sheet_row" && e.structured?.values ? (
                          <div className="scroll-x"><table className="text-xs"><tbody><tr>{(e.structured.values as string[]).map((v, i) => <td key={i} className={`border border-hairline px-2 py-1 ${i > 0 ? "num text-right" : ""}`}>{v}</td>)}</tr></tbody></table></div>
                        ) : e.kind === "csv_row" && e.structured?.record ? (
                          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">{Object.entries(e.structured.record as Record<string, string>).map(([kk, vv]) => vv ? <div key={kk} className="contents"><dt className="font-mono text-fg-muted">{kk}</dt><dd className={/revenue/.test(kk) ? "num" : ""}>{vv}</dd></div> : null)}</dl>
                        ) : (
                          <p className={e.contains_instruction_text ? "text-fg-muted" : ""}>{e.text}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
    </>
  );
}
