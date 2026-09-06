import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import { Markdown, isTableSeparator, parseBlocks, stripCitations, type CitationSources } from "./markdown";

const E1 = "11111111-1111-4111-8111-111111111111";
const M1 = "22222222-2222-4222-8222-222222222222";
const CITES: CitationSources = {
  evidence: [{ id: E1, document_id: "doc-1", document_name: "northstar-cim.pdf", doc_type: "cim", locator: { page: 3 }, kind: "page", text: "Revenue grew 18%." }],
  metrics: [{ id: M1, key: "dscr", label: "DSCR (x)", value: "1.33", unit: "multiple", formula: "cfads / debt_service" }],
};
const noop = () => {};
afterEach(cleanup);
const md = (text: string, onOpen = noop) => render(<div><Markdown text={text} citations={CITES} onOpen={onOpen} /></div>);

describe("Markdown blocks", () => {
  it("renders plain paragraphs split on blank lines and joins soft line breaks", () => {
    const { container } = md("First line\ncontinues here.\n\nSecond paragraph.");
    const ps = container.querySelectorAll("p");
    expect(ps).toHaveLength(2);
    expect(ps[0]).toHaveTextContent("First line continues here.");
    expect(ps[1]).toHaveTextContent("Second paragraph.");
    expect(container.querySelector("ul, ol, table, pre, h3")).toBeNull();
  });

  it("renders a bullet list with a citation chip inside an item and opens the source on click", () => {
    const onOpen = vi.fn();
    const { container, getByRole } = md(`- Revenue grew 18% [E:${E1}]\n* Margins held\n- Third`, onOpen);
    const items = container.querySelectorAll("ul > li");
    expect(items).toHaveLength(3);
    const chip = getByRole("button", { name: /CIM p\.3/ });
    expect(items[0].contains(chip)).toBe(true);
    expect(items[0].textContent).not.toContain("[E:");
    fireEvent.click(chip);
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ documentId: "doc-1", evidenceId: E1, locator: { page: 3 } }));
  });

  it("renders ordered lists with their start number and one nested level by two-space indent", () => {
    const { container } = md("3. Third\n4. Fourth\n  - nested a\n  - nested b\n5. Fifth");
    const ol = container.querySelector("ol");
    expect(ol).not.toBeNull();
    expect(ol).toHaveAttribute("start", "3");
    expect(ol?.querySelectorAll(":scope > li")).toHaveLength(3);
    const nested = ol?.querySelectorAll(":scope > li")[1].querySelector("ul");
    expect(nested?.querySelectorAll("li")).toHaveLength(2);
    expect(nested?.querySelectorAll("li")[0]).toHaveTextContent("nested a");
  });

  it("renders bold, italic, and inline code", () => {
    const { container } = md("Use **DSCR** and `cfads / debt_service` with *care*, __also bold__ and _also em_.");
    const strongs = Array.from(container.querySelectorAll("strong")).map((s) => s.textContent);
    expect(strongs).toEqual(["DSCR", "also bold"]);
    const code = container.querySelector("code");
    expect(code).toHaveTextContent("cfads / debt_service");
    expect(code?.className).toContain("font-mono");
    const ems = Array.from(container.querySelectorAll("em")).map((e) => e.textContent);
    expect(ems).toEqual(["care", "also em"]);
  });

  it("renders a fenced code block in a mono pre with a hairline border and keeps the language", () => {
    const { container } = md("Before\n\n```python\nprint(**kwargs)\n# not a heading\n```\n\nAfter");
    const pre = container.querySelector("pre");
    expect(pre).not.toBeNull();
    expect(pre?.className).toContain("font-mono");
    expect(pre?.className).toContain("text-[12px]");
    expect(pre?.className).toContain("border-hairline");
    expect(pre?.querySelector("code")).toHaveAttribute("data-lang", "python");
    expect(pre?.textContent).toBe("print(**kwargs)\n# not a heading");
    expect(container.querySelectorAll("strong, h3, h4, h5")).toHaveLength(0);
    expect(container.querySelectorAll("p")).toHaveLength(2);
  });

  it("renders an unterminated fence (mid-stream) as code rather than text", () => {
    const { container } = md("```\nlet x = 1");
    expect(container.querySelector("pre")).toHaveTextContent("let x = 1");
  });

  it("renders GFM tables with the app table styling, alignment, and numeric cells in mono", () => {
    const { container } = md("| Metric | Value | Note |\n|:---|---:|---|\n| DSCR | 1.33x | fine |\n| Revenue | $12.9M |");
    const table = container.querySelector("table");
    expect(table).not.toBeNull();
    expect(table?.parentElement?.className).toContain("scroll-x");
    expect(table?.parentElement?.className).toContain("border-hairline");
    const ths = table?.querySelectorAll("th") ?? [];
    expect(Array.from(ths).map((t) => t.textContent)).toEqual(["Metric", "Value", "Note"]);
    expect(ths[0]).toHaveAttribute("scope", "col");
    expect(ths[1].className).toContain("text-right");
    const rows = table?.querySelectorAll("tbody tr") ?? [];
    expect(rows).toHaveLength(2);
    const cells = rows[0].querySelectorAll("td");
    expect(cells[1]).toHaveTextContent("1.33x");
    expect(cells[1].className).toContain("num");
    expect(cells[1].className).toContain("text-right");
    expect(cells[0].className).not.toContain("num");
    expect(rows[1].querySelectorAll("td")).toHaveLength(3);
  });

  it("sizes headings 15/14/13px semibold and clamps deeper levels to the smallest", () => {
    const { container } = md("# One\n## Two\n### Three\n#### Four\nBody");
    const h3 = container.querySelector("h3");
    const h4 = container.querySelector("h4");
    const h5s = container.querySelectorAll("h5");
    expect(h3).toHaveTextContent("One");
    expect(h3?.className).toContain("text-[15px]");
    expect(h3?.className).toContain("font-semibold");
    expect(h4?.className).toContain("text-[14px]");
    expect(h5s).toHaveLength(2);
    expect(h5s[0].className).toContain("text-[13px]");
    expect(container.querySelector("h1, h2")).toBeNull();
    expect(container.querySelector("p")).toHaveTextContent("Body");
  });

  it("renders javascript: and relative links as plain text and https links as new-tab anchors", () => {
    const { container, queryByRole, getByText } = md("[click](javascript:alert(1)) and [lab](/app/x) then [docs](https://example.com/a?b=1).");
    expect(queryByRole("link", { name: "click" })).toBeNull();
    expect(queryByRole("link", { name: "lab" })).toBeNull();
    expect(getByText(/click and lab then/)).toBeInTheDocument();
    expect(container.textContent).not.toContain("javascript:");
    const a = container.querySelector("a");
    expect(a).toHaveTextContent("docs");
    expect(a).toHaveAttribute("href", "https://example.com/a?b=1");
    expect(a).toHaveAttribute("title", "https://example.com/a?b=1");
    expect(a).toHaveAttribute("target", "_blank");
    expect(a).toHaveAttribute("rel", "noreferrer");
  });

  it("shows the real target when a URL-looking label points at a different host", () => {
    const { container } = md("See [https://a.example](https://b.example) and [www.a.example/x](https://b.example/y) but [a.example/p](https://a.example/q) and [docs](https://b.example).");
    const links = Array.from(container.querySelectorAll("a"));
    expect(links.map((a) => a.textContent)).toEqual(["https://b.example", "https://b.example/y", "a.example/p", "docs"]);
    expect(links[0]).toHaveAttribute("href", "https://b.example");
    expect(links[0]).toHaveAttribute("title", "https://b.example");
    expect(container.textContent).not.toContain("a.example](");
  });

  it("renders three sibling items for an indented list, not one item with two children", () => {
    const { container } = md("  - a\n  - b\n  - c");
    const ul = container.querySelector("ul");
    expect(ul?.querySelectorAll(":scope > li")).toHaveLength(3);
    expect(container.querySelectorAll("ul")).toHaveLength(1);
    expect(Array.from(container.querySelectorAll("li")).map((l) => l.textContent)).toEqual(["a", "b", "c"]);
  });

  it("nests relative to the list head and ends the list on a dedented item", () => {
    const { container } = md("1. First\n\n   Explanation.\n\n   - sub a\n   - sub b\n   - sub c\n\n- top");
    const uls = container.querySelectorAll("ul");
    expect(uls).toHaveLength(2);
    expect(uls[0].querySelectorAll(":scope > li")).toHaveLength(3);
    expect(uls[0].querySelector("ul")).toBeNull();
    expect(uls[1]).toHaveTextContent("top");
  });

  it("caps blockquote nesting at eight levels and renders deeper text as a paragraph", () => {
    const { container } = md(">".repeat(12) + " deep");
    expect(container.querySelectorAll("blockquote")).toHaveLength(8);
    const p = container.querySelector("blockquote p");
    expect(p).toHaveTextContent(">>>> deep");
  });

  it("renders a message with no citation lists at all without throwing", () => {
    const { container } = render(<div><Markdown text={`Grew 18% [E:${E1}] and [M:${M1}]`} citations={{}} onOpen={noop} /></div>);
    expect(container).toHaveTextContent("[source]");
    expect(container).toHaveTextContent("calc");
  });

  it("keeps snake_case identifiers literal and renders quotes and rules", () => {
    const { container } = md("Use debt_service_coverage here.\n\n> quoted **line**\n\n---\n\nEnd");
    expect(container.querySelector("em")).toBeNull();
    expect(container.querySelector("p")).toHaveTextContent("Use debt_service_coverage here.");
    const quote = container.querySelector("blockquote");
    expect(quote).toHaveTextContent("quoted line");
    expect(quote?.querySelector("strong")).toHaveTextContent("line");
    expect(container.querySelector("hr")).not.toBeNull();
  });

  it("renders metric markers as calculation chips and unknown evidence ids as [source]", () => {
    const { container } = md(`DSCR is [M:${M1}] and this [E:33333333-3333-4333-8333-333333333333] is unknown.`);
    expect(container).toHaveTextContent("DSCR 1.33x");
    expect(container.querySelector('[title="DSCR (x): cfads / debt_service"]')).not.toBeNull();
    expect(container).toHaveTextContent("[source]");
    expect(container.textContent).not.toContain("[E:");
  });

  it("never injects raw HTML", () => {
    const { container } = md("<img src=x onerror=alert(1)> **safe**");
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});

describe("parseBlocks", () => {
  it("lets a list interrupt a paragraph and keeps loose lists together", () => {
    const blocks = parseBlocks("Risks:\n- one\n\n- two\n\nNext.");
    expect(blocks.map((b) => b.t)).toEqual(["p", "list", "p"]);
    const list = blocks[1];
    expect(list.t === "list" && list.items).toHaveLength(2);
  });
  it("does not treat a year-prefixed sentence as an ordered list", () => {
    expect(parseBlocks("2024. Revenue grew.").map((b) => b.t)).toEqual(["p"]);
  });
  it("parses a 5000-deep nested blockquote without throwing", () => {
    let blocks: ReturnType<typeof parseBlocks> = [];
    expect(() => { blocks = parseBlocks(">".repeat(5000) + " x"); }).not.toThrow();
    let depth = 0;
    let b = blocks[0];
    while (b && b.t === "quote") { depth++; b = b.blocks[0]; }
    expect(depth).toBe(8);
    expect(b?.t).toBe("p");
  });
  it("tests a table separator on a 100k-space line in linear time", () => {
    const leading = " ".repeat(100_000) + "|---|x";
    const inner = "|" + " ".repeat(100_000) + "|---|x";
    const t0 = performance.now();
    expect(isTableSeparator(leading)).toBe(false);
    expect(isTableSeparator(inner)).toBe(false);
    expect(isTableSeparator("\t".repeat(100_000) + "|")).toBe(false);
    parseBlocks(`a | b\n${leading}\nc | d\n${inner}`);
    expect(performance.now() - t0).toBeLessThan(50);
    for (const ok of ["|:---|---:|---|", "---|---", "| --- | :---: | --: |", ":--|--:", "|:-|", "| - |", "  |---|  "]) expect(isTableSeparator(ok)).toBe(true);
    for (const bad of ["|a|b|", "| -- x |", "|", "", "---"]) expect(isTableSeparator(bad)).toBe(bad === "---");
  });
});

describe("stripCitations", () => {
  it("removes markers and the whitespace before them", () => {
    expect(stripCitations(`Revenue grew 18% [E:${E1}].\nDSCR was fine [M:${M1}] and held.`)).toBe("Revenue grew 18%.\nDSCR was fine and held.");
    expect(stripCitations(`Trailing [E:${E1}] \nnext`)).toBe("Trailing\nnext");
  });
  it("leaves markers inside backtick spans and fenced blocks untouched", () => {
    const span = `Use \`cfads / debt_service [M:${M1}]\` for 1.33x [M:${M1}].`;
    expect(stripCitations(span)).toBe(`Use \`cfads / debt_service [M:${M1}]\` for 1.33x.`);
    const fence = `Text [E:${E1}].\n\n\`\`\`\nx = 1  [E:${E1}]  \n\`\`\`\nAfter [E:${E1}].`;
    expect(stripCitations(fence)).toBe(`Text.\n\n\`\`\`\nx = 1  [E:${E1}]  \n\`\`\`\nAfter.`);
    expect(stripCitations(`\`\`\`\nopen [M:${M1}]`)).toBe(`\`\`\`\nopen [M:${M1}]`);
  });
});
