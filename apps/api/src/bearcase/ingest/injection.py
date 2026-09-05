"""Detects instruction-like text inside documents. Detection never changes behavior; it only
labels evidence so reviewers can see it and evaluations can prove it stayed inert."""

from __future__ import annotations

import re

INSTRUCTION_PATTERNS = [
    re.compile(r"ignore (all |any )?(previous|prior|above) instructions", re.I),
    re.compile(r"mark (every|all) (financial )?claims? as supported", re.I),
    re.compile(r"change the purchase price to", re.I),
    re.compile(r"\b(system|assistant) (prompt|instruction)s?\b", re.I),
    re.compile(r"\byou are (now )?(an? |the )?(ai|assistant|model)\b", re.I),
    re.compile(r"disregard (the )?(above|previous)", re.I),
    re.compile(r"note to (automated|ai) readers", re.I),
]


def contains_instruction_text(text: str) -> bool:
    return any(p.search(text) for p in INSTRUCTION_PATTERNS)


def instruction_spans(text: str) -> list[str]:
    hits: list[str] = []
    for p in INSTRUCTION_PATTERNS:
        for m in p.finditer(text):
            hits.append(m.group(0))
    return hits
