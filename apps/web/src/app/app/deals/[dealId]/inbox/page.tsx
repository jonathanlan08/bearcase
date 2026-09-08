"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useReviewQueue } from "@/components/app/hooks";
import { PageHeader, useDealKicker } from "@/components/app/shell";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { StatusGlyph, STATUS_LABEL } from "@/components/domain/status";
import type { QueueItem } from "@/lib/api";

/** Where each queue item is settled. Claims open with the claim selected; adjustments land on the bridge. */
function href(base: string, item: QueueItem): string {
  switch (item.href_key) {
    case "claims": return item.claim_id ? `${base}/claims?claim=${item.claim_id}` : `${base}/claims`;
    case "financials": return item.adjustment_id ? `${base}/financials#bridge` : `${base}/financials#check-read`;
    case "questions": return `${base}/questions`;
    default: return `${base}/documents`;
  }
}

const GROUP_HINT: Record<string, string> = {
  figures: "Numbers the rules were unsure about. Open the statement and confirm the row, the scale, or the year before the calculations that use it are trusted.",
  discrepancies: "Claims the documents contradict, leave open, or that need a human call. Read the evidence, then confirm, correct, or reject; each decision is recorded under your name.",
  adjustments: "Add-backs the rules accepted or left open without a person's decision. The checked EBITDA counts them until you decide.",
  missing: "Documents the seller has not supplied. Each one is already a question in the export.",
};

/** The review inbox: everything a person still has to decide, in the order to do it. Empty groups stay visible so the
 *  reader sees what has been cleared, not only what remains. */
export default function InboxPage() {
  const { dealId } = useParams<{ dealId: string }>();
  const kicker = useDealKicker();
  const q = useReviewQueue(dealId);
  const base = `/app/deals/${dealId}`;
  const router = useRouter();
  // Keyboard review: J/K move through every item across groups, Enter opens it; the active row is marked, not only coloured.
  const flat = useMemo(() => (q.data?.groups ?? []).flatMap((g) => g.items), [q.data]);
  const [active, setActive] = useState(0);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
      if (e.key === "j" || e.key === "J") { e.preventDefault(); setActive((i) => Math.min(flat.length - 1, i + 1)); }
      else if (e.key === "k" || e.key === "K") { e.preventDefault(); setActive((i) => Math.max(0, i - 1)); }
      else if (e.key === "Enter" && flat[active]) { e.preventDefault(); router.push(href(base, flat[active])); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [flat, active, router, base]);
  useEffect(() => { document.getElementById(`queue-item-${active}`)?.scrollIntoView({ block: "nearest" }); }, [active]);
  return (
    <div>
      <PageHeader kicker={kicker} title="Review queue">
        <p className="mt-2 max-w-3xl text-sm text-fg-muted">What still needs a person, in the order to do it. Items leave the queue when you record a decision or upload what is missing; nothing here is decided for you. <span className="hidden lg:inline">Keys: <kbd className="rounded border border-hairline px-1 font-mono text-[11px]">J</kbd> <kbd className="rounded border border-hairline px-1 font-mono text-[11px]">K</kbd> move, <kbd className="rounded border border-hairline px-1 font-mono text-[11px]">Enter</kbd> open.</span></p>
      </PageHeader>
      <div className="flex flex-col gap-4 p-4 md:p-6">
        {q.isPending && <><Skeleton className="h-24" /><Skeleton className="h-24" /></>}
        {q.isError && <ErrorState detail={String(q.error)} onRetry={() => q.refetch()} />}
        {q.data && q.data.total === 0 && <EmptyState title="Nothing left to decide" body="Every flagged figure, discrepancy, and add-back has a decision, and no document is missing. Export the seller questions or generate the report." action={<Link href={`${base}/questions`} className="text-sm text-accent hover:underline">Open Seller Questions</Link>} />}
        {q.data && q.data.total > 0 && (
          <>
            <p className="text-sm"><span className="num font-medium">{q.data.total}</span> {q.data.total === 1 ? "item needs" : "items need"} a decision.</p>
            {q.data.groups.map((g, gi) => (
              <section key={g.key} aria-labelledby={`q-${g.key}`} className="rounded-[var(--radius-3)] border border-hairline bg-bg-raised">
                <div className="flex flex-wrap items-baseline gap-2 px-5 py-3">
                  <span className="num text-xs text-fg-muted">{gi + 1}</span>
                  <h2 id={`q-${g.key}`} className="text-sm font-medium">{g.title}</h2>
                  <span className="num text-xs text-fg-muted">{g.items.length}</span>
                </div>
                <p className="px-5 pb-3 text-xs text-fg-muted">{GROUP_HINT[g.key]}</p>
                {g.items.length === 0 ? <p className="border-t border-hairline px-5 py-3 text-sm text-fg-muted"><StatusGlyph status="supported" size={12} className="mr-1 inline align-middle" />Nothing here.</p> : (
                  <ol className="divide-y divide-hairline border-t border-hairline">
                    {g.items.map((item) => { const idx = flat.indexOf(item); const isActive = idx === active; return (
                      <li key={item.id} id={`queue-item-${idx}`} aria-current={isActive ? "true" : undefined} className={`flex items-start gap-3 px-5 py-3 text-sm ${isActive ? "border-l-2 border-accent bg-bg-muted/40" : "border-l-2 border-transparent"}`}>
                        <StatusGlyph status={item.status ?? "review_required"} className="mt-1" />
                        <div className="min-w-0 flex-1">
                          <Link href={href(base, item)} className="font-medium hover:underline">{item.title}</Link>
                          {item.status && <span className="ml-2 text-xs text-fg-muted">{STATUS_LABEL[item.status] ?? item.status}</span>}
                          {item.detail && <p className="mt-0.5 line-clamp-2 text-fg-muted">{item.detail}</p>}
                          {item.resolution && <p className="mt-0.5 text-fg-muted"><span className="font-medium text-fg">What would change this:</span> {item.resolution}</p>}
                        </div>
                        <Link href={href(base, item)} className="shrink-0 text-xs text-accent hover:underline">Open</Link>
                      </li>
                    ); })}
                  </ol>
                )}
              </section>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
