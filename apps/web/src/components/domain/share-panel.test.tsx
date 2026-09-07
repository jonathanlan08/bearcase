import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SharePanel, isOwner, MAX_MEMBERS } from "./share-panel";
import type { DealMember, DealMembers, User } from "@/lib/api";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const OWNER: User = { id: "u1", email: "Owner@Example.com", display_name: "Dana Owner", is_demo: false, email_verified: true };
const VIEWER: User = { id: "u2", email: "pat@example.com", display_name: "Pat", is_demo: false, email_verified: true };
const members = (rows: DealMember[]): DealMembers => ({ owner: { email: "owner@example.com", display_name: "Dana Owner" }, members: rows });
const row = (id: string, email: string, accepted: boolean, role: DealMember["role"] = "viewer"): DealMember => ({ id, email, role, accepted });

/** Fake API: `me` decides who is signed in; the member list is mutable so invites and removals show up on refetch. */
function stubApi(me: User, list: DealMembers, opts: { inviteStatus?: number; inviteDetail?: string } = {}) {
  const calls: Array<{ method: string; url: string; body?: unknown }> = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, url, body });
    if (/\/auth\/me$/.test(url)) return Response.json(me);
    if (method === "GET" && /\/members$/.test(url)) return Response.json(list);
    if (method === "POST" && /\/members$/.test(url)) {
      if (opts.inviteStatus) return Response.json({ detail: opts.inviteDetail ?? "Refused" }, { status: opts.inviteStatus });
      const m = row(`m${list.members.length + 1}`, body.email, false, body.role);
      list.members.push(m);
      return Response.json(m);
    }
    const del = /\/members\/([^/]+)$/.exec(url);
    if (method === "DELETE" && del) { list.members = list.members.filter((m) => m.id !== del[1]); return new Response(null, { status: 204 }); }
    return Response.json({ detail: "Not found" }, { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls };
}

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><SharePanel dealId="d1" /></QueryClientProvider>);
}

describe("isOwner", () => {
  it("compares the owner's email case-insensitively and is false without data or a user", () => {
    expect(isOwner(members([]), "OWNER@example.com")).toBe(true);
    expect(isOwner(members([]), "pat@example.com")).toBe(false);
    expect(isOwner(undefined, "owner@example.com")).toBe(false);
    expect(isOwner(members([]), undefined)).toBe(false);
  });
});

describe("SharePanel", () => {
  it("shows the owner, each member with role and pending state, and the invite form to the owner", async () => {
    stubApi(OWNER, members([row("m1", "pat@example.com", true, "editor"), row("m2", "sam@example.com", false)]));
    mount();
    await screen.findByText("Invite a collaborator", { selector: "p" });
    expect(screen.getByText("Dana Owner")).toBeInTheDocument();
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText("Editor")).toBeInTheDocument();
    expect(within(items[0]).getByText("Accepted")).toBeInTheDocument();
    expect(within(items[1]).getByText("Viewer")).toBeInTheDocument();
    expect(within(items[1]).getByText("Invite pending")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove sam@example.com" })).toBeInTheDocument();
    expect(screen.getByText(`2/${MAX_MEMBERS}`)).toBeInTheDocument();
  });

  it("sends an invite with the chosen role, then lists it as pending", async () => {
    const { calls } = stubApi(OWNER, members([]));
    mount();
    await screen.findByText("Nobody else can open this deal yet.");
    fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "new@example.com" } });
    fireEvent.change(screen.getByLabelText(/Role/), { target: { value: "editor" } });
    expect(screen.getByText(/except delete the deal, manage members/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Send invite" }));
    await screen.findByText("Invite pending");
    const post = calls.find((c) => c.method === "POST");
    expect(post?.body).toEqual({ email: "new@example.com", role: "editor" });
    expect(screen.getByText("new@example.com")).toBeInTheDocument();
    expect((screen.getByLabelText(/Email/) as HTMLInputElement).value).toBe("");
  });

  it("shows the API's refusal sentence when an invite fails", async () => {
    stubApi(OWNER, members([]), { inviteStatus: 400, inviteDetail: "That address already has access." });
    mount();
    await screen.findByText("Nobody else can open this deal yet.");
    fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "dup@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Send invite" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That address already has access.");
  });

  it("disables inviting until the owner's email is verified, and at the member cap", async () => {
    stubApi({ ...OWNER, email_verified: false }, members([]));
    mount();
    await screen.findByText(/Verify your email address before sharing/);
    expect(screen.getByRole("button", { name: "Send invite" })).toBeDisabled();
    expect(screen.getByLabelText(/Email/)).toBeDisabled();
    cleanup();
    stubApi(OWNER, members(Array.from({ length: MAX_MEMBERS }, (_, i) => row(`m${i}`, `p${i}@example.com`, true))));
    mount();
    await screen.findByText(new RegExp(`maximum of ${MAX_MEMBERS} members`));
    expect(screen.getByRole("button", { name: "Send invite" })).toBeDisabled();
  });

  it("gives a member no invite form and only a Leave action on their own row", async () => {
    const { calls } = stubApi(VIEWER, members([row("m1", "PAT@example.com", true), row("m2", "sam@example.com", true)]));
    mount();
    await screen.findByText("(you)");
    expect(screen.queryByText("Invite a collaborator")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Remove/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Leave this deal" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.url.endsWith("/members/m1"))).toBe(true));
    await waitFor(() => expect(screen.queryByText("(you)")).not.toBeInTheDocument());
  });
});
