"""Scenario projection. Five-year equity model driven entirely by named, persisted inputs.

Every output carries the input snapshot that produced it. The AI layer may explain these
outputs but never produces them.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from bearcase import ENGINE_VERSION
from bearcase.engine import formulas as f
from bearcase.engine.money import D, quantize_money, quantize_ratio

ZERO = Decimal(0)
ONE = Decimal(1)
HUNDRED = Decimal(100)

ASSUMPTION_SPECS: list[dict[str, Any]] = [
    {"key": "revenue_growth_pct", "label": "Revenue growth (annual)", "unit": "pct", "min": -30, "max": 30, "step": 0.5},
    {"key": "largest_customer_loss_pct", "label": "Loss of largest customer", "unit": "pct", "min": 0, "max": 100, "step": 5},
    {"key": "gross_margin_change_bps", "label": "Gross-margin change", "unit": "count", "min": -600, "max": 300, "step": 25},
    {"key": "labor_cost_growth_pct", "label": "Labor-cost growth (annual)", "unit": "pct", "min": 0, "max": 15, "step": 0.5},
    {"key": "other_opex_growth_pct", "label": "Other opex growth (annual)", "unit": "pct", "min": 0, "max": 10, "step": 0.5},
    {"key": "interest_rate_pct", "label": "Interest rate", "unit": "pct", "min": 3, "max": 15, "step": 0.25},
    {
        "key": "purchase_price",
        "label": "Purchase price (enterprise value)",
        "unit": "usd",
        "min": 5_000_000,
        "max": 20_000_000,
        "step": 100_000,
    },
    {"key": "debt_pct", "label": "Debt share of purchase price", "unit": "pct", "min": 0, "max": 80, "step": 5},
    {
        "key": "accepted_addbacks",
        "label": "Accepted add-backs (annual)",
        "unit": "usd",
        "min": 0,
        "max": 1_000_000,
        "step": 5_000,
    },
    {"key": "cash_tax_rate_pct", "label": "Cash tax rate", "unit": "pct", "min": 0, "max": 40, "step": 1},
    {"key": "maintenance_capex", "label": "Maintenance capex (annual)", "unit": "usd", "min": 0, "max": 1_000_000, "step": 5_000},
    {
        "key": "nwc_pct_of_revenue_change",
        "label": "Working capital as % of revenue change",
        "unit": "pct",
        "min": 0,
        "max": 25,
        "step": 1,
    },
]


@dataclass(frozen=True)
class ScenarioInputs:
    """Deal facts (from verified metrics) + scenario assumptions."""

    # Deal facts
    base_revenue: Decimal
    largest_customer_revenue: Decimal
    gross_margin_pct: Decimal
    labor_opex: Decimal
    other_opex: Decimal
    depreciation_amortization: Decimal
    amortization_years: int
    payments_per_year: int
    covenant_dscr_threshold: Decimal | None
    exit_multiple: Decimal
    hold_years: int
    # Assumptions
    revenue_growth_pct: Decimal
    largest_customer_loss_pct: Decimal
    gross_margin_change_bps: Decimal
    labor_cost_growth_pct: Decimal
    other_opex_growth_pct: Decimal
    interest_rate_pct: Decimal
    purchase_price: Decimal
    debt_pct: Decimal
    accepted_addbacks: Decimal
    cash_tax_rate_pct: Decimal
    maintenance_capex: Decimal
    nwc_pct_of_revenue_change: Decimal

    def snapshot(self) -> dict[str, Any]:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in asdict(self).items()}

    def hash(self) -> str:
        return hashlib.sha256(json.dumps(self.snapshot(), sort_keys=True).encode()).hexdigest()


@dataclass
class YearProjection:
    year: int
    revenue: Decimal
    gross_profit: Decimal
    labor_opex: Decimal
    other_opex: Decimal
    addbacks: Decimal
    ebitda: Decimal
    depreciation_amortization: Decimal
    interest: Decimal
    principal: Decimal
    taxable_income: Decimal
    cash_taxes: Decimal
    working_capital_investment: Decimal
    cfads: Decimal
    debt_service: Decimal
    dscr: Decimal | None
    fcfe: Decimal
    closing_debt: Decimal


@dataclass
class ScenarioOutputs:
    engine_version: str
    years: list[YearProjection]
    enterprise_value: Decimal
    funded_debt: Decimal
    equity: Decimal
    annual_debt_service: Decimal
    year1: dict[str, Any]
    cfads_bridge: dict[str, Any]
    dscr: Decimal | None
    cash_on_cash_pct: Decimal | None
    irr_pct: Decimal | None
    irr_cashflows: list[str]
    exit: dict[str, Any]
    break_even_revenue: Decimal | None
    warnings: list[dict[str, Any]] = field(default_factory=list)
    calcs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        def conv(v: Any) -> Any:
            if isinstance(v, Decimal):
                return str(v)
            if isinstance(v, list):
                return [conv(x) for x in v]
            if isinstance(v, dict):
                return {k: conv(x) for k, x in v.items()}
            if hasattr(v, "__dataclass_fields__"):
                return conv(asdict(v))
            return v

        return conv(asdict(self))


def project(inp: ScenarioInputs) -> ScenarioOutputs:
    warnings: list[dict[str, Any]] = []
    calcs: dict[str, Any] = {}

    funded_debt = quantize_money(inp.purchase_price * inp.debt_pct / HUNDRED) or ZERO
    equity = quantize_money(inp.purchase_price - funded_debt) or ZERO
    ads_calc = f.annual_debt_service(funded_debt, inp.interest_rate_pct, inp.amortization_years, inp.payments_per_year)
    calcs["annual_debt_service"] = ads_calc.as_snapshot()
    ads = ads_calc.value or ZERO
    schedule = (
        f.amortization_schedule(funded_debt, inp.interest_rate_pct, inp.amortization_years, inp.payments_per_year)
        if funded_debt > 0
        else []
    )

    gm = (inp.gross_margin_pct + inp.gross_margin_change_bps / HUNDRED) / HUNDRED
    growth = ONE + inp.revenue_growth_pct / HUNDRED
    labor_growth = ONE + inp.labor_cost_growth_pct / HUNDRED
    other_growth = ONE + inp.other_opex_growth_pct / HUNDRED
    tax_rate = inp.cash_tax_rate_pct / HUNDRED
    nwc_rate = inp.nwc_pct_of_revenue_change / HUNDRED

    prev_revenue = inp.base_revenue
    retained_base = inp.base_revenue - inp.largest_customer_revenue * inp.largest_customer_loss_pct / HUNDRED
    years: list[YearProjection] = []
    for t in range(1, inp.hold_years + 1):
        revenue = retained_base * growth**t
        gross_profit = revenue * gm
        labor = inp.labor_opex * labor_growth**t
        other = inp.other_opex * other_growth**t
        addbacks = inp.accepted_addbacks
        ebitda = gross_profit - labor - other + addbacks
        sched = schedule[t - 1] if t - 1 < len(schedule) else None
        interest = sched.interest if sched else ZERO
        principal = sched.principal if sched else ZERO
        closing_debt = sched.closing_balance if sched else ZERO
        taxable = ebitda - inp.depreciation_amortization - interest
        cash_taxes = taxable * tax_rate if taxable > 0 else ZERO
        nwc = (revenue - prev_revenue) * nwc_rate
        cfads_calc = f.cfads(ebitda, inp.maintenance_capex, cash_taxes, nwc)
        cfads_v = cfads_calc.value or ZERO
        debt_service = interest + principal
        dscr_calc = f.dscr(cfads_v, debt_service)
        fcfe = cfads_v - debt_service
        years.append(
            YearProjection(
                year=t,
                revenue=quantize_money(revenue) or ZERO,
                gross_profit=quantize_money(gross_profit) or ZERO,
                labor_opex=quantize_money(labor) or ZERO,
                other_opex=quantize_money(other) or ZERO,
                addbacks=quantize_money(addbacks) or ZERO,
                ebitda=quantize_money(ebitda) or ZERO,
                depreciation_amortization=inp.depreciation_amortization,
                interest=interest,
                principal=principal,
                taxable_income=quantize_money(taxable) or ZERO,
                cash_taxes=quantize_money(cash_taxes) or ZERO,
                working_capital_investment=quantize_money(nwc) or ZERO,
                cfads=cfads_v,
                debt_service=quantize_money(debt_service) or ZERO,
                dscr=dscr_calc.value,
                fcfe=quantize_money(fcfe) or ZERO,
                closing_debt=closing_debt,
            )
        )
        if t == 1:
            calcs["cfads"] = cfads_calc.as_snapshot()
            calcs["dscr"] = dscr_calc.as_snapshot()
        prev_revenue = revenue

    y1 = years[0]
    coc = f.cash_on_cash(y1.fcfe, equity)
    calcs["cash_on_cash"] = coc.as_snapshot()

    last = years[-1]
    exit_ev = quantize_money(last.ebitda * inp.exit_multiple) or ZERO
    exit_equity = quantize_money(exit_ev - last.closing_debt) or ZERO
    cashflows = [-equity] + [y.fcfe for y in years[:-1]] + [last.fcfe + exit_equity]
    irr_calc = f.irr(cashflows)
    calcs["irr"] = irr_calc.as_snapshot()

    be = f.break_even_revenue(
        fixed_costs=y1.labor_opex + y1.other_opex - y1.addbacks,
        contribution_margin_pct=gm * HUNDRED,
        annual_debt_service_value=ads,
        maintenance_capex=inp.maintenance_capex,
    )
    calcs["break_even_revenue"] = be.as_snapshot()

    threshold = inp.covenant_dscr_threshold
    if threshold is not None and y1.dscr is not None:
        if y1.dscr < threshold:
            warnings.append(
                {
                    "code": "covenant_breach",
                    "severity": "critical",
                    "year": 1,
                    "message": f"Year-1 DSCR {y1.dscr:.2f}x is below the {threshold:.2f}x covenant threshold.",
                    "value": str(y1.dscr),
                    "threshold": str(threshold),
                }
            )
        elif y1.dscr < threshold * Decimal("1.10"):
            warnings.append(
                {
                    "code": "covenant_warning",
                    "severity": "high",
                    "year": 1,
                    "message": f"Year-1 DSCR {y1.dscr:.2f}x is within 10% of the {threshold:.2f}x covenant threshold.",
                    "value": str(y1.dscr),
                    "threshold": str(threshold),
                }
            )
        for y in years[1:]:
            if y1.dscr >= threshold and y.dscr is not None and y.dscr < threshold:
                warnings.append(
                    {
                        "code": "covenant_breach",
                        "severity": "high",
                        "year": y.year,
                        "message": f"Year-{y.year} DSCR {y.dscr:.2f}x is below the {threshold:.2f}x covenant threshold.",
                        "value": str(y.dscr),
                        "threshold": str(threshold),
                    }
                )
                break
    if y1.fcfe < 0:
        warnings.append(
            {
                "code": "equity_shortfall",
                "severity": "critical",
                "year": 1,
                "message": f"Year-1 cash flow to equity is negative ({y1.fcfe:,.0f}); the deal requires additional equity or a restructured facility.",
                "value": str(y1.fcfe),
            }
        )
    if y1.ebitda < ZERO:
        warnings.append(
            {
                "code": "negative_ebitda",
                "severity": "critical",
                "year": 1,
                "message": "Year-1 EBITDA is negative under these assumptions.",
                "value": str(y1.ebitda),
            }
        )
    if irr_calc.value is not None and irr_calc.value < 0:
        warnings.append(
            {
                "code": "negative_irr",
                "severity": "high",
                "year": inp.hold_years,
                "message": f"Projected equity IRR is negative ({irr_calc.value:.1f}%).",
                "value": str(irr_calc.value),
            }
        )

    return ScenarioOutputs(
        engine_version=ENGINE_VERSION,
        years=years,
        enterprise_value=inp.purchase_price,
        funded_debt=funded_debt,
        equity=equity,
        annual_debt_service=ads,
        year1={
            "revenue": str(y1.revenue),
            "ebitda": str(y1.ebitda),
            "cfads": str(y1.cfads),
            "debt_service": str(y1.debt_service),
            "dscr": None if y1.dscr is None else str(y1.dscr),
            "fcfe": str(y1.fcfe),
        },
        cfads_bridge={
            "adjusted_ebitda": str(y1.ebitda),
            "maintenance_capex": str(-inp.maintenance_capex),
            "cash_taxes": str(-y1.cash_taxes),
            "working_capital_investment": str(-y1.working_capital_investment),
            "cfads": str(y1.cfads),
        },
        dscr=y1.dscr,
        cash_on_cash_pct=coc.value,
        irr_pct=irr_calc.value,
        irr_cashflows=[str(quantize_money(c)) for c in cashflows],
        exit={
            "year": inp.hold_years,
            "ebitda": str(last.ebitda),
            "exit_multiple": str(inp.exit_multiple),
            "enterprise_value": str(exit_ev),
            "debt_repaid_balance": str(last.closing_debt),
            "equity_proceeds": str(exit_equity),
        },
        break_even_revenue=be.value,
        warnings=warnings,
        calcs=calcs,
    )


def sensitivity_grid(
    inp: ScenarioInputs,
    row_key: str,
    row_values: list[Decimal],
    col_key: str,
    col_values: list[Decimal],
    output: str = "dscr",
) -> dict[str, Any]:
    """Recompute year-1 DSCR (or another year-1 output) over a grid of two assumptions."""
    cells: list[list[dict[str, Any]]] = []
    for rv in row_values:
        row: list[dict[str, Any]] = []
        for cv in col_values:
            variant = ScenarioInputs(**{**asdict(inp), row_key: rv, col_key: cv})
            out = project(variant)
            value = out.year1.get(output)
            breach = out.dscr is not None and inp.covenant_dscr_threshold is not None and out.dscr < inp.covenant_dscr_threshold
            row.append({"row": str(rv), "col": str(cv), "value": value, "breach": breach})
        cells.append(row)
    return {
        "row_key": row_key,
        "col_key": col_key,
        "row_values": [str(v) for v in row_values],
        "col_values": [str(v) for v in col_values],
        "output": output,
        "threshold": None if inp.covenant_dscr_threshold is None else str(inp.covenant_dscr_threshold),
        "cells": cells,
        "engine_version": ENGINE_VERSION,
    }


def inputs_from_dict(data: dict[str, Any]) -> ScenarioInputs:
    ints = {"amortization_years", "payments_per_year", "hold_years"}
    kwargs: dict[str, Any] = {}
    for key in ScenarioInputs.__dataclass_fields__:
        v = data[key]
        if key in ints:
            kwargs[key] = int(v)
        elif key == "covenant_dscr_threshold":
            kwargs[key] = D(v)
        else:
            kwargs[key] = D(v)
    return ScenarioInputs(**kwargs)


__all__ = [
    "ASSUMPTION_SPECS",
    "ScenarioInputs",
    "ScenarioOutputs",
    "YearProjection",
    "inputs_from_dict",
    "project",
    "quantize_ratio",
    "sensitivity_grid",
]
