import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SharedReportBody, SharedReportView } from "./shared-report";
import type { SharedReport } from "@/lib/api";

beforeAll(() => {
  // Radix positions the popover with ResizeObserver, which jsdom does not provide.
  globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const EV = "11111111-2222-3333-4444-555555555555";
const GONE = "99999999-2222-3333-4444-555555555555";
const M = "aaaaaaaa-2222-3333-4444-555555555555";

const REPORT: SharedReport = {
  company_name: "Northstar HVAC Services",
  is_demo: true,
  version_no: 3,
  generated_at: "2026-09-28T10:00:00Z",
  outcome: "material_concerns_identified",
  validation: { valid: true, material_statements: 36, material_cited: 36 },
  provenance: { provider: "mock", model: "rules", prompt_version: "p1", schema_version: "s1", engine_version: "e1" },
  sections: [
    { key: "executive_summary", title: "Executive summary", kind: "narrative", derived_from: [], table: { columns: [], rows: [] }, statements: [{ text: "Revenue grew 11.6% a year, not 18%.", role: null, evidence_ids: [EV, GONE], metric_ids: [M] }] },
    { key: "claim_table", title: "Claims", kind: "table", derived_from: [], statements: [], table: { columns: ["Claim", "Status", "Verified"], rows: [{ label: "Growth", cells: ["Revenue grew 18%", "contradicted", "11.6%"], evidence_ids: [EV], metric_ids: [], status: "contradicted", decision: null, severity: null }] } },
  ],
  evidence: { [EV]: { document_name: "income-statement.xlsx", locator: "sheet Income Statement, row 4", snippet: "Revenue 4,120,000 3,690,000" } },
  metrics: { [M]: { label: "Revenue CAGR", period: "FY2025", formula: "(end / start) ^ (1 / years) - 1" } },
};

describe("SharedReportBody", () => {
  it("shows the header, the outcome with a glyph and label, and the fictional-deal footer with a link home", () => {
    render(<SharedReportBody data={REPORT} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Northstar HVAC Services");
    expect(screen.getByText((_, el) => el?.tagName === "P" && el.textContent === "Shared from BearCase, read only")).toBeInTheDocument();
    expect(screen.getByText(/Red-team review, version 3, generated/)).toBeInTheDocument();
    expect(screen.getAllByText("Material concerns identified").length).toBeGreaterThan(0);
    expect(screen.getByText(/every figure in this report are fictional/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "bearcase.me" })).toHaveAttribute("href", "https://bearcase.me");
    // the status cell in a table carries its label, not colour alone
    expect(screen.getAllByText("Contradicted").length).toBeGreaterThan(0);
  });

  it("omits the fictional note for a real deal", () => {
    render(<SharedReportBody data={{ ...REPORT, is_demo: false }} />);
    expect(screen.queryByText(/fictional/)).toBeNull();
  });

  it("opens a citation's document name, location, and passage in place, and says when a source is gone", async () => {
    render(<SharedReportBody data={REPORT} />);
    fireEvent.click(screen.getAllByRole("button", { name: `Source E:${EV.slice(0, 6)}` })[0]);
    expect(await screen.findByText("income-statement.xlsx")).toBeInTheDocument();
    expect(screen.getByText("sheet Income Statement, row 4")).toBeInTheDocument();
    expect(screen.getByText("Revenue 4,120,000 3,690,000")).toBeInTheDocument();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: `Source E:${GONE.slice(0, 6)}` }));
    expect(await screen.findByText("This source is no longer in the deal.")).toBeInTheDocument();
  });
});

describe("SharedReportView", () => {
  it("reads the report without credentials beyond the token and shows the API's reason for a dead link", async () => {
    const fetchMock = vi.fn(async () => Response.json({ detail: "This link does not work. It may have been revoked or expired; ask the sender for a new one." }, { status: 404 }));
    vi.stubGlobal("fetch", fetchMock);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={qc}><SharedReportView token="tok_abcdefghijklmnopqrstuvwxyz" /></QueryClientProvider>);
    expect(await screen.findByRole("heading", { name: "This report is not available" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("revoked or expired");
    expect(fetchMock).toHaveBeenCalledWith("/api/shared/reports/tok_abcdefghijklmnopqrstuvwxyz", expect.anything());
  });
});
