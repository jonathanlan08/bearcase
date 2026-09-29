import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReportSharePanel, shareUrl } from "./report-share";
import type { ReportShare } from "@/lib/api";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const share = (id: string, active = true, extra: Partial<ReportShare> = {}): ReportShare => ({ id, report_id: "r1", created_at: "2026-09-28T10:00:00Z", expires_at: null, revoked_at: active ? null : "2026-09-28T11:00:00Z", created_by: "Dana", active, ...extra });

/** Fake API over a mutable list: create appends a live link and returns its path once; revoke marks it inactive. */
function stubApi(rows: ReportShare[], opts: { listStatus?: number; listDetail?: string } = {}) {
  const calls: Array<{ method: string; url: string; body?: unknown }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, url, body });
    if (method === "GET" && /\/shares$/.test(url)) {
      if (opts.listStatus) return Response.json({ detail: opts.listDetail ?? "Refused" }, { status: opts.listStatus });
      return Response.json(rows);
    }
    if (method === "POST" && /\/share$/.test(url)) {
      const s = share(`s${rows.length + 1}`, true, { expires_at: body?.expires_in_days ? "2026-10-05T10:00:00Z" : null });
      rows.unshift(s);
      return Response.json({ ...s, path: "/r/tok_abcdefghijklmnopqrstuvwxyz", url: "http://localhost:3000/r/tok_abcdefghijklmnopqrstuvwxyz" }, { status: 201 });
    }
    const del = /\/shares\/([^/]+)$/.exec(url);
    if (method === "DELETE" && del) { const row = rows.find((r) => r.id === del[1]); if (row) { row.active = false; row.revoked_at = "2026-09-28T12:00:00Z"; } return new Response(null, { status: 204 }); }
    return Response.json({ detail: "Not found" }, { status: 404 });
  }));
  return { calls };
}

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><ReportSharePanel dealId="d1" reportId="r1" /></QueryClientProvider>);
}

describe("shareUrl", () => {
  it("joins this site's origin and the server's path", () => {
    expect(shareUrl("/r/abc", "https://bearcase.me")).toBe("https://bearcase.me/r/abc");
  });
});

describe("ReportSharePanel", () => {
  it("creates a link with the chosen expiry, shows it once with a copy button, and lists it as live", async () => {
    const { calls } = stubApi([share("s0", false)]);
    const writeText = vi.fn(async () => undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    mount();
    await screen.findByText("No live links to this report.");
    expect(screen.getByText(/1 revoked or expired link no longer opens/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Link works"), { target: { value: "7" } });
    fireEvent.click(screen.getByRole("button", { name: "Create link" }));
    const input = await screen.findByLabelText<HTMLInputElement>("Your link");
    expect(input.value).toBe(`${window.location.origin}/r/tok_abcdefghijklmnopqrstuvwxyz`);
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ expires_in_days: 7 });
    expect(screen.getByText(/cannot show it again/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(input.value));
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
    await screen.findByText(/Expires/);
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("revokes a live link and hides the shown link when it was the one revoked", async () => {
    const { calls } = stubApi([share("s1")]);
    mount();
    const revoke = await screen.findByRole("button", { name: /Revoke the link/ });
    fireEvent.click(revoke);
    await screen.findByText("No live links to this report.");
    expect(calls.some((c) => c.method === "DELETE" && c.url.endsWith("/api/deals/d1/reports/r1/shares/s1"))).toBe(true);
  });

  it("shows the API's refusal to a viewer instead of the controls", async () => {
    stubApi([], { listStatus: 403, listDetail: "Viewers can read and chat on this deal; ask the owner for editor access to make changes." });
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("editor access");
    expect(screen.queryByRole("button", { name: "Create link" })).toBeNull();
  });
});
