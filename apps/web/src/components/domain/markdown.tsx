"use client";

import { Fragment, useMemo, type ReactNode } from "react";
import { CitationChip } from "@/components/domain/citation";
import type { ViewerTarget } from "@/components/domain/document-viewer";
import { Table, td, th } from "@/components/ui/table";
import { fmtValue } from "@/lib/format";

export interface EvidenceCite { id: string; document_id: string; document_name: string; doc_type: string; locator: Record<string, unknown>; kind: string; text: string }
export interface MetricCite { id: string; key: string; label: string; value: string | null; unit: string; formula: string | null }
/** Both lists may be missing on the wire (a reply interrupted before its citations resolved persists as `{}`); readers default them to []. */
export interface CitationSources { evidence?: EvidenceCite[]; metrics?: MetricCite[] }

const MARKER = /[ \t]*\[(?:E|M):[0-9a-f-]{36}\]/g;
// Code is verbatim: a fenced block (to its closing fence, or the end of the text while streaming) or a backtick span.
const CODE_REGION = /(```[\s\S]*?(?:```|$)|`[^`\n]+`)/;

/** Message text without the [E:id]/[M:id] markers the service emits (for the clipboard). Code segments are copied as written. */
export function stripCitations(text: string): string {
  const parts = text.split(CODE_REGION);
  return parts
    .map((seg, i) => {
      if (i % 2 === 1) return seg;
      const cleaned = seg.replace(MARKER, "").replace(/[ \t]+(?=\n)/g, "");
      return i === parts.length - 1 ? cleaned.replace(/[ \t]+$/, "") : cleaned;
    })
    .join("");
}

// ---------- Inline syntax: citations, `code`, **strong**, __strong__, *em*, _em_, [text](https://...) ----------

type Inline =
  | { t: "text"; v: string }
  | { t: "code"; v: string }
  | { t: "strong"; c: Inline[] }
  | { t: "em"; c: Inline[] }
  | { t: "link"; href: string; c: Inline[] }
  | { t: "cite"; kind: "E" | "M"; id: string };

// Alternatives are tried in this order at each position; the leftmost match wins. Emphasis content may not
// cross its own delimiter, so "**a** b **c**" yields two strong runs rather than one.
const INLINE = /\[(E|M):([0-9a-f-]{36})\]|`([^`\n]+)`|\*\*(?=\S)((?:(?!\*\*)[^\n])*?\S)\*\*|__(?=\S)((?:(?!__)[^\n])*?\S)__|\*(?=[^\s*])([^*\n]*?[^\s*])\*|_(?=[^\s_])([^_\n]*?[^\s_])_|\[([^[\]\n]+)\]\(([^\s()]*(?:\([^\s()]*\)[^\s()]*)*)\)/g;
const WORD = /[A-Za-z0-9]/;
const SAFE_HREF = /^https?:\/\/\S+$/i;
const HOSTNAME = /^(?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d{1,5})?(?:[/?#]\S*)?$/i;

/** Host of an http(s) URL or of a bare hostname (optionally with port or path); null when the text is not URL-like. */
function hostOf(s: string): string | null {
  const t = s.trim();
  try {
    if (/^https?:\/\//i.test(t)) return new URL(t).host.toLowerCase();
    if (HOSTNAME.test(t)) return new URL(`https://${t}`).host.toLowerCase();
  } catch { /* not a parsable URL */ }
  return null;
}

function parseInline(src: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  for (const m of src.matchAll(INLINE)) {
    const start = m.index ?? 0;
    const end = start + m[0].length;
    if (start > last) out.push({ t: "text", v: src.slice(last, start) });
    if (m[1] === "E" || m[1] === "M") out.push({ t: "cite", kind: m[1], id: m[2] });
    else if (m[3] !== undefined) out.push({ t: "code", v: m[3] });
    else if (m[4] !== undefined) out.push({ t: "strong", c: parseInline(m[4]) });
    else if (m[5] !== undefined || m[7] !== undefined) {
      // Underscore emphasis only at word boundaries, so snake_case identifiers stay literal.
      const bounded = (start === 0 || !WORD.test(src[start - 1])) && (end === src.length || !WORD.test(src[end]));
      if (!bounded) out.push({ t: "text", v: m[0] });
      else if (m[5] !== undefined) out.push({ t: "strong", c: parseInline(m[5]) });
      else out.push({ t: "em", c: parseInline(m[7] ?? "") });
    } else if (m[6] !== undefined) out.push({ t: "em", c: parseInline(m[6]) });
    else if (SAFE_HREF.test(m[9])) {
      // A label that is itself a URL or hostname must agree with the target's host; otherwise the target is what is shown,
      // so a trusted-looking label cannot dress up an attacker-controlled link.
      const label = parseInline(m[8]);
      const labelHost = hostOf(plain(label));
      const spoofed = labelHost !== null && labelHost !== hostOf(m[9]);
      out.push({ t: "link", href: m[9], c: spoofed ? [{ t: "text", v: m[9] }] : label });
    } else out.push(...parseInline(m[8])); // non-http(s) targets render as their label text, never as a link
    last = end;
  }
  if (last < src.length) out.push({ t: "text", v: src.slice(last) });
  return out;
}

function plain(nodes: Inline[]): string {
  return nodes.map((n) => (n.t === "text" || n.t === "code" ? n.v : n.t === "cite" ? "" : plain(n.c))).join("");
}

// ---------- Block syntax: paragraphs, headings, lists (one nested level), fenced code, quotes, tables, rules ----------

type Align = "left" | "center" | "right" | null;
interface ListBlock { t: "list"; ordered: boolean; start: number; items: Item[] }
interface Item { c: Inline[]; sub?: ListBlock }
type Block =
  | { t: "p"; c: Inline[] }
  | { t: "h"; level: 1 | 2 | 3; c: Inline[] }
  | ListBlock
  | { t: "code"; lang: string; code: string }
  | { t: "quote"; blocks: Block[] }
  | { t: "table"; align: Align[]; head: Inline[][]; rows: Inline[][][] }
  | { t: "hr" };

const FENCE = /^ {0,3}(`{3,}|~{3,})[ \t]*(\S*)/;
const FENCE_CLOSE = /^ {0,3}(`{3,}|~{3,})[ \t]*$/;
const HEADING = /^ {0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$/;
const HR = /^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$/;
const QUOTE = /^ {0,3}> ?(.*)$/;
const ITEM = /^(\s*)(?:([-*+])|(\d{1,3})[.)])[ \t]+(.*)$/;
// Every whitespace run is separated from the next by a mandatory "|" or "-", and the line is trimmed before the test,
// so a non-matching line backtracks linearly rather than quadratically.
const SEP = /^\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?$/;
/** Nested quotes deeper than this render as a paragraph instead of recursing (model output can be arbitrarily deep). */
const MAX_QUOTE_DEPTH = 8;
/** A GFM separator line longer than this is not one; it also bounds the regex work per line. */
const MAX_SEP_LENGTH = 2000;

/** True for a GFM table header separator such as "|:---|---:|" or "--- | ---". */
export function isTableSeparator(line: string): boolean {
  return SEP.test(line.trim());
}

interface ItemInfo { indent: number; ordered: boolean; num: number; text: string }
function itemInfo(line: string): ItemInfo | null {
  const m = ITEM.exec(line);
  if (!m) return null;
  return { indent: m[1].replace(/\t/g, "  ").length, ordered: m[3] !== undefined, num: m[3] ? Number(m[3]) : 1, text: m[4] };
}

function splitRow(line: string): string[] {
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  return s.split("|").map((c) => c.trim());
}

function tableAt(lines: string[], i: number): { head: string[]; align: Align[] } | null {
  const line = lines[i];
  const next = lines[i + 1];
  if (!line.includes("|") || next === undefined || next.length > MAX_SEP_LENGTH || !next.includes("|") || !isTableSeparator(next)) return null;
  const head = splitRow(line);
  const seps = splitRow(next);
  if (head.length === 0 || head.length !== seps.length) return null;
  const align = seps.map<Align>((s) => (s.startsWith(":") && s.endsWith(":") ? "center" : s.endsWith(":") ? "right" : s.startsWith(":") ? "left" : null));
  return { head, align };
}

function startsBlock(lines: string[], i: number): boolean {
  const l = lines[i];
  return FENCE.test(l) || HEADING.test(l) || HR.test(l) || QUOTE.test(l) || ITEM.test(l) || tableAt(lines, i) !== null;
}

interface RawItem { text: string; sub?: { ordered: boolean; start: number; items: RawItem[] } }

function parseList(lines: string[], start: number): { block: ListBlock; next: number } {
  const head = itemInfo(lines[start]) ?? { indent: 0, ordered: false, num: 1, text: lines[start] };
  // Nesting is relative to the list's own indentation: two more columns than the head nests, fewer ends the list.
  const nestAt = head.indent + 2;
  const items: RawItem[] = [];
  let cur: RawItem | null = null;
  let i = start;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      // A blank line keeps the list only when the next non-blank line is another item of it (loose lists).
      let j = i + 1;
      while (j < lines.length && !lines[j].trim()) j++;
      const nxt = j < lines.length ? itemInfo(lines[j]) : null;
      if (nxt && nxt.indent >= head.indent && (nxt.indent >= nestAt || nxt.ordered === head.ordered)) { i = j; continue; }
      break;
    }
    const info = itemInfo(line);
    if (info) {
      if (info.indent < head.indent) break;
      if (info.indent >= nestAt && items.length) {
        const parent = items[items.length - 1];
        parent.sub ??= { ordered: info.ordered, start: info.num, items: [] };
        cur = { text: info.text };
        parent.sub.items.push(cur);
      } else {
        if (items.length && info.ordered !== head.ordered) break;
        cur = { text: info.text };
        items.push(cur);
      }
      i++;
      continue;
    }
    if (!cur || startsBlock(lines, i)) break;
    cur.text += ` ${line.trim()}`;
    i++;
  }
  const conv = (r: RawItem): Item => ({ c: parseInline(r.text), sub: r.sub ? { t: "list", ordered: r.sub.ordered, start: r.sub.start, items: r.sub.items.map(conv) } : undefined });
  return { block: { t: "list", ordered: head.ordered, start: head.num, items: items.map(conv) }, next: i };
}

/** Line-based, deterministic Markdown subset. Anything unrecognised is kept as paragraph text. */
export function parseBlocks(text: string, depth = 0): Block[] {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const out: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    const fence = FENCE.exec(line);
    if (fence) {
      const open = fence[1];
      const code: string[] = [];
      i++;
      while (i < lines.length) {
        const close = FENCE_CLOSE.exec(lines[i]);
        if (close && close[1][0] === open[0] && close[1].length >= open.length) { i++; break; }
        code.push(lines[i]);
        i++;
      }
      out.push({ t: "code", lang: fence[2], code: code.join("\n") });
      continue;
    }
    const h = HEADING.exec(line);
    if (h) { out.push({ t: "h", level: Math.min(3, h[1].length) as 1 | 2 | 3, c: parseInline(h[2]) }); i++; continue; }
    if (HR.test(line)) { out.push({ t: "hr" }); i++; continue; }
    if (QUOTE.test(line)) {
      const raw: string[] = [];
      const inner: string[] = [];
      let q: RegExpExecArray | null;
      while (i < lines.length && (q = QUOTE.exec(lines[i]))) { raw.push(lines[i].trim()); inner.push(q[1]); i++; }
      if (depth < MAX_QUOTE_DEPTH) out.push({ t: "quote", blocks: parseBlocks(inner.join("\n"), depth + 1) });
      else out.push({ t: "p", c: parseInline(raw.join(" ")) });
      continue;
    }
    const tbl = tableAt(lines, i);
    if (tbl) {
      const rows: Inline[][][] = [];
      i += 2;
      while (i < lines.length && lines[i].trim() && lines[i].includes("|")) {
        const cells = splitRow(lines[i]);
        rows.push(tbl.head.map((_, ci) => parseInline(cells[ci] ?? "")));
        i++;
      }
      out.push({ t: "table", align: tbl.align, head: tbl.head.map((c) => parseInline(c)), rows });
      continue;
    }
    if (ITEM.test(line)) {
      const list = parseList(lines, i);
      out.push(list.block);
      i = list.next;
      continue;
    }
    const para = [line.trim()];
    i++;
    while (i < lines.length && lines[i].trim() && !startsBlock(lines, i)) { para.push(lines[i].trim()); i++; }
    out.push({ t: "p", c: parseInline(para.join(" ")) });
  }
  return out;
}

// ---------- Rendering ----------

interface Ctx { evidence: Map<string, EvidenceCite>; metrics: Map<string, MetricCite>; onOpen: (t: ViewerTarget) => void }

function Cite({ kind, id, ctx }: { kind: "E" | "M"; id: string; ctx: Ctx }) {
  if (kind === "E") {
    const e = ctx.evidence.get(id);
    if (!e) return <span className="font-mono text-[10px] text-fg-muted">[source]</span>;
    return (
      <span className="mx-0.5 inline-flex align-middle">
        <CitationChip docType={e.doc_type} documentName={e.document_name} locator={e.locator} kind={e.kind} onClick={() => ctx.onOpen({ documentId: e.document_id, documentName: e.document_name, evidenceId: e.id, locator: e.locator })} />
      </span>
    );
  }
  const mm = ctx.metrics.get(id);
  return (
    <span className="mx-0.5 inline-flex h-[20px] items-center rounded-[var(--radius-1)] bg-bg-muted px-1.5 align-middle font-mono text-[11px] text-fg-muted" title={mm ? `${mm.label}: ${mm.formula ?? "calculated"}` : "calculation"}>
      {mm ? `${mm.label.split(" (")[0]} ${fmtValue(mm.value, mm.unit)}` : "calc"}
    </span>
  );
}

function renderInline(nodes: Inline[], ctx: Ctx): ReactNode[] {
  return nodes.map((n, i) => {
    switch (n.t) {
      case "text": return <Fragment key={i}>{n.v}</Fragment>;
      case "code": return <code key={i} className="rounded-[var(--radius-1)] bg-bg-muted px-1 py-px font-mono text-[0.85em]">{n.v}</code>;
      case "strong": return <strong key={i} className="font-semibold">{renderInline(n.c, ctx)}</strong>;
      case "em": return <em key={i}>{renderInline(n.c, ctx)}</em>;
      case "link": return <a key={i} href={n.href} title={n.href} target="_blank" rel="noreferrer" className="text-accent underline-offset-2 hover:underline">{renderInline(n.c, ctx)}</a>;
      case "cite": return <Cite key={i} kind={n.kind} id={n.id} ctx={ctx} />;
    }
  });
}

const HEADING_SIZE = ["text-[15px]", "text-[14px]", "text-[13px]"] as const;
const NUMERIC = /^[\s$€£(+\-−–]*\d[\d,.]*\s*(?:%|x|k|m|b|bps|pp|yr)?\)?\s*$/i;
const ALIGN: Record<Exclude<Align, null>, string> = { left: "text-left", center: "text-center", right: "text-right" };

function ListView({ list, ctx, nested = false }: { list: ListBlock; ctx: Ctx; nested?: boolean }) {
  const spacing = nested ? "mt-1" : "mb-3 last:mb-0";
  const items = list.items.map((it, i) => (
    <li key={i} className="my-1 pl-0.5">
      {renderInline(it.c, ctx)}
      {it.sub && <ListView list={it.sub} ctx={ctx} nested />}
    </li>
  ));
  if (list.ordered) return <ol start={list.start !== 1 ? list.start : undefined} className={`${spacing} list-decimal pl-5`}>{items}</ol>;
  return <ul className={`${spacing} ${nested ? "list-[circle]" : "list-disc"} pl-5`}>{items}</ul>;
}

function BlockView({ b, ctx }: { b: Block; ctx: Ctx }) {
  switch (b.t) {
    case "p":
      return <p className="mb-3 last:mb-0">{renderInline(b.c, ctx)}</p>;
    case "h": {
      const cls = `mb-1.5 mt-4 font-semibold leading-snug first:mt-0 ${HEADING_SIZE[b.level - 1]}`;
      const kids = renderInline(b.c, ctx);
      if (b.level === 1) return <h3 className={cls}>{kids}</h3>;
      if (b.level === 2) return <h4 className={cls}>{kids}</h4>;
      return <h5 className={cls}>{kids}</h5>;
    }
    case "list":
      return <ListView list={b} ctx={ctx} />;
    case "code":
      return (
        <pre className="mb-3 overflow-x-auto rounded-[var(--radius-2)] border border-hairline bg-bg-muted px-3 py-2 font-mono text-[12px] leading-relaxed last:mb-0">
          <code data-lang={b.lang || undefined}>{b.code}</code>
        </pre>
      );
    case "quote":
      return <blockquote className="mb-3 border-l-2 border-hairline pl-3 text-fg-muted last:mb-0">{b.blocks.map((x, i) => <BlockView key={i} b={x} ctx={ctx} />)}</blockquote>;
    case "table":
      return (
        <Table className="mb-3 last:mb-0">
          <thead>
            <tr>{b.head.map((c, i) => <th key={i} scope="col" className={`${th} ${b.align[i] ? ALIGN[b.align[i]] : ""}`}>{renderInline(c, ctx)}</th>)}</tr>
          </thead>
          <tbody>
            {b.rows.map((r, ri) => (
              <tr key={ri}>
                {r.map((c, ci) => {
                  const numeric = NUMERIC.test(plain(c));
                  const align = b.align[ci] ? ALIGN[b.align[ci]] : numeric ? "text-right" : "";
                  return <td key={ci} className={`${td} ${numeric ? "num" : ""} ${align}`}>{renderInline(c, ctx)}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </Table>
      );
    case "hr":
      return <hr className="my-3 border-hairline" />;
  }
}

/**
 * Assistant text as React: a small Markdown subset (paragraphs, headings, lists, fenced code, quotes, GFM tables,
 * rules; bold, italic, code, http(s) links) plus [E:id]/[M:id] citation markers rendered as chips. No HTML injection:
 * everything is built as elements and React escapes the text.
 */
export function Markdown({ text, citations, onOpen }: { text: string; citations: CitationSources; onOpen: (t: ViewerTarget) => void }) {
  const blocks = useMemo(() => parseBlocks(text), [text]);
  const ctx = useMemo<Ctx>(() => ({ evidence: new Map((citations.evidence ?? []).map((e) => [e.id, e])), metrics: new Map((citations.metrics ?? []).map((m) => [m.id, m])), onOpen }), [citations, onOpen]);
  return <>{blocks.map((b, i) => <BlockView key={i} b={b} ctx={ctx} />)}</>;
}
