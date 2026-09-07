import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import VerifyPage from "./page";

const params = vi.hoisted(() => ({ token: "" as string | null }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(params.token ? { token: params.token } : {}),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

afterEach(() => { cleanup(); vi.unstubAllGlobals(); params.token = ""; });

function stubVerify(reply: () => Response) {
  const posts: Array<{ url: string; body: unknown }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    posts.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    return reply();
  }));
  return posts;
}

describe("/verify", () => {
  it("posts the token from the query once and shows success", async () => {
    params.token = "abc123";
    const posts = stubVerify(() => Response.json({ verified: true }));
    render(<VerifyPage />);
    await screen.findByText("Email verified");
    expect(posts).toHaveLength(1);
    expect(posts[0].url).toBe("/api/auth/verify");
    expect(posts[0].body).toEqual({ token: "abc123" });
    expect(screen.getByRole("link", { name: "Open your deals" })).toHaveAttribute("href", "/app");
  });

  it("shows the API's reason and a resend hint when the token is refused", async () => {
    params.token = "expired";
    stubVerify(() => Response.json({ detail: "This link has expired." }, { status: 400 }));
    render(<VerifyPage />);
    await screen.findByText("This link did not work");
    expect(screen.getByText("This link has expired.")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Resend the link");
  });

  it("does not call the API when the link has no token", () => {
    const posts = stubVerify(() => Response.json({ verified: true }));
    render(<VerifyPage />);
    expect(screen.getByText("This link did not work")).toBeInTheDocument();
    expect(screen.getByText(/This link has no token/)).toBeInTheDocument();
    expect(posts).toHaveLength(0);
  });
});
