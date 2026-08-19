from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_accounts, require_non_employee, require_admin
from app.db.session import get_db
from app.models.models import Expense, Payment, User
from app.schemas.transactions import PaymentCreate, PaymentOut, CancelRequest
from app.schemas.edit_requests import PaymentUpdate
from app.services import payment_service, edit_request_service, project_scope_service
from app.models.enums import RoleName

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


@router.post("", response_model=PaymentOut, dependencies=[Depends(require_accounts)])
def create_payment(payload: PaymentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role.name == RoleName.ACCOUNTS:
        assigned = set(project_scope_service.get_accounts_assigned_project_ids(db, user))
        for alloc in payload.allocations:
            exp = db.query(Expense).filter(Expense.id == alloc.expense_id).first()
            if not exp or exp.project_id not in assigned:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not assigned to this payment's project(s)")
    payment = payment_service.create_payment_with_allocations(
        db, payment_date=payload.payment_date, vendor_id=payload.vendor_id, employee_id=payload.employee_id,
        account_id=payload.account_id, payment_mode=payload.payment_mode, reference_number=payload.reference_number,
        remarks=payload.remarks, allocations=[a.model_dump() for a in payload.allocations], created_by=user.id,
    )
    db.commit()
    db.refresh(payment)
    return payment


@router.get("", response_model=list[PaymentOut], dependencies=[Depends(require_non_employee)])
def list_payments(
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
    vendor_id: int | None = None, employee_id: int | None = None,
    account_id: int | None = None, payment_mode: str | None = None, is_cancelled: bool | None = None,
    date_from: str | None = None, date_to: str | None = None,
):
    q = db.query(Payment)
    if vendor_id:
        q = q.filter(Payment.vendor_id == vendor_id)
    if employee_id:
        q = q.filter(Payment.employee_id == employee_id)
    if account_id:
        q = q.filter(Payment.account_id == account_id)
    if payment_mode:
        q = q.filter(Payment.payment_mode == payment_mode)
    if is_cancelled is not None:
        q = q.filter(Payment.is_cancelled == is_cancelled)
    if date_from:
        q = q.filter(Payment.payment_date >= date_from)
    if date_to:
        q = q.filter(Payment.payment_date <= date_to)
    rows = q.order_by(Payment.payment_date.desc(), Payment.id.desc()).limit(500).all()
    if user.role.name == RoleName.ACCOUNTS:
        assigned = set(project_scope_service.get_accounts_assigned_project_ids(db, user))
        if not assigned:
            return []
        rows = [p for p in rows if assigned & set(project_scope_service.payment_project_ids(db, p))]
    return rows


@router.get("/{payment_id}", response_model=PaymentOut, dependencies=[Depends(require_non_employee)])
def get_payment(payment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(Payment).filter(Payment.id == payment_id).first()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    if user.role.name == RoleName.ACCOUNTS:
        project_scope_service.assert_payment_in_scope(db, user, p)
    return p


@router.put("/{payment_id}", response_model=PaymentOut, dependencies=[Depends(require_admin)])
def update_payment(payment_id: int, payload: PaymentUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Direct edit - Admin/Super Admin only, applies immediately. Amount and
    allocations are not editable here (by design - see CLAUDE.md); only
    payment_date/account_id/payment_mode/reference_number/remarks. Accounts
    proposes the same edit via POST /edit-requests instead."""
    changes = payload.model_dump(exclude_unset=True)
    p = edit_request_service.direct_edit(db, "PAYMENT", payment_id, changes, user)
    db.commit()
    db.refresh(p)
    return p


@router.post("/{payment_id}/cancel", response_model=PaymentOut, dependencies=[Depends(require_accounts)])
def cancel_payment(payment_id: int, payload: CancelRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(Payment).filter(Payment.id == payment_id).first()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    if user.role.name == RoleName.ACCOUNTS:
        project_scope_service.assert_payment_in_scope(db, user, p)
    payment_service.cancel_payment(db, p, user.id, payload.reason)
    db.commit()
    db.refresh(p)
    return p
