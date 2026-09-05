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
import { fmtMoney, fmtPct, fmtX, fmtValue, fmtDate } from "@/lib/format";
import { useToast } from "@/components/ui/toast";

export default function ScenariosPage() {
  const { dealId } = useParams<{ dealId: string }>();
  const kicker = useDealKicker();
  const qc = useQueryClient();
  const { toast } = useToast();
  const scenarios = useScenarios(dealId);
  const facts = useFacts(dealId);
  const [sel, setSel] = useState<string | null>(null);
  const sc = useMemo(() => scenarios.data?.find((s) => s.id === sel) ?? scenarios.data?.[0], [scenarios.data, sel]);
  const run = useMutation({ mutationFn: async ({ id, draft, dirty }: { id: string; draft: Record<string, string>; dirty: boolean }) => { if (dirty) await api.put(`/api/deals/${dealId}/scenarios/${id}/assumptions`, { values: draft }); return api.post(`/api/deals/${dealId}/scenarios/${id}/run`); }, onSuccess: () => { qc.invalidateQueries({ queryKey: qk.scenarios(dealId) }); qc.invalidateQueries({ queryKey: qk.summary(dealId) }); toast({ title: "Scenario run saved", description: "The input snapshot and outputs are immutable.", tone: "success" }); }, onError: (e) => toast({ title: "Run failed", description: String(e), tone: "error" }) });
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
  return (
    <div>
      <PageHeader kicker={kicker} title="Scenario Lab" actions={<Button variant="secondary" size="sm" icon={<Plus size={14} />} onClick={() => create.mutate()} loading={create.isPending}>New scenario</Button>}>
        <div className="mt-4 flex flex-wrap gap-1" role="tablist" aria-label="Scenarios">
          {scenarios.data.map((s) => { const b = s.latest_result?.warnings.some((w) => w.code === "covenant_breach"); const w = s.latest_result?.warnings.some((x) => x.code === "covenant_warning"); return (
            <button key={s.id} role="tab" aria-selected={sc?.id === s.id} onClick={() => setSel(s.id)} className={`inline-flex h-9 items-center gap-2 rounded-full border px-3 text-sm ${sc?.id === s.id ? "border-fg bg-fg text-bg" : "border-hairline hover:bg-bg-muted"}`}>
              <StatusGlyph status={b ? "breach" : w ? "warning" : s.latest_result ? "supported" : "pending"} size={11} />{s.name}<span className="num text-xs opacity-70">{fmtX(s.latest_result?.outputs.year1.dscr ?? null)}</span>
            </button>
          ); })}
        </div>
      </PageHeader>
      {sc && (
        <div className="grid gap-4 p-4 md:p-6 xl:grid-cols-[380px_minmax(0,1fr)]">
          <AssumptionsPanel key={`${sc.id}:${sc.result_count}`} dealId={dealId} scenario={sc} specs={specs} running={run.isPending} onRun={(draft, dirty) => run.mutate({ id: sc.id, draft, dirty })} />
          <div className="flex flex-col gap-4">
            {!res && <EmptyState title="No result yet" body="Run the scenario to persist an immutable input snapshot and outputs." action={<Button onClick={() => run.mutate({ id: sc.id, draft: Object.fromEntries(sc.assumptions.map((a) => [a.key, String(Number(a.value))])), dirty: false })} loading={run.isPending}>Run scenario</Button>} />}
            {res && out && y1 && (
              <>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <Kpi label="Revenue, year 1" value={fmtMoney(y1.revenue)} />
                  <Kpi label="EBITDA, year 1" value={fmtMoney(y1.ebitda)} />
                  <Kpi label="CFADS, year 1" value={fmtMoney(y1.cfads)} />
                  <Kpi label="Annual debt service" value={fmtMoney(out.annual_debt_service)} />
                  <Kpi label="Cash-on-cash, year 1" value={fmtPct(out.cash_on_cash_pct)} />
                  <Kpi label="Equity IRR, 5-year" value={out.irr_pct === null ? "undefined" : fmtPct(out.irr_pct)} note={out.irr_pct === null ? "no sign change in cash flows" : "periodic IRR, not XIRR"} />
                  <Kpi label="Break-even revenue" value={fmtMoney(out.break_even_revenue)} note="pre-tax, before working capital" />
                  <div className="rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-3"><DscrGauge value={y1.dscr} threshold={threshold} /></div>
                </div>
                {res.warnings.length > 0 && (
                  <ul className="flex flex-col gap-1.5" aria-label="Warnings">{res.warnings.map((w, i) => <li key={i} className={`flex items-start gap-2 rounded-[var(--radius-2)] border p-2 text-sm ${w.severity === "critical" ? "border-red/50" : "border-amber/50"}`}><StatusGlyph status={w.code.includes("breach") || w.severity === "critical" ? "breach" : "warning"} className="mt-0.5" /><span>{w.message}</span></li>)}</ul>
                )}
                <Panel title="Five-year projection">
                  <Table caption="Projection by year" stickyFirst>
                    <thead><tr><th className={th}>Line</th>{out.years.map((y) => <th key={y.year} className={`${th} text-right`}>Year {y.year}</th>)}</tr></thead>
                    <tbody>
                      {([["revenue", "Revenue"], ["gross_profit", "Gross profit"], ["labor_opex", "Labor opex"], ["other_opex", "Other opex"], ["addbacks", "Accepted add-backs"], ["ebitda", "EBITDA"], ["interest", "Interest"], ["cash_taxes", "Cash taxes"], ["working_capital_investment", "Working-capital investment"], ["cfads", "CFADS"], ["debt_service", "Debt service"], ["dscr", "DSCR"], ["fcfe", "Cash flow to equity"], ["closing_debt", "Closing debt"]] as const).map(([k, label]) => (
                        <tr key={k} className={["ebitda", "cfads", "dscr"].includes(k) ? "font-medium" : ""}><td className={td}>{label}</td>{out.years.map((y) => <td key={y.year} className={`${td} num text-right`}>{k === "dscr" ? fmtX(y.dscr) : fmtMoney(y[k])}</td>)}</tr>
                      ))}
                    </tbody>
                  </Table>
                </Panel>
                <Panel title="Sensitivity: year-1 DSCR" actions={grid.isFetching && <span className="micro text-[10px]">computing…</span>}>
                  {grid.data ? <SensitivityGrid grid={grid.data} rowLabel="Largest-customer loss %" colLabel="Gross-margin change (bps)" fmt={(v) => fmtX(v)} /> : <Skeleton className="h-48" />}
                </Panel>
                <Panel title="Run history">
                  <RunHistory dealId={dealId} scenario={sc} />
                </Panel>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function AssumptionsPanel({ dealId, scenario, specs, running, onRun }: { dealId: string; scenario: Scenario; specs: AssumptionSpec[]; running: boolean; onRun: (draft: Record<string, string>, dirty: boolean) => void }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const initial = useMemo(() => Object.fromEntries(scenario.assumptions.map((a) => [a.key, String(Number(a.value))])), [scenario]);
  const [draft, setDraft] = useState<Record<string, string>>(initial);
  const dirty = scenario.assumptions.some((a) => Number(a.value) !== Number(draft[a.key]));
  const save = useMutation({ mutationFn: () => api.put<Scenario>(`/api/deals/${dealId}/scenarios/${scenario.id}/assumptions`, { values: draft }), onSuccess: () => qc.invalidateQueries({ queryKey: qk.scenarios(dealId) }), onError: (e) => toast({ title: "Invalid assumption", description: String(e), tone: "error" }) });
  return (
    <Panel title={<span className="flex items-center gap-2">Assumptions {dirty && <span className="micro text-[10px] text-amber">draft</span>}</span>} actions={<Button size="sm" icon={<Play size={14} />} onClick={() => onRun(draft, dirty)} loading={running}>Run scenario</Button>}>
      {scenario.description && <p className="mb-3 text-xs text-fg-muted">{scenario.description}</p>}
      <div className="flex flex-col gap-4">
        {specs.map((spec) => <AssumptionControl key={spec.key} spec={spec} value={draft[spec.key] ?? ""} onChange={(v) => setDraft({ ...draft, [spec.key]: v })} />)}
      </div>
      {dirty && <div className="mt-4 flex gap-2"><Button size="sm" variant="secondary" onClick={() => save.mutate()} loading={save.isPending}>Save without running</Button><Button size="sm" variant="ghost" onClick={() => setDraft(initial)}>Reset</Button></div>}
    </Panel>
  );
}

function Kpi({ label, value, note }: { label: string; value: string; note?: string }) {
  return <div className="rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-3"><p className="text-xs text-fg-muted">{label}</p><p className="num mt-1 text-xl">{value}</p>{note && <p className="mt-0.5 text-[11px] text-fg-muted">{note}</p>}</div>;
}

function AssumptionControl({ spec, value, onChange }: { spec: AssumptionSpec; value: string; onChange: (v: string) => void }) {
  const id = `a-${spec.key}`;
  const suffix = spec.unit === "pct" ? "%" : spec.unit === "usd" ? "USD" : spec.unit === "count" ? "bps" : "";
  const shown = spec.unit === "usd" ? fmtMoney(value) : `${Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 })}${spec.unit === "pct" ? "%" : spec.unit === "count" ? " bps" : ""}`;
  return (
    <div>
      <div className="flex items-center justify-between gap-2"><label htmlFor={id} className="text-sm">{spec.label}</label><span className="num text-sm">{shown}</span></div>
      <div className="mt-1 flex items-center gap-2">
        <input id={id} type="range" min={spec.min} max={spec.max} step={spec.step} value={value} onChange={(e) => onChange(e.target.value)} className="h-6 w-full accent-[var(--accent)]" aria-valuetext={`${value} ${suffix}`} />
        <input aria-label={`${spec.label} value`} type="number" min={spec.min} max={spec.max} step={spec.step} value={value} onChange={(e) => onChange(e.target.value)} className="num h-8 w-28 rounded-[var(--radius-1)] border border-hairline bg-bg-raised px-2 text-right text-sm" />
      </div>
    </div>
  );
}

function RunHistory({ dealId, scenario }: { dealId: string; scenario: Scenario }) {
  const runs = useQuery({ queryKey: ["runs", dealId, scenario.id, scenario.result_count], queryFn: () => api.get<Scenario["latest_result"][]>(`/api/deals/${dealId}/scenarios/${scenario.id}/results`) });
  if (!runs.data) return <Skeleton className="h-16" />;
  return (
    <Table caption="Scenario runs">
      <thead><tr><th className={th}>Run</th><th className={th}>When</th><th className={th}>Engine</th><th className={th}>Input hash</th><th className={`${th} text-right`}>DSCR</th><th className={th}>Warnings</th></tr></thead>
      <tbody>{[...runs.data].reverse().map((r) => r && <tr key={r.id}><td className={`${td} num`}>{r.run_no}</td><td className={`${td} text-xs text-fg-muted`}>{fmtDate(r.created_at)}</td><td className={`${td} font-mono text-xs`}>{r.engine_version}</td><td className={`${td} font-mono text-xs text-fg-muted`} title={r.input_hash}>{r.input_hash.slice(0, 12)}</td><td className={`${td} num text-right`}>{fmtX(r.outputs.year1.dscr)}</td><td className={`${td} text-xs`}>{r.warnings.map((w) => w.code).join(", ") || "—"}</td></tr>)}</tbody>
    </Table>
  );
}

export { fmtValue };
