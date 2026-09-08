"""The one-page summary: what gets forwarded to a lender or a lawyer. Built from persisted rows with reportlab; no
model. Three findings, the EBITDA bridge in one line, DSCR by scenario, the confidence budget, what was not checked,
and the corrections and seller replies on record."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from fastapi import APIRouter, Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select

from bearcase.api.deps import DbDep, DealDep, UserDep
from bearcase.api.routes.deals import deal_summary
from bearcase.api.routes.financials import statement_mapping
from bearcase.api.routes.questions_seller import latest_replies
from bearcase.audit import record
from bearcase.engine.metrics import format_money, format_multiple
from bearcase.models import ReviewNote, StatementCorrection

router = APIRouter(tags=["reports"])


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=17, leading=21, alignment=0, spaceAfter=2),
        "sub": ParagraphStyle("s", parent=base["Normal"], fontSize=9, textColor=colors.HexColor("#6F7780"), spaceAfter=8),
        "h": ParagraphStyle("h", parent=base["Heading3"], fontSize=11, spaceBefore=8, spaceAfter=3),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=9.5, leading=12.5),
        "small": ParagraphStyle("sm", parent=base["Normal"], fontSize=8, leading=10, textColor=colors.HexColor("#6F7780")),
    }


@router.get("/deals/{deal_id}/summary.pdf")
def summary_pdf(deal: DealDep, db: DbDep, user: UserDep) -> Response:
    s = deal_summary(deal, db)  # the same numbers the overview shows
    mapping: dict[str, Any] = statement_mapping(deal, db)
    cov = mapping["coverage"]
    corrections = db.scalars(select(StatementCorrection).where(StatementCorrection.deal_id == deal.id)).all()
    replies = latest_replies(db, deal.id)
    st = _styles()
    story: list[Any] = [
        Paragraph(f"{deal.company_name}: one-page review summary", st["title"]),
        Paragraph(f"{deal.industry}. Prepared with BearCase from the seller's documents. A citation shows where a figure came from, not that it is true. Not financial, legal, tax, or investment advice.{' Fictional demonstration deal.' if deal.is_demo else ''}", st["sub"]),
    ]
    notes = db.scalars(select(ReviewNote).where(ReviewNote.deal_id == deal.id).order_by(ReviewNote.created_at)).all()
    if notes:
        story.append(Paragraph("The reviewer's memo", st["h"]))
        lab = {"conclusion": "Conclusion", "assumption": "Assumption", "open_question": "Open question"}
        for n in sorted(notes, key=lambda n: ({"conclusion": 0, "assumption": 1, "open_question": 2}.get(n.kind, 3), n.created_at))[:8]:
            story.append(Paragraph(f"<b>{lab.get(n.kind, 'Note')}.</b> {n.text}", st["body"]))
        story.append(Spacer(1, 4))
    story.append(Paragraph("Read these first", st["h"]))
    if not s.top_findings:
        story.append(Paragraph("No findings recorded yet.", st["body"]))
    for i, f in enumerate(s.top_findings[:3], 1):
        story.append(Paragraph(f"<b>{i}. {f.title}</b> ({f.severity}). {f.detail}", st["body"]))
        if f.resolution:
            story.append(Paragraph(f"What would change this: {f.resolution}", st["small"]))
        story.append(Spacer(1, 3))
    story.append(Paragraph("Earnings", st["h"]))
    rows = [["Reported EBITDA", format_money(s.reported_ebitda)], ["Seller's adjusted EBITDA", format_money(s.seller_adjusted_ebitda)], ["Checked adjusted EBITDA", format_money(s.verified_adjusted_ebitda)]]
    t = Table(rows, colWidths=[2.6 * inch, 1.6 * inch], hAlign="LEFT")
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#B9B3A7")), ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold")]))
    story.append(t)
    story.append(Paragraph("Debt coverage by scenario", st["h"]))
    drows = [[sc["name"], format_multiple(sc["dscr"]), "below the lender's minimum" if "covenant_breach" in sc["warnings"] else ("near the minimum" if "covenant_warning" in sc["warnings"] else "covers the loan")] for sc in s.dscr_by_scenario] or [["No scenarios run", "", ""]]
    if s.covenant_threshold is not None:
        drows.append(["Lender's minimum (covenant)", format_multiple(s.covenant_threshold), ""])
    t2 = Table(drows, colWidths=[2.6 * inch, 1.0 * inch, 2.4 * inch], hAlign="LEFT")
    t2.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#B9B3A7"))]))
    story.append(t2)
    c = s.confidence or {}
    story.append(Paragraph("What this rests on", st["h"]))
    story.append(Paragraph(f"Of {c.get('total', 0)} claims, {c.get('decided', 0)} rest on a reviewer's decision, {c.get('rules_only', 0)} on rules alone, {c.get('needs_person', 0)} still need a person, and {c.get('no_evidence', 0)} have no evidence in the documents.", st["body"]))
    story.append(Paragraph(f"Documents read: {cov['documents_ready']}; failed or pending: {cov['documents_failed'] + cov['documents_pending']}; statements not mapped: {cov['statements_unmapped']}; rows nothing matched: {cov['unmapped_rows']}; lines summed from parts: {cov['ambiguous_lines']}; figures marked for review: {cov['metrics_requiring_review']}.", st["small"]))
    story.append(Paragraph("Corrections and the seller's replies", st["h"]))
    if corrections:
        for x in corrections:
            story.append(Paragraph(f"{x.line_key.replace('_', ' ').capitalize()} {x.period_label}: {format_money(x.original_value)} corrected to {format_money(x.corrected_value)}{(' (' + x.note + ')') if x.note else ''}.", st["body"]))
    else:
        story.append(Paragraph("No figures have been corrected by a person.", st["body"]))
    if replies:
        totals: dict[str, int] = {}
        for r in replies.values():
            totals[r["outcome"]] = totals.get(r["outcome"], 0) + 1
        story.append(Paragraph(f"Seller replies recorded: {len(replies)} (answered {totals.get('answered', 0)}, not answered {totals.get('dodged', 0)}, document requested {totals.get('needs_document', 0)}).", st["body"]))
    else:
        story.append(Paragraph("No seller replies recorded yet.", st["body"]))
    missing = s.missing_documents
    if missing:
        story.append(Paragraph("Still missing: " + "; ".join(m.title for m in missing[:5]) + ".", st["small"]))
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.8 * inch, rightMargin=0.8 * inch, topMargin=0.7 * inch, bottomMargin=0.7 * inch, title=f"{deal.company_name} summary")
    doc.build(story)
    record(db, deal_id=deal.id, user_id=user.id, event_type="summary.exported", object_type="deal", object_id=deal.id, summary="Exported the one-page summary (PDF)", payload={"findings": len(s.top_findings[:3])})
    db.commit()
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in deal.company_name).strip("-")[:40]
    return Response(buf.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="bearcase-{slug}-summary.pdf"'})
