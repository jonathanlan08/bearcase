import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { ConnectModel, MessageView, type ChatOption, type Msg } from "./deal-chat";

const OPTIONS: ChatOption[] = [
  { provider: "gemini", label: "Google Gemini", env: "GEMINI_API_KEY", free_tier: true, free_tier_note: "Free of charge for Flash models; limits shown in AI Studio.", default_model: "gemini-3.8-flash", key_url: "https://aistudio.google.com/apikey" },
  { provider: "groq", label: "Groq", env: "GROQ_API_KEY", free_tier: true, free_tier_note: "Free plan, no card needed.", default_model: "openai/gpt-oss-120b", key_url: "https://console.groq.com/keys" },
  { provider: "openai", label: "OpenAI", env: "OPENAI_API_KEY", free_tier: false, free_tier_note: "Prepaid credits, minimum $5.", default_model: "gpt-5.6-luna", key_url: "https://platform.openai.com/api-keys" },
];

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
    const { getByText } = render(<ol><MessageView m={msg({ label: "Google Gemini" })} onOpen={() => {}} /></ol>);
    expect(getByText("Google Gemini · gemini-3.8-flash")).toBeInTheDocument();
  });
  it("falls back to provider/model for persisted messages without a label", () => {
    const { getByText } = render(<ol><MessageView m={msg({})} onOpen={() => {}} /></ol>);
    expect(getByText("gemini/gemini-3.8-flash")).toBeInTheDocument();
  });
});
