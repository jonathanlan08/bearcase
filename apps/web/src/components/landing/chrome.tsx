"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Menu, X } from "lucide-react";
import { buttonClass } from "@/components/ui/button";
import { Wordmark } from "@/components/ui/primitives";

const GITHUB = process.env.NEXT_PUBLIC_GITHUB_URL ?? "/github";

export function SiteNav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 80);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  return (
    <header className={`fixed inset-x-0 top-0 z-40 transition-colors duration-200 ${scrolled || open ? "border-b border-hairline bg-ink-950/85 backdrop-blur-sm" : "bg-transparent"}`}>
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-6 lg:px-10">
        <Link href="/" className="rounded-[var(--radius-1)]"><Wordmark size="lg" /></Link>
        <nav aria-label="Site" className="hidden items-center gap-7 text-sm md:flex">
          <Link href="/methodology" className="text-fg-muted hover:text-fg">Methodology</Link>
          <a href={GITHUB} className="text-fg-muted hover:text-fg" target="_blank" rel="noreferrer">GitHub</a>
          <Link href="/demo" className={buttonClass("primary", "sm")}>Explore the demo</Link>
        </nav>
        <div className="flex items-center gap-2 md:hidden">
          <Link href="/demo" className={buttonClass("primary", "sm")}>Demo</Link>
          <button type="button" aria-expanded={open} aria-controls="site-menu" aria-label={open ? "Close menu" : "Open menu"} className="rounded-[var(--radius-1)] p-2 text-fg" onClick={() => setOpen((o) => !o)}>{open ? <X size={18} /> : <Menu size={18} />}</button>
        </div>
      </div>
      {open && (
        <nav id="site-menu" aria-label="Site" className="border-t border-hairline px-6 py-4 md:hidden">
          <ul className="flex flex-col gap-3 text-base">
            <li><Link href="/methodology" onClick={() => setOpen(false)}>Methodology</Link></li>
            <li><a href={GITHUB} target="_blank" rel="noreferrer">GitHub</a></li>
            <li><Link href="/app" onClick={() => setOpen(false)}>Open the app</Link></li>
          </ul>
        </nav>
      )}
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="border-t border-hairline">
      <div className="mx-auto grid max-w-[1200px] gap-10 px-6 py-14 md:grid-cols-3 lg:px-10">
        <div>
          <Wordmark />
          <p className="mt-3 max-w-xs text-sm text-fg-muted">AI-assisted acquisition diligence and investment-committee red-team review. Open source, MIT licensed.</p>
        </div>
        <div>
          <p className="micro">Product</p>
          <ul className="mt-3 flex flex-col gap-2 text-sm">
            <li><Link href="/demo" className="hover:underline">Explore the demo</Link></li>
            <li><Link href="/methodology" className="hover:underline">Methodology</Link></li>
            <li><a href={GITHUB} className="hover:underline" target="_blank" rel="noreferrer">View on GitHub</a></li>
          </ul>
        </div>
        <div>
          <p className="micro">Disclosure</p>
          <p className="mt-3 text-sm text-fg-muted">Northstar HVAC Services and every person, customer, contract, lender, and number in the demo are fictional. BearCase is an educational prototype and does not provide financial, legal, tax, or investment advice.</p>
          <p className="mt-3 font-mono text-[11px] text-fg-muted">Runs with a deterministic mock provider by default; the Anthropic API is optional.</p>
        </div>
      </div>
    </footer>
  );
}
