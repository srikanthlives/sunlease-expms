"""Builds a landscape, tabular PDF export of the Invoices list - same rows
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
    "invoice_number": ("Invoice #", 2.6),
    "vendor_id": ("Vendor", 3.2),
    "invoice_date": ("Date", 2.0),
    "due_date": ("Due Date", 2.0),
    "project_id": ("Project", 2.8),
    "category_id": ("Head", 2.6),
    "sub_category_id": ("Sub-Head", 2.6),
    "description": ("Description", 4.0),
    "taxable_amount": ("Taxable", 2.2),
    "tax": ("Tax", 2.0),
    "total_amount": ("Amount", 2.2),
    "status": ("Status", 2.0),
    "is_verified": ("Verified", 1.8),
}
MANDATORY_COLUMNS = ["invoice_number", "invoice_date"]
DEFAULT_COLUMNS = [
    "invoice_number", "vendor_id", "invoice_date", "due_date", "project_id",
    "category_id", "taxable_amount", "tax", "total_amount", "status",
]
MONEY_COLUMNS = {"taxable_amount", "tax", "total_amount"}


def _money(v) -> str:
    return f"{float(v or 0):,.2f}"


def _cell(key: str, inv, cell_style) -> str:
    if key == "invoice_number":
        return inv.invoice_number
    if key == "vendor_id":
        return Paragraph(inv.vendor.vendor_name if inv.vendor else "-", cell_style)
    if key == "invoice_date":
        return str(inv.invoice_date)
    if key == "due_date":
        return str(inv.due_date) if inv.due_date else "-"
    if key == "project_id":
        return Paragraph(inv.project.name if inv.project else "-", cell_style)
    if key == "category_id":
        return Paragraph(inv.expense.category.name if inv.expense and inv.expense.category else "-", cell_style)
    if key == "sub_category_id":
        return Paragraph(inv.expense.sub_category.name if inv.expense and inv.expense.sub_category else "-", cell_style)
    if key == "description":
        return Paragraph(inv.description or "-", cell_style)
    if key == "taxable_amount":
        return _money(inv.taxable_amount)
    if key == "tax":
        return _money(inv.cgst + inv.sgst + inv.igst + inv.other_tax)
    if key == "total_amount":
        return _money(inv.total_amount)
    if key == "status":
        return Paragraph(inv.status or "-", cell_style)
    if key == "is_verified":
        return "Yes" if (inv.expense and inv.expense.is_verified) else "-"
    return "-"


def build_invoices_pdf(rows: list, columns: list[str] | None, filters_desc: str, summary: dict, generated_by: str) -> bytes:
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

    elements = [Paragraph("Supplier Invoices", ParagraphStyle("title", parent=styles["Heading1"], fontSize=16))]
    if filters_desc:
        elements.append(Paragraph(filters_desc, meta_style))
    elements.append(Paragraph(f"Generated {dt.datetime.utcnow().strftime('%d-%b-%Y %H:%M')} UTC by {generated_by}", meta_style))
    elements.append(Spacer(1, 10))

    header_style = ParagraphStyle("colhead", parent=styles["Normal"], fontSize=7, leading=9, textColor=colors.white, fontName="Helvetica-Bold")
    header_row = [Paragraph(COLUMN_DEFS[c][0], header_style) for c in cols]
    data = [header_row] + [[_cell(c, inv, cell_style) for c in cols] for inv in rows]

    total_units = sum(COLUMN_DEFS[c][1] for c in cols)
    avail_width = landscape(A4)[0] - 2 * cm
    col_widths = [avail_width * (COLUMN_DEFS[c][1] / total_units) for c in cols]

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
            f"<b>{summary['count']} invoice(s)</b> &nbsp;&nbsp; "
            f"Taxable: {_money(summary['taxable_amount'])} &nbsp;&nbsp; "
            f"Tax: {_money(summary['tax_amount'])} &nbsp;&nbsp; "
            f"Total: {_money(summary['total_amount'])}",
            meta_style,
        ))

    doc.build(elements)
    return buf.getvalue()
