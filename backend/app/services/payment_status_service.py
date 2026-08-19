from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import PaymentAllocation, Expense


def get_paid_amount(db: Session, expense_id: int) -> Decimal:
    total = (
        db.query(func.coalesce(func.sum(PaymentAllocation.allocated_amount), 0))
        .filter(PaymentAllocation.expense_id == expense_id)
        .scalar()
    )
    return Decimal(total or 0)


def recalculate_payment_status(db: Session, expense: Expense) -> str:
    """Recompute and persist an expense's payment_status from its allocations.
    This is the ONLY place payment_status should be written - never set it
    directly from request payloads."""
    paid = (
        db.query(func.coalesce(func.sum(PaymentAllocation.allocated_amount), 0))
        .filter(PaymentAllocation.expense_id == expense.id)
        .scalar()
    )
    paid = Decimal(paid or 0)
    total = Decimal(expense.total_amount or 0)

    if paid <= 0:
        status = "UNPAID"
    elif paid < total:
        status = "PARTIALLY_PAID"
    else:
        status = "PAID"

    expense.payment_status = status
    db.add(expense)
    return status
