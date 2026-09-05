"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useLocalFlag } from "@/lib/hooks";
import { FolderOpen, ListChecks, Calculator, FlaskConical, FileText, LayoutDashboard, History, PanelLeftClose, PanelLeftOpen, LogOut, ChevronDown } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useDeal, useDeals, useSummary, qk } from "@/components/app/hooks";
import { useMe } from "@/components/app/gate";
import { Wordmark } from "@/components/ui/primitives";
import { DropdownMenu } from "radix-ui";

const PRIMARY = [
  { key: "documents", label: "Deal Room", n: "01", Icon: FolderOpen },
  { key: "claims", label: "Claim Audit", n: "02", Icon: ListChecks },
  { key: "financials", label: "Financial Verification", n: "03", Icon: Calculator },
  { key: "scenarios", label: "Scenario Lab", n: "04", Icon: FlaskConical },
  { key: "report", label: "Red-Team Report", n: "05", Icon: FileText },
];
const SECONDARY = [
  { key: "", label: "Overview", Icon: LayoutDashboard },
  { key: "audit", label: "Audit history", Icon: History },
];

export function DealShell({ children }: { children: React.ReactNode }) {
  const { dealId } = useParams<{ dealId: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const deal = useDeal(dealId);
  const deals = useDeals();
  const summary = useSummary(dealId);
  const me = useMe();
  const [collapsed, setCollapsed] = useLocalFlag("bc.rail");
  const toggle = () => setCollapsed(!collapsed);
  const base = `/app/deals/${dealId}`;
  const isActive = (key: string) => (key ? pathname.startsWith(`${base}/${key}`) : pathname === base);
  const mode = summary.data?.mode;
  const logout = async () => { await api.post("/api/auth/logout"); qc.clear(); router.push("/app"); };

  const NavLink = ({ href, label, n, Icon, active }: { href: string; label: string; n?: string; Icon: React.ComponentType<{ size?: number }>; active: boolean }) => (
    <Link href={href} aria-current={active ? "page" : undefined} title={collapsed ? label : undefined} className={`group flex h-10 items-center gap-3 rounded-[var(--radius-2)] px-2.5 text-sm transition-colors duration-[120ms] ${active ? "bg-bg-muted font-medium text-fg" : "text-fg-muted hover:bg-bg-muted hover:text-fg"}`}>
      <Icon size={16} />
      {!collapsed && (<><span className="flex-1 truncate">{label}</span>{n && <span className="micro text-[10px] text-fg-muted">{n}</span>}</>)}
    </Link>
  );

  return (
    <div className="flex min-h-svh">
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
                  <DropdownMenu.Item key={d.id} asChild><Link href={`/app/deals/${d.id}`} className="block rounded-[var(--radius-1)] px-2 py-1.5 text-sm outline-none hover:bg-bg-muted focus:bg-bg-muted">{d.company_name}</Link></DropdownMenu.Item>
                ))}
                <DropdownMenu.Separator className="my-1 h-px bg-hairline" />
                <DropdownMenu.Item asChild><Link href="/app/deals/new" className="block rounded-[var(--radius-1)] px-2 py-1.5 text-sm outline-none hover:bg-bg-muted focus:bg-bg-muted">Create a deal…</Link></DropdownMenu.Item>
                <DropdownMenu.Item asChild><Link href="/app" className="block rounded-[var(--radius-1)] px-2 py-1.5 text-sm outline-none hover:bg-bg-muted focus:bg-bg-muted">All deals</Link></DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        </div>
        <nav className="mt-3 flex flex-col gap-0.5 px-2">
          {PRIMARY.map((n) => <NavLink key={n.key} href={`${base}/${n.key}`} label={n.label} n={n.n} Icon={n.Icon} active={isActive(n.key)} />)}
          <div className="my-2 h-px bg-hairline" />
          {SECONDARY.map((n) => <NavLink key={n.key} href={n.key ? `${base}/${n.key}` : base} label={n.label} Icon={n.Icon} active={isActive(n.key)} />)}
        </nav>
        <div className="mt-auto flex flex-col gap-2 p-3">
          {!collapsed && mode && (
            <div className="rounded-[var(--radius-2)] border border-hairline p-2">
              <p className="micro">{mode.provider === "anthropic" ? "Anthropic" : "Mock AI"}</p>
              <p className="mt-0.5 truncate font-mono text-[11px] text-fg-muted">{mode.model}</p>
            </div>
          )}
          {!collapsed && deal.data?.is_demo && <p className="text-[11px] leading-snug text-fg-muted">Northstar HVAC is fictional. Not financial, legal, tax, or investment advice.</p>}
          <button type="button" onClick={logout} className="flex h-8 items-center gap-2 rounded-[var(--radius-1)] px-1 text-xs text-fg-muted hover:bg-bg-muted" title="Sign out"><LogOut size={14} />{!collapsed && (me.data?.display_name ?? "Sign out")}</button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 items-center gap-3 border-b border-hairline bg-bg-raised px-4 md:hidden">
          <Link href="/app"><Wordmark /></Link>
          <span className="min-w-0 flex-1 truncate text-sm font-medium">{deal.data?.company_name}</span>
        </header>
        <main id="main" className="flex-1 pb-20 md:pb-0">{children}</main>
        <nav className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t border-hairline bg-bg-raised pb-[env(safe-area-inset-bottom)] md:hidden" aria-label="Primary">
          {PRIMARY.map(({ key, label, Icon }) => (
            <Link key={key} href={`${base}/${key}`} aria-current={isActive(key) ? "page" : undefined} className={`flex h-14 flex-col items-center justify-center gap-1 text-[10px] ${isActive(key) ? "text-fg font-medium" : "text-fg-muted"}`}>
              <Icon size={18} /><span className="truncate px-1">{label.split(" ")[0]}</span>
            </Link>
          ))}
        </nav>
      </div>
    </div>
  );
}

export function PageHeader({ title, kicker, actions, children }: { title: string; kicker?: string; actions?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="border-b border-hairline bg-bg px-4 py-5 md:px-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          {kicker && <p className="micro">{kicker}</p>}
          <h1 className="mt-1 text-3xl md:text-[34px]" tabIndex={-1}>{title}</h1>
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
  return `${deal.data.company_name}${deal.data.is_demo ? " · fictional" : ""}`.toUpperCase();
}

export { qk };
