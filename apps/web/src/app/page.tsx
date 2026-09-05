import type { Metadata } from "next";
import Link from "next/link";
import { SiteNav, SiteFooter } from "@/components/landing/chrome";
import { Hero } from "@/components/landing/hero";
import { ClaimEvidenceFigure, ContradictionFigure, ReportFigure, ScenarioFigure, WaterfallFigure } from "@/components/landing/figures";
import { buttonClass } from "@/components/ui/button";

export const metadata: Metadata = { title: "BearCase AI" };

const GITHUB = process.env.NEXT_PUBLIC_GITHUB_URL ?? "/github";

export default function LandingPage() {
  return (
    <div data-world="ink" className="min-h-svh bg-bg text-fg">
      <SiteNav />
      <main id="main">
        <Hero />

        {/* 1. Split: claim and its evidence */}
        <section className="content-auto border-t border-hairline">
          <div className="mx-auto grid max-w-[1200px] gap-10 px-6 py-24 md:grid-cols-12 md:py-32 lg:px-10">
            <div className="md:col-span-4">
              <h2 className="text-3xl md:text-4xl">Every claim gets a source.</h2>
              <p className="mt-4 text-[17px] leading-relaxed text-fg-muted">BearCase quotes each material claim from the memo, the model, the term sheet, and the contracts, and links it to the page, sheet, row, or cell it came from. Then it checks what the primary sources actually say.</p>
            </div>
            <div className="md:col-span-8"><ClaimEvidenceFigure /></div>
          </div>
        </section>

        {/* 2. Full width: contradiction */}
        <section className="content-auto border-t border-hairline">
          <div className="mx-auto max-w-[1200px] px-6 py-24 md:py-32 lg:px-10">
            <div className="max-w-[640px]">
              <h2 className="text-3xl md:text-4xl">Two documents, one disagreement.</h2>
              <p className="mt-4 text-[17px] leading-relaxed text-fg-muted">Numbers are recomputed from statements and customer files by deterministic code. Narrative claims are compared only with retrieved evidence. A claim ends up supported, contradicted, unsupported, or with a reviewer, and the rule that decided is always shown.</p>
            </div>
            <div className="mt-12"><ContradictionFigure /></div>
          </div>
        </section>

        {/* 3. Stacked: waterfall */}
        <section className="content-auto border-t border-hairline">
          <div className="mx-auto max-w-[1200px] px-6 py-24 md:py-32 lg:px-10">
            <div className="max-w-[640px]">
              <h2 className="text-3xl md:text-4xl">Adjusted EBITDA, adjusted back.</h2>
              <p className="mt-4 text-[17px] leading-relaxed text-fg-muted">Each seller add-back is tested against the statement lines it claims to normalize. Recurring costs are rejected, one-time items are accepted with their note, and anything without evidence stays out of the total. Multiples, leverage, debt service, and coverage follow from the verified figure.</p>
            </div>
            <div className="mt-12"><WaterfallFigure /></div>
          </div>
        </section>

        {/* 4. Split reversed: scenario */}
        <section className="content-auto border-t border-hairline">
          <div className="mx-auto grid max-w-[1200px] gap-10 px-6 py-24 md:grid-cols-12 md:py-32 lg:px-10">
            <div className="md:col-span-8 md:order-1"><ScenarioFigure /></div>
            <div className="md:col-span-4 md:order-2">
              <h2 className="text-3xl md:text-4xl">Find the downside before the lender does.</h2>
              <p className="mt-4 text-[17px] leading-relaxed text-fg-muted">Base, downside, and severe cases share one five-year model with named inputs. Move an assumption and the engine recomputes revenue, EBITDA, the cash-flow bridge, coverage, and returns. Every run stores an immutable input snapshot.</p>
            </div>
          </div>
        </section>

        {/* 5. Report */}
        <section className="content-auto border-t border-hairline">
          <div className="mx-auto max-w-[1200px] px-6 py-24 md:py-32 lg:px-10">
            <div className="max-w-[640px]">
              <h2 className="text-3xl md:text-4xl">A review the committee can check.</h2>
              <p className="mt-4 text-[17px] leading-relaxed text-fg-muted">Verified financials, the claim ledger, contradictions, unsupported assumptions, concentration, adjustments, scenarios, risks, open questions, and every reviewer decision, with citations that resolve. Ask the deal a question in plain language and get the same discipline back.</p>
            </div>
            <div className="mt-12"><ReportFigure /></div>
          </div>
        </section>

        {/* 6. Two-column definition list: who does what */}
        <section className="content-auto border-t border-hairline">
          <div className="mx-auto max-w-[1200px] px-6 py-24 md:py-32 lg:px-10">
            <h2 className="max-w-[640px] text-3xl md:text-4xl">The model reads. The code counts. The reviewer decides.</h2>
            <dl className="mt-12 grid gap-x-16 gap-y-8 md:grid-cols-2">
              {[
                ["Classifying and quoting", "The model classifies documents, quotes material claims with a source, ranks evidence, and drafts questions and narrative."],
                ["Every number", "Deterministic code maps statements with cell provenance and computes growth, margins, EBITDA bridges, multiples, debt service, coverage, and returns. Missing inputs stay missing."],
                ["Every citation", "Provider output must validate against a versioned schema. Uncited material statements fail the report. Original AI output is immutable; reviewer decisions are additive and audited."],
                ["Untrusted documents", "Uploads are validated by content and never executed. Instruction-like text inside a document is stored as inert content and reported as a finding."],
              ].map(([t, d]) => (
                <div key={t} className="border-t border-hairline pt-4"><dt className="text-lg font-semibold">{t}</dt><dd className="mt-2 text-[15px] leading-relaxed text-fg-muted">{d}</dd></div>
              ))}
            </dl>
            <div className="mt-10 flex flex-wrap gap-3"><Link href="/methodology" className={buttonClass("secondary")}>Read the methodology</Link><a href={GITHUB} className={buttonClass("ghost")} target="_blank" rel="noreferrer">View on GitHub</a></div>
          </div>
        </section>

        {/* 7. Close */}
        <section className="border-t border-hairline">
          <div className="mx-auto max-w-[1200px] px-6 py-24 lg:px-10">
            <div className="max-w-[720px]">
              <h2 className="text-4xl md:text-5xl">Open the fictional Northstar deal.</h2>
              <p className="mt-4 text-lg text-fg-muted">Seven documents, nineteen claims, four contradictions, one covenant breach. No API key required.</p>
              <div className="mt-8 flex flex-wrap gap-3"><Link href="/demo" className={buttonClass("primary", "md", "h-11 px-5")}>Explore the demo</Link></div>
              <p className="mt-8 max-w-[560px] text-sm text-fg-muted">Northstar HVAC is fictional. BearCase is an educational prototype and does not provide financial, legal, tax, or investment advice.</p>
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
