# Formula contract

Implementation: `apps/api/src/bearcase/engine/formulas.py`. All arithmetic uses `decimal.Decimal`. Every function returns a `Calc` with `value`, `unit`, `formula`, `inputs`, `missing`, and `notes`. A missing input yields `value=None` with the input named in `missing`; divide-by-zero yields `value=None` with a note. Callers must never default a `None`.

| Key | Formula | Missing data / edge behavior |
|---|---|---|
| `revenue_growth` | (current − prior) / prior | None when prior missing or zero |
| `cagr` | (last / first)^(1/years) − 1 | None for non-positive base or zero years |
| `gross_margin` | (revenue − COGS) / revenue | None when revenue is zero |
| `operating_margin` | operating income / revenue | None when revenue is zero |
| `ebitda_reported` | net income + interest + tax + depreciation + amortization | A stated EBITDA line that differs by > $1 adds a review note |
| `ebitda_adjusted_verified` | reported + Σ accepted add-backs − Σ accepted downward adjustments | Rejected/review/unsupported items excluded but preserved |
| `enterprise_value` | purchase price (EV basis) or equity price + debt assumed − cash acquired | Basis is an explicit deal input |
| `ev_to_ebitda` | EV / EBITDA | None when EBITDA is zero; negative noted |
| `debt_to_ebitda` | funded debt / EBITDA | None when EBITDA is zero |
| `annual_debt_service` | P·r/(1−(1+r)^−n) × payments per year | Zero rate: P/n; interest-only and balloon out of scope |
| `cfads` | adjusted EBITDA − maintenance capex − cash taxes − working-capital investment | Bridge persisted with each scenario |
| `dscr` | CFADS / annual debt service | None when debt service is zero |
| `cash_on_cash` | year-1 cash flow to equity / initial equity | None when equity is zero |
| `irr` | Σ cf_t/(1+r)^t = 0, annual periods, bisection on [−99%, 1000%] | None without a sign change; periodic, not XIRR |
| `break_even_revenue` | (fixed costs + capex + debt service) / contribution margin | Pre-tax, before working capital; None when inputs missing |
| `customer_concentration_top1` | top customer revenue / total | — |
| `recurring_revenue_pct` | contract-supported recurring revenue / total | — |

## Scenario projection (`engine/scenarios.py`)

Year t (1..5): revenue = (base − largest customer × loss%) × (1+g)^t; gross profit = revenue × (GM + bps/10000); labor = labor × (1+labor growth)^t; other = other × (1+other growth)^t; EBITDA = gross profit − labor − other + accepted add-backs; interest and principal from the level amortization schedule; cash taxes = max(0, EBITDA − D&A − interest) × rate; working-capital investment = Δrevenue × NWC%; CFADS per the bridge; DSCR = CFADS / (interest + principal); FCFE = CFADS − debt service; exit at hold year = EBITDA × exit multiple (entry EV / verified EBITDA) − remaining debt; IRR over [−equity, FCFE₁..₄, FCFE₅ + exit equity].

Warnings: `covenant_breach` (DSCR < threshold), `covenant_warning` (DSCR < 1.1 × threshold), `equity_shortfall` (FCFE₁ < 0), `negative_ebitda`, `negative_irr`.

## Worked example (Northstar, base case)

Debt $7,560,000 at 8.00% over 10 years, monthly: payment = 7,560,000 × 0.0066667 / (1 − 1.0066667^−120) = $91,723.66; annual debt service $1,100,683.94. Year-1 EBITDA $1,917,800; capex $185,000; cash taxes $214,534; working capital $41,440; CFADS $1,476,826; DSCR 1.34x. Tests in `apps/api/tests/test_formulas.py` and `test_scenarios.py` pin these values.
