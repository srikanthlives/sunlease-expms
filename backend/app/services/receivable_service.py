"""Business logic for Receivables (Quotations, Receivable Invoices,
Receivable Payments) - the mirror image of invoice_service/payment_service,
but for money owed TO the company rather than by it."""
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.enums import AuditAction, QuotationStatus, ReceivableStatus
from app.models.models import Quotation, ReceivableInvoice, ReceivablePayment, ReceivablePaymentAllocation
from app.services import audit_service, numbering


def _tax_total(cgst, sgst, igst, other_tax) -> Decimal:
    return Decimal(cgst or 0) + Decimal(sgst or 0) + Decimal(igst or 0) + Decimal(other_tax or 0)


# ---------------------------------------------------------------------------
# Quotations
# ---------------------------------------------------------------------------

def create_quotation(db: Session, *, quotation_number, customer_name, project_id, quotation_date, valid_until, description,
                      taxable_amount, cgst, sgst, igst, other_tax, created_by) -> Quotation:
    if db.query(Quotation).filter(Quotation.quotation_number == quotation_number).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Quotation number '{quotation_number}' already exists")
    total = Decimal(taxable_amount or 0) + _tax_total(cgst, sgst, igst, other_tax)
    q = Quotation(
        quotation_number=quotation_number,
        customer_name=customer_name, project_id=project_id, quotation_date=quotation_date, valid_until=valid_until,
        description=description, taxable_amount=taxable_amount, cgst=cgst, sgst=sgst, igst=igst,
        other_tax=other_tax, total_amount=total, status=QuotationStatus.DRAFT, created_by=created_by,
    )
    db.add(q)
    db.flush()
    audit_service.record(db, "QUOTATION", q.id, AuditAction.CREATE, created_by, {"quotation_number": q.quotation_number})
    return q


def update_quotation(db: Session, q: Quotation, *, quotation_number, customer_name, project_id, quotation_date, valid_until, description,
                      taxable_amount, cgst, sgst, igst, other_tax, actor_id) -> Quotation:
    if q.status == QuotationStatus.CONVERTED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This quotation has already been converted to an invoice and can no longer be edited")
    if quotation_number != q.quotation_number and db.query(Quotation).filter(Quotation.quotation_number == quotation_number).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Quotation number '{quotation_number}' already exists")
    q.quotation_number = quotation_number
    q.customer_name = customer_name
    q.project_id = project_id
    q.quotation_date = quotation_date
    q.valid_until = valid_until
    q.description = description
    q.taxable_amount = taxable_amount
    q.cgst, q.sgst, q.igst, q.other_tax = cgst, sgst, igst, other_tax
    q.total_amount = Decimal(taxable_amount or 0) + _tax_total(cgst, sgst, igst, other_tax)
    db.add(q)
    audit_service.record(db, "QUOTATION", q.id, AuditAction.UPDATE, actor_id, {})
    return q


def send_quotation(db: Session, q: Quotation, actor_id: int) -> Quotation:
    if q.status != QuotationStatus.DRAFT:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a draft quotation can be sent")
    q.status = QuotationStatus.SENT
    db.add(q)
    audit_service.record(db, "QUOTATION", q.id, AuditAction.SUBMIT, actor_id, {})
    return q


def accept_quotation(db: Session, q: Quotation, actor_id: int) -> Quotation:
    if q.status not in (QuotationStatus.SENT, QuotationStatus.DRAFT):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a sent (or draft) quotation can be accepted")
    q.status = QuotationStatus.ACCEPTED
    db.add(q)
    audit_service.record(db, "QUOTATION", q.id, AuditAction.APPROVE, actor_id, {})
    return q


def reject_quotation(db: Session, q: Quotation, actor_id: int, reason: str | None) -> Quotation:
    if q.status == QuotationStatus.CONVERTED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This quotation has already been converted to an invoice")
    q.status = QuotationStatus.REJECTED
    q.rejection_reason = reason
    db.add(q)
    audit_service.record(db, "QUOTATION", q.id, AuditAction.REJECT, actor_id, {"reason": reason})
    return q


def delete_quotation(db: Session, q: Quotation, actor_id: int):
    """Hard delete - only while still DRAFT (nothing sent to the customer
    yet). Once SENT/ACCEPTED/REJECTED it's kept for the record; once
    CONVERTED it's linked to a real receivable and must never disappear."""
    if q.status != QuotationStatus.DRAFT:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a draft quotation can be deleted - reject it instead")
    audit_service.record(db, "QUOTATION", q.id, AuditAction.DELETE, actor_id, {"quotation_number": q.quotation_number})
    db.delete(q)


def convert_quotation(db: Session, q: Quotation, actor_id: int, *, invoice_number, invoice_date, due_date) -> ReceivableInvoice:
    if q.status != QuotationStatus.ACCEPTED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only an accepted quotation can be converted to an invoice")
    invoice = create_receivable_invoice(
        db, invoice_number=invoice_number, customer_name=q.customer_name, project_id=q.project_id,
        invoice_date=invoice_date, due_date=due_date,
        quotation_id=q.id, po_number=None, description=q.description, taxable_amount=q.taxable_amount,
        cgst=q.cgst, sgst=q.sgst, igst=q.igst, other_tax=q.other_tax, created_by=actor_id,
    )
    q.status = QuotationStatus.CONVERTED
    q.receivable_invoice_id = invoice.id
    db.add(q)
    audit_service.record(db, "QUOTATION", q.id, AuditAction.UPDATE, actor_id, {"converted_to": invoice.invoice_number})
    return invoice


# ---------------------------------------------------------------------------
# Receivable Invoices
# ---------------------------------------------------------------------------

def create_receivable_invoice(db: Session, *, invoice_number, customer_name, project_id, invoice_date, due_date, quotation_id, po_number, description,
                               taxable_amount, cgst, sgst, igst, other_tax, created_by) -> ReceivableInvoice:
    if db.query(ReceivableInvoice).filter(ReceivableInvoice.invoice_number == invoice_number).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invoice number '{invoice_number}' already exists")
    total = Decimal(taxable_amount or 0) + _tax_total(cgst, sgst, igst, other_tax)
    inv = ReceivableInvoice(
        invoice_number=invoice_number,
        customer_name=customer_name, project_id=project_id, invoice_date=invoice_date, due_date=due_date, quotation_id=quotation_id,
        po_number=po_number, description=description, taxable_amount=taxable_amount, cgst=cgst, sgst=sgst, igst=igst,
        other_tax=other_tax, total_amount=total, status=ReceivableStatus.ACTIVE, payment_status="UNPAID",
        created_by=created_by,
    )
    db.add(inv)
    db.flush()
    audit_service.record(db, "RECEIVABLE_INVOICE", inv.id, AuditAction.CREATE, created_by, {"invoice_number": inv.invoice_number})
    return inv


def update_receivable_invoice(db: Session, inv: ReceivableInvoice, *, invoice_number, customer_name, project_id, invoice_date, due_date,
                               po_number, description, taxable_amount, cgst, sgst, igst, other_tax, actor_id) -> ReceivableInvoice:
    if inv.status != ReceivableStatus.ACTIVE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A cancelled invoice cannot be edited")
    if invoice_number != inv.invoice_number and db.query(ReceivableInvoice).filter(ReceivableInvoice.invoice_number == invoice_number).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invoice number '{invoice_number}' already exists")
    new_total = Decimal(taxable_amount or 0) + _tax_total(cgst, sgst, igst, other_tax)
    if new_total < get_receivable_paid_amount(db, inv.id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot reduce the invoice total below what's already been received against it")
    inv.invoice_number = invoice_number
    inv.customer_name = customer_name
    inv.project_id = project_id
    inv.invoice_date = invoice_date
    inv.due_date = due_date
    inv.po_number = po_number
    inv.description = description
    inv.taxable_amount = taxable_amount
    inv.cgst, inv.sgst, inv.igst, inv.other_tax = cgst, sgst, igst, other_tax
    inv.total_amount = new_total
    db.add(inv)
    recalculate_receivable_payment_status(db, inv)
    audit_service.record(db, "RECEIVABLE_INVOICE", inv.id, AuditAction.UPDATE, actor_id, {})
    return inv


def cancel_receivable_invoice(db: Session, inv: ReceivableInvoice, actor_id: int, reason: str | None):
    if get_receivable_paid_amount(db, inv.id) > 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot cancel an invoice that has payments allocated to it - delete the payment(s) first")
    inv.status = ReceivableStatus.CANCELLED
    db.add(inv)
    audit_service.record(db, "RECEIVABLE_INVOICE", inv.id, AuditAction.CANCEL, actor_id, {"reason": reason})
    return inv


def delete_receivable_invoice(db: Session, inv: ReceivableInvoice, actor_id: int):
    """Hard delete - only for an unpaid invoice with no quotation link (a
    converted quotation's invoice is deleted by deleting/rejecting the
    quotation flow instead, to keep the two in sync)."""
    if get_receivable_paid_amount(db, inv.id) > 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This invoice has a payment allocated to it - delete the payment first")
    if inv.quotation_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This invoice was generated from a quotation and can't be deleted directly - cancel it instead")
    audit_service.record(db, "RECEIVABLE_INVOICE", inv.id, AuditAction.DELETE, actor_id, {"invoice_number": inv.invoice_number})
    db.delete(inv)


def get_receivable_paid_amount(db: Session, invoice_id: int) -> Decimal:
    total = (
        db.query(func.coalesce(func.sum(ReceivablePaymentAllocation.allocated_amount), 0))
        .join(ReceivablePayment, ReceivablePaymentAllocation.receivable_payment_id == ReceivablePayment.id)
        .filter(ReceivablePaymentAllocation.receivable_invoice_id == invoice_id, ReceivablePayment.is_cancelled.is_(False))
        .scalar()
    )
    return Decimal(total or 0)


def recalculate_receivable_payment_status(db: Session, inv: ReceivableInvoice) -> str:
    """The ONLY place ReceivableInvoice.payment_status should be written -
    mirrors payment_status_service.recalculate_payment_status."""
    paid = get_receivable_paid_amount(db, inv.id)
    total = Decimal(inv.total_amount or 0)
    if paid <= 0:
        payment_status = "UNPAID"
    elif paid < total:
        payment_status = "PARTIALLY_PAID"
    else:
        payment_status = "PAID"
    inv.payment_status = payment_status
    db.add(inv)
    return payment_status


# ---------------------------------------------------------------------------
# Receivable Payments
# ---------------------------------------------------------------------------

def create_receivable_payment_with_allocations(db: Session, *, payment_date, account_id, payment_mode,
                                                reference_number, remarks, allocations: list[dict], created_by) -> ReceivablePayment:
    if not allocations:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one allocation is required")
    invoices_by_id = {}
    total = Decimal("0")
    for a in allocations:
        inv = db.query(ReceivableInvoice).filter(ReceivableInvoice.id == a["receivable_invoice_id"]).first()
        if not inv or inv.status != ReceivableStatus.ACTIVE:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invoice {a['receivable_invoice_id']} not found or cancelled")
        amount = Decimal(str(a["allocated_amount"]))
        if amount <= 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Allocated amount must be positive")
        outstanding = inv.total_amount - get_receivable_paid_amount(db, inv.id)
        if amount > outstanding:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Allocated amount exceeds outstanding balance for {inv.invoice_number}")
        invoices_by_id[inv.id] = inv
        total += amount

    payment = ReceivablePayment(
        payment_number=numbering.next_receivable_payment_number(db),
        payment_date=payment_date, account_id=account_id, payment_mode=payment_mode, amount=total,
        reference_number=reference_number, remarks=remarks, created_by=created_by,
    )
    db.add(payment)
    db.flush()

    for a in allocations:
        alloc = ReceivablePaymentAllocation(
            receivable_payment_id=payment.id, receivable_invoice_id=a["receivable_invoice_id"],
            allocated_amount=Decimal(str(a["allocated_amount"])),
        )
        db.add(alloc)

    db.flush()
    for inv in invoices_by_id.values():
        recalculate_receivable_payment_status(db, inv)

    audit_service.record(db, "RECEIVABLE_PAYMENT", payment.id, AuditAction.CREATE, created_by, {"payment_number": payment.payment_number, "amount": str(total)})
    return payment


def update_receivable_payment(db: Session, payment: ReceivablePayment, *, payment_date, account_id, payment_mode,
                               reference_number, remarks, actor_id) -> ReceivablePayment:
    """Metadata-only edit - amount and allocations are never touched here
    (see ReceivablePaymentUpdate schema docstring)."""
    if payment.is_cancelled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A cancelled payment cannot be edited")
    if payment_date is not None:
        payment.payment_date = payment_date
    if account_id is not None:
        payment.account_id = account_id
    if payment_mode is not None:
        payment.payment_mode = payment_mode
    if reference_number is not None:
        payment.reference_number = reference_number
    if remarks is not None:
        payment.remarks = remarks
    db.add(payment)
    audit_service.record(db, "RECEIVABLE_PAYMENT", payment.id, AuditAction.UPDATE, actor_id, {})
    return payment


def delete_receivable_payment(db: Session, payment: ReceivablePayment, actor_id: int):
    """Hard delete - only while unverified/uncancelled. Reverses allocations
    first, so affected invoices fall back to UNPAID/PARTIALLY_PAID."""
    affected_invoice_ids = [a.receivable_invoice_id for a in payment.allocations]
    audit_service.record(db, "RECEIVABLE_PAYMENT", payment.id, AuditAction.DELETE, actor_id, {"payment_number": payment.payment_number})
    db.delete(payment)
    db.flush()
    for inv_id in affected_invoice_ids:
        inv = db.query(ReceivableInvoice).filter(ReceivableInvoice.id == inv_id).first()
        if inv:
            recalculate_receivable_payment_status(db, inv)


def cancel_receivable_payment(db: Session, payment: ReceivablePayment, actor_id: int, reason: str | None):
    if payment.is_cancelled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This payment is already cancelled")
    payment.is_cancelled = True
    db.add(payment)
    db.flush()
    audit_service.record(db, "RECEIVABLE_PAYMENT", payment.id, AuditAction.CANCEL, actor_id, {"reason": reason})
    for a in payment.allocations:
        inv = db.query(ReceivableInvoice).filter(ReceivableInvoice.id == a.receivable_invoice_id).first()
        if inv:
            recalculate_receivable_payment_status(db, inv)
    return payment
