"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Dialog } from "radix-ui";
import { Search } from "lucide-react";
import { useClaims, useDocs } from "@/components/app/hooks";
import { useSellerQuestions } from "@/components/app/workflow-hooks";
import { StatusGlyph } from "@/components/domain/status";

interface Hit { key: string; group: string; label: string; detail?: string; href: string; status?: string }

const PAGES: Array<[string, string]> = [["Overview", ""], ["Review queue", "inbox"], ["Deal Room", "documents"], ["Claim Audit", "claims"], ["Financial Verification", "financials"], ["Scenario Lab", "scenarios"], ["Red-Team Report", "report"], ["Seller Questions", "questions"], ["Audit history", "audit"]];

/** Cmd+K / Ctrl+K: find a page, a claim, a document, or a seller question in this deal without knowing which screen
 *  holds it. Lists are read through the same queries the pages use, so nothing here is a second source of truth. */
export function CommandPalette() {
  const { dealId } = useParams<{ dealId?: string }>();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const id = dealId ?? "";
  const claims = useClaims(id);
  const docs = useDocs(id);
  const questions = useSellerQuestions(id);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen((o) => !o); setQ(""); setActive(0); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const hits = useMemo<Hit[]>(() => {
    if (!id) return [];
    const base = `/app/deals/${id}`;
    const all: Hit[] = [
      ...PAGES.map(([label, key]) => ({ key: `page:${key}`, group: "Pages", label, href: key ? `${base}/${key}` : base })),
      ...(claims.data ?? []).map((c) => ({ key: `claim:${c.id}`, group: "Claims", label: c.claim_text, detail: c.document_name, href: `${base}/claims?claim=${c.id}`, status: c.effective_status })),
      ...(docs.data ?? []).map((d) => ({ key: `doc:${d.id}`, group: "Documents", label: d.display_name, detail: d.doc_type.replace(/_/g, " "), href: `${base}/documents` })),
      ...(questions.data?.questions ?? []).map((x) => ({ key: `q:${x.id}`, group: "Seller questions", label: x.question, detail: x.severity, href: `${base}/questions` })),
    ];
    const needle = q.trim().toLowerCase();
    const scored = needle ? all.filter((h) => `${h.label} ${h.detail ?? ""}`.toLowerCase().includes(needle)) : all.filter((h) => h.group === "Pages");
    return scored.slice(0, 12);
  }, [id, q, claims.data, docs.data, questions.data]);
  const go = (h: Hit) => { setOpen(false); router.push(h.href); };
  if (!id) return null;
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[70] bg-black/30" />
        <Dialog.Content className="fixed left-1/2 top-[12vh] z-[70] w-[min(92vw,600px)] -translate-x-1/2 overflow-hidden rounded-[var(--radius-3)] border border-hairline bg-bg-raised shadow-lg" aria-describedby={undefined}>
          <Dialog.Title className="sr-only">Find anything in this deal</Dialog.Title>
          <div className="flex items-center gap-2 border-b border-hairline px-3">
            <Search size={16} className="text-fg-muted" />
            <input autoFocus aria-label="Search this deal" placeholder="Find a page, claim, document, or question" className="h-11 flex-1 bg-transparent text-sm outline-none" value={q} onChange={(e) => { setQ(e.target.value); setActive(0); }} onKeyDown={(e) => { if (e.key === "ArrowDown") { e.preventDefault(); setActive((i) => Math.min(hits.length - 1, i + 1)); } else if (e.key === "ArrowUp") { e.preventDefault(); setActive((i) => Math.max(0, i - 1)); } else if (e.key === "Enter" && hits[active]) { e.preventDefault(); go(hits[active]); } }} />
            <kbd className="rounded border border-hairline px-1 font-mono text-[11px] text-fg-muted">esc</kbd>
          </div>
          <ul role="listbox" aria-label="Results" className="max-h-[50vh] overflow-y-auto py-1">
            {hits.length === 0 && <li className="px-3 py-3 text-sm text-fg-muted">Nothing matches.</li>}
            {hits.map((h, i) => (
              <li key={h.key} role="option" aria-selected={i === active}>
                <button type="button" onMouseEnter={() => setActive(i)} onClick={() => go(h)} className={`flex w-full items-start gap-3 px-3 py-2 text-left text-sm ${i === active ? "bg-bg-muted" : ""}`}>
                  <span className="w-28 shrink-0 pt-0.5 text-[11px] uppercase tracking-wide text-fg-muted">{h.group}</span>
                  <span className="min-w-0 flex-1">
                    <span className="line-clamp-2">{h.status && <StatusGlyph status={h.status} size={11} className="mr-1 inline align-middle" />}{h.label}</span>
                    {h.detail && <span className="block text-xs text-fg-muted">{h.detail}</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
