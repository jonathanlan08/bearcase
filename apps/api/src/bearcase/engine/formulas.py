"""Documented formulas. Each function is pure, Decimal-based, and returns a Calc.

Missing-data policy: a None input yields Calc(value=None, missing=(...)). Divide-by-zero
policy: the quotient is None with a note. Nothing is ever silently defaulted.
See docs/formulas/README.md for the human-readable contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from bearcase.engine.money import Calc, D, pct, quantize_money, quantize_ratio, require, safe_div

ZERO = Decimal(0)
ONE = Decimal(1)


def _qm(value: Decimal) -> Decimal:
    """Non-optional money quantization for schedule rows."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def revenue_growth(current: Decimal | None, prior: Decimal | None, label: str = "revenue_growth") -> Calc:
    """(current_period_revenue - prior_period_revenue) / prior_period_revenue"""
    missing = require(current_period_revenue=current, prior_period_revenue=prior)
    value = None
    notes: tuple[str, ...] = ()
    if not missing:
        value = safe_div(current - prior, prior)  # type: ignore[operator]
        if value is None:
            notes = ("prior_period_revenue is zero; growth undefined",)
    return Calc(
        label,
        quantize_ratio(pct(value)),
        "pct",
        "(current_period_revenue - prior_period_revenue) / prior_period_revenue",
        {"current_period_revenue": current, "prior_period_revenue": prior},
        missing,
        notes,
    )


def cagr(first: Decimal | None, last: Decimal | None, years: int) -> Calc:
    """(last / first) ** (1 / years) - 1"""
    missing = require(first_period_revenue=first, last_period_revenue=last)
    value = None
    notes: tuple[str, ...] = ()
    if not missing:
        if first <= 0 or years <= 0:  # type: ignore[operator]
            notes = ("CAGR undefined for non-positive base or zero years",)
        else:
            ratio = last / first  # type: ignore[operator]
            value = D(float(ratio) ** (1.0 / years)) - ONE  # type: ignore[operator]
    return Calc(
        "cagr",
        quantize_ratio(pct(value)),
        "pct",
        "(last_period_revenue / first_period_revenue) ** (1 / years) - 1",
        {"first_period_revenue": first, "last_period_revenue": last, "years": years},
        missing,
        notes,
    )


def gross_margin(revenue: Decimal | None, cogs: Decimal | None) -> Calc:
    """(revenue - cost_of_goods_sold) / revenue"""
    missing = require(revenue=revenue, cost_of_goods_sold=cogs)
    value = None if missing else safe_div(revenue - cogs, revenue)  # type: ignore[operator]
    notes = ("revenue is zero; margin undefined",) if (not missing and value is None) else ()
    return Calc(
        "gross_margin",
        quantize_ratio(pct(value)),
        "pct",
        "(revenue - cost_of_goods_sold) / revenue",
        {"revenue": revenue, "cost_of_goods_sold": cogs},
        missing,
        notes,
    )


def operating_margin(operating_income: Decimal | None, revenue: Decimal | None) -> Calc:
    """operating_income / revenue"""
    missing = require(operating_income=operating_income, revenue=revenue)
    value = None if missing else safe_div(operating_income, revenue)
    notes = ("revenue is zero; margin undefined",) if (not missing and value is None) else ()
    return Calc(
        "operating_margin",
        quantize_ratio(pct(value)),
        "pct",
        "operating_income / revenue",
        {"operating_income": operating_income, "revenue": revenue},
        missing,
        notes,
    )


def reported_ebitda(
    net_income: Decimal | None,
    interest_expense: Decimal | None,
    income_tax_expense: Decimal | None,
    depreciation: Decimal | None,
    amortization: Decimal | None,
) -> Calc:
    """net_income + interest_expense + income_tax_expense + depreciation + amortization"""
    missing = require(
        net_income=net_income,
        interest_expense=interest_expense,
        income_tax_expense=income_tax_expense,
        depreciation=depreciation,
        amortization=amortization,
    )
    value = None
    if not missing:
        value = net_income + interest_expense + income_tax_expense + depreciation + amortization  # type: ignore[operator]
    return Calc(
        "ebitda_reported",
        quantize_money(value),
        "usd",
        "net_income + interest_expense + income_tax_expense + depreciation + amortization",
        {
            "net_income": net_income,
            "interest_expense": interest_expense,
            "income_tax_expense": income_tax_expense,
            "depreciation": depreciation,
            "amortization": amortization,
        },
        missing,
    )


def adjusted_ebitda(
    reported: Decimal | None,
    accepted_add_backs: dict[str, Decimal],
    accepted_downward_adjustments: dict[str, Decimal] | None = None,
    key: str = "ebitda_adjusted_verified",
) -> Calc:
    """reported_EBITDA + sum(accepted_add_backs) - sum(accepted_downward_adjustments)"""
    downward = accepted_downward_adjustments or {}
    missing = require(reported_ebitda=reported)
    value = None
    if not missing:
        value = reported + sum(accepted_add_backs.values(), ZERO) - sum(downward.values(), ZERO)  # type: ignore[operator]
    return Calc(
        key,
        quantize_money(value),
        "usd",
        "reported_EBITDA + sum(accepted_add_backs) - sum(accepted_downward_adjustments)",
        {
            "reported_ebitda": reported,
            "accepted_add_backs": {k: str(v) for k, v in accepted_add_backs.items()},
            "accepted_downward_adjustments": {k: str(v) for k, v in downward.items()},
        },
        missing,
    )


def enterprise_value(
    purchase_price: Decimal | None,
    basis: str,
    debt_assumed: Decimal | None = ZERO,
    cash_acquired: Decimal | None = ZERO,
) -> Calc:
    """basis == enterprise_value: purchase_price; else equity_purchase_price + debt_assumed - cash_acquired"""
    if basis == "enterprise_value":
        missing = require(purchase_price=purchase_price)
        return Calc(
            "enterprise_value",
            quantize_money(purchase_price),
            "usd",
            "purchase_price (stated as enterprise value)",
            {"purchase_price": purchase_price, "basis": basis},
            missing,
        )
    missing = require(equity_purchase_price=purchase_price, debt_assumed=debt_assumed, cash_acquired=cash_acquired)
    value = None if missing else purchase_price + debt_assumed - cash_acquired  # type: ignore[operator]
    return Calc(
        "enterprise_value",
        quantize_money(value),
        "usd",
        "equity_purchase_price + debt_assumed - cash_acquired",
        {"equity_purchase_price": purchase_price, "debt_assumed": debt_assumed, "cash_acquired": cash_acquired, "basis": basis},
        missing,
    )


def ev_to_ebitda(ev: Decimal | None, ebitda: Decimal | None, key: str = "ev_to_ebitda") -> Calc:
    """enterprise_value / EBITDA"""
    missing = require(enterprise_value=ev, ebitda=ebitda)
    value = None if missing else safe_div(ev, ebitda)
    notes = ("EBITDA is zero; multiple undefined",) if (not missing and value is None) else ()
    if value is not None and ebitda is not None and ebitda < 0:
        notes = ("EBITDA is negative; multiple is not meaningful",)
    return Calc(
        key,
        quantize_ratio(value),
        "multiple",
        "enterprise_value / EBITDA",
        {"enterprise_value": ev, "ebitda": ebitda},
        missing,
        notes,
    )


def debt_to_ebitda(funded_debt: Decimal | None, ebitda: Decimal | None, key: str = "debt_to_ebitda") -> Calc:
    """funded_debt / EBITDA"""
    missing = require(funded_debt=funded_debt, ebitda=ebitda)
    value = None if missing else safe_div(funded_debt, ebitda)
    notes = ("EBITDA is zero; leverage undefined",) if (not missing and value is None) else ()
    return Calc(
        key,
        quantize_ratio(value),
        "multiple",
        "funded_debt / EBITDA",
        {"funded_debt": funded_debt, "ebitda": ebitda},
        missing,
        notes,
    )


def periodic_payment(principal: Decimal, annual_rate_pct: Decimal, years: int, payments_per_year: int = 12) -> Decimal:
    """payment = P * r / (1 - (1 + r) ** -n); zero-rate: P / n"""
    n = years * payments_per_year
    if n <= 0:
        raise ValueError("amortization must cover at least one period")
    r = annual_rate_pct / Decimal(100) / Decimal(payments_per_year)
    if r == 0:
        return principal / Decimal(n)
    return principal * r / (ONE - (ONE + r) ** (-n))


def annual_debt_service(
    principal: Decimal | None, annual_rate_pct: Decimal | None, years: int | None, payments_per_year: int = 12
) -> Calc:
    """payment * payments_per_year for a level amortizing loan. Interest-only and balloon structures
    require an explicit schedule and are not modeled by this function."""
    missing = require(principal=principal, annual_rate_pct=annual_rate_pct)
    if years is None:
        missing = (*missing, "amortization_years")
    value = None
    notes: tuple[str, ...] = ()
    if not missing:
        payment = periodic_payment(principal, annual_rate_pct, years, payments_per_year)  # type: ignore[arg-type]
        value = payment * Decimal(payments_per_year)
        if annual_rate_pct == 0:
            notes = ("zero-interest debt: straight-line principal repayment",)
    return Calc(
        "annual_debt_service",
        quantize_money(value),
        "usd",
        "payment = P * r / (1 - (1 + r) ** -n); annual_debt_service = payment * payments_per_year",
        {
            "principal": principal,
            "annual_rate_pct": annual_rate_pct,
            "amortization_years": years,
            "payments_per_year": payments_per_year,
        },
        missing,
        notes,
    )


@dataclass(frozen=True)
class YearSchedule:
    year: int
    opening_balance: Decimal
    interest: Decimal
    principal: Decimal
    closing_balance: Decimal


def amortization_schedule(
    principal: Decimal, annual_rate_pct: Decimal, years: int, payments_per_year: int = 12
) -> list[YearSchedule]:
    """Level-payment schedule aggregated to annual interest and principal."""
    payment = periodic_payment(principal, annual_rate_pct, years, payments_per_year)
    r = annual_rate_pct / Decimal(100) / Decimal(payments_per_year)
    balance = principal
    out: list[YearSchedule] = []
    for year in range(1, years + 1):
        opening = balance
        interest_total = ZERO
        principal_total = ZERO
        for _ in range(payments_per_year):
            interest = balance * r
            principal_part = payment - interest
            if principal_part > balance:
                principal_part = balance
            balance -= principal_part
            interest_total += interest
            principal_total += principal_part
        out.append(YearSchedule(year, _qm(opening), _qm(interest_total), _qm(principal_total), _qm(balance)))
    return out


def cfads(
    adjusted_ebitda_value: Decimal | None,
    maintenance_capex: Decimal | None,
    cash_taxes: Decimal | None,
    working_capital_investment: Decimal | None,
) -> Calc:
    """adjusted_EBITDA - maintenance_capex - cash_taxes - working_capital_investment

    This is the CFADS bridge BearCase exposes. EBITDA is never silently labeled CFADS."""
    missing = require(
        adjusted_ebitda=adjusted_ebitda_value,
        maintenance_capex=maintenance_capex,
        cash_taxes=cash_taxes,
        working_capital_investment=working_capital_investment,
    )
    value = None
    if not missing:
        value = adjusted_ebitda_value - maintenance_capex - cash_taxes - working_capital_investment  # type: ignore[operator]
    return Calc(
        "cfads",
        quantize_money(value),
        "usd",
        "adjusted_EBITDA - maintenance_capex - cash_taxes - working_capital_investment",
        {
            "adjusted_ebitda": adjusted_ebitda_value,
            "maintenance_capex": maintenance_capex,
            "cash_taxes": cash_taxes,
            "working_capital_investment": working_capital_investment,
        },
        missing,
    )


def dscr(cfads_value: Decimal | None, ads: Decimal | None) -> Calc:
    """cash_flow_available_for_debt_service / annual_debt_service"""
    missing = require(cfads=cfads_value, annual_debt_service=ads)
    value = None if missing else safe_div(cfads_value, ads)
    notes = ("annual_debt_service is zero; DSCR undefined",) if (not missing and value is None) else ()
    return Calc(
        "dscr",
        quantize_ratio(value),
        "multiple",
        "cash_flow_available_for_debt_service / annual_debt_service",
        {"cfads": cfads_value, "annual_debt_service": ads},
        missing,
        notes,
    )


def cash_on_cash(year_one_cash_flow_to_equity: Decimal | None, initial_equity: Decimal | None) -> Calc:
    """year_one_cash_flow_to_equity / initial_equity_contribution"""
    missing = require(year_one_cash_flow_to_equity=year_one_cash_flow_to_equity, initial_equity_contribution=initial_equity)
    value = None if missing else safe_div(year_one_cash_flow_to_equity, initial_equity)
    notes = ("initial equity is zero; return undefined",) if (not missing and value is None) else ()
    return Calc(
        "cash_on_cash",
        quantize_ratio(pct(value)),
        "pct",
        "year_one_cash_flow_to_equity / initial_equity_contribution",
        {"year_one_cash_flow_to_equity": year_one_cash_flow_to_equity, "initial_equity_contribution": initial_equity},
        missing,
        notes,
    )


def irr(cashflows: list[Decimal], max_iter: int = 200, tol: Decimal = Decimal("1e-10")) -> Calc:
    """Periodic IRR (equal annual periods): the rate r where sum(cf_t / (1+r)^t) = 0.

    Not XIRR: dates are not used. Solved by bisection on [-0.99, 10]; None if no sign change."""
    inputs = {"cashflows": [str(c) for c in cashflows], "method": "periodic_bisection"}
    if len(cashflows) < 2:
        return Calc("irr", None, "pct", "sum(cf_t / (1 + r)^t) = 0", inputs, ("cashflows",))
    if not (any(c < 0 for c in cashflows) and any(c > 0 for c in cashflows)):
        return Calc("irr", None, "pct", "sum(cf_t / (1 + r)^t) = 0", inputs, (), ("no sign change in cash flows; IRR undefined",))

    def npv(rate: Decimal) -> Decimal:
        total = ZERO
        for t, cf in enumerate(cashflows):
            total += cf / (ONE + rate) ** t
        return total

    lo, hi = Decimal("-0.99"), Decimal("10")
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return Calc("irr", None, "pct", "sum(cf_t / (1 + r)^t) = 0", inputs, (), ("no root in [-99%, 1000%]",))
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < tol or (hi - lo) < tol:
            break
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    rate = (lo + hi) / 2
    return Calc(
        "irr",
        quantize_ratio(pct(rate)),
        "pct",
        "sum(cf_t / (1 + r)^t) = 0 (periodic, annual)",
        inputs,
        (),
        ("periodic IRR, not date-aware XIRR",),
    )


def break_even_revenue(
    fixed_costs: Decimal | None,
    contribution_margin_pct: Decimal | None,
    annual_debt_service_value: Decimal | None,
    maintenance_capex: Decimal | None,
) -> Calc:
    """(fixed_costs + maintenance_capex + annual_debt_service) / contribution_margin

    Revenue at which CFADS equals debt service, before taxes and working capital."""
    missing = require(
        fixed_costs=fixed_costs,
        contribution_margin_pct=contribution_margin_pct,
        annual_debt_service=annual_debt_service_value,
        maintenance_capex=maintenance_capex,
    )
    value = None
    notes: tuple[str, ...] = ("pre-tax, excludes working-capital movements",)
    if not missing:
        cm = contribution_margin_pct / Decimal(100)  # type: ignore[operator]
        value = safe_div(fixed_costs + maintenance_capex + annual_debt_service_value, cm)  # type: ignore[operator]
        if value is None:
            notes = (*notes, "contribution margin is zero; break-even undefined")
    return Calc(
        "break_even_revenue",
        quantize_money(value),
        "usd",
        "(fixed_costs + maintenance_capex + annual_debt_service) / contribution_margin",
        {
            "fixed_costs": fixed_costs,
            "contribution_margin_pct": contribution_margin_pct,
            "annual_debt_service": annual_debt_service_value,
            "maintenance_capex": maintenance_capex,
        },
        missing,
        notes,
    )


def customer_concentration(top_customer_revenue: Decimal | None, total_revenue: Decimal | None) -> Calc:
    """top_customer_revenue / total_revenue"""
    missing = require(top_customer_revenue=top_customer_revenue, total_revenue=total_revenue)
    value = None if missing else safe_div(top_customer_revenue, total_revenue)
    return Calc(
        "customer_concentration_top1",
        quantize_ratio(pct(value)),
        "pct",
        "top_customer_revenue / total_revenue",
        {"top_customer_revenue": top_customer_revenue, "total_revenue": total_revenue},
        missing,
    )


def recurring_revenue_share(recurring_revenue: Decimal | None, total_revenue: Decimal | None) -> Calc:
    """contract_supported_recurring_revenue / total_revenue"""
    missing = require(recurring_revenue=recurring_revenue, total_revenue=total_revenue)
    value = None if missing else safe_div(recurring_revenue, total_revenue)
    return Calc(
        "recurring_revenue_pct",
        quantize_ratio(pct(value)),
        "pct",
        "contract_supported_recurring_revenue / total_revenue",
        {"recurring_revenue": recurring_revenue, "total_revenue": total_revenue},
        missing,
    )
