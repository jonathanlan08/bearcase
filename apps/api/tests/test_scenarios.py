from decimal import Decimal as D

import pytest

from bearcase.engine.scenarios import ScenarioInputs, inputs_from_dict, project, sensitivity_grid
from bearcase.fixtures import northstar_facts as N

FACTS = dict(
    base_revenue=D("12950000"),
    largest_customer_revenue=D("2850000"),
    gross_margin_pct=D("35"),
    labor_opex=D("1565000"),
    other_opex=D("1327500"),
    depreciation_amortization=D("310000"),
    amortization_years=10,
    payments_per_year=12,
    covenant_dscr_threshold=D("1.25"),
    exit_multiple=D("6.96132597"),
    hold_years=5,
)


def _inputs(key: str) -> ScenarioInputs:
    return ScenarioInputs(**FACTS, **N.SCENARIOS[key]["assumptions"])


def test_base_case_above_threshold_with_warning():
    out = project(_inputs("base"))
    y1 = out.years[0]
    assert y1.revenue == D("13468000.00")
    assert y1.ebitda == D("1917800.00")
    assert out.dscr == D("1.34173445")
    assert out.dscr > D("1.25")
    assert [w["code"] for w in out.warnings] == ["covenant_warning"]


def test_downside_breaches_covenant():
    out = project(_inputs("downside"))
    assert out.dscr == D("0.99700720")
    assert any(w["code"] == "covenant_breach" for w in out.warnings)
    assert out.years[0].working_capital_investment < 0  # revenue decline releases working capital


def test_severe_downside():
    out = project(_inputs("severe_downside"))
    assert out.dscr < D("0.5")
    assert out.irr_pct is None  # no sign change -> undefined, never silently defaulted


def test_snapshot_round_trip_and_hash_stability():
    inp = _inputs("base")
    again = inputs_from_dict(inp.snapshot())
    assert again == inp and again.hash() == inp.hash()
    assert project(inp).to_dict()["year1"] == project(again).to_dict()["year1"]


def test_ground_truth_matches_engine(ground_truth):
    for key, sc in ground_truth["scenarios"].items():
        out = project(_inputs(key))
        assert str(out.dscr) == sc["expected"]["dscr"], key
        assert str(out.annual_debt_service) == sc["expected"]["annual_debt_service"]


def test_sensitivity_grid_marks_breaches():
    grid = sensitivity_grid(
        _inputs("base"), "largest_customer_loss_pct", [D("0"), D("50")], "gross_margin_change_bps", [D("0"), D("-300")]
    )
    assert grid["cells"][0][0]["breach"] is False
    assert grid["cells"][1][1]["breach"] is True


@pytest.mark.parametrize("rate", ["0", "8.0"])
def test_zero_rate_debt(rate):
    out = project(ScenarioInputs(**{**FACTS}, **{**N.SCENARIOS["base"]["assumptions"], "interest_rate_pct": D(rate)}))
    assert out.annual_debt_service > 0
