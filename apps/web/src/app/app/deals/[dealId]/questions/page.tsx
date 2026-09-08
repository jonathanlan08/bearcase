"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Copy, Download } from "lucide-react";
import { api, type Evidence, type SellerQuestion } from "@/lib/api";
import { qk, useDeal, useEvidence } from "@/components/app/hooks";
import { useSellerQuestions, wqk } from "@/components/app/workflow-hooks";
import { PageHeader, useDealKicker } from "@/components/app/shell";
import { Button, buttonClass } from "@/components/ui/button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { SeverityChip, StatusGlyph } from "@/components/domain/status";
import { CitationChip } from "@/components/domain/citation";
import { DocumentViewer, type ViewerTarget } from "@/components/domain/document-viewer";
import { useToast } from "@/components/ui/toast";
import { askTheDeal } from "@/lib/chat-bus";
import { useSellerReplies } from "@/components/app/hooks";
import { sellerReplies, type ReplyOutcome, type SellerReply } from "@/lib/api";
import { titleCase, fmtDate } from "@/lib/format";

const SEVERITY_ORDER = ["critical", "high", "medium", "low"];
/** What each severity means for the buyer, as the group heading. */
const SEVERITY_HEADING: Record<string, string> = { critical: "Ask before anything else", high: "Ask before you sign", medium: "Ask during the review", low: "Worth asking" };
/** Where a question came from, in the words the overview uses for findings. */
const KIND_LABEL: Record<string, string> = { contradiction: "Documents disagree", unsupported: "No evidence found", missing_document: "Document missing", covenant: "Loan coverage", concentration: "Customer concentration", risk: "Risk", integrity: "Document integrity" };
const MAX_CHIPS = 4;
const ACTION = "text-[11px] text-fg-muted underline-offset-2 hover:text-fg hover:underline";

/** Questions by severity, most serious first, each numbered once across the whole page so the copy and the screen agree. */
interface Group { severity: string; items: Array<{ q: SellerQuestion; n: number }> }

function groupBySeverity(questions: SellerQuestion[]): Group[] {
  const rank = (s: string) => { const i = SEVERITY_ORDER.indexOf(s); return i === -1 ? SEVERITY_ORDER.length : i; };
  const map = new Map<string, SellerQuestion[]>();
  for (const q of questions) map.set(q.severity, [...(map.get(q.severity) ?? []), q]);
  const sorted = Array.from(map, ([severity, items]) => ({ severity, items })).sort((a, b) => rank(a.severity) - rank(b.severity));
  let n = 0;
  return sorted.map((g) => ({ severity: g.severity, items: g.items.map((q) => ({ q, n: ++n })) }));
}

/** Plain text for the clipboard: the checked questions only, numbered as on screen, each with its reason and sources. */
function questionsText(company: string, groups: Group[], included: (id: string) => boolean): string {
  const lines: string[] = [`Questions for the seller: ${company}`];
  for (const g of groups) {
    const items = g.items.filter(({ q }) => included(q.id));
    if (items.length === 0) continue;
    lines.push("", `${SEVERITY_HEADING[g.severity] ?? titleCase(g.severity)} (${g.severity})`);
    for (const { q, n } of items) {
      lines.push(`${n}. ${q.question}`, `   Why we ask: ${q.why}`);
      if (q.document_names.length > 0) lines.push(`   Sources: ${q.document_names.join(", ")}`);
    }
  }
  return lines.join("\n");
}

/** Hand a fetched export to the browser's save dialog. */
function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function QuestionsPage() {
  const { dealId } = useParams<{ dealId: string }>();
  const kicker = useDealKicker();
  const deal = useDeal(dealId);
  const qc = useQueryClient();
  const { toast } = useToast();
  const questions = useSellerQuestions(dealId);
  const replies = useSellerReplies(dealId);
  const [replying, setReplying] = useState<string | null>(null);
  // Unchecked questions stay out of "Copy all"; everything is included until the user says otherwise.
  const [excluded, setExcluded] = useState<ReadonlySet<string>>(() => new Set());
  const [copied, setCopied] = useState(false);
  const [viewer, setViewer] = useState<ViewerTarget | null>(null);
  const base = `/app/deals/${dealId}`;
  const included = (id: string) => !excluded.has(id);
  const toggle = (id: string) => setExcluded((prev) => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  const all = questions.data?.questions ?? [];
  const groups = groupBySeverity(all);
  const includedCount = all.filter((q) => included(q.id)).length;
  const company = deal.data?.company_name ?? "this deal";

  const copyAll = async () => {
    try {
      await navigator.clipboard.writeText(questionsText(company, groups, included));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      toast({ title: "Could not copy", description: "The browser blocked clipboard access. Download the file instead.", tone: "error" });
    }
  };
  const download = useMutation({
    mutationFn: () => {
      const ids = all.filter((q) => included(q.id)).map((q) => q.id);
      const sel = ids.length === all.length ? "" : `&ids=${encodeURIComponent(ids.join(","))}`;
      return api.download(`/api/deals/${dealId}/seller-questions/export?format=md${sel}`, "seller-questions.md");
    },
    onSuccess: ({ blob, filename }) => {
      saveBlob(blob, filename);
      // The export is the "questions" step of the workflow and an audit entry; both read from the server.
      qc.invalidateQueries({ queryKey: wqk.progress(dealId) });
      qc.invalidateQueries({ queryKey: qk.audit(dealId) });
      toast({ title: "Questions downloaded", description: `${filename} is ready to send to the seller.`, tone: "success" });
    },
    onError: (e) => toast({ title: "Could not download the questions", description: String(e), tone: "error" }),
  });
  const openEvidence = (e: Evidence) => setViewer({ documentId: e.document_id, documentName: e.document_name, evidenceId: e.id, locator: e.locator });
  const draft = (q: SellerQuestion) => askTheDeal(`Draft a question for the seller about: ${q.question}. Cite the evidence ids.`, { send: true });

  return (
    <div>
      <PageHeader kicker={kicker} title="Questions for the seller" actions={
        all.length > 0 && (
          <>
            <Button variant="secondary" size="sm" icon={<Copy size={14} />} onClick={copyAll} aria-live="polite">{copied ? "Copied" : "Copy all"}</Button>
            <Button variant="secondary" size="sm" icon={<Download size={14} />} onClick={() => download.mutate()} loading={download.isPending}>Download .md</Button>
          </>
        )
      }>
        <p className="mt-2 max-w-3xl text-sm text-fg-muted">Every question here comes from a finding: a claim the documents disagree with, a claim with nothing behind it, or a document that is missing. Each one carries the evidence that raised it, so the seller can answer with a page or a cell rather than a story. Untick the ones you do not want to send, then copy the list or download it; only the ticked questions leave the workspace.</p>
        {questions.data && all.length > 0 && (
          <p className="mt-2 text-xs text-fg-muted">
            Built from <span className="num">{questions.data.generated_from.findings}</span> findings and <span className="num">{questions.data.generated_from.claims}</span> claims, the same list as the report&apos;s management questions. <span className="num">{includedCount}</span> of <span className="num">{all.length}</span> ticked. Copy and download both send only the ticked questions; the report keeps every question.
          </p>
        )}
      </PageHeader>
      <div className="p-4 md:p-6">
        {questions.isPending && <div><Skeleton className="h-8 w-56" /><Skeleton className="mt-4 h-24" /><Skeleton className="mt-2 h-24" /></div>}
        {questions.isError && <ErrorState detail={String(questions.error)} onRetry={() => questions.refetch()} />}
        {questions.data && all.length === 0 && (
          <EmptyState title="No questions yet" body="Questions appear once analysis has found something to ask about: a contradiction, a claim without evidence, or a missing document. Add the seller's documents and run analysis first." action={<Link href={`${base}/documents`} className={buttonClass("primary", "sm")}>Open the Deal Room</Link>} />
        )}
        {groups.length > 0 && (
          <div className="flex max-w-[76ch] flex-col gap-8">
            {groups.map((g) => (
              <section key={g.severity} aria-labelledby={`sev-${g.severity}`}>
                <div className="flex flex-wrap items-baseline gap-3 border-b border-hairline pb-2">
                  <h2 id={`sev-${g.severity}`} className="text-xl">{SEVERITY_HEADING[g.severity] ?? titleCase(g.severity)}</h2>
                  <SeverityChip severity={g.severity} />
                  <span className="text-xs text-fg-muted"><span className="num">{g.items.length}</span> {g.items.length === 1 ? "question" : "questions"}</span>
                </div>
                <ol className="divide-y divide-hairline">
                  {g.items.map(({ q, n }) => {
                    const on = included(q.id);
                    return (
                      <li key={q.id} className={`flex gap-3 py-4 ${on ? "" : "opacity-60"}`}>
                        <label className="flex h-6 shrink-0 items-center">
                          <input type="checkbox" className="h-4 w-4 accent-[var(--accent)]" checked={on} onChange={() => toggle(q.id)} aria-label={`Include question ${n}: ${q.question}`} />
                        </label>
                        <div className="min-w-0 flex-1">
                          <p className="text-[15px] leading-relaxed"><span className="num mr-2 text-xs text-fg-muted" aria-hidden>{n}</span>{q.question}</p>
                          <p className="mt-1 text-sm text-fg-muted"><span className="font-medium text-fg">Why we ask:</span> {q.why}</p>
                          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
                            <span className="text-[11px] text-fg-muted">{KIND_LABEL[q.kind] ?? titleCase(q.kind)}</span>
                            {q.evidence_ids.slice(0, MAX_CHIPS).map((id) => <EvidenceChip key={id} dealId={dealId} id={id} onOpen={openEvidence} />)}
                            {q.evidence_ids.length > MAX_CHIPS && <span className="text-[11px] text-fg-muted">+{q.evidence_ids.length - MAX_CHIPS} more</span>}
                            {q.evidence_ids.length === 0 && q.document_names.length > 0 && <span className="text-[11px] text-fg-muted">Sources: {q.document_names.join(", ")}</span>}
                          </div>
                          <div className="mt-2 flex flex-wrap gap-x-3" role="group" aria-label={`Actions for question ${n}`}>
                            <button type="button" className={ACTION} onClick={() => draft(q)}>Draft with the assistant</button>
                            {q.claim_id && <Link href={`${base}/claims?claim=${q.claim_id}`} className={ACTION}>Open the claim</Link>}
                            <button type="button" className={ACTION} onClick={() => setReplying(replying === q.id ? null : q.id)}>{replies.data?.replies[q.id] ? "Update the seller’s reply" : "Record the seller’s reply"}</button>
                          </div>
                          {replies.data?.replies[q.id] && replying !== q.id && <ReplyLine r={replies.data.replies[q.id]} />}
                          {replying === q.id && <ReplyForm dealId={dealId} question={q} existing={replies.data?.replies[q.id] ?? null} onDone={() => setReplying(null)} />}
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </section>
            ))}
          </div>
        )}
      </div>
      <DocumentViewer dealId={dealId} target={viewer} onClose={() => setViewer(null)} />
    </div>
  );
}

const OUTCOME_LABEL: Record<ReplyOutcome, string> = { answered: "Answered", dodged: "Not answered", needs_document: "Document requested" };
const OUTCOME_STATUS: Record<ReplyOutcome, string> = { answered: "supported", dodged: "contradicted", needs_document: "review_required" };

/** The seller's current reply to one question, and how the buyer read it. */
function ReplyLine({ r }: { r: SellerReply }) {
  return (
    <p className="mt-2 rounded-[var(--radius-1)] border border-hairline bg-bg-raised px-3 py-2 text-sm">
      <StatusGlyph status={OUTCOME_STATUS[r.outcome]} size={12} className="mr-1 inline align-middle" /><span className="font-medium">{OUTCOME_LABEL[r.outcome]}.</span> <span className="text-fg-muted">Seller said:</span> “{r.reply_text}” <span className="text-xs text-fg-muted">{r.by ?? "reviewer"}, {fmtDate(r.created_at)}</span>
    </p>
  );
}

/** Paste what the seller wrote back and say what it amounts to. Additive: a later reply supersedes, nothing is deleted. */
function ReplyForm({ dealId, question, existing, onDone }: { dealId: string; question: SellerQuestion; existing: SellerReply | null; onDone: () => void }) {
  const [text, setText] = useState(existing?.reply_text ?? "");
  const [outcome, setOutcome] = useState<ReplyOutcome>(existing?.outcome ?? "answered");
  const qc = useQueryClient();
  const { toast } = useToast();
  const m = useMutation({
    mutationFn: () => sellerReplies.record(dealId, { question_id: question.id, question_text: question.question, reply_text: text.trim(), outcome }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: qk.replies(dealId) }); qc.invalidateQueries({ queryKey: qk.audit(dealId) }); toast({ title: "Reply recorded", tone: "success" }); onDone(); },
    onError: (e) => toast({ title: "Could not record the reply", description: String(e), tone: "error" }),
  });
  return (
    <form className="mt-2 flex flex-col gap-2 rounded-[var(--radius-1)] border border-hairline bg-bg-raised p-3" onSubmit={(e) => { e.preventDefault(); if (text.trim()) m.mutate(); }}>
      <label className="text-xs text-fg-muted" htmlFor={`reply-${question.id}`}>What the seller said</label>
      <textarea id={`reply-${question.id}`} className="min-h-[72px] rounded-[var(--radius-1)] border border-hairline bg-bg px-2 py-1.5 text-sm" value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the seller’s reply, or summarise the call." required />
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-xs text-fg-muted" htmlFor={`outcome-${question.id}`}>What it amounts to</label>
        <select id={`outcome-${question.id}`} className="h-8 rounded-[var(--radius-1)] border border-hairline bg-bg px-2 text-sm" value={outcome} onChange={(e) => setOutcome(e.target.value as ReplyOutcome)}>
          {(Object.keys(OUTCOME_LABEL) as ReplyOutcome[]).map((k) => <option key={k} value={k}>{OUTCOME_LABEL[k]}</option>)}
        </select>
        <span className="ml-auto flex gap-2"><Button type="button" size="sm" variant="secondary" onClick={onDone}>Cancel</Button><Button type="submit" size="sm" loading={m.isPending}>Save</Button></span>
      </div>
    </form>
  );
}

/** One citation chip. The evidence row is fetched on its own (cached per id), so the chip can name the document and the spot; until then it shows the id. */
function EvidenceChip({ dealId, id, onOpen }: { dealId: string; id: string; onOpen: (e: Evidence) => void }) {
  const ev = useEvidence(dealId, id);
  const e = ev.data;
  if (e) return <CitationChip docType={e.doc_type} documentName={e.document_name} locator={e.locator} kind={e.kind} onClick={() => onOpen(e)} />;
  return <CitationChip docType="unknown" locator={null} label={ev.isError ? "source unavailable" : `E:${id.slice(0, 6)}`} />;
}
