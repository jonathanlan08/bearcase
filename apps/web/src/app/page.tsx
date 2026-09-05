import type { Metadata } from "next";
import Link from "next/link";
import { SiteNav, SiteFooter } from "@/components/landing/chrome";
import { Hero } from "@/components/landing/hero";
import { ClaimEvidenceFigure, ContradictionFigure, ProofStrip, ReportFigure, ScenarioFigure, WaterfallFigure } from "@/components/landing/figures";
import { buttonClass } from "@/components/ui/button";

export const metadata: Metadata = { title: "BearCase AI · Stress-test every claim before capital moves" };

function Section({ n, label, title, children, copy, id }: { n: string; label: string; title: React.ReactNode; copy: React.ReactNode; children: React.ReactNode; id: string }) {
  return (
    <section id={id} className="content-auto border-t border-hairline">
      <div className="mx-auto grid max-w-[1200px] gap-10 px-6 py-24 md:grid-cols-12 md:py-32 lg:px-10">
        <div className="md:col-span-5">
          <p className="micro">{n} · {label}</p>
          <h2 className="mt-3 text-3xl md:text-4xl">{title}</h2>
          <div className="mt-4 text-[17px] leading-relaxed text-fg-muted">{copy}</div>
        </div>
        <div className="md:col-span-7">{children}</div>
      </div>
    </section>
  );
}

export default function LandingPage() {
  return (
    <div data-world="ink" className="min-h-svh bg-bg text-fg">
      <SiteNav />
      <main id="main">
        <Hero />
        <section className="mx-auto max-w-[1200px] px-6 pb-8 lg:px-10"><ProofStrip /></section>
        <Section id="claims" n="01" label="Claims" title={<>Every claim gets a <em className="font-display italic">source</em>.</>} copy={<p>BearCase reads the CIM, model, term sheet, and contracts, quotes each material claim verbatim, and links it to the page, sheet, row, or cell it came from. Then it goes looking for what the primary sources actually say.</p>}>
          <ClaimEvidenceFigure />
        </Section>
        <Section id="contradictions" n="02" label="Contradictions" title={<>Two documents, one <em className="font-display italic">disagreement</em>.</>} copy={<p>Numeric claims are recomputed from statements and customer files by deterministic code. Narrative claims are compared with retrieved evidence only. A claim can be supported, contradicted, unsupported, or sent to a human, and the rule that decided is always shown.</p>}>
          <ContradictionFigure />
        </Section>
        <Section id="financials" n="03" label="Financial verification" title={<>Adjusted EBITDA, <em className="font-display italic">adjusted back</em>.</>} copy={<p>Each seller add-back is tested against the statement lines it claims to normalize. Recurring costs are rejected, one-time items are accepted with their note, and anything without evidence stays visible but out of the total. Multiples, leverage, debt service, CFADS, and DSCR follow from the verified figure.</p>}>
          <WaterfallFigure />
        </Section>
        <Section id="scenarios" n="04" label="Scenario Lab" title={<>Find the <em className="font-display italic">downside</em> before the lender does.</>} copy={<p>Base, downside, and severe cases share one five-year model with named inputs. Move the assumptions and the engine recomputes revenue, EBITDA, the CFADS bridge, DSCR, cash-on-cash, and IRR. Every run stores an immutable input snapshot.</p>}>
          <ScenarioFigure />
        </Section>
        <Section id="report" n="05" label="Red-Team Report" title={<>A review the committee can <em className="font-display italic">check</em>.</>} copy={<p>Verified financials, the claim ledger, contradictions, unsupported assumptions, concentration, adjustments, scenarios, a risk register, missing information, management questions, negotiation conditions, and every reviewer decision, all with citations that resolve.</p>}>
          <ReportFigure />
        </Section>
        <section id="methodology" className="content-auto border-t border-hairline">
          <div className="mx-auto max-w-[1200px] px-6 py-24 md:py-32 lg:px-10">
            <p className="micro">06 · Methodology and code</p>
            <h2 className="mt-3 max-w-2xl text-3xl md:text-4xl">The model reads. The code counts. The reviewer decides.</h2>
            <div className="mt-10 grid gap-8 md:grid-cols-3 text-sm">
              <div><p className="font-medium">AI responsibilities</p><ul className="mt-2 list-disc space-y-1 pl-5 text-fg-muted"><li>Document classification</li><li>Claim extraction with sources</li><li>Evidence ranking and comparison</li><li>Questions, conditions, narrative</li></ul></div>
              <div><p className="font-medium">Deterministic code</p><ul className="mt-2 list-disc space-y-1 pl-5 text-fg-muted"><li>Upload validation and hashing</li><li>Statement mapping with cell provenance</li><li>Every financial formula and scenario</li><li>Citation and report validation, audit history</li></ul></div>
              <div><p className="font-medium">Stack</p><ul className="mt-2 list-disc space-y-1 pl-5 text-fg-muted"><li>FastAPI, SQLAlchemy 2, Alembic, Pydantic</li><li>SQLite by default, PostgreSQL and S3 by config</li><li>Next.js, TypeScript, Tailwind, React Three Fiber</li><li>Anthropic API behind an interface, deterministic mock mode</li></ul></div>
            </div>
            <div className="mt-8 flex flex-wrap gap-3"><Link href="/methodology" className={buttonClass("secondary")}>Read the methodology</Link><a href={process.env.NEXT_PUBLIC_GITHUB_URL ?? "/github"} className={buttonClass("ghost")} target="_blank" rel="noreferrer">View on GitHub</a></div>
          </div>
        </section>
        <section className="border-t border-hairline">
          <div className="mx-auto max-w-[1200px] px-6 py-28 text-center lg:px-10">
            <h2 className="text-4xl md:text-5xl">Open the fictional <em className="font-display italic">Northstar</em> deal.</h2>
            <p className="mx-auto mt-4 max-w-xl text-fg-muted">Seven documents, nineteen claims, four contradictions, one covenant breach. No API key required.</p>
            <div className="mt-8 flex flex-wrap justify-center gap-3"><Link href="/demo" className={buttonClass("primary")}>Explore the demo</Link><a href={process.env.NEXT_PUBLIC_GITHUB_URL ?? "/github"} className={buttonClass("secondary")} target="_blank" rel="noreferrer">View on GitHub</a></div>
            <p className="mt-6 text-xs text-fg-muted">Northstar HVAC is fictional. BearCase is an educational prototype and does not provide financial, legal, tax, or investment advice.</p>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
