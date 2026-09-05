import type { ClaimStatus } from "@/lib/api";

export type StatusKey = ClaimStatus | "warning" | "breach" | "accepted" | "rejected" | "ready" | "failed" | "queued" | "running" | "parsing" | "extracting" | "uploaded" | "succeeded" | "cancelled" | "pending";

export const STATUS_LABEL: Record<string, string> = {
  supported: "Supported", contradicted: "Contradicted", unsupported: "Unsupported", review_required: "Review required", pending: "Pending",
  warning: "Below threshold", breach: "Covenant breach", accepted: "Accepted", rejected: "Rejected",
  ready: "Ready", failed: "Failed", queued: "Queued", running: "Running", parsing: "Parsing", extracting: "Extracting", uploaded: "Uploaded", succeeded: "Succeeded", cancelled: "Cancelled",
};

const TONE: Record<string, string> = {
  supported: "text-accent", accepted: "text-accent", ready: "text-accent", succeeded: "text-accent",
  contradicted: "text-red", breach: "text-red", rejected: "text-red", failed: "text-red",
  review_required: "text-amber", warning: "text-amber", running: "text-amber", parsing: "text-amber", extracting: "text-amber",
  unsupported: "text-graphite", pending: "text-graphite", queued: "text-graphite", uploaded: "text-graphite", cancelled: "text-graphite",
};

/** Shape + glyph + color. Never color alone. */
export function StatusGlyph({ status, size = 14, className = "" }: { status: string; size?: number; className?: string }) {
  const tone = TONE[status] ?? "text-graphite";
  const common = { width: size, height: size, viewBox: "0 0 16 16", "aria-hidden": true, className: `shrink-0 ${tone} ${className}` } as const;
  switch (status) {
    case "supported":
    case "accepted":
    case "ready":
    case "succeeded":
      return (<svg {...common}><circle cx="8" cy="8" r="7" fill="currentColor" /><path d="M4.5 8.2l2.3 2.3 4.7-4.8" stroke="var(--bg-raised)" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>);
    case "contradicted":
    case "breach":
    case "rejected":
    case "failed":
      return (<svg {...common}><path d="M8 1l7 7-7 7-7-7z" fill="currentColor" /><path d="M8 4.6v4.2M8 11.2v.4" stroke="var(--bg-raised)" strokeWidth="1.6" strokeLinecap="round" /></svg>);
    case "review_required":
    case "running":
    case "parsing":
    case "extracting":
      return (<svg {...common}><rect x="1.5" y="1.5" width="13" height="13" rx="1" stroke="currentColor" strokeWidth="1.6" fill="none" /><path d="M6.2 6.3a1.9 1.9 0 113 1.6c-.7.4-1.2.9-1.2 1.6M8 11.6v.3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" fill="none" /></svg>);
    case "warning":
      return (<svg {...common}><path d="M8 1.8L15 14H1z" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinejoin="round" /><path d="M8 6v3.4M8 11.6v.3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>);
    default:
      return (<svg {...common}><circle cx="8" cy="8" r="6.6" stroke="currentColor" strokeWidth="1.6" strokeDasharray="2.4 2.2" fill="none" /><path d="M5.2 8h5.6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>);
  }
}

export function StatusChip({ status, size = "md", className = "" }: { status: string; size?: "sm" | "md"; className?: string }) {
  const tone = TONE[status] ?? "text-graphite";
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-hairline bg-bg-raised ${size === "sm" ? "h-5 px-1.5 text-[11px]" : "h-6 px-2 text-xs"} font-medium ${tone} ${className}`}>
      <StatusGlyph status={status} size={size === "sm" ? 11 : 13} />
      <span className="text-fg">{STATUS_LABEL[status] ?? status}</span>
    </span>
  );
}

export function ConfidenceMeter({ value }: { value: string | number }) {
  const n = Math.max(0, Math.min(1, Number(value)));
  const filled = Math.round(n * 5);
  return (
    <span className="inline-flex items-center gap-1.5" aria-label={`Confidence ${Math.round(n * 100)}%`} title={`Confidence ${Math.round(n * 100)}%`}>
      <span className="flex gap-0.5" aria-hidden>
        {[0, 1, 2, 3, 4].map((i) => (<span key={i} className={`h-2 w-1.5 rounded-[1px] ${i < filled ? "bg-fg" : "bg-bg-muted border border-hairline"}`} />))}
      </span>
      <span className="num text-xs text-fg-muted">{Math.round(n * 100)}%</span>
    </span>
  );
}

export function SeverityChip({ severity }: { severity: string }) {
  const map: Record<string, string> = { critical: "text-red", high: "text-red", medium: "text-amber", low: "text-graphite" };
  const shape: Record<string, string> = { critical: "breach", high: "contradicted", medium: "warning", low: "unsupported" };
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium ${map[severity] ?? "text-graphite"}`}>
      <StatusGlyph status={shape[severity] ?? "unsupported"} size={11} />
      <span className="text-fg">{severity}</span>
    </span>
  );
}
