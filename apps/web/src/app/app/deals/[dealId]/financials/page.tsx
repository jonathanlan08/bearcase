"use client";

import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MessageSquareText } from "lucide-react";
import { api, type Adjustment, type Financials, type Metric, type StatementMapping } from "@/lib/api";
import { useFinancials, useStatementMapping, qk } from "@/components/app/hooks";
import { PageHeader, useDealKicker } from "@/components/app/shell";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui/primitives";
import { Table, td, th } from "@/components/ui/table";
import { StatusChip, StatusGlyph, STATUS_LABEL } from "@/components/domain/status";
import { CitationChip } from "@/components/domain/citation";
import { AddbackWaterfall, DscrGauge } from "@/components/domain/charts";
import { DocumentViewer, type ViewerTarget } from "@/components/domain/document-viewer";
import { useEvidence } from "@/components/app/hooks";
import { fmtMoney, fmtPct, fmtValue, titleCase, toNumber } from "@/lib/format";
import { useToast } from "@/components/ui/toast";
import { askTheDeal } from "@/lib/chat-bus";
import { Dialog } from "radix-ui";
import { Field, inputClass } from "@/components/ui/field";

const LINES: Array<[string, string, boolean]> = [["revenue", "Revenue", true], ["cost_of_goods_sold", "Cost of goods sold", false], ["gross_profit", "Gross profit", true], ["opex_owner_compensation", "Owner compensation", false], ["opex_salaries_wages", "Salaries and wages", false], ["opex_temporary_labor", "Temporary labor", false], ["opex_marketing", "Marketing and advertising", false], ["opex_legal_professional", "Legal and professional", false], ["opex_insurance", "Insurance", false], ["opex_rent_occupancy", "Rent and occupancy", false], ["opex_vehicle_fuel", "Vehicle and fuel", false], ["opex_software_it", "Software and IT", false], ["opex_other_ga", "Other G&A", false], ["operating_expenses", "Total operating expenses", true], ["ebitda", "EBITDA (stated)", true], ["depreciation", "Depreciation", false], ["amortization", "Amortization", false], ["operating_income", "Operating income", true], ["interest_expense", "Interest expense", false], ["income_before_tax", "Income before tax", false], ["income_tax_expense", "Income tax expense", false], ["net_income", "Net income", true]];
const CALC: Array<[string, string, string]> = [["revenue_growth", "Revenue growth", "pct"], ["gross_margin", "Gross margin", "pct"], ["operating_margin", "Operating margin", "pct"], ["ebitda_reported", "Reported EBITDA (reconciled)", "usd"]];
/** key, label, one-line meaning for a first-time buyer */
const DEAL: Array<[string, string, string]> = [
  ["cagr", "Revenue CAGR", "Average yearly revenue growth over the statement periods."],
  ["ebitda_adjusted_seller", "Seller adjusted EBITDA", "Reported EBITDA plus every adjustment the seller asks you to accept."],
  ["ebitda_adjusted_verified", "Checked adjusted EBITDA", "Reported EBITDA plus only the adjustments that passed the rules or a reviewer. Rule-based until a person records a decision."],
  ["enterprise_value", "Enterprise value", "The price for the whole business, debt included."],
  ["ev_to_ebitda_seller", "EV / seller EBITDA", "Price paid per dollar of the seller's EBITDA."],
  ["ev_to_ebitda_verified", "EV / checked EBITDA", "Price paid per dollar of checked EBITDA; higher means you pay more for the same earnings."],
  ["debt_to_ebitda_seller", "Debt / seller EBITDA", "Years of the seller's EBITDA needed to repay the acquisition debt."],
  ["debt_to_ebitda_verified", "Debt / checked EBITDA", "Years of checked EBITDA needed to repay the acquisition debt."],
  ["annual_debt_service", "Annual debt service", "Interest plus principal due to the lender each year."],
  ["cfads_base", "CFADS (base, year 1)", "Cash flow available for debt service: EBITDA after capex, cash taxes, and working capital."],
  ["dscr_base", "DSCR (base, year 1)", "Cash available ÷ debt payments due. Below 1.00x the business cannot cover its loan."],
  ["cash_on_cash_base", "Cash-on-cash (base, year 1)", "Year-1 cash to equity holders ÷ equity invested."],
  ["irr_base", "Equity IRR (base, 5-year)", "Annualized return on the equity over five years, including the assumed exit."],
  ["customer_concentration_top1", "Largest customer share", "Share of revenue from the single largest customer."],
  ["recurring_revenue_pct", "Contract-supported recurring revenue", "Revenue backed by signed customer contracts."],
];

export default function FinancialsPage() {
  const { dealId } = useParams<{ dealId: string }>();
  const kicker = useDealKicker();
  const fin = useFinancials(dealId);
  const [viewer, setViewer] = useState<ViewerTarget | null>(null);
  const [decide, setDecide] = useState<string | null>(null);
  const open = (eid: string) => setViewer({ documentId: "", evidenceId: eid });
  if (fin.isPending) return <div className="p-6"><Skeleton className="h-8 w-64" /><Skeleton className="mt-6 h-72" /></div>;
  if (fin.isError) return <div className="p-6"><ErrorState detail={String(fin.error)} onRetry={() => fin.refetch()} /></div>;
  const f = fin.data;
  if (f.periods.length === 0) return <div><PageHeader kicker={kicker} title="Financial Verification" /><div className="p-6"><EmptyState title="No financial statements mapped" body="Upload an income statement workbook (XLSX) and run analysis. Line items are mapped to canonical keys with cell-level provenance." /></div></div>;
  return (
    <div>
      <PageHeader kicker={kicker} title="Financial Verification">
        <p className="mt-2 max-w-3xl text-sm text-fg-muted">The seller’s adjusted EBITDA, rebuilt from the statements one adjustment at a time. Every number links to the cell or sentence it came from.</p>
      </PageHeader>
      <div className="flex flex-col gap-6 p-4 md:p-6">
        <CheckWhatWeRead dealId={dealId} onCite={open} />
        <WhatChanged f={f} dealId={dealId} onOpen={setViewer} onDecide={setDecide} />
        <Panel title="Add-back bridge: from the seller's number to the verified number" id="bridge">
          <AddbackWaterfall steps={f.waterfall} sellerTotal={latest(f, "ebitda_adjusted_seller")?.value} />
          <Table caption="Seller adjustments and the decision on each" className="mt-4">
            <thead><tr><th className={th}>Adjustment</th><th className={`${th} text-right`}>Amount</th><th className={th}>Decision</th><th className={th}>Why</th><th className={th}>Evidence</th><th className={th}><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {f.adjustments.map((a) => (
                <tr key={a.id}>
                  <td className={td}><p className="font-medium">{a.label}</p>{a.seller_rationale && <p className="mt-0.5 text-xs text-fg-muted">Seller: {a.seller_rationale}</p>}</td>
                  <td className={`${td} num text-right`}>{fmtMoney(a.amount)}</td>
                  <td className={td}><StatusChip status={a.decision} /><p className={`mt-1 text-[11px] font-medium ${a.decided_by_user_id ? "text-accent" : "text-fg-muted"}`}>{a.decided_by_user_id ? "Reviewer decision" : "Rule-based, provisional"}</p></td>
                  <td className={`${td} text-xs`}>{a.decision_rationale}<p className="mt-1 font-mono text-[10px] text-fg-muted">rule: {a.decision_rule}</p></td>
                  <td className={td}><span className="inline-flex flex-wrap gap-1">{a.evidence_ids.slice(0, 4).map((e) => <EvidenceCite key={e} dealId={dealId} id={e} onOpen={setViewer} />)}</span></td>
                  <td className={`${td} whitespace-nowrap`}><Button size="sm" variant="ghost" onClick={() => setDecide(a.id)}>Decide…</Button><Button size="sm" variant="ghost" icon={<MessageSquareText size={14} />} onClick={() => askTheDeal(askAboutAdjustment(a))}>Ask</Button></td>
                </tr>
              ))}
            </tbody>
          </Table>
          <p className="mt-2 text-xs text-fg-muted">Accepted adjustments are added back to reported EBITDA. Rejected, unsupported, and review-required adjustments are excluded until a reviewer decides otherwise.</p>
        </Panel>
        <details className="group rounded-[var(--radius-3)] border border-hairline bg-bg-raised">
          <summary className="cursor-pointer list-none px-5 py-3 text-sm font-medium [&::-webkit-details-marker]:hidden">Reference <span className="ml-2 font-normal text-fg-muted">deal metrics, cash-flow bridge, debt coverage, and the statement as mapped</span></summary>
        <div className="flex flex-col gap-6 border-t border-hairline p-4">
        <section aria-labelledby="deal-metrics">
          <h2 id="deal-metrics" className="text-sm font-medium">Deal metrics</h2>
          <p className="mt-1 text-xs text-fg-muted">Computed by the deterministic engine from the mapped statements and the deal terms. Open “Formula and inputs” on any card to see exactly how.</p>
          <div className="mt-3 grid gap-4 lg:grid-cols-3">
            {DEAL.map(([key, label, hint]) => { const m = latest(f, key); return m ? <MetricCard key={key} m={m} label={label} hint={hint} onCite={open} /> : null; })}
          </div>
        </section>
        <div className="grid gap-4 md:grid-cols-2">
          <Panel title="CFADS bridge (base case, year 1)"><p className="mb-2 text-xs text-fg-muted">CFADS is the cash actually available to pay the lender: EBITDA after maintenance capex, cash taxes, and working-capital investment.</p><CfadsBridge m={latest(f, "cfads_base")} /></Panel>
          <Panel title="Debt service coverage"><DscrGauge value={latest(f, "dscr_base")?.value ?? null} threshold={String(latest(f, "covenant_dscr_threshold")?.value ?? "")} /><p className="mt-2 text-xs text-fg-muted">DSCR = CFADS ÷ annual debt service. EBITDA is never labeled CFADS; the bridge on the left shows every deduction.</p></Panel>
        </div>
        <StatementTable f={f} onCite={open} />
        </div>
        </details>
      </div>
      <DocumentViewer dealId={dealId} target={viewer} onClose={() => setViewer(null)} />
      <DecisionDialog dealId={dealId} adjustmentId={decide} onClose={() => setDecide(null)} f={f} />
    </div>
  );
}

const LINE_LABEL = new Map(LINES.map(([k, l]) => [k, l]));
const SCALE_LABEL: Record<number, string> = { 1: "dollars (no scale stated)", 1000: "thousands (×1,000 applied)", 1000000: "millions (×1,000,000 applied)" };

/** "Check what we read": the interpretation behind every number on this page, before any of it is trusted. Detected
 *  periods, scale, and the row each line came from, with the cells to open; lines the rules were unsure about are
 *  flagged; rows nothing matched are listed so the reader can see what was not read. */
function CheckWhatWeRead({ dealId, onCite }: { dealId: string; onCite: (eid: string) => void }) {
  const q = useStatementMapping(dealId);
  const [showAll, setShowAll] = useState(false);
  if (q.isPending) return <Panel title="Check what we read" id="check-read"><Skeleton className="h-24" /></Panel>;
  if (q.isError || !q.data) return null;
  const m: StatementMapping = q.data;
  const cov = m.coverage;
  const flagged = m.statements.flatMap((s) => (s.lines ?? []).filter((l) => l.needs_review).map((l) => ({ ...l, sheet: s.sheet })));
  const unread = cov.documents_failed + cov.documents_pending + cov.statements_unmapped + cov.unmapped_rows + cov.ambiguous_lines + cov.metrics_requiring_review;
  const mappedStatement = m.statements.find((s) => s.mapped);
  const summaryLine = mappedStatement
    ? `${(mappedStatement.periods ?? []).length} years read, ${SCALE_LABEL[mappedStatement.scale ?? 1]?.split(" (")[0] ?? "scaled"}, ${(mappedStatement.lines ?? []).length} of ${LINES.length} lines, ${flagged.length === 0 ? "nothing flagged" : `${flagged.length} flagged`}${unread > 0 ? `, ${unread} item${unread === 1 ? "" : "s"} not checked` : ""}`
    : "no statement was read";
  return (
    <details id="check-read" className="group rounded-[var(--radius-3)] border border-hairline bg-bg-raised" open={flagged.length > 0 || unread > 0}>
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 px-5 py-3 text-sm [&::-webkit-details-marker]:hidden">
        <StatusGlyph status={flagged.length > 0 || cov.statements_unmapped > 0 ? "review_required" : "supported"} size={12} />
        <span className="font-medium">Check what we read</span>
        <span className="text-fg-muted">{summaryLine}</span>
        <span className="ml-auto text-xs text-accent">details</span>
      </summary>
    <div className="border-t border-hairline p-5">
      <p className="text-sm text-fg-muted">Every figure below was read from a spreadsheet by rules, not by a person. Before relying on it, confirm the years, the scale, and the rows the rules picked. Anything the rules were unsure about is flagged; anything they could not read is listed.</p>
      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="flex flex-col gap-4">
          {m.statements.map((s) => s.mapped ? (
            <dl key={s.document_id} className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm md:grid-cols-4">
              <div className="col-span-2 md:col-span-4"><dt className="text-xs text-fg-muted">Statement</dt><dd className="font-medium">{s.document_name} <span className="font-mono text-[11px] text-fg-muted">sheet {s.sheet}, header row {s.header_row}</span></dd></div>
              <div><dt className="text-xs text-fg-muted">Years found</dt><dd className="num">{(s.periods ?? []).map((p) => p.label).join(", ")}</dd></div>
              <div><dt className="text-xs text-fg-muted">Scale</dt><dd>{SCALE_LABEL[s.scale ?? 1] ?? `×${s.scale}`}</dd></div>
              <div><dt className="text-xs text-fg-muted">Currency</dt><dd>{s.currency}</dd></div>
              <div><dt className="text-xs text-fg-muted">Lines read</dt><dd className="num">{(s.lines ?? []).length} of {LINES.length}</dd></div>
              {(s.unmapped_rows ?? []).length > 0 && (
                <div className="col-span-2 md:col-span-4">
                  <dt className="text-xs text-fg-muted">Rows nothing matched ({s.unmapped_rows!.length})</dt>
                  <dd className="mt-1 flex flex-wrap gap-1">{(showAll ? s.unmapped_rows! : s.unmapped_rows!.slice(0, 8)).map((r) => <span key={r.row} className="rounded-[var(--radius-1)] border border-hairline px-1.5 py-0.5 font-mono text-[11px] text-fg-muted">row {r.row}: {r.label || "(blank)"}</span>)}{s.unmapped_rows!.length > 8 && <button type="button" className="text-xs text-accent hover:underline" onClick={() => setShowAll((v) => !v)}>{showAll ? "show fewer" : `and ${s.unmapped_rows!.length - 8} more`}</button>}</dd>
                </div>
              )}
            </dl>
          ) : (
            <p key={s.document_id} className="text-sm"><StatusGlyph status="review_required" size={12} className="mr-1 inline align-middle" /><span className="font-medium">{s.document_name}</span> was not read as a statement. {s.reason}</p>
          ))}
          {flagged.length > 0 ? (
            <div>
              <p className="text-sm font-medium"><StatusGlyph status="review_required" size={12} className="mr-1 inline align-middle" />{flagged.length} {flagged.length === 1 ? "line needs" : "lines need"} a person to confirm</p>
              <ul className="mt-1 space-y-1 text-sm text-fg-muted">
                {flagged.map((l) => <li key={l.key}>{LINE_LABEL.get(l.key) ?? l.key}{l.components ? `: summed from ${l.components.join(" + ")} because no total row exists` : ": matched by prefix only"}{Object.values(l.cells)[0]?.evidence_id && <button type="button" className="ml-2 text-xs text-accent hover:underline" onClick={() => onCite(Object.values(l.cells)[0]!.evidence_id!)}>open the rows</button>}</li>)}
              </ul>
            </div>
          ) : <p className="text-sm text-fg-muted"><StatusGlyph status="supported" size={12} className="mr-1 inline align-middle" />Every line matched a row exactly; nothing was summed or guessed.</p>}
        </div>
        <div className="rounded-[var(--radius-2)] border border-hairline bg-bg-raised p-4">
          <p className="text-xs text-fg-muted">What was not checked</p>
          <dl className="mt-2 grid grid-cols-2 gap-y-1.5 text-sm">
            <dt className="text-fg-muted">Documents read</dt><dd className="num text-right">{cov.documents_ready}</dd>
            <dt className="text-fg-muted">Documents failed or pending</dt><dd className="num text-right">{cov.documents_failed + cov.documents_pending}</dd>
            <dt className="text-fg-muted">Statements not mapped</dt><dd className="num text-right">{cov.statements_unmapped}</dd>
            <dt className="text-fg-muted">Rows nothing matched</dt><dd className="num text-right">{cov.unmapped_rows}</dd>
            <dt className="text-fg-muted">Lines summed from parts</dt><dd className="num text-right">{cov.ambiguous_lines}</dd>
            <dt className="text-fg-muted">Figures marked for review</dt><dd className="num text-right">{cov.metrics_requiring_review}</dd>
            <dt className="text-fg-muted">Claims still to review</dt><dd className="num text-right">{(cov.claims_by_status.review_required ?? 0) + (cov.claims_by_status.pending ?? 0)}</dd>
            <dt className="text-fg-muted">Claims with no evidence</dt><dd className="num text-right">{cov.claims_by_status.unsupported ?? 0}</dd>
          </dl>
          <p className="mt-3 text-xs text-fg-muted">{unread === 0 ? "Nothing is outstanding on the statements. The claims list and the report still need a person." : "Each count above is something a report reader would otherwise not know was left unread."}</p>
        </div>
      </div>
    </div>
    </details>
  );
}

function latest(f: Financials, key: string): Metric | undefined {
  const rows = f.metrics.filter((m) => m.key === key);
  return rows[rows.length - 1];
}

function askAboutAdjustment(a: Adjustment): string {
  return `Explain the seller's add-back "${a.label}" (${fmtMoney(a.amount)}, ${a.period_label}). The rule marked it ${STATUS_LABEL[a.decision] ?? a.decision}${a.decision_rationale ? ` because: ${a.decision_rationale}` : ""}. Should I accept it, and what should I ask the seller for?`;
}

/**
 * The headline first: what the seller said, what survived review, and the reasons for every excluded adjustment.
 * The subtraction is presentation only; both totals come from persisted engine metrics.
 */
function WhatChanged({ f, dealId, onOpen, onDecide }: { f: Financials; dealId: string; onOpen: (t: ViewerTarget) => void; onDecide: (id: string) => void }) {
  const seller = latest(f, "ebitda_adjusted_seller");
  const verified = latest(f, "ebitda_adjusted_verified");
  const reported = latest(f, "ebitda_reported");
  const s = toNumber(seller?.value), v = toNumber(verified?.value);
  const diff = s !== null && v !== null ? v - s : null;
  const pct = diff !== null && s ? (diff / s) * 100 : null;
  const excluded = f.adjustments.filter((a) => a.decision !== "accepted");
  const accepted = f.adjustments.length - excluded.length;
  const tone = diff === null ? "" : diff < 0 ? "text-red" : diff > 0 ? "text-accent" : "";
  return (
    <Panel title="What changed and why" id="what-changed">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div>
          <dl className="grid grid-cols-2 gap-3">
            <div><dt className="text-xs text-fg-muted">Seller’s adjusted EBITDA</dt><dd className="num mt-1 text-2xl text-graphite">{seller ? fmtValue(seller.value, seller.unit) : "—"}</dd></div>
            <div><dt className="text-xs text-fg-muted">Checked adjusted EBITDA</dt><dd className="num mt-1 text-2xl text-accent">{verified ? fmtValue(verified.value, verified.unit) : "—"}{verified?.requires_review && <StatusGlyph status="review_required" size={12} className="ml-2 inline align-middle" />}</dd></div>
            <div><dt className="text-xs text-fg-muted">Difference</dt><dd className={`num mt-1 text-lg ${tone}`}>{diff === null ? "—" : `${diff >= 0 ? "+" : "−"}${fmtMoney(Math.abs(diff))}${pct !== null ? ` (${fmtPct(pct, 1, true)})` : ""}`}</dd></div>
            <div><dt className="text-xs text-fg-muted">Reported EBITDA (statements)</dt><dd className="num mt-1 text-lg">{reported ? fmtValue(reported.value, reported.unit) : "—"}</dd></div>
          </dl>
          <p className="mt-3 text-sm text-fg-muted">{accepted} of {f.adjustments.length} seller adjustments were accepted{excluded.length ? `; ${excluded.length} ${excluded.length === 1 ? "was" : "were"} excluded for the reasons listed here` : ""}. Decisions without a reviewer’s note are rule-based and provisional; recording your own decision recomputes the checked number and marks it reviewed.</p>
        </div>
        <div>
          {excluded.length === 0 ? <p className="text-sm text-fg-muted">Every seller adjustment passed review, so the verified number equals the seller’s. The bridge below shows each step.</p> : (
            <ol className="flex flex-col gap-2" aria-label="Excluded adjustments and reasons">
              {excluded.map((a) => (
                <li key={a.id} className="rounded-[var(--radius-2)] border border-hairline p-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2"><StatusGlyph status={a.decision} /><span className="font-medium">{a.label}</span><span className="num text-fg-muted">{fmtMoney(a.amount)}</span><span className="ml-auto text-xs text-fg-muted">{STATUS_LABEL[a.decision] ?? titleCase(a.decision)}{a.decided_by_user_id ? " · reviewer decision" : " · rule-based, provisional"}</span></div>
                  {a.decision_rationale && <p className="mt-1 text-fg-muted">{a.decision_rationale}</p>}
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    {a.evidence_ids.slice(0, 3).map((e) => <EvidenceCite key={e} dealId={dealId} id={e} onOpen={onOpen} />)}
                    <button type="button" className="ml-auto text-xs text-accent hover:underline" onClick={() => onDecide(a.id)}>Decide…</button>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </Panel>
  );
}

function EvidenceCite({ dealId, id, onOpen }: { dealId: string; id: string; onOpen: (t: ViewerTarget) => void }) {
  const ev = useEvidence(dealId, id);
  if (!ev.data) return <span className="font-mono text-[10px] text-fg-muted">{id.slice(0, 6)}</span>;
  return <CitationChip docType={ev.data.doc_type} documentName={ev.data.document_name} locator={ev.data.locator} kind={ev.data.kind} onClick={() => onOpen({ documentId: ev.data.document_id, documentName: ev.data.document_name, evidenceId: ev.data.id, locator: ev.data.locator })} />;
}

function StatementTable({ f, onCite }: { f: Financials; onCite: (eid: string) => void }) {
  const byKey = useMemo(() => { const m = new Map<string, Metric>(); for (const x of f.metrics) if (x.period_label) m.set(`${x.key}|${x.period_label}`, x); return m; }, [f.metrics]);
  return (
    <Panel id="statement" title={<span>Income statement, as mapped from the workbook <span className="ml-2 font-mono text-[11px] text-fg-muted">{f.periods[0]?.source_sheet}</span></span>}>
      <p className="mb-3 text-xs text-fg-muted">The source data behind everything above. Click a number to open the spreadsheet cell it was read from; calculated rows show their formula on hover.</p>
      <Table caption="Income statement by period" stickyFirst>
        <thead><tr><th className={th}>Line item</th>{f.periods.map((p) => <th key={p.id} className={`${th} text-right`}>{p.label}</th>)}</tr></thead>
        <tbody>
          {LINES.map(([key, label, bold]) => (
            <tr key={key} className={bold ? "font-medium" : ""}>
              <td className={td}>{label}</td>
              {f.periods.map((p) => { const m = byKey.get(`${key}|${p.label}`); return <td key={p.id} className={`${td} num text-right`}>{m ? <button type="button" className="rounded-[2px] hover:bg-accent/10 hover:underline" title={`Cell ${String(m.input_snapshot.cell ?? "")}: click to open`} onClick={() => m.evidence_ids[0] && onCite(m.evidence_ids[0])}>{fmtMoney(m.value)}{m.requires_review && <StatusGlyph status="review_required" size={10} className="ml-1 inline" />}</button> : <span className="text-fg-muted">—</span>}</td>; })}
            </tr>
          ))}
          <tr><td className={`${td} pt-4 text-xs font-medium text-fg-muted`} colSpan={f.periods.length + 1}>Calculated by the engine</td></tr>
          {CALC.map(([key, label, unit]) => (
            <tr key={key}>
              <td className={td}>{label}</td>
              {f.periods.map((p) => { const m = byKey.get(`${key}|${p.label}`); return <td key={p.id} className={`${td} num text-right`}>{m ? <span title={m.formula ?? ""}>{fmtValue(m.value, unit)}{m.requires_review && <StatusGlyph status="review_required" size={10} className="ml-1 inline" />}</span> : <span className="text-fg-muted">—</span>}</td>; })}
            </tr>
          ))}
        </tbody>
      </Table>
    </Panel>
  );
}

function MetricCard({ m, label, hint, onCite }: { m: Metric; label: string; hint: string; onCite: (eid: string) => void }) {
  const tone = m.key.includes("verified") ? "text-accent" : m.key.includes("seller") ? "text-graphite" : "";
  return (
    <div className="rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-4">
      <div className="flex items-start justify-between gap-2"><p className="text-sm text-fg-muted">{label}</p><span className="text-[11px] text-fg-muted">{m.source}</span></div>
      <p className={`num mt-1 text-2xl ${tone}`}>{fmtValue(m.value, m.unit)}{m.requires_review && <StatusGlyph status="review_required" size={12} className="ml-2 inline align-middle" />}</p>
      <p className="mt-1 text-xs text-fg-muted">{hint}</p>
      {m.missing_inputs.length > 0 && <p className="mt-1 text-xs text-amber">Missing: {m.missing_inputs.join(", ")}</p>}
      <details className="mt-2 text-xs">
        <summary className="cursor-pointer text-fg-muted hover:text-fg">Formula and inputs</summary>
        <p className="mt-1 font-mono">{m.formula ?? "extracted value"}</p>
        <pre className="mt-1 max-h-40 overflow-auto rounded-[var(--radius-1)] bg-bg-muted p-2 font-mono text-[10.5px]">{JSON.stringify(m.input_snapshot.inputs ?? m.input_snapshot, null, 1)}</pre>
        {m.evidence_ids.length > 0 && <div className="mt-1 flex flex-wrap gap-1">{m.evidence_ids.slice(0, 5).map((e) => <button key={e} type="button" className="font-mono text-[10px] text-accent hover:underline" onClick={() => onCite(e)}>E:{e.slice(0, 6)}</button>)}</div>}
      </details>
    </div>
  );
}

function CfadsBridge({ m }: { m?: Metric }) {
  const b = m?.input_snapshot.bridge as Record<string, string> | undefined;
  if (!b) return <p className="text-sm text-fg-muted">Run the base scenario to build the bridge.</p>;
  const rows: Array<[string, string, boolean]> = [["Adjusted EBITDA (year 1)", b.adjusted_ebitda, true], ["Maintenance capex", b.maintenance_capex, false], ["Cash taxes", b.cash_taxes, false], ["Working-capital investment", b.working_capital_investment, false], ["CFADS", b.cfads, true]];
  return (
    <table className="w-full text-sm"><caption className="sr-only">CFADS bridge: adjusted EBITDA less deductions equals CFADS</caption><tbody>{rows.map(([l, v, bold]) => <tr key={l} className={bold ? "font-medium" : ""}><td className="py-1">{l}</td><td className="num py-1 text-right">{fmtMoney(v, { signed: !bold })}</td></tr>)}</tbody></table>
  );
}

function DecisionDialog({ dealId, adjustmentId, onClose, f }: { dealId: string; adjustmentId: string | null; onClose: () => void; f: Financials }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const a = f.adjustments.find((x) => x.id === adjustmentId);
  const [decision, setDecision] = useState("accepted");
  const [rationale, setRationale] = useState("");
  const m = useMutation({ mutationFn: () => api.post(`/api/deals/${dealId}/adjustments/${adjustmentId}/decision`, { decision, rationale }), onSuccess: () => { qc.invalidateQueries({ queryKey: qk.financials(dealId) }); qc.invalidateQueries({ queryKey: qk.summary(dealId) }); qc.invalidateQueries({ queryKey: qk.audit(dealId) }); toast({ title: "Decision recorded", description: "Checked adjusted EBITDA and multiples were recomputed.", tone: "success" }); onClose(); }, onError: (e) => toast({ title: "Could not record decision", description: String(e), tone: "error" }) });
  return (
    <Dialog.Root open={!!a} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink-950/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(520px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-5 shadow-[var(--shadow-2)] outline-none">
          <Dialog.Title className="text-lg font-medium">Decide on “{a?.label}”</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-fg-muted">The rule-based decision ({STATUS_LABEL[a?.decision ?? ""] ?? a?.decision.replace("_", " ")}) stays in the audit trail. Your decision recomputes checked adjusted EBITDA.</Dialog.Description>
          <form className="mt-4 flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); if (rationale.trim()) m.mutate(); }}>
            <Field label="Decision">{(p) => <select id={p.id} className={inputClass(false)} value={decision} onChange={(e) => setDecision(e.target.value)}>{["accepted", "rejected", "review_required", "unsupported"].map((d) => <option key={d} value={d}>{STATUS_LABEL[d] ?? titleCase(d)}</option>)}</select>}</Field>
            <Field label="Rationale" required help="Why you decided this way; it appears in the audit history and the report.">{(p) => <textarea id={p.id} aria-describedby={p.describedBy} className={inputClass(false, "h-24 py-2")} value={rationale} onChange={(e) => setRationale(e.target.value)} required />}</Field>
            <div className="flex justify-end gap-2"><Dialog.Close asChild><Button type="button" variant="secondary">Cancel</Button></Dialog.Close><Button type="submit" loading={m.isPending}>Record decision</Button></div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
