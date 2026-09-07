/** Storyboard for the Evidence Core hero.
 *
 *  Two clocks drive the scene. Scroll fraction `s ∈ [0,1]` is what the reader controls; storyboard progress `p ∈ [0,1]`
 *  is what every entity animates against. Ten fine-grained STAGES (each ~0.1 of `p`) own the ramps inside
 *  `evidence-core.tsx`; three CHAPTERS (one scroll each) are the readable story and own the HTML captions.
 *  `storyProgress` maps `s` onto `p` piecewise-linearly so each chapter gets exactly one third of the scroll.
 *  See docs/design/3d-evidence-core.md. */

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

/** The three readable states of the hero. `p` is the storyboard progress where the chapter begins; the next chapter's
 *  `p` (or 1) is where it ends. Titles are the on-screen captions; details are the one-line plain-language explanation. */
export const CHAPTERS = [
  { key: "claim", title: "Seller says 18% growth", detail: "The memo claims 18% annual growth. BearCase quotes the claim and links it to the page it came from.", p: 0 },
  { key: "evidence", title: "The statements show 11.6%", detail: "Recomputed from the income statement, growth is 11.6% a year. The claim is marked contradicted.", p: 0.5 },
  { key: "open", title: "Open the evidence", detail: "Every figure links to the cell it came from, then feeds the model, the downside case, and the report.", p: 0.68 },
] as const;

export type Status = "supported" | "contradicted" | "unsupported" | "review";

/** Claim nodes. `hero` marks the claim the captions talk about; it renders larger so the eye can follow it. */
export const NODES: Array<{ id: string; status: Status; label: string; doc: number; value: string; hero?: boolean }> = [
  { id: "rev", status: "supported", label: "FY2024 revenue $12.95M", doc: 0, value: "supported by Income Statement!D4" },
  { id: "gm", status: "supported", label: "Gross margin 35.0%", doc: 0, value: "recomputed 35.0%" },
  { id: "growth", status: "contradicted", label: "18% annual growth", doc: 0, value: "statements show 11.6% a year", hero: true },
  { id: "conc", status: "contradicted", label: "No customer above 10%", doc: 3, value: "Apex is 22.0%" },
  { id: "ebitda", status: "contradicted", label: "Adjusted EBITDA $2.10M", doc: 1, value: "verified $1.81M" },
  { id: "rec", status: "contradicted", label: "85% recurring revenue", doc: 3, value: "68.0% contract-supported" },
  { id: "rate", status: "supported", label: "8.00% fixed, 10-year amortization", doc: 4, value: "matches the model" },
  { id: "dscr", status: "supported", label: "Minimum DSCR 1.25x", doc: 4, value: "matches deal terms" },
  { id: "churn", status: "unsupported", label: "Churn below 5%", doc: 0, value: "no churn data" },
  { id: "term", status: "review", label: "Apex term through 2027", doc: 5, value: "contract ends 2026; 60-day termination" },
];

export const DOC_LABELS = ["CIM", "Model", "Statements", "Customers", "Term sheet", "Contract"];

function clamp01(x: number): number {
  return Math.max(0, Math.min(1, x));
}

/** Smoothstep between two progress values. */
export function ramp(p: number, a: number, b: number): number {
  const t = clamp01((p - a) / (b - a));
  return t * t * (3 - 2 * t);
}

export function stageIndex(p: number): number {
  let i = 0;
  for (let k = 0; k < STAGES.length; k++) if (p >= STAGES[k].start) i = k;
  return i;
}

/** Chapter for a scroll fraction: each chapter owns one third of the scroll range. */
export function chapterIndex(s: number): number {
  return Math.min(CHAPTERS.length - 1, Math.floor(clamp01(s) * CHAPTERS.length));
}

/** Scroll fraction → storyboard progress. Piecewise-linear so that chapter i spans scroll [i/3, (i+1)/3] and storyboard
 *  [CHAPTERS[i].p, CHAPTERS[i+1].p]. Continuous and monotonic; `storyProgress(0) = 0`, `storyProgress(1) = 1`. */
export function storyProgress(s: number): number {
  const c = clamp01(s);
  const n = CHAPTERS.length;
  const i = Math.min(n - 1, Math.floor(c * n));
  const local = c * n - i;
  const a = CHAPTERS[i].p;
  const b = i + 1 < n ? CHAPTERS[i + 1].p : 1;
  return a + (b - a) * local;
}

/** How far a claim's verdict has been revealed at progress `p` (0 = still a neutral claim, 1 = full status colour).
 *  Chapter 1 (p < 0.5) shows claims as claims; chapter 2 reveals what the evidence says, supported first, then the
 *  contradictions pulse, then unsupported claims fade and review items turn amber. Everything is revealed by p = 0.68. */
export function statusReveal(status: Status, p: number): number {
  switch (status) {
    case "supported": return ramp(p, 0.5, 0.56);
    case "contradicted": return ramp(p, 0.52, 0.6);
    case "unsupported": return ramp(p, 0.6, 0.66);
    case "review": return ramp(p, 0.6, 0.68);
  }
}

/** The part of the hero viewport that is free for the composition, as fractions of the sticky box (top-left origin).
 *  Side-by-side layouts leave everything right of the copy; stacked layouts leave the band between the captions and the copy.
 *  The scene frames the core inside it so the headline and actions never sit over the busy centre. */
export interface FreeRegion { left: number; right: number; top: number; bottom: number }
export const FULL_REGION: FreeRegion = { left: 0, right: 1, top: 0, bottom: 1 };

/** Tiny external store shared by the hero and the scene. The hero writes the scroll fraction from a passive scroll listener
 *  and the free region from a resize measurement; the scene reads both every frame without re-rendering React; the captions
 *  subscribe to the scroll fraction through `useSyncExternalStore`. The region never notifies (nothing in React depends on it). */
export interface SceneStore {
  get(): number;
  set(v: number): void;
  subscribe(cb: () => void): () => void;
  region: FreeRegion;
  setRegion(r: FreeRegion): void;
}

export function createSceneStore(): SceneStore {
  let value = 0;
  const subs = new Set<() => void>();
  const store: SceneStore = {
    get: () => value,
    set: (v) => {
      const next = clamp01(v);
      if (next === value) return;
      value = next;
      subs.forEach((cb) => cb());
    },
    subscribe: (cb) => {
      subs.add(cb);
      return () => { subs.delete(cb); };
    },
    region: FULL_REGION,
    setRegion: (r) => {
      const left = clamp01(r.left), top = clamp01(r.top);
      store.region = { left, right: Math.max(left + 0.2, clamp01(r.right)), top, bottom: Math.max(top + 0.2, clamp01(r.bottom)) };
    },
  };
  return store;
}
