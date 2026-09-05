import type { ReactNode } from "react";

export function Table({ children, caption, className = "", stickyFirst = false }: { children: ReactNode; caption?: string; className?: string; stickyFirst?: boolean }) {
  return (
    <div className={`scroll-x rounded-[var(--radius-2)] border border-hairline ${className}`}>
      <table className={`w-full border-collapse text-sm ${stickyFirst ? "[&_td:first-child]:sticky [&_td:first-child]:left-0 [&_td:first-child]:bg-bg-raised [&_th:first-child]:sticky [&_th:first-child]:left-0 [&_th:first-child]:z-[1] [&_th:first-child]:bg-bg-muted" : ""}`}>
        {caption && <caption className="sr-only">{caption}</caption>}
        {children}
      </table>
    </div>
  );
}

export const th = "px-3 py-2 text-left text-xs font-medium text-fg-muted bg-bg-muted border-b border-hairline whitespace-nowrap";
export const td = "px-3 py-2 align-top border-b border-hairline last:border-b-0";
