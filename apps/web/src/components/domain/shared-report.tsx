"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Popover } from "radix-ui";
import { ApiError, errorDetail, reportShares, type SharedEvidence, type SharedMetric, type SharedReport } from "@/lib/api";
import { Skeleton, Wordmark } from "@/components/ui/primitives";
import { StatusGlyph } from "@/components/domain/status";
import { OUTCOME_LABEL, ReportBody, ReportToc, outcomeStatus } from "@/components/domain/report-view";
import { fmtDateTime, titleCase } from "@/lib/format";

const HOME = "https://bearcase.me";

const chip = "inline-flex h-[18px] items-center rounded-[var(--radius-1)] border border-hairline bg-bg-muted px-1 font-mono text-[10.5px] hover:border-accent data-[state=open]:border-accent data-[state=open]:bg-accent/10";
const card = "z-50 w-[min(88vw,340px)] rounded-[var(--radius-2)] border border-hairline bg-bg-raised p-3 text-sm shadow-[var(--shadow-2)]";

/** A citation chip that opens its source in place: the recipient has no account, so there is no document to open. */
function SharedCite({ kind, id, evidence, metric }: { kind: "E" | "M"; id: string; evidence?: SharedEvidence; metric?: SharedMetric }) {
  const label = `${kind}:${id.slice(0, 6)}`;
  return (
    <Popover.Root>
      <Popover.Trigger className={chip} aria-label={kind === "E" ? `Source ${label}` : `Calculation ${label}`}>{label}</Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className={card} sideOffset={6} collisionPadding={12}>
          {kind === "E" && (evidence ? (
            <>
              <p className="font-medium">{evidence.document_name}</p>
              {evidence.locator && <p className="text-xs text-fg-muted">{evidence.locator}</p>}
              <blockquote className="mt-2 border-l-2 border-hairline pl-2 text-fg-muted">{evidence.snippet}</blockquote>
              <p className="mt-2 text-xs text-fg-muted">A passage in a document the seller provided. It shows where the statement came from, not that it is correct.</p>
            </>
          ) : <p className="text-fg-muted">This source is no longer in the deal.</p>)}
          {kind === "M" && (metric ? (
            <>
              <p className="font-medium">{metric.label}{metric.period ? `, ${metric.period}` : ""}</p>
              <p className="text-xs text-fg-muted">Calculated by BearCase&apos;s engine from source figures, not by the model.</p>
              {metric.formula && <p className="mt-2 break-words font-mono text-[11px] text-fg-muted">{metric.formula}</p>}
            </>
          ) : <p className="text-fg-muted">This calculation is no longer in the deal.</p>)}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

function Frame({ children }: { children: React.ReactNode }) {
  return <div data-world="paper" className="min-h-svh bg-bg text-fg">{children}</div>;
}

function Unavailable({ detail }: { detail: string }) {
  return (
    <Frame>
      <main id="main" className="mx-auto grid min-h-svh max-w-md place-items-center p-6">
        <div>
          <a href={HOME} className="inline-block rounded-[var(--radius-1)]"><Wordmark size="lg" /></a>
          <h1 className="mt-6 text-3xl">This report is not available</h1>
          <p role="alert" className="mt-2 text-sm text-fg-muted">{detail}</p>
        </div>
      </main>
    </Frame>
  );
}

/** The report body and chrome for a shared link, given the API's reply. Split out so it renders in tests without a fetch. */
export function SharedReportBody({ data }: { data: SharedReport }) {
  const toc = useMemo(() => data.sections.map((s) => ({ key: s.key, title: s.title })), [data]);
  const cite = (kind: "E" | "M", id: string) => <SharedCite kind={kind} id={id} evidence={kind === "E" ? data.evidence[id] : undefined} metric={kind === "M" ? data.metrics[id] : undefined} />;
  const p = data.provenance;
  return (
    <Frame>
      <header className="border-b border-hairline">
        <div className="mx-auto max-w-6xl px-4 py-6 md:px-6">
          <p className="text-sm text-fg-muted">Shared from <a href={HOME} className="text-fg underline-offset-2 hover:underline">BearCase</a>, read only</p>
          <h1 className="mt-4 text-3xl md:text-4xl">{data.company_name}</h1>
          <p className="mt-1 text-sm text-fg-muted">Red-team review, version {data.version_no}, generated {fmtDateTime(data.generated_at)}</p>
          <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
            <span className="inline-flex items-center gap-2 rounded-[var(--radius-1)] border border-hairline px-3 py-1 font-medium"><StatusGlyph status={outcomeStatus(data.outcome)} />{OUTCOME_LABEL[data.outcome] ?? titleCase(data.outcome)}</span>
            <span className="inline-flex items-center gap-1.5"><StatusGlyph status={data.validation.valid ? "supported" : "contradicted"} size={12} /><span className="num">{data.validation.material_cited}/{data.validation.material_statements}</span> material statements cited</span>
          </div>
          <p className="mt-3 max-w-3xl text-xs text-fg-muted">An E chip names the document and passage a statement came from; an M chip names a calculation BearCase&apos;s engine made. Select a chip to read its source. A citation shows where a statement came from, not that the statement is correct.</p>
        </div>
      </header>
      <main id="main" className="mx-auto grid max-w-6xl gap-6 px-4 py-6 md:px-6 lg:grid-cols-[180px_minmax(0,1fr)]">
        <ReportToc sections={toc} />
        <article className="min-w-0 max-w-[76ch]">
          <ReportBody sections={data.sections} cite={cite} />
        </article>
      </main>
      <footer className="border-t border-hairline">
        <div className="mx-auto flex max-w-6xl flex-col gap-1.5 px-4 py-6 text-xs text-fg-muted md:px-6">
          {data.is_demo && <p className="text-sm text-fg">The company, its documents, and every figure in this report are fictional. It was generated from BearCase&apos;s demonstration deal.</p>}
          <p>BearCase does not provide financial, legal, tax, or investment advice.</p>
          <p>Generated by {p.provider}/{p.model}, prompt {p.prompt_version}, schema {p.schema_version}, engine {p.engine_version}.</p>
          <p>Made with BearCase, which checks a seller&apos;s documents for financial inconsistencies. <a href={HOME} className="text-fg underline underline-offset-2">bearcase.me</a></p>
        </div>
      </footer>
    </Frame>
  );
}

/** Fetches the shared report for a token and renders it; unknown, revoked, and expired links all read the same. */
export function SharedReportView({ token }: { token: string }) {
  const q = useQuery({ queryKey: ["shared-report", token], queryFn: () => reportShares.read(token), retry: false, staleTime: 60_000 });
  if (q.isPending) {
    return <Frame><div className="mx-auto max-w-6xl p-6" aria-busy="true"><Skeleton className="h-6 w-1/3" /><Skeleton className="mt-4 h-10 w-2/3" /><Skeleton className="mt-8 h-64" /></div></Frame>;
  }
  if (q.isError) {
    const gone = q.error instanceof ApiError && q.error.status === 404;
    const limited = q.error instanceof ApiError && q.error.status === 429;
    return <Unavailable detail={gone || limited ? errorDetail(q.error, "This link does not work.") : "The report could not be loaded. Check your connection and reload the page."} />;
  }
  return <SharedReportBody data={q.data} />;
}
