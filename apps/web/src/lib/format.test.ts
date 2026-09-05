import { describe, expect, it } from "vitest";
import { fmtLocator, fmtMoney, fmtPct, fmtValue, fmtX, toNumber } from "./format";

describe("format", () => {
  it("formats money with explicit units", () => {
    expect(fmtMoney("12950000")).toBe("$12,950,000");
    expect(fmtMoney("12950000", { compact: true })).toBe("$12.95M");
    expect(fmtMoney("-65000", { compact: true })).toBe("-$65K");
    expect(fmtMoney(105000, { signed: true })).toBe("+$105,000");
    expect(fmtMoney(null)).toBe("n/a");
  });
  it("formats percentages and multiples", () => {
    expect(fmtPct("11.58818520")).toBe("11.6%");
    expect(fmtX("1.34173445")).toBe("1.34x");
    expect(fmtValue("10", "years")).toBe("10 yr");
    expect(fmtValue(null, "usd")).toBe("n/a");
  });
  it("never coerces garbage to a number", () => {
    expect(toNumber("abc")).toBeNull();
    expect(toNumber("")).toBeNull();
  });
  it("renders locators for pages, sheets, rows, and aggregates", () => {
    expect(fmtLocator({ page: 3, paragraph: 2 })).toBe("p.3 ¶2");
    expect(fmtLocator({ sheet: "Income Statement", row: 4 })).toBe("Income Statement!4");
    expect(fmtLocator({ row: 14 })).toBe("row 14");
    expect(fmtLocator({ aggregate: "customer_totals" })).toBe("aggregate (customer totals)");
  });
});
