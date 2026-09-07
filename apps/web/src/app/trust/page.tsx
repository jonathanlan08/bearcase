import type { Metadata } from "next";
import Link from "next/link";
import { SiteNav, SiteFooter } from "@/components/landing/chrome";
import { StatementKindsLegend } from "@/components/domain/statement-kinds";

export const metadata: Metadata = {
  title: "How BearCase handles your documents",
  description: "Who can see a deal, what leaves the server and when, how long documents are kept, what deleting one removes, what the labels and citations mean, and the limits.",
};

const SECTIONS: Array<{ id: string; title: string }> = [
  { id: "who", title: "Who can see your deal" },
  { id: "leaves", title: "What leaves the server" },
  { id: "keep", title: "How long we keep documents" },
  { id: "delete", title: "Deleting a document" },
  { id: "labels", title: "What the labels mean" },
  { id: "citation", title: "What a citation proves" },
  { id: "limits", title: "Limits" },
];

export default function TrustPage() {
  return (
    <div data-world="ink" className="min-h-svh bg-bg text-fg">
      <SiteNav />
      <main id="main" className="mx-auto max-w-3xl px-6 pb-24 pt-32">
        <h1 className="text-[44px] leading-[1.05] md:text-[56px]">How BearCase handles your documents.</h1>
        <p className="mt-6 text-lg text-fg-muted">You are about to upload a seller&apos;s financial statements, contracts, and loan terms. This page says, in plain words, who can see them, what leaves the server and when, how long they are kept, and what the marks on every statement mean. Where the answer is a limit, it says so.</p>
        <nav aria-label="On this page" className="mt-8">
          <ol className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
            {SECTIONS.map((s, i) => <li key={s.id}><a href={`#${s.id}`} className="text-fg-muted underline-offset-2 hover:text-fg hover:underline"><span className="num mr-1.5 text-xs" aria-hidden>{i + 1}</span>{s.title}</a></li>)}
          </ol>
        </nav>

        <section id="who" aria-labelledby="who-h" className="scroll-mt-24">
          <h2 id="who-h" className="mt-16 text-3xl">Who can see your deal</h2>
          <p className="mt-6 text-fg-muted">A deal belongs to the account that created it, and every request for anything inside it, a document, a claim, a piece of evidence, a scenario, a chat thread, is checked against that owner first. Another account asking for your deal gets &ldquo;not found&rdquo;, not &ldquo;forbidden&rdquo;: the server does not confirm the deal exists. There is no sharing, no team, and no admin view yet; the only way another person sees your deal is by signing in as you.</p>
          <p className="mt-4 text-fg-muted">The demo works the same way. Each visitor to <Link href="/demo" className="text-fg underline underline-offset-2">/demo</Link> gets a private demo identity and their own copy of the fictional Northstar deal. Anything you upload, decide, or ask there is visible to your browser session only; the next visitor gets a fresh copy and cannot open yours. A signed-in account keeps its own identity when it opens the demo.</p>
        </section>

        <section id="leaves" aria-labelledby="leaves-h" className="scroll-mt-24">
          <h2 id="leaves-h" className="mt-16 text-3xl">What leaves the server</h2>
          <p className="mt-6 text-fg-muted">Reading your files, checking the numbers, running the scenarios, and building the report all happen on the server with code and a rule-based reader. None of that sends anything anywhere.</p>
          <p className="mt-4 text-fg-muted">The assistant is the exception, and only when a model is connected. The assistant provider you configure (Anthropic, OpenAI, Google Gemini, Groq, OpenRouter, a local Ollama, or your own server) receives what the chat tools return for your question: claim text, short evidence snippets, and the deal brief, a one-page summary of the deal&apos;s figures. It does not receive your files. If no key is configured, nothing is sent to anyone: the same chat runs on the offline rule-based composer, and the panel says so. If you switch the document reader itself from the rule-based reader to a model, the text of your documents goes to that provider too.</p>
          <p className="mt-4 text-fg-muted">Read the provider&apos;s terms before you connect it. On Google&apos;s free tier, inputs may be used to improve Google&apos;s products, and every visitor to a deployment shares the operator&apos;s one key and its limits. Use a paid plan, or no model at all, for a confidential deal. The panel always names the provider that answered, and the audit history keeps every reply.</p>
        </section>

        <section id="keep" aria-labelledby="keep-h" className="scroll-mt-24">
          <h2 id="keep-h" className="mt-16 text-3xl">How long we keep documents</h2>
          <p className="mt-6 text-fg-muted">Documents in your own account are kept until you delete them. There is no automatic purge, and no backup either: this is a prototype, and the server that holds your files is the only copy.</p>
          <p className="mt-4 text-fg-muted">Demo deals are temporary. A visitor&apos;s demo identity, deals, and files are deleted 14 days after their newest session expired, a few at a time when a new demo starts. Sign-in sessions last 14 days as well. Each account is capped at 50 documents per deal and 500 MB in total, and a single upload at 25 MB.</p>
        </section>

        <section id="delete" aria-labelledby="delete-h" className="scroll-mt-24">
          <h2 id="delete-h" className="mt-16 text-3xl">Deleting a document</h2>
          <p className="mt-6 text-fg-muted">Delete a document from the Deal Room and the server removes the file and every stored version of it, the evidence that was read from it, and the claims that came from it, together with their evidence links and any reviewer decisions on them. Citations that pointed at that document no longer open.</p>
          <p className="mt-4 text-fg-muted">What the delete does not do is recompute. Findings, metrics, scenarios, the report, and the questions for the seller were built from the documents present at the time, so after a delete they may describe evidence that is gone. The Deal Room asks you to run analysis again, and keeps asking until you do. The audit history records that a document was deleted, with its name and time but not its contents.</p>
        </section>

        <section id="labels" aria-labelledby="labels-h" className="scroll-mt-24">
          <h2 id="labels-h" className="mt-16 text-3xl">What the labels mean</h2>
          <p className="mt-6 text-fg-muted">Every statement BearCase shows you is one of four kinds, and the mark beside it says which. Two of them carry a citation you can open; two do not. Keeping them apart is most of what makes the review checkable.</p>
          <StatementKindsLegend variant="full" className="mt-6 border-y border-hairline" />
        </section>

        <section id="citation" aria-labelledby="citation-h" className="scroll-mt-24">
          <h2 id="citation-h" className="mt-16 text-3xl">What a citation proves</h2>
          <p className="mt-6 text-fg-muted">A citation that resolves proves provenance: the statement came from this page and paragraph, this sheet and row, or this CSV row, in this version of this document. Code checks every citation before anything is saved, and a report fails if a material statement has none.</p>
          <p className="mt-4 text-fg-muted">A citation does not prove the statement is correct. The seller&apos;s memo can be cited perfectly and still be wrong; a calculation can cite its inputs and still rest on a mis-read cell; the assistant can cite a real passage and misread it. What carries the judgement is the status rule that compared the claim with the evidence, the number recomputed from the statements, and you, opening the source and reading it. A citation is the shortest path to that source, not a substitute for it.</p>
        </section>

        <section id="limits" aria-labelledby="limits-h" className="scroll-mt-24">
          <h2 id="limits-h" className="mt-16 text-3xl">Limits</h2>
          <ul className="mt-6 list-disc space-y-2 pl-5 text-fg-muted">
            <li>The default reader is rule-based. It finds the claims it has rules for and can miss or misread others; a model can be connected for extraction, but every status is still meant to be reviewed by a person.</li>
            <li>The evaluation suite scores the curated Northstar fixtures. Passing it shows the pipeline is consistent on documents it was built with, not that it is accurate on yours. Reviewed claims can be exported as a dataset so that a release can be measured against real corrections.</li>
            <li>Uploads are checked by their content and never executed. Text inside a document that reads like an instruction is stored as inert content, labelled, and reported as a finding; it never changes what the system does.</li>
            <li>A deployment for confidential deals would still need encryption at rest, backups, monitoring, an external penetration test, and a paid model plan. None of those exist here yet.</li>
            <li>BearCase is an educational prototype. It is not diligence software and does not provide financial, legal, tax, or investment advice. The Northstar deal and everyone in it are fictional.</li>
          </ul>
          <p className="mt-8 text-sm text-fg-muted">How the checks themselves work, status by status and formula by formula, is on <Link href="/methodology" className="text-fg underline underline-offset-2">How we check claims</Link>.</p>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
