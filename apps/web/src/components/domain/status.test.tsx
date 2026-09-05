import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { StatusChip, StatusGlyph, ConfidenceMeter, STATUS_LABEL } from "./status";

describe("status", () => {
  it("renders a text label for every claim status (never color alone)", () => {
    for (const s of ["supported", "contradicted", "unsupported", "review_required"]) {
      const { getByText } = render(<StatusChip status={s} />);
      expect(getByText(STATUS_LABEL[s])).toBeInTheDocument();
    }
  });
  it("uses distinct shapes per status", () => {
    const { container: a } = render(<StatusGlyph status="supported" />);
    const { container: b } = render(<StatusGlyph status="contradicted" />);
    const { container: c } = render(<StatusGlyph status="unsupported" />);
    const { container: d } = render(<StatusGlyph status="review_required" />);
    expect(a.querySelector("circle")).not.toBeNull();
    expect(b.querySelector("path")?.getAttribute("d")).toContain("M8 1l7 7");
    expect(c.querySelector("circle")?.getAttribute("stroke-dasharray")).toBeTruthy();
    expect(d.querySelector("rect")).not.toBeNull();
  });
  it("exposes confidence to assistive tech", () => {
    const { getByLabelText } = render(<ConfidenceMeter value="0.88" />);
    expect(getByLabelText("Confidence 88%")).toBeInTheDocument();
  });
});
