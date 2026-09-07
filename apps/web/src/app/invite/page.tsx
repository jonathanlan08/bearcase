"use client";

import Link from "next/link";
import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { errorDetail, members } from "@/lib/api";
import { AppGate } from "@/components/app/gate";
import { AuthCard } from "@/components/account/auth-card";
import { buttonClass } from "@/components/ui/button";

/** Runs only once the gate has a signed-in user: the invite is accepted for that account, and its email must match. */
function AcceptInvite() {
  const token = useSearchParams().get("token") ?? "";
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<Promise<{ deal_id: string }> | null>(null);
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    const request = (pending.current ??= members.accept(token));
    request
      .then((r) => { if (!cancelled) router.replace(`/app/deals/${r.deal_id}`); })
      .catch((e: unknown) => { if (!cancelled) setError(errorDetail(e, "The invite could not be accepted.")); });
    return () => { cancelled = true; };
  }, [token, router]);
  if (!token) return <AuthCard title="This link did not work" lede="This link has no token. Open the link from the email as it was sent."><Link href="/app" className={buttonClass("secondary")}>Open your deals</Link></AuthCard>;
  if (error) {
    return (
      <AuthCard title="This invite did not work" lede={error}>
        <p role="alert" className="text-sm text-fg-muted">Invites work for the address they were sent to, once, for 7 days. If you signed in with a different address, sign out and back in with the invited one, or ask the owner to send a new invite.</p>
        <Link href="/app" className={`${buttonClass("secondary")} mt-4`}>Open your deals</Link>
      </AuthCard>
    );
  }
  return <AuthCard title="Accepting the invite"><p className="text-sm text-fg-muted" aria-live="polite">One moment.</p></AuthCard>;
}

/** Signed out, the gate shows the sign-in panel in place; once signed in the invite is accepted without another click. */
export default function InvitePage() {
  return (
    <div data-world="paper" className="min-h-svh bg-bg text-fg">
      <AppGate>
        <Suspense fallback={<AuthCard title="Accepting the invite"><p className="text-sm text-fg-muted">One moment.</p></AuthCard>}><AcceptInvite /></Suspense>
      </AppGate>
    </div>
  );
}
