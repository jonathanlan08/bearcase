"use client";

import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, Plus } from "lucide-react";
import { api, type Scenario, type Sensitivity, type AssumptionSpec } from "@/lib/api";
import { useFacts, useScenarios, qk } from "@/components/app/hooks";
import { PageHeader, useDealKicker } from "@/components/app/shell";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui/primitives";
import { Table, td, th } from "@/components/ui/table";
import { StatusGlyph } from "@/components/domain/status";
import { DscrGauge, SensitivityGrid } from "@/components/domain/charts";
import { fmtMoney, fmtPct, fmtX, fmtDateTime, toNumber } from "@/lib/format";
import { useToast } from "@/components/ui/toast";

/** One plain sentence per assumption so the sliders read without a finance background. Keys mirror ASSUMPTION_SPECS in the engine. */
const HELP: Record<string, string> = {
  revenue_growth_pct: "Yearly change in total revenue, before any customer loss below.",
  largest_customer_loss_pct: "Share of the largest customer's revenue that goes away in year 1. 100% means the customer leaves entirely; 0% keeps all of it.",
  gross_margin_change_bps: "Basis points (bps): 100 bps is 1 percentage point of gross margin, so −100 bps takes a 42.0% margin to 41.0%.",
  labor_cost_growth_pct: "Yearly increase in wages and other labor costs.",
  other_opex_growth_pct: "Yearly increase in every other operating expense.",
  interest_rate_pct: "Interest rate on the acquisition debt.",
  purchase_price: "Price for the whole business, debt included (enterprise value).",
  debt_pct: "Share of the purchase price funded with debt; the rest is equity.",
  accepted_addbacks: "Adjustments added back to EBITDA each year. Defaults to the reviewed total from Financial Verification.",
  cash_tax_rate_pct: "Taxes actually paid in cash, as a share of taxable income.",
  maintenance_capex: "Yearly spending needed just to keep equipment and vehicles working.",
  nwc_pct_of_revenue_change: "Cash tied up in receivables and inventory for every dollar of revenue growth.",
};

const toDraft = (s: Scenario): Record<string, string> => Object.fromEntries(s.assumptions.map((a) => [a.key, String(Number(a.value))]));

export default function ScenariosPage() {
  const { dealId } = useParams<{ dealId: string }>();
  const kicker = useDealKicker();
  const qc = useQueryClient();
  const { toast } = useToast();
  const scenarios = useScenarios(dealId);
  const facts = useFacts(dealId);
  const [sel, setSel] = useState<string | null>(null);
  // Edited-but-unsaved assumptions per scenario; absent means "same as saved". Cleared after a successful run.
  const [drafts, setDrafts] = useState<Record<string, Record<string, string>>>({});
  const sc = useMemo(() => scenarios.data?.find((s) => s.id === sel) ?? scenarios.data?.[0], [scenarios.data, sel]);
  const run = useMutation({
    mutationFn: async ({ id, draft, dirty }: { id: string; draft: Record<string, string>; dirty: boolean }) => { if (dirty) await api.put(`/api/deals/${dealId}/scenarios/${id}/assumptions`, { values: draft }); return api.post(`/api/deals/${dealId}/scenarios/${id}/run`); },
    onSuccess: (_r, vars) => { setDrafts((d) => { const n = { ...d }; delete n[vars.id]; return n; }); qc.invalidateQueries({ queryKey: qk.scenarios(dealId) }); qc.invalidateQueries({ queryKey: qk.summary(dealId) }); toast({ title: "Scenario run saved", description: "The input snapshot and outputs are immutable; earlier runs stay in the history.", tone: "success" }); },
    onError: (e) => toast({ title: "Run failed", description: String(e), tone: "error" }),
  });
  const create = useMutation({ mutationFn: () => api.post<Scenario>(`/api/deals/${dealId}/scenarios`, { name: `Custom ${(scenarios.data?.length ?? 0) - 2}`, base_on_scenario_id: sc?.id }), onSuccess: (s) => { qc.invalidateQueries({ queryKey: qk.scenarios(dealId) }); setSel(s.id); } });
  const grid = useQuery({ queryKey: ["sensitivity", dealId, sc?.id, sc?.latest_result?.id], queryFn: () => api.post<Sensitivity>(`/api/deals/${dealId}/scenarios/sensitivity`, { scenario_id: sc!.id }), enabled: !!sc?.latest_result });
  if (scenarios.isPending || facts.isPending) return <div className="p-6"><Skeleton className="h-8 w-64" /><Skeleton className="mt-6 h-96" /></div>;
  if (scenarios.isError) return <div className="p-6"><ErrorState detail={String(scenarios.error)} onRetry={() => scenarios.refetch()} /></div>;
  if (!scenarios.data?.length || facts.data?.missing.length) return <div><PageHeader kicker={kicker} title="Scenario Lab" /><div className="p-6"><EmptyState title="Scenario inputs are not ready" body={facts.data?.missing.length ? `Missing: ${facts.data.missing.join(", ")}. Map financial statements and run analysis first.` : "Run analysis to seed Base, Downside, and Severe downside scenarios."} /></div></div>;
  const specs = facts.data!.specs;
  const res = sc?.latest_result ?? null;
  const out = res?.outputs;
  const y1 = out?.years[0];
  const threshold = String(facts.data!.facts.covenant_dscr_threshold ?? "");
  const saved = sc ? toDraft(sc) : {};
  const draft = sc ? (drafts[sc.id] ?? saved) : {};
  const dirty = !!sc && sc.assumptions.some((a) => Number(a.value) !== Number(draft[a.key]));
  const runNow = () => { if (sc) run.mutate({ id: sc.id, draft, dirty }); };
  return (
    <div>
      <PageHeader kicker={kicker} title="Scenario Lab" actions={<Button variant="secondary" size="sm" icon={<Plus size={14} />} onClick={() => create.mutate()} loading={create.isPending}>New scenario</Button>}>
        <p className="mt-2 max-w-3xl text-sm text-fg-muted">Test whether the business can still pay its loan when things go wrong. Change an assumption, run, and watch the debt coverage.</p>
        <div className="mt-4 flex flex-wrap gap-1" role="tablist" aria-label="Scenarios">
          {scenarios.data.map((s) => { const b = s.latest_result?.warnings.some((w) => w.code === "covenant_breach"); const w = s.latest_result?.warnings.some((x) => x.code === "covenant_warning"); return (
            <button key={s.id} role="tab" aria-selected={sc?.id === s.id} onClick={() => setSel(s.id)} className={`inline-flex h-9 items-center gap-2 rounded-[var(--radius-2)] border px-3 text-sm ${sc?.id === s.id ? "border-fg bg-fg text-bg" : "border-hairline hover:bg-bg-muted"}`}>
              <StatusGlyph status={b ? "breach" : w ? "warning" : s.latest_result ? "supported" : "pending"} size={11} />{s.name}<span className="num text-xs opacity-70">{fmtX(s.latest_result?.outputs.year1.dscr ?? null)}</span>
            </button>
          ); })}
        </div>
      </PageHeader>
      {sc && (
        <>
          <ResultStrip scenario={sc} threshold={threshold} dirty={dirty} running={run.isPending} onRun={runNow} />
          <div className="grid grid-cols-[minmax(0,1fr)] gap-4 p-4 md:p-6 xl:grid-cols-[380px_minmax(0,1fr)]">
            <AssumptionsPanel dealId={dealId} scenario={sc} specs={specs} draft={draft} dirty={dirty} running={run.isPending} onChange={(next) => setDrafts((d) => ({ ...d, [sc.id]: next }))} onReset={() => setDrafts((d) => { const n = { ...d }; delete n[sc.id]; return n; })} onRun={runNow} />
            <div className="flex flex-col gap-4">
              {!res && <EmptyState title="No result yet" body="Run the scenario to persist an immutable input snapshot and outputs." action={<Button onClick={runNow} loading={run.isPending}>Run scenario</Button>} />}
              {res && out && y1 && (
                <>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <Kpi label="Revenue, year 1" value={fmtMoney(y1.revenue)} />
                    <Kpi label="EBITDA, year 1" value={fmtMoney(y1.ebitda)} note="after accepted add-backs" />
                    <Kpi label="CFADS, year 1" value={fmtMoney(y1.cfads)} note="cash available to pay the lender" />
                    <Kpi label="Annual debt service" value={fmtMoney(out.annual_debt_service)} note="interest plus principal due each year" />
                    <Kpi label="Cash-on-cash, year 1" value={fmtPct(out.cash_on_cash_pct)} note="cash to equity ÷ equity invested" />
                    <Kpi label="Equity IRR, 5-year" value={out.irr_pct === null ? "undefined" : fmtPct(out.irr_pct)} note={out.irr_pct === null ? "no sign change in cash flows" : "annualized return on the equity; periodic IRR, not XIRR"} />
                    <Kpi label="Break-even revenue" value={fmtMoney(out.break_even_revenue)} note="revenue at which the loan is just covered; pre-tax, before working capital" />
                    <div className="rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-3"><DscrGauge value={y1.dscr} threshold={threshold} /><p className="mt-1 text-[11px] text-fg-muted">Debt coverage: CFADS ÷ debt service. Below 1.00x the business cannot pay its loan from its own cash.</p></div>
                  </div>
                  {res.warnings.length > 0 && (
                    <ul className="flex flex-col gap-1.5" aria-label="Warnings">{res.warnings.map((w, i) => <li key={i} className={`flex items-start gap-2 rounded-[var(--radius-2)] border p-2 text-sm ${w.severity === "critical" ? "border-red/50" : "border-amber/50"}`}><StatusGlyph status={w.code.includes("breach") || w.severity === "critical" ? "breach" : "warning"} className="mt-0.5" /><span>{w.message}</span></li>)}</ul>
                  )}
                  <Panel title="Five-year projection">
                    <Table caption="Projection by year" stickyFirst>
                      <thead><tr><th className={th}>Line</th>{out.years.map((y) => <th key={y.year} className={`${th} text-right`}>Year {y.year}</th>)}</tr></thead>
                      <tbody>
                        {([["revenue", "Revenue"], ["gross_profit", "Gross profit"], ["labor_opex", "Labor opex"], ["other_opex", "Other opex"], ["addbacks", "Accepted add-backs"], ["ebitda", "EBITDA"], ["interest", "Interest"], ["cash_taxes", "Cash taxes"], ["working_capital_investment", "Working-capital investment"], ["cfads", "CFADS (cash available for debt service)"], ["debt_service", "Debt service"], ["dscr", "DSCR (coverage)"], ["fcfe", "Cash flow to equity"], ["closing_debt", "Closing debt"]] as const).map(([k, label]) => (
                          <tr key={k} className={["ebitda", "cfads", "dscr"].includes(k) ? "font-medium" : ""}><td className={td}>{label}</td>{out.years.map((y) => <td key={y.year} className={`${td} num text-right`}>{k === "dscr" ? fmtX(y.dscr) : fmtMoney(y[k])}</td>)}</tr>
                        ))}
                      </tbody>
                    </Table>
                  </Panel>
                  <Panel title="Sensitivity: year-1 DSCR" actions={grid.isFetching && <span className="micro text-[10px]">computing…</span>}>
                    <p className="mb-3 text-xs text-fg-muted">Each cell is the year-1 debt coverage if the largest customer loses that share of its revenue (rows) and gross margin moves by that many basis points (columns; 100 bps = 1 percentage point). Cells below the covenant are marked.</p>
                    {grid.data ? <SensitivityGrid grid={grid.data} rowLabel="Largest-customer loss %" colLabel="Gross-margin change (bps)" fmt={(v) => fmtX(v)} /> : <Skeleton className="h-48" />}
                  </Panel>
                  <Panel title="Run history">
                    <RunHistory dealId={dealId} scenario={sc} />
                  </Panel>
                </>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/** Stays pinned while the assumptions scroll, so the answer to "can it still pay the loan?" never leaves the screen. */
function ResultStrip({ scenario, threshold, dirty, running, onRun }: { scenario: Scenario; threshold: string; dirty: boolean; running: boolean; onRun: () => void }) {
  const res = scenario.latest_result;
  const y1 = res?.outputs.years[0];
  const dscr = toNumber(y1?.dscr), thr = toNumber(threshold);
  const breach = res?.warnings.some((w) => w.code === "covenant_breach") || (dscr !== null && dscr < 1);
  const warn = !breach && (res?.warnings.some((w) => w.code === "covenant_warning") || (dscr !== null && thr !== null && dscr < thr));
  return (
    <div className="sticky top-0 z-30 border-b border-hairline bg-bg-raised px-4 py-2 md:px-6" role="status" aria-live="polite" aria-label="Latest result">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-sm">
        <span className="font-medium">{scenario.name}</span>
        {res && y1 ? (
          <>
            <span className="inline-flex items-center gap-1.5"><StatusGlyph status={breach ? "breach" : warn ? "warning" : "supported"} size={12} />Year-1 debt coverage <span className="num text-base font-medium">{fmtX(y1.dscr)}</span>{thr !== null && <span className="text-xs text-fg-muted">vs {fmtX(thr)} covenant</span>}</span>
            <span className="num text-xs text-fg-muted">{fmtMoney(y1.cfads)} cash ÷ {fmtMoney(res.outputs.annual_debt_service)} due</span>
            <span className="text-xs text-fg-muted">Run {res.run_no}, {fmtDateTime(res.created_at)}</span>
          </>
        ) : <span className="text-xs text-fg-muted">Not run yet</span>}
        {dirty && <span className="inline-flex items-center gap-1 text-xs font-medium text-amber"><StatusGlyph status="warning" size={11} />Assumptions changed; run to update</span>}
        <Button size="sm" icon={<Play size={14} />} className="ml-auto" onClick={onRun} loading={running}>Run scenario</Button>
      </div>
    </div>
  );
}

function AssumptionsPanel({ dealId, scenario, specs, draft, dirty, running, onChange, onReset, onRun }: { dealId: string; scenario: Scenario; specs: AssumptionSpec[]; draft: Record<string, string>; dirty: boolean; running: boolean; onChange: (next: Record<string, string>) => void; onReset: () => void; onRun: () => void }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const save = useMutation({ mutationFn: () => api.put<Scenario>(`/api/deals/${dealId}/scenarios/${scenario.id}/assumptions`, { values: draft }), onSuccess: () => { onReset(); qc.invalidateQueries({ queryKey: qk.scenarios(dealId) }); }, onError: (e) => toast({ title: "Invalid assumption", description: String(e), tone: "error" }) });
  return (
    <Panel title={<span className="flex items-center gap-2">Assumptions {dirty && <span className="text-xs font-medium text-amber">unsaved changes</span>}</span>} actions={<Button size="sm" icon={<Play size={14} />} onClick={onRun} loading={running}>Run scenario</Button>}>
      {scenario.description && <p className="mb-3 text-xs text-fg-muted">{scenario.description}</p>}
      <div className="flex flex-col gap-4">
        {specs.map((spec) => <AssumptionControl key={spec.key} spec={spec} value={draft[spec.key] ?? ""} onChange={(v) => onChange({ ...draft, [spec.key]: v })} />)}
      </div>
      {dirty && <div className="mt-4 flex gap-2"><Button size="sm" variant="secondary" onClick={() => save.mutate()} loading={save.isPending}>Save without running</Button><Button size="sm" variant="ghost" onClick={onReset}>Reset</Button></div>}
    </Panel>
  );
}

function Kpi({ label, value, note }: { label: string; value: string; note?: string }) {
  return <div className="rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-3"><p className="text-xs text-fg-muted">{label}</p><p className="num mt-1 text-xl">{value}</p>{note && <p className="mt-0.5 text-[11px] text-fg-muted">{note}</p>}</div>;
}

function AssumptionControl({ spec, value, onChange }: { spec: AssumptionSpec; value: string; onChange: (v: string) => void }) {
  const id = `a-${spec.key}`;
  const helpId = `${id}-help`;
  const suffix = spec.unit === "pct" ? "%" : spec.unit === "usd" ? "USD" : spec.unit === "count" ? "bps" : "";
  const shown = spec.unit === "usd" ? fmtMoney(value) : `${Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 })}${spec.unit === "pct" ? "%" : spec.unit === "count" ? " bps" : ""}`;
  const help = HELP[spec.key];
  return (
    <div>
      <div className="flex items-center justify-between gap-2"><label htmlFor={id} className="text-sm">{spec.label}</label><span className="num text-sm">{shown}</span></div>
      <div className="mt-1 flex items-center gap-2">
        <input id={id} type="range" min={spec.min} max={spec.max} step={spec.step} value={value} onChange={(e) => onChange(e.target.value)} className="h-6 w-full accent-[var(--accent)]" aria-valuetext={`${value} ${suffix}`} aria-describedby={help ? helpId : undefined} />
        <input aria-label={`${spec.label} value`} type="number" min={spec.min} max={spec.max} step={spec.step} value={value} onChange={(e) => onChange(e.target.value)} className="num h-8 w-28 rounded-[var(--radius-1)] border border-hairline bg-bg-raised px-2 text-right text-sm" aria-describedby={help ? helpId : undefined} />
      </div>
      {help && <p id={helpId} className="mt-1 text-[11px] leading-snug text-fg-muted">{help}</p>}
    </div>
  );
}

function RunHistory({ dealId, scenario }: { dealId: string; scenario: Scenario }) {
  const runs = useQuery({ queryKey: ["runs", dealId, scenario.id, scenario.result_count], queryFn: () => api.get<Scenario["latest_result"][]>(`/api/deals/${dealId}/scenarios/${scenario.id}/results`) });
  if (!runs.data) return <Skeleton className="h-16" />;
  return (
    <Table caption="Scenario runs, newest first">
      <thead><tr><th className={th}>Run</th><th className={th}>When</th><th className={th}>Engine</th><th className={th}>Input hash</th><th className={`${th} text-right`}>DSCR</th><th className={th}>Warnings</th></tr></thead>
      <tbody>{[...runs.data].reverse().map((r) => r && <tr key={r.id}><td className={`${td} num`}>{r.run_no}</td><td className={`${td} whitespace-nowrap text-xs text-fg-muted`}>{fmtDateTime(r.created_at)}</td><td className={`${td} font-mono text-xs`}>{r.engine_version}</td><td className={`${td} font-mono text-xs text-fg-muted`} title={r.input_hash}>{r.input_hash.slice(0, 12)}</td><td className={`${td} num text-right`}>{fmtX(r.outputs.year1.dscr)}</td><td className={`${td} text-xs`}>{r.warnings.map((w) => w.code.replace(/_/g, " ")).join(", ") || "—"}</td></tr>)}</tbody>
    </Table>
  );
}
