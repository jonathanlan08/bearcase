"use client";

import { useId, useState } from "react";
import { fmtMoney, fmtX, toNumber } from "@/lib/format";
import { StatusGlyph } from "@/components/domain/status";
import type { WaterfallStep, Sensitivity } from "@/lib/api";

/* Color roles (validated with the dataviz palette script): signal = verified/accepted, graphite = seller/rejected,
   amber = review, red = breach. Every mark also carries a label, glyph, or pattern. */
const FILL: Record<string, string> = { accepted: "var(--chart-signal)", reported: "var(--chart-graphite)", verified: "var(--chart-signal)", rejected: "var(--chart-graphite)", review_required: "var(--chart-amber)", unsupported: "var(--chart-graphite)", pending: "var(--chart-graphite)" };

export function AddbackWaterfall({ steps, sellerTotal }: { steps: WaterfallStep[]; sellerTotal?: string | null }) {
  const pid = useId();
  const [hover, setHover] = useState<number | null>(null);
  if (!steps.length) return null;
  const totals = steps.map((s) => Number(s.running_total));
  const seller = toNumber(sellerTotal);
  const lo = Math.min(...totals);
  const hi = Math.max(...totals, ...steps.filter((s) => s.decision !== "reported" && s.decision !== "verified").map((s) => Number(s.running_total) + Math.abs(Number(s.amount))), seller ?? 0);
  const floorRaw = lo - (hi - lo) * 0.35;
  const floor = Math.max(0, Math.floor(floorRaw / 100_000) * 100_000);
  const ceil = Math.ceil((hi * 1.04) / 100_000) * 100_000;
  const W = 760, H = 320, padL = 64, padR = 16, padT = 40, padB = 68;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const y = (v: number) => padT + innerH - ((Math.max(floor, v) - floor) / (ceil - floor || 1)) * innerH;
  const slot = innerW / steps.length;
  const bw = Math.min(56, slot * 0.62);
  const tickCount = 4;
  const ticks = Array.from({ length: tickCount + 1 }, (_, i) => floor + ((ceil - floor) * i) / tickCount);
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`Add-back bridge from reported EBITDA to verified adjusted EBITDA; axis starts at ${fmtMoney(floor, { compact: true })}`} onMouseLeave={() => setHover(null)}>
        <defs>
          <pattern id={`${pid}-hatch`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="var(--chart-graphite)" strokeWidth="1.5" /></pattern>
        </defs>
        {ticks.map((t) => <g key={t}><line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke="var(--hairline)" strokeWidth="1" /><text x={padL - 6} y={y(t) + 4} textAnchor="end" className="fill-fg-muted" fontSize="10" fontFamily="var(--font-mono)">{fmtMoney(t, { compact: true })}</text></g>)}
        {seller !== null && seller > floor && <g><line x1={padL} x2={W - padR} y1={y(seller)} y2={y(seller)} stroke="var(--chart-graphite)" strokeWidth="1" strokeDasharray="4 3" /><text x={padL + 6} y={y(seller) - 5} fontSize="10" fontFamily="var(--font-mono)" className="fill-fg-muted">seller {fmtMoney(seller, { compact: true })}</text></g>}
        {steps.map((s, i) => {
          const amt = Number(s.amount);
          const isTotal = s.decision === "reported" || s.decision === "verified";
          const prev = i === 0 ? floor : Number(steps[i - 1].running_total);
          const top = isTotal ? Number(s.running_total) : s.included ? Math.max(prev, prev + amt) : prev + Math.abs(amt);
          const bottom = isTotal ? floor : s.included ? Math.min(prev, prev + amt) : prev;
          const x = padL + i * slot + (slot - bw) / 2;
          const fill = s.included ? FILL[s.decision] ?? "var(--chart-signal)" : `url(#${pid}-hatch)`;
          const active = hover === i;
          return (
            <g key={i} onMouseEnter={() => setHover(i)} onFocus={() => setHover(i)} tabIndex={0} role="listitem" aria-label={`${s.label}: ${fmtMoney(amt, { signed: !isTotal })}${s.included ? "" : `, ${s.decision.replace("_", " ")}, excluded`}; running total ${fmtMoney(s.running_total)}`}>
              <rect x={x - 6} y={padT} width={bw + 12} height={innerH} fill="transparent" />
              {i > 0 && !isTotal && <line x1={x - (slot - bw) / 2} x2={x} y1={y(prev)} y2={y(prev)} stroke="var(--fg-muted)" strokeWidth="1" />}
              <rect x={x} y={y(top)} width={bw} height={Math.max(2, y(bottom) - y(top))} fill={fill} rx={2} stroke={active ? "var(--fg)" : s.included ? "none" : "var(--chart-graphite)"} strokeWidth={active ? 1.5 : 1} strokeDasharray={s.included ? undefined : "3 2"} />
              <text x={x + bw / 2} y={y(top) - 6} textAnchor="middle" fontSize="11" fontFamily="var(--font-mono)" className="fill-fg">{isTotal ? fmtMoney(s.running_total, { compact: true }) : `${amt >= 0 ? "+" : "−"}${fmtMoney(Math.abs(amt), { compact: true })}`}</text>
              <foreignObject x={padL + i * slot} y={H - padB + 6} width={slot} height={padB - 6}><div className="px-0.5 text-center text-[10px] leading-tight text-fg-muted" style={{ fontFamily: "var(--font-sans)" }}>{s.label.replace(/\s*\(.*\)/, "")}</div></foreignObject>
            </g>
          );
        })}
        <line x1={padL} x2={W - padR} y1={y(floor)} y2={y(floor)} stroke="var(--fg-muted)" strokeWidth="1" />
      </svg>
      <figcaption className="mt-2 flex flex-wrap gap-4 text-xs text-fg-muted">
        <span>Axis starts at {fmtMoney(floor, { compact: true })}</span>
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-3 rounded-[2px] bg-chart-signal" />Accepted or total</span>
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-3 rounded-[2px] border border-dashed border-graphite diag-hatch text-graphite" />Rejected, review, or unsupported (excluded)</span>
        {hover !== null && <span className="ml-auto num text-fg">{steps[hover].label}: {fmtMoney(steps[hover].amount, { signed: true })}, running {fmtMoney(steps[hover].running_total)}</span>}
      </figcaption>
    </figure>
  );
}

export function DscrGauge({ value, threshold, label }: { value: string | null; threshold: string | null; label?: string }) {
  const v = toNumber(value);
  const t = toNumber(threshold);
  const max = Math.max(2, (t ?? 1.25) * 1.6, (v ?? 0) * 1.1);
  const W = 260, H = 64;
  const x = (n: number) => 8 + (Math.max(0, Math.min(max, n)) / max) * (W - 16);
  const status = v === null ? "unsupported" : t !== null && v < t ? "breach" : t !== null && v < t * 1.1 ? "warning" : "supported";
  return (
    <figure className="w-full max-w-[260px]">
      <div className="flex items-baseline justify-between"><span className="text-sm text-fg-muted">{label ?? "DSCR, year 1"}</span><span className="inline-flex items-center gap-1.5 num text-xl"><StatusGlyph status={status} size={14} />{fmtX(v)}</span></div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-1 w-full" role="img" aria-label={`DSCR ${fmtX(v)} versus covenant threshold ${fmtX(t)}`}>
        <rect x={8} y={22} width={W - 16} height={10} rx={2} fill="var(--bg-muted)" />
        {t !== null && <rect x={8} y={22} width={x(t) - 8} height={10} rx={2} fill="var(--chart-red)" opacity={0.18} />}
        {v !== null && <rect x={8} y={22} width={x(v) - 8} height={10} rx={2} fill={status === "breach" ? "var(--chart-red)" : status === "warning" ? "var(--chart-amber)" : "var(--chart-signal)"} />}
        {t !== null && <g><line x1={x(t)} x2={x(t)} y1={14} y2={40} stroke="var(--fg)" strokeWidth="1.5" /><text x={x(t)} y={52} textAnchor="middle" fontSize="10" fontFamily="var(--font-mono)" className="fill-fg-muted">threshold {fmtX(t)}</text></g>}
        {v !== null && <polygon points={`${x(v)},18 ${x(v) - 4},12 ${x(v) + 4},12`} fill="var(--fg)" />}
        <text x={8} y={62} fontSize="9" fontFamily="var(--font-mono)" className="fill-fg-muted">0.0x</text>
        <text x={W - 8} y={62} textAnchor="end" fontSize="9" fontFamily="var(--font-mono)" className="fill-fg-muted">{max.toFixed(1)}x</text>
      </svg>
    </figure>
  );
}

export function SensitivityGrid({ grid, rowLabel, colLabel, fmt }: { grid: Sensitivity; rowLabel: string; colLabel: string; fmt: (v: string | null) => string }) {
  const [table, setTable] = useState(false);
  const t = toNumber(grid.threshold);
  const nums = grid.cells.flat().map((c) => toNumber(c.value)).filter((n): n is number => n !== null);
  const lo = Math.min(...nums), hi = Math.max(...nums);
  const tone = (n: number | null, breach: boolean) => {
    if (n === null) return "var(--bg-muted)";
    if (breach) { const k = t ? Math.max(0, Math.min(1, (t - n) / t)) : 0.5; return `color-mix(in oklab, var(--chart-red) ${25 + k * 45}%, var(--bg-raised))`; }
    const k = hi === lo ? 0.5 : (n - lo) / (hi - lo);
    return `color-mix(in oklab, var(--chart-signal) ${12 + k * 40}%, var(--bg-raised))`;
  };
  return (
    <figure>
      <div className="mb-2 flex items-center justify-between text-xs text-fg-muted">
        <span>Rows: {rowLabel} · Columns: {colLabel} · cells show year-1 {grid.output.toUpperCase()}; ◆ marks a covenant breach</span>
        <button type="button" className="text-accent hover:underline" onClick={() => setTable((s) => !s)} aria-pressed={table}>{table ? "Show grid" : "Show as table"}</button>
      </div>
      <div className="scroll-x">
        <table className="w-full border-collapse text-xs" aria-label={`Sensitivity of ${grid.output} to ${rowLabel} and ${colLabel}`}>
          <thead><tr><th className="p-1 text-left font-medium text-fg-muted">{rowLabel} ↓ / {colLabel} →</th>{grid.col_values.map((c) => <th key={c} className="num p-1 text-right font-medium text-fg-muted">{c}</th>)}</tr></thead>
          <tbody>
            {grid.cells.map((row, i) => (
              <tr key={i}>
                <th scope="row" className="num p-1 text-left font-medium text-fg-muted">{grid.row_values[i]}</th>
                {row.map((cell, j) => { const n = toNumber(cell.value); return (
                  <td key={j} className="p-0.5">
                    <div className="flex h-9 items-center justify-end gap-1 rounded-[2px] px-2 num" style={{ background: table ? "transparent" : tone(n, cell.breach) }} title={`${rowLabel} ${cell.row}, ${colLabel} ${cell.col}: ${fmt(cell.value)}${cell.breach ? " (breach)" : ""}`}>
                      {cell.breach && <StatusGlyph status="breach" size={10} />}{fmt(cell.value)}
                    </div>
                  </td>
                ); })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}

export function CompareBars({ rows, max }: { rows: Array<{ label: string; value: string | null; tone: "seller" | "verified" | "reported"; note?: string }>; max?: number }) {
  const m = max ?? Math.max(...rows.map((r) => Number(r.value ?? 0)), 1);
  return (
    <ul className="flex flex-col gap-2" aria-label="Comparison">
      {rows.map((r) => (
        <li key={r.label} className="text-sm">
          <div className="flex justify-between"><span>{r.label}</span><span className="num">{fmtMoney(r.value)}</span></div>
          <div className="mt-1 h-2.5 w-full rounded-[2px] bg-bg-muted"><div className={`h-2.5 rounded-[2px] ${r.tone === "verified" ? "bg-accent" : r.tone === "seller" ? "border border-graphite diag-hatch text-graphite" : "bg-graphite"}`} style={{ width: `${(Number(r.value ?? 0) / m) * 100}%` }} /></div>
          {r.note && <p className="mt-0.5 text-xs text-fg-muted">{r.note}</p>}
        </li>
      ))}
    </ul>
  );
}
