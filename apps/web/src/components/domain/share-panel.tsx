"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Dialog } from "radix-ui";
import { Users, X } from "lucide-react";
import { errorDetail, members as membersApi, type DealMembers, type MemberRole } from "@/lib/api";
import { useMe } from "@/components/app/gate";
import { Button } from "@/components/ui/button";
import { Field, inputClass } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/primitives";

export const MAX_MEMBERS = 5;

/** What each role may do, in the words the API enforces. Shown beside the role select so the owner picks knowingly. */
export const ROLE_HELP: Record<MemberRole, string> = {
  viewer: "Reads everything, asks the deal, and exports the seller questions. Cannot upload, delete, run analysis, decide, or run scenarios.",
  editor: "Everything you can do except delete the deal, manage members, or export the review dataset.",
};

export const mqk = { members: (dealId: string) => ["members", dealId] as const };
export const useMembers = (dealId: string) => useQuery({ queryKey: mqk.members(dealId), queryFn: () => membersApi.list(dealId) });

/** Owner-only controls appear when the signed-in address is the owner's; comparison is case-insensitive like the API's. */
export function isOwner(data: DealMembers | undefined, email: string | undefined): boolean {
  return !!data && !!email && data.owner.email.toLowerCase() === email.toLowerCase();
}

/** Members list, invite form, and remove actions for one deal. Rendered inside the Share dialog; testable on its own. */
export function SharePanel({ dealId }: { dealId: string }) {
  const qc = useQueryClient();
  const me = useMe();
  const list = useMembers(dealId);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<MemberRole>("viewer");
  const [error, setError] = useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: mqk.members(dealId) });
  const invite = useMutation({
    mutationFn: () => membersApi.invite(dealId, email.trim(), role),
    onSuccess: () => { setEmail(""); setError(null); refresh(); },
    onError: (e) => setError(errorDetail(e, "The invite could not be sent.")),
  });
  const remove = useMutation({
    mutationFn: (memberId: string) => membersApi.remove(dealId, memberId),
    onSuccess: () => { setError(null); refresh(); },
    onError: (e) => setError(errorDetail(e, "The member could not be removed.")),
  });

  if (list.isPending || me.isPending) return <div className="flex flex-col gap-2"><Skeleton className="h-5 w-40" /><Skeleton className="h-16 w-full" /></div>;
  if (list.isError || !list.data) return <p role="alert" className="text-sm text-red">{errorDetail(list.error, "The member list could not be loaded.")}</p>;

  const data = list.data;
  const owner = isOwner(data, me.data?.email);
  const myEmail = me.data?.email.toLowerCase();
  const verified = me.data?.email_verified === true;
  const full = data.members.length >= MAX_MEMBERS;
  const canInvite = owner && verified && !full;

  return (
    <div className="flex flex-col gap-5 text-sm">
      <div>
        <p className="text-xs font-medium text-fg-muted">Owner</p>
        <p className="mt-1">{data.owner.display_name} <span className="text-fg-muted">({data.owner.email})</span></p>
      </div>
      <div>
        <p className="text-xs font-medium text-fg-muted">Members <span className="num">{data.members.length}/{MAX_MEMBERS}</span></p>
        {data.members.length === 0
          ? <p className="mt-1 text-fg-muted">Nobody else can open this deal yet.</p>
          : (
            <ul className="mt-1 divide-y divide-hairline border-y border-hairline">
              {data.members.map((m) => {
                const self = m.email.toLowerCase() === myEmail;
                return (
                  <li key={m.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                    <span className="min-w-0 flex-1 truncate">{m.email}{self && <span className="text-fg-muted"> (you)</span>}</span>
                    <span className="text-xs text-fg-muted">{m.role === "editor" ? "Editor" : "Viewer"}</span>
                    <span className={`text-xs ${m.accepted ? "text-fg-muted" : "text-amber"}`}>{m.accepted ? "Accepted" : "Invite pending"}</span>
                    {(owner || self) && (
                      <Button variant="ghost" size="sm" onClick={() => remove.mutate(m.id)} loading={remove.isPending && remove.variables === m.id} aria-label={self && !owner ? "Leave this deal" : `Remove ${m.email}`}>{self && !owner ? "Leave" : "Remove"}</Button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
      </div>
      {owner && (
        <form className="flex flex-col gap-3 rounded-[var(--radius-2)] border border-hairline p-3" onSubmit={(e) => { e.preventDefault(); if (canInvite) invite.mutate(); }} aria-label="Invite a collaborator">
          <p className="font-medium">Invite a collaborator</p>
          {!verified && <p className="text-xs text-amber">Verify your email address before sharing a deal. The banner at the top of the workspace can resend the link.</p>}
          {verified && full && <p className="text-xs text-fg-muted">This deal has the maximum of {MAX_MEMBERS} members. Remove one to invite another.</p>}
          <Field label="Email" required>{(p) => <input {...p} type="email" className={inputClass(p.invalid)} value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="off" disabled={!canInvite} />}</Field>
          <Field label="Role" help={ROLE_HELP[role]}>{(p) => (
            <select id={p.id} aria-describedby={p.describedBy} className={inputClass(false)} value={role} onChange={(e) => setRole(e.target.value as MemberRole)} disabled={!canInvite}>
              <option value="viewer">Viewer</option>
              <option value="editor">Editor</option>
            </select>
          )}</Field>
          <Button type="submit" variant="secondary" size="sm" className="self-start" loading={invite.isPending} disabled={!canInvite || !email.trim()}>Send invite</Button>
          <p className="text-xs text-fg-muted">The invite goes by email and works for 7 days. The person must sign in with that exact address to accept it.</p>
        </form>
      )}
      {error && <p role="alert" className="text-sm text-red">{error}</p>}
    </div>
  );
}

/** The header button that opens the Share dialog. */
export function ShareButton({ dealId }: { dealId: string }) {
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <Button variant="secondary" size="sm" icon={<Users size={14} />}>Share</Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink-950/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[85svh] w-[min(92vw,520px)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-5 shadow-[var(--shadow-2)]">
          <div className="flex items-start justify-between gap-3">
            <div>
              <Dialog.Title className="text-lg font-semibold">Share this deal</Dialog.Title>
              <Dialog.Description className="mt-1 text-xs text-fg-muted">Members act under their own name; the audit history records who did what.</Dialog.Description>
            </div>
            <Dialog.Close className="rounded-[var(--radius-1)] p-1.5 text-fg-muted hover:bg-bg-muted" aria-label="Close"><X size={16} /></Dialog.Close>
          </div>
          <div className="mt-4"><SharePanel dealId={dealId} /></div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
