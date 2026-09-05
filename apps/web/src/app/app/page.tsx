"use client";

import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api, type Deal } from "@/lib/api";
import { useDeals } from "@/components/app/hooks";
import { Button, buttonClass } from "@/components/ui/button";
import { EmptyState, ErrorState, Skeleton, Wordmark } from "@/components/ui/primitives";
import { Table, td, th } from "@/components/ui/table";
import { StatusGlyph } from "@/components/domain/status";
import { fmtMoney, fmtDate } from "@/lib/format";
import { useMe } from "@/components/app/gate";

export default function DealsPage() {
  const deals = useDeals();
  const me = useMe();
  const router = useRouter();
  const qc = useQueryClient();
  const demo = useMutation({ mutationFn: () => api.post<Deal>("/api/demo/session"), onSuccess: (d) => { qc.invalidateQueries(); router.push(`/app/deals/${d.id}`); } });
  return (
    <div>
      <header className="flex h-14 items-center justify-between border-b border-hairline bg-bg-raised px-4 md:px-6">
        <Link href="/"><Wordmark /></Link>
        <div className="flex items-center gap-3 text-sm text-fg-muted">
          <span>{me.data?.display_name}</span>
          <Link href="/app/deals/new" className={buttonClass("primary", "sm")}>Create a deal</Link>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-6xl px-4 py-8 md:px-6">
        <p className="micro">Deals</p>
        <h1 className="mt-1 text-3xl">Review room</h1>
        <div className="mt-6">
          {deals.isPending && <Skeleton className="h-40 w-full" />}
          {deals.isError && <ErrorState detail={String(deals.error)} onRetry={() => deals.refetch()} />}
          {deals.data && deals.data.length === 0 && (
            <EmptyState title="No deals yet" body="Open the fictional Northstar HVAC deal to see the full workflow, or create a deal and upload your own documents." action={<div className="flex gap-2"><Button onClick={() => demo.mutate()} loading={demo.isPending}>Open the Northstar demo</Button><Link href="/app/deals/new" className={buttonClass("secondary")}>Create a deal</Link></div>} />
          )}
          {deals.data && deals.data.length > 0 && (
            <Table caption="Deals">
              <thead><tr><th className={th}>Deal</th><th className={th}>Industry</th><th className={`${th} text-right`}>Purchase price</th><th className={th}>Documents</th><th className={th}>Claims</th><th className={th}>Updated</th></tr></thead>
              <tbody>
                {deals.data.map((d) => (
                  <tr key={d.id} className="hover:bg-bg-muted/60">
                    <td className={td}><Link href={`/app/deals/${d.id}`} className="font-medium hover:underline">{d.company_name}</Link>{d.is_demo && <span className="micro ml-2 text-[10px]">fictional</span>}</td>
                    <td className={`${td} text-fg-muted`}>{d.industry}</td>
                    <td className={`${td} num text-right`}>{fmtMoney(d.purchase_price)}</td>
                    <td className={`${td} num`}>{d.documents_ready}/{d.document_count}</td>
                    <td className={td}>
                      <span className="inline-flex items-center gap-2">
                        {(["supported", "contradicted", "review_required", "unsupported"] as const).map((s) => (
                          <span key={s} className="inline-flex items-center gap-1 num text-xs" title={s.replace("_", " ")}><StatusGlyph status={s} size={11} />{d.claim_counts[s] ?? 0}</span>
                        ))}
                      </span>
                    </td>
                    <td className={`${td} text-fg-muted`}>{fmtDate(d.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </div>
        {deals.data && deals.data.length > 0 && !deals.data.some((d) => d.is_demo) && (
          <div className="mt-6"><Button variant="secondary" onClick={() => demo.mutate()} loading={demo.isPending}>Add the Northstar demo deal</Button></div>
        )}
      </main>
    </div>
  );
}
