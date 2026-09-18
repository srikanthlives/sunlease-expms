import datetime as dt

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import Expense, Payment, EmployeeClaim, Quotation, ReceivableInvoice, ReceivablePayment


def _next_number(db: Session, model, column, prefix: str) -> str:
    year = dt.datetime.utcnow().strftime("%y")
    like_pattern = f"{prefix}-{year}%"
    count = db.query(func.count()).select_from(model).filter(column.like(like_pattern)).scalar() or 0
    seq = count + 1
    return f"{prefix}-{year}{seq:05d}"


def next_expense_number(db: Session) -> str:
    return _next_number(db, Expense, Expense.expense_number, "EXP")


def next_payment_number(db: Session) -> str:
    return _next_number(db, Payment, Payment.payment_number, "PAY")


def next_claim_number(db: Session) -> str:
    return _next_number(db, EmployeeClaim, EmployeeClaim.claim_number, "CLM")


def next_quotation_number(db: Session) -> str:
    return _next_number(db, Quotation, Quotation.quotation_number, "QTN")


def next_receivable_invoice_number(db: Session) -> str:
    return _next_number(db, ReceivableInvoice, ReceivableInvoice.invoice_number, "RCV")


def next_receivable_payment_number(db: Session) -> str:
    return _next_number(db, ReceivablePayment, ReceivablePayment.payment_number, "RCP")
