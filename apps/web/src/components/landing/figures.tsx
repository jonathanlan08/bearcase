"use client";

import { motion } from "motion/react";
import { useMediaQuery } from "@/lib/hooks";
import { useMemo, useState } from "react";
import snapshot from "@/content/northstar-snapshot.json";
import { StatusChip, StatusGlyph } from "@/components/domain/status";
import { fmtMoney, fmtX } from "@/lib/format";

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
        <p className="text-xs text-fg-muted">From the CIM, page 3</p>
        <p className="mt-2 text-lg leading-snug">“{S.claims[0].text}”</p>
        <div className="mt-4"><StatusChip status="contradicted" /></div>
      </Sheet>
      <svg width="88" height="40" viewBox="0 0 88 40" className="hidden justify-self-center md:block" aria-hidden>
        <motion.path d="M4 20 H84" stroke="var(--chart-red)" strokeWidth="1.25" fill="none" initial={{ pathLength: reduced ? 1 : 0 }} whileInView={{ pathLength: 1 }} viewport={view} transition={{ duration: 0.9, ease }} />
        <rect x="0" y="16" width="8" height="8" fill="var(--chart-red)" />
        <motion.circle cx="84" cy="20" r="3" fill="var(--color-ink-900)" stroke="var(--chart-red)" strokeWidth="1.25" initial={{ opacity: reduced ? 1 : 0 }} whileInView={{ opacity: 1 }} viewport={view} transition={{ delay: 0.8 }} />
      </svg>
      <Sheet className="p-5">
        <p className="text-xs text-fg-muted">From the financial statements, Income Statement rows B4 to D4</p>
        <table className="mt-2 w-full text-sm"><thead><tr className="text-left text-xs text-fg-muted">{years.map((y) => <th key={y} className="py-1 font-medium">{y}</th>)}</tr></thead><tbody><tr>{years.map((y) => <td key={y} className="num py-1 pr-3">{fmtMoney(S.revenue[y as keyof typeof S.revenue], { compact: true })}</td>)}</tr></tbody></table>
        <p className="mt-3 text-sm">Recomputed growth <span className="num font-medium text-accent">{S.cagr_pct}% a year</span>, against the claimed <span className="num font-medium text-red">{S.cim_growth_pct}%</span>.</p>
      </Sheet>
      <figcaption className="sr-only">A claim from the CIM is linked by a hairline to the spreadsheet cells that contradict it.</figcaption>
    </figure>
  );
}

/** Two sources, one contradiction; hovering the chip highlights both. */
export function ContradictionFigure() {
  const [hot, setHot] = useState(false);
  const hl = hot ? "border-chart-red" : "border-hairline";
  return (
    <figure>
      <div className="grid gap-4 md:grid-cols-2">
        <div className={`rounded-[var(--radius-3)] border bg-ink-900/80 p-5 transition-colors duration-150 ${hl}`}>
          <p className="text-xs text-fg-muted">CIM, page 5</p>
          <p className="mt-2 text-lg leading-snug">“{S.claims[1].text}”</p>
        </div>
        <div className={`rounded-[var(--radius-3)] border bg-ink-900/80 p-5 transition-colors duration-150 ${hl}`}>
          <p className="text-xs text-fg-muted">Customer revenue file, row 2 and the customer totals</p>
          <p className="mt-2 text-lg leading-snug">{S.top_customer.name}: <span className="num">{fmtMoney(S.top_customer.revenue)}</span> of <span className="num">{fmtMoney(S.revenue.FY2024)}</span></p>
          <p className="num mt-1 text-sm text-fg-muted">{S.top_customer.pct}% of FY2024 revenue</p>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-4">
        <button type="button" onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)} onFocus={() => setHot(true)} onBlur={() => setHot(false)} className="inline-flex items-center gap-2 rounded-[var(--radius-2)] border border-hairline px-3 py-1.5 text-sm hover:border-chart-red" aria-describedby="contra-desc">
          <StatusGlyph status="contradicted" /> Contradicted
        </button>
        <p id="contra-desc" className="max-w-xl text-sm text-fg-muted">Hover the status to see both sources light up. Neither document is trusted on its own; both are cited, and a reviewer decides.</p>
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
  const floor = 1_500_000, ceil = 2_200_000;
  const W = 900, H = 340, padL = 64, padR = 16, padT = 44, padB = 70;
  const innerH = H - padT - padB, innerW = W - padL - padR;
  const y = (v: number) => padT + innerH - ((Math.max(floor, v) - floor) / (ceil - floor)) * innerH;
  const slot = innerW / steps.length, bw = Math.min(72, slot * 0.62);
  const ticks = [1_500_000, 1_700_000, 1_900_000, 2_100_000];
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Bridge from reported EBITDA of $1.64M through five seller add-backs to verified adjusted EBITDA of $1.81M; the seller claimed $2.10M. Axis starts at $1.5M.">
        <defs><pattern id="lp-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="var(--chart-graphite)" strokeWidth="1.6" /></pattern></defs>
        {ticks.map((t) => <g key={t}><line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke="var(--hairline)" /><text x={padL - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fontFamily="var(--font-mono)" fill="var(--fg-muted)">{fmtMoney(t, { compact: true })}</text></g>)}
        <line x1={padL} x2={W - padR} y1={y(seller)} y2={y(seller)} stroke="var(--chart-graphite)" strokeDasharray="5 4" />
        <text x={padL + 6} y={y(seller) - 6} fontSize="11" fontFamily="var(--font-mono)" fill="var(--fg-muted)">seller&apos;s adjusted EBITDA {fmtMoney(seller, { compact: true })}</text>
        {steps.map((s, i) => {
          const x = padL + i * slot + (slot - bw) / 2;
          const isTotal = s.decision === "reported" || s.decision === "verified";
          const top = isTotal ? s.to : Math.max(s.from, s.to), bottom = isTotal ? floor : Math.min(s.from, s.to);
          const h = Math.max(2, y(bottom) - y(top));
          return (
            <g key={s.label}>
              {i > 0 && !isTotal && <line x1={x - (slot - bw) / 2} x2={x} y1={y(s.from)} y2={y(s.from)} stroke="var(--fg-muted)" strokeWidth="1" />}
              <motion.rect x={x} width={bw} rx={2} fill={s.included ? "var(--chart-signal)" : "url(#lp-hatch)"} stroke={s.included ? "none" : "var(--chart-graphite)"} strokeDasharray={s.included ? undefined : "3 2"} initial={{ y: reduced ? y(top) : y(bottom), height: reduced ? h : 0 }} whileInView={{ y: y(top), height: h }} viewport={view} transition={{ duration: 0.55, delay: i * 0.07, ease }} />
              <text x={x + bw / 2} y={y(top) - 8} textAnchor="middle" fontSize="12" fontFamily="var(--font-mono)" fill="var(--fg)">{isTotal ? fmtMoney(s.to, { compact: true }) : `+${fmtMoney(s.amount, { compact: true })}`}</text>
              {isTotal && <text x={x + bw / 2} y={y(floor) - 6} textAnchor="middle" fontSize="10" fontFamily="var(--font-mono)" fill="var(--color-ink-950)" opacity="0.7">from $0</text>}
              <foreignObject x={padL + i * slot} y={H - padB + 8} width={slot} height={padB - 8}><div className="px-1 text-center text-[11px] leading-tight text-fg-muted" style={{ fontFamily: "var(--font-sans)" }}>{s.label}<br /><span className={s.decision === "accepted" || isTotal ? "text-accent" : s.decision === "review_required" ? "text-amber" : "text-graphite"}>{isTotal ? "" : s.decision.replace("_", " ")}</span></div></foreignObject>
            </g>
          );
        })}
        <line x1={padL} x2={W - padR} y1={y(floor)} y2={y(floor)} stroke="var(--fg-muted)" />
        <g transform={`translate(${padL - 2} ${y(floor) + 2})`} aria-hidden><path d="M-3 0 l3 -5 l3 5 M-3 6 l3 -5 l3 5" stroke="var(--fg-muted)" fill="none" strokeWidth="1" /></g>
      </svg>
      <figcaption className="mt-3 text-sm text-fg-muted">The axis starts at $1.5M so each step is legible. Solid bars are accepted and counted. Hatched bars were rejected, sent to review, or found unsupported; they stay visible and out of the total. Every bar cites a statement line or a note.</figcaption>
    </figure>
  );
}

/** Interactive DSCR from the engine's precomputed sensitivity grid (bilinear interpolation). */
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
    <figure className="grid gap-8 md:grid-cols-[1fr_1fr] md:items-center">
      <div className="flex flex-col gap-6">
        <label className="block text-sm"><span className="flex justify-between">Loss of the largest customer <span className="num">{loss}%</span></span><input type="range" min={0} max={100} step={5} value={loss} onChange={(e) => setLoss(Number(e.target.value))} className="mt-2 w-full accent-[var(--chart-signal)]" aria-valuetext={`${loss} percent`} /></label>
        <label className="block text-sm"><span className="flex justify-between">Gross-margin compression <span className="num">{bps} bps</span></span><input type="range" min={-400} max={0} step={25} value={bps} onChange={(e) => setBps(Number(e.target.value))} className="mt-2 w-full accent-[var(--chart-signal)]" aria-valuetext={`${bps} basis points`} /></label>
        <p className="text-sm text-fg-muted">Interpolated from a 5 by 5 grid the engine computed from the base case: {S.deal.rate}% over {S.deal.years} years, {fmtMoney(S.deal.ads, { compact: true })} of annual debt service. Inside the app every point is recomputed exactly.</p>
      </div>
      <Sheet className="p-5">
        <div className="flex items-baseline justify-between"><span className="text-sm text-fg-muted">Year-one debt service coverage</span><span className="inline-flex items-center gap-2 num text-3xl"><StatusGlyph status={status} size={16} />{fmtX(dscr)}</span></div>
        <div className="relative mt-5 h-3 w-full rounded-[3px] bg-ink-700" role="img" aria-label={`DSCR ${fmtX(dscr)} against a ${fmtX(threshold)} covenant`}>
          <div className="absolute inset-y-0 left-0 rounded-[3px] bg-chart-red/25" style={{ width: pct(threshold) }} />
          <motion.div className={`absolute inset-y-0 left-0 rounded-[3px] ${status === "breach" ? "bg-chart-red" : status === "warning" ? "bg-chart-amber" : "bg-chart-signal"}`} animate={{ width: pct(dscr) }} transition={{ duration: 0.4, ease }} />
          <div className="absolute -top-1 h-5 w-px bg-fg" style={{ left: pct(threshold) }} />
        </div>
        <div className="mt-2 flex justify-between font-mono text-[11px] text-fg-muted"><span>0.0x</span><span>covenant {fmtX(threshold)}</span><span>{max.toFixed(1)}x</span></div>
        <p className="mt-4 text-sm text-fg-muted" aria-live="polite">{status === "breach" ? "Below the lender's minimum: cash flow no longer covers debt service under these assumptions." : status === "warning" ? "Inside 10% of the covenant. Little room for error." : "Above the covenant with headroom."}</p>
      </Sheet>
    </figure>
  );
}

/** The report, section by section, with its citation counts. */
export function ReportFigure() {
  return (
    <figure className="grid gap-8 md:grid-cols-[1fr_1.2fr] md:items-start">
      <div className="flex flex-col gap-3 text-sm text-fg-muted">
        <p className="inline-flex items-center gap-2 self-start rounded-[var(--radius-2)] border border-hairline px-3 py-1.5 font-medium text-fg"><StatusGlyph status="contradicted" /> Material concerns identified</p>
        <p>Four outcomes are possible. None of them is “buy” or “reject”. The tool describes the state of the review; the committee decides.</p>
        <p className="num">36 of 36 material statements cited.</p>
      </div>
      <Sheet className="p-5">
        <ol className="grid grid-cols-1 gap-y-2 sm:grid-cols-2 sm:gap-x-8">
          {S.report_sections.map((s, i) => (
            <motion.li key={s} initial={{ opacity: 0, y: 6 }} whileInView={{ opacity: 1, y: 0 }} viewport={view} transition={{ duration: 0.35, delay: i * 0.04, ease }} className="flex items-center justify-between gap-3 border-b border-hairline py-1.5 text-sm last:border-b-0 sm:[&:nth-last-child(2)]:border-b-0">
              <span>{s}</span>
              <span className="num text-xs text-fg-muted">{[3, 5, 8, 6, 3, 5, 3, 7, 4, 3, 2, 12][i] ?? 2} cites</span>
            </motion.li>
          ))}
        </ol>
      </Sheet>
    </figure>
  );
}
