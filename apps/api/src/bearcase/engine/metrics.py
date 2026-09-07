"""Derive period metrics from mapped statement line items and deal-level verified metrics.

Input: {period_label: {line_key: Decimal | None}} ordered by period. Output: list of Calc with
period attribution, ready to persist as FinancialMetric rows (source=calculated).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bearcase.engine import formulas as f
from bearcase.engine.money import Calc

# Canonical line keys the statement mapper produces.
LINE_KEYS = [
    "revenue",
    "cost_of_goods_sold",
    "gross_profit",
    "opex_owner_compensation",
    "opex_salaries_wages",
    "opex_temporary_labor",
    "opex_marketing",
    "opex_legal_professional",
    "opex_insurance",
    "opex_rent_occupancy",
    "opex_vehicle_fuel",
    "opex_software_it",
    "opex_other_ga",
    "operating_expenses",
    "ebitda",
    "depreciation",
    "amortization",
    "operating_income",
    "interest_expense",
    "income_before_tax",
    "income_tax_expense",
    "net_income",
]

LABOR_LINE_KEYS = ["opex_owner_compensation", "opex_salaries_wages", "opex_temporary_labor"]


@dataclass(frozen=True)
class PeriodCalc:
    period_label: str | None
    calc: Calc


def period_metrics(periods: dict[str, dict[str, Decimal | None]]) -> list[PeriodCalc]:
    """Compute per-period and cross-period metrics. Periods must be ordered oldest → newest."""
    out: list[PeriodCalc] = []
    labels = list(periods.keys())
    for i, label in enumerate(labels):
        li = periods[label]
        rev = li.get("revenue")
        out.append(PeriodCalc(label, f.gross_margin(rev, li.get("cost_of_goods_sold"))))
        out.append(PeriodCalc(label, f.operating_margin(li.get("operating_income"), rev)))
        recon = f.reported_ebitda(
            li.get("net_income"),
            li.get("interest_expense"),
            li.get("income_tax_expense"),
            li.get("depreciation"),
            li.get("amortization"),
        )
        stated = li.get("ebitda")
        if recon.value is not None and stated is not None and abs(recon.value - stated) > Decimal("1"):
            recon = Calc(
                recon.key,
                recon.value,
                recon.unit,
                recon.formula,
                recon.inputs,
                recon.missing,
                (
                    *recon.notes,
                    f"stated EBITDA line ({stated}) does not equal the reconciliation ({recon.value}); review required",
                ),
            )
        out.append(PeriodCalc(label, recon))
        if i > 0:
            prior = periods[labels[i - 1]].get("revenue")
            out.append(PeriodCalc(label, f.revenue_growth(rev, prior)))
    if len(labels) >= 2:
        first, last = periods[labels[0]].get("revenue"), periods[labels[-1]].get("revenue")
        out.append(PeriodCalc(labels[-1], f.cagr(first, last, len(labels) - 1)))
    return out


def ebitda_margin(ebitda: Decimal | None, revenue: Decimal | None) -> Calc:
    c = f.operating_margin(ebitda, revenue)
    return Calc("ebitda_margin", c.value, c.unit, "EBITDA / revenue", {"ebitda": ebitda, "revenue": revenue}, c.missing, c.notes)


# ---------- reader-facing number formatting -------------------------------------------------
# One formatter for every number that reaches a reader (finding text, report prose, table cells).
# Decimal repr such as "3.00000000" or "0E-8" must never appear in prose; callers pass the unit
# and get a string with separators, one decimal for percentages, two for multiples, none for money.

Number = Decimal | int | float | str


def _dec(v: Number) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def format_money(v: Number | None) -> str:
    """$1,810,000 (no decimals, thousands separators, sign before the symbol)."""
    if v is None:
        return "n/a"
    d = _dec(v)
    body = f"${abs(d):,.0f}"
    return f"-{body}" if d < 0 and body != "$0" else body


def format_pct(v: Number | None) -> str:
    """11.6% (one decimal)."""
    return "n/a" if v is None else f"{_dec(v):.1f}%"


def format_multiple(v: Number | None) -> str:
    """1.34x (two decimals)."""
    return "n/a" if v is None else f"{_dec(v):.2f}x"


def format_plain(v: Number | None) -> str:
    """Integers with separators; otherwise up to two decimals with trailing zeros trimmed."""
    if v is None:
        return "n/a"
    d = _dec(v)
    if d == d.to_integral_value():
        return f"{int(d):,}"
    return f"{d:,.2f}".rstrip("0").rstrip(".")


def format_value(v: Number | None, unit: str | None) -> str:
    """Format by unit: usd, pct, multiple, years, months, count, text."""
    if v is None:
        return "n/a"
    u = (unit or "").lower()
    if u == "usd":
        return format_money(v)
    if u == "pct":
        return format_pct(v)
    if u == "multiple":
        return format_multiple(v)
    if u in ("years", "months"):
        n = format_plain(v)
        singular = u[:-1]
        return f"{n} {singular if n == '1' else u}"
    return format_plain(v)
