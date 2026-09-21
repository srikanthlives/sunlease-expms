import datetime as dt

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import Expense, Payment, EmployeeClaim, Quotation, ReceivableInvoice, ReceivablePayment


def _next_number(db: Session, model, column, prefix: str) -> str:
    """Sequence must be derived from the highest existing number, not a row
    COUNT - deleting any row (e.g. an invoice-linked expense removed via
    invoice deletion) shrinks the count without freeing its number, so a
    COUNT-based next value can collide with a still-existing later row and
    raise a UNIQUE constraint IntegrityError on insert."""
    year = dt.datetime.utcnow().strftime("%y")
    prefix_len = len(f"{prefix}-{year}")
    like_pattern = f"{prefix}-{year}%"
    existing = db.query(column).filter(column.like(like_pattern)).all()
    max_seq = 0
    for (value,) in existing:
        try:
            seq = int(value[prefix_len:])
        except (TypeError, ValueError):
            continue
        max_seq = max(max_seq, seq)
    seq = max_seq + 1
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
