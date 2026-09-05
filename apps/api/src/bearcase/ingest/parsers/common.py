from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedChunk:
    kind: str  # page_text | sheet_row | sheet_cell | csv_row | csv_aggregate
    locator: dict[str, Any]
    text: str
    structured: dict[str, Any] | None = None


@dataclass
class ParseResult:
    chunks: list[ParsedChunk]
    page_count: int | None = None
    sheet_count: int | None = None
    row_count: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    full_text: str = ""


class ParseError(ValueError):
    pass
