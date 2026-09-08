import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConnectModel, DealChat, MessageView, QUICK_PROMPTS, budgetLine, isBudgetExhausted, isRateLimit, type ChatConfig, type ChatOption, type Msg } from "./deal-chat";
import { askTheDeal, getChatBusState, onChatPrompt, resetChatBus, setChatOpen, takeChatPrompt } from "@/lib/chat-bus";
import { fmtDate } from "@/lib/format";

// The renderer's internal parseBlocks call is a module-local binding, so the module's Markdown export is what a test
// can make throw; the flag keeps every other test on the real renderer.
const renderFailure = vi.hoisted(() => ({ on: false }));
vi.mock("./markdown", async (importOriginal) => {
  const mod = await importOriginal<typeof import("./markdown")>();
  const Markdown = (props: Parameters<typeof mod.Markdown>[0]) => {
    if (renderFailure.on) throw new Error("parseBlocks failed");
    return <mod.Markdown {...props} />;
  };
  return { ...mod, Markdown };
});

const OPTIONS: ChatOption[] = [
  { provider: "gemini", label: "Google Gemini", env: "GEMINI_API_KEY", free_tier: true, free_tier_note: "Free of charge for Flash models; limits shown in AI Studio.", default_model: "gemini-3.8-flash", key_url: "https://aistudio.google.com/apikey" },
  { provider: "groq", label: "Groq", env: "GROQ_API_KEY", free_tier: true, free_tier_note: "Free plan, no card needed.", default_model: "openai/gpt-oss-120b", key_url: "https://console.groq.com/keys" },
  { provider: "openai", label: "OpenAI", env: "OPENAI_API_KEY", free_tier: false, free_tier_note: "Prepaid credits, minimum $5.", default_model: "gpt-5.6-luna", key_url: "https://platform.openai.com/api-keys" },
];
const E1 = "11111111-1111-4111-8111-111111111111";
const M1 = "22222222-2222-4222-8222-222222222222";
const EV = { id: E1, document_id: "d1", document_name: "cim.pdf", doc_type: "cim", locator: { page: 3 }, kind: "page", text: "" };
const ME = { id: M1, key: "verified_adjusted_ebitda", label: "Verified adjusted EBITDA (USD)", value: "1810000", unit: "usd", formula: "reported_ebitda + accepted_adjustments" };
const CONFIG: ChatConfig = { provider: "mock", label: "Rule-based composer", model: "rules", models: ["rules"], live: false, note: "No model key is configured.", suggested: ["Why was adjusted EBITDA reduced?"], options: OPTIONS };
/** A connected provider offering two models; `picker` stays off unless a test turns it on. */
const LIVE: ChatConfig = { ...CONFIG, provider: "gemini", label: "Google Gemini", model: "gemini-3.8-flash", models: ["gemini-3.8-flash", "gemini-3.7-flash"], live: true, note: "Live model: answers are drafted by Google Gemini (gemini-3.8-flash)." };
const noop = () => {};
afterEach(() => { cleanup(); resetChatBus(); vi.unstubAllGlobals(); });

function msg(overrides: Partial<Msg>): Msg {
  return { id: "m1", role: "assistant", content: "Revenue grew.", citations: { evidence: [], metrics: [] }, tool_calls: [], grounded: true, provider: "gemini", model: "gemini-3.8-flash", error: null, created_at: "2026-09-06T10:00:00Z", ...overrides };
}

describe("ConnectModel", () => {
  it("lists options in API order with label link, env var, and a plain 'free tier' marker, never a model id", () => {
    const { container, getAllByRole, getByText, queryAllByText, queryByText } = render(<ConnectModel options={OPTIONS} />);
    expect(getByText("Connect a model")).toBeInTheDocument();
    expect(getByText("Add one key to .env in the repo root and restart the API. Free options first.")).toBeInTheDocument();
    const links = getAllByRole("link");
    expect(links.map((a) => a.textContent)).toEqual(["Google Gemini", "Groq", "OpenAI"]);
    for (const [i, a] of links.entries()) {
      expect(a).toHaveAttribute("href", OPTIONS[i].key_url);
      expect(a).toHaveAttribute("target", "_blank");
      expect(a).toHaveAttribute("rel", "noreferrer");
    }
    const codes = Array.from(container.querySelectorAll("code"));
    expect(codes.map((c) => c.textContent)).toEqual(["GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY"]);
    for (const c of codes) expect(c.className).toContain("font-mono");
    expect(queryByText(/gemini-3\.8-flash|gpt-oss|gpt-5/)).toBeNull();
    expect(queryAllByText("free tier")).toHaveLength(2);
    expect(container.querySelector("svg")).toBeNull();
  });
  it("renders nothing when there are no options", () => {
    const { container } = render(<ConnectModel options={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("MessageView footer", () => {
  it("names neither the provider nor the model, with or without a label, and keeps time, Copy, and Regenerate", () => {
    const { queryByText, getByText, getByRole, rerender } = render(<ol><MessageView m={msg({ label: "Google Gemini" })} onOpen={noop} onRegenerate={noop} /></ol>);
    expect(queryByText(/Google Gemini|gemini/i)).toBeNull();
    expect(getByText(fmtDate("2026-09-06T10:00:00Z"))).toBeInTheDocument();
    expect(getByRole("button", { name: "Copy" })).toBeInTheDocument();
    expect(getByRole("button", { name: "Regenerate" })).toBeInTheDocument();
    rerender(<ol><MessageView m={msg({ label: undefined })} onOpen={noop} /></ol>);
    expect(queryByText(/gemini/i)).toBeNull();
  });
  it("counts the resolving citations for a grounded deal answer and asks for review, with the supported glyph", () => {
    const { getByText, container } = render(<ol><MessageView m={msg({ scope: "deal", grounded: true, citations: { evidence: [EV], metrics: [ME] } })} onOpen={noop} /></ol>);
    const verdict = getByText("All 2 citations resolve · review the answer");
    expect(verdict).toBeInTheDocument();
    expect(verdict.closest("span")?.getAttribute("title")).toMatch(/where each figure came from, not that the whole answer is right/);
    expect(container.querySelector("svg circle")).not.toBeNull();
    expect(container.querySelector("svg rect")).toBeNull();
  });
  it("uses the singular for one citation and a plain note when a grounded deal answer cites nothing", () => {
    const { getByText, rerender } = render(<ol><MessageView m={msg({ scope: "deal", grounded: true, citations: { evidence: [EV], metrics: [] } })} onOpen={noop} /></ol>);
    expect(getByText("1 citation resolves · review the answer")).toBeInTheDocument();
    rerender(<ol><MessageView m={msg({ scope: "deal", grounded: true })} onOpen={noop} /></ol>);
    expect(getByText("No figures to cite · review the answer")).toBeInTheDocument();
  });
  it("shows the uncited-figures warning with the paragraph count for an ungrounded deal answer", () => {
    const { getByText, container } = render(<ol><MessageView m={msg({ scope: "deal", grounded: false, citations: { evidence: [], metrics: [], material_sentences: 3, cited_sentences: 1 } })} onOpen={noop} /></ol>);
    expect(getByText("Figures not cited from the deal room (1 of 3 paragraphs cited)")).toBeInTheDocument();
    expect(container.querySelector("svg rect")).not.toBeNull();
    expect(container.querySelector("svg circle")).toBeNull();
  });
  it("labels a grounded general answer with a neutral glyph instead of the review warning", () => {
    const { getByText, queryByText, container } = render(<ol><MessageView m={msg({ scope: "general", grounded: true })} onOpen={noop} /></ol>);
    expect(getByText("General answer, not from the deal room")).toBeInTheDocument();
    expect(queryByText(/paragraphs? cited/)).toBeNull();
    expect(container.querySelector("svg path")?.getAttribute("d")).toContain("M8 1.5l5.6");
    expect(container.querySelector("svg rect, svg circle")).toBeNull();
  });
  it("never labels an ungrounded reply as general, whatever scope it carries", () => {
    const { getByText, queryByText, container } = render(<ol><MessageView m={msg({ scope: "general", grounded: false, citations: { evidence: [], metrics: [], material_sentences: 2, cited_sentences: 0, scope: "general" } })} onOpen={noop} /></ol>);
    expect(getByText("Figures not cited from the deal room (0 of 2 paragraphs cited)")).toBeInTheDocument();
    expect(queryByText("General answer, not from the deal room")).toBeNull();
    expect(container.querySelector("svg rect")).not.toBeNull();
  });
  it("reads the scope persisted inside citations for reloaded threads", () => {
    const { getByText } = render(<ol><MessageView m={msg({ grounded: true, citations: { evidence: [], metrics: [], scope: "general" } })} onOpen={noop} /></ol>);
    expect(getByText("General answer, not from the deal room")).toBeInTheDocument();
  });
  it("shows no verdict for a finished reply with no text", () => {
    const { queryByText } = render(<ol><MessageView m={msg({ content: "", error: "Stopped." })} onOpen={noop} /></ol>);
    expect(queryByText(/cited|General answer/)).toBeNull();
  });
});

describe("MessageView progress", () => {
  it("says Thinking before any tool starts, Reading the deal room once one has, and neither once text streams", () => {
    const { getByRole, queryByRole, getByText, container, rerender } = render(<ol><MessageView m={msg({ streaming: true, content: "", tools: [] })} onOpen={noop} /></ol>);
    expect(getByRole("status")).toHaveTextContent("Thinking…");
    expect(container.querySelector(".animate-pulse")).not.toBeNull();
    rerender(<ol><MessageView m={msg({ streaming: true, content: "", tools: ["Findings", "Metrics"] })} onOpen={noop} /></ol>);
    expect(getByRole("status")).toHaveTextContent("Reading the deal room…");
    expect(getByText("Findings, Metrics")).toBeInTheDocument();
    expect(container.querySelector(".animate-pulse")).not.toBeNull();
    rerender(<ol><MessageView m={msg({ streaming: true, content: "Revenue", tools: ["Findings"] })} onOpen={noop} /></ol>);
    expect(queryByRole("status")).toBeNull();
    expect(getByText("Revenue")).toBeInTheDocument();
    expect(container.querySelector(".animate-pulse")).not.toBeNull();
    rerender(<ol><MessageView m={msg({ content: "Revenue", tools: ["Findings"] })} onOpen={noop} /></ol>);
    expect(queryByRole("status")).toBeNull();
    expect(container.querySelector(".animate-pulse")).toBeNull();
  });

  it("shows a switch notice above the answer as one muted line", () => {
    const { getByText } = render(<ol><MessageView m={msg({ notice: "Gemini 3.8 Flash is busy; answering with Gemini 3.7 Flash." })} onOpen={noop} /></ol>);
    const note = getByText("Gemini 3.8 Flash is busy; answering with Gemini 3.7 Flash.");
    expect(note.tagName).toBe("P");
    expect(note.className).toContain("text-fg-muted");
    expect(note.compareDocumentPosition(getByText("Revenue grew."))).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("shows a rate-limit error with the review glyph and the text unchanged; other errors keep the error tone", () => {
    expect(isRateLimit("Too many requests. Try again in 30 seconds.")).toBe(true);
    expect(isRateLimit("Google Gemini rate limit reached (free tier).")).toBe(true);
    expect(isRateLimit("Stopped.")).toBe(false);
  });

  it("treats the monthly budget refusal as a wait, and words the budget line from the config", () => {
    const refusal = "You have used this month's 300 assistant answers. The budget resets on 1 October 2026.";
    expect(isBudgetExhausted(refusal)).toBe(true);
    expect(isRateLimit(refusal)).toBe(true);
    expect(isBudgetExhausted("Too many requests. Try again in 30 seconds.")).toBe(false);
    expect(budgetLine({ limit: 300, used: 12, resets_on: "2026-10-01" })).toBe("12 of 300 answers used this month");
    expect(budgetLine(undefined)).toBeNull();
    const { getByText, container, rerender } = render(<ol><MessageView m={msg({ content: "", error: "Too many requests. Try again in 30 seconds." })} onOpen={noop} /></ol>);
    const err = getByText("Too many requests. Try again in 30 seconds.");
    expect(err.className).not.toContain("text-red");
    expect(err.querySelector("svg rect")).not.toBeNull();
    rerender(<ol><MessageView m={msg({ content: "", error: "Request failed (500)" })} onOpen={noop} /></ol>);
    expect(getByText("Request failed (500)").className).toContain("text-red");
    expect(container.querySelector("svg rect")).toBeNull();
  });
});

describe("MessageView content", () => {
  it("renders Markdown with citation chips", () => {
    const m = msg({ content: `## Summary\n\n- Revenue grew 18% [E:${E1}]\n- Use \`dscr\`` , citations: { evidence: [{ id: E1, document_id: "d1", document_name: "cim.pdf", doc_type: "cim", locator: { page: 3 }, kind: "page", text: "" }], metrics: [] } });
    const { container, getByRole } = render(<ol><MessageView m={m} onOpen={noop} /></ol>);
    expect(container.querySelector("h4")).toHaveTextContent("Summary");
    expect(container.querySelectorAll("ul > li")).toHaveLength(2);
    expect(getByRole("button", { name: /CIM p\.3/ })).toBeInTheDocument();
    expect(container.querySelector("code")).toHaveTextContent("dscr");
  });

  it("renders a repeated metric as one chip and compact same-metric markers; evidence chips repeat in full", () => {
    const text = `Verified adjusted EBITDA is $1.81M [M:${M1}] against the seller's $2.10M [E:${E1}].\n\n- The gap is $290,000 [M:${M1}]\n- Owner salary add-back rejected [E:${E1}]\n\n| Item | Value |\n|---|---|\n| EBITDA | [M:${M1}] |`;
    const { container, getAllByRole } = render(<ol><MessageView m={msg({ content: text, citations: { evidence: [EV], metrics: [ME] } })} onOpen={noop} /></ol>);
    const chips = container.querySelectorAll('[data-cite="metric"]');
    const repeats = container.querySelectorAll('[data-cite="metric-repeat"]');
    expect(chips).toHaveLength(1);
    expect(chips[0]).toHaveTextContent("Verified adjusted EBITDA $1,810,000");
    expect(repeats).toHaveLength(2);
    for (const r of repeats) {
      expect(r.getAttribute("title")).toBe(chips[0].getAttribute("title"));
      expect(r.textContent).toBe("same metric: Verified adjusted EBITDA");
      expect(r.querySelector(".sr-only")).toHaveTextContent("Verified adjusted EBITDA");
    }
    // the first occurrence in reading order keeps the full chip
    expect(container.querySelector("p")?.contains(chips[0])).toBe(true);
    expect(getAllByRole("button", { name: /CIM p\.3/ })).toHaveLength(2);
  });
});

describe("MessageView actions", () => {
  afterEach(() => { vi.useRealTimers(); });

  it("copies the text without citation markers and shows Copied for 1.5 s", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const { getByRole } = render(<ol><MessageView m={msg({ content: `Revenue grew 18% [E:${E1}].` })} onOpen={noop} /></ol>);
    const btn = getByRole("button", { name: "Copy" });
    await act(async () => { fireEvent.click(btn); await Promise.resolve(); });
    expect(writeText).toHaveBeenCalledWith("Revenue grew 18%.");
    expect(btn).toHaveTextContent("Copied");
    act(() => { vi.advanceTimersByTime(1500); });
    expect(btn).toHaveTextContent("Copy");
  });

  it("offers Regenerate only when a handler is passed, and calls it", () => {
    const onRegenerate = vi.fn();
    const { getByRole, queryByRole, rerender } = render(<ol><MessageView m={msg({})} onOpen={noop} onRegenerate={onRegenerate} /></ol>);
    fireEvent.click(getByRole("button", { name: "Regenerate" }));
    expect(onRegenerate).toHaveBeenCalledTimes(1);
    rerender(<ol><MessageView m={msg({})} onOpen={noop} /></ol>);
    expect(queryByRole("button", { name: "Regenerate" })).toBeNull();
    expect(getByRole("button", { name: "Copy" })).toBeInTheDocument();
  });

  it("shows no actions while streaming, and Regenerate but no Copy for an empty errored reply", () => {
    const { queryByRole, queryByText, rerender, getByText } = render(<ol><MessageView m={msg({ streaming: true, content: "partial" })} onOpen={noop} onRegenerate={noop} /></ol>);
    expect(queryByRole("button", { name: "Copy" })).toBeNull();
    expect(queryByRole("button", { name: "Regenerate" })).toBeNull();
    expect(queryByText("No reply was recorded.")).toBeNull();
    rerender(<ol><MessageView m={msg({ streaming: true, content: "" })} onOpen={noop} onRegenerate={noop} /></ol>);
    expect(queryByText("No reply was recorded.")).toBeNull();
    rerender(<ol><MessageView m={msg({ content: "", error: "Stopped." })} onOpen={noop} onRegenerate={noop} /></ol>);
    expect(getByText("Stopped.")).toBeInTheDocument();
    expect(queryByText("No reply was recorded.")).toBeNull();
    expect(queryByRole("button", { name: "Copy" })).toBeNull();
    expect(queryByRole("button", { name: "Regenerate" })).not.toBeNull();
  });

  it("renders an interrupted persisted reply (no text, no error, no citation lists) with a placeholder and Regenerate", () => {
    const onRegenerate = vi.fn();
    let result: ReturnType<typeof render> | undefined;
    expect(() => { result = render(<ol><MessageView m={msg({ content: "", error: null, citations: {} })} onOpen={noop} onRegenerate={onRegenerate} /></ol>); }).not.toThrow();
    const { getByText, getByRole, queryByRole, queryByText } = result!;
    const note = getByText("No reply was recorded.");
    expect(note.className).toContain("text-fg-muted");
    expect(queryByText(/gemini/i)).toBeNull();
    expect(queryByRole("button", { name: "Copy" })).toBeNull();
    expect(queryByText(/cited|General answer/)).toBeNull();
    fireEvent.click(getByRole("button", { name: "Regenerate" }));
    expect(onRegenerate).toHaveBeenCalledTimes(1);
  });

  it("falls back to the raw text when rendering the reply throws, keeping the footer", () => {
    const quiet = vi.spyOn(console, "error").mockImplementation(() => {});
    renderFailure.on = true;
    try {
      const text = `Raw **text** [E:${E1}]\n> line`;
      const { container, getByRole } = render(<ol><MessageView m={msg({ content: text })} onOpen={noop} onRegenerate={noop} /></ol>);
      const pre = container.querySelector("pre");
      expect(pre).not.toBeNull();
      expect(pre?.textContent).toBe(text);
      expect(container.querySelector("strong, blockquote")).toBeNull();
      expect(getByRole("button", { name: "Regenerate" })).toBeInTheDocument();
      expect(getByRole("button", { name: "Copy" })).toBeInTheDocument();
    } finally {
      renderFailure.on = false;
      quiet.mockRestore();
    }
  });

  it("returns to the rich view once the text changes after a render failure", () => {
    const quiet = vi.spyOn(console, "error").mockImplementation(() => {});
    renderFailure.on = true;
    try {
      const { container, rerender } = render(<ol><MessageView m={msg({ content: "**bad**" })} onOpen={noop} /></ol>);
      expect(container.querySelector("pre")).not.toBeNull();
      renderFailure.on = false;
      rerender(<ol><MessageView m={msg({ content: "**good**" })} onOpen={noop} /></ol>);
      expect(container.querySelector("pre")).toBeNull();
      expect(container.querySelector("strong")).toHaveTextContent("good");
    } finally {
      renderFailure.on = false;
      quiet.mockRestore();
    }
  });
});

describe("chat bus", () => {
  it("trims and caps prompts, numbers requests, hands each out once, and drops an untaken prompt on close", () => {
    askTheDeal("  Explain this finding: owner salary  ");
    const first = getChatBusState().prompt;
    expect(getChatBusState().open).toBe(true);
    expect(first).toMatchObject({ text: "Explain this finding: owner salary", send: false });
    askTheDeal("What is missing?", { send: true });
    const second = getChatBusState().prompt;
    expect(second?.id).toBeGreaterThan(first?.id ?? 0);
    expect(second?.send).toBe(true);
    expect(takeChatPrompt(first?.id ?? 0)).toBe(false);
    expect(takeChatPrompt(second?.id ?? 0)).toBe(true);
    expect(takeChatPrompt(second?.id ?? 0)).toBe(false);
    expect(getChatBusState()).toEqual({ open: true, prompt: null });
    askTheDeal("pending");
    setChatOpen(false);
    expect(getChatBusState()).toEqual({ open: false, prompt: null });
    askTheDeal("   ");
    expect(getChatBusState()).toEqual({ open: true, prompt: null });
    askTheDeal("x".repeat(4100));
    expect(getChatBusState().prompt?.text).toHaveLength(4000);
  });

  it("delivers a pending prompt to a new subscriber at once, then each new prompt", () => {
    askTheDeal("first");
    const seen: string[] = [];
    const off = onChatPrompt((p) => seen.push(p.text));
    expect(seen).toEqual(["first"]);
    askTheDeal("second", { send: true });
    expect(seen).toEqual(["first", "second"]);
    off();
    askTheDeal("third");
    expect(seen).toEqual(["first", "second"]);
  });
});

/** Same-origin API stand-in: chat config, thread list, thread detail, and a streamed reply that records what was posted. */
function stubApi(reply = "Here is the answer.", opts: { config?: Partial<ChatConfig>; before?: Array<[string, unknown]> } = {}) {
  const config = { ...CONFIG, ...opts.config };
  const posts: Array<{ message: string; thread_id: string | null }> = [];
  const threads = new Map<string, Msg[]>();
  const sse = (events: Array<[string, unknown]>) => events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join("");
  const stamp = "2026-09-06T10:00:00Z";
  const row = (id: string, role: Msg["role"], content: string): Msg => ({ id, role, content, citations: { evidence: [], metrics: [], scope: "deal" }, tool_calls: [], grounded: true, scope: "deal", provider: "mock", model: "rules", error: null, created_at: stamp });
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? "GET";
    if (method === "POST" && /\/chat$/.test(url)) {
      const body = JSON.parse(String(init?.body)) as { message: string; thread_id: string | null };
      posts.push(body);
      const tid = body.thread_id ?? "t1";
      const list = threads.get(tid) ?? [];
      const n = list.length;
      list.push(row(`u${n}`, "user", body.message), row(`a${n}`, "assistant", reply));
      threads.set(tid, list);
      const frames = sse([
        ["meta", { thread_id: tid, provider: config.provider, model: config.model, label: config.label }],
        ...(opts.before ?? []),
        ["tool", { name: "get_findings", label: "Findings", status: "start" }],
        ["text", { delta: reply }],
        ["citations", { evidence: [], metrics: [], scope: "deal" }],
        ["done", { message_id: `a${n}`, content: reply, grounded: true, scope: "deal" }],
      ]);
      return new Response(frames, { status: 200, headers: { "Content-Type": "text/event-stream" } });
    }
    if (/\/chat\/config$/.test(url)) return Response.json(config);
    if (/\/chat\/threads$/.test(url)) return Response.json([...threads.keys()].map((id) => ({ id, title: "Thread", created_at: stamp, updated_at: stamp, message_count: threads.get(id)?.length ?? 0 })));
    const detail = /\/chat\/threads\/([^/]+)$/.exec(url);
    if (detail && threads.has(detail[1])) return Response.json({ id: detail[1], title: "Thread", created_at: stamp, updated_at: stamp, message_count: threads.get(detail[1])?.length ?? 0, messages: threads.get(detail[1]) });
    return Response.json({ detail: "Not found" }, { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, posts };
}

/** StrictMode on purpose: effects run twice in development, and a prompt must still be sent exactly once. */
function renderChat(dealId: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<StrictMode><QueryClientProvider client={qc}><DealChat dealId={dealId} /></QueryClientProvider></StrictMode>);
}

const box = () => screen.getByRole("textbox", { name: "Message" }) as HTMLTextAreaElement;

describe("DealChat panel", () => {
  it("opens on askTheDeal with the prompt prefilled and focused, and takes the prompt without sending", async () => {
    const { posts } = stubApi();
    renderChat("deal-prefill");
    expect(screen.queryByRole("dialog")).toBeNull();
    act(() => { askTheDeal("Explain this finding: Owner salary add-back of $180,000"); });
    const input = await screen.findByRole("textbox", { name: "Message" });
    expect(input).toHaveValue("Explain this finding: Owner salary add-back of $180,000");
    await waitFor(() => expect(document.activeElement).toBe(input));
    expect((input as HTMLTextAreaElement).selectionStart).toBe("Explain this finding: Owner salary add-back of $180,000".length);
    expect(getChatBusState()).toEqual({ open: true, prompt: null });
    expect(await screen.findByText(/offline, rule-based/)).toBeInTheDocument();
    expect(posts).toHaveLength(0);
  });

  it("sends the prompt at once for askTheDeal with send, exactly once, and shows the streamed reply", async () => {
    const { posts } = stubApi("Two documents are still missing.");
    renderChat("deal-send");
    act(() => { askTheDeal("What is missing?", { send: true }); });
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toEqual({ message: "What is missing?", thread_id: null });
    expect(await screen.findByText("Two documents are still missing.")).toBeInTheDocument();
    expect(box()).toHaveValue("");
    expect(getChatBusState().prompt).toBeNull();
    await waitFor(() => expect(screen.getByRole("group", { name: "Quick prompts" })).toBeInTheDocument());
    expect(posts).toHaveLength(1);
  });

  it("shows the quick prompts under the input: two send as they are, two prefill; the row hides while a reply streams", async () => {
    const { posts } = stubApi();
    renderChat("deal-quick");
    fireEvent.click(screen.getByRole("button", { name: /^Chat/ }));
    const group = await screen.findByRole("group", { name: "Quick prompts" });
    expect(within(group).getAllByRole("button").map((b) => b.textContent)).toEqual(QUICK_PROMPTS.map((p) => p.label));
    expect(QUICK_PROMPTS.map((p) => p.label)).toEqual(["Explain this finding", "What should I ask the seller?", "What is missing?", "What changed after this scenario?"]);
    fireEvent.click(within(group).getByRole("button", { name: "What changed after this scenario?" }));
    expect(screen.queryByRole("group", { name: "Quick prompts" })).toBeNull();
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toEqual({ message: "What changed after this scenario?", thread_id: null });
    await screen.findByText("Here is the answer.");
    const again = await screen.findByRole("group", { name: "Quick prompts" });
    fireEvent.click(within(again).getByRole("button", { name: "What is missing?" }));
    await waitFor(() => expect(posts).toHaveLength(2));
    expect(posts[1]).toEqual({ message: "What is missing?", thread_id: "t1" });
    const row = await screen.findByRole("group", { name: "Quick prompts" });
    fireEvent.click(within(row).getByRole("button", { name: "What should I ask the seller?" }));
    expect(box()).toHaveValue("What should I ask the seller about ");
    await waitFor(() => expect(document.activeElement).toBe(box()));
    fireEvent.click(within(row).getByRole("button", { name: "Explain this finding" }));
    expect(box()).toHaveValue("Explain this finding: ");
    expect(posts).toHaveLength(2);
  });

  it("resumes the last conversation when reopened, and a prompt sent while resuming lands in that thread", async () => {
    const { posts } = stubApi("Resumed reply.");
    renderChat("deal-resume");
    act(() => { askTheDeal("Which documents are missing?", { send: true }); });
    await screen.findByText("Resumed reply.", {}, { timeout: 5000 });
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull(), { timeout: 5000 });
    fireEvent.click(screen.getByRole("button", { name: /^Chat/ }));
    expect(await screen.findByText("Resumed reply.", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(posts).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull(), { timeout: 5000 });
    act(() => { askTheDeal("And the contracts?", { send: true }); });
    await waitFor(() => expect(posts).toHaveLength(2), { timeout: 5000 });
    expect(posts[1]).toEqual({ message: "And the contracts?", thread_id: "t1" });
    await waitFor(() => expect(screen.getAllByText("Resumed reply.")).toHaveLength(2), { timeout: 5000 });
  });

  it("names no provider or model when live and hides the model picker unless the server opts in", async () => {
    stubApi("Answer.", { config: LIVE });
    renderChat("deal-live");
    fireEvent.click(screen.getByRole("button", { name: /^Chat/ }));
    expect(await screen.findByText(/^About /)).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Model" })).toBeNull();
    expect(screen.queryByText(/gemini|Google Gemini/i)).toBeNull();
    expect(screen.queryByText("Connect a model")).toBeNull();
  });

  it("shows the model picker when the server sets picker with more than one model", async () => {
    stubApi("Answer.", { config: { ...LIVE, picker: true } });
    renderChat("deal-picker");
    fireEvent.click(screen.getByRole("button", { name: /^Chat/ }));
    const picker = await screen.findByRole("combobox", { name: "Model" });
    expect(within(picker).getAllByRole("option").map((o) => o.textContent)).toEqual(["gemini-3.8-flash", "gemini-3.7-flash"]);
    expect(screen.getByText(/^About /)).toBeInTheDocument();
  });

  it("keeps the picker hidden when picker is set but only one model is offered", async () => {
    stubApi("Answer.", { config: { ...LIVE, picker: true, models: ["gemini-3.8-flash"] } });
    renderChat("deal-one-model");
    fireEvent.click(screen.getByRole("button", { name: /^Chat/ }));
    await screen.findByText(/^About /);
    expect(screen.queryByRole("combobox", { name: "Model" })).toBeNull();
  });

  it("renders a switch notice from the stream above the answer, and the footer still names no model", async () => {
    const { posts } = stubApi("Fallback answer.", { config: LIVE, before: [["switch", { from: "gemini-3.8-flash", to: "gemini-3.7-flash", message: "Gemini 3.8 Flash is busy; answering with Gemini 3.7 Flash." }]] });
    renderChat("deal-switch");
    act(() => { askTheDeal("What is missing?", { send: true }); });
    await waitFor(() => expect(posts).toHaveLength(1), { timeout: 5000 });
    const notice = await screen.findByText("Gemini 3.8 Flash is busy; answering with Gemini 3.7 Flash.");
    const answer = await screen.findByText("Fallback answer.");
    expect(notice.compareDocumentPosition(answer)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    await waitFor(() => expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument(), { timeout: 5000 });
    expect(screen.queryByText(/gemini-3\.[78]-flash/)).toBeNull();
  });

  it("drops a prompt when the panel is closed before it was taken", async () => {
    const { posts } = stubApi();
    renderChat("deal-drop");
    act(() => { askTheDeal("Explain this finding: X"); });
    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    act(() => { setChatOpen(true); });
    const input = await screen.findByRole("textbox", { name: "Message" });
    expect(input).toHaveValue("");
    expect(posts).toHaveLength(0);
  });
});
