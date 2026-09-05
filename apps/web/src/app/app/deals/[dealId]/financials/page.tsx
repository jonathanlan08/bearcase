"use client";

import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Financials, type Metric } from "@/lib/api";
import { useFinancials, qk } from "@/components/app/hooks";
import { PageHeader, useDealKicker } from "@/components/app/shell";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui/primitives";
import { Table, td, th } from "@/components/ui/table";
import { StatusChip, StatusGlyph } from "@/components/domain/status";
import { CitationChip } from "@/components/domain/citation";
import { AddbackWaterfall, DscrGauge } from "@/components/domain/charts";
import { DocumentViewer, type ViewerTarget } from "@/components/domain/document-viewer";
import { useEvidence } from "@/components/app/hooks";
import { fmtMoney, fmtValue, titleCase } from "@/lib/format";
import { useToast } from "@/components/ui/toast";
import { Dialog } from "radix-ui";
import { Field, inputClass } from "@/components/ui/field";

const LINES: Array<[string, string, boolean]> = [["revenue", "Revenue", true], ["cost_of_goods_sold", "Cost of goods sold", false], ["gross_profit", "Gross profit", true], ["opex_owner_compensation", "Owner compensation", false], ["opex_salaries_wages", "Salaries and wages", false], ["opex_temporary_labor", "Temporary labor", false], ["opex_marketing", "Marketing and advertising", false], ["opex_legal_professional", "Legal and professional", false], ["opex_insurance", "Insurance", false], ["opex_rent_occupancy", "Rent and occupancy", false], ["opex_vehicle_fuel", "Vehicle and fuel", false], ["opex_software_it", "Software and IT", false], ["opex_other_ga", "Other G&A", false], ["operating_expenses", "Total operating expenses", true], ["ebitda", "EBITDA (stated)", true], ["depreciation", "Depreciation", false], ["amortization", "Amortization", false], ["operating_income", "Operating income", true], ["interest_expense", "Interest expense", false], ["income_before_tax", "Income before tax", false], ["income_tax_expense", "Income tax expense", false], ["net_income", "Net income", true]];
const CALC: Array<[string, string, string]> = [["revenue_growth", "Revenue growth", "pct"], ["gross_margin", "Gross margin", "pct"], ["operating_margin", "Operating margin", "pct"], ["ebitda_reported", "Reported EBITDA (reconciled)", "usd"]];
const DEAL: Array<[string, string]> = [["cagr", "Revenue CAGR"], ["ebitda_adjusted_seller", "Seller adjusted EBITDA"], ["ebitda_adjusted_verified", "Verified adjusted EBITDA"], ["enterprise_value", "Enterprise value"], ["ev_to_ebitda_seller", "EV / seller EBITDA"], ["ev_to_ebitda_verified", "EV / verified EBITDA"], ["debt_to_ebitda_seller", "Debt / seller EBITDA"], ["debt_to_ebitda_verified", "Debt / verified EBITDA"], ["annual_debt_service", "Annual debt service"], ["cfads_base", "CFADS (base, year 1)"], ["dscr_base", "DSCR (base, year 1)"], ["cash_on_cash_base", "Cash-on-cash (base, year 1)"], ["irr_base", "Equity IRR (base, 5-year)"], ["customer_concentration_top1", "Largest customer share"], ["recurring_revenue_pct", "Contract-supported recurring revenue"]];

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
      <PageHeader kicker={kicker} title="Financial Verification" />
      <div className="flex flex-col gap-6 p-4 md:p-6">
        <StatementTable f={f} onCite={open} />
        <div className="grid gap-4 lg:grid-cols-3">
          {DEAL.map(([key, label]) => { const m = latest(f, key); return m ? <MetricCard key={key} m={m} label={label} onCite={open} /> : null; })}
        </div>
        <Panel title="Seller add-backs and verified adjusted EBITDA">
          <AddbackWaterfall steps={f.waterfall} sellerTotal={latest(f, "ebitda_adjusted_seller")?.value} />
          <Table caption="Seller adjustments" className="mt-4">
            <thead><tr><th className={th}>Adjustment</th><th className={`${th} text-right`}>Amount</th><th className={th}>Decision</th><th className={th}>Rationale</th><th className={th}>Evidence</th><th className={th}><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {f.adjustments.map((a) => (
                <tr key={a.id}>
                  <td className={td}><p className="font-medium">{a.label}</p>{a.seller_rationale && <p className="mt-0.5 text-xs text-fg-muted">Seller: {a.seller_rationale}</p>}</td>
                  <td className={`${td} num text-right`}>{fmtMoney(a.amount)}</td>
                  <td className={td}><StatusChip status={a.decision} />{a.decided_by_user_id && <p className="mt-1 text-[11px] font-medium text-accent">reviewer decision</p>}</td>
                  <td className={`${td} text-xs`}>{a.decision_rationale}<p className="mt-1 font-mono text-[10px] text-fg-muted">rule: {a.decision_rule}</p></td>
                  <td className={td}><span className="inline-flex flex-wrap gap-1">{a.evidence_ids.slice(0, 4).map((e) => <EvidenceCite key={e} dealId={dealId} id={e} onOpen={setViewer} />)}</span></td>
                  <td className={td}><Button size="sm" variant="ghost" onClick={() => setDecide(a.id)}>Decide…</Button></td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>
        <div className="grid gap-4 md:grid-cols-2">
          <Panel title="CFADS bridge (base case, year 1)"><CfadsBridge m={latest(f, "cfads_base")} /></Panel>
          <Panel title="Debt service coverage"><DscrGauge value={latest(f, "dscr_base")?.value ?? null} threshold={String(latest(f, "covenant_dscr_threshold")?.value ?? "")} /><p className="mt-2 text-xs text-fg-muted">DSCR = CFADS ÷ annual debt service. EBITDA is never labeled CFADS; the bridge above shows every deduction.</p></Panel>
        </div>
      </div>
      <DocumentViewer dealId={dealId} target={viewer} onClose={() => setViewer(null)} />
      <DecisionDialog dealId={dealId} adjustmentId={decide} onClose={() => setDecide(null)} f={f} />
    </div>
  );
}

function latest(f: Financials, key: string): Metric | undefined {
  const rows = f.metrics.filter((m) => m.key === key);
  return rows[rows.length - 1];
}

function EvidenceCite({ dealId, id, onOpen }: { dealId: string; id: string; onOpen: (t: ViewerTarget) => void }) {
  const ev = useEvidence(dealId, id);
  if (!ev.data) return <span className="font-mono text-[10px] text-fg-muted">{id.slice(0, 6)}</span>;
  return <CitationChip docType={ev.data.doc_type} documentName={ev.data.document_name} locator={ev.data.locator} kind={ev.data.kind} onClick={() => onOpen({ documentId: ev.data.document_id, documentName: ev.data.document_name, evidenceId: ev.data.id, locator: ev.data.locator })} />;
}

function StatementTable({ f, onCite }: { f: Financials; onCite: (eid: string) => void }) {
  const byKey = useMemo(() => { const m = new Map<string, Metric>(); for (const x of f.metrics) if (x.period_label) m.set(`${x.key}|${x.period_label}`, x); return m; }, [f.metrics]);
  return (
    <Panel title={<span>Income statement <span className="ml-2 font-mono text-[11px] text-fg-muted">{f.periods[0]?.source_sheet}</span></span>}>
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
      <p className="mt-2 text-xs text-fg-muted">Extracted values link to the exact spreadsheet cell. Calculated rows show their formula on hover.</p>
    </Panel>
  );
}

function MetricCard({ m, label, onCite }: { m: Metric; label: string; onCite: (eid: string) => void }) {
  const tone = m.key.includes("verified") ? "text-accent" : m.key.includes("seller") ? "text-graphite" : "";
  return (
    <div className="rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-4">
      <div className="flex items-start justify-between gap-2"><p className="text-sm text-fg-muted">{label}</p><span className="text-[11px] text-fg-muted">{m.source}</span></div>
      <p className={`num mt-1 text-2xl ${tone}`}>{fmtValue(m.value, m.unit)}{m.requires_review && <StatusGlyph status="review_required" size={12} className="ml-2 inline align-middle" />}</p>
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
    <table className="w-full text-sm"><tbody>{rows.map(([l, v, bold]) => <tr key={l} className={bold ? "font-medium" : ""}><td className="py-1">{l}</td><td className="num py-1 text-right">{fmtMoney(v, { signed: !bold })}</td></tr>)}</tbody></table>
  );
}

function DecisionDialog({ dealId, adjustmentId, onClose, f }: { dealId: string; adjustmentId: string | null; onClose: () => void; f: Financials }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const a = f.adjustments.find((x) => x.id === adjustmentId);
  const [decision, setDecision] = useState("accepted");
  const [rationale, setRationale] = useState("");
  const m = useMutation({ mutationFn: () => api.post(`/api/deals/${dealId}/adjustments/${adjustmentId}/decision`, { decision, rationale }), onSuccess: () => { qc.invalidateQueries({ queryKey: qk.financials(dealId) }); qc.invalidateQueries({ queryKey: qk.summary(dealId) }); qc.invalidateQueries({ queryKey: qk.audit(dealId) }); toast({ title: "Decision recorded", description: "Verified adjusted EBITDA and multiples were recomputed.", tone: "success" }); onClose(); }, onError: (e) => toast({ title: "Could not record decision", description: String(e), tone: "error" }) });
  return (
    <Dialog.Root open={!!a} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink-950/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(520px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-5 shadow-[var(--shadow-2)] outline-none">
          <Dialog.Title className="text-lg font-medium">Decide on “{a?.label}”</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-fg-muted">The rule-based decision ({a?.decision.replace("_", " ")}) stays in the audit trail. Your decision recomputes verified adjusted EBITDA.</Dialog.Description>
          <form className="mt-4 flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); if (rationale.trim()) m.mutate(); }}>
            <Field label="Decision">{(p) => <select id={p.id} className={inputClass(false)} value={decision} onChange={(e) => setDecision(e.target.value)}>{["accepted", "rejected", "review_required", "unsupported"].map((d) => <option key={d} value={d}>{titleCase(d)}</option>)}</select>}</Field>
            <Field label="Rationale" required>{(p) => <textarea id={p.id} className={inputClass(false, "h-24 py-2")} value={rationale} onChange={(e) => setRationale(e.target.value)} required />}</Field>
            <div className="flex justify-end gap-2"><Dialog.Close asChild><Button type="button" variant="secondary">Cancel</Button></Dialog.Close><Button type="submit" loading={m.isPending}>Record decision</Button></div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
