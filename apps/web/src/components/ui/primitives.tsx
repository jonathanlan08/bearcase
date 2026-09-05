import type { ReactNode } from "react";

export function MicroLabel({ children, className = "", as: Tag = "p" }: { children: ReactNode; className?: string; as?: "p" | "span" | "div" | "h2" | "h3" }) {
  return <Tag className={`micro ${className}`}>{children}</Tag>;
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded-[var(--radius-1)] border border-hairline bg-bg-muted px-1 font-mono text-[11px] text-fg-muted">{children}</kbd>;
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden className={`animate-pulse rounded-[var(--radius-1)] bg-bg-muted ${className}`} />;
}

export function Panel({ children, className = "", title, actions, id }: { children: ReactNode; className?: string; title?: ReactNode; actions?: ReactNode; id?: string }) {
  return (
    <section id={id} className={`rounded-[var(--radius-3)] border border-hairline bg-bg-raised ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-hairline px-4 py-3">
          <div className="min-w-0 text-sm font-medium">{title}</div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-[var(--radius-3)] border border-dashed border-hairline px-6 py-14 text-center">
      <EvidenceLinkMark size={28} className="text-fg-muted" />
      <p className="mt-4 text-base font-medium">{title}</p>
      {body && <p className="mt-1 max-w-md text-sm text-fg-muted">{body}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorState({ title = "Something went wrong", detail, onRetry }: { title?: string; detail?: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-[var(--radius-3)] border border-red/40 bg-bg-raised p-4">
      <p className="text-sm font-medium text-red">{title}</p>
      {detail && <p className="mt-1 break-words font-mono text-xs text-fg-muted">{detail}</p>}
      {onRetry && (
        <button type="button" onClick={onRetry} className="mt-3 text-sm font-medium text-accent underline-offset-2 hover:underline">Retry</button>
      )}
    </div>
  );
}

/** Brand symbol: two squares (source, claim) joined by a hairline with a hollow node (the core). */
export function EvidenceLinkMark({ size = 20, className = "", animate = false, title = "BearCase" }: { size?: number; className?: string; animate?: boolean; title?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} role="img" aria-label={title}>
      <rect x="2" y="2" width="5" height="5" fill="currentColor" />
      <rect x="17" y="17" width="5" height="5" fill="currentColor" />
      <line x1="7" y1="7" x2="17" y2="17" stroke="currentColor" strokeWidth="1.25" strokeDasharray={animate ? "14.2" : undefined} strokeDashoffset={animate ? "14.2" : undefined} style={animate ? { animation: "bc-draw 900ms var(--ease-reveal) forwards" } : undefined} />
      <circle cx="12" cy="12" r="2.4" stroke="currentColor" strokeWidth="1.25" fill="var(--bg, transparent)" />
      {animate && <style>{`@keyframes bc-draw { to { stroke-dashoffset: 0; } }`}</style>}
    </svg>
  );
}

export function Wordmark({ className = "", size = "md" }: { className?: string; size?: "md" | "lg" }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <EvidenceLinkMark size={size === "lg" ? 22 : 18} />
      <span className={`font-medium tracking-[-0.02em] ${size === "lg" ? "text-lg" : "text-[15px]"}`}>BearCase</span>
    </span>
  );
}
