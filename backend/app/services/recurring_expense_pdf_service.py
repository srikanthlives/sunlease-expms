"""Builds a landscape, tabular PDF export of the Recurring Expenses template
list - same rows and columns the user is looking at on screen. Mirrors
expense_pdf_service.py (reportlab platypus Table/SimpleDocTemplate)."""
import datetime as dt
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

# key -> (header label, relative column width unit)
COLUMN_DEFS = {
    "frequency": ("Frequency", 1.8),
    "amount_type": ("Amount", 2.0),
    "payee": ("Payee", 2.8),
    "project_id": ("Project", 2.4),
    "category_id": ("Head", 2.4),
    "sub_category_id": ("Sub-Head", 2.4),
    "description": ("Description", 3.6),
    "next_occurrence_date": ("Next Bill Date", 2.0),
    "is_active": ("Status", 1.6),
    "is_verified": ("Verified", 1.6),
}
MANDATORY_COLUMNS = ["name"]
DEFAULT_COLUMNS = ["name", "frequency", "amount_type", "payee", "project_id", "category_id", "next_occurrence_date", "is_active"]
_COLUMN_DEFS_ALL = {**COLUMN_DEFS, "name": ("Name", 2.6)}

FREQUENCY_LABELS = {
    "WEEKLY": "Weekly", "BIWEEKLY": "Bi-Weekly", "MONTHLY": "Monthly",
    "QUARTERLY": "Quarterly", "HALF_YEARLY": "Half-Yearly", "ANNUALLY": "Annually",
}


def _money(v) -> str:
    return f"{float(v or 0):,.2f}"


def _payee(tpl) -> str:
    if tpl.payee_type == "VENDOR":
        return tpl.vendor.vendor_name if tpl.vendor else "-"
    return tpl.supplier_name or "-"


def _cell(key: str, tpl, cell_style) -> str:
    if key == "name":
        return tpl.name
    if key == "frequency":
        return FREQUENCY_LABELS.get(tpl.frequency, tpl.frequency)
    if key == "amount_type":
        return _money(tpl.fixed_amount) if tpl.amount_type == "FIXED" else "Open"
    if key == "payee":
        return Paragraph(_payee(tpl), cell_style)
    if key == "project_id":
        return Paragraph(tpl.project.name if tpl.project else "-", cell_style)
    if key == "category_id":
        return Paragraph(tpl.category.name if tpl.category else "-", cell_style)
    if key == "sub_category_id":
        return Paragraph(tpl.sub_category.name if tpl.sub_category else "-", cell_style)
    if key == "description":
        return Paragraph(tpl.description or "-", cell_style)
    if key == "next_occurrence_date":
        return str(tpl.next_occurrence_date)
    if key == "is_active":
        return "ACTIVE" if tpl.is_active else "INACTIVE"
    if key == "is_verified":
        return "Yes" if tpl.is_verified else "-"
    return "-"


def build_recurring_expenses_pdf(rows: list, columns: list[str] | None, filters_desc: str, count: int, generated_by: str) -> bytes:
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

    elements = [Paragraph("Recurring Expenses", ParagraphStyle("title", parent=styles["Heading1"], fontSize=16))]
    if filters_desc:
        elements.append(Paragraph(filters_desc, meta_style))
    elements.append(Paragraph(f"Generated {dt.datetime.utcnow().strftime('%d-%b-%Y %H:%M')} UTC by {generated_by}", meta_style))
    elements.append(Spacer(1, 10))

    header_style = ParagraphStyle("colhead", parent=styles["Normal"], fontSize=7, leading=9, textColor=colors.white, fontName="Helvetica-Bold")
    header_row = [Paragraph(_COLUMN_DEFS_ALL[c][0], header_style) for c in cols]
    data = [header_row] + [[_cell(c, tpl, cell_style) for c in cols] for tpl in rows]

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
    table.setStyle(TableStyle(style))
    elements.append(table)

    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"<b>{count} recurring expense(s)</b>", meta_style))

    doc.build(elements)
    return buf.getvalue()
