import Link from "next/link";
import { SiteNav, SiteFooter } from "@/components/landing/chrome";

/** Frame for the terms and privacy drafts: the template warning sits above the text, not in a footnote. */
export function LegalPage({ title, lede, updated, children }: { title: string; lede: string; updated: string; children: React.ReactNode }) {
  return (
    <div data-world="ink" className="min-h-svh bg-bg text-fg">
      <SiteNav />
      <main id="main" className="mx-auto max-w-3xl px-6 pb-24 pt-32">
        <p role="note" className="rounded-[var(--radius-2)] border border-amber/50 bg-bg-raised px-4 py-3 text-sm"><span aria-hidden>▲ </span><span className="font-medium">Template, have a lawyer review before use.</span> This draft is written in plain language for a prototype and has not been reviewed by counsel.</p>
        <h1 className="mt-8 text-[44px] leading-[1.05] md:text-[56px]">{title}</h1>
        <p className="mt-6 text-lg text-fg-muted">{lede}</p>
        <p className="mt-3 text-sm text-fg-muted">Last updated {updated}. Facts about storage and access are the ones on <Link href="/trust" className="text-fg underline underline-offset-2">the trust page</Link>; where the two differ, the trust page is the one kept current.</p>
        <div className="mt-4">{children}</div>
      </main>
      <SiteFooter />
    </div>
  );
}

export function LegalSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mt-12 text-2xl">{title}</h2>
      <div className="mt-4 flex flex-col gap-3 text-fg-muted">{children}</div>
    </section>
  );
}
