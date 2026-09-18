"""Builds a landscape, tabular PDF export of the Employee Claims LIST view -
same rows and columns the user is looking at on screen. Mirrors
expense_pdf_service.py (reportlab platypus Table/SimpleDocTemplate). Distinct
from claim_pdf_service.py, which renders a single claim's detail + its
attachments, not a list."""
import datetime as dt
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

# key -> (header label, relative column width unit)
COLUMN_DEFS = {
    "employee_id": ("Employee", 2.8),
    "category_id": ("Overall Head", 2.6),
    "description": ("Description", 4.0),
    "claim_date": ("Date", 2.0),
    "total_amount": ("Amount", 2.2),
    "status": ("Status", 2.2),
}
MANDATORY_COLUMNS = ["claim_number"]
DEFAULT_COLUMNS = ["claim_number", "employee_id", "category_id", "claim_date", "total_amount", "status"]
MONEY_COLUMNS = {"total_amount"}
_COLUMN_DEFS_ALL = {**COLUMN_DEFS, "claim_number": ("Claim #", 2.2)}


def _money(v) -> str:
    return f"{float(v or 0):,.2f}"


def _cell(key: str, c, cell_style) -> str:
    if key == "claim_number":
        return c.claim_number
    if key == "employee_id":
        return Paragraph(c.employee.employee_name if c.employee else "-", cell_style)
    if key == "category_id":
        return Paragraph(c.category.name if c.category else "-", cell_style)
    if key == "description":
        return Paragraph(c.description or "-", cell_style)
    if key == "claim_date":
        return str(c.claim_date)
    if key == "total_amount":
        return _money(c.total_amount)
    if key == "status":
        return Paragraph((c.status or "").replace("_", " "), cell_style)
    return "-"


def build_claims_pdf(rows: list, columns: list[str] | None, filters_desc: str, summary: dict, generated_by: str) -> bytes:
    requested = [c for c in (columns or []) if c in COLUMN_DEFS]
    cols = list(dict.fromkeys(MANDATORY_COLUMNS + (requested or DEFAULT_COLUMNS)))

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=1 * cm, rightMargin=1 * cm, topMargin=1.2 * cm, bottomMargin=1.2 * cm,
    )
    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle("cell", parent=styles["Normal"], fontSize=7, leading=9)
    meta_style = ParagraphStyle("meta", parent=styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#475569"))

    elements = [Paragraph("Employee Claims", ParagraphStyle("title", parent=styles["Heading1"], fontSize=16))]
    if filters_desc:
        elements.append(Paragraph(filters_desc, meta_style))
    elements.append(Paragraph(f"Generated {dt.datetime.utcnow().strftime('%d-%b-%Y %H:%M')} UTC by {generated_by}", meta_style))
    elements.append(Spacer(1, 10))

    header_style = ParagraphStyle("colhead", parent=styles["Normal"], fontSize=7, leading=9, textColor=colors.white, fontName="Helvetica-Bold")
    header_row = [Paragraph(_COLUMN_DEFS_ALL[c][0], header_style) for c in cols]
    data = [header_row] + [[_cell(c, claim, cell_style) for c in cols] for claim in rows]

    total_units = sum(_COLUMN_DEFS_ALL[c][1] for c in cols)
    avail_width = landscape(A4)[0] - 2 * cm
    col_widths = [avail_width * (_COLUMN_DEFS_ALL[c][1] / total_units) for c in cols]

    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e5e5")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for i, key in enumerate(cols):
        if key in MONEY_COLUMNS:
            style.append(("ALIGN", (i, 1), (i, -1), "RIGHT"))
    table.setStyle(TableStyle(style))
    elements.append(table)

    if summary:
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(
            f"<b>{summary['count']} claim(s)</b> &nbsp;&nbsp; Total: {_money(summary['total_amount'])}",
            meta_style,
        ))

    doc.build(elements)
    return buf.getvalue()
