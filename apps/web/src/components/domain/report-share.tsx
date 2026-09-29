"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Dialog } from "radix-ui";
import { Link2, X } from "lucide-react";
import { errorDetail, reportShares, type ReportShareCreated } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Field, inputClass } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/primitives";
import { fmtDateTime } from "@/lib/format";

export const sqk = { shares: (dealId: string, reportId: string) => ["report-shares", dealId, reportId] as const };

const EXPIRY: Array<{ value: string; label: string; days: number | null }> = [
  { value: "none", label: "Until revoked", days: null },
  { value: "7", label: "7 days", days: 7 },
  { value: "30", label: "30 days", days: 30 },
];

/** The full address of a share path on this site; the server returns the path, the browser knows its own origin. */
export function shareUrl(path: string, origin: string = typeof window === "undefined" ? "" : window.location.origin): string {
  return `${origin}${path}`;
}

/** Create a read-only link to one validated report, copy it, and see or revoke the links that are still live. */
export function ReportSharePanel({ dealId, reportId }: { dealId: string; reportId: string }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: sqk.shares(dealId, reportId), queryFn: () => reportShares.list(dealId, reportId), retry: false });
  const [expiry, setExpiry] = useState("none");
  const [created, setCreated] = useState<ReportShareCreated | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: sqk.shares(dealId, reportId) });
  const create = useMutation({
    mutationFn: () => reportShares.create(dealId, reportId, EXPIRY.find((e) => e.value === expiry)?.days ?? null),
    onSuccess: (s) => { setCreated(s); setCopied(false); setError(null); refresh(); },
    onError: (e) => setError(errorDetail(e, "The link could not be created.")),
  });
  const revoke = useMutation({
    mutationFn: (shareId: string) => reportShares.revoke(dealId, reportId, shareId),
    onSuccess: (_h, shareId) => { if (created?.id === shareId) setCreated(null); setError(null); refresh(); },
    onError: (e) => setError(errorDetail(e, "The link could not be revoked.")),
  });
  const copy = async (url: string) => {
    try { await navigator.clipboard.writeText(url); setCopied(true); } catch { setError("The browser blocked clipboard access. Select the link and copy it by hand."); }
  };

  if (list.isPending) return <div className="flex flex-col gap-2"><Skeleton className="h-5 w-40" /><Skeleton className="h-16 w-full" /></div>;
  if (list.isError) return <p role="alert" className="text-sm text-red">{errorDetail(list.error, "The links could not be loaded.")}</p>;

  const active = (list.data ?? []).filter((s) => s.active);
  const inactive = (list.data ?? []).length - active.length;
  const url = created ? shareUrl(created.path) : "";

  return (
    <div className="flex flex-col gap-5 text-sm">
      {created ? (
        <div className="flex flex-col gap-2 rounded-[var(--radius-2)] border border-hairline p-3">
          <label htmlFor="share-url" className="font-medium">Your link</label>
          <div className="flex gap-2">
            <input id="share-url" readOnly value={url} className={inputClass(false, "font-mono text-xs")} onFocus={(e) => e.currentTarget.select()} />
            <Button type="button" variant="secondary" size="sm" className="h-10" onClick={() => copy(url)}>{copied ? "Copied" : "Copy"}</Button>
          </div>
          <p className="text-xs text-fg-muted" aria-live="polite">Copy it now. BearCase stores only a fingerprint of the link, so it cannot show it again. {created.expires_at ? `It stops working on ${fmtDateTime(created.expires_at)}.` : "It works until you revoke it."}</p>
        </div>
      ) : (
        <form className="flex flex-col gap-3 rounded-[var(--radius-2)] border border-hairline p-3" aria-label="Create a read-only link" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <Field label="Link works" help="Anyone with the link can read this report version, with each citation's document name and passage. Nothing else in the deal.">{(p) => (
            <select id={p.id} aria-describedby={p.describedBy} className={inputClass(false)} value={expiry} onChange={(e) => setExpiry(e.target.value)}>
              {EXPIRY.map((e) => <option key={e.value} value={e.value}>{e.label}</option>)}
            </select>
          )}</Field>
          <Button type="submit" variant="secondary" size="sm" className="self-start" loading={create.isPending}>Create link</Button>
        </form>
      )}
      <div>
        <p className="text-xs font-medium text-fg-muted">Live links <span className="num">{active.length}</span></p>
        {active.length === 0
          ? <p className="mt-1 text-fg-muted">No live links to this report.</p>
          : (
            <ul className="mt-1 divide-y divide-hairline border-y border-hairline">
              {active.map((s) => (
                <li key={s.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                  <span className="min-w-0 flex-1">Created {fmtDateTime(s.created_at)}{s.created_by ? ` by ${s.created_by}` : ""}</span>
                  <span className="text-xs text-fg-muted">{s.expires_at ? `Expires ${fmtDateTime(s.expires_at)}` : "No expiry"}</span>
                  <Button variant="ghost" size="sm" onClick={() => revoke.mutate(s.id)} loading={revoke.isPending && revoke.variables === s.id} aria-label={`Revoke the link created ${fmtDateTime(s.created_at)}`}>Revoke</Button>
                </li>
              ))}
            </ul>
          )}
        {inactive > 0 && <p className="mt-2 text-xs text-fg-muted">{inactive} revoked or expired link{inactive === 1 ? "" : "s"} no longer open{inactive === 1 ? "s" : ""} the report.</p>}
      </div>
      {error && <p role="alert" className="text-sm text-red">{error}</p>}
    </div>
  );
}

/** The report header button. Shown for validated reports only; the API refuses the rest and refuses viewers. */
export function ReportShareButton({ dealId, reportId, versionNo }: { dealId: string; reportId: string; versionNo: number }) {
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <Button variant="secondary" size="sm" icon={<Link2 size={14} />}>Share link</Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink-950/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[85svh] w-[min(92vw,520px)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-5 shadow-[var(--shadow-2)]">
          <div className="flex items-start justify-between gap-3">
            <div>
              <Dialog.Title className="text-lg font-semibold">Share report version {versionNo}</Dialog.Title>
              <Dialog.Description className="mt-1 text-xs text-fg-muted">A read-only page for someone without an account: a partner, a lender, an adviser. Revoke the link and the page stops opening.</Dialog.Description>
            </div>
            <Dialog.Close className="rounded-[var(--radius-1)] p-1.5 text-fg-muted hover:bg-bg-muted" aria-label="Close"><X size={16} /></Dialog.Close>
          </div>
          <div className="mt-4"><ReportSharePanel dealId={dealId} reportId={reportId} /></div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
