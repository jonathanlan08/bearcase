import type { Metadata } from "next";
import { SiteNav, SiteFooter } from "@/components/landing/chrome";

export const metadata: Metadata = { title: "Methodology" };

const FORMULAS: Array<[string, string, string]> = [
  ["Revenue growth", "(current − prior) / prior", "None if prior is missing or zero"],
  ["CAGR", "(last / first)^(1/years) − 1", "None for non-positive base"],
  ["Gross margin", "(revenue − COGS) / revenue", "None if revenue is zero"],
  ["Operating margin", "operating income / revenue", "None if revenue is zero"],
  ["Reported EBITDA", "net income + interest + tax + depreciation + amortization", "Stated EBITDA line is cross-checked; a mismatch flags review"],
  ["Verified adjusted EBITDA", "reported EBITDA + accepted add-backs − accepted downward adjustments", "Rejected and unsupported items stay visible but excluded"],
  ["Enterprise value", "purchase price, or equity price + debt assumed − cash acquired", "Basis is an explicit deal input"],
  ["EV / EBITDA, Debt / EBITDA", "enterprise value ÷ EBITDA, funded debt ÷ EBITDA", "None if EBITDA is zero; negative EBITDA is noted"],
  ["Annual debt service", "P·r / (1 − (1+r)^−n) × payments per year", "Zero-rate loans amortize straight-line; balloon structures are out of scope"],
  ["CFADS", "adjusted EBITDA − maintenance capex − cash taxes − working-capital investment", "The bridge is stored with every scenario"],
  ["DSCR", "CFADS ÷ annual debt service", "EBITDA is never silently labeled CFADS"],
  ["Cash-on-cash", "year-1 cash flow to equity ÷ initial equity", "None if equity is zero"],
  ["IRR", "rate where Σ cf_t / (1+r)^t = 0, annual periods, bisection", "Periodic, not XIRR; None without a sign change"],
  ["Break-even revenue", "(fixed costs + capex + debt service) ÷ contribution margin", "Pre-tax, before working capital; hidden when inputs are missing"],
  ["Customer concentration", "top customer revenue ÷ total revenue", "Aggregated from the customer file with row citations"],
  ["Recurring revenue share", "contract-supported recurring revenue ÷ total revenue", "Only rows typed as maintenance agreements count"],
];

export default function MethodologyPage() {
  return (
    <div data-world="ink" className="min-h-svh bg-bg text-fg">
      <SiteNav />
      <main id="main" className="mx-auto max-w-3xl px-6 pb-24 pt-32">
        <h1 className="text-[44px] leading-[1.05] md:text-[56px]">How BearCase decides what is true.</h1>
        <p className="mt-6 text-lg text-fg-muted">Two systems share the work. A language model reads and compares; deterministic code counts. Neither is allowed to do the other&apos;s job.</p>

        <h2 className="mt-16 text-3xl">Claim statuses</h2>
        <dl className="mt-6 grid gap-4 sm:grid-cols-2">
          {[["Supported", "At least one resolvable citation directly confirms the claim, or the deterministic engine reproduces the number within tolerance."], ["Contradicted", "At least one resolvable citation directly conflicts, or the engine's value differs beyond tolerance (1.0 point for percentages, 2% for currency)."], ["Unsupported", "No provided evidence addresses the claim. Absence of evidence is never treated as contradiction."], ["Review required", "Evidence is partial, mixed, or low-confidence; a calculated input needs a human check; or a reviewer rejected the AI finding."]].map(([t, d]) => (
            <div key={t} className="rounded-[var(--radius-3)] border border-hairline p-4"><dt className="font-medium">{t}</dt><dd className="mt-1 text-sm text-fg-muted">{d}</dd></div>
          ))}
        </dl>
        <p className="mt-4 text-sm text-fg-muted">Guardrails apply in code regardless of provider: Supported requires a supporting citation, Contradicted requires a contradicting one, uncited output degrades to Unsupported, and low confidence routes to review.</p>

        <h2 className="mt-16 text-3xl">What the model does, what code does</h2>
        <div className="mt-6 grid gap-6 sm:grid-cols-2 text-sm">
          <div><p className="mb-2 text-sm font-semibold">The model (Claude, or the rule-based mock)</p><ul className="list-disc space-y-1 pl-5 text-fg-muted"><li>Classify documents</li><li>Extract material claims with a source chunk</li><li>Rank and compare retrieved evidence</li><li>Draft questions, conditions, and narrative</li><li>Explain persisted calculation outputs</li></ul></div>
          <div><p className="mb-2 text-sm font-semibold">Deterministic code</p><ul className="list-disc space-y-1 pl-5 text-fg-muted"><li>Validate and hash uploads; never execute content</li><li>Map statements with cell provenance</li><li>Every financial formula below</li><li>Scenario projections and immutable snapshots</li><li>Citation existence and report validation</li><li>Authorization, state machines, audit history</li></ul></div>
        </div>

        <h2 className="mt-16 text-3xl">Formula contract</h2>
        <div className="mt-6 scroll-x rounded-[var(--radius-2)] border border-hairline">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-hairline text-left text-xs text-fg-muted"><th className="p-3">Metric</th><th className="p-3">Formula</th><th className="p-3">Missing data and edge cases</th></tr></thead>
            <tbody>{FORMULAS.map(([m, fm, n]) => <tr key={m} className="border-b border-hairline last:border-b-0"><td className="p-3 font-medium">{m}</td><td className="p-3 font-mono text-xs">{fm}</td><td className="p-3 text-fg-muted">{n}</td></tr>)}</tbody>
          </table>
        </div>
        <p className="mt-3 text-sm text-fg-muted">All arithmetic is Decimal. A missing input yields no value and a named reason; nothing is defaulted silently. Every persisted metric stores its formula and input snapshot.</p>

        <h2 className="mt-16 text-3xl">Citations and trust</h2>
        <ul className="mt-6 list-disc space-y-2 pl-5 text-fg-muted">
          <li>Every evidence chunk records document, version, page and paragraph, sheet and row, or CSV row. Citations resolve or the claim is dropped.</li>
          <li>Uploaded documents are untrusted. Instruction-like text inside them is stored as inert content, labeled, and surfaced as a finding. It never changes system behavior.</li>
          <li>Provider output must validate against a versioned schema before anything is persisted. Prompt, schema, model, and run id are stored with every extraction.</li>
          <li>Original AI output is immutable. Reviewer decisions are additive and audited; the report shows both.</li>
          <li>A report fails validation if any material statement lacks a resolvable citation or a named derivation.</li>
        </ul>

        <h2 className="mt-16 text-3xl">Limitations</h2>
        <ul className="mt-6 list-disc space-y-2 pl-5 text-fg-muted">
          <li>Portfolio prototype with synthetic data. Not diligence software, and not financial, legal, tax, or investment advice.</li>
          <li>Extraction can be incomplete or wrong; every status is meant to be reviewed by a person.</li>
          <li>Financial outputs depend on mapped and reviewed inputs. Interest-only and balloon debt structures are not modeled.</li>
          <li>A real deployment would need stronger identity, retention, encryption, monitoring, and vendor-risk controls.</li>
        </ul>
      </main>
      <SiteFooter />
    </div>
  );
}
