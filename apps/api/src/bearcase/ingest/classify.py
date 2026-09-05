"""Rule-based document classification. The AI provider may refine an UNKNOWN result."""

from __future__ import annotations

import re
from dataclasses import dataclass

from bearcase.ingest.parsers.common import ParseResult


@dataclass(frozen=True)
class Classification:
    doc_type: str
    confidence: float
    rationale: str


_RULES: list[tuple[str, re.Pattern[str], float]] = [
    ("cim", re.compile(r"confidential information memorandum|investment memorandum|\bCIM\b", re.I), 0.95),
    ("debt_term_sheet", re.compile(r"term sheet|senior (secured )?term loan|amortization:|financial covenants", re.I), 0.92),
    (
        "customer_contract",
        re.compile(r"(master )?services? agreement|termination for convenience|initial term of this agreement", re.I),
        0.9,
    ),
]


def classify(extension: str, display_name: str, parsed: ParseResult) -> Classification:
    name = display_name.lower()
    text = parsed.full_text[:20000]
    if extension == "csv":
        header = {h.lower() for h in parsed.meta.get("header", [])}
        if {"customer_name", "revenue_type"} & header and any("revenue" in h for h in header):
            return Classification("customer_revenue", 0.96, "CSV header contains customer and revenue columns")
        return Classification("other", 0.5, "CSV without recognizable customer-revenue columns")
    if extension == "xlsx":
        sheets = {s["title"].lower() for s in parsed.meta.get("sheets", [])}
        if any("income statement" in s or "profit" in s or "p&l" in s for s in sheets):
            return Classification("financial_statements", 0.95, "Workbook contains an income statement sheet")
        if {"assumptions", "projections"} & sheets or "model" in name:
            return Classification("acquisition_model", 0.9, "Workbook contains assumptions/projections sheets")
        return Classification("other", 0.5, "Workbook without recognizable statement or model sheets")
    if extension == "pdf":
        if "cim" in name or "memorandum" in name:
            return Classification("cim", 0.9, "Filename indicates a CIM")
        if "term" in name and "sheet" in name:
            return Classification("debt_term_sheet", 0.9, "Filename indicates a term sheet")
        if "contract" in name or "agreement" in name:
            return Classification("customer_contract", 0.85, "Filename indicates a contract")
        for doc_type, pattern, conf in _RULES:
            if pattern.search(text):
                return Classification(doc_type, conf, f"Content matched '{pattern.pattern[:40]}'")
        return Classification("unknown", 0.3, "No classification rule matched")
    return Classification("unknown", 0.0, "Unsupported extension")
