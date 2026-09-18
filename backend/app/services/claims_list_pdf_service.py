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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from app.services.pdf_number_format import format_inr
from app.services.pdf_table_helpers import build_styled_table, build_footer_row

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
    return format_inr(v)


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
    data_rows = [[_cell(c, claim, cell_style) for c in cols] for claim in rows]

    money_col_indexes = [i for i, key in enumerate(cols) if key in MONEY_COLUMNS]
    col_units = [_COLUMN_DEFS_ALL[c][1] for c in cols]
    footer_row = build_footer_row(cols, f"{summary['count']} Claim(s)", summary, cell_style) if summary else None
    table = build_styled_table(header_row, data_rows, col_units, money_col_indexes, footer_row)
    elements.append(table)

    doc.build(elements)
    return buf.getvalue()
