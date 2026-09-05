"""Map an income-statement sheet to canonical line keys with cell-level provenance."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from bearcase.ingest.parsers.common import ParsedChunk

SYNONYMS: dict[str, list[str]] = {
    "revenue": ["revenue", "net revenue", "total revenue", "sales", "net sales"],
    "cost_of_goods_sold": ["cost of goods sold", "cogs", "cost of sales", "cost of revenue"],
    "gross_profit": ["gross profit", "gross margin $"],
    "opex_owner_compensation": ["owner compensation", "owner salary", "officer compensation"],
    "opex_salaries_wages": ["salaries and wages", "salaries & wages", "payroll", "wages"],
    "opex_temporary_labor": ["temporary labor", "temp labor", "contract labor"],
    "opex_marketing": ["marketing and advertising", "marketing", "advertising"],
    "opex_legal_professional": ["legal and professional fees", "legal and professional", "professional fees", "legal"],
    "opex_insurance": ["insurance"],
    "opex_rent_occupancy": ["rent and occupancy", "rent", "occupancy"],
    "opex_vehicle_fuel": ["vehicle and fuel", "vehicles", "fuel"],
    "opex_software_it": ["software and it", "software", "it expense"],
    "opex_other_ga": ["other general and administrative", "other g&a", "other operating"],
    "operating_expenses": ["total operating expenses", "operating expenses", "total opex"],
    "ebitda": ["ebitda"],
    "depreciation": ["depreciation"],
    "amortization": ["amortization"],
    "operating_income": ["operating income", "ebit", "income from operations"],
    "interest_expense": ["interest expense", "interest"],
    "income_before_tax": ["income before tax", "pre-tax income", "ebt"],
    "income_tax_expense": ["income tax expense", "income taxes", "taxes"],
    "net_income": ["net income", "net earnings", "net profit"],
}
_PERIOD = re.compile(r"^(FY|CY)?\s?(20\d{2})[A-Z]?$", re.I)


@dataclass
class MappedValue:
    value: Decimal
    raw: str
    cell: str
    sheet: str
    row: int
    chunk_index: int
    confidence: float


@dataclass
class StatementMap:
    sheet: str
    periods: list[str]
    lines: dict[str, dict[str, MappedValue]] = field(default_factory=dict)  # period -> line_key -> value
    unmapped_rows: list[dict[str, Any]] = field(default_factory=list)
    header_row: int | None = None

    def as_periods(self) -> dict[str, dict[str, Decimal | None]]:
        return {p: {k: (mv.value if (mv := self.lines.get(p, {}).get(k)) else None) for k in SYNONYMS} for p in self.periods}


def _to_decimal(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    if isinstance(v, int | float):
        return Decimal(str(v))
    s = str(v).replace(",", "").replace("$", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return -d if neg else d


def _match_line(label: str) -> tuple[str | None, float]:
    norm = re.sub(r"[^a-z0-9&$ ]", " ", label.lower()).strip()
    norm = re.sub(r"\s+", " ", norm)
    best: tuple[str | None, float] = (None, 0.0)
    for key, syns in SYNONYMS.items():
        for syn in syns:
            if norm == syn:
                return key, 1.0
            if norm.startswith(syn) and len(syn) >= 4 and best[1] < 0.8:
                best = (key, 0.8)
    return best


def map_income_statement(chunks: list[ParsedChunk], sheet_title_hint: str = "income statement") -> StatementMap | None:
    rows = [
        (i, c) for i, c in enumerate(chunks) if c.kind == "sheet_row" and sheet_title_hint in c.locator.get("sheet", "").lower()
    ]
    if not rows:
        return None
    sheet = rows[0][1].locator["sheet"]
    header: list[str] | None = None
    header_row = None
    period_cols: dict[int, str] = {}
    for _, c in rows:
        values = c.structured["values"] if c.structured else []
        found = {ci: v.strip().upper().replace(" ", "") for ci, v in enumerate(values) if _PERIOD.match(v.strip())}
        if len(found) >= 2:
            header = values
            header_row = c.locator["row"]
            period_cols = {ci: (v if v.startswith("FY") else f"FY{v}") for ci, v in found.items()}
            break
    if header is None:
        return None
    periods = [period_cols[ci] for ci in sorted(period_cols)]
    smap = StatementMap(sheet=sheet, periods=periods, header_row=header_row)
    for p in periods:
        smap.lines[p] = {}
    from openpyxl.utils import get_column_letter

    for idx, c in rows:
        if c.locator["row"] <= (header_row or 0):
            continue
        values = c.structured["values"] if c.structured else []
        label = values[0] if values else ""
        key, conf = _match_line(label)
        if key is None:
            smap.unmapped_rows.append({"row": c.locator["row"], "label": label})
            continue
        for ci, period in period_cols.items():
            if ci >= len(values):
                continue
            raw = values[ci]
            cell = f"{get_column_letter(ci + 1)}{c.locator['row']}"
            cell_raw = (c.structured or {}).get("cells", {}).get(cell, raw)
            d = _to_decimal(cell_raw)
            if d is None:
                continue
            if key in smap.lines[period] and smap.lines[period][key].confidence >= conf:
                continue
            smap.lines[period][key] = MappedValue(d, str(raw), cell, sheet, c.locator["row"], idx, conf)
    return smap
