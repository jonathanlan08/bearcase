"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { auth, errorDetail } from "@/lib/api";
import { AuthCard } from "@/components/account/auth-card";
import { Button, buttonClass } from "@/components/ui/button";
import { Field, inputClass } from "@/components/ui/field";

export function ResetPassword() {
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const reset = useMutation({ mutationFn: () => auth.reset(token, password), onError: (e) => setError(errorDetail(e, "The password could not be changed.")) });
  const mismatch = again.length > 0 && again !== password;

  if (!token) {
    return (
      <AuthCard title="This link did not work" lede="This link has no token. Open the link from the email as it was sent, or request a new one.">
        <Link href="/forgot" className={buttonClass("secondary")}>Request a new link</Link>
      </AuthCard>
    );
  }
  if (reset.isSuccess) {
    return (
      <AuthCard title="Password changed" lede="Every other session of your account was signed out. Sign in with the new password.">
        <Link href="/app" className={buttonClass("primary")}>Sign in</Link>
      </AuthCard>
    );
  }
  return (
    <AuthCard title="Choose a new password" lede="Links work for one hour and once.">
      <form className="flex flex-col gap-3 rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-4" onSubmit={(e) => { e.preventDefault(); if (mismatch) return; setError(null); reset.mutate(); }}>
        <Field label="New password" help="At least 8 characters." required>{(p) => <input {...p} type="password" className={inputClass(p.invalid)} value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} autoComplete="new-password" />}</Field>
        <Field label="New password again" required error={mismatch ? "The two passwords differ." : undefined}>{(p) => <input {...p} type="password" className={inputClass(p.invalid)} value={again} onChange={(e) => setAgain(e.target.value)} required minLength={8} autoComplete="new-password" />}</Field>
        {error && (
          <p role="alert" className="text-sm text-red">{error} <Link href="/forgot" className="underline underline-offset-2">Request a new link</Link>.</p>
        )}
        <Button type="submit" loading={reset.isPending} disabled={mismatch || !password}>Change password</Button>
      </form>
    </AuthCard>
  );
}

export default function ResetPage() {
  return <Suspense fallback={<AuthCard title="Choose a new password"><p className="text-sm text-fg-muted">One moment.</p></AuthCard>}><ResetPassword /></Suspense>;
}
