/** Number formatting: tabular, explicit units, signed when asked. */
const money0 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const int0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export type Num = string | number | null | undefined;

export function toNumber(v: Num): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

export function fmtMoney(v: Num, opts: { compact?: boolean; signed?: boolean } = {}): string {
  const n = toNumber(v);
  if (n === null) return "n/a";
  const sign = opts.signed && n > 0 ? "+" : "";
  if (opts.compact) {
    const abs = Math.abs(n);
    if (abs >= 1_000_000) return `${sign}${n < 0 ? "-" : ""}$${(abs / 1_000_000).toFixed(2)}M`;
    if (abs >= 1_000) return `${sign}${n < 0 ? "-" : ""}$${(abs / 1_000).toFixed(0)}K`;
  }
  return sign + money0.format(n);
}

export function fmtInt(v: Num): string {
  const n = toNumber(v);
  return n === null ? "n/a" : int0.format(n);
}

export function fmtPct(v: Num, digits = 1, signed = false): string {
  const n = toNumber(v);
  if (n === null) return "n/a";
  return `${signed && n > 0 ? "+" : ""}${n.toFixed(digits)}%`;
}

export function fmtX(v: Num, digits = 2): string {
  const n = toNumber(v);
  return n === null ? "n/a" : `${n.toFixed(digits)}x`;
}

export function fmtValue(v: Num, unit: string | null | undefined): string {
  switch (unit) {
    case "usd":
      return fmtMoney(v);
    case "pct":
      return fmtPct(v);
    case "multiple":
      return fmtX(v);
    case "years": {
      const n = toNumber(v);
      return n === null ? "n/a" : `${n} yr`;
    }
    case "count":
      return fmtInt(v);
    default:
      return v === null || v === undefined ? "n/a" : String(v);
  }
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  const d = new Date(iso);
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function shortId(id: string | null | undefined): string {
  return id ? id.slice(0, 8) : "";
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

/** Locator → "CIM p.3 ¶2", "Income Statement!D4", "row 14" */
export function fmtLocator(loc: Record<string, unknown> | null | undefined, kind?: string): string {
  if (!loc) return "";
  if (loc.aggregate) return `aggregate (${String(loc.aggregate).replace(/_/g, " ")})`;
  if (loc.page) return `p.${loc.page}${loc.paragraph ? ` ¶${loc.paragraph}` : ""}`;
  if (loc.sheet) return `${loc.sheet}!${loc.row ?? ""}`;
  if (loc.row) return `row ${loc.row}`;
  return kind ?? "";
}
