"use client";

import { Component, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Dialog } from "radix-ui";
import { MessageSquareText, Plus, Send, Square, X, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { useLocalString, useModifierKey } from "@/lib/hooks";
import { onChatPrompt, setChatOpen, takeChatPrompt, toggleChat, useChatBus, resetChatBus } from "@/lib/chat-bus";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/primitives";
import { StatusGlyph } from "@/components/domain/status";
import { Markdown, stripCitations, type CitationSources } from "@/components/domain/markdown";
import { DocumentViewer, type ViewerTarget } from "@/components/domain/document-viewer";
import { StatementKindsLegend } from "@/components/domain/statement-kinds";
import { fmtDate, fmtInt } from "@/lib/format";

/** "deal" when the reply used deal tools, resolved a citation, or stated an uncited figure; "general" only for a grounded general-assistant answer. */
export type AnswerScope = "deal" | "general";
export interface Citations extends CitationSources { unresolved?: number; material_sentences?: number; cited_sentences?: number; scope?: AnswerScope }
/** `notice` is the server-worded line from a `switch` event (the default model was busy and a fallback answered); only a streamed draft carries it. */
export interface Msg { id: string; role: "user" | "assistant"; content: string; citations: Citations; tool_calls: Array<{ name: string; label?: string }>; grounded: boolean; scope?: AnswerScope; provider: string; model: string; label?: string; error: string | null; created_at: string; streaming?: boolean; tools?: string[]; notice?: string }
interface Thread { id: string; title: string; created_at: string; updated_at: string; message_count: number }
interface ThreadDetail extends Thread { messages: Msg[] }
export interface ChatOption { provider: string; label: string; env: string; free_tier: boolean; free_tier_note: string; default_model: string; key_url: string; models?: string[] }
/** `picker` is the server's opt-in for a model choice; without it the panel never names or offers a model. */
export interface ChatConfig { provider: string; label: string; model: string; models?: string[]; picker?: boolean; live: boolean; note: string; suggested: string[]; options: ChatOption[] }

/**
 * Companion prompts shown under the input whenever the assistant is not busy. The first two need the user's context
 * (which finding, which topic), so they prefill the textarea for the user to finish; the last two are complete
 * questions and are sent as they are. Pages hand over richer context through `askTheDeal` in `lib/chat-bus.ts`.
 */
export const QUICK_PROMPTS: ReadonlyArray<{ label: string; text: string; send: boolean }> = [
  { label: "Explain this finding", text: "Explain this finding: ", send: false },
  { label: "What should I ask the seller?", text: "What should I ask the seller about ", send: false },
  { label: "What is missing?", text: "What is missing?", send: true },
  { label: "What changed after this scenario?", text: "What changed after this scenario?", send: true },
];

/** Which backend answers chat. One row per deal, shared by the shell card and the panel, so opening the panel does not fetch it again. */
export function useChatConfig(dealId: string) {
  return useQuery({ queryKey: ["chat-config", dealId], queryFn: () => api.get<ChatConfig>(`/api/deals/${dealId}/chat/config`), enabled: !!dealId, staleTime: Infinity });
}

/** Provider throttling reads as "wait", not "broken": the review glyph instead of the error tone. */
export function isRateLimit(message: string): boolean {
  return /rate limit|too many requests/i.test(message);
}

const ACTION = "text-[11px] text-fg-muted underline-offset-2 hover:text-fg hover:underline";
const CURSOR = <span className="ml-0.5 inline-block h-[1em] w-[2px] animate-pulse bg-fg align-text-bottom" aria-hidden />;
const CHIP = "rounded-[var(--radius-1)] border border-hairline px-2 py-1 text-left text-[11px] text-fg-muted transition-colors duration-[120ms] hover:bg-bg-muted hover:text-fg";

/** The most recent thread per deal for this browser session, so reopening the panel resumes the conversation. */
const lastThread = new Map<string, string>();

export function DealChat({ dealId }: { dealId: string }) {
  const { open } = useChatBus();
  // Panel state lives in a module store so other screens can open it; leaving the deal must not carry it over.
  useEffect(() => () => resetChatBus(), [dealId]);
  const mod = useModifierKey();
  const shortcut = mod === "⌘" ? "⌘/" : "Ctrl+/";
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key === "/") { e.preventDefault(); toggleChat(); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <Dialog.Root open={open} onOpenChange={setChatOpen}>
      <Dialog.Trigger asChild>
        <button type="button" className="fixed bottom-20 right-4 z-40 inline-flex h-11 items-center gap-2 rounded-[var(--radius-3)] bg-fg px-4 text-sm font-medium text-bg shadow-[var(--shadow-2)] transition-transform duration-150 hover:opacity-90 active:scale-[0.98] md:bottom-5 md:right-5" aria-label={`Ask the deal (${shortcut})`}>
          <MessageSquareText size={16} /> Ask the deal
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-ink-950/30" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[880px] flex-col bg-bg-raised shadow-[var(--shadow-2)] outline-none md:w-[min(80vw,880px)]" aria-describedby="chat-desc">
          {open && <ChatPanel dealId={dealId} shortcut={shortcut} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** Focus the textarea with the caret after the text, so a prefilled prompt can be finished by typing. */
function focusInput(el: HTMLTextAreaElement | null): void {
  if (!el) return;
  el.focus();
  const n = el.value.length;
  el.setSelectionRange(n, n);
}

/** Grow the textarea with its content, up to the same cap as its max-h class. */
function autosize(el: HTMLTextAreaElement | null): void {
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(160, el.scrollHeight)}px`;
}

function ChatPanel({ dealId, shortcut }: { dealId: string; shortcut: string }) {
  const qc = useQueryClient();
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [restoring, setRestoring] = useState(() => lastThread.has(dealId));
  // Bumped whenever the textarea should take focus with the caret after its text (a prefilled prompt, a new thread).
  const [focusTick, setFocusTick] = useState(0);
  const [viewer, setViewer] = useState<ViewerTarget | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const config = useChatConfig(dealId);
  const threads = useQuery({ queryKey: ["chat-threads", dealId], queryFn: () => api.get<Thread[]>(`/api/deals/${dealId}/chat/threads`) });
  const [storedModel, setStoredModel] = useLocalString(`bearcase.chat.model.${dealId}`);

  useEffect(() => { focusInput(inputRef.current); }, [threadId, focusTick]);
  useEffect(() => { autosize(inputRef.current); }, [input]);
  useEffect(() => { listRef.current?.scrollTo?.({ top: listRef.current.scrollHeight }); }, [messages]);
  // Closing the panel mid-reply stops the stream instead of leaving it running against an unmounted panel.
  useEffect(() => () => { abortRef.current?.abort(); }, []);

  const live = config.data?.live === true;
  const defaultModel = config.data?.model ?? "";
  const models = config.data?.models ?? [];
  const pickModel = live && config.data?.picker === true && models.length > 1;
  const model = pickModel && storedModel && models.includes(storedModel) ? storedModel : defaultModel;

  const loadThread = useCallback(async (id: string) => {
    abortRef.current?.abort();
    const t = await api.get<ThreadDetail>(`/api/deals/${dealId}/chat/threads/${id}`);
    setThreadId(id);
    setMessages(t.messages.map(withCitationLists));
    lastThread.set(dealId, id);
  }, [dealId]);

  // Resume the conversation this panel showed last time it was open; a thread deleted meanwhile starts fresh.
  useEffect(() => {
    const id = lastThread.get(dealId);
    if (!id) return;
    let cancelled = false;
    api.get<ThreadDetail>(`/api/deals/${dealId}/chat/threads/${id}`)
      .then((t) => { if (cancelled) return; setThreadId(id); setMessages(t.messages.map(withCitationLists)); })
      .catch(() => { lastThread.delete(dealId); })
      .finally(() => { if (!cancelled) setRestoring(false); });
    return () => { cancelled = true; };
  }, [dealId]);

  const send = useCallback(async (text: string) => {
    const q = text.trim();
    if (!q || busy || restoring) return;
    setInput("");
    setBusy(true);
    const userMsg: Msg = { id: `u-${Date.now()}`, role: "user", content: q, citations: { evidence: [], metrics: [] }, tool_calls: [], grounded: false, provider: "", model: "", error: null, created_at: new Date().toISOString() };
    const draft: Msg = { id: `a-${Date.now()}`, role: "assistant", content: "", citations: { evidence: [], metrics: [] }, tool_calls: [], grounded: false, provider: "", model: "", error: null, created_at: new Date().toISOString(), streaming: true, tools: [] };
    setMessages((m) => [...m, userMsg, draft]);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      // The model id travels only when the user picked something other than the server default.
      const body = { message: q, thread_id: threadId, ...(live && model && model !== defaultModel ? { model } : {}) };
      const res = await fetch(`/api/deals/${dealId}/chat`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: ctrl.signal });
      if (!res.ok || !res.body) {
        const detail = await res.json().then((j: { detail?: unknown }) => (typeof j?.detail === "string" ? j.detail : "")).catch(() => "");
        const retry = res.headers.get("Retry-After");
        throw new Error(res.status === 429 ? `Too many requests. Try again in ${retry ?? "a few"} seconds.` : detail || `Request failed (${res.status})`);
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      const update = (fn: (d: Msg) => Msg) => setMessages((m) => m.map((x) => (x.id === draft.id ? fn(x) : x)));
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let idx: number;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const frame = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          const ev = /^event: (\w+)/m.exec(frame)?.[1];
          const dataLine = frame.split("\n").find((l) => l.startsWith("data: "));
          if (!ev || !dataLine) continue;
          const data = JSON.parse(dataLine.slice(6));
          if (ev === "meta") {
            if (!threadId) { setThreadId(data.thread_id); lastThread.set(dealId, data.thread_id); }
            update((d) => ({ ...d, provider: data.provider, model: data.model, label: data.label }));
          }
          else if (ev === "tool" && data.status === "start") update((d) => ({ ...d, tools: [...(d.tools ?? []), data.label ?? data.name] }));
          else if (ev === "text") update((d) => ({ ...d, content: d.content + data.delta }));
          else if (ev === "citations") update((d) => ({ ...d, citations: { evidence: [], metrics: [], ...data }, scope: data.scope ?? d.scope }));
          else if (ev === "switch") update((d) => ({ ...d, notice: data.message }));
          else if (ev === "error") update((d) => ({ ...d, error: data.message }));
          else if (ev === "done") update((d) => ({ ...d, id: data.message_id, content: data.content, grounded: data.grounded, scope: data.scope ?? d.scope, model: data.model ?? d.model, streaming: false }));
        }
      }
    } catch (e) {
      const msg = e instanceof Error && e.name === "AbortError" ? "Stopped." : String(e);
      setMessages((m) => m.map((x) => (x.id === draft.id ? { ...x, error: msg, streaming: false } : x)));
    } finally {
      setBusy(false);
      abortRef.current = null;
      qc.invalidateQueries({ queryKey: ["chat-threads", dealId] });
    }
  }, [busy, restoring, dealId, threadId, qc, live, model, defaultModel]);

  const prefill = useCallback((text: string) => { setInput(text); setFocusTick((t) => t + 1); }, []);

  // Prompts handed over through the chat bus (a page's "Explain this finding", a scenario's "What changed?"). The
  // subscription replays a prompt that was pending when the panel opened, and each prompt is taken exactly once
  // (StrictMode runs effects twice). Nothing is taken while a resumed conversation is still loading, so a sent
  // message lands in that thread rather than opening a new one; one that arrives while a reply is streaming is
  // prefilled instead of dropped.
  useEffect(() => onChatPrompt((p) => {
    if (restoring || !takeChatPrompt(p.id)) return;
    if (p.send && !busy) void send(p.text);
    else prefill(p.text);
  }), [restoring, busy, send, prefill]);

  const newThread = () => { abortRef.current?.abort(); setThreadId(null); setMessages([]); lastThread.delete(dealId); setFocusTick((t) => t + 1); };
  const deleteThread = async (id: string) => { await fetch(`/api/deals/${dealId}/chat/threads/${id}`, { method: "DELETE", credentials: "include" }); if (id === threadId) newThread(); qc.invalidateQueries({ queryKey: ["chat-threads", dealId] }); };
  const lastUser = [...messages].reverse().find((m) => m.role === "user");
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const regenerate = lastUser && !busy ? () => send(lastUser.content) : undefined;
  const ready = !busy && !restoring;
  return (
    <>
      <div className="flex h-14 items-center gap-3 border-b border-hairline px-4">
        <div className="min-w-0 flex-1">
          <Dialog.Title className="text-sm font-semibold">Ask the deal</Dialog.Title>
          <Dialog.Description id="chat-desc" className="truncate text-[11px] text-fg-muted">
            {config.data ? (live ? "Answers drawn from the deal room, with citations" : "Offline mode: rule-based answers") : "Loading"}
          </Dialog.Description>
        </div>
        {pickModel && (
          <select aria-label="Model" value={model} onChange={(e) => setStoredModel(e.target.value)} className="h-7 max-w-[9rem] shrink rounded-[var(--radius-1)] border border-hairline bg-bg-raised px-1.5 text-[11px] text-fg md:max-w-[14rem]">
            {models.map((id) => <option key={id} value={id}>{id}</option>)}
          </select>
        )}
        <button type="button" onClick={newThread} className="rounded-[var(--radius-1)] p-1.5 text-fg-muted hover:bg-bg-muted md:hidden" aria-label="New conversation"><Plus size={16} /></button>
        <Kbd>{shortcut}</Kbd>
        <Dialog.Close className="rounded-[var(--radius-1)] p-1.5 text-fg-muted hover:bg-bg-muted" aria-label="Close"><X size={16} /></Dialog.Close>
      </div>
      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-44 shrink-0 flex-col border-r border-hairline md:flex">
          <button type="button" onClick={newThread} className="m-2 inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-2)] border border-hairline px-2 text-xs hover:bg-bg-muted"><Plus size={12} /> New conversation</button>
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
            {threads.data?.map((t) => (
              <div key={t.id} className={`group flex items-center gap-1 rounded-[var(--radius-1)] ${t.id === threadId ? "bg-bg-muted" : "hover:bg-bg-muted/60"}`}>
                <button type="button" onClick={() => loadThread(t.id)} aria-current={t.id === threadId ? "true" : undefined} className="min-w-0 flex-1 truncate px-2 py-1.5 text-left text-xs" title={t.title}>{t.title}</button>
                <button type="button" onClick={() => deleteThread(t.id)} aria-label={`Delete conversation ${t.title}`} className="p-1 text-fg-muted opacity-0 hover:text-red group-hover:opacity-100 focus:opacity-100"><Trash2 size={12} /></button>
              </div>
            ))}
            {threads.data?.length === 0 && <p className="px-2 py-1.5 text-[11px] text-fg-muted">No conversations yet.</p>}
          </div>
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
            {restoring && messages.length === 0 && <p className="text-xs text-fg-muted">Loading your last conversation</p>}
            {!restoring && messages.length === 0 && (
              <div className="flex min-h-full flex-col justify-end gap-4">
                <div className="text-sm text-fg-muted">
                  <p className="text-base font-semibold text-fg">Ask anything.</p>
                  {config.data && !live && <p className="mt-2 max-w-[46ch]">{config.data.note}</p>}
                  <p className="mt-2 max-w-[46ch]">Deal facts come from the claim ledger, verified metrics, add-back decisions, scenario runs, and the documents, each with a citation you can open. A citation shows where a figure came from, not that the whole answer is right, so open the sources before you rely on it. Everything else is answered as a general assistant.</p>
                  <StatementKindsLegend className="mt-3 max-w-[60ch]" />
                </div>
                {config.data && !live && <ConnectModel options={config.data.options} />}
                {config.data && (
                  <div className="flex flex-wrap gap-1.5">
                    {config.data.suggested.map((s) => <button key={s} type="button" className="rounded-[var(--radius-2)] border border-hairline px-2.5 py-1.5 text-left text-xs hover:bg-bg-muted" onClick={() => send(s)}>{s}</button>)}
                  </div>
                )}
              </div>
            )}
            <ol className="flex flex-col gap-4">
              {messages.map((m) => <MessageView key={m.id} m={m} onOpen={setViewer} onRegenerate={m.id === lastAssistant?.id ? regenerate : undefined} />)}
            </ol>
          </div>
          <div className="border-t border-hairline p-3">
            <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); send(input); }}>
              <textarea ref={inputRef} aria-label="Message" placeholder="Ask anything" rows={1} className="min-h-[40px] max-h-40 min-w-0 flex-1 resize-none rounded-[var(--radius-2)] border border-hairline bg-bg-raised px-3 py-2 text-sm leading-relaxed" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }} maxLength={4000} />
              {busy ? <Button type="button" variant="secondary" icon={<Square size={14} />} onClick={() => abortRef.current?.abort()}>Stop</Button> : <Button type="submit" icon={<Send size={14} />} disabled={!input.trim() || restoring}>Send</Button>}
            </form>
            {ready && (
              <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Quick prompts">
                {QUICK_PROMPTS.map((p) => (
                  <button key={p.label} type="button" onClick={() => { if (p.send) void send(p.text); else prefill(p.text); }} className={CHIP}>{p.label}</button>
                ))}
              </div>
            )}
            <p className="mt-2 text-[11px] text-fg-muted">Enter to send, Shift+Enter for a new line. Not financial, legal, tax, or investment advice.</p>
          </div>
        </div>
      </div>
      <DocumentViewer dealId={dealId} target={viewer} onClose={() => setViewer(null)} />
    </>
  );
}

/** Empty-state block when no model is connected: one instruction and the provider options in API order (free tiers first). */
export function ConnectModel({ options }: { options: ChatOption[] }) {
  if (!options?.length) return null;
  return (
    <div className="text-sm">
      <p className="font-medium text-fg">Connect a model</p>
      <p className="mt-1 max-w-[46ch] text-fg-muted">Add one key to .env in the repo root and restart the API. Free options first.</p>
      <ul className="mt-2 divide-y divide-hairline border-y border-hairline">
        {options.map((o) => (
          <li key={o.provider} className="py-1.5 text-xs">
            <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-0.5">
              <a href={o.key_url} target="_blank" rel="noreferrer" className="font-medium text-accent underline-offset-2 hover:underline">{o.label}</a>
              <code className="font-mono text-[11px] text-fg">{o.env}</code>
              {o.free_tier && <span className="text-fg-muted">free tier</span>}
            </div>
            {o.free_tier_note && <p className="mt-0.5 max-w-[60ch] leading-snug text-[11px] text-fg-muted">{o.free_tier_note}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A persisted row always gets both citation lists, so a reply interrupted before its citations resolved still renders. */
function withCitationLists(m: Msg): Msg {
  return { ...m, citations: { evidence: [], metrics: [], ...m.citations } };
}

/**
 * Footer verdict for a finished reply. Uncited figures always win over the scope label: a reply is "general" only when the
 * service found nothing to cite, so an ungrounded reply is shown as ungrounded whatever scope it carries. A grounded deal
 * reply says what was checked (every citation points at a row of this deal room) and asks for review: a resolving citation
 * shows where a figure came from, not that the reasoning around it is right.
 */
export function grounding(m: Msg): { status: string; text: string; detail: string } {
  const scope = m.scope ?? m.citations.scope;
  if (!m.grounded && (m.citations.material_sentences ?? 0) === 0 && (m.citations.unresolved ?? 0) === 0) {
    return {
      status: "review_required",
      text: "No citation to open · review the answer",
      detail: "This reply drew on deal data but returned nothing you can open, for example a list of missing documents. Check the sources yourself.",
    };
  }
  if (!m.grounded) {
    return {
      status: "review_required",
      text: `Figures not cited from the deal room (${fmtInt(m.citations.cited_sentences ?? 0)} of ${fmtInt(m.citations.material_sentences ?? 0)} paragraphs cited)`,
      detail: "At least one paragraph states a figure without a citation, or a citation did not match this deal room. Treat those figures as unverified.",
    };
  }
  if (scope === "general") return { status: "general", text: "General answer, not from the deal room", detail: "No deal data was used for this reply." };
  const n = (m.citations.evidence?.length ?? 0) + (m.citations.metrics?.length ?? 0);
  const detail = "Every citation points at a document passage or a calculated metric in this deal room. That shows where each figure came from, not that the whole answer is right.";
  if (n === 0) return { status: "supported", text: "No figures to cite · review the answer", detail };
  if (n === 1) return { status: "supported", text: "1 citation resolves · review the answer", detail };
  return { status: "supported", text: `All ${fmtInt(n)} citations resolve · review the answer`, detail };
}

export function MessageView({ m, onOpen, onRegenerate }: { m: Msg; onOpen: (t: ViewerTarget) => void; onRegenerate?: () => void }) {
  const [copied, setCopied] = useState(false);
  if (m.role === "user") return <li className="self-end max-w-[85%] rounded-[var(--radius-3)] bg-bg-muted px-3.5 py-2.5 text-sm">{m.content}</li>;
  const tools = m.tools?.length ? m.tools : m.tool_calls.map((t) => t.label ?? t.name);
  // Every non-streaming row is finished, including one stopped before any text arrived: it still gets its footer and Regenerate.
  const finished = !m.streaming;
  const verdict = finished && m.content ? grounding(m) : null;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(stripCitations(m.content));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard unavailable (insecure context or denied) */ }
  };
  return (
    <li className="max-w-full">
      {tools.length > 0 && <p className="mb-1.5 text-[11px] text-fg-muted">{Array.from(new Set(tools)).join(", ")}</p>}
      {m.notice && <p className="mb-1.5 text-[11px] text-fg-muted">{m.notice}</p>}
      <div className="text-[15px] leading-relaxed">
        {m.streaming && !m.content
          ? <p role="status" className="text-xs text-fg-muted">{tools.length > 0 ? "Reading the deal room…" : "Thinking…"}{CURSOR}</p>
          : finished && !m.content && !m.error
            ? <p className="text-xs text-fg-muted">No reply was recorded.</p>
            : <RichText text={m.content} citations={m.citations} onOpen={onOpen} />}
        {m.streaming && m.content && CURSOR}
      </div>
      {m.error && (isRateLimit(m.error)
        ? <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-fg-muted"><StatusGlyph status="review_required" size={11} />{m.error}</p>
        : <p className="mt-2 text-xs text-red">{m.error}</p>)}
      {finished && (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-fg-muted">
          {verdict && <span className="inline-flex items-center gap-1" title={verdict.detail}><StatusGlyph status={verdict.status} size={11} />{verdict.text}</span>}
          <span>{fmtDate(m.created_at)}</span>
          {m.content && <button type="button" onClick={copy} aria-live="polite" className={ACTION}>{copied ? "Copied" : "Copy"}</button>}
          {onRegenerate && <button type="button" onClick={onRegenerate} className={ACTION}>Regenerate</button>}
        </div>
      )}
    </li>
  );
}

/** Assistant text: Markdown with [E:id]/[M:id] markers rendered as citation chips, behind a boundary so one bad reply cannot take the chat down. */
function RichText(props: { text: string; citations: Citations; onOpen: (t: ViewerTarget) => void }) {
  return <MessageBody text={props.text}><Markdown {...props} /></MessageBody>;
}

/** Falls back to the raw text when rendering a reply throws; tries the rich view again once the text changes (streaming). */
class MessageBody extends Component<{ text: string; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidUpdate(prev: { text: string }) {
    if (this.state.failed && prev.text !== this.props.text) this.setState({ failed: false });
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return <pre className="whitespace-pre-wrap break-words font-sans text-[15px] leading-relaxed">{this.props.text}</pre>;
  }
}
