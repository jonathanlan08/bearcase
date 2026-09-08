"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { billing, fmtPrice } from "@/lib/api";
import { buttonClass } from "@/components/ui/button";

const CONTACT = process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? "";

/** The commercial next step on the landing page: the public pilot price from the API (no session needed), the scope in
 *  one line, and a reachable person. When the API is unreachable the scope and the links stay; only the price is absent. */
export function PilotOffer() {
  const offer = useQuery({ queryKey: ["billing-offer"], queryFn: billing.offer, retry: false, staleTime: 5 * 60_000 });
  const price = offer.data ? fmtPrice(offer.data.pilot.amount_cents, offer.data.pilot.currency) : null;
  return (
    <div className="rounded-[var(--radius-2)] border border-hairline bg-bg-raised p-6 md:p-8">
      <p className="micro text-fg-muted">The paid pilot</p>
      <p className="mt-2 text-2xl md:text-3xl">
        One real deal, checked end to end{price ? <>, <span className="num">{price}</span></> : ""}.
      </p>
      <p className="mt-3 max-w-[560px] text-[15px] leading-relaxed text-fg-muted">
        You upload one deal. BearCase runs the checks, a person reads every contradiction and add-back decision, and you get the questions and the report within five business days.
      </p>
      <div className="mt-5 flex flex-wrap gap-3">
        <Link href="/pilot" className={buttonClass("primary")}>{offer.data?.configured ? "Start a pilot" : "Read the pilot terms"}</Link>
        {CONTACT
          ? <a href={`mailto:${CONTACT}?subject=${encodeURIComponent("BearCase pilot")}`} className={buttonClass("secondary")}>Talk to a person first</a>
          : <Link href="/pilot" className={buttonClass("secondary")}>What the pilot covers</Link>}
      </div>
      <p className="mt-4 text-xs text-fg-muted">No customer results yet. The first pilots will be reported here, including what the checks missed.</p>
    </div>
  );
}
