"use client";

import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { useAudit } from "@/components/app/hooks";
import { useUsage } from "@/components/app/workflow-hooks";
import { PageHeader, useDealKicker } from "@/components/app/shell";
import { ErrorState, Panel, Skeleton, EmptyState } from "@/components/ui/primitives";
import { Table, td, th } from "@/components/ui/table";
import { fmtBytes, fmtDateTime, fmtInt, localZoneName, titleCase } from "@/lib/format";

/** Sentences for the API's event codes (see `record(...)` call sites in apps/api). Unknown codes fall back to the code in words. */
const EVENT_TEXT: Record<string, string> = {
  "deal.created": "Deal created",
  "deal.seeded": "Demo deal seeded",
  "deal.process_requested": "Document processing requested",
  "deal.analyzed": "Analysis completed",
  "deal.asked": "Question asked",
  "document.uploaded": "Document uploaded",
  "document.rejected": "Upload rejected",
  "document.reprocess_requested": "Document read again",
  "document.deleted": "Document deleted",
  "evidence.opened": "Evidence opened",
  "seller_questions.exported": "Questions for the seller exported",
  "review_dataset.exported": "Review dataset exported",
  "claim.accept": "Assessment confirmed",
  "claim.reject": "Finding rejected",
  "claim.correct": "Claim corrected",
  "claim.undo": "Decision undone",
  "adjustment.decided": "Add-back decision recorded",
  "scenario.created": "Scenario created",
  "scenario.assumptions_updated": "Assumptions updated",
  "scenario.run": "Scenario run",
  "report.requested": "Report requested",
  "report.generated": "Report generated",
  "chat.reply": "Chat reply recorded",
  "user.registered": "Account registered",
};
const GROUP_LABEL: Record<string, string> = { deal: "Deal", document: "Documents", evidence: "Evidence", claim: "Claim reviews", adjustment: "Add-back decisions", scenario: "Scenarios", report: "Reports", seller_questions: "Questions for the seller", review_dataset: "Review dataset", chat: "Chat", user: "Account" };

function eventText(eventType: string): string {
  return EVENT_TEXT[eventType] ?? titleCase(eventType.replace(".", " "));
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 4 });

/** What the deal has used: the assistant's messages and tokens, the documents read, the storage held, and a cost estimate from a fixed price table. */
function UsagePanel({ dealId }: { dealId: string }) {
  const usage = useUsage(dealId);
  const u = usage.data;
  const models = u ? Object.entries(u.chat.by_model).sort((a, b) => b[1] - a[1]) : [];
  return (
    <Panel title="Usage" className="mb-4">
      {usage.isPending && <Skeleton className="h-20" />}
      {usage.isError && <p className="text-sm text-fg-muted">Usage could not be loaded for this deal.</p>}
      {u && (
        <>
          <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
            <div><dt className="text-xs text-fg-muted">Assistant messages</dt><dd className="num mt-0.5 font-medium">{fmtInt(u.chat.messages)}</dd></div>
            <div><dt className="text-xs text-fg-muted">Tokens in / out</dt><dd className="num mt-0.5 font-medium">{fmtInt(u.chat.input_tokens)} / {fmtInt(u.chat.output_tokens)}</dd></div>
            <div><dt className="text-xs text-fg-muted">Tool calls</dt><dd className="num mt-0.5 font-medium">{fmtInt(u.chat.tool_calls)}</dd></div>
            <div><dt className="text-xs text-fg-muted">Documents read</dt><dd className="mt-0.5 font-medium"><span className="num">{fmtInt(u.documents.count)}</span> <span className="text-xs font-normal text-fg-muted">(<span className="num">{fmtInt(u.documents.pages)}</span> pages, <span className="num">{fmtInt(u.documents.rows)}</span> rows, {fmtBytes(u.documents.bytes)})</span></dd></div>
            <div><dt className="text-xs text-fg-muted">Storage held</dt><dd className="num mt-0.5 font-medium">{fmtBytes(u.storage_bytes)}</dd></div>
            <div><dt className="text-xs text-fg-muted">Estimated model cost</dt><dd className="num mt-0.5 font-medium">{u.cost_estimate_usd === null ? "n/a" : usd.format(u.cost_estimate_usd)}</dd></div>
          </dl>
          {models.length > 0 && <p className="mt-3 text-xs text-fg-muted">By model: {models.map(([m, n]) => `${m} (${fmtInt(n)})`).join(", ")}.</p>}
          <p className="mt-2 text-xs text-fg-muted">{u.pricing_note} The estimate uses a fixed price table, not the provider&apos;s invoice; storage and processing time are counted so you can see what one deal costs to run.</p>
        </>
      )}
    </Panel>
  );
}

export default function AuditPage() {
  const { dealId } = useParams<{ dealId: string }>();
  const kicker = useDealKicker();
  const audit = useAudit(dealId);
  const [type, setType] = useState("all");
  const types = useMemo(() => Array.from(new Set((audit.data ?? []).map((e) => e.event_type.split(".")[0]))).sort(), [audit.data]);
  const rows = (audit.data ?? []).filter((e) => type === "all" || e.event_type.startsWith(`${type}.`));
  return (
    <div>
      <PageHeader kicker={kicker} title="Audit history" actions={<select aria-label="Filter by event type" className="h-8 rounded-[var(--radius-1)] border border-hairline bg-bg-raised px-2 text-sm" value={type} onChange={(e) => setType(e.target.value)}><option value="all">All events</option>{types.map((t) => <option key={t} value={t}>{GROUP_LABEL[t] ?? titleCase(t)}</option>)}</select>}>
        <p className="mt-2 max-w-3xl text-sm text-fg-muted">Every change to this deal, who made it, and when. Reviewer decisions never overwrite the AI’s original output; they are added here as separate entries.</p>
      </PageHeader>
      <div className="p-4 md:p-6">
        <UsagePanel dealId={dealId} />
        {audit.isPending && <Skeleton className="h-64" />}
        {audit.isError && <ErrorState detail={String(audit.error)} onRetry={() => audit.refetch()} />}
        {audit.data && audit.data.length === 0 && <EmptyState title="No events yet" body="Uploads, analysis runs, reviewer decisions, scenario runs, and reports will appear here." />}
        {audit.data && audit.data.length > 0 && rows.length === 0 && <p className="text-sm text-fg-muted">No events of this kind yet.</p>}
        {rows.length > 0 && (
          <>
            <p className="mb-3 text-xs text-fg-muted">Times are shown in your local time zone ({localZoneName()}).</p>
            <Table caption="Audit events">
              <thead><tr><th className={th}>When</th><th className={th}>Who</th><th className={th}>What happened</th><th className={th}>Technical details</th></tr></thead>
              <tbody>
                {rows.map((e) => (
                  <tr key={e.id}>
                    <td className={`${td} num whitespace-nowrap text-xs text-fg-muted`}>{fmtDateTime(e.created_at)}</td>
                    <td className={`${td} whitespace-nowrap`}>{e.user_name}</td>
                    <td className={td}><p className="font-medium">{eventText(e.event_type)}</p><p className="text-sm text-fg-muted">{e.summary}</p></td>
                    <td className={td}>
                      <details>
                        <summary className="cursor-pointer text-xs text-accent">Show</summary>
                        <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-[11px] text-fg-muted">
                          <dt>Event code</dt><dd className="font-mono">{e.event_type}</dd>
                          <dt>Object</dt><dd className="font-mono">{e.object_type}{e.object_id ? ` ${e.object_id}` : ""}</dd>
                          <dt>Event id</dt><dd className="font-mono">{e.id}</dd>
                        </dl>
                        {Object.keys(e.payload).length > 0 && <pre className="mt-1 max-w-md overflow-x-auto rounded-[var(--radius-1)] bg-bg-muted p-2 font-mono text-[11px]">{JSON.stringify(e.payload, null, 1)}</pre>}
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </>
        )}
      </div>
    </div>
  );
}
