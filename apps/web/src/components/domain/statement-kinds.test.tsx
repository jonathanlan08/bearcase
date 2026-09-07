import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, within } from "@testing-library/react";
import { STATEMENT_KINDS, StatementKindMark, StatementKindsLegend } from "./statement-kinds";

afterEach(cleanup);

describe("statement kinds legend", () => {
  it("lists the four kinds in order with a mark and a label beside each (never a mark alone)", () => {
    expect(STATEMENT_KINDS.map((k) => k.label)).toEqual(["Source fact", "Calculation", "Assumption", "AI interpretation"]);
    expect(STATEMENT_KINDS.map((k) => k.mark)).toEqual(["E", "M", "A", "AI"]);
    const { getByRole } = render(<StatementKindsLegend />);
    const list = getByRole("list", { name: "What the labels mean" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(4);
    for (const [i, row] of rows.entries()) {
      const mark = row.querySelector("[data-kind]");
      expect(mark).toHaveTextContent(STATEMENT_KINDS[i].mark);
      expect(mark).toHaveAttribute("aria-hidden", "true");
      expect(row).toHaveTextContent(STATEMENT_KINDS[i].label);
      expect(row).toHaveTextContent(STATEMENT_KINDS[i].short);
    }
  });

  it("uses the citation-chip shape for source facts and calculations and a dashed shape for the uncited kinds", () => {
    const { container } = render(<><StatementKindMark kind="source" /><StatementKindMark kind="calculation" /><StatementKindMark kind="assumption" /><StatementKindMark kind="interpretation" /></>);
    const marks = Array.from(container.querySelectorAll("[data-kind]"));
    expect(marks.map((m) => m.textContent)).toEqual(["E", "M", "A", "AI"]);
    expect(marks[0].className).not.toContain("border-dashed");
    expect(marks[1].className).not.toContain("border-dashed");
    expect(marks[2].className).toContain("border-dashed");
    expect(marks[3].className).toContain("border-dashed");
    for (const m of marks) expect(m.className).toContain("font-mono");
  });

  it("explains the limits in the full variant: a source fact can be wrong, a citation is not correctness", () => {
    const { container, getAllByRole } = render(<StatementKindsLegend variant="full" />);
    const dl = container.querySelector("dl");
    expect(dl).toHaveAttribute("aria-label", "What the labels mean");
    expect(getAllByRole("term")).toHaveLength(4);
    const defs = getAllByRole("definition").map((d) => d.textContent ?? "");
    expect(defs[0]).toMatch(/where to look, not that the seller is right/);
    expect(defs[1]).toMatch(/The model never produces one/);
    expect(defs[2]).toMatch(/carry no citation/);
    expect(defs[3]).toMatch(/not that the sentence around it is right/);
  });
});
