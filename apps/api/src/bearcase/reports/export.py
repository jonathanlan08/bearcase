"""Markdown and PDF export of a stored report."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from bearcase.models import Report


def _cite(st: dict[str, Any]) -> str:
    refs = [f"E:{e[:8]}" for e in st.get("evidence_ids", [])] + [f"M:{m[:8]}" for m in st.get("metric_ids", [])]
    return f" [{', '.join(refs)}]" if refs else ""


def to_markdown(report: Report, company: str) -> str:
    lines = [
        f"# Red-team review: {company}",
        "",
        f"Outcome: **{report.outcome.value.replace('_', ' ')}**  ",
        f"Report v{report.version_no} · {report.status.value} · provider {report.provider}/{report.model} · prompt {report.prompt_version} · schema {report.schema_version} · engine {report.engine_version}",
        "",
        "> Fictional demonstration data. BearCase does not provide financial, legal, tax, or investment advice.",
        "",
    ]
    for s in report.sections:
        lines.append(f"## {s['title']}")
        lines.append("")
        for st in s.get("statements", []):
            lines.append(f"- {st['text']}{_cite(st)}")
        table = s.get("table") or {}
        if table.get("rows"):
            cols = table["columns"]
            lines.append("")
            lines.append("| " + " | ".join(cols) + " |")
            lines.append("|" + "---|" * len(cols))
            for r in table["rows"]:
                lines.append("| " + " | ".join(str(c).replace("|", "/") for c in r["cells"]) + " |")
        lines.append("")
    return "\n".join(lines)


def to_pdf(report: Report, company: str) -> bytes:
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=18, leading=22)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12.5, leading=15, spaceBefore=10)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.5, leading=12.5)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=colors.HexColor("#666666"))
    story: list[Any] = [
        Paragraph(f"Red-team review: {company}", h1),
        Paragraph(f"Outcome: {report.outcome.value.replace('_', ' ')} · v{report.version_no} · {report.status.value}", body),
        Paragraph(
            f"Provider {report.provider}/{report.model} · prompt {report.prompt_version} · schema {report.schema_version} · engine {report.engine_version}",
            small,
        ),
        Paragraph("Fictional demonstration data. BearCase does not provide financial, legal, tax, or investment advice.", small),
        Spacer(1, 8),
    ]
    for s in report.sections:
        story.append(Paragraph(s["title"], h2))
        for st in s.get("statements", []):
            story.append(Paragraph(f"• {st['text']}<font size=7 color='#666666'>{_cite(st)}</font>", body))
        table = s.get("table") or {}
        if table.get("rows"):
            data = [table["columns"]] + [[Paragraph(str(c)[:400], small) for c in r["cells"]] for r in table["rows"][:80]]
            t = Table(data, repeatRows=1, colWidths=[(6.7 * inch) / len(table["columns"])] * len(table["columns"]))
            t.setStyle(
                TableStyle(
                    [
                        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
                        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ]
                )
            )
            story.append(t)
        story.append(Spacer(1, 6))
    buf = BytesIO()
    SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.8 * inch,
        title=f"BearCase report {company}",
    ).build(story)
    return buf.getvalue()
