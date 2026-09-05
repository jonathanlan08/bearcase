"""Independent worked examples for every formula. Expected values were computed by hand."""

from decimal import Decimal as D

from bearcase.engine import formulas as f


def test_revenue_growth_and_missing():
    assert f.revenue_growth(D("11600000"), D("10400000")).value == D("11.53846154")
    c = f.revenue_growth(D("10"), None)
    assert c.value is None and c.missing == ("prior_period_revenue",)
    z = f.revenue_growth(D("10"), D("0"))
    assert z.value is None and "zero" in z.notes[0]


def test_cagr_two_years():
    # (12.95 / 10.40) ** 0.5 - 1 = 0.115882 -> 11.59%
    assert f.cagr(D("10400000"), D("12950000"), 2).value == D("11.58818520")


def test_margins():
    assert f.gross_margin(D("12950000"), D("8417500")).value == D("35.00000000")
    assert f.operating_margin(D("1330000"), D("12950000")).value == D("10.27027027")
    assert f.gross_margin(D("0"), D("0")).value is None


def test_reported_ebitda_reconciliation():
    # 1,173,250 + 95,000 + 61,750 + 280,000 + 30,000 = 1,640,000
    c = f.reported_ebitda(D("1173250"), D("95000"), D("61750"), D("280000"), D("30000"))
    assert c.value == D("1640000.00")


def test_adjusted_ebitda_excludes_rejected():
    c = f.adjusted_ebitda(D("1640000"), {"owner": D("105000"), "litigation": D("65000")})
    assert c.value == D("1810000.00")
    assert f.adjusted_ebitda(None, {}).missing == ("reported_ebitda",)


def test_enterprise_value_bases():
    assert f.enterprise_value(D("12600000"), "enterprise_value").value == D("12600000.00")
    assert f.enterprise_value(D("5000000"), "equity_price", D("8000000"), D("400000")).value == D("12600000.00")


def test_multiples():
    assert f.ev_to_ebitda(D("12600000"), D("2100000")).value == D("6.00000000")
    assert f.ev_to_ebitda(D("12600000"), D("1810000")).value == D("6.96132597")
    assert f.debt_to_ebitda(D("7560000"), D("1810000")).value == D("4.17679558")
    assert f.ev_to_ebitda(D("1"), D("0")).value is None


def test_debt_service_hand_check():
    # r = 0.08/12, n = 120: payment = 7,560,000 * r / (1 - (1+r)^-120) = 91,723.66; * 12 = 1,100,683.94
    c = f.annual_debt_service(D("7560000"), D("8.0"), 10, 12)
    assert c.value == D("1100683.94")
    assert f.annual_debt_service(D("1200"), D("0"), 1, 12).value == D("1200.00")
    sched = f.amortization_schedule(D("7560000"), D("8.0"), 10, 12)
    assert len(sched) == 10
    assert sched[0].interest + sched[0].principal == D("1100683.94")
    assert abs(sched[-1].closing_balance) < D("0.05")


def test_cfads_and_dscr():
    c = f.cfads(D("1810000"), D("185000"), D("120000"), D("45000"))
    assert c.value == D("1460000.00")
    assert f.dscr(D("1460000"), D("1100683.94")).value == D("1.32644799")
    assert f.dscr(D("1"), D("0")).value is None


def test_cash_on_cash_and_irr():
    assert f.cash_on_cash(D("376141.62"), D("5040000")).value == D("7.46312738")
    # -100 now, +110 in one year -> 10%
    assert f.irr([D("-100"), D("110")]).value == D("10.00000000")
    assert f.irr([D("-100"), D("-5")]).value is None
    assert "periodic" in f.irr([D("-100"), D("60"), D("60")]).notes[0]


def test_break_even_requires_inputs():
    c = f.break_even_revenue(D("2600000"), D("35"), D("1100000"), D("185000"))
    assert c.value == D("11100000.00")
    assert f.break_even_revenue(None, D("35"), D("1"), D("1")).value is None


def test_concentration_and_recurring():
    assert f.customer_concentration(D("2850000"), D("12950000")).value == D("22.00772201")
    assert f.recurring_revenue_share(D("8806000"), D("12950000")).value == D("68.00000000")
