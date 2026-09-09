import type { Metadata } from "next";
import Link from "next/link";
import { SiteNav, SiteFooter } from "@/components/landing/chrome";
import { Hero } from "@/components/landing/hero";
import { ClaimEvidenceFigure } from "@/components/landing/figures";
import { PilotOffer } from "@/components/landing/pilot-offer";
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
/** Three questions from the fictional Northstar deal, copied from the seller-questions export the demo produces. */
const SAMPLE_QUESTIONS = [
  { severity: "critical", question: "In our downside scenario the cash flow does not cover the loan payments the lender requires. What signed renewals, backlog, or cost commitments for next year can you share?", sources: [] as string[] },
  { severity: "high", question: "The CIM says revenue has grown at approximately 18% annually since FY2022, but the financial statements show a revenue CAGR of 11.6%. Which figure should we rely on, and what explains the difference?", sources: ["northstar-cim.pdf", "northstar-financial-statements.xlsx"] },
  { severity: "high", question: "The CIM says no single customer represents more than 10% of revenue, but the customer revenue file shows the largest customer at 22.0%. Please confirm the concentration and the term of that contract.", sources: ["northstar-cim.pdf", "northstar-customer-revenue.csv"] },
];

const DEMO = {
  headlineClaims: S.claims.length,
  contradicted: S.claims.filter((c) => c.status === "contradicted").length,
  addbacks: S.addbacks.length,
  scenarios: scenarios.length,
  belowCovenant: scenarios.filter((s) => s.breach).length,
  sellerEbitda: fmtMoney(S.ebitda.seller, { compact: true }),
  verifiedEbitda: fmtMoney(S.ebitda.verified, { compact: true }),
  covenant: fmtX(S.deal.threshold),
  questions: 19, // seller questions the Northstar demo exports (repeated issues merged); test_first_customer.py asserts this count
};
const WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];
const word = (n: number) => WORDS[n] ?? String(n);


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
              <p className="mt-4 text-[17px] leading-relaxed text-fg-muted">Every claim links to the page, row, or cell it came from. Then the primary source is checked.</p>
            </div>
            <div className="md:col-span-8"><ClaimEvidenceFigure /></div>
          </div>
        </section>

        {/* What you receive: the deliverable itself, then the paid pilot. */}
        <section className="content-auto border-t border-hairline" aria-labelledby="deliverable-heading">
          <div className="mx-auto grid max-w-[1200px] gap-10 px-6 py-24 md:grid-cols-12 md:py-32 lg:px-10">
            <div className="md:col-span-5">
              <h2 id="deliverable-heading" className="text-3xl md:text-4xl">What you actually receive.</h2>
              <p className="mt-4 text-[17px] leading-relaxed text-fg-muted">Two files: questions for the seller, each tied to the document that raised it, and a report whose every figure names its source. Three of the {word(DEMO.questions)} questions from the Northstar demo, as exported:</p>
              <div className="mt-8"><PilotOffer /></div>
            </div>
            <div className="md:col-span-7">
              <figure className="rounded-[var(--radius-2)] border border-hairline bg-bg-raised p-6 md:p-8">
                <figcaption className="micro text-fg-muted">seller-questions.md · excerpt</figcaption>
                <ol className="mt-4 space-y-5 text-[15px] leading-relaxed">
                  {SAMPLE_QUESTIONS.map((q, i) => (
                    <li key={i} className="grid grid-cols-[auto_1fr] gap-x-3">
                      <span className="num pt-0.5 text-sm text-fg-muted">{i + 1}.</span>
                      <div>
                        <p><span className={`micro mr-2 ${q.severity === "critical" ? "text-red" : "text-amber"}`}>{q.severity}</span>{q.question}</p>
                        <p className="mt-1 font-mono text-[12px] text-fg-muted">{q.sources.length ? `Sources: ${q.sources.join(", ")}` : "Source: the downside scenario in the acquisition model"}</p>
                      </div>
                    </li>
                  ))}
                </ol>
                <p className="mt-6 text-xs text-fg-muted">Open the demo to read all {word(DEMO.questions)} and download the file.</p>
                <p className="mt-3 text-xs text-fg-muted">Northstar is a tidy package. <Link href="/demo?deal=messy" className="text-fg underline underline-offset-2">Try the messy one</Link>, where the years are reversed, the revenue is split across rows, and promised documents never arrived.</p>
              </figure>
            </div>
          </div>
        </section>

        {/* How it works, in three lines */}
        <section className="content-auto border-t border-hairline">
          <div className="mx-auto max-w-[1200px] px-6 py-20 md:py-24 lg:px-10">
            <h2 className="max-w-[640px] text-3xl md:text-4xl">The model reads. The code counts. You decide.</h2>
            <dl className="mt-8 grid gap-x-16 gap-y-6 md:grid-cols-3">
              {[["The model reads", "It quotes claims and drafts questions. It never produces a financial number."], ["The code counts", "Every figure is computed from the statements with its cell recorded."], ["You decide", "Every status is provisional until a person records a decision, and the original is never edited."]].map(([t, d]) => (
                <div key={t} className="border-t border-hairline pt-4"><dt className="text-lg font-semibold">{t}</dt><dd className="mt-2 text-[15px] leading-relaxed text-fg-muted">{d}</dd></div>
              ))}
            </dl>
            <p className="mt-6 text-sm text-fg-muted"><Link href="/methodology" className="underline underline-offset-2 hover:text-fg">How each check works</Link> · <Link href="/trust" className="underline underline-offset-2 hover:text-fg">How your documents are handled</Link></p>
          </div>
        </section>

        {/* 7. Close */}
        <section className="border-t border-hairline">
          <div className="mx-auto max-w-[1200px] px-6 py-24 lg:px-10">
            <div className="max-w-[720px]">
              <h2 className="text-4xl md:text-5xl">See what the checks find.</h2>
              <p className="mt-4 text-lg text-fg-muted">
                In the fictional Northstar deal, {word(DEMO.contradicted)} of {word(DEMO.headlineClaims)} headline claims are contradicted by the seller&apos;s own documents, the seller&apos;s <span className="num">{DEMO.sellerEbitda}</span> becomes <span className="num">{DEMO.verifiedEbitda}</span> once the add-backs are tested, and {word(DEMO.belowCovenant)} of {word(DEMO.scenarios)} scenarios fall below the lender&apos;s minimum.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link href="/demo" className={buttonClass("primary", "md", "h-11 px-5")}>Explore the demo</Link>
                <Link href="/app" className={buttonClass("secondary", "md", "h-11 px-5")}>Sign in or create an account</Link>
              </div>
              <p className="mt-4 text-sm text-fg-muted">Try a fictional deal. No account or API key needed. <Link href="/trust" className="underline underline-offset-2 hover:text-fg">How we handle your documents</Link>.</p>
              <p className="mt-8 max-w-[560px] text-sm text-fg-muted">Northstar HVAC is fictional. BearCase is a first-pass check, not a substitute for professional diligence, and does not provide financial, legal, tax, or investment advice.</p>
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
