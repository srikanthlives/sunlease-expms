from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.models import Expense, Payment, PaymentAllocation
from app.models.enums import SourceType, AuditAction
from app.services import numbering, audit_service
from app.services.payment_status_service import recalculate_payment_status


def create_expense_record(
    db: Session, *, source_type: str, source_id: int | None, expense_date, project_id, vendor_id,
    employee_id, category_id, sub_category_id, description, base_amount: Decimal, gst_amount: Decimal,
    other_amount: Decimal, created_by: int, supplier_name: str | None = None, bill_number: str | None = None,
) -> Expense:
    total = Decimal(base_amount or 0) + Decimal(gst_amount or 0) + Decimal(other_amount or 0)
    if total <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Expense total amount must be greater than zero")

    expense = Expense(
        expense_number=numbering.next_expense_number(db),
        source_type=source_type,
        source_id=source_id,
        expense_date=expense_date,
        project_id=project_id,
        vendor_id=vendor_id,
        employee_id=employee_id,
        category_id=category_id,
        sub_category_id=sub_category_id,
        supplier_name=supplier_name,
        bill_number=bill_number,
        description=description,
        base_amount=base_amount or 0,
        gst_amount=gst_amount or 0,
        other_amount=other_amount or 0,
        total_amount=total,
        status="ACTIVE",
        payment_status="UNPAID",
        created_by=created_by,
    )
    db.add(expense)
    db.flush()
    audit_service.record(db, "EXPENSE", expense.id, AuditAction.CREATE, created_by, {"total_amount": str(total)})
    return expense


def pay_expense_immediately(
    db: Session, *, expense: Expense, payment_date, account_id, payment_mode, reference_number,
    remarks, created_by: int,
) -> Payment:
    """Create a payment + allocation covering the full expense amount, atomically
    alongside expense creation. Caller is responsible for the outer commit."""
    payment = Payment(
        payment_number=numbering.next_payment_number(db),
        payment_date=payment_date,
        vendor_id=expense.vendor_id,
        employee_id=expense.employee_id,
        account_id=account_id,
        payment_mode=payment_mode,
        amount=expense.total_amount,
        reference_number=reference_number,
        remarks=remarks,
        created_by=created_by,
    )
    db.add(payment)
    db.flush()

    allocation = PaymentAllocation(payment_id=payment.id, expense_id=expense.id, allocated_amount=expense.total_amount)
    db.add(allocation)
    db.flush()

    recalculate_payment_status(db, expense)
    audit_service.record(db, "PAYMENT", payment.id, AuditAction.PAY, created_by, {"expense_id": expense.id, "amount": str(payment.amount)})
    return payment


def cancel_expense(db: Session, expense: Expense, actor_id: int, reason: str | None = None):
    """Financial records are never hard-deleted - cancel with an audit trail instead."""
    if expense.payment_status != "UNPAID":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot cancel an expense that has payments allocated to it")
    expense.status = "CANCELLED"
    db.add(expense)
    audit_service.record(db, "EXPENSE", expense.id, AuditAction.CANCEL, actor_id, {"reason": reason})
    return expense
