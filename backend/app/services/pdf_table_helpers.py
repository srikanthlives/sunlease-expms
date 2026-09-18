"""Shared table-styling helper for the list-export PDF services
(expense/invoice/payment/claims_list/recurring_expense/receivables). A
subtotal row, when given, is appended as a bold, shaded row inside the
table itself - not a separate line of text below it - so it reads as part
of the list rather than a disconnected summary."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.platypus import Table, TableStyle


def build_styled_table(header_row, data_rows, col_units, money_col_indexes, footer_row=None):
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
    return table


def build_footer_row(cols: list[str], count_label: str, summary: dict, cell_style, key_aliases: dict | None = None):
    """One cell per column in `cols`: the count label in the first column,
    a formatted total wherever `summary` has a value for that column's key
    (optionally remapped via `key_aliases`, e.g. a "tax" column summarized
    under a "tax_amount" summary key), blank everywhere else."""
    from app.services.pdf_number_format import format_inr
    aliases = key_aliases or {}
    row = []
    for i, key in enumerate(cols):
        summary_key = aliases.get(key, key)
        if i == 0:
            row.append(count_label)
        elif summary_key in summary:
            row.append(format_inr(summary[summary_key]))
        else:
            row.append("")
    return row
