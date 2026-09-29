import type { ReactNode } from "react";
import { Table, td, th } from "@/components/ui/table";
import { StatusChip } from "@/components/domain/status";

/**
 * The report body, presentational only: section headings, cited statements, and tables. The in-app report page and
 * the public shared page both render through it and differ only in what a citation chip does (`cite`), so a shared
 * report reads exactly like the one in the workspace.
 */

export const OUTCOME_LABEL: Record<string, string> = {
  additional_diligence_required: "Additional diligence required",
  material_concerns_identified: "Material concerns identified",
  assumptions_require_revision: "Assumptions require revision",
  ready_for_ic_review: "Ready for investment-committee review",
};

/** The glyph an outcome carries next to its label (never colour alone). */
export function outcomeStatus(outcome: string): string {
  return outcome === "ready_for_ic_review" ? "supported" : outcome === "material_concerns_identified" ? "contradicted" : "review_required";
}

/** Sections shown open: the review itself. Everything else is the ledger behind it and opens on demand. */
export const LEAD_SECTIONS = new Set(["executive_summary", "contradictions", "open_questions", "management_questions", "reviewer_decisions"]);

export interface ViewStatement { text: string; evidence_ids: string[]; metric_ids: string[] }
export interface ViewRow { label?: string; cells: string[]; evidence_ids: string[]; metric_ids?: string[]; status?: string | null; decision?: string | null; severity?: string | null }
export interface ViewSection { key: string; title: string; statements: ViewStatement[]; table: { columns?: string[]; rows?: ViewRow[] }; derived_from: string[] }

/** Renders one citation chip. `kind` is E (a passage in a document) or M (a calculation by the engine). */
export type CiteRenderer = (kind: "E" | "M", id: string) => ReactNode;

function hasStatusCell(row: ViewRow): boolean {
  return row.status != null || row.decision != null || row.severity != null;
}

export function ReportSectionView({ s, cite }: { s: ViewSection; cite: CiteRenderer }) {
  return (
    <section id={`sec-${s.key}`} className="mb-10 scroll-mt-4">
      <h2 className="text-2xl">{s.title}</h2>
      {s.derived_from?.length > 0 && <p className="mt-1 text-xs text-fg-muted">Analysis derived from {s.derived_from.join(", ")}</p>}
      {s.statements.length > 0 && (
        <ul className="mt-3 flex flex-col gap-2 text-[15px] leading-relaxed">
          {s.statements.map((st, i) => (
            <li key={i}>{st.text} <span className="ml-1 inline-flex flex-wrap gap-1 align-middle">{st.evidence_ids.map((e) => <span key={e}>{cite("E", e)}</span>)}{st.metric_ids.map((m) => <span key={m}>{cite("M", m)}</span>)}</span></li>
          ))}
        </ul>
      )}
      {s.table?.rows && s.table.rows.length > 0 && (
        <Table caption={s.title} className="mt-3">
          <thead><tr>{(s.table.columns ?? []).map((c) => <th key={c} className={th}>{c}</th>)}<th className={th}>Sources</th></tr></thead>
          <tbody>
            {s.table.rows.map((row, i) => (
              <tr key={i}>
                {row.cells.map((c, j) => <td key={j} className={`${td} ${j > 0 && /^[$\-\d]/.test(String(c)) ? "num text-right" : ""}`}>{hasStatusCell(row) && j === 1 ? <StatusChip status={String(row.status ?? row.decision ?? c)} size="sm" /> : String(c)}</td>)}
                <td className={td}><span className="inline-flex flex-wrap gap-1">{row.evidence_ids.slice(0, 3).map((e) => <span key={e}>{cite("E", e)}</span>)}{(row.metric_ids ?? []).slice(0, 2).map((m) => <span key={m}>{cite("M", m)}</span>)}</span></td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </section>
  );
}

/** The whole body: the first sections open, the ledger behind them folded, with a line saying how to read it. */
export function ReportBody({ sections, cite }: { sections: ViewSection[]; cite: CiteRenderer }) {
  return (
    <>
      {sections.map((s, i) => LEAD_SECTIONS.has(s.key) || i < 2
        ? <ReportSectionView key={s.key} s={s} cite={cite} />
        : (
          <details key={s.key} id={`sec-${s.key}`} className="mb-4 scroll-mt-4 rounded-[var(--radius-2)] border border-hairline">
            <summary className="cursor-pointer list-none px-4 py-3 text-base font-medium [&::-webkit-details-marker]:hidden">{s.title}<span className="ml-2 text-xs font-normal text-fg-muted">{s.statements.length} statement{s.statements.length === 1 ? "" : "s"}{s.table?.rows?.length ? `, ${s.table.rows.length} rows` : ""}</span></summary>
            <div className="border-t border-hairline px-4 pb-2"><ReportSectionView s={{ ...s, key: `${s.key}-body` }} cite={cite} /></div>
          </details>
        ))}
      <p className="mt-2 text-xs text-fg-muted">The first sections are the review. The rest is the ledger behind it; open a section to read it, or use the jump list.</p>
    </>
  );
}

/** Section list for the side nav and the mobile jump select. */
export function ReportToc({ sections }: { sections: Array<{ key: string; title: string }> }) {
  return (
    <nav aria-label="Report sections" className="lg:sticky lg:top-4 lg:self-start">
      <label className="text-xs text-fg-muted lg:hidden" htmlFor="report-jump">Jump to section</label>
      <select id="report-jump" className="mt-1 h-9 w-full rounded-[var(--radius-1)] border border-hairline bg-bg-raised px-2 text-sm lg:hidden" onChange={(e) => document.getElementById(`sec-${e.target.value}`)?.scrollIntoView({ block: "start" })}>{sections.map((t) => <option key={t.key} value={t.key}>{t.title}</option>)}</select>
      <ol className="hidden flex-col gap-1 text-sm lg:flex">{sections.map((t, i) => <li key={t.key}><a href={`#sec-${t.key}`} className="flex gap-2 rounded-[var(--radius-1)] px-2 py-1 text-fg-muted hover:bg-bg-muted hover:text-fg"><span className="num w-5 shrink-0 text-xs">{String(i + 1).padStart(2, "0")}</span><span className="min-w-0">{t.title}</span></a></li>)}</ol>
    </nav>
  );
}
