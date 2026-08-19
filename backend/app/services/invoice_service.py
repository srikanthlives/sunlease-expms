from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.models import Invoice
from app.models.enums import SourceType, AuditAction
from app.services import expense_service, audit_service


def create_invoice(
    db: Session, *, invoice_number, vendor_id, invoice_date, due_date, project_id, description,
    taxable_amount: Decimal, cgst: Decimal, sgst: Decimal, igst: Decimal, other_tax: Decimal,
    category_id, sub_category_id, created_by: int, pay_immediately: bool = False,
    payment_date=None, account_id=None, payment_mode=None, reference_number=None, remarks=None,
):
    total = Decimal(taxable_amount or 0) + Decimal(cgst or 0) + Decimal(sgst or 0) + Decimal(igst or 0) + Decimal(other_tax or 0)
    if total <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invoice total must be greater than zero")
    if pay_immediately and (not account_id or not payment_mode or not payment_date):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "account_id, payment_mode and payment_date are required to pay immediately")

    # Expense created first without a source_id, invoice created second, then linked.
    expense = expense_service.create_expense_record(
        db, source_type=SourceType.INVOICE, source_id=None, expense_date=invoice_date, project_id=project_id,
        vendor_id=vendor_id, employee_id=None, category_id=category_id, sub_category_id=sub_category_id,
        description=description, base_amount=taxable_amount, gst_amount=(Decimal(cgst or 0) + Decimal(sgst or 0) + Decimal(igst or 0)),
        other_amount=other_tax, created_by=created_by,
    )

    invoice = Invoice(
        invoice_number=invoice_number, vendor_id=vendor_id, invoice_date=invoice_date, due_date=due_date,
        project_id=project_id, description=description, taxable_amount=taxable_amount, cgst=cgst, sgst=sgst,
        igst=igst, other_tax=other_tax, total_amount=total, status="RECORDED", expense_id=expense.id,
        created_by=created_by,
    )
    db.add(invoice)
    db.flush()

    expense.source_id = invoice.id
    db.add(expense)

    if pay_immediately:
        expense_service.pay_expense_immediately(
            db, expense=expense, payment_date=payment_date, account_id=account_id, payment_mode=payment_mode,
            reference_number=reference_number, remarks=remarks, created_by=created_by,
        )

    audit_service.record(db, "INVOICE", invoice.id, AuditAction.CREATE, created_by, {"total_amount": str(total)})
    return invoice


def cancel_invoice(db: Session, invoice: Invoice, actor_id: int, reason: str | None = None):
    if invoice.expense.payment_status != "UNPAID":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot cancel an invoice with payments allocated")
    invoice.status = "CANCELLED"
    db.add(invoice)
    expense_service.cancel_expense(db, invoice.expense, actor_id, reason)
    audit_service.record(db, "INVOICE", invoice.id, AuditAction.CANCEL, actor_id, {"reason": reason})
    return invoice
