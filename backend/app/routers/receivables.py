import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_receivables, require_receivables_view
from app.db.session import get_db
from app.models.models import Quotation, ReceivableInvoice, ReceivablePayment, User
from app.models.enums import QuotationStatus, ReceivableStatus
from app.schemas.receivables import (
    QuotationCreate, QuotationOut, QuotationRejectRequest, QuotationConvertRequest,
    ReceivableInvoiceCreate, ReceivableInvoiceOut, ReceivableCancelRequest,
    ReceivablePaymentCreate, ReceivablePaymentUpdate, ReceivablePaymentOut,
)
from app.services import receivable_service

router = APIRouter(prefix="/api/v1/receivables", tags=["receivables"])


# ---------------------------------------------------------------------------
# Quotations
# ---------------------------------------------------------------------------

def _quotation_out(q: Quotation) -> QuotationOut:
    out = QuotationOut.model_validate(q)
    out.receivable_invoice_number = q.receivable_invoice.invoice_number if q.receivable_invoice else None
    out.project_name = q.project.name if q.project else None
    return out


@router.post("/quotations", response_model=QuotationOut, dependencies=[Depends(require_receivables)])
def create_quotation(payload: QuotationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = receivable_service.create_quotation(db, **payload.model_dump(), created_by=user.id)
    db.commit()
    db.refresh(q)
    return _quotation_out(q)


@router.get("/quotations", response_model=list[QuotationOut], dependencies=[Depends(require_receivables_view)])
def list_quotations(
    db: Session = Depends(get_db), status_: str | None = Query(None, alias="status"),
    project_id: int | None = None,
    date_from: dt.date | None = None, date_to: dt.date | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=500),
):
    q = db.query(Quotation)
    if status_:
        q = q.filter(Quotation.status == status_)
    if project_id:
        q = q.filter(Quotation.project_id == project_id)
    if date_from:
        q = q.filter(Quotation.quotation_date >= date_from)
    if date_to:
        q = q.filter(Quotation.quotation_date <= date_to)
    rows = q.order_by(Quotation.id.desc()).all()
    total = len(rows)
    page_rows = rows[(page - 1) * page_size: (page - 1) * page_size + page_size]
    return [_quotation_out(r) for r in page_rows]


@router.get("/quotations/summary", dependencies=[Depends(require_receivables_view)])
def quotations_summary(
    db: Session = Depends(get_db), status_: str | None = Query(None, alias="status"),
    project_id: int | None = None,
    date_from: dt.date | None = None, date_to: dt.date | None = None,
):
    q = db.query(Quotation)
    if status_:
        q = q.filter(Quotation.status == status_)
    if project_id:
        q = q.filter(Quotation.project_id == project_id)
    if date_from:
        q = q.filter(Quotation.quotation_date >= date_from)
    if date_to:
        q = q.filter(Quotation.quotation_date <= date_to)
    rows = q.all()
    total_amount = sum((r.total_amount for r in rows), Decimal("0"))
    return {"count": len(rows), "total_amount": total_amount}


@router.get("/quotations/{quotation_id}", response_model=QuotationOut, dependencies=[Depends(require_receivables_view)])
def get_quotation(quotation_id: int, db: Session = Depends(get_db)):
    q = db.query(Quotation).filter(Quotation.id == quotation_id).first()
    if not q:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quotation not found")
    return _quotation_out(q)


@router.put("/quotations/{quotation_id}", response_model=QuotationOut, dependencies=[Depends(require_receivables)])
def update_quotation(quotation_id: int, payload: QuotationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Quotation).filter(Quotation.id == quotation_id).first()
    if not q:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quotation not found")
    receivable_service.update_quotation(db, q, **payload.model_dump(), actor_id=user.id)
    db.commit()
    db.refresh(q)
    return _quotation_out(q)


@router.delete("/quotations/{quotation_id}", dependencies=[Depends(require_receivables)])
def delete_quotation(quotation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Quotation).filter(Quotation.id == quotation_id).first()
    if not q:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quotation not found")
    receivable_service.delete_quotation(db, q, user.id)
    db.commit()
    return {"detail": "Quotation deleted"}


@router.post("/quotations/{quotation_id}/send", response_model=QuotationOut, dependencies=[Depends(require_receivables)])
def send_quotation(quotation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Quotation).filter(Quotation.id == quotation_id).first()
    if not q:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quotation not found")
    receivable_service.send_quotation(db, q, user.id)
    db.commit()
    db.refresh(q)
    return _quotation_out(q)


@router.post("/quotations/{quotation_id}/accept", response_model=QuotationOut, dependencies=[Depends(require_receivables)])
def accept_quotation(quotation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Quotation).filter(Quotation.id == quotation_id).first()
    if not q:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quotation not found")
    receivable_service.accept_quotation(db, q, user.id)
    db.commit()
    db.refresh(q)
    return _quotation_out(q)


@router.post("/quotations/{quotation_id}/reject", response_model=QuotationOut, dependencies=[Depends(require_receivables)])
def reject_quotation(quotation_id: int, payload: QuotationRejectRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Quotation).filter(Quotation.id == quotation_id).first()
    if not q:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quotation not found")
    receivable_service.reject_quotation(db, q, user.id, payload.reason)
    db.commit()
    db.refresh(q)
    return _quotation_out(q)


@router.post("/quotations/{quotation_id}/convert", response_model=ReceivableInvoiceOut, dependencies=[Depends(require_receivables)])
def convert_quotation(quotation_id: int, payload: QuotationConvertRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Quotation).filter(Quotation.id == quotation_id).first()
    if not q:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quotation not found")
    inv = receivable_service.convert_quotation(
        db, q, user.id, invoice_number=payload.invoice_number, invoice_date=payload.invoice_date, due_date=payload.due_date,
    )
    db.commit()
    db.refresh(inv)
    return _invoice_out(db, inv)


# ---------------------------------------------------------------------------
# Receivable Invoices
# ---------------------------------------------------------------------------

def _invoice_out(db: Session, inv: ReceivableInvoice) -> ReceivableInvoiceOut:
    paid = receivable_service.get_receivable_paid_amount(db, inv.id)
    out = ReceivableInvoiceOut.model_validate(inv)
    out.paid_amount = paid
    out.balance_due = inv.total_amount - paid
    out.quotation_number = inv.quotation.quotation_number if inv.quotation else None
    out.project_name = inv.project.name if inv.project else None
    return out


@router.post("/invoices", response_model=ReceivableInvoiceOut, dependencies=[Depends(require_receivables)])
def create_receivable_invoice(payload: ReceivableInvoiceCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    inv = receivable_service.create_receivable_invoice(db, **payload.model_dump(), quotation_id=None, created_by=user.id)
    db.commit()
    db.refresh(inv)
    return _invoice_out(db, inv)


@router.get("/invoices", response_model=list[ReceivableInvoiceOut], dependencies=[Depends(require_receivables_view)])
def list_receivable_invoices(
    db: Session = Depends(get_db), status_: str | None = Query(None, alias="status"),
    payment_status: str | None = None, project_id: int | None = None,
    date_from: dt.date | None = None, date_to: dt.date | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=500),
):
    q = db.query(ReceivableInvoice)
    if status_:
        q = q.filter(ReceivableInvoice.status == status_)
    if payment_status:
        q = q.filter(ReceivableInvoice.payment_status == payment_status)
    if project_id:
        q = q.filter(ReceivableInvoice.project_id == project_id)
    if date_from:
        q = q.filter(ReceivableInvoice.invoice_date >= date_from)
    if date_to:
        q = q.filter(ReceivableInvoice.invoice_date <= date_to)
    rows = q.order_by(ReceivableInvoice.id.desc()).all()
    page_rows = rows[(page - 1) * page_size: (page - 1) * page_size + page_size]
    return [_invoice_out(db, r) for r in page_rows]


@router.get("/invoices/summary", dependencies=[Depends(require_receivables_view)])
def receivable_invoices_summary(
    db: Session = Depends(get_db), status_: str | None = Query(None, alias="status"),
    payment_status: str | None = None, project_id: int | None = None,
    date_from: dt.date | None = None, date_to: dt.date | None = None,
):
    q = db.query(ReceivableInvoice)
    if status_:
        q = q.filter(ReceivableInvoice.status == status_)
    if payment_status:
        q = q.filter(ReceivableInvoice.payment_status == payment_status)
    if project_id:
        q = q.filter(ReceivableInvoice.project_id == project_id)
    if date_from:
        q = q.filter(ReceivableInvoice.invoice_date >= date_from)
    if date_to:
        q = q.filter(ReceivableInvoice.invoice_date <= date_to)
    rows = q.all()
    total_amount = sum((r.total_amount for r in rows), Decimal("0"))
    paid_amount = sum((receivable_service.get_receivable_paid_amount(db, r.id) for r in rows), Decimal("0"))
    return {"count": len(rows), "total_amount": total_amount, "paid_amount": paid_amount, "balance_due": total_amount - paid_amount}


@router.get("/invoices/{invoice_id}", response_model=ReceivableInvoiceOut, dependencies=[Depends(require_receivables_view)])
def get_receivable_invoice(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.query(ReceivableInvoice).filter(ReceivableInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    return _invoice_out(db, inv)


@router.put("/invoices/{invoice_id}", response_model=ReceivableInvoiceOut, dependencies=[Depends(require_receivables)])
def update_receivable_invoice(invoice_id: int, payload: ReceivableInvoiceCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    inv = db.query(ReceivableInvoice).filter(ReceivableInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    receivable_service.update_receivable_invoice(db, inv, **payload.model_dump(), actor_id=user.id)
    db.commit()
    db.refresh(inv)
    return _invoice_out(db, inv)


@router.delete("/invoices/{invoice_id}", dependencies=[Depends(require_receivables)])
def delete_receivable_invoice(invoice_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    inv = db.query(ReceivableInvoice).filter(ReceivableInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    receivable_service.delete_receivable_invoice(db, inv, user.id)
    db.commit()
    return {"detail": "Invoice deleted"}


@router.post("/invoices/{invoice_id}/cancel", response_model=ReceivableInvoiceOut, dependencies=[Depends(require_receivables)])
def cancel_receivable_invoice(invoice_id: int, payload: ReceivableCancelRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    inv = db.query(ReceivableInvoice).filter(ReceivableInvoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    receivable_service.cancel_receivable_invoice(db, inv, user.id, payload.reason)
    db.commit()
    db.refresh(inv)
    return _invoice_out(db, inv)


# ---------------------------------------------------------------------------
# Receivable Payments
# ---------------------------------------------------------------------------

def _payment_out(p: ReceivablePayment) -> ReceivablePaymentOut:
    out = ReceivablePaymentOut.model_validate(p)
    for a, out_a in zip(p.allocations, out.allocations):
        out_a.invoice_number = a.invoice.invoice_number if a.invoice else None
    return out


@router.post("/payments", response_model=ReceivablePaymentOut, dependencies=[Depends(require_receivables)])
def create_receivable_payment(payload: ReceivablePaymentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    payment = receivable_service.create_receivable_payment_with_allocations(
        db, payment_date=payload.payment_date, account_id=payload.account_id, payment_mode=payload.payment_mode,
        reference_number=payload.reference_number, remarks=payload.remarks,
        allocations=[a.model_dump() for a in payload.allocations], created_by=user.id,
    )
    db.commit()
    db.refresh(payment)
    return _payment_out(payment)


@router.get("/payments", response_model=list[ReceivablePaymentOut], dependencies=[Depends(require_receivables_view)])
def list_receivable_payments(
    db: Session = Depends(get_db), account_id: int | None = None, is_cancelled: bool | None = None,
    date_from: dt.date | None = None, date_to: dt.date | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=500),
):
    q = db.query(ReceivablePayment)
    if account_id:
        q = q.filter(ReceivablePayment.account_id == account_id)
    if is_cancelled is not None:
        q = q.filter(ReceivablePayment.is_cancelled == is_cancelled)
    if date_from:
        q = q.filter(ReceivablePayment.payment_date >= date_from)
    if date_to:
        q = q.filter(ReceivablePayment.payment_date <= date_to)
    rows = q.order_by(ReceivablePayment.id.desc()).all()
    page_rows = rows[(page - 1) * page_size: (page - 1) * page_size + page_size]
    return [_payment_out(p) for p in page_rows]


@router.put("/payments/{payment_id}", response_model=ReceivablePaymentOut, dependencies=[Depends(require_receivables)])
def update_receivable_payment(payment_id: int, payload: ReceivablePaymentUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(ReceivablePayment).filter(ReceivablePayment.id == payment_id).first()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    receivable_service.update_receivable_payment(
        db, p, payment_date=payload.payment_date, account_id=payload.account_id, payment_mode=payload.payment_mode,
        reference_number=payload.reference_number, remarks=payload.remarks, actor_id=user.id,
    )
    db.commit()
    db.refresh(p)
    return _payment_out(p)


@router.delete("/payments/{payment_id}", dependencies=[Depends(require_receivables)])
def delete_receivable_payment(payment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(ReceivablePayment).filter(ReceivablePayment.id == payment_id).first()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    receivable_service.delete_receivable_payment(db, p, user.id)
    db.commit()
    return {"detail": "Payment deleted"}


@router.post("/payments/{payment_id}/cancel", response_model=ReceivablePaymentOut, dependencies=[Depends(require_receivables)])
def cancel_receivable_payment(payment_id: int, payload: ReceivableCancelRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(ReceivablePayment).filter(ReceivablePayment.id == payment_id).first()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    receivable_service.cancel_receivable_payment(db, p, user.id, payload.reason)
    db.commit()
    db.refresh(p)
    return _payment_out(p)
