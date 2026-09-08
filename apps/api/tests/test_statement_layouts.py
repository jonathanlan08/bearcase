"""Equivalent statement layouts must give equivalent numbers (mapper + metric engine, no database)."""

from decimal import Decimal

from bearcase.engine.metrics import period_metrics
from bearcase.ingest.parsers.common import ParsedChunk
from bearcase.ingest.statement_mapper import map_income_statement


def _mapped(rows: list[list[str]], sheet: str = "Income Statement"):
    return map_income_statement(
        [ParsedChunk("sheet_row", {"sheet": sheet, "row": i + 1}, " | ".join(r), {"values": r}) for i, r in enumerate(rows)]
    )


def _cagr(statement):
    return next(c for c in period_metrics(statement.as_periods()) if c.calc.key == "cagr")


def test_column_order_does_not_change_growth() -> None:
    asc = _mapped([["Line item", "FY2022", "FY2023", "FY2024"], ["Revenue", "100", "110", "121"]])
    desc = _mapped([["Line item", "FY2024", "FY2023", "FY2022"], ["Revenue", "121", "110", "100"]])
    assert asc is not None and desc is not None
    assert asc.periods == desc.periods == ["FY2022", "FY2023", "FY2024"]
    assert asc.as_periods() == desc.as_periods()
    a, d = _cagr(asc), _cagr(desc)
    assert a.calc.value == d.calc.value == Decimal("10.00000000")
    assert a.period_label == d.period_label == "FY2024"


def test_missing_year_uses_elapsed_years() -> None:
    gap = _mapped([["Line item", "FY2022", "FY2024"], ["Revenue", "100", "121"]])
    assert gap is not None
    c = _cagr(gap)
    assert c.calc.value == Decimal("10.00000000")
    growth = next(c for c in period_metrics(gap.as_periods()) if c.calc.key == "revenue_growth")
    assert growth.calc.value == Decimal("21.00000000")
    assert any("spans 2 years" in n for n in growth.calc.notes)


def test_duplicate_year_columns_are_rejected() -> None:
    assert _mapped([["Line item", "FY2024", "FY2024"], ["Revenue", "1", "2"]]) is None


def test_thousands_scale_is_applied() -> None:
    s = _mapped([["Income Statement (USD in thousands)"], ["Line item", "FY2023", "FY2024"], ["Revenue", "1100", "1210"]])
    assert s is not None
    assert s.scale == 1000
    mv = s.lines["FY2024"]["revenue"]
    assert mv.value == Decimal("1210000")
    assert mv.raw == "1210"


def test_scale_from_sheet_title() -> None:
    s = _mapped([["Line item", "FY2023", "FY2024"], ["Revenue", "2", "3"]], sheet="P&L ($000s)")
    assert s is not None and s.lines["FY2024"]["revenue"].value == Decimal("3000")


def test_revenue_components_sum_and_require_review() -> None:
    s = _mapped([["Line item", "FY2023", "FY2024"], ["Revenue - service", "100", "120"], ["Revenue - installation", "200", "240"]])
    assert s is not None
    mv = s.lines["FY2024"]["revenue"]
    assert mv.value == Decimal("360")
    assert mv.confidence < 0.8
    assert s.ambiguous["revenue"] == ["Revenue - service", "Revenue - installation"]


def test_total_row_wins_over_components() -> None:
    s = _mapped([["Line item", "FY2023", "FY2024"], ["Revenue - service", "100", "120"], ["Total revenue", "300", "360"]])
    assert s is not None
    mv = s.lines["FY2024"]["revenue"]
    assert mv.value == Decimal("360") and mv.confidence == 1.0 and "revenue" not in s.ambiguous


def test_numbers_in_titles_do_not_imply_scale() -> None:
    s = _mapped([["Northstar HVAC statements, 10000 Main St"], ["Line item", "FY2023", "FY2024"], ["Revenue", "5", "6"]])
    assert s is not None and s.scale == 1 and s.lines["FY2024"]["revenue"].value == Decimal("6")


def test_currency_is_stated_or_assumed() -> None:
    from bearcase.ingest.statement_mapper import detect_currency

    stated = _mapped([["Income statement (USD)"], ["Line item", "FY2023", "FY2024"], ["Revenue", "1", "2"]])
    assert stated is not None and stated.currency == "USD"
    silent = _mapped([["Income statement"], ["Line item", "FY2023", "FY2024"], ["Revenue", "1", "2"]])
    assert silent is not None and silent.currency is None
    assert detect_currency("Statement of income, in EUR thousands") == "EUR"
