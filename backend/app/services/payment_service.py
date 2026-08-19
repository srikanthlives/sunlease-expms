from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.models import Payment, PaymentAllocation, Expense
from app.models.enums import AuditAction
from app.services import numbering, audit_service
from app.services.payment_status_service import get_paid_amount, recalculate_payment_status


def create_payment_with_allocations(
    db: Session, *, payment_date, vendor_id, employee_id, account_id, payment_mode, reference_number,
    remarks, allocations: list[dict], created_by: int,
) -> Payment:
    """allocations: list of {expense_id, allocated_amount}.
    Validates every allocation against outstanding balance before writing anything,
    then creates the payment + all allocations in one atomic unit."""
    if not allocations:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one allocation is required")

    total_amount = Decimal("0")
    expenses: dict[int, Expense] = {}
    for alloc in allocations:
        expense_id = alloc["expense_id"]
        amount = Decimal(str(alloc["allocated_amount"]))
        if amount <= 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Allocation amount must be greater than zero")

        expense = db.query(Expense).filter(Expense.id == expense_id).first()
        if not expense:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Expense {expense_id} not found")
        if expense.status != "ACTIVE":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Expense {expense.expense_number} is not active")

        already_paid = get_paid_amount(db, expense_id)
        outstanding = Decimal(expense.total_amount) - already_paid
        if amount > outstanding:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Allocation of {amount} to {expense.expense_number} exceeds outstanding balance of {outstanding}",
            )
        expenses[expense_id] = expense
        total_amount += amount

    payment = Payment(
        payment_number=numbering.next_payment_number(db),
        payment_date=payment_date,
        vendor_id=vendor_id,
        employee_id=employee_id,
        account_id=account_id,
        payment_mode=payment_mode,
        amount=total_amount,
        reference_number=reference_number,
        remarks=remarks,
        created_by=created_by,
    )
    db.add(payment)
    db.flush()

    for alloc in allocations:
        pa = PaymentAllocation(
            payment_id=payment.id,
            expense_id=alloc["expense_id"],
            allocated_amount=Decimal(str(alloc["allocated_amount"])),
        )
        db.add(pa)
    db.flush()

    for expense in expenses.values():
        recalculate_payment_status(db, expense)

    audit_service.record(
        db, "PAYMENT", payment.id, AuditAction.PAY, created_by,
        {"amount": str(total_amount), "expense_ids": list(expenses.keys())},
    )
    return payment


def cancel_payment(db: Session, payment: Payment, actor_id: int, reason: str | None = None):
    """Reverse a payment: mark cancelled, remove its allocations, recalc affected
    expense statuses. Allocation rows are deleted (not the payment record) so the
    payment stays visible for audit while its financial effect is undone."""
    if payment.is_cancelled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment already cancelled")

    affected_expense_ids = [a.expense_id for a in payment.allocations]
    for alloc in list(payment.allocations):
        db.delete(alloc)
    db.flush()

    payment.is_cancelled = True
    db.add(payment)

    for expense_id in affected_expense_ids:
        expense = db.query(Expense).filter(Expense.id == expense_id).first()
        if expense:
            recalculate_payment_status(db, expense)

    audit_service.record(db, "PAYMENT", payment.id, AuditAction.CANCEL, actor_id, {"reason": reason})
    return payment
