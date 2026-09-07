"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { ApiError, billing, errorDetail, fmtPrice, type BillingOffer } from "@/lib/api";
import { SiteNav, SiteFooter } from "@/components/landing/chrome";
import { Button, buttonClass } from "@/components/ui/button";
import { fmtDate } from "@/lib/format";

const CONTACT = process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? "";

/** What one pilot covers. Wording follows docs/go-to-market.md ("Bounded pilot offer"); the price comes from the API. */
const SCOPE = [
  { title: "One document set, one deal", body: "You upload the seller's documents for a single deal. Text-layer PDFs, XLSX, and CSV; an income statement sheet must be named like one." },
  { title: "A human check before delivery", body: "A person reads every contradiction, every add-back the rules accepted or excluded, and every statement mapping the rules flagged, before anything is sent, and says in writing what was checked and what was not." },
  { title: "Delivered within five business days", body: "Two files: the seller-questions export (Markdown) and the red-team report (PDF). Each states where every figure came from." },
];

/** The limits stated up front, so nobody buys a pilot expecting what the tool does not do. */
const LIMITS = [
  "No OCR: scanned PDFs without a text layer are not read.",
  "Annual periods only; no monthly statements.",
  "Debt is modelled as amortising; no interest-only or balloon structures.",
  "Add-back rules test recurrence and prior-year excess, not a market salary.",
  "A live model provider receives claim text and evidence snippets, named on the trust page. It never receives your files in the chat.",
  "A citation shows where a statement came from, not that it is true. Nothing in the deliverable is investment, legal, or tax advice.",
];

function StartPilot({ status, signedIn }: { status: BillingOffer; signedIn: boolean }) {
  const [error, setError] = useState<string | null>(null);
  const checkout = useMutation({
    mutationFn: () => billing.checkout(),
    onSuccess: ({ url }) => { window.location.assign(url); },
    onError: (e) => setError(e instanceof ApiError && e.status === 401 ? "Sign in first, then come back to start the pilot." : errorDetail(e, "Checkout could not be started.")),
  });
  const price = fmtPrice(status.pilot.amount_cents, status.pilot.currency);
  if (!signedIn) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-fg-muted">The pilot is {price} for one deal. Create an account or sign in first; you come back here to pay.</p>
        <div className="flex flex-wrap gap-3">
          <Link href="/app?next=/pilot" className={buttonClass("primary")}>Sign in or create an account</Link>
          {CONTACT && <a href={`mailto:${CONTACT}?subject=${encodeURIComponent("BearCase pilot")}`} className={buttonClass("secondary")}>Ask a question first</a>}
        </div>
      </div>
    );
  }
  if (!status.configured) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-fg-muted">Checkout is not enabled on this deployment. Write to us and we will send an invoice for {price}.</p>
        {CONTACT
          ? <a href={`mailto:${CONTACT}?subject=${encodeURIComponent("BearCase pilot")}`} className={buttonClass("primary")}>Contact us</a>
          : <p className="text-sm text-fg-muted">No contact address is configured on this deployment.</p>}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <Button onClick={() => { setError(null); checkout.mutate(); }} loading={checkout.isPending}>Start a pilot, {price}</Button>
      <p className="text-xs text-fg-muted">Payment is taken by Stripe before delivery. You will be signed in to your workspace when you come back.</p>
      {error && <p role="alert" className="text-sm text-red">{error}</p>}
    </div>
  );
}

/** Stripe returns to `?status=success|cancelled`; the lines here are the only acknowledgement until the webhook marks the purchase paid. */
function Outcome() {
  const status = useSearchParams().get("status");
  if (status === "success") return <p role="status" className="mt-6 rounded-[var(--radius-2)] border border-hairline bg-bg-raised p-4 text-sm">Thank you. Your payment is being confirmed; the purchase below shows &ldquo;paid&rdquo; once Stripe has told us. We will write to you within one business day to arrange the document set.</p>;
  if (status === "cancelled") return <p role="status" className="mt-6 rounded-[var(--radius-2)] border border-hairline bg-bg-raised p-4 text-sm">Checkout was cancelled. Nothing was charged.</p>;
  return null;
}

export default function PilotPage() {
  // The offer is public; purchases need a session. A 401 on status only means "not signed in".
  const offer = useQuery({ queryKey: ["billing-offer"], queryFn: billing.offer, retry: false });
  const status = useQuery({ queryKey: ["billing-status"], queryFn: billing.status, retry: false });
  const signedIn = status.isSuccess;
  const purchases = status.data?.purchases ?? [];
  return (
    <div data-world="ink" className="min-h-svh bg-bg text-fg">
      <SiteNav />
      <main id="main" className="mx-auto max-w-3xl px-6 pb-24 pt-32">
        <h1 className="text-[44px] leading-[1.05] md:text-[56px]">A bounded pilot, one deal at a time.</h1>
        <p className="mt-6 text-lg text-fg-muted">BearCase checks a seller&apos;s documents for financial inconsistencies and shows you what to investigate before buying the business. The pilot puts that on one real deal, with a person checking the output before you rely on it.</p>
        <Suspense fallback={null}><Outcome /></Suspense>

        <section aria-labelledby="scope-h">
          <h2 id="scope-h" className="mt-16 text-3xl">What you get</h2>
          <dl className="mt-6 grid gap-6 md:grid-cols-3">
            {SCOPE.map((s) => <div key={s.title}><dt className="font-medium">{s.title}</dt><dd className="mt-1 text-sm text-fg-muted">{s.body}</dd></div>)}
          </dl>
        </section>

        <section aria-labelledby="limits-h">
          <h2 id="limits-h" className="mt-16 text-3xl">What it does not do</h2>
          <ul className="mt-6 list-disc space-y-2 pl-5 text-fg-muted">{LIMITS.map((l) => <li key={l}>{l}</li>)}</ul>
          <p className="mt-4 text-sm text-fg-muted">How documents are stored, who sees what, and what a citation proves are on <Link href="/trust" className="text-fg underline underline-offset-2">the trust page</Link>.</p>
        </section>

        <section aria-labelledby="price-h">
          <h2 id="price-h" className="mt-16 text-3xl">Price</h2>
          <div className="mt-6 rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-6">
            {offer.isPending && <p className="text-fg-muted">Loading the offer.</p>}
            {offer.isError && <p role="alert" className="text-fg-muted">The offer could not be loaded.{CONTACT && <> Write to <a href={`mailto:${CONTACT}`} className="text-fg underline underline-offset-2">{CONTACT}</a>.</>}</p>}
            {offer.data && (
              <>
                <p className="text-3xl"><span className="num">{fmtPrice(offer.data.pilot.amount_cents, offer.data.pilot.currency)}</span> <span className="text-base text-fg-muted">per deal</span></p>
                <p className="mt-2 text-sm text-fg-muted">{offer.data.pilot.description}</p>
                <div className="mt-6"><StartPilot status={offer.data} signedIn={signedIn} /></div>
              </>
            )}
          </div>
          {purchases.length > 0 && (
            <div className="mt-6">
              <h3 className="text-lg">Your purchases</h3>
              <ul className="mt-2 divide-y divide-hairline border-y border-hairline text-sm">
                {purchases.map((p) => (
                  <li key={p.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2">
                    <span className="num">{fmtPrice(p.amount_cents, p.currency)}</span>
                    <span className="text-fg-muted">{fmtDate(p.created_at)}</span>
                    <span className={p.status === "paid" ? "font-medium" : "text-fg-muted"}>{p.status === "paid" ? "Paid" : p.status === "failed" ? "Failed" : "Pending"}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
        <p className="mt-16 text-xs text-fg-muted">By starting a pilot you agree to the <Link href="/terms" className="underline underline-offset-2">terms of use</Link> and the <Link href="/privacy" className="underline underline-offset-2">privacy notice</Link>.</p>
      </main>
      <SiteFooter />
    </div>
  );
}
