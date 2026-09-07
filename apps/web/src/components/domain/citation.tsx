"use client";

import { fmtLocator } from "@/lib/format";
import { FileText, Table2, Rows3 } from "lucide-react";

const DOC_ABBR: Record<string, string> = { cim: "CIM", financial_statements: "FS", acquisition_model: "Model", customer_revenue: "CSV", debt_term_sheet: "Term sheet", customer_contract: "Contract", other: "Doc", unknown: "Doc" };

/** Plain-language names for the Deal Room and anywhere a first-time buyer reads a document type. Keys mirror `DocTypeLiteral` in the API. */
const DOC_NAME: Record<string, string> = {
  cim: "Sales memo (CIM)",
  financial_statements: "Financial statements",
  acquisition_model: "Acquisition model",
  customer_revenue: "Customer revenue file",
  debt_term_sheet: "Loan term sheet",
  customer_contract: "Customer contract",
  other: "Other document",
  unknown: "Not yet classified",
};

/** What each document type contributes, for the "what is missing" checklist. */
export const DOC_PURPOSE: Record<string, string> = {
  cim: "The seller's story: growth, margins, customers, and the adjustments they want you to accept.",
  financial_statements: "The income statement by year; every verified number starts here.",
  acquisition_model: "Purchase price, debt, and the seller's projections.",
  customer_revenue: "Revenue by customer, used to check concentration and recurring revenue.",
  debt_term_sheet: "Rate, amortization, and the covenant the lender will test.",
  customer_contract: "Terms behind the recurring-revenue claims.",
};

export function docTypeName(docType: string | null | undefined): string {
  if (!docType) return DOC_NAME.unknown;
  return DOC_NAME[docType] ?? docType.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function docAbbr(docType: string, name?: string): string {
  if (docType === "customer_contract" && name) {
    const m = name.match(/contract-([a-z]+)/i);
    if (m) return `Contract (${m[1][0].toUpperCase()}${m[1].slice(1)})`;
  }
  return DOC_ABBR[docType] ?? "Doc";
}

export function CitationChip({ docType, documentName, locator, kind, onClick, active = false, label }: { docType: string; documentName?: string; locator: Record<string, unknown> | null | undefined; kind?: string; onClick?: () => void; active?: boolean; label?: string }) {
  const Icon = kind?.startsWith("sheet") ? Table2 : kind?.startsWith("csv") ? Rows3 : FileText;
  const text = label ?? `${docAbbr(docType, documentName)} ${fmtLocator(locator, kind)}`.trim();
  const cls = `inline-flex h-[22px] max-w-full items-center gap-1 rounded-[var(--radius-1)] border px-1.5 font-mono text-[11.5px] leading-none transition-colors duration-[120ms] ${active ? "border-accent bg-accent/10 text-fg" : "border-hairline bg-bg-muted text-fg hover:border-accent"}`;
  if (!onClick) return <span className={cls} title={documentName}><Icon size={11} aria-hidden /><span className="truncate">{text}</span></span>;
  return (
    <button type="button" className={cls} onClick={onClick} title={documentName ? `Open ${documentName}` : "Open source"} aria-pressed={active}>
      <Icon size={11} aria-hidden />
      <span className="truncate">{text}</span>
    </button>
  );
}
