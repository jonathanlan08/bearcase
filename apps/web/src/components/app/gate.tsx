"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { api, ApiError, errorDetail, type Deal, type User } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Field, inputClass } from "@/components/ui/field";
import { EvidenceLinkMark, Skeleton, Wordmark } from "@/components/ui/primitives";
import { qk } from "@/components/app/hooks";
import { useRouter } from "next/navigation";

export function useMe() {
  return useQuery({ queryKey: qk.me, queryFn: () => api.get<User>("/api/auth/me"), retry: false });
}

/** Renders children only for an authenticated user; otherwise the sign-in / demo panel. */
export function AppGate({ children }: { children: React.ReactNode }) {
  const me = useMe();
  if (me.isPending) {
    return (
      <div className="mx-auto max-w-5xl p-8">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="mt-6 h-40 w-full" />
      </div>
    );
  }
  if (me.isError && (me.error as ApiError).status === 401) return <SignIn />;
  if (me.isError) return <div className="p-8 text-sm text-red">Cannot reach the API. Start it with <code className="font-mono">make api</code> and reload.</div>;
  return <>{children}</>;
}

function SignIn() {
  const qc = useQueryClient();
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ email: "", password: "", display_name: "" });
  const [error, setError] = useState<string | null>(null);
  // The account that was just created; the gate shows "Check your email" before handing over to the workspace.
  const [registered, setRegistered] = useState<User | null>(null);
  const demo = useMutation({
    mutationFn: () => api.post<Deal>("/api/demo/session"),
    onSuccess: (deal) => { qc.invalidateQueries({ queryKey: qk.me }); router.push(`/app/deals/${deal.id}`); },
    onError: (e) => setError(e instanceof Error ? e.message : "Demo failed"),
  });
  const auth = useMutation({
    mutationFn: () => api.post<User>(mode === "login" ? "/api/auth/login" : "/api/auth/register", mode === "login" ? { email: form.email, password: form.password } : form),
    onSuccess: (user) => { if (mode === "register") setRegistered(user); else qc.invalidateQueries({ queryKey: qk.me }); },
    onError: (e) => setError(errorDetail(e, "Sign-in failed")),
  });
  if (registered) {
    return (
      <main id="main" className="grid min-h-svh place-items-center p-6">
        <div className="w-full max-w-md">
          <Wordmark size="lg" />
          <h1 className="mt-6 text-3xl">Check your email</h1>
          <p className="mt-2 text-sm text-fg-muted">We sent a verification link to <span className="font-medium text-fg">{registered.email}</span>. It works for 24 hours. You can open your workspace now; sharing a deal waits until the address is verified.</p>
          <div className="mt-6 flex flex-wrap gap-2">
            <Button onClick={() => qc.invalidateQueries({ queryKey: qk.me })}>Continue to your deals</Button>
          </div>
          <p className="mt-4 text-xs text-fg-muted">No email? Check the spam folder, or resend the link from the banner inside the workspace.</p>
        </div>
      </main>
    );
  }
  return (
    <main id="main" className="grid min-h-svh place-items-center p-6">
      <div className="w-full max-w-md">
        <Wordmark size="lg" />
        <h1 className="mt-6 text-3xl">Open the review room</h1>
        <p className="mt-2 text-sm text-fg-muted">The fictional Northstar HVAC deal is pre-loaded. Start a demo session, or sign in to work on your own deals.</p>
        <div className="mt-6 rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-4">
          <Button className="w-full" onClick={() => demo.mutate()} loading={demo.isPending} icon={<EvidenceLinkMark size={16} />}>Open the Northstar demo</Button>
          <p className="mt-2 text-center text-xs text-fg-muted">Seeds a synthetic deal for the demo analyst. No API key required.</p>
        </div>
        <form className="mt-4 rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-4" onSubmit={(e) => { e.preventDefault(); setError(null); auth.mutate(); }}>
          <div className="mb-3 flex gap-4 text-sm">
            <button type="button" className={`border-b-2 pb-1 ${mode === "login" ? "border-accent font-medium" : "border-transparent text-fg-muted"}`} onClick={() => setMode("login")}>Sign in</button>
            <button type="button" className={`border-b-2 pb-1 ${mode === "register" ? "border-accent font-medium" : "border-transparent text-fg-muted"}`} onClick={() => setMode("register")}>Create account</button>
          </div>
          <div className="flex flex-col gap-3">
            {mode === "register" && (
              <Field label="Display name" required>{(p) => <input {...p} className={inputClass(p.invalid)} value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} required autoComplete="name" />}</Field>
            )}
            <Field label="Email" required>{(p) => <input {...p} type="email" className={inputClass(p.invalid)} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required autoComplete="email" />}</Field>
            <Field label="Password" help="At least 8 characters." required>{(p) => <input {...p} type="password" className={inputClass(p.invalid)} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required minLength={8} autoComplete={mode === "login" ? "current-password" : "new-password"} />}</Field>
            {error && <p role="alert" className="text-sm text-red">{error}</p>}
            <Button type="submit" variant="secondary" loading={auth.isPending}>{mode === "login" ? "Sign in" : "Create account"}</Button>
            {mode === "login" && <Link href="/forgot" className="self-start text-xs text-fg-muted underline-offset-2 hover:text-fg hover:underline">Forgot password?</Link>}
          </div>
        </form>
        <p className="mt-6 text-xs text-fg-muted">BearCase is an educational prototype and does not provide financial, legal, tax, or investment advice.</p>
      </div>
    </main>
  );
}
