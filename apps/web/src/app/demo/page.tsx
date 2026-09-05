"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, type Deal } from "@/lib/api";
import { EvidenceLinkMark } from "@/components/ui/primitives";

/** Starts a demo session (seeding Northstar if needed) and enters the deal. */
export default function DemoPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    api.post<Deal>("/api/demo/session").then((d) => { if (!cancelled) router.replace(`/app/deals/${d.id}`); }).catch((e) => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, [router]);
  return (
    <main id="main" data-world="ink" className="grid min-h-svh place-items-center bg-bg px-6 text-fg">
      <div className="text-center">
        <EvidenceLinkMark size={32} animate className="mx-auto text-accent" />
        {!error ? <p className="mt-4 text-sm text-fg-muted" aria-live="polite">Opening the fictional Northstar HVAC deal…</p> : (
          <div role="alert" className="mt-4 max-w-md text-sm">
            <p className="text-red">The demo could not start.</p>
            <p className="mt-1 font-mono text-xs text-fg-muted">{error}</p>
            <p className="mt-3 text-fg-muted">Is the API running? Start it with <code className="font-mono">make api</code>, then <Link href="/demo" className="text-accent underline">try again</Link>.</p>
          </div>
        )}
      </div>
    </main>
  );
}
