"use client";

import { motion, useReducedMotion } from "motion/react";
import { useMemo, useState } from "react";
import snapshot from "@/content/northstar-snapshot.json";
import { StatusChip, StatusGlyph } from "@/components/domain/status";
import { fmtMoney, fmtX } from "@/lib/format";

const S = snapshot;
const view = { once: true, amount: 0.4 } as const;
const reveal = (delay = 0) => ({ initial: { opacity: 0, y: 8 }, whileInView: { opacity: 1, y: 0 }, viewport: view, transition: { duration: 0.32, delay, ease: [0.32, 0.72, 0, 1] as const } });

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`rounded-[var(--radius-3)] border border-hairline bg-ink-900 p-4 ${className}`}>{children}</div>;
}

/** Section 2: a claim card wired to its spreadsheet cells by a drawn hairline. */
export function ClaimEvidenceFigure() {
  const reduced = useReducedMotion();
  const years = Object.keys(S.revenue);
  return (
    <figure className="relative grid gap-6 md:grid-cols-[1fr_auto_1fr] md:items-center">
      <motion.div {...reveal(0)}>
        <Card>
          <p className="micro">Claim · {S.claims[0].source}</p>
          <p className="mt-2 text-lg leading-snug">“{S.claims[0].text}”</p>
          <div className="mt-3"><StatusChip status="contradicted" /></div>
        </Card>
      </motion.div>
      <svg width="120" height="60" viewBox="0 0 120 60" className="hidden justify-self-center md:block" aria-hidden>
        <motion.path d="M4 30 H116" stroke="var(--chart-red)" strokeWidth="1.25" fill="none" initial={{ pathLength: reduced ? 1 : 0 }} whileInView={{ pathLength: 1 }} viewport={view} transition={{ duration: 0.9, ease: [0.32, 0.72, 0, 1] }} />
        <rect x="0" y="26" width="8" height="8" fill="var(--chart-red)" />
        <motion.circle cx="116" cy="30" r="3" fill="var(--ink-900)" stroke="var(--chart-red)" strokeWidth="1.25" initial={{ opacity: reduced ? 1 : 0 }} whileInView={{ opacity: 1 }} viewport={view} transition={{ delay: 0.8 }} />
      </svg>
      <motion.div {...reveal(0.15)}>
        <Card>
          <p className="micro">Evidence · Income Statement!B4:D4</p>
          <table className="mt-2 w-full text-sm"><thead><tr className="text-left text-xs text-fg-muted">{years.map((y) => <th key={y} className="py-1 font-medium">{y}</th>)}</tr></thead><tbody><tr>{years.map((y) => <td key={y} className="num py-1 pr-3">{fmtMoney(S.revenue[y as keyof typeof S.revenue], { compact: true })}</td>)}</tr></tbody></table>
          <p className="mt-3 text-sm">Recomputed CAGR <span className="num text-accent">{S.cagr_pct}%</span> <span className="text-fg-muted">vs. claimed</span> <span className="num text-red">{S.cim_growth_pct}%</span></p>
          <p className="mt-1 font-mono text-[11px] text-fg-muted">(last / first)^(1/2) − 1 · deterministic engine</p>
        </Card>
      </motion.div>
      <figcaption className="sr-only">A claim from the CIM is linked by a hairline to the spreadsheet cells that contradict it.</figcaption>
    </figure>
  );
}

/** Section 3: two sources, one contradiction; hovering the chip highlights both. */
export function ContradictionFigure() {
  const [hot, setHot] = useState(false);
  const hl = hot ? "border-red bg-red/10" : "border-hairline";
  return (
    <figure className="grid gap-4 md:grid-cols-2">
      <motion.div {...reveal(0)} className={`rounded-[var(--radius-3)] border bg-ink-900 p-4 transition-colors duration-[120ms] ${hl}`}>
        <p className="micro">Source A · {S.claims[1].source}</p>
        <p className="mt-2 text-lg leading-snug">“{S.claims[1].text}”</p>
      </motion.div>
      <motion.div {...reveal(0.1)} className={`rounded-[var(--radius-3)] border bg-ink-900 p-4 transition-colors duration-[120ms] ${hl}`}>
        <p className="micro">Source B · customer revenue CSV, row 2 + aggregate</p>
        <p className="mt-2 text-lg leading-snug">{S.top_customer.name}: <span className="num">{fmtMoney(S.top_customer.revenue)}</span> of <span className="num">{fmtMoney(S.revenue.FY2024)}</span></p>
        <p className="mt-1 num text-sm text-fg-muted">= {S.top_customer.pct}% of FY2024 revenue</p>
      </motion.div>
      <div className="md:col-span-2">
        <button type="button" onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)} onFocus={() => setHot(true)} onBlur={() => setHot(false)} className="inline-flex items-center gap-2 rounded-full border border-hairline px-3 py-1.5 text-sm hover:border-red" aria-describedby="contra-desc">
          <StatusGlyph status="contradicted" /> Contradicted · hover to highlight both sources
        </button>
        <p id="contra-desc" className="mt-3 max-w-xl text-sm text-fg-muted">A statement that “no customer exceeds 10%” meets a customer file in which one account is 22%. Neither document is trusted; both are cited, and a reviewer decides. Absence of evidence never counts as contradiction.</p>
      </div>
    </figure>
  );
}

/** Section 4: reported → verified waterfall with rejected items hatched. */
export function WaterfallFigure() {
  const reduced = useReducedMotion();
  const steps = useMemo(() => {
    const reported = Number(S.ebitda.reported);
    let run = reported;
    const out: Array<{ label: string; amount: number; included: boolean; decision: string; from: number; to: number }> = [{ label: "Reported EBITDA", amount: reported, included: true, decision: "reported", from: 0, to: reported }];
    for (const a of S.addbacks) { const amt = Number(a.amount); const inc = a.decision === "accepted"; const from = run; if (inc) run += amt; out.push({ label: a.label, amount: amt, included: inc, decision: a.decision, from, to: inc ? run : from + amt }); }
    out.push({ label: "Verified adjusted", amount: run, included: true, decision: "verified", from: 0, to: run });
    return out;
  }, []);
  const max = Number(S.ebitda.seller) * 1.06;
  const W = 720, H = 260, padL = 48, padB = 58, padT = 16;
  const innerH = H - padT - padB, innerW = W - padL - 12;
  const y = (v: number) => padT + innerH - (v / max) * innerH;
  const slot = innerW / steps.length, bw = Math.min(54, slot * 0.6);
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Waterfall from reported EBITDA of $1.64M through five seller add-backs to verified adjusted EBITDA of $1.81M; the seller claimed $2.10M">
        <defs><pattern id="lp-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="var(--chart-graphite)" strokeWidth="1.5" /></pattern></defs>
        <line x1={padL} x2={W - 12} y1={y(Number(S.ebitda.seller))} y2={y(Number(S.ebitda.seller))} stroke="var(--chart-graphite)" strokeDasharray="4 3" />
        <text x={W - 12} y={y(Number(S.ebitda.seller)) - 5} textAnchor="end" fontSize="10" fontFamily="var(--font-mono)" fill="var(--fg-muted)">seller {fmtMoney(S.ebitda.seller, { compact: true })}</text>
        {steps.map((s, i) => {
          const x = padL + i * slot + (slot - bw) / 2;
          const top = Math.max(s.from, s.to), bottom = Math.min(s.from, s.to);
          const isTotal = s.decision === "reported" || s.decision === "verified";
          return (
            <g key={s.label}>
              <motion.rect x={x} width={bw} rx={2} fill={s.included ? "var(--chart-signal)" : "url(#lp-hatch)"} stroke={s.included ? "none" : "var(--chart-graphite)"} strokeDasharray={s.included ? undefined : "3 2"} initial={{ y: reduced ? y(top) : y(bottom), height: reduced ? y(bottom) - y(top) : 0 }} whileInView={{ y: y(top), height: Math.max(2, y(bottom) - y(top)) }} viewport={view} transition={{ duration: 0.5, delay: i * 0.08, ease: [0.32, 0.72, 0, 1] }} />
              <text x={x + bw / 2} y={y(top) - 6} textAnchor="middle" fontSize="11" fontFamily="var(--font-mono)" fill="var(--fg)">{isTotal ? fmtMoney(s.to, { compact: true }) : `▲ ${fmtMoney(s.amount, { compact: true })}`}</text>
              <foreignObject x={padL + i * slot} y={H - padB + 6} width={slot} height={padB - 6}><div className="px-0.5 text-center text-[10px] leading-tight text-fg-muted" style={{ fontFamily: "var(--font-sans)" }}>{s.label}<br /><span className={s.decision === "accepted" || isTotal ? "text-accent" : s.decision === "review_required" ? "text-amber" : "text-graphite"}>{isTotal ? "" : s.decision.replace("_", " ")}</span></div></foreignObject>
            </g>
          );
        })}
        <line x1={padL} x2={W - 12} y1={y(0)} y2={y(0)} stroke="var(--fg-muted)" />
      </svg>
      <figcaption className="mt-2 text-xs text-fg-muted">Accepted add-backs are solid; rejected, review-required, and unsupported items are hatched and excluded from the running total. Every bar cites a statement line or a note.</figcaption>
    </figure>
  );
}

/** Section 5: interactive DSCR from the engine's precomputed sensitivity grid (bilinear interpolation). */
export function ScenarioFigure() {
  const rows = S.sensitivity.rows.map(Number), cols = S.sensitivity.cols.map(Number);
  const [loss, setLoss] = useState(0);
  const [bps, setBps] = useState(0);
  const threshold = Number(S.deal.threshold);
  const dscr = useMemo(() => {
    const cell = (i: number, j: number) => Number(S.sensitivity.cells[i][j].v ?? 0);
    const ri = Math.min(rows.length - 2, Math.max(0, rows.findIndex((r, i) => loss >= r && loss <= (rows[i + 1] ?? Infinity))));
    const cj = Math.min(cols.length - 2, Math.max(0, cols.findIndex((c, j) => bps <= c && bps >= (cols[j + 1] ?? -Infinity))));
    const tr = (loss - rows[ri]) / (rows[ri + 1] - rows[ri]), tc = (bps - cols[cj]) / (cols[cj + 1] - cols[cj]);
    const a = cell(ri, cj) * (1 - tc) + cell(ri, cj + 1) * tc, b = cell(ri + 1, cj) * (1 - tc) + cell(ri + 1, cj + 1) * tc;
    return a * (1 - tr) + b * tr;
  }, [loss, bps, rows, cols]);
  const status = dscr < threshold ? "breach" : dscr < threshold * 1.1 ? "warning" : "supported";
  const max = 2.2;
  const pct = (v: number) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`;
  return (
    <figure className="grid gap-6 md:grid-cols-[1fr_1fr]">
      <div className="flex flex-col gap-5">
        <label className="block text-sm"><span className="flex justify-between">Loss of largest customer <span className="num">{loss}%</span></span><input type="range" min={0} max={100} step={5} value={loss} onChange={(e) => setLoss(Number(e.target.value))} className="mt-1 w-full accent-[var(--chart-signal)]" aria-valuetext={`${loss} percent`} /></label>
        <label className="block text-sm"><span className="flex justify-between">Gross-margin compression <span className="num">{bps} bps</span></span><input type="range" min={-400} max={0} step={25} value={bps} onChange={(e) => setBps(Number(e.target.value))} className="mt-1 w-full accent-[var(--chart-signal)]" aria-valuetext={`${bps} basis points`} /></label>
        <p className="text-xs text-fg-muted">Interpolated from a 5×5 grid the deterministic engine computed from the base case ({S.deal.rate}% over {S.deal.years} years, {fmtMoney(S.deal.ads, { compact: true })} annual debt service). The app recomputes exactly.</p>
      </div>
      <Card>
        <div className="flex items-baseline justify-between"><span className="text-sm text-fg-muted">DSCR, year 1</span><span className="inline-flex items-center gap-2 num text-3xl"><StatusGlyph status={status} size={16} />{fmtX(dscr)}</span></div>
        <div className="relative mt-4 h-3 w-full rounded-[2px] bg-ink-700" role="img" aria-label={`DSCR ${fmtX(dscr)} against a ${fmtX(threshold)} covenant`}>
          <div className="absolute inset-y-0 left-0 rounded-[2px] bg-chart-red/20" style={{ width: pct(threshold) }} />
          <motion.div className={`absolute inset-y-0 left-0 rounded-[2px] ${status === "breach" ? "bg-chart-red" : status === "warning" ? "bg-chart-amber" : "bg-chart-signal"}`} animate={{ width: pct(dscr) }} transition={{ duration: 0.4, ease: [0.2, 0, 0, 1] }} />
          <div className="absolute -top-1 h-5 w-px bg-fg" style={{ left: pct(threshold) }} />
        </div>
        <div className="mt-2 flex justify-between font-mono text-[10px] text-fg-muted"><span>0.0x</span><span>covenant {fmtX(threshold)}</span><span>{max.toFixed(1)}x</span></div>
        <p className="mt-4 text-sm text-fg-muted" aria-live="polite">{status === "breach" ? "Below the lender's minimum: the deal cannot service its debt from cash flow under these assumptions." : status === "warning" ? "Within 10% of the covenant: little room for error." : "Above the covenant with headroom."}</p>
      </Card>
    </figure>
  );
}

/** Section 6: the report assembling section by section with citation chips. */
export function ReportFigure() {
  return (
    <figure>
      <Card className="max-w-2xl">
        <div className="flex flex-wrap items-center gap-3 border-b border-hairline pb-3 text-sm">
          <span className="inline-flex items-center gap-2 rounded-full border border-hairline px-3 py-1 font-medium"><StatusGlyph status="contradicted" /> Material concerns identified</span>
          <span className="num text-fg-muted">36/36 material statements cited</span>
        </div>
        <ol className="mt-3 flex flex-col gap-1.5">
          {S.report_sections.map((s, i) => (
            <motion.li key={s} {...reveal(i * 0.06)} className="flex items-center gap-3 text-sm">
              <span className="num w-6 text-xs text-fg-muted">{String(i + 1).padStart(2, "0")}</span>
              <span className="flex-1">{s}</span>
              <span className="inline-flex gap-1">{["E", "M", "E"].slice(0, (i % 3) + 1).map((k, j) => <span key={j} className="rounded-[var(--radius-1)] border border-hairline bg-ink-800 px-1 font-mono text-[10px] text-fg-muted">{k}:{(i * 7 + j * 13).toString(16).padStart(4, "0")}</span>)}</span>
            </motion.li>
          ))}
        </ol>
      </Card>
      <figcaption className="mt-3 max-w-2xl text-sm text-fg-muted">Sections are assembled from persisted rows. Narrative sentences are drafted by the model and must cite evidence (E) or a calculation (M), or the report fails validation. Outcomes describe the state of the review; the tool never says buy or reject.</figcaption>
    </figure>
  );
}

export function ProofStrip() {
  const items = [["4 claim statuses", "Supported, contradicted, unsupported, review required. Absence of evidence is not contradiction."], ["16 documented formulas", "Decimal arithmetic, explicit missing-data behavior, input snapshots on every persisted metric."], ["Cited or labeled", "Every material statement in the report resolves to evidence or names the inputs it derives from."]];
  return (
    <ul className="grid gap-px overflow-hidden rounded-[var(--radius-3)] border border-hairline bg-hairline md:grid-cols-3">
      {items.map(([t, d]) => <li key={t} className="bg-ink-950 p-5"><p className="font-medium">{t}</p><p className="mt-1 text-sm text-fg-muted">{d}</p></li>)}
    </ul>
  );
}
