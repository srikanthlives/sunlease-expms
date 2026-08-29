"""Builds a single downloadable PDF for an employee claim: a summary page
(claim details + every line, mirroring the claim detail screen) followed by
one page per attachment - the overall claim's proof and each line's proof,
in that order. An image attachment becomes a full page with the image
scaled to fit; a PDF attachment (e.g. a scanned bill saved as PDF) has its
own pages merged in directly. Each expense line with an attachment gets a
clickable "View Proof" link that jumps straight to that attachment's first
page elsewhere in the same document. Gives an employee (or reviewer) one
file that is the complete record of a claim for their own copy/reimbursement
filing.
"""
import datetime as dt
from io import BytesIO

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject, RectangleObject
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from sqlalchemy.orm import Session

from app.models.models import Document, EmployeeClaim
from app.services.storage import get_storage

IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

PAGE_W, PAGE_H = A4
MARGIN_X = 1.8 * cm
MARGIN_TOP = 2 * cm
MARGIN_BOTTOM = 2 * cm

# Expense-lines table column layout (must sum to PAGE_W - 2*MARGIN_X).
COL_WIDTHS = {"num": 0.9 * cm, "date": 2.1 * cm, "head": 2.6 * cm, "subhead": 2.6 * cm, "desc": 5.4 * cm, "amount": 2.2 * cm, "proof": 2.2 * cm}


def _money(v) -> str:
    return f"Rs. {float(v or 0):,.2f}"


def _col_x():
    x = MARGIN_X
    xs = {}
    for key in ("num", "date", "head", "subhead", "desc", "amount", "proof"):
        xs[key] = x
        x += COL_WIDTHS[key]
    return xs


def _build_summary_pdf(claim: EmployeeClaim, lines_with_proof: set[int]) -> tuple[bytes, list[dict]]:
    """Returns (pdf_bytes, proof_boxes) - proof_boxes is a list of
    {"local_page": int, "rect": (x0,y0,x1,y1), "line_id": int} for every
    line that has at least one attachment, so the caller can turn each into
    a real internal PDF link once the final page numbering is known (this
    document doesn't yet contain the attachment pages it needs to point at)."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    normal_style = styles["Normal"].clone("body")
    normal_style.fontSize = 9.5
    normal_style.leading = 13
    cell_style = styles["Normal"].clone("cell")
    cell_style.fontSize = 8
    cell_style.leading = 10

    proof_boxes = []
    local_page = 0
    y = PAGE_H - MARGIN_TOP
    content_width = PAGE_W - 2 * MARGIN_X

    def draw_paragraph(text, style, x, max_width):
        nonlocal y
        p = Paragraph(text, style)
        w, h = p.wrap(max_width, PAGE_H)
        p.drawOn(c, x, y - h)
        y -= h
        return h

    def ensure_space(needed):
        nonlocal y, local_page
        if y - needed < MARGIN_BOTTOM:
            c.showPage()
            local_page += 1
            y = PAGE_H - MARGIN_TOP

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(MARGIN_X, y - 16, f"Employee Claim - {claim.claim_number}")
    y -= 30

    # Meta grid
    employee_name = claim.employee.employee_name if claim.employee else "-"
    project_name = claim.project.name if claim.project else "-"
    category_name = claim.category.name if claim.category else "-"
    meta_rows = [
        ("Employee", employee_name, "Status", claim.status),
        ("Claim Date", str(claim.claim_date), "Project", project_name),
        ("Overall Head", category_name, "Total Amount", _money(claim.total_amount)),
    ]
    c.setFont("Helvetica", 9)
    for label1, val1, label2, val2 in meta_rows:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(MARGIN_X, y - 10, label1)
        c.drawString(MARGIN_X + 5.5 * cm, y - 10, label2)
        c.setFont("Helvetica", 9)
        c.drawString(MARGIN_X + 3.2 * cm, y - 10, str(val1)[:60])
        c.drawString(MARGIN_X + 8.7 * cm, y - 10, str(val2)[:40])
        y -= 18
    y -= 8

    if claim.description:
        draw_paragraph(f"<b>Description:</b> {claim.description}", normal_style, MARGIN_X, content_width)
        y -= 10
    if claim.status == "REJECTED" and claim.rejection_reason:
        draw_paragraph(f"<b>Rejection reason:</b> {claim.rejection_reason}", normal_style, MARGIN_X, content_width)
        y -= 10
    if claim.expense_number:
        draw_paragraph(f"<b>Recorded as expense:</b> {claim.expense_number}", normal_style, MARGIN_X, content_width)
        y -= 10

    c.setFont("Helvetica-Bold", 12)
    c.drawString(MARGIN_X, y - 12, "Expense Lines")
    y -= 26

    cols = _col_x()
    header_h = 16

    def draw_table_header():
        nonlocal y
        c.setFillColor(colors.HexColor("#1e293b"))
        c.rect(MARGIN_X, y - header_h, content_width, header_h, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8)
        labels = {"num": "#", "date": "Date", "head": "Head", "subhead": "Sub-Head", "desc": "Description", "amount": "Amount", "proof": "Proof"}
        for key, label in labels.items():
            c.drawString(cols[key] + 3, y - header_h + 5, label)
        c.setFillColor(colors.black)
        y -= header_h

    draw_table_header()

    row_pad = 5
    for i, line in enumerate(claim.lines, start=1):
        head_name = line.expense_head.name if line.expense_head else "-"
        sub_name = line.expense_sub_head.name if line.expense_sub_head else "-"
        desc_text = line.description or "-"

        desc_p = Paragraph(desc_text, cell_style)
        desc_w, desc_h = desc_p.wrap(COL_WIDTHS["desc"] - 6, PAGE_H)
        head_p = Paragraph(head_name, cell_style)
        head_w, head_h = head_p.wrap(COL_WIDTHS["head"] - 6, PAGE_H)
        sub_p = Paragraph(sub_name, cell_style)
        sub_w, sub_h = sub_p.wrap(COL_WIDTHS["subhead"] - 6, PAGE_H)
        row_h = max(desc_h, head_h, sub_h, 14) + row_pad

        ensure_space(row_h)
        if y == PAGE_H - MARGIN_TOP:  # a page break just happened - redraw header
            draw_table_header()

        row_top = y
        desc_p.drawOn(c, cols["desc"] + 3, row_top - desc_h - row_pad / 2)
        head_p.drawOn(c, cols["head"] + 3, row_top - head_h - row_pad / 2)
        sub_p.drawOn(c, cols["subhead"] + 3, row_top - sub_h - row_pad / 2)

        c.setFont("Helvetica", 8)
        c.drawString(cols["num"] + 3, row_top - 12, str(i))
        c.drawString(cols["date"] + 3, row_top - 12, str(line.expense_date))
        c.drawRightString(cols["amount"] + COL_WIDTHS["amount"] - 4, row_top - 12, _money(line.amount))

        if line.id in lines_with_proof:
            c.setFillColor(colors.HexColor("#1d4ed8"))
            c.setFont("Helvetica-Bold", 8)
            proof_label = "View Proof →"
            c.drawString(cols["proof"] + 3, row_top - 12, proof_label)
            c.setFillColor(colors.black)
            label_w = c.stringWidth(proof_label, "Helvetica-Bold", 8)
            proof_boxes.append({
                "local_page": local_page,
                "rect": (cols["proof"] + 3, row_top - 14, cols["proof"] + 3 + label_w, row_top),
                "line_id": line.id,
            })
        else:
            c.setFont("Helvetica", 8)
            c.setFillColor(colors.HexColor("#94a3b8"))
            c.drawString(cols["proof"] + 3, row_top - 12, "No proof")
            c.setFillColor(colors.black)

        c.setStrokeColor(colors.HexColor("#e5e5e5"))
        c.line(MARGIN_X, row_top - row_h, MARGIN_X + content_width, row_top - row_h)
        y = row_top - row_h

    ensure_space(24)
    c.setStrokeColor(colors.HexColor("#1e293b"))
    c.line(MARGIN_X, y, MARGIN_X + content_width, y)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(cols["desc"] + 3, y - 14, "Total")
    c.drawRightString(cols["amount"] + COL_WIDTHS["amount"] - 4, y - 14, _money(claim.total_amount))
    y -= 30

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawString(MARGIN_X, MARGIN_BOTTOM - 20, f"Generated {dt.datetime.utcnow().strftime('%d-%b-%Y %H:%M')} UTC")

    c.showPage()
    c.save()
    return buf.getvalue(), proof_boxes


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

    line_number_by_id = {line.id: i for i, line in enumerate(claim.lines, start=1)}
    overall_docs = db.query(Document).filter(Document.claim_id == claim.id).order_by(Document.id).all()
    line_ids = list(line_number_by_id.keys())
    line_docs = db.query(Document).filter(Document.claim_line_id.in_(line_ids)).order_by(Document.id).all() if line_ids else []

    # The first (lowest-id) attachment per line is what "View Proof" jumps to.
    first_doc_by_line = {}
    for d in line_docs:
        first_doc_by_line.setdefault(d.claim_line_id, d)
    lines_with_proof = set(first_doc_by_line.keys())

    summary_bytes, proof_boxes = _build_summary_pdf(claim, lines_with_proof)
    for page in PdfReader(BytesIO(summary_bytes)).pages:
        writer.add_page(page)

    attachments = [(d, "Overall Claim Attachment") for d in overall_docs]
    attachments += [(d, f"Line {line_number_by_id[d.claim_line_id]} Attachment") for d in line_docs]

    first_page_index_by_doc_id = {}
    for doc, label in attachments:
        caption = f"{label}: {doc.original_filename}"
        try:
            content = await storage.retrieve_file(doc.stored_filename)
        except Exception:
            first_page_index_by_doc_id[doc.id] = len(writer.pages)
            page_bytes = _placeholder_page_pdf(caption, "Could not load this file - it may be missing from storage.")
            for page in PdfReader(BytesIO(page_bytes)).pages:
                writer.add_page(page)
            continue

        first_page_index_by_doc_id[doc.id] = len(writer.pages)

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

    # Now that every page (summary + attachments) exists in the writer with
    # a known final index, wire up each "View Proof" box to the real target.
    # Built by hand rather than via pypdf.annotations.Link: that helper's
    # target_page_index support leaves /Dest as a bare page *number*
    # instead of an indirect reference to the page object, which is invalid
    # per the PDF spec (readers may tolerate it, but not reliably).
    for box in proof_boxes:
        first_doc = first_doc_by_line.get(box["line_id"])
        if first_doc is None:
            continue
        target_index = first_page_index_by_doc_id.get(first_doc.id)
        if target_index is None:
            continue
        annotation = DictionaryObject({
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Link"),
            NameObject("/Rect"): RectangleObject(box["rect"]),
            NameObject("/Border"): ArrayObject([NumberObject(0), NumberObject(0), NumberObject(0)]),
        })
        added = writer.add_annotation(page_number=box["local_page"], annotation=annotation)
        target_ref = writer.pages[target_index].indirect_reference
        added[NameObject("/Dest")] = ArrayObject([target_ref, NameObject("/Fit")])

    out = BytesIO()
    writer.write(out)
    return out.getvalue()
