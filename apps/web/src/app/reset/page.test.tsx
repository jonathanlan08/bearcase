import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ResetPage from "./page";

const params = vi.hoisted(() => ({ token: "" as string | null }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(params.token ? { token: params.token } : {}),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

afterEach(() => { cleanup(); vi.unstubAllGlobals(); params.token = ""; });

function stubReset(reply: () => Response) {
  const posts: Array<{ url: string; body: unknown }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    posts.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    return reply();
  }));
  return posts;
}

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><ResetPage /></QueryClientProvider>);
}

describe("/reset", () => {
  it("asks for the password twice, refuses a mismatch, and posts the token with the new password", async () => {
    params.token = "tok";
    const posts = stubReset(() => Response.json({ ok: true }));
    mount();
    const first = screen.getByLabelText(/^New password \*?$/);
    const again = screen.getByLabelText(/New password again/);
    fireEvent.change(first, { target: { value: "correct horse" } });
    fireEvent.change(again, { target: { value: "correct hors" } });
    expect(screen.getByRole("alert")).toHaveTextContent("The two passwords differ.");
    expect(screen.getByRole("button", { name: "Change password" })).toBeDisabled();
    fireEvent.change(again, { target: { value: "correct horse" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    await screen.findByText("Password changed");
    expect(posts).toHaveLength(1);
    expect(posts[0].url).toBe("/api/auth/reset");
    expect(posts[0].body).toEqual({ token: "tok", password: "correct horse" });
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/app");
  });

  it("shows the API's reason with a link to request a new link when the token is refused", async () => {
    params.token = "old";
    stubReset(() => Response.json({ detail: "This link has already been used." }, { status: 400 }));
    mount();
    fireEvent.change(screen.getByLabelText(/^New password \*?$/), { target: { value: "correct horse" } });
    fireEvent.change(screen.getByLabelText(/New password again/), { target: { value: "correct horse" } });
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This link has already been used.");
    expect(screen.getByRole("link", { name: "Request a new link" })).toHaveAttribute("href", "/forgot");
  });

  it("offers a new link instead of a form when the token is missing", () => {
    const posts = stubReset(() => Response.json({ ok: true }));
    mount();
    expect(screen.getByText("This link did not work")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Request a new link" })).toHaveAttribute("href", "/forgot");
    expect(posts).toHaveLength(0);
  });
});
