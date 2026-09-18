"""Builds a landscape, tabular PDF export of the Expenses list - the same
rows and columns the user is looking at on screen (whatever filters are
active, whatever columns aren't hidden via the Columns picker), not a fixed
report. Uses reportlab's platypus Table/SimpleDocTemplate rather than the
manual canvas approach in claim_pdf_service - a plain paginated table with a
repeated header is exactly what Table(repeatRows=1) inside a doc.build() is
for, and it's far less code than hand-rolling page breaks.
"""
import datetime as dt
from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from app.services.pdf_number_format import format_inr
from app.services.pdf_table_helpers import build_styled_table, build_footer_row
from app.services.payment_status_service import get_paid_amount

# key -> (header label, relative column width unit)
COLUMN_DEFS = {
    "expense_number": ("Expense #", 2.6),
    "expense_date": ("Date", 2.0),
    "source_type": ("Source", 2.2),
    "payee": ("Vendor / Employee / Supplier", 3.6),
    "bill_number": ("Voucher / Bill No", 2.6),
    "project_id": ("Project", 2.8),
    "category_id": ("Head", 2.6),
    "sub_category_id": ("Sub-Head", 2.6),
    "base_amount": ("Base", 2.2),
    "gst_amount": ("GST", 2.0),
    "other_amount": ("Other", 2.0),
    "total_amount": ("Amount", 2.4),
    "paid_amount": ("Paid", 2.2),
    "balance_due": ("Balance", 2.2),
    "description": ("Description", 4.5),
    "payment_status": ("Payment", 2.4),
    "status": ("Status", 2.0),
    "is_verified": ("Verified", 1.8),
}
# Always shown, regardless of what the caller asks for - mirrors the
# frontend's sticky-left expense_number/expense_date columns.
MANDATORY_COLUMNS = ["expense_number", "expense_date"]
DEFAULT_COLUMNS = [
    "expense_number", "expense_date", "source_type", "payee", "project_id", "category_id",
    "total_amount", "paid_amount", "balance_due", "payment_status", "status",
]
MONEY_COLUMNS = {"base_amount", "gst_amount", "other_amount", "total_amount", "paid_amount", "balance_due"}


def _money(v) -> str:
    return format_inr(v)


def _payee(e) -> str:
    if e.source_type == "INVOICE":
        return e.vendor.vendor_name if e.vendor else "-"
    if e.source_type == "EMPLOYEE_CLAIM":
        return e.employee.employee_name if e.employee else "-"
    return e.supplier_name or "-"


def _cell(key: str, e, paid_by_id: dict, cell_style) -> str:
    if key == "expense_number":
        return e.expense_number
    if key == "expense_date":
        return str(e.expense_date)
    if key == "source_type":
        return Paragraph((e.source_type or "").replace("_", " "), cell_style)
    if key == "payee":
        return Paragraph(_payee(e), cell_style)
    if key == "bill_number":
        return Paragraph(e.bill_number or "-", cell_style)
    if key == "project_id":
        return Paragraph(e.project.name if e.project else "-", cell_style)
    if key == "category_id":
        return Paragraph(e.category.name if e.category else "-", cell_style)
    if key == "sub_category_id":
        return Paragraph(e.sub_category.name if e.sub_category else "-", cell_style)
    if key == "base_amount":
        return _money(e.base_amount)
    if key == "gst_amount":
        return _money(e.gst_amount)
    if key == "other_amount":
        return _money(e.other_amount)
    if key == "total_amount":
        return _money(e.total_amount)
    if key == "paid_amount":
        return _money(paid_by_id.get(e.id, 0))
    if key == "balance_due":
        return _money(e.total_amount - paid_by_id.get(e.id, 0))
    if key == "description":
        return Paragraph(e.description or "-", cell_style)
    if key == "payment_status":
        return Paragraph((e.payment_status or "").replace("_", " "), cell_style)
    if key == "status":
        return Paragraph(e.status or "-", cell_style)
    if key == "is_verified":
        return "Yes" if e.is_verified else "-"
    return "-"


def build_expenses_pdf(db, rows: list, columns: list[str] | None, filters_desc: str, summary: dict, generated_by: str) -> bytes:
    requested = [c for c in (columns or []) if c in COLUMN_DEFS]
    cols = list(dict.fromkeys(MANDATORY_COLUMNS + (requested or DEFAULT_COLUMNS)))

    needs_paid = any(c in ("paid_amount", "balance_due") for c in cols)
    paid_by_id = {e.id: get_paid_amount(db, e.id) for e in rows} if needs_paid else {}

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=1 * cm, rightMargin=1 * cm, topMargin=1.2 * cm, bottomMargin=1.2 * cm,
    )
    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle("cell", parent=styles["Normal"], fontSize=7, leading=9)
    meta_style = ParagraphStyle("meta", parent=styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#475569"))

    elements = [
        Paragraph("Expenses", ParagraphStyle("title", parent=styles["Heading1"], fontSize=16)),
    ]
    if filters_desc:
        elements.append(Paragraph(filters_desc, meta_style))
    elements.append(Paragraph(
        f"Generated {dt.datetime.utcnow().strftime('%d-%b-%Y %H:%M')} UTC by {generated_by}", meta_style,
    ))
    elements.append(Spacer(1, 10))

    header_style = ParagraphStyle("colhead", parent=styles["Normal"], fontSize=7, leading=9, textColor=colors.white, fontName="Helvetica-Bold")
    header_row = [Paragraph(COLUMN_DEFS[c][0], header_style) for c in cols]
    data_rows = [[_cell(c, e, paid_by_id, cell_style) for c in cols] for e in rows]

    money_col_indexes = [i for i, key in enumerate(cols) if key in MONEY_COLUMNS]
    col_units = [COLUMN_DEFS[c][1] for c in cols]
    footer_row = build_footer_row(cols, f"{summary['count']} Expense(s)", summary, cell_style) if summary else None
    table = build_styled_table(header_row, data_rows, col_units, money_col_indexes, footer_row)
    elements.append(table)

    doc.build(elements)
    return buf.getvalue()
