"use client";

import { useState } from "react";
import { Dialog } from "radix-ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type ClaimDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Field, inputClass } from "@/components/ui/field";
import { qk } from "@/components/app/hooks";
import { useToast } from "@/components/ui/toast";

type Action = "accept" | "reject" | "correct" | "undo";

/** What each reviewer action is called in the UI. "accept" is the API verb; on screen it confirms the AI assessment. */
export const ACTION_LABEL: Record<Action, string> = { accept: "Assessment confirmed", reject: "Finding rejected", correct: "Correction recorded", undo: "Decision undone" };

/** Past-tense sentence fragments for the decision history: "{user} confirmed the assessment". */
export const ACTION_VERB: Record<string, string> = { accept: "confirmed the assessment", reject: "rejected the finding", correct: "corrected the claim", undo: "undid the previous decision" };

export function useReview(dealId: string) {
  const qc = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ claimId, body }: { claimId: string; body: { action: Action; corrected_value?: string; corrected_unit?: string; resulting_status?: string; note?: string } }) => api.post<ClaimDetail>(`/api/deals/${dealId}/claims/${claimId}/review`, body),
    onSuccess: (d, vars) => {
      qc.invalidateQueries({ queryKey: qk.claims(dealId) });
      qc.invalidateQueries({ queryKey: qk.claim(dealId, vars.claimId) });
      qc.invalidateQueries({ queryKey: qk.audit(dealId) });
      qc.invalidateQueries({ queryKey: qk.summary(dealId) });
      if (vars.body.action !== "undo") toast({ title: ACTION_LABEL[vars.body.action], description: "Recorded as a separate entry. The original AI output is unchanged.", tone: "success", action: { label: "Undo", onClick: () => api.post(`/api/deals/${dealId}/claims/${vars.claimId}/review`, { action: "undo" }).then(() => { qc.invalidateQueries({ queryKey: qk.claims(dealId) }); qc.invalidateQueries({ queryKey: qk.claim(dealId, vars.claimId) }); }) } });
    },
    onError: (e) => toast({ title: "Could not record decision", description: String(e), tone: "error" }),
  });
}

export function CorrectionDialog({ open, onOpenChange, claim, onSubmit, pending, defaultMode = "correct" }: { open: boolean; onOpenChange: (o: boolean) => void; claim: ClaimDetail | null; onSubmit: (body: { action: "correct" | "reject"; corrected_value?: string; corrected_unit?: string; resulting_status?: string; note: string }) => void; pending: boolean; defaultMode?: "correct" | "reject" }) {
  const [mode, setMode] = useState<"correct" | "reject">(defaultMode);
  const [value, setValue] = useState("");
  const [unit, setUnit] = useState<string>(claim?.claimed_unit && claim.claimed_unit !== "text" ? claim.claimed_unit : "pct");
  const [status, setStatus] = useState("review_required");
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  if (!claim) return null;
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink-950/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(560px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-[var(--radius-3)] border border-hairline bg-bg-raised p-5 shadow-[var(--shadow-2)] outline-none">
          <Dialog.Title className="text-lg font-medium">Reviewer decision</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-fg-muted">The original extraction stays on the claim. Your decision is recorded as a separate, auditable entry with your name and a note.</Dialog.Description>
          <p className="mt-3 rounded-[var(--radius-2)] bg-bg-muted p-2 text-sm">{claim.claim_text}</p>
          <div className="mt-4 flex flex-wrap gap-4 text-sm" role="radiogroup" aria-label="Decision type">
            {(["correct", "reject"] as const).map((m) => <label key={m} className="flex items-center gap-2"><input type="radio" name="mode" checked={mode === m} onChange={() => setMode(m)} />{m === "correct" ? "Correct the value or status" : "Reject the AI finding"}</label>)}
          </div>
          <p className="mt-1 text-xs text-fg-muted">{mode === "correct" ? "Use this when the extractor read the sentence wrong or the status should be different." : "Use this when the sentence is not really a claim, or the finding should not count at all."}</p>
          <form className="mt-4 flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); if (!note.trim()) { setErr("A note is required."); return; } setErr(null); onSubmit(mode === "correct" ? { action: "correct", corrected_value: value || undefined, corrected_unit: value ? unit : undefined, resulting_status: status, note } : { action: "reject", note }); }}>
            {mode === "correct" && (
              <div className="grid grid-cols-[1fr_120px] gap-3">
                <Field label="Corrected value" help="Leave blank to change only the status.">{(p) => <input {...p} className={inputClass(p.invalid)} value={value} onChange={(e) => setValue(e.target.value)} inputMode="decimal" />}</Field>
                <Field label="Unit">{(p) => <select id={p.id} className={inputClass(false)} value={unit} onChange={(e) => setUnit(e.target.value)}>{["pct", "usd", "multiple", "years", "months", "count", "text"].map((u) => <option key={u} value={u}>{u}</option>)}</select>}</Field>
              </div>
            )}
            {mode === "correct" && (
              <Field label="Resulting status">{(p) => <select id={p.id} className={inputClass(false)} value={status} onChange={(e) => setStatus(e.target.value)}>{["supported", "contradicted", "unsupported", "review_required"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}</select>}</Field>
            )}
            <Field label="Note" required error={err ?? undefined} help="Why this decision was made; appears in the audit history and the report.">{(p) => <textarea id={p.id} aria-describedby={p.describedBy} aria-invalid={p.invalid} className={inputClass(p.invalid, "h-24 py-2")} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
            <div className="mt-2 flex justify-end gap-2"><Dialog.Close asChild><Button type="button" variant="secondary">Cancel</Button></Dialog.Close><Button type="submit" loading={pending}>{mode === "correct" ? "Record correction" : "Reject finding"}</Button></div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
