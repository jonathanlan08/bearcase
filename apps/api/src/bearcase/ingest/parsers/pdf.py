"""PDF text extraction with PyMuPDF. Text and block positions only; no JavaScript, no forms."""

from __future__ import annotations

import pymupdf

from bearcase.ingest.parsers.common import ParsedChunk, ParseError, ParseResult


def parse_pdf(data: bytes, max_pages: int = 300) -> ParseResult:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ParseError(f"Could not open PDF: {exc}") from exc
    if doc.is_encrypted:
        raise ParseError("Encrypted PDFs are not accepted.")
    if doc.page_count > max_pages:
        raise ParseError(f"PDF has {doc.page_count} pages; the limit is {max_pages}.")
    chunks: list[ParsedChunk] = []
    texts: list[str] = []
    for page_index in range(doc.page_count):
        page = doc[page_index]
        blocks = page.get_text("blocks")
        para_no = 0
        for block in blocks:
            x0, y0, x1, y1, text, _bno, btype = block[:7]
            if btype != 0:
                continue
            text = " ".join(text.split())
            if len(text) < 3:
                continue
            para_no += 1
            chunks.append(
                ParsedChunk(
                    kind="page_text",
                    locator={
                        "page": page_index + 1,
                        "paragraph": para_no,
                        "bbox": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
                    },
                    text=text,
                )
            )
            texts.append(text)
    return ParseResult(
        chunks=chunks,
        page_count=doc.page_count,
        full_text="\n".join(texts),
        meta={"producer": doc.metadata.get("producer", "") if doc.metadata else ""},
    )
