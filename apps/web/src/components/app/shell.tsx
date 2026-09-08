"use client";

import { CommandPalette } from "@/components/app/command-palette";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useLocalFlag } from "@/lib/hooks";
import { FolderOpen, ListChecks, Calculator, FlaskConical, FileText, MessageCircleQuestionMark, LayoutDashboard, History, PanelLeftClose, PanelLeftOpen, LogOut, ChevronDown, MoreHorizontal, ShieldCheck, Inbox } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, auth, errorDetail } from "@/lib/api";
import { useDeal, useDeals, qk } from "@/components/app/hooks";
import { useMe } from "@/components/app/gate";
import { Wordmark } from "@/components/ui/primitives";
import { DropdownMenu } from "radix-ui";
import { DealChat, useChatConfig } from "@/components/domain/deal-chat";

/** `short` is the mobile bottom-nav label: a whole word that still says what the screen is. */
const PRIMARY = [
  { key: "documents", label: "Deal Room", short: "Documents", n: "01", Icon: FolderOpen },
  { key: "claims", label: "Claim Audit", short: "Claims", n: "02", Icon: ListChecks },
  { key: "financials", label: "Financial Verification", short: "Financials", n: "03", Icon: Calculator },
  { key: "scenarios", label: "Scenario Lab", short: "Scenarios", n: "04", Icon: FlaskConical },
  { key: "report", label: "Red-Team Report", short: "Report", n: "05", Icon: FileText },
  { key: "questions", label: "Seller Questions", short: "Questions", n: "06", Icon: MessageCircleQuestionMark },
];
const SECONDARY = [
  { key: "", label: "Overview", Icon: LayoutDashboard },
  { key: "inbox", label: "Review queue", Icon: Inbox },
  { key: "audit", label: "Audit history", Icon: History },
];

/*
 * Mobile geometry (below md): the bottom nav is 56px plus the safe-area inset; the floating chat trigger is 44px tall and
 * sits above the nav. Content gets enough bottom padding to scroll clear of both, and the trigger's offset includes the
 * safe-area inset so it never lands on the nav on phones with a home indicator. The trigger is rendered by DealChat as
 * the only fixed-position button inside the wrapper (the panel is portaled out), so the descendant-selector class below
 * adjusts only its offset without touching that component or depending on its label.
 */
// Bottom padding keeps the last row of content clear of the bottom nav (mobile) and the floating chat button (desktop).
const MAIN_PAD = "pb-[calc(9rem+env(safe-area-inset-bottom))] md:pb-20";
const CHAT_TRIGGER_OFFSET = "[&_button.fixed]:bottom-[calc(4.5rem+env(safe-area-inset-bottom))] md:[&_button.fixed]:bottom-5";
const MENU_ITEM = "block rounded-[var(--radius-1)] px-2 py-1.5 text-sm outline-none hover:bg-bg-muted focus:bg-bg-muted";

export function DealShell({ children }: { children: React.ReactNode }) {
  const { dealId } = useParams<{ dealId: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const deal = useDeal(dealId);
  const deals = useDeals();
  // Fetched once per deal here; the chat panel reads the same row when it opens.
  const chatConfig = useChatConfig(dealId);
  const me = useMe();
  const [collapsed, setCollapsed] = useLocalFlag("bc.rail");
  const toggle = () => setCollapsed(!collapsed);
  const base = `/app/deals/${dealId}`;
  const isActive = (key: string) => (key ? pathname.startsWith(`${base}/${key}`) : pathname === base);
  const logout = async () => { await api.post("/api/auth/logout"); qc.clear(); router.push("/app"); };

  const NavLink = ({ href, label, Icon, active }: { href: string; label: string; Icon: React.ComponentType<{ size?: number }>; active: boolean }) => (
    <Link href={href} aria-current={active ? "page" : undefined} title={collapsed ? label : undefined} aria-label={collapsed ? label : undefined} className={`group flex h-10 items-center gap-3 rounded-[var(--radius-2)] px-2.5 text-sm transition-colors duration-[120ms] ${active ? "bg-bg-muted font-medium text-fg" : "text-fg-muted hover:bg-bg-muted hover:text-fg"}`}>
      <Icon size={16} />
      {!collapsed && <span className="flex-1 truncate">{label}</span>}
    </Link>
  );

  return (
    <div className="flex min-h-svh">
      <CommandPalette />
      <aside className={`sticky top-0 hidden h-svh shrink-0 flex-col border-r border-hairline bg-bg-raised transition-[width] duration-200 md:flex ${collapsed ? "w-14" : "w-[232px]"}`} aria-label="Deal navigation">
        <div className="flex h-14 items-center justify-between px-3">
          <Link href="/app" className="rounded-[var(--radius-1)]">{collapsed ? <Wordmark className="[&>span:last-child]:hidden" /> : <Wordmark />}</Link>
          <button type="button" onClick={toggle} aria-label={collapsed ? "Expand navigation" : "Collapse navigation"} className="rounded-[var(--radius-1)] p-1.5 text-fg-muted hover:bg-bg-muted">{collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}</button>
        </div>
        <div className="px-2">
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button type="button" className="flex h-10 w-full items-center gap-2 rounded-[var(--radius-2)] border border-hairline px-2.5 text-left text-sm hover:bg-bg-muted" aria-label="Switch deal">
                <span className="min-w-0 flex-1 truncate font-medium">{collapsed ? "•" : deal.data?.company_name ?? "…"}</span>
                {!collapsed && <ChevronDown size={14} className="text-fg-muted" />}
              </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content align="start" sideOffset={6} className="z-50 min-w-[220px] rounded-[var(--radius-2)] border border-hairline bg-bg-raised p-1 shadow-[var(--shadow-2)]">
                {(deals.data ?? []).map((d) => (
                  <DropdownMenu.Item key={d.id} asChild><Link href={`/app/deals/${d.id}`} className={MENU_ITEM}>{d.company_name}</Link></DropdownMenu.Item>
                ))}
                <DropdownMenu.Separator className="my-1 h-px bg-hairline" />
                <DropdownMenu.Item asChild><Link href="/app/deals/new" className={MENU_ITEM}>Create a deal…</Link></DropdownMenu.Item>
                <DropdownMenu.Item asChild><Link href="/app" className={MENU_ITEM}>All deals</Link></DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        </div>
        {!collapsed && <button type="button" onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }))} className="mx-2 mt-3 flex h-8 items-center gap-2 rounded-[var(--radius-2)] border border-hairline px-2 text-left text-xs text-fg-muted hover:bg-bg-muted" aria-label="Find anything (Command K)"><span className="flex-1">Find anything</span><kbd className="font-mono text-[10px]">⌘K</kbd></button>}
        <nav className="mt-3 flex flex-col gap-0.5 px-2">
          {PRIMARY.map((n) => <NavLink key={n.key} href={`${base}/${n.key}`} label={n.label} Icon={n.Icon} active={isActive(n.key)} />)}
          <div className="my-2 h-px bg-hairline" />
          {SECONDARY.map((n) => <NavLink key={n.key} href={n.key ? `${base}/${n.key}` : base} label={n.label} Icon={n.Icon} active={isActive(n.key)} />)}
        </nav>
        <div className="mt-auto flex flex-col gap-2 p-3">
          {!collapsed && chatConfig.data && (
            <p className="truncate px-1 text-[11px] text-fg-muted">Assistant: {chatConfig.data.live ? chatConfig.data.label : "offline, rule-based"}</p>
          )}
          {!collapsed && deal.data?.is_demo && <p className="text-[11px] leading-snug text-fg-muted">{(deal.data.company_name ?? "This deal").split(",")[0]} is fictional. Not financial, legal, tax, or investment advice.</p>}
          <Link href="/trust" className="flex h-8 items-center gap-2 rounded-[var(--radius-1)] px-1 text-xs text-fg-muted hover:bg-bg-muted hover:text-fg" title={collapsed ? "Trust & data" : undefined} aria-label={collapsed ? "Trust & data" : undefined}><ShieldCheck size={14} />{!collapsed && "Trust & data"}</Link>
          {!collapsed && (
            <p className="flex flex-wrap gap-x-2 px-1 text-[11px] text-fg-muted">
              <Link href="/pilot" className="hover:text-fg hover:underline">Pilot</Link>
              <Link href="/terms" className="hover:text-fg hover:underline">Terms</Link>
              <Link href="/privacy" className="hover:text-fg hover:underline">Privacy</Link>
            </p>
          )}
          <button type="button" onClick={logout} className="flex h-8 items-center gap-2 rounded-[var(--radius-1)] px-1 text-xs text-fg-muted hover:bg-bg-muted" title="Sign out" aria-label={collapsed ? "Sign out" : undefined}><LogOut size={14} />{!collapsed && (me.data?.display_name ?? "Sign out")}</button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 items-center gap-3 border-b border-hairline bg-bg-raised px-4 md:hidden">
          <Link href="/app" aria-label="All deals"><Wordmark /></Link>
          <span className="min-w-0 flex-1 truncate text-sm font-medium">{deal.data?.company_name}</span>
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button type="button" className="rounded-[var(--radius-1)] p-1.5 text-fg-muted hover:bg-bg-muted" aria-label="More pages and account"><MoreHorizontal size={18} /></button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content align="end" sideOffset={6} className="z-50 min-w-[200px] rounded-[var(--radius-2)] border border-hairline bg-bg-raised p-1 shadow-[var(--shadow-2)]">
                {SECONDARY.map((n) => <DropdownMenu.Item key={n.key} asChild><Link href={n.key ? `${base}/${n.key}` : base} className={MENU_ITEM} aria-current={isActive(n.key) ? "page" : undefined}>{n.label}</Link></DropdownMenu.Item>)}
                <DropdownMenu.Separator className="my-1 h-px bg-hairline" />
                <DropdownMenu.Item asChild><Link href="/app/deals/new" className={MENU_ITEM}>Create a deal…</Link></DropdownMenu.Item>
                <DropdownMenu.Item asChild><Link href="/app" className={MENU_ITEM}>All deals</Link></DropdownMenu.Item>
                <DropdownMenu.Item asChild><Link href="/trust" className={MENU_ITEM}>Trust &amp; data</Link></DropdownMenu.Item>
                <DropdownMenu.Item asChild><Link href="/pilot" className={MENU_ITEM}>Pilot</Link></DropdownMenu.Item>
                <DropdownMenu.Item asChild><Link href="/terms" className={MENU_ITEM}>Terms</Link></DropdownMenu.Item>
                <DropdownMenu.Item asChild><Link href="/privacy" className={MENU_ITEM}>Privacy</Link></DropdownMenu.Item>
                <DropdownMenu.Item asChild><button type="button" onClick={logout} className={`${MENU_ITEM} w-full text-left`}>Sign out{me.data?.display_name ? ` (${me.data.display_name})` : ""}</button></DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        </header>
        {me.data && !me.data.is_demo && !me.data.email_verified && <VerifyBanner email={me.data.email} />}
        <main id="main" className={`flex-1 ${MAIN_PAD}`}>{children}</main>
        <div className={CHAT_TRIGGER_OFFSET}><DealChat dealId={dealId} /></div>
        <nav className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-6 border-t border-hairline bg-bg-raised pb-[env(safe-area-inset-bottom)] md:hidden" aria-label="Primary">
          {PRIMARY.map(({ key, label, short, Icon }) => (
            <Link key={key} href={`${base}/${key}`} aria-current={isActive(key) ? "page" : undefined} aria-label={label} className={`flex h-14 flex-col items-center justify-center gap-1 text-[10px] ${isActive(key) ? "text-fg font-medium" : "text-fg-muted"}`}>
              <Icon size={18} /><span className="truncate px-1">{short}</span>
            </Link>
          ))}
        </nav>
      </div>
    </div>
  );
}

/** Shown to a signed-in account whose address is not verified yet: sharing a deal needs it. Resend is one click; the reply is worded here. */
export function VerifyBanner({ email }: { email: string }) {
  const [note, setNote] = useState<string | null>(null);
  const resend = useMutation({
    mutationFn: () => auth.resendVerification(),
    onSuccess: () => setNote(`A new link is on its way to ${email}.`),
    onError: (e) => setNote(errorDetail(e, "The link could not be sent. Try again in a minute.")),
  });
  return (
    <div role="status" className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-hairline bg-bg-muted px-4 py-2 text-xs md:px-6">
      <span><span aria-hidden>▲ </span>Your email address is not verified. Open the link we sent to <span className="font-medium">{email}</span> to share deals.</span>
      <button type="button" onClick={() => resend.mutate()} disabled={resend.isPending} className="font-medium text-accent underline-offset-2 hover:underline disabled:opacity-50">Resend the link</button>
      {note && <span className="text-fg-muted">{note}</span>}
    </div>
  );
}

export function PageHeader({ title, kicker, actions, children, className = "" }: { title: string; kicker?: string; actions?: React.ReactNode; children?: React.ReactNode; className?: string }) {
  return (
    <div className={`${className} border-b border-hairline bg-bg px-4 py-5 md:px-6`}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          {kicker && <p className="text-sm text-fg-muted">{kicker}</p>}
          <h1 className="mt-1 text-[26px] md:text-[30px]" tabIndex={-1}>{title}</h1>
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </div>
  );
}

export function useDealKicker(): string {
  const { dealId } = useParams<{ dealId: string }>();
  const deal = useDeal(dealId);
  if (!deal.data) return "";
  return `${deal.data.company_name}${deal.data.is_demo ? " (fictional demonstration deal)" : ""}`;
}

export { qk };
