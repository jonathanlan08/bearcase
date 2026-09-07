"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Dialog } from "radix-ui";
import { X } from "lucide-react";
import { useDocEvidence } from "@/components/app/hooks";
import { Skeleton } from "@/components/ui/primitives";
import { fmtCell, fmtLocator } from "@/lib/format";
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

const NUMERIC = /^-?\d+(\.\d+)?$/;
const MONEY_COLUMN = /revenue|amount|total|value|price|sales|cost|fee|balance/i;

function ViewerBody({ dealId, target }: { dealId: string; target: ViewerTarget }) {
  const q = useDocEvidence(dealId, target.documentId);
  const [filter, setFilter] = useState<string>("all");
  const targetRef = useRef<HTMLElement | null>(null);
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
  const highlight = useMemo(() => new Set([...(target.highlightIds ?? []), ...(target.evidenceId ? [target.evidenceId] : [])]), [target.highlightIds, target.evidenceId]);
  const setTarget = (isTarget: boolean) => (el: HTMLElement | null) => { if (isTarget) targetRef.current = el; };
  return (
    <>
      <div className="flex h-14 items-center gap-3 border-b border-hairline px-4">
        <div className="min-w-0 flex-1">
          <Dialog.Title className="truncate text-sm font-medium">{target.documentName ?? "Document"}</Dialog.Title>
          <p className="text-[11px] text-fg-muted">{target.locator ? `Cited location: ${fmtLocator(target.locator)}` : "Source document"}{highlight.size > 0 ? " · highlighted parts are cited" : ""}</p>
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
        {keys.filter((k) => filter === "all" || k === filter).map((k) => {
          const rows = groups.get(k) ?? [];
          const isSheet = rows.length > 0 && rows.every((e) => e.kind === "sheet_row" && Array.isArray(e.structured?.values));
          return (
            <section key={k} className="mb-6">
              <h3 className="mb-2 text-xs font-semibold text-fg-muted">{k}</h3>
              {isSheet ? <SheetTable name={k} rows={rows} highlight={highlight} targetId={target.evidenceId ?? null} setTarget={setTarget} /> : (
                <div className="flex flex-col gap-1.5">
                  {rows.map((e) => {
                    const hit = highlight.has(e.id);
                    const isTarget = e.id === target.evidenceId;
                    return (
                      <div key={e.id} ref={setTarget(isTarget)} className={`rounded-[var(--radius-2)] border px-3 py-2 text-sm ${hit ? "border-accent bg-accent/10" : "border-hairline"}`} aria-current={isTarget ? "true" : undefined}>
                        <div className="mb-1 flex flex-wrap items-center gap-2">
                          <span className="font-mono text-[11px] text-fg-muted">{fmtLocator(e.locator, e.kind)}</span>
                          {e.contains_instruction_text && <span className="rounded-[var(--radius-1)] border border-amber px-1.5 font-mono text-[10px] uppercase tracking-wider text-amber" title="This text tried to give instructions; it is shown but never followed">inert instruction text</span>}
                          {hit && <span className="text-[11px] font-medium text-accent">cited</span>}
                        </div>
                        {e.kind === "csv_row" && e.structured?.record ? (
                          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">{Object.entries(e.structured.record as Record<string, string>).map(([kk, vv]) => vv ? <div key={kk} className="contents"><dt className="font-mono text-fg-muted">{kk}</dt><dd className={MONEY_COLUMN.test(kk) ? "num" : ""}>{MONEY_COLUMN.test(kk) ? fmtCell(vv) : vv}</dd></div> : null)}</dl>
                        ) : (
                          <p className={e.contains_instruction_text ? "text-fg-muted" : ""}>{e.text}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          );
        })}
      </div>
    </>
  );
}

function sameValues(a: unknown, b: string[]): boolean {
  return Array.isArray(a) && a.length === b.length && a.every((v, i) => String(v ?? "") === String(b[i] ?? ""));
}

/**
 * One aligned table per sheet: the workbook's header row becomes the table header, every other row keeps its
 * spreadsheet row number in the first column, cited rows are highlighted and announced, and numbers carry separators.
 */
function SheetTable({ name, rows, highlight, targetId, setTarget }: { name: string; rows: Evidence[]; highlight: Set<string>; targetId: string | null; setTarget: (isTarget: boolean) => (el: HTMLElement | null) => void }) {
  const header = ((rows[0].structured?.header as string[] | undefined) ?? []).map((h) => String(h ?? ""));
  const width = Math.max(header.length, ...rows.map((r) => (r.structured?.values as string[]).length));
  // A title row with a single cell is not a header; only promote a row that labels at least two columns.
  const headerRow = header.filter((h) => h.trim()).length >= 2 ? rows.find((r) => sameValues(r.structured?.values, header)) : undefined;
  const body = rows.filter((r) => r !== headerRow);
  const cited = rows.filter((r) => highlight.has(r.id)).length;
  const values = (r: Evidence) => (r.structured?.values as Array<string | null>) ?? [];
  const renderRow = (r: Evidence, head: boolean) => {
    const hit = highlight.has(r.id);
    const isTarget = r.id === targetId;
    const vals = values(r);
    return (
      <tr key={r.id} ref={setTarget(isTarget)} aria-current={isTarget ? "true" : undefined} className={hit ? "bg-accent/10" : head ? "bg-bg-muted" : ""}>
        <th scope="row" className={`whitespace-nowrap border-b border-hairline px-2 py-1 text-left font-mono font-normal text-fg-muted ${hit ? "text-accent" : ""}`}>
          {String(r.locator.row ?? "")}{hit && <span className="sr-only"> (cited)</span>}{r.contains_instruction_text && <span className="sr-only"> (contains inert instruction text)</span>}
        </th>
        {Array.from({ length: width }, (_, i) => {
          const raw = vals[i] ?? "";
          const numeric = NUMERIC.test(String(raw).trim());
          const cls = `border-b border-hairline px-2 py-1 whitespace-nowrap ${numeric ? "num text-right" : "text-left"} ${head ? "font-medium text-fg-muted" : ""}`;
          return head ? <th key={i} scope="col" className={cls}>{fmtCell(raw)}</th> : <td key={i} className={cls}>{fmtCell(raw)}</td>;
        })}
      </tr>
    );
  };
  return (
    <div className="scroll-x rounded-[var(--radius-2)] border border-hairline">
      <table className="w-full border-collapse text-xs">
        <caption className="sr-only">Sheet {name}: {body.length} rows{cited > 0 ? `, ${cited} cited by the claim; cited rows are marked` : ""}. The first column is the spreadsheet row number.</caption>
        <thead>
          {headerRow ? renderRow(headerRow, true) : (
            <tr className="bg-bg-muted">
              <th scope="col" className="border-b border-hairline px-2 py-1 text-left font-mono text-[10px] font-medium text-fg-muted">Row</th>
              {Array.from({ length: width }, (_, i) => <th key={i} scope="col" className="border-b border-hairline px-2 py-1 text-left font-medium text-fg-muted">{header[i] ?? ""}</th>)}
            </tr>
          )}
        </thead>
        <tbody>{body.map((r) => renderRow(r, false))}</tbody>
      </table>
    </div>
  );
}
