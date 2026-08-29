"""Builds a single downloadable PDF for an employee claim: a summary page
(claim details + every line, mirroring the claim detail screen) followed by
one page per attachment - the overall claim's proof and each line's proof,
in that order. An image attachment becomes a full page with the image
scaled to fit; a PDF attachment (e.g. a scanned bill saved as PDF) has its
own pages merged in directly. Gives an employee (or reviewer) one file that
is the complete record of a claim for their own copy/reimbursement filing.
"""
import datetime as dt
from io import BytesIO

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.models.models import Document, EmployeeClaim
from app.services.storage import get_storage

IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _money(v) -> str:
    return f"Rs. {float(v or 0):,.2f}"


def _build_summary_pdf(claim: EmployeeClaim) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=1.8 * cm, rightMargin=1.8 * cm)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"Employee Claim - {claim.claim_number}", styles["Title"]))
    story.append(Spacer(1, 0.3 * cm))

    employee_name = claim.employee.employee_name if claim.employee else "-"
    project_name = claim.project.name if claim.project else "-"
    category_name = claim.category.name if claim.category else "-"

    meta_rows = [
        ["Employee", employee_name, "Status", claim.status],
        ["Claim Date", str(claim.claim_date), "Project", project_name],
        ["Overall Head", category_name, "Total Amount", _money(claim.total_amount)],
    ]
    meta_table = Table(meta_rows, colWidths=[3.2 * cm, 6 * cm, 3.2 * cm, 4.5 * cm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e5e5")),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.4 * cm))

    if claim.description:
        story.append(Paragraph(f"<b>Description:</b> {claim.description}", styles["Normal"]))
        story.append(Spacer(1, 0.4 * cm))

    if claim.status == "REJECTED" and claim.rejection_reason:
        story.append(Paragraph(f"<b>Rejection reason:</b> {claim.rejection_reason}", styles["Normal"]))
        story.append(Spacer(1, 0.4 * cm))

    if claim.expense_number:
        story.append(Paragraph(f"<b>Recorded as expense:</b> {claim.expense_number}", styles["Normal"]))
        story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("Expense Lines", styles["Heading3"]))
    line_rows = [["#", "Date", "Head", "Sub-Head", "Description", "Amount"]]
    for i, line in enumerate(claim.lines, start=1):
        line_rows.append([
            str(i), str(line.expense_date),
            line.expense_head.name if line.expense_head else "-",
            line.expense_sub_head.name if line.expense_sub_head else "-",
            line.description or "-",
            _money(line.amount),
        ])
    line_rows.append(["", "", "", "", "Total", _money(claim.total_amount)])

    lines_table = Table(line_rows, colWidths=[0.9 * cm, 2.3 * cm, 2.8 * cm, 2.8 * cm, 5.5 * cm, 2.5 * cm], repeatRows=1)
    lines_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e5e5")),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#1e293b")),
    ]))
    story.append(lines_table)
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(f"Generated {dt.datetime.utcnow().strftime('%d-%b-%Y %H:%M')} UTC", styles["Normal"]))

    doc.build(story)
    return buf.getvalue()


def _image_page_pdf(image_bytes: bytes, caption: str) -> bytes | None:
    """One A4 page with the image scaled to fit, captioned. Returns None if
    the image can't be decoded (corrupt/unsupported) rather than failing
    the whole export."""
    try:
        reader = ImageReader(BytesIO(image_bytes))
        img_w, img_h = reader.getSize()

        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        page_w, page_h = A4
        margin = 1.5 * cm
        caption_height = 1 * cm

        c.setFont("Helvetica-Bold", 9)
        c.drawString(margin, page_h - margin + 0.2 * cm, caption[:120])

        max_w = page_w - 2 * margin
        max_h = page_h - 2 * margin - caption_height
        scale = min(max_w / img_w, max_h / img_h)
        draw_w, draw_h = img_w * scale, img_h * scale
        x = (page_w - draw_w) / 2
        y = margin + (max_h - draw_h) / 2

        # The actual pixel decode (not just the header read above) can still
        # fail on a truncated/corrupt file - keep it inside the same guard
        # so a bad attachment degrades to a placeholder page, not a 500.
        c.drawImage(reader, x, y, width=draw_w, height=draw_h, preserveAspectRatio=True, mask="auto")
        c.showPage()
        c.save()
        return buf.getvalue()
    except Exception:
        return None


def _placeholder_page_pdf(caption: str, note: str) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(page_w / 2, page_h / 2 + 20, caption[:120])
    c.setFont("Helvetica", 9)
    c.drawCentredString(page_w / 2, page_h / 2 - 5, note)
    c.showPage()
    c.save()
    return buf.getvalue()


async def build_claim_pdf(db: Session, claim: EmployeeClaim) -> bytes:
    writer = PdfWriter()
    storage = get_storage()

    summary_bytes = _build_summary_pdf(claim)
    for page in PdfReader(BytesIO(summary_bytes)).pages:
        writer.add_page(page)

    line_number_by_id = {line.id: i for i, line in enumerate(claim.lines, start=1)}
    overall_docs = db.query(Document).filter(Document.claim_id == claim.id).order_by(Document.id).all()
    line_ids = list(line_number_by_id.keys())
    line_docs = db.query(Document).filter(Document.claim_line_id.in_(line_ids)).order_by(Document.id).all() if line_ids else []

    attachments = [(d, "Overall Claim Attachment") for d in overall_docs]
    attachments += [(d, f"Line {line_number_by_id[d.claim_line_id]} Attachment") for d in line_docs]

    for doc, label in attachments:
        caption = f"{label}: {doc.original_filename}"
        try:
            content = await storage.retrieve_file(doc.stored_filename)
        except Exception:
            page_bytes = _placeholder_page_pdf(caption, "Could not load this file - it may be missing from storage.")
            for page in PdfReader(BytesIO(page_bytes)).pages:
                writer.add_page(page)
            continue

        if doc.mime_type == "application/pdf":
            try:
                for page in PdfReader(BytesIO(content)).pages:
                    writer.add_page(page)
                continue
            except Exception:
                pass  # fall through to placeholder below
        elif doc.mime_type in IMAGE_MIME_TYPES:
            page_bytes = _image_page_pdf(content, caption)
            if page_bytes:
                for page in PdfReader(BytesIO(page_bytes)).pages:
                    writer.add_page(page)
                continue

        page_bytes = _placeholder_page_pdf(caption, f"'{doc.original_filename}' ({doc.mime_type}) is not previewable in this PDF - open it from the app instead.")
        for page in PdfReader(BytesIO(page_bytes)).pages:
            writer.add_page(page)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()
