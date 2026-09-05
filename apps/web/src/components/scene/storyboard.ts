/** Storyboard: progress p in [0,1] → per-entity targets. Ten stages of ~0.1 each. See docs/design/3d-evidence-core.md. */

export const STAGES = [
  { key: "enter", caption: "Deal documents enter the review", start: 0.0 },
  { key: "separate", caption: "Claims and values separate from the pages", start: 0.1 },
  { key: "flow", caption: "Evidence flows into the analysis core", start: 0.2 },
  { key: "connect", caption: "Claims connect to their sources", start: 0.3 },
  { key: "stabilize", caption: "Supported claims stabilize", start: 0.4 },
  { key: "contradict", caption: "Contradictions pulse against primary evidence", start: 0.5 },
  { key: "dissolve", caption: "Unsupported claims lose their connections", start: 0.6 },
  { key: "model", caption: "Verified metrics reorganize into a financial model", start: 0.68 },
  { key: "downside", caption: "A downside scenario breaches the covenant", start: 0.8 },
  { key: "report", caption: "Claims, metrics, risks, and citations assemble into a report", start: 0.9 },
] as const;

export type Status = "supported" | "contradicted" | "unsupported" | "review";

export const NODES: Array<{ id: string; status: Status; label: string; doc: number; value: string }> = [
  { id: "rev", status: "supported", label: "FY2024 revenue $12.95M", doc: 0, value: "supported by Income Statement!D4" },
  { id: "gm", status: "supported", label: "Gross margin 35.0%", doc: 0, value: "recomputed 35.0%" },
  { id: "growth", status: "contradicted", label: "18% annual growth", doc: 0, value: "CAGR is 11.6%" },
  { id: "conc", status: "contradicted", label: "No customer above 10%", doc: 3, value: "Apex is 22.0%" },
  { id: "ebitda", status: "contradicted", label: "Adjusted EBITDA $2.10M", doc: 1, value: "verified $1.81M" },
  { id: "rec", status: "contradicted", label: "85% recurring revenue", doc: 3, value: "68.0% contract-supported" },
  { id: "rate", status: "supported", label: "8.00% fixed, 10-year amortization", doc: 4, value: "matches the model" },
  { id: "dscr", status: "supported", label: "Minimum DSCR 1.25x", doc: 4, value: "matches deal terms" },
  { id: "churn", status: "unsupported", label: "Churn below 5%", doc: 0, value: "no churn data" },
  { id: "term", status: "review", label: "Apex term through 2027", doc: 5, value: "contract ends 2026; 60-day termination" },
];

export const DOC_LABELS = ["CIM", "Model", "Statements", "Customers", "Term sheet", "Contract"];

/** Smoothstep between two progress values. */
export function ramp(p: number, a: number, b: number): number {
  const t = Math.max(0, Math.min(1, (p - a) / (b - a)));
  return t * t * (3 - 2 * t);
}

export function stageIndex(p: number): number {
  let i = 0;
  for (let k = 0; k < STAGES.length; k++) if (p >= STAGES[k].start) i = k;
  return i;
}
