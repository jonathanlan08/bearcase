"use client";

import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { useAudit } from "@/components/app/hooks";
import { PageHeader, useDealKicker } from "@/components/app/shell";
import { ErrorState, Skeleton, EmptyState } from "@/components/ui/primitives";
import { Table, td, th } from "@/components/ui/table";
import { fmtDate } from "@/lib/format";

export default function AuditPage() {
  const { dealId } = useParams<{ dealId: string }>();
  const kicker = useDealKicker();
  const audit = useAudit(dealId);
  const [type, setType] = useState("all");
  const types = useMemo(() => Array.from(new Set((audit.data ?? []).map((e) => e.event_type.split(".")[0]))).sort(), [audit.data]);
  const rows = (audit.data ?? []).filter((e) => type === "all" || e.event_type.startsWith(type));
  return (
    <div>
      <PageHeader kicker={kicker} title="Audit history" actions={<select aria-label="Filter by event type" className="h-8 rounded-[var(--radius-1)] border border-hairline bg-bg-raised px-2 text-sm" value={type} onChange={(e) => setType(e.target.value)}><option value="all">All events</option>{types.map((t) => <option key={t} value={t}>{t}</option>)}</select>} />
      <div className="p-4 md:p-6">
        {audit.isPending && <Skeleton className="h-64" />}
        {audit.isError && <ErrorState detail={String(audit.error)} onRetry={() => audit.refetch()} />}
        {audit.data && audit.data.length === 0 && <EmptyState title="No events yet" />}
        {rows.length > 0 && (
          <Table caption="Audit events">
            <thead><tr><th className={th}>Time</th><th className={th}>Actor</th><th className={th}>Event</th><th className={th}>Summary</th><th className={th}>Details</th></tr></thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id}>
                  <td className={`${td} num whitespace-nowrap text-xs text-fg-muted`}>{fmtDate(e.created_at)}</td>
                  <td className={`${td} whitespace-nowrap`}>{e.user_name}</td>
                  <td className={`${td} font-mono text-xs`}>{e.event_type}</td>
                  <td className={td}>{e.summary}</td>
                  <td className={td}>{Object.keys(e.payload).length > 0 && <details><summary className="cursor-pointer text-xs text-accent">diff</summary><pre className="mt-1 max-w-md overflow-x-auto rounded-[var(--radius-1)] bg-bg-muted p-2 font-mono text-[11px]">{JSON.stringify(e.payload, null, 1)}</pre></details>}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </div>
    </div>
  );
}
