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
_YEAR = re.compile(r"(20\d{2})")
# A statement header that states its scale: "(USD in thousands)", "$000s", "in millions". Applied to every
# mapped value; the raw cell text is kept beside the scaled value so a reviewer sees both.
_SCALE = re.compile(r"in\s+thousands|(?<![\d,.])\$?\s?000'?s?\b|\bthousands\b|in\s+millions|\bmillions\b|\$mm\b|\$m\b", re.I)
_MILLIONS = re.compile(r"million|\$mm\b|\$m\b", re.I)


def detect_scale(text: str) -> int:
    """1, 1_000, or 1_000_000 from a title such as "Income Statement (USD in thousands)"."""
    m = _SCALE.search(text)
    if not m:
        return 1
    return 1_000_000 if _MILLIONS.search(m.group(0)) else 1_000


def period_year(label: str) -> int | None:
    m = _YEAR.search(label)
    return int(m.group(1)) if m else None


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
    scale: int = 1  # multiplier stated by the sheet (thousands, millions); values are already multiplied
    # Line keys whose value was assembled from several component rows because no total row exists; a
    # reviewer must confirm the sum. {line_key: [row labels]}
    ambiguous: dict[str, list[str]] = field(default_factory=dict)

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


# Sheet titles that name the same statement. The classifier accepts any of these, so the mapper must too; a
# workbook whose income statement is on a sheet called "P&L" otherwise produced no statement at all.
SHEET_ALIASES: dict[str, tuple[str, ...]] = {
    "income statement": ("income statement", "profit and loss", "profit & loss", "p&l", "p & l"),
}


def _sheet_matches(title: str, hint: str) -> bool:
    norm = re.sub(r"\s+", " ", title.lower()).strip()
    return any(alias in norm for alias in SHEET_ALIASES.get(hint, (hint,)))


def map_income_statement(chunks: list[ParsedChunk], sheet_title_hint: str = "income statement") -> StatementMap | None:
    """Map the first sheet whose title names the statement and whose rows carry period columns. Rows from
    different sheets are never combined: a workbook with both a "P&L" and a "P&L (prior year)" sheet maps one."""
    by_sheet: dict[str, list[tuple[int, ParsedChunk]]] = {}
    for i, c in enumerate(chunks):
        if c.kind == "sheet_row" and _sheet_matches(c.locator.get("sheet", ""), sheet_title_hint):
            by_sheet.setdefault(c.locator["sheet"], []).append((i, c))
    for sheet, rows in by_sheet.items():
        smap = _map_sheet(sheet, rows)
        if smap is not None:
            return smap
    return None


def _map_sheet(sheet: str, rows: list[tuple[int, ParsedChunk]]) -> StatementMap | None:
    header: list[str] | None = None
    header_row = None
    period_cols: dict[int, str] = {}
    scale = 1
    for _, c in rows:
        values = c.structured["values"] if c.structured else []
        found = {ci: v.strip().upper().replace(" ", "") for ci, v in enumerate(values) if _PERIOD.match(v.strip())}
        if len(found) >= 2:
            header = values
            header_row = c.locator["row"]
            period_cols = {ci: (v if v.startswith("FY") else f"FY{v}") for ci, v in found.items()}
            break
        # rows above the header are titles: "Income Statement (USD in thousands)"
        scale = max(scale, detect_scale(" ".join(v for v in values if v)))
    if header is None:
        return None
    scale = max(scale, detect_scale(sheet))
    # Columns keep whatever order the seller chose; the statement is always oldest -> newest, because every
    # cross-period calculation (growth, CAGR) assumes that. Two columns naming the same year are rejected.
    labelled = sorted(period_cols.items(), key=lambda kv: (period_year(kv[1]) or 0, kv[0]))
    periods = [label for _, label in labelled]
    if len(set(periods)) != len(periods):
        return None
    smap = StatementMap(sheet=sheet, periods=periods, header_row=header_row, scale=scale)
    for p in periods:
        smap.lines[p] = {}
    from openpyxl.utils import get_column_letter

    # Every row that matches a line, per period, so components ("Revenue - service", "Revenue - installation")
    # can be resolved after the whole sheet is read instead of keeping whichever came first.
    candidates: dict[tuple[str, str], list[tuple[MappedValue, str]]] = {}
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
            mv = MappedValue(d * scale, str(raw), cell, sheet, c.locator["row"], idx, conf)
            candidates.setdefault((period, key), []).append((mv, label.strip()))
    for (period, key), found_rows in candidates.items():
        exact = [mv for mv, _ in found_rows if mv.confidence >= 1.0]
        if exact:
            smap.lines[period][key] = exact[0]
            continue
        if len(found_rows) == 1:
            smap.lines[period][key] = found_rows[0][0]
            continue
        # Several partial matches and no total row: the line is the sum of its components, flagged for review.
        first = found_rows[0][0]
        total = sum((mv.value for mv, _ in found_rows), Decimal(0))
        labels = [lbl for _, lbl in found_rows]
        smap.lines[period][key] = MappedValue(
            total, " + ".join(mv.raw for mv, _ in found_rows), first.cell, sheet, first.row, first.chunk_index, 0.6
        )
        smap.ambiguous.setdefault(key, labels)
    return smap
