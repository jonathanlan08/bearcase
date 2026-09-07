"use client";

import Link from "next/link";
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { auth, errorDetail } from "@/lib/api";
import { AuthCard } from "@/components/account/auth-card";
import { buttonClass } from "@/components/ui/button";

type State = { kind: "checking" } | { kind: "missing" } | { kind: "verified" } | { kind: "failed"; reason: string };

/** Posts the token from the link once; the same token cannot be used twice, so Strict Mode's second effect run shares the request. */
export function VerifyEmail() {
  const token = useSearchParams().get("token") ?? "";
  const [state, setState] = useState<State>(() => (token ? { kind: "checking" } : { kind: "missing" }));
  const pending = useRef<Promise<unknown> | null>(null);
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    const request = (pending.current ??= auth.verify(token));
    request
      .then(() => { if (!cancelled) setState({ kind: "verified" }); })
      .catch((e: unknown) => { if (!cancelled) setState({ kind: "failed", reason: errorDetail(e, "The link could not be checked.") }); });
    return () => { cancelled = true; };
  }, [token]);

  if (state.kind === "checking") return <AuthCard title="Checking your link"><p className="text-sm text-fg-muted" aria-live="polite">One moment.</p></AuthCard>;
  if (state.kind === "verified") {
    return (
      <AuthCard title="Email verified" lede="Your address is confirmed. You can now share deals with a collaborator.">
        <Link href="/app" className={buttonClass("primary")}>Open your deals</Link>
      </AuthCard>
    );
  }
  const reason = state.kind === "missing" ? "This link has no token. Open the link from the email as it was sent." : state.reason;
  return (
    <AuthCard title="This link did not work" lede={reason}>
      <p role="alert" className="text-sm text-fg-muted">Links expire after 24 hours and work once. Sign in and use <span className="font-medium text-fg">Resend the link</span> in the banner at the top of the workspace to get a new one.</p>
      <Link href="/app" className={`${buttonClass("secondary")} mt-4`}>Sign in</Link>
    </AuthCard>
  );
}

export default function VerifyPage() {
  return <Suspense fallback={<AuthCard title="Checking your link"><p className="text-sm text-fg-muted">One moment.</p></AuthCard>}><VerifyEmail /></Suspense>;
}
