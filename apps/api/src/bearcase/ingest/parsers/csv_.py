"""Strict CSV parsing: explicit encoding handling, header required, row limit, per-row schema."""

from __future__ import annotations

import csv
from io import StringIO

from bearcase.ingest.parsers.common import ParsedChunk, ParseError, ParseResult


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ParseError("CSV is not valid UTF-8 or Latin-1 text.")


def _num(v: str) -> float | None:
    s = v.replace(",", "").replace("$", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_csv(data: bytes, max_rows: int = 50000) -> ParseResult:
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(StringIO(text), dialect)
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration as exc:
        raise ParseError("CSV has no header row.") from exc
    if not header or any(not h for h in header):
        raise ParseError("CSV header contains empty column names.")
    chunks: list[ParsedChunk] = []
    texts: list[str] = []
    rows = 0
    for line_no, row in enumerate(reader, start=2):
        if not any(cell.strip() for cell in row):
            continue
        rows += 1
        if rows > max_rows:
            raise ParseError(f"CSV exceeds the {max_rows} row limit.")
        if len(row) != len(header):
            raise ParseError(f"Row {line_no} has {len(row)} columns; expected {len(header)}.")
        record = {h: c.strip() for h, c in zip(header, row, strict=True)}
        numeric = {h: n for h, v in record.items() if (n := _num(v)) is not None}
        row_text = "; ".join(f"{h}={v}" for h, v in record.items() if v)
        chunks.append(
            ParsedChunk(
                kind="csv_row",
                locator={"row": line_no, "record_index": rows},
                text=row_text,
                structured={"record": record, "numeric": numeric, "header": header},
            )
        )
        texts.append(row_text)
    return ParseResult(
        chunks=chunks, row_count=rows, full_text="\n".join(texts), meta={"header": header, "delimiter": dialect.delimiter}
    )
