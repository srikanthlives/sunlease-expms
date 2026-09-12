import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_accounts, require_non_employee, require_admin
from app.db.session import get_db
from app.models.models import Invoice, Expense, User
from app.schemas.transactions import InvoiceCreate, InvoiceOut, CancelRequest
from app.schemas.edit_requests import InvoiceUpdate
from app.services import invoice_service, edit_request_service, project_scope_service
from app.models.enums import RoleName

router = APIRouter(prefix="/api/v1/invoices", tags=["invoices"])


def _to_out(inv: Invoice) -> InvoiceOut:
    # Invoice itself has no category/sub_category columns - they live on the
    # resolved Expense, so surface them from there for display/edit purposes.
    # Verification is likewise borrowed from the linked Expense, the single
    # source of truth those two rows share (Invoice has no is_verified column).
    out = InvoiceOut.model_validate(inv)
    if inv.expense:
        out.category_id = inv.expense.category_id
        out.sub_category_id = inv.expense.sub_category_id
        out.is_verified = inv.expense.is_verified
        out.verified_by = inv.expense.verified_by
        out.verified_by_name = (inv.expense.verifier.full_name or inv.expense.verifier.username) if inv.expense.verifier else None
        out.verified_at = inv.expense.verified_at
    return out


@router.post("", response_model=InvoiceOut, dependencies=[Depends(require_accounts)])
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role.name == RoleName.ACCOUNTS:
        project_scope_service.assert_project_in_scope(db, user, payload.project_id)
    invoice = invoice_service.create_invoice(
        db, invoice_number=payload.invoice_number, vendor_id=payload.vendor_id, invoice_date=payload.invoice_date,
        due_date=payload.due_date, project_id=payload.project_id, description=payload.description,
        taxable_amount=payload.taxable_amount, cgst=payload.cgst, sgst=payload.sgst, igst=payload.igst,
        other_tax=payload.other_tax, category_id=payload.category_id, sub_category_id=payload.sub_category_id,
        created_by=user.id, pay_immediately=payload.pay_immediately, payment_date=payload.payment_date,
        account_id=payload.account_id, payment_mode=payload.payment_mode, reference_number=payload.reference_number,
        remarks=payload.remarks,
    )
    db.commit()
    db.refresh(invoice)
    return _to_out(invoice)


@router.get("", response_model=list[InvoiceOut], dependencies=[Depends(require_non_employee)])
def list_invoices(
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
    vendor_id: int | None = None, project_id: int | None = None, category_id: int | None = None,
    status_: str | None = None, date_from: dt.date | None = None, date_to: dt.date | None = None,
):
    q = db.query(Invoice)
    if vendor_id:
        q = q.filter(Invoice.vendor_id == vendor_id)
    if project_id:
        q = q.filter(Invoice.project_id == project_id)
    if status_:
        q = q.filter(Invoice.status == status_)
    if date_from:
        q = q.filter(Invoice.invoice_date >= date_from)
    if date_to:
        q = q.filter(Invoice.invoice_date <= date_to)
    if category_id:
        # Category lives on the linked Expense, not Invoice itself.
        q = q.join(Expense, Invoice.expense_id == Expense.id).filter(Expense.category_id == category_id)
    if user.role.name == RoleName.ACCOUNTS:
        assigned = project_scope_service.get_accounts_assigned_project_ids(db, user)
        q = q.filter(Invoice.project_id.in_(assigned)) if assigned else q.filter(False)
    rows = q.order_by(Invoice.invoice_date.desc(), Invoice.id.desc()).limit(500).all()
    return [_to_out(inv) for inv in rows]


@router.get("/{invoice_id}", response_model=InvoiceOut, dependencies=[Depends(require_non_employee)])
def get_invoice(invoice_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    if user.role.name == RoleName.ACCOUNTS:
        project_scope_service.assert_project_in_scope(db, user, inv.project_id)
    return _to_out(inv)


@router.put("/{invoice_id}", response_model=InvoiceOut, dependencies=[Depends(require_accounts)])
def update_invoice(invoice_id: int, payload: InvoiceUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Admin/Super Admin edit directly and unconditionally. Accounts may also
    edit directly, in full, until the underlying expense is verified (see
    POST /expenses/{id}/verify) - after that, Accounts must propose the same
    edit via POST /edit-requests instead."""
    changes = payload.model_dump(exclude_unset=True)
    if user.role.name == RoleName.ACCOUNTS:
        existing = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not existing:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
        project_scope_service.assert_project_in_scope(db, user, existing.project_id)
        inv = edit_request_service.accounts_edit(db, "INVOICE", invoice_id, changes, user)
    else:
        inv = edit_request_service.direct_edit(db, "INVOICE", invoice_id, changes, user)
    db.commit()
    db.refresh(inv)
    return _to_out(inv)


@router.post("/{invoice_id}/verify", response_model=InvoiceOut, dependencies=[Depends(require_admin)])
def verify_invoice(invoice_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Verifies the invoice's underlying Expense (the shared source of truth)
    - once verified, Accounts can no longer edit this invoice directly."""
    inv = edit_request_service.set_verification(db, "INVOICE", invoice_id, user, True)
    db.commit()
    db.refresh(inv)
    return _to_out(inv)


@router.post("/{invoice_id}/unverify", response_model=InvoiceOut, dependencies=[Depends(require_admin)])
def unverify_invoice(invoice_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    inv = edit_request_service.set_verification(db, "INVOICE", invoice_id, user, False)
    db.commit()
    db.refresh(inv)
    return _to_out(inv)


@router.post("/{invoice_id}/cancel", response_model=InvoiceOut, dependencies=[Depends(require_accounts)])
def cancel_invoice(invoice_id: int, payload: CancelRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    if user.role.name == RoleName.ACCOUNTS:
        project_scope_service.assert_project_in_scope(db, user, inv.project_id)
    invoice_service.cancel_invoice(db, inv, user.id, payload.reason)
    db.commit()
    db.refresh(inv)
    return inv
