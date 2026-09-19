"""Builds landscape, tabular PDF exports of the three Receivables list
views (Quotations, Receivable Invoices, Payments Received) - same rows and
columns the user is looking at on screen for the active filters. Mirrors
expense_pdf_service.py / invoice_pdf_service.py (reportlab platypus
Table/SimpleDocTemplate). Fixed column sets, unlike the payable-side
exports - these lists have no Columns picker to mirror."""
import datetime as dt
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from app.services.pdf_number_format import format_inr


def _money(v) -> str:
    return format_inr(v)


def _tax(row) -> float:
    return float(row.cgst or 0) + float(row.sgst or 0) + float(row.igst or 0) + float(row.other_tax or 0)


def _doc_shell(title: str, filters_desc: str, generated_by: str):
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=1 * cm, rightMargin=1 * cm, topMargin=1.2 * cm, bottomMargin=1.2 * cm,
    )
    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle("cell", parent=styles["Normal"], fontSize=7, leading=9)
    meta_style = ParagraphStyle("meta", parent=styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#475569"))
    elements = [Paragraph(title, ParagraphStyle("title", parent=styles["Heading1"], fontSize=16))]
    if filters_desc:
        elements.append(Paragraph(filters_desc, meta_style))
    elements.append(Paragraph(f"Generated {dt.datetime.utcnow().strftime('%d-%b-%Y %H:%M')} UTC by {generated_by}", meta_style))
    elements.append(Spacer(1, 10))
    return buf, doc, styles, cell_style, meta_style, elements


def _build_table(elements, header_row, data_rows, col_units, money_col_indexes, footer_row=None):
    """`footer_row`, if given, is appended as a bold, shaded subtotal row at
    the bottom of the table itself - not a separate line of text below it,
    so it reads as part of the list (like the on-screen Table's `footer`
    prop) rather than a disconnected summary."""
    total_units = sum(col_units)
    avail_width = landscape(A4)[0] - 2 * cm
    col_widths = [avail_width * (u / total_units) for u in col_units]
    all_rows = [header_row] + data_rows + ([footer_row] if footer_row else [])
    table = Table(all_rows, colWidths=col_widths, repeatRows=1)
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
    for i in money_col_indexes:
        style.append(("ALIGN", (i, 1), (i, -1), "RIGHT"))
    if footer_row:
        last = len(all_rows) - 1
        style += [
            ("BACKGROUND", (0, last), (-1, last), colors.HexColor("#e2e8f0")),
            ("FONTNAME", (0, last), (-1, last), "Helvetica-Bold"),
            ("LINEABOVE", (0, last), (-1, last), 1, colors.HexColor("#1e293b")),
        ]
    table.setStyle(TableStyle(style))
    elements.append(table)


def build_quotations_pdf(rows: list, filters_desc: str, summary: dict, generated_by: str) -> bytes:
    buf, doc, styles, cell_style, meta_style, elements = _doc_shell("Proforma Invoices", filters_desc, generated_by)
    header_style = ParagraphStyle("colhead", parent=styles["Normal"], fontSize=7, leading=9, textColor=colors.white, fontName="Helvetica-Bold")
    headers = ["Proforma #", "Customer", "Project", "Date", "Valid Until", "Description", "Taxable", "GST", "Amount", "Status", "Invoice"]
    units = [2.2, 2.6, 2.0, 1.6, 1.6, 3.2, 1.8, 1.6, 1.8, 1.6, 2.2]
    header_row = [Paragraph(h, header_style) for h in headers]
    data_rows = []
    for r in rows:
        data_rows.append([
            Paragraph(r.quotation_number, cell_style), Paragraph(r.customer_name, cell_style), Paragraph(r.project.name if r.project else "-", cell_style),
            str(r.quotation_date), str(r.valid_until) if r.valid_until else "-",
            Paragraph(r.description or "-", cell_style),
            _money(r.taxable_amount), _money(_tax(r)), _money(r.total_amount),
            Paragraph((r.status or "").replace("_", " "), cell_style),
            Paragraph(r.receivable_invoice.invoice_number if r.receivable_invoice else "-", cell_style),
        ])
    footer_row = [
        Paragraph(f"{summary['count']} Proforma Invoice(s)", cell_style), "", "", "", "", "",
        _money(summary["taxable_amount"]), _money(summary["tax_amount"]), _money(summary["total_amount"]),
        "", "",
    ]
    _build_table(elements, header_row, data_rows, units, money_col_indexes=[6, 7, 8], footer_row=footer_row)
    doc.build(elements)
    return buf.getvalue()


def build_receivable_invoices_pdf(rows: list, paid_by_id: dict, filters_desc: str, summary: dict, generated_by: str) -> bytes:
    buf, doc, styles, cell_style, meta_style, elements = _doc_shell("Receivable Invoices", filters_desc, generated_by)
    header_style = ParagraphStyle("colhead", parent=styles["Normal"], fontSize=7, leading=9, textColor=colors.white, fontName="Helvetica-Bold")
    headers = ["Invoice #", "Customer", "Project", "Proforma #", "PO Number", "Date", "Due Date", "Description", "Taxable", "GST", "Amount", "Received", "Balance", "Payment", "Status"]
    units = [2.2, 2.4, 1.8, 2.0, 1.8, 1.6, 1.6, 2.8, 1.6, 1.4, 1.6, 1.6, 1.6, 1.6, 1.4]
    header_row = [Paragraph(h, header_style) for h in headers]
    data_rows = []
    for r in rows:
        paid = paid_by_id.get(r.id, 0)
        data_rows.append([
            Paragraph(r.invoice_number, cell_style), Paragraph(r.customer_name, cell_style), Paragraph(r.project.name if r.project else "-", cell_style),
            Paragraph(r.quotation.quotation_number if r.quotation else "-", cell_style), Paragraph((r.po_number or "-").replace("\n", ", "), cell_style),
            str(r.invoice_date), str(r.due_date) if r.due_date else "-",
            Paragraph(r.description or "-", cell_style),
            _money(r.taxable_amount), _money(_tax(r)), _money(r.total_amount),
            _money(paid), _money(float(r.total_amount) - float(paid)),
            Paragraph((r.payment_status or "").replace("_", " "), cell_style),
            Paragraph(r.status or "-", cell_style),
        ])
    footer_row = [
        Paragraph(f"{summary['count']} Invoice(s)", cell_style), "", "", "", "", "", "", "",
        _money(summary["taxable_amount"]), _money(summary["tax_amount"]), _money(summary["total_amount"]),
        _money(summary["paid_amount"]), _money(summary["balance_due"]), "", "",
    ]
    _build_table(elements, header_row, data_rows, units, money_col_indexes=[8, 9, 10, 11, 12], footer_row=footer_row)
    doc.build(elements)
    return buf.getvalue()


def build_receivable_payments_pdf(rows: list, filters_desc: str, summary: dict, generated_by: str) -> bytes:
    buf, doc, styles, cell_style, meta_style, elements = _doc_shell("Payments Received", filters_desc, generated_by)
    header_style = ParagraphStyle("colhead", parent=styles["Normal"], fontSize=7, leading=9, textColor=colors.white, fontName="Helvetica-Bold")
    headers = ["Payment #", "Date", "Account", "Mode", "Reference", "Amount", "Allocated To", "Status"]
    units = [2.2, 1.8, 2.4, 1.6, 2.2, 1.8, 3.2, 1.6]
    header_row = [Paragraph(h, header_style) for h in headers]
    data_rows = []
    for p in rows:
        allocated = ", ".join((a.invoice.invoice_number if a.invoice else f"#{a.receivable_invoice_id}") for a in p.allocations)
        data_rows.append([
            Paragraph(p.payment_number, cell_style), str(p.payment_date), Paragraph(p.account.account_name if p.account else "-", cell_style),
            Paragraph(p.payment_mode, cell_style), Paragraph(p.reference_number or "-", cell_style), _money(p.amount),
            Paragraph(allocated or "-", cell_style), Paragraph("CANCELLED" if p.is_cancelled else "ACTIVE", cell_style),
        ])
    footer_row = [
        Paragraph(f"{summary['count']} Payment(s)", cell_style), "", "", "",
        "", _money(summary["amount"]), "", "",
    ]
    _build_table(elements, header_row, data_rows, units, money_col_indexes=[5], footer_row=footer_row)
    doc.build(elements)
    return buf.getvalue()
