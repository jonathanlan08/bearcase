import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { ConnectModel, MessageView, type ChatOption, type Msg } from "./deal-chat";

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
const noop = () => {};
afterEach(cleanup);

function msg(overrides: Partial<Msg>): Msg {
  return { id: "m1", role: "assistant", content: "Revenue grew.", citations: { evidence: [], metrics: [] }, tool_calls: [], grounded: true, provider: "gemini", model: "gemini-3.8-flash", error: null, created_at: "2026-09-06T10:00:00Z", ...overrides };
}

describe("ConnectModel", () => {
  it("lists options in API order with label link, env var, default model, and a plain 'free tier' marker", () => {
    const { container, getAllByRole, getByText, queryAllByText } = render(<ConnectModel options={OPTIONS} />);
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
    expect(getByText("gemini-3.8-flash")).toBeInTheDocument();
    expect(queryAllByText("free tier")).toHaveLength(2);
    expect(container.querySelector("svg")).toBeNull();
  });
  it("renders nothing when there are no options", () => {
    const { container } = render(<ConnectModel options={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("MessageView footer", () => {
  it("shows the human label with the model when the stream meta carried one", () => {
    const { getByText } = render(<ol><MessageView m={msg({ label: "Google Gemini" })} onOpen={noop} /></ol>);
    expect(getByText("Google Gemini · gemini-3.8-flash")).toBeInTheDocument();
  });
  it("falls back to provider/model for persisted messages without a label", () => {
    const { getByText } = render(<ol><MessageView m={msg({})} onOpen={noop} /></ol>);
    expect(getByText("gemini/gemini-3.8-flash")).toBeInTheDocument();
  });
  it("keeps the supported glyph and label for a grounded deal answer", () => {
    const { getByText, container } = render(<ol><MessageView m={msg({ scope: "deal", grounded: true })} onOpen={noop} /></ol>);
    expect(getByText("Every factual paragraph cited")).toBeInTheDocument();
    expect(container.querySelector("svg circle")).not.toBeNull();
    expect(container.querySelector("svg rect")).toBeNull();
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

describe("MessageView content", () => {
  it("renders Markdown with citation chips", () => {
    const m = msg({ content: `## Summary\n\n- Revenue grew 18% [E:${E1}]\n- Use \`dscr\`` , citations: { evidence: [{ id: E1, document_id: "d1", document_name: "cim.pdf", doc_type: "cim", locator: { page: 3 }, kind: "page", text: "" }], metrics: [] } });
    const { container, getByRole } = render(<ol><MessageView m={m} onOpen={noop} /></ol>);
    expect(container.querySelector("h4")).toHaveTextContent("Summary");
    expect(container.querySelectorAll("ul > li")).toHaveLength(2);
    expect(getByRole("button", { name: /CIM p\.3/ })).toBeInTheDocument();
    expect(container.querySelector("code")).toHaveTextContent("dscr");
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
    expect(getByText("gemini/gemini-3.8-flash")).toBeInTheDocument();
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
