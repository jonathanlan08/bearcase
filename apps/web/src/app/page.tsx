import type { Metadata } from "next";
import Link from "next/link";
import { SiteNav, SiteFooter } from "@/components/landing/chrome";
import { Hero } from "@/components/landing/hero";
import { ClaimEvidenceFigure, ContradictionFigure, ReportFigure, ScenarioFigure, WaterfallFigure } from "@/components/landing/figures";
import { buttonClass } from "@/components/ui/button";
import snapshot from "@/content/northstar-snapshot.json";
import { fmtMoney, fmtX } from "@/lib/format";

export const metadata: Metadata = {
  title: "BearCase AI",
  description: "BearCase checks a seller's documents for financial inconsistencies and shows you what to investigate before buying the business.",
};

/** Demo facts come from the committed Northstar snapshot, the same file the figures render from, so the copy cannot drift from the figures. */
const S = snapshot;
const scenarios = Object.values(S.scenarios);
const DEMO = {
  headlineClaims: S.claims.length,
  contradicted: S.claims.filter((c) => c.status === "contradicted").length,
  addbacks: S.addbacks.length,
  scenarios: scenarios.length,
  belowCovenant: scenarios.filter((s) => s.breach).length,
  sellerEbitda: fmtMoney(S.ebitda.seller, { compact: true }),
  verifiedEbitda: fmtMoney(S.ebitda.verified, { compact: true }),
  covenant: fmtX(S.deal.threshold),
};
const WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];
const word = (n: number) => WORDS[n] ?? String(n);
const capWord = (n: number) => { const w = word(n); return w.charAt(0).toUpperCase() + w.slice(1); };

/** The same four steps the deal overview tracks, in the same words. */
const FIRST_SESSION: Array<[string, string]> = [
  ["Add documents", "Upload what the seller gave you: the sales memo, the financial statements, the customer list, the contracts, and the loan terms."],
  ["Check the findings", "Each claim is marked supported, contradicted, unsupported, or review required, with the page or cell it came from beside it. Start with the ones the documents disagree with."],
  ["Inspect the evidence", "Open the cited page or cell next to the claim and decide for yourself. Test the downside too: lose the largest customer and see whether the cash still covers the loan."],
  ["Send questions to the seller", "Every contradiction and every gap becomes a question with its evidence attached. Copy the list or download it, and ask the seller before you sign."],
];

export default function LandingPage() {
  return (
    <div data-world="ink" className="min-h-svh bg-bg text-fg">
      <SiteNav />
      <main id="main">
        <Hero />

        {/* 0. Plain-language framing and the first session */}
        <section className="content-auto border-t border-hairline" aria-labelledby="first-session-heading">
          <div className="mx-auto max-w-[1200px] px-6 py-24 md:py-32 lg:px-10">
            <div className="max-w-[680px]">
              <h2 id="first-session-heading" className="text-3xl md:text-4xl">The seller&apos;s story, checked line by line against the paperwork.</h2>
              <p className="mt-4 text-[17px] leading-relaxed text-fg-muted">BearCase reads what the seller hands over, quotes each claim next to the page or cell behind it, recomputes the numbers with plain code, and shows you where the story and the evidence disagree. Overstated earnings, one customer that is most of the revenue, and loan payments the cash will not cover show up before you sign, not after.</p>
            </div>
            <h3 className="mt-16 text-lg font-semibold">What your first session looks like</h3>
            <ol className="mt-5 grid gap-x-10 gap-y-8 md:grid-cols-4">
              {FIRST_SESSION.map(([t, d], i) => (
                <li key={t} className="border-t border-hairline pt-4">
                  <p className="text-lg font-semibold"><span className="num mr-2 text-fg-muted" aria-hidden>{i + 1}</span>{t}</p>
                  <p className="mt-2 text-[15px] leading-relaxed text-fg-muted">{d}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* 1. Split: claim and its evidence */}
        <section className="content-auto border-t border-hairline">
          <div className="mx-auto grid max-w-[1200px] gap-10 px-6 py-24 md:grid-cols-12 md:py-32 lg:px-10">
            <div className="md:col-span-4">
              <h2 className="text-3xl md:text-4xl">Every claim gets a source.</h2>
              <p className="mt-4 text-[17px] leading-relaxed text-fg-muted">BearCase quotes each material claim from the sales memo, the buyer&apos;s model, the loan term sheet, and the contracts, and links it to the page, sheet, row, or cell it came from. Then it checks what the primary sources actually say.</p>
            </div>
            <div className="md:col-span-8"><ClaimEvidenceFigure /></div>
          </div>
        </section>

        {/* 2. Full width: contradiction */}
        <section className="content-auto border-t border-hairline">
          <div className="mx-auto max-w-[1200px] px-6 py-24 md:py-32 lg:px-10">
            <div className="max-w-[640px]">
              <h2 className="text-3xl md:text-4xl">Two documents, one disagreement.</h2>
              <p className="mt-4 text-[17px] leading-relaxed text-fg-muted">Numbers are recomputed from the statements and the customer file by deterministic code. Narrative claims are compared only with evidence retrieved from the documents. A claim ends up supported, contradicted, unsupported, or with a reviewer, and the rule that decided is always shown. Missing evidence is never counted as a contradiction.</p>
            </div>
            <div className="mt-12"><ContradictionFigure /></div>
          </div>
        </section>

        {/* 3. Stacked: waterfall */}
        <section className="content-auto border-t border-hairline">
          <div className="mx-auto max-w-[1200px] px-6 py-24 md:py-32 lg:px-10">
            <div className="max-w-[640px]">
              <h2 className="text-3xl md:text-4xl">Adjusted EBITDA, adjusted back.</h2>
              <p className="mt-4 text-[17px] leading-relaxed text-fg-muted">Sellers add back costs they say will not recur, which makes earnings look larger. Each add-back is tested against the statement lines it claims to normalize: recurring costs are rejected, one-time items are accepted with their note, and anything without evidence stays out of the total. The price multiple, the debt load, and the loan coverage all follow from the verified figure, not the seller&apos;s.</p>
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
              <p className="mt-4 text-[17px] leading-relaxed text-fg-muted">Base, downside, and severe cases share one five-year model with named inputs. Move an assumption and the engine recomputes revenue, earnings, the cash available for the loan, coverage against the lender&apos;s minimum, and returns. Every run stores an immutable snapshot of its inputs, so a result can always be reproduced.</p>
            </div>
          </div>
        </section>

        {/* 5. Report */}
        <section className="content-auto border-t border-hairline">
          <div className="mx-auto max-w-[1200px] px-6 py-24 md:py-32 lg:px-10">
            <div className="max-w-[640px]">
              <h2 className="text-3xl md:text-4xl">A review the committee can check.</h2>
              <p className="mt-4 text-[17px] leading-relaxed text-fg-muted">Checked financials, the claim ledger, contradictions, unsupported assumptions, customer concentration, adjustments, scenarios, risks, open questions for the seller, and every reviewer decision, with citations that open the source. Ask the deal a question in plain language and get the same discipline back.</p>
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
                ["Reading and quoting", "The model classifies documents, quotes material claims with a source, ranks evidence, and drafts questions and narrative. It never produces a financial number."],
                ["Every number", "Deterministic code maps the statements with cell-level provenance and computes growth, margins, EBITDA bridges, multiples, debt service, coverage, and returns. Missing inputs stay missing; nothing is defaulted silently."],
                ["Every citation", "Model output must validate against a versioned schema. A material statement without a citation fails the report. Original AI output is immutable; reviewer decisions are additive and audited."],
                ["Untrusted documents", "Uploads are validated by content and never executed. Text inside a document that reads like an instruction is stored as inert content and reported as a finding."],
              ].map(([t, d]) => (
                <div key={t} className="border-t border-hairline pt-4"><dt className="text-lg font-semibold">{t}</dt><dd className="mt-2 text-[15px] leading-relaxed text-fg-muted">{d}</dd></div>
              ))}
            </dl>
            <div className="mt-10 flex flex-wrap gap-3"><Link href="/methodology" className={buttonClass("secondary")}>Read how claims are checked</Link></div>
          </div>
        </section>

        {/* 7. Close */}
        <section className="border-t border-hairline">
          <div className="mx-auto max-w-[1200px] px-6 py-24 lg:px-10">
            <div className="max-w-[720px]">
              <h2 className="text-4xl md:text-5xl">Buying a small business for the first time? See what the checks find.</h2>
              <p className="mt-4 text-lg text-fg-muted">
                BearCase is for the person about to buy a company on the strength of the seller&apos;s package: an owner-operator, a search fund, a family taking on a loan. In the fictional Northstar deal, {word(DEMO.headlineClaims)} headline claims come from the sales memo and {word(DEMO.contradicted)} of them are contradicted by the seller&apos;s own documents. {capWord(DEMO.addbacks)} add-backs are put to the test: the seller says <span className="num">{DEMO.sellerEbitda}</span>, the statements support <span className="num">{DEMO.verifiedEbitda}</span>. {capWord(DEMO.belowCovenant)} of {word(DEMO.scenarios)} scenarios fall below the lender&apos;s <span className="num">{DEMO.covenant}</span> minimum. Each one ends as a question for the seller, with the evidence attached.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link href="/demo" className={buttonClass("primary", "md", "h-11 px-5")}>Explore the demo</Link>
                <Link href="/app" className={buttonClass("secondary", "md", "h-11 px-5")}>Sign in or create an account</Link>
              </div>
              <p className="mt-4 text-sm text-fg-muted">Try a fictional deal. No account or API key needed. <Link href="/trust" className="underline underline-offset-2 hover:text-fg">How we handle your documents</Link>.</p>
              <p className="mt-8 max-w-[560px] text-sm text-fg-muted">Northstar HVAC is fictional. BearCase is an educational prototype and does not provide financial, legal, tax, or investment advice.</p>
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
