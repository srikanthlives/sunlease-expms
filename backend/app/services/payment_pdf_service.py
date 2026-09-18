"""Builds a landscape, tabular PDF export of the Payments list - same rows
and columns the user is looking at on screen. Mirrors expense_pdf_service.py
(reportlab platypus Table/SimpleDocTemplate)."""
import datetime as dt
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

# key -> (header label, relative column width unit)
COLUMN_DEFS = {
    "payee": ("Payee", 3.2),
    "account_id": ("Account", 2.6),
    "payment_mode": ("Mode", 1.8),
    "reference_number": ("Reference / UTR", 2.6),
    "amount": ("Amount", 2.2),
    "allocations": ("Allocated To", 3.2),
    "remarks": ("Remarks", 2.6),
    "is_cancelled": ("Status", 1.8),
    "is_verified": ("Verified", 1.8),
}
MANDATORY_COLUMNS = ["payment_number", "payment_date"]
DEFAULT_COLUMNS = ["payment_number", "payment_date", "payee", "account_id", "payment_mode", "amount", "allocations", "is_cancelled"]
MONEY_COLUMNS = {"amount"}
_COLUMN_DEFS_ALL = {**COLUMN_DEFS, "payment_number": ("Payment #", 2.2), "payment_date": ("Date", 2.0)}


def _money(v) -> str:
    return f"{float(v or 0):,.2f}"


def _payee(p) -> str:
    if p.vendor_id:
        return p.vendor.vendor_name if p.vendor else "-"
    if p.employee_id:
        return p.employee.employee_name if p.employee else "-"
    return "Expense"


def _cell(key: str, p, cell_style) -> str:
    if key == "payment_number":
        return p.payment_number
    if key == "payment_date":
        return str(p.payment_date)
    if key == "payee":
        return Paragraph(_payee(p), cell_style)
    if key == "account_id":
        return Paragraph(p.account.account_name if p.account else "-", cell_style)
    if key == "payment_mode":
        return p.payment_mode
    if key == "reference_number":
        return Paragraph(p.reference_number or "-", cell_style)
    if key == "amount":
        return _money(p.amount)
    if key == "allocations":
        text = ", ".join(a.expense.expense_number if a.expense else f"#{a.expense_id}" for a in p.allocations)
        return Paragraph(text or "-", cell_style)
    if key == "remarks":
        return Paragraph(p.remarks or "-", cell_style)
    if key == "is_cancelled":
        return "CANCELLED" if p.is_cancelled else "ACTIVE"
    if key == "is_verified":
        return "Yes" if p.is_verified else "-"
    return "-"


def build_payments_pdf(rows: list, columns: list[str] | None, filters_desc: str, summary: dict, generated_by: str) -> bytes:
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

    elements = [Paragraph("Payments", ParagraphStyle("title", parent=styles["Heading1"], fontSize=16))]
    if filters_desc:
        elements.append(Paragraph(filters_desc, meta_style))
    elements.append(Paragraph(f"Generated {dt.datetime.utcnow().strftime('%d-%b-%Y %H:%M')} UTC by {generated_by}", meta_style))
    elements.append(Spacer(1, 10))

    header_style = ParagraphStyle("colhead", parent=styles["Normal"], fontSize=7, leading=9, textColor=colors.white, fontName="Helvetica-Bold")
    header_row = [Paragraph(_COLUMN_DEFS_ALL[c][0], header_style) for c in cols]
    data = [header_row] + [[_cell(c, p, cell_style) for c in cols] for p in rows]

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
            f"<b>{summary['count']} payment(s)</b> &nbsp;&nbsp; Amount: {_money(summary['amount'])}",
            meta_style,
        ))

    doc.build(elements)
    return buf.getvalue()
