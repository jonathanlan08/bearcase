"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { auth, errorDetail } from "@/lib/api";
import { AuthCard } from "@/components/account/auth-card";
import { Button } from "@/components/ui/button";
import { Field, inputClass } from "@/components/ui/field";

/** The reply never says whether the address exists: the same sentence for every submission (the API answers 200 either way). */
export const SENT = "If that address has an account, a reset link is on its way.";

export default function ForgotPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const request = useMutation({ mutationFn: () => auth.requestReset(email.trim()), onError: (e) => setError(errorDetail(e, "The request could not be sent. Try again in a minute.")) });
  if (request.isSuccess) return <AuthCard title="Check your email" lede={SENT}><p className="text-sm text-fg-muted">The link works for one hour.</p></AuthCard>;
  return (
    <AuthCard title="Reset your password" lede="Enter the address you signed up with.">
      <form className="flex flex-col gap-3 rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-4" onSubmit={(e) => { e.preventDefault(); setError(null); request.mutate(); }}>
        <Field label="Email" required>{(p) => <input {...p} type="email" className={inputClass(p.invalid)} value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />}</Field>
        {error && <p role="alert" className="text-sm text-red">{error}</p>}
        <Button type="submit" loading={request.isPending}>Send a reset link</Button>
      </form>
    </AuthCard>
  );
}
