/**
 * The four kinds of statement a reader meets in BearCase, and the mark each one carries. Used in the report header,
 * the chat empty state, and the trust page, so the same words explain the same marks everywhere.
 *
 * A source fact and a calculation carry the citation marks the product already shows (`E:…` on an evidence chip,
 * `M:…` on a metric chip). An assumption and an AI interpretation carry no citation: their marks are dashed, so the
 * difference is a shape as well as a letter, and the label always sits beside the mark.
 */

export type StatementKindKey = "source" | "calculation" | "assumption" | "interpretation";

export interface StatementKind { key: StatementKindKey; mark: string; label: string; short: string; detail: string }

export const STATEMENT_KINDS: ReadonlyArray<StatementKind> = [
  { key: "source", mark: "E", label: "Source fact", short: "a passage in a document you uploaded", detail: "A page, a sheet row, or a CSV row in a document the seller gave you. The chip opens the document at that spot. The passage is quoted as it was written, so it can still be wrong; a source fact tells you where to look, not that the seller is right." },
  { key: "calculation", mark: "M", label: "Calculation", short: "a number computed by code from source facts", detail: "A number BearCase's engine computed from source facts with a stored formula and input snapshot. The model never produces one. It is only as good as its inputs: a calculation built on a mis-read cell is wrong in the same way." },
  { key: "assumption", mark: "A", label: "Assumption", short: "a value someone chose, not a document", detail: "A value a person chose rather than a document stated: the purchase price and loan terms you entered, a scenario input, a growth rate. Assumptions carry no citation. Change one and every calculation downstream changes with it." },
  { key: "interpretation", mark: "AI", label: "AI interpretation", short: "prose drafted by the model; check it against the sources", detail: "Prose the model drafted: why a claim got its status, what a finding means, an answer in the chat. It may cite source facts and calculations, and a citation that resolves shows where a figure came from, not that the sentence around it is right. Read the sources before you rely on it." },
];

const MARK = "inline-flex h-[18px] min-w-[18px] shrink-0 items-center justify-center rounded-[var(--radius-1)] border px-1 font-mono text-[10.5px] leading-none";

/** The mark alone, for a legend row or a table header; `aria-hidden` because the label always accompanies it. */
export function StatementKindMark({ kind, className = "" }: { kind: StatementKindKey; className?: string }) {
  const k = STATEMENT_KINDS.find((x) => x.key === kind);
  if (!k) return null;
  const cited = kind === "source" || kind === "calculation";
  return <span aria-hidden data-kind={kind} className={`${MARK} ${cited ? "border-hairline bg-bg-muted text-fg" : "border-dashed border-graphite bg-transparent text-fg-muted"} ${className}`}>{k.mark}</span>;
}

/**
 * The legend. `inline` is one wrapping row (mark, label, short phrase) for a page header or an empty state; `full`
 * is a definition list with the long explanation, for the trust page.
 */
export function StatementKindsLegend({ variant = "inline", className = "" }: { variant?: "inline" | "full"; className?: string }) {
  if (variant === "full") {
    return (
      <dl className={`flex flex-col divide-y divide-hairline ${className}`} aria-label="What the labels mean">
        {STATEMENT_KINDS.map((k) => (
          <div key={k.key} className="grid gap-x-4 gap-y-1 py-3 sm:grid-cols-[180px_minmax(0,1fr)]">
            <dt className="flex items-center gap-2 text-sm font-medium"><StatementKindMark kind={k.key} />{k.label}</dt>
            <dd className="text-sm leading-relaxed text-fg-muted">{k.detail}</dd>
          </div>
        ))}
      </dl>
    );
  }
  return (
    <ul className={`flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-fg-muted ${className}`} aria-label="What the labels mean">
      {STATEMENT_KINDS.map((k) => (
        <li key={k.key} className="inline-flex items-center gap-1.5" title={k.detail}>
          <StatementKindMark kind={k.key} />
          <span className="font-medium text-fg">{k.label}</span>
          <span>{k.short}</span>
        </li>
      ))}
    </ul>
  );
}
