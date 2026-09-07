"use client";

import Link from "next/link";
import { Wordmark } from "@/components/ui/primitives";

/** The one-column frame the account pages share (verify, reset, forgot, invite): wordmark, a plain heading, then the body. */
export function AuthCard({ title, lede, children }: { title: string; lede?: React.ReactNode; children: React.ReactNode }) {
  return (
    <main id="main" data-world="paper" className="grid min-h-svh place-items-center bg-bg p-6 text-fg">
      <div className="w-full max-w-md">
        <Link href="/" className="inline-block rounded-[var(--radius-1)]"><Wordmark size="lg" /></Link>
        <h1 className="mt-6 text-3xl">{title}</h1>
        {lede && <p className="mt-2 text-sm text-fg-muted">{lede}</p>}
        <div className="mt-6">{children}</div>
        <p className="mt-8 text-xs text-fg-muted"><Link href="/app" className="underline-offset-2 hover:underline">Back to the workspace</Link></p>
      </div>
    </main>
  );
}
