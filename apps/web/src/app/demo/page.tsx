"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, ApiError, type Deal } from "@/lib/api";
import { buttonClass } from "@/components/ui/button";
import { EvidenceLinkMark } from "@/components/ui/primitives";

/** A visitor-facing reason for the failure, without developer instructions. */
function describe(e: unknown): { reason: string; code: string | null } {
  if (e instanceof ApiError) {
    if (e.status === 429) return { reason: "Too many demo sessions are being opened right now.", code: `HTTP ${e.status}` };
    if (e.status >= 500) return { reason: "The server hit an error while preparing the deal.", code: `HTTP ${e.status}` };
    return { reason: e.message, code: `HTTP ${e.status}` };
  }
  if (e instanceof TypeError) return { reason: "The service could not be reached.", code: null };
  return { reason: e instanceof Error ? e.message : String(e), code: null };
}

/** Starts a demo session (seeding the chosen deal if needed) and enters it. `?deal=messy` opens the Tidewater package:
 *  thousands, reversed and missing years, revenue split across rows, promised documents absent. */
export default function DemoPage() {
  return <Suspense fallback={null}><DemoStarter /></Suspense>;
}

function DemoStarter() {
  const router = useRouter();
  const which = useSearchParams().get("deal") === "messy" ? "messy" : "northstar";
  const [error, setError] = useState<{ reason: string; code: string | null } | null>(null);
  const [attempt, setAttempt] = useState(0);
  // React Strict Mode runs this effect twice in development; the ref lets both runs share one request instead of creating two sessions.
  const pending = useRef<Promise<Deal> | null>(null);
  useEffect(() => {
    let cancelled = false;
    const request = (pending.current ??= api.post<Deal>(`/api/demo/session?deal=${which}`));
    request
      .then((d) => { if (!cancelled) router.replace(`/app/deals/${d.id}`); })
      .catch((e: unknown) => { if (!cancelled) setError(describe(e)); });
    return () => { cancelled = true; };
  }, [router, attempt, which]);
  const retry = () => { pending.current = null; setError(null); setAttempt((n) => n + 1); };
  return (
    <main id="main" data-world="ink" className="grid min-h-svh place-items-center bg-bg px-6 text-fg">
      <div className="max-w-md text-center">
        <EvidenceLinkMark size={32} animate className="mx-auto text-accent" />
        {!error ? (
          <div className="mt-4 text-sm text-fg-muted" aria-live="polite">
            <p>Opening the fictional {which === "messy" ? "Tidewater Plumbing" : "Northstar HVAC"} deal…</p>
            <p className="mt-1">The first visit can take a few seconds while the demo is seeded.</p>
          </div>
        ) : (
          <div role="alert" className="mt-4 text-sm">
            <p className="font-medium text-red">The demo could not start.</p>
            <p className="mt-1 text-fg-muted">{error.reason} Nothing was saved. Try again in a moment; if it keeps failing, the demo may be down.</p>
            {error.code && <p className="mt-1 font-mono text-xs text-fg-muted">{error.code}</p>}
            <div className="mt-4 flex justify-center gap-2">
              <button type="button" onClick={retry} className={buttonClass("primary", "sm")}>Retry</button>
              <Link href="/" className={buttonClass("secondary", "sm")}>Home</Link>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
