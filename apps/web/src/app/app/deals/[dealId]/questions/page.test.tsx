import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import QuestionsPage from "./page";
import { getChatBusState, resetChatBus } from "@/lib/chat-bus";
import type { SellerQuestions } from "@/lib/api";

vi.mock("next/navigation", () => ({
  useParams: () => ({ dealId: "d1" }),
  usePathname: () => "/app/deals/d1/questions",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const E1 = "11111111-1111-4111-8111-111111111111";
const E2 = "22222222-2222-4222-8222-222222222222";
const EVIDENCE: Record<string, unknown> = {
  [E1]: { id: E1, document_id: "doc-cim", document_name: "northstar-cim.pdf", doc_type: "cim", kind: "page", chunk_index: 0, locator: { page: 3, paragraph: 2 }, text: "Revenue grew 18% year over year.", structured: null, contains_instruction_text: false },
  [E2]: { id: E2, document_id: "doc-fs", document_name: "statements.xlsx", doc_type: "financial_statements", kind: "sheet_row", chunk_index: 4, locator: { sheet: "Income Statement", row: 4 }, text: "Revenue 12,400,000", structured: { values: ["Revenue", "12400000"] }, contains_instruction_text: false },
};
const QUESTIONS: SellerQuestions = {
  generated_from: { findings: 3, claims: 2 },
  questions: [
    { id: "q-low", question: "Which customers are under a signed maintenance agreement?", why: "The recurring-revenue share could not be checked without the contracts.", kind: "missing_document", severity: "low", evidence_ids: [], metric_ids: [], claim_id: null, finding_id: "f3", document_names: ["northstar-cim.pdf"] },
    { id: "q-high", question: "The sales memo states 18% revenue growth; the statements show 11.6%. Which figure is right?", why: "The memo and the income statement disagree on the same year.", kind: "contradiction", severity: "high", evidence_ids: [E1, E2], metric_ids: ["m1"], claim_id: "claim-growth", finding_id: "f1", document_names: ["northstar-cim.pdf", "statements.xlsx"] },
    { id: "q-high-2", question: "What does the $180,000 owner-salary add-back replace?", why: "The recorded salary is lower than the amount added back.", kind: "unsupported", severity: "high", evidence_ids: [E1], metric_ids: [], claim_id: null, finding_id: "f2", document_names: ["northstar-cim.pdf"] },
  ],
};

function stubApi(questions: SellerQuestions = QUESTIONS) {
  const calls: string[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    calls.push(`${init?.method ?? "GET"} ${url}`);
    if (/\/seller-questions\/export\?format=md$/.test(url)) return new Response("# Questions for the seller\n", { status: 200, headers: { "Content-Type": "text/markdown", "Content-Disposition": 'attachment; filename="northstar-seller-questions.md"' } });
    if (/\/seller-questions$/.test(url)) return Response.json(questions);
    if (/\/api\/deals\/d1$/.test(url)) return Response.json({ id: "d1", company_name: "Northstar HVAC", is_demo: true });
    const ev = /\/evidence\/([^/?]+)$/.exec(url);
    if (ev && EVIDENCE[ev[1]]) return Response.json(EVIDENCE[ev[1]]);
    if (/\/documents\/[^/]+\/evidence/.test(url)) return Response.json([]);
    return Response.json({ detail: "Not found" }, { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(<QueryClientProvider client={qc}><QuestionsPage /></QueryClientProvider>);
  return { ...utils, qc };
}

afterEach(() => { cleanup(); resetChatBus(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("Questions for the seller", () => {
  it("groups questions by severity in order, numbers them, shows the why, and resolves evidence chips to document spots", async () => {
    stubApi();
    renderPage();
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Questions for the seller");
    const headings = await screen.findAllByRole("heading", { level: 2 });
    expect(headings.map((h) => h.textContent)).toEqual(["Ask before you sign", "Worth asking"]);
    expect(screen.getByText(/Built from/)).toHaveTextContent("Built from 3 findings and 2 claims");
    const high = screen.getByRole("region", { name: "Ask before you sign" });
    const rows = within(high).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("The sales memo states 18% revenue growth");
    expect(rows[0]).toHaveTextContent("Why we ask: The memo and the income statement disagree on the same year.");
    expect(rows[0]).toHaveTextContent("Documents disagree");
    expect(within(rows[0]).getByRole("link", { name: "Open the claim" })).toHaveAttribute("href", "/app/deals/d1/claims?claim=claim-growth");
    expect(await within(rows[0]).findByRole("button", { name: /CIM p\.3/ })).toBeInTheDocument();
    expect(within(rows[0]).getByRole("button", { name: /Income Statement!4/ })).toBeInTheDocument();
    const low = screen.getByRole("region", { name: "Worth asking" });
    expect(within(low).getByRole("listitem")).toHaveTextContent("Sources: northstar-cim.pdf");
    expect(within(low).queryByRole("link", { name: "Open the claim" })).toBeNull();
    // numbering runs across groups
    expect(within(low).getByRole("checkbox").getAttribute("aria-label")).toMatch(/^Include question 3:/);
  });

  it("copies only the ticked questions, with the reason and sources, and every question is ticked by default", async () => {
    stubApi();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderPage();
    const boxes = await screen.findAllByRole("checkbox");
    expect(boxes).toHaveLength(3);
    for (const b of boxes) expect(b).toBeChecked();
    expect(screen.getByText(/ticked\./)).toHaveTextContent("3 of 3 ticked");
    fireEvent.click(boxes[1]);
    expect(boxes[1]).not.toBeChecked();
    expect(screen.getByText(/ticked\./)).toHaveTextContent("2 of 3 ticked");
    const copy = screen.getByRole("button", { name: "Copy all" });
    await act(async () => { fireEvent.click(copy); await Promise.resolve(); });
    expect(writeText).toHaveBeenCalledTimes(1);
    const text = writeText.mock.calls[0][0] as string;
    expect(text.startsWith("Questions for the seller: Northstar HVAC")).toBe(true);
    expect(text).toContain("1. The sales memo states 18% revenue growth");
    expect(text).toContain("   Why we ask: The memo and the income statement disagree on the same year.");
    expect(text).toContain("   Sources: northstar-cim.pdf, statements.xlsx");
    expect(text).not.toContain("owner-salary add-back");
    expect(text).toContain("3. Which customers are under a signed maintenance agreement?");
    expect(copy).toHaveTextContent("Copied");
  });

  it("hands 'Draft with the assistant' to the chat bus as a sent prompt that asks for evidence ids", async () => {
    stubApi();
    renderPage();
    const buttons = await screen.findAllByRole("button", { name: "Draft with the assistant" });
    fireEvent.click(buttons[0]);
    const state = getChatBusState();
    expect(state.open).toBe(true);
    expect(state.prompt).toMatchObject({ send: true, text: "Draft a question for the seller about: The sales memo states 18% revenue growth; the statements show 11.6%. Which figure is right?. Cite the evidence ids." });
  });

  it("downloads the Markdown export with the server's file name and invalidates the workflow progress", async () => {
    const { calls } = stubApi();
    const createObjectURL = vi.fn(() => "blob:questions");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const { qc } = renderPage();
    qc.setQueryData(["progress", "d1"], { steps: [] });
    const button = await screen.findByRole("button", { name: "Download .md" });
    fireEvent.click(button);
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(calls).toContain("GET /api/deals/d1/seller-questions/export?format=md");
    const anchor = click.mock.instances[0] as HTMLAnchorElement;
    expect(anchor.download).toBe("northstar-seller-questions.md");
    expect(anchor.href).toContain("blob:questions");
    await waitFor(() => expect(qc.getQueryState(["progress", "d1"])?.isInvalidated).toBe(true));
  });

  it("opens the document viewer from an evidence chip", async () => {
    stubApi();
    renderPage();
    const chip = await screen.findByRole("button", { name: /Income Statement!4/ });
    fireEvent.click(chip);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("statements.xlsx")).toBeInTheDocument();
    expect(within(dialog).getByText(/Cited location: Income Statement!4/)).toBeInTheDocument();
  });

  it("shows an empty state with a way to the Deal Room when nothing has been found to ask", async () => {
    stubApi({ questions: [], generated_from: { findings: 0, claims: 0 } });
    renderPage();
    expect(await screen.findByText("No questions yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the Deal Room" })).toHaveAttribute("href", "/app/deals/d1/documents");
    expect(screen.queryByRole("button", { name: "Copy all" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Download .md" })).toBeNull();
  });
});
