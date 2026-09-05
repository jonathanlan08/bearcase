"""Decimal helpers and the Calc result type used by every formula."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, getcontext
from typing import Any

getcontext().prec = 34

MONEY_Q = Decimal("0.01")
RATIO_Q = Decimal("0.00000001")
Number = int | float | str | Decimal


def D(value: Number | None) -> Decimal | None:  # conventional short name
    """Coerce to Decimal without binary-float artifacts. None passes through."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(repr(value))
    return Decimal(str(value))


def quantize_money(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def quantize_ratio(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(RATIO_Q, rounding=ROUND_HALF_UP)


def safe_div(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    """Division that returns None when either side is missing or the denominator is zero."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def pct(value: Decimal | None) -> Decimal | None:
    """Ratio (0.116) → percent (11.6)."""
    return None if value is None else value * Decimal(100)


@dataclass(frozen=True)
class Calc:
    """A calculation result with its complete provenance.

    value is None when a required input is missing or a divide-by-zero occurred; `missing`
    and `notes` explain why. Callers must never substitute a default for a None value.
    """

    key: str
    value: Decimal | None
    unit: str  # usd | pct | multiple | years | ratio
    formula: str
    inputs: dict[str, Any] = field(default_factory=dict)
    missing: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.value is not None

    def as_snapshot(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": None if self.value is None else str(self.value),
            "unit": self.unit,
            "formula": self.formula,
            "inputs": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in self.inputs.items()},
            "missing": list(self.missing),
            "notes": list(self.notes),
        }


def require(**values: Decimal | None) -> tuple[str, ...]:
    return tuple(k for k, v in values.items() if v is None)
