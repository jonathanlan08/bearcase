"""Aggregate a customer-revenue CSV into concentration and recurring-revenue evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from bearcase.ingest.parsers.common import ParsedChunk

RECURRING_TYPES = {"maintenance_agreement", "maintenance", "recurring", "subscription", "service_agreement"}


@dataclass
class CustomerAggregate:
    revenue_column: str
    total: Decimal
    recurring: Decimal
    customer_totals: list[tuple[str, Decimal, list[int]]]  # name, total, chunk indexes
    recurring_chunks: list[int] = field(default_factory=list)
    customer_count: int = 0

    @property
    def top(self) -> tuple[str, Decimal, list[int]] | None:
        return self.customer_totals[0] if self.customer_totals else None


def aggregate_customers(chunks: list[ParsedChunk], period_hint: str = "fy2024") -> CustomerAggregate | None:
    rows = [(i, c) for i, c in enumerate(chunks) if c.kind == "csv_row" and c.structured]
    if not rows:
        return None
    header = rows[0][1].structured["header"]  # type: ignore[index]
    rev_col = next((h for h in header if period_hint in h.lower() and "revenue" in h.lower()), None) or next(
        (h for h in header if "revenue" in h.lower() and "type" not in h.lower()), None
    )
    name_col = next((h for h in header if "customer_name" in h.lower() or h.lower() == "customer"), None)
    type_col = next((h for h in header if "revenue_type" in h.lower() or "type" in h.lower()), None)
    if not rev_col or not name_col:
        return None
    totals: dict[str, Decimal] = {}
    idxs: dict[str, list[int]] = {}
    total = Decimal(0)
    recurring = Decimal(0)
    recurring_chunks: list[int] = []
    for i, c in rows:
        rec = c.structured["record"]  # type: ignore[index]
        try:
            amt = Decimal(rec[rev_col].replace(",", "").replace("$", "") or "0")
        except Exception:
            continue
        name = rec[name_col]
        totals[name] = totals.get(name, Decimal(0)) + amt
        idxs.setdefault(name, []).append(i)
        total += amt
        if type_col and rec.get(type_col, "").strip().lower() in RECURRING_TYPES:
            recurring += amt
            recurring_chunks.append(i)
    ordered = sorted(((n, t, idxs[n]) for n, t in totals.items()), key=lambda x: x[1], reverse=True)
    return CustomerAggregate(rev_col, total, recurring, ordered, recurring_chunks, len(totals))
