"use client";

import { motion } from "motion/react";
import { useMediaQuery } from "@/lib/hooks";
import { useMemo, useState } from "react";
import snapshot from "@/content/northstar-snapshot.json";
import { StatusChip, StatusGlyph } from "@/components/domain/status";
import { fmtMoney, fmtPct, fmtX } from "@/lib/format";

const S = snapshot;
const view = { once: true, amount: 0.4 } as const;
const ease = [0.16, 1, 0.3, 1] as const;

function Sheet({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`rounded-[var(--radius-3)] border border-hairline bg-ink-900/80 ${className}`}>{children}</div>;
}

/** A claim card wired to its spreadsheet cells by a drawn hairline. */
export function ClaimEvidenceFigure() {
  const reduced = useMediaQuery("(prefers-reduced-motion: reduce)");
  const years = Object.keys(S.revenue);
  return (
    <figure className="relative grid gap-4 md:grid-cols-[1fr_88px_1fr] md:items-center">
      <Sheet className="p-5">
        <p className="text-xs text-fg-muted">From the sales memo (CIM), page 3</p>
        <p className="mt-2 text-lg leading-snug">“{S.claims[0].text}”</p>
        <div className="mt-4"><StatusChip status="contradicted" /></div>
      </Sheet>
      <svg width="88" height="40" viewBox="0 0 88 40" className="hidden justify-self-center md:block" aria-hidden>
        <motion.path d="M4 20 H84" stroke="var(--chart-red)" strokeWidth="1.25" fill="none" initial={{ pathLength: reduced ? 1 : 0 }} whileInView={{ pathLength: 1 }} viewport={view} transition={{ duration: 0.9, ease }} />
        <rect x="0" y="16" width="8" height="8" fill="var(--chart-red)" />
        <motion.circle cx="84" cy="20" r="3" fill="var(--color-ink-900)" stroke="var(--chart-red)" strokeWidth="1.25" initial={{ opacity: reduced ? 1 : 0 }} whileInView={{ opacity: 1 }} viewport={view} transition={{ delay: 0.8 }} />
      </svg>
      <Sheet className="p-5">
        <p className="text-xs text-fg-muted">From the financial statements, Income Statement cells B4 to D4</p>
        <table className="mt-2 w-full text-sm">
          <caption className="sr-only">Revenue by fiscal year</caption>
          <thead><tr className="text-left text-xs text-fg-muted">{years.map((y) => <th key={y} scope="col" className="py-1 font-medium">{y}</th>)}</tr></thead>
          <tbody><tr>{years.map((y) => <td key={y} className="num py-1 pr-3">{fmtMoney(S.revenue[y as keyof typeof S.revenue], { compact: true })}</td>)}</tr></tbody>
        </table>
        <p className="mt-3 text-sm">Recomputed growth <span className="num font-medium text-accent">{fmtPct(S.cagr_pct)} a year</span>, against the claimed <span className="num font-medium text-red">{S.cim_growth_pct}%</span>.</p>
      </Sheet>
      <figcaption className="sr-only">A claim from the sales memo is linked by a hairline to the spreadsheet cells that contradict it.</figcaption>
    </figure>
  );
}

/** Two sources, one contradiction; hovering or focusing the chip highlights both. */
export function ContradictionFigure() {
  const [hot, setHot] = useState(false);
  const hl = hot ? "border-chart-red" : "border-hairline";
  return (
    <figure>
      <div className="grid gap-4 md:grid-cols-2">
        <div className={`rounded-[var(--radius-3)] border bg-ink-900/80 p-5 transition-colors duration-150 ${hl}`}>
          <p className="text-xs text-fg-muted">Sales memo (CIM), page 5</p>
          <p className="mt-2 text-lg leading-snug">“{S.claims[1].text}”</p>
        </div>
        <div className={`rounded-[var(--radius-3)] border bg-ink-900/80 p-5 transition-colors duration-150 ${hl}`}>
          <p className="text-xs text-fg-muted">Customer revenue file, row 2 and the customer totals</p>
          <p className="mt-2 text-lg leading-snug">{S.top_customer.name}: <span className="num">{fmtMoney(S.top_customer.revenue)}</span> of <span className="num">{fmtMoney(S.revenue.FY2024)}</span></p>
          <p className="mt-1 text-sm text-fg-muted"><span className="num">{fmtPct(S.top_customer.pct)}</span> of FY2024 revenue. The memo says no customer is above <span className="num">{S.top_customer.cim_max_pct}%</span>.</p>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-4">
        <button type="button" onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)} onFocus={() => setHot(true)} onBlur={() => setHot(false)} className="inline-flex items-center gap-2 rounded-[var(--radius-2)] border border-hairline px-3 py-1.5 text-sm hover:border-chart-red" aria-describedby="contra-desc">
          <StatusGlyph status="contradicted" /> Contradicted
        </button>
        <p id="contra-desc" className="max-w-xl text-sm text-fg-muted">Hover or focus the status to see both sources light up. Neither document is trusted on its own; both are cited, and a reviewer decides.</p>
      </div>
    </figure>
  );
}

/** Reported to verified EBITDA as a bridge on a truncated axis so each add-back is legible. */
export function WaterfallFigure() {
  const reduced = useMediaQuery("(prefers-reduced-motion: reduce)");
  const steps = useMemo(() => {
    const reported = Number(S.ebitda.reported);
    let run = reported;
    const out: Array<{ label: string; amount: number; included: boolean; decision: string; from: number; to: number }> = [{ label: "Reported EBITDA", amount: reported, included: true, decision: "reported", from: 0, to: reported }];
    for (const a of S.addbacks) { const amt = Number(a.amount); const inc = a.decision === "accepted"; const from = run; if (inc) run += amt; out.push({ label: a.label, amount: amt, included: inc, decision: a.decision, from, to: inc ? run : from + amt }); }
    out.push({ label: "Verified adjusted EBITDA", amount: run, included: true, decision: "verified", from: 0, to: run });
    return out;
  }, []);
  const seller = Number(S.ebitda.seller);
  const reported = steps[0].to, verified = steps[steps.length - 1].to;
  const floor = 1_500_000, ceil = 2_200_000;
  const W = 900, H = 340, padL = 64, padR = 16, padT = 44, padB = 70;
  const innerH = H - padT - padB, innerW = W - padL - padR;
  const y = (v: number) => padT + innerH - ((Math.max(floor, v) - floor) / (ceil - floor)) * innerH;
  const slot = innerW / steps.length, bw = Math.min(72, slot * 0.62);
  const ticks = [1_500_000, 1_700_000, 1_900_000, 2_100_000];
  const compact = (v: number) => fmtMoney(v, { compact: true });
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`Bridge from reported EBITDA of ${compact(reported)} through ${S.addbacks.length} seller add-backs to verified adjusted EBITDA of ${compact(verified)}; the seller claimed ${compact(seller)}. The axis starts at ${compact(floor)}.`}>
        <defs><pattern id="lp-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="var(--chart-graphite)" strokeWidth="1.6" /></pattern></defs>
        {ticks.map((t) => <g key={t}><line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke="var(--hairline)" /><text x={padL - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fontFamily="var(--font-mono)" fill="var(--fg-muted)">{compact(t)}</text></g>)}
        <line x1={padL} x2={W - padR} y1={y(seller)} y2={y(seller)} stroke="var(--chart-graphite)" strokeDasharray="5 4" />
        <text x={padL + 6} y={y(seller) - 6} fontSize="11" fontFamily="var(--font-mono)" fill="var(--fg-muted)">seller&apos;s adjusted EBITDA {compact(seller)}</text>
        {steps.map((s, i) => {
          const x = padL + i * slot + (slot - bw) / 2;
          const isTotal = s.decision === "reported" || s.decision === "verified";
          const top = isTotal ? s.to : Math.max(s.from, s.to), bottom = isTotal ? floor : Math.min(s.from, s.to);
          const h = Math.max(2, y(bottom) - y(top));
          return (
            <g key={s.label}>
              {i > 0 && !isTotal && <line x1={x - (slot - bw) / 2} x2={x} y1={y(s.from)} y2={y(s.from)} stroke="var(--fg-muted)" strokeWidth="1" />}
              <motion.rect x={x} width={bw} rx={2} fill={s.included ? "var(--chart-signal)" : "url(#lp-hatch)"} stroke={s.included ? "none" : "var(--chart-graphite)"} strokeDasharray={s.included ? undefined : "3 2"} initial={{ y: reduced ? y(top) : y(bottom), height: reduced ? h : 0 }} whileInView={{ y: y(top), height: h }} viewport={view} transition={{ duration: 0.55, delay: i * 0.07, ease }} />
              <text x={x + bw / 2} y={y(top) - 8} textAnchor="middle" fontSize="12" fontFamily="var(--font-mono)" fill="var(--fg)">{isTotal ? compact(s.to) : `+${compact(s.amount)}`}</text>
              {isTotal && <text x={x + bw / 2} y={y(floor) - 6} textAnchor="middle" fontSize="10" fontFamily="var(--font-mono)" fill="var(--color-ink-950)" opacity="0.7">from $0</text>}
              <foreignObject x={padL + i * slot} y={H - padB + 8} width={slot} height={padB - 8}><div className="px-1 text-center text-[11px] leading-tight text-fg-muted" style={{ fontFamily: "var(--font-sans)" }}>{s.label}<br /><span className={s.decision === "accepted" || isTotal ? "text-accent" : s.decision === "review_required" ? "text-amber" : "text-graphite"}>{isTotal ? "" : s.decision.replace("_", " ")}</span></div></foreignObject>
            </g>
          );
        })}
        <line x1={padL} x2={W - padR} y1={y(floor)} y2={y(floor)} stroke="var(--fg-muted)" />
        <g transform={`translate(${padL - 2} ${y(floor) + 2})`} aria-hidden><path d="M-3 0 l3 -5 l3 5 M-3 6 l3 -5 l3 5" stroke="var(--fg-muted)" fill="none" strokeWidth="1" /></g>
      </svg>
      <figcaption className="mt-3 text-sm text-fg-muted">The axis starts at {compact(floor)} so each step is legible. Solid bars are accepted and counted. Hatched bars were rejected, sent to review, or found unsupported; they stay visible and out of the total. Every bar cites a statement line or a note.</figcaption>
    </figure>
  );
}

const ROWS = S.sensitivity.rows.map(Number);
const COLS = S.sensitivity.cols.map(Number);

/** Interactive DSCR from the engine's precomputed sensitivity grid (bilinear interpolation). */
export function ScenarioFigure() {
  const [loss, setLoss] = useState(0);
  const [bps, setBps] = useState(0);
  const threshold = Number(S.deal.threshold);
  const dscr = useMemo(() => {
    const cell = (i: number, j: number) => Number(S.sensitivity.cells[i][j].v ?? 0);
    const ri = Math.min(ROWS.length - 2, Math.max(0, ROWS.findIndex((r, i) => loss >= r && loss <= (ROWS[i + 1] ?? Infinity))));
    const cj = Math.min(COLS.length - 2, Math.max(0, COLS.findIndex((c, j) => bps <= c && bps >= (COLS[j + 1] ?? -Infinity))));
    const tr = (loss - ROWS[ri]) / (ROWS[ri + 1] - ROWS[ri]), tc = (bps - COLS[cj]) / (COLS[cj + 1] - COLS[cj]);
    const a = cell(ri, cj) * (1 - tc) + cell(ri, cj + 1) * tc, b = cell(ri + 1, cj) * (1 - tc) + cell(ri + 1, cj + 1) * tc;
    return a * (1 - tr) + b * tr;
  }, [loss, bps]);
  const status = dscr < threshold ? "breach" : dscr < threshold * 1.1 ? "warning" : "supported";
  const max = 2.2;
  const pct = (v: number) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`;
  const points = Math.abs(bps) / 100;
  return (
    <figure className="grid gap-8 md:grid-cols-[1fr_1fr] md:items-center">
      <div className="flex flex-col gap-6">
        <label className="block text-sm"><span className="flex justify-between">Loss of the largest customer <span className="num">{loss}%</span></span><input type="range" min={0} max={100} step={5} value={loss} onChange={(e) => setLoss(Number(e.target.value))} className="mt-2 w-full accent-[var(--chart-signal)]" aria-valuetext={`${loss} percent of the largest customer's revenue lost`} /></label>
        <label className="block text-sm"><span className="flex justify-between">Gross margin lost <span className="num">{points.toFixed(2)} points <span className="text-fg-muted">({bps} bps)</span></span></span><input type="range" min={-400} max={0} step={25} value={bps} onChange={(e) => setBps(Number(e.target.value))} className="mt-2 w-full accent-[var(--chart-signal)]" aria-valuetext={`${points} percentage points of gross margin lost`} /></label>
        <p className="text-sm text-fg-muted">Interpolated from a 5 by 5 grid the engine computed from the base case: {S.deal.rate}% interest over {S.deal.years} years, {fmtMoney(S.deal.ads, { compact: true })} of loan payments a year. Inside the app every point is recomputed exactly.</p>
      </div>
      <Sheet className="p-5">
        <div className="flex items-baseline justify-between gap-3"><span className="text-sm text-fg-muted">Year-one debt coverage (DSCR)</span><span className="inline-flex items-center gap-2 num text-3xl"><StatusGlyph status={status} size={16} />{fmtX(dscr)}</span></div>
        <div className="relative mt-5 h-3 w-full rounded-[3px] bg-ink-700" role="img" aria-label={`DSCR ${fmtX(dscr)} against the lender's ${fmtX(threshold)} minimum`}>
          <div className="absolute inset-y-0 left-0 rounded-[3px] bg-chart-red/25" style={{ width: pct(threshold) }} />
          <motion.div className={`absolute inset-y-0 left-0 rounded-[3px] ${status === "breach" ? "bg-chart-red" : status === "warning" ? "bg-chart-amber" : "bg-chart-signal"}`} animate={{ width: pct(dscr) }} transition={{ duration: 0.4, ease }} />
          <div className="absolute -top-1 h-5 w-px bg-fg" style={{ left: pct(threshold) }} />
        </div>
        <div className="mt-2 flex justify-between font-mono text-[11px] text-fg-muted"><span>0.0x</span><span>lender&apos;s minimum {fmtX(threshold)}</span><span>{max.toFixed(1)}x</span></div>
        <p className="mt-4 text-sm text-fg-muted" aria-live="polite">{status === "breach" ? `Below the lender's ${fmtX(threshold)} minimum: the cash no longer covers the loan payments under these assumptions.` : status === "warning" ? "Within 10% of the lender's minimum. Little room for error." : "Above the lender's minimum with room to spare."}</p>
      </Sheet>
    </figure>
  );
}

/** The report, section by section. */
export function ReportFigure() {
  return (
    <figure className="grid gap-8 md:grid-cols-[1fr_1.2fr] md:items-start">
      <div className="flex flex-col gap-3 text-sm text-fg-muted">
        <p className="inline-flex items-center gap-2 self-start rounded-[var(--radius-2)] border border-hairline px-3 py-1.5 font-medium text-fg"><StatusGlyph status="contradicted" /> Material concerns identified</p>
        <p>One of four outcomes a report can reach. None of them is “buy” or “reject”: the report describes the state of the review, and the committee decides.</p>
        <p>Every material statement carries a citation that opens its source, or the report fails validation.</p>
      </div>
      <Sheet className="p-5">
        <ol className="grid grid-cols-1 gap-y-2 sm:grid-cols-2 sm:gap-x-8" aria-label="Report sections in order">
          {S.report_sections.map((s, i) => (
            <motion.li key={s} initial={{ opacity: 0, y: 6 }} whileInView={{ opacity: 1, y: 0 }} viewport={view} transition={{ duration: 0.35, delay: i * 0.04, ease }} className="flex items-center gap-3 border-b border-hairline py-1.5 text-sm last:border-b-0 sm:[&:nth-last-child(2)]:border-b-0">
              <span className="num w-5 text-xs text-fg-muted" aria-hidden>{i + 1}</span>
              <span>{s}</span>
            </motion.li>
          ))}
        </ol>
      </Sheet>
      <figcaption className="sr-only">The {S.report_sections.length} sections of the red-team report, in order.</figcaption>
    </figure>
  );
}
