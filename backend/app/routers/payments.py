import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_accounts, require_non_employee, require_admin
from app.db.session import get_db
from app.models.models import Expense, Payment, PaymentAllocation, User, Vendor, Employee, Account, Project, ExpenseCategory, ExpenseSubCategory
from app.schemas.transactions import PaymentCreate, PaymentOut, CancelRequest
from app.schemas.edit_requests import PaymentUpdate
from app.services import payment_service, edit_request_service, project_scope_service, payment_pdf_service
from app.models.enums import RoleName

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


def _to_out(p: Payment) -> PaymentOut:
    out = PaymentOut.model_validate(p)
    out.verified_by_name = (p.verifier.full_name or p.verifier.username) if p.verifier else None
    return out


def _payee_of(p: Payment) -> str:
    if p.vendor_id:
        return p.vendor.vendor_name if p.vendor else ""
    if p.employee_id:
        return p.employee.employee_name if p.employee else ""
    return "Expense"


_SORT_KEYS = {"payment_date", "payee", "account_id", "payment_mode", "amount", "is_cancelled", "is_verified"}


def _sort_rows(rows: list[Payment], sort_by: str, sort_dir: str) -> list[Payment]:
    """In-memory sort over the FULL filtered set (called before pagination
    slices it) - mirrors expenses.py/invoices.py's _sort_rows for the same
    reason: `payee` and `account_id` (by name) aren't plain sortable columns."""
    if sort_by not in _SORT_KEYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown sort_by '{sort_by}'")

    def key(p: Payment):
        if sort_by == "payment_date":
            return p.payment_date
        if sort_by == "payee":
            return _payee_of(p).lower()
        if sort_by == "account_id":
            return (p.account.account_name if p.account else "").lower()
        if sort_by == "payment_mode":
            return p.payment_mode or ""
        if sort_by == "amount":
            return p.amount
        if sort_by == "is_cancelled":
            return p.is_cancelled
        if sort_by == "is_verified":
            return p.is_verified

    with_value = [r for r in rows if key(r) is not None]
    without_value = [r for r in rows if key(r) is None]
    with_value.sort(key=key, reverse=(sort_dir == "desc"))
    return with_value + without_value


def _apply_filters(
    q, *, vendor_id, employee_id, account_id, payment_mode, is_cancelled,
    date_from, date_to, project_id, category_id, sub_category_id,
):
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
    if project_id or category_id or sub_category_id:
        # A payment has no project/head/sub-head of its own - reached only
        # through its allocations' expenses. Matches if ANY allocation
        # touches an expense in the given project/head/sub-head.
        q = q.join(PaymentAllocation, PaymentAllocation.payment_id == Payment.id).join(
            Expense, PaymentAllocation.expense_id == Expense.id
        )
        if project_id:
            q = q.filter(Expense.project_id == project_id)
        if category_id:
            q = q.filter(Expense.category_id == category_id)
        if sub_category_id:
            q = q.filter(Expense.sub_category_id == sub_category_id)
        q = q.distinct()
    return q


def _filtered_rows(db: Session, user: User, **filters) -> list[Payment]:
    q = _apply_filters(db.query(Payment), **filters)
    rows = q.order_by(Payment.payment_date.desc(), Payment.id.desc()).all()
    if user.role.name == RoleName.ACCOUNTS:
        assigned = set(project_scope_service.get_accounts_assigned_project_ids(db, user))
        if not assigned:
            return []
        rows = [p for p in rows if assigned & set(project_scope_service.payment_project_ids(db, p))]
    return rows


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
    return _to_out(payment)


@router.get("", response_model=list[PaymentOut], dependencies=[Depends(require_non_employee)])
def list_payments(
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
    vendor_id: int | None = None, employee_id: int | None = None,
    account_id: int | None = None, payment_mode: str | None = None, is_cancelled: bool | None = None,
    date_from: str | None = None, date_to: str | None = None,
    project_id: int | None = None, category_id: int | None = None, sub_category_id: int | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(500, ge=1, le=500),
    sort_by: str | None = None, sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
):
    # page_size defaults to the old hardcoded cap (500) so existing callers
    # that don't pass page/page_size keep seeing the full result set - only a
    # caller that opts into a smaller page_size (the Payments list screen)
    # gets truncated pages.
    rows = _filtered_rows(
        db, user, vendor_id=vendor_id, employee_id=employee_id, account_id=account_id,
        payment_mode=payment_mode, is_cancelled=is_cancelled, date_from=date_from, date_to=date_to,
        project_id=project_id, category_id=category_id, sub_category_id=sub_category_id,
    )
    if sort_by:
        rows = _sort_rows(rows, sort_by, sort_dir)
    page_rows = rows[(page - 1) * page_size: (page - 1) * page_size + page_size]
    return [_to_out(p) for p in page_rows]


@router.get("/summary", dependencies=[Depends(require_non_employee)])
def payments_summary(
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
    vendor_id: int | None = None, employee_id: int | None = None,
    account_id: int | None = None, payment_mode: str | None = None, is_cancelled: bool | None = None,
    date_from: str | None = None, date_to: str | None = None,
    project_id: int | None = None, category_id: int | None = None, sub_category_id: int | None = None,
):
    """Aggregate totals over the FULL filtered result set (not just the
    current page) - backs the pagination count and the amount summary row
    on the Payments list screen. Same filters as GET /payments."""
    rows = _filtered_rows(
        db, user, vendor_id=vendor_id, employee_id=employee_id, account_id=account_id,
        payment_mode=payment_mode, is_cancelled=is_cancelled, date_from=date_from, date_to=date_to,
        project_id=project_id, category_id=category_id, sub_category_id=sub_category_id,
    )
    amount = sum((p.amount for p in rows), Decimal("0"))
    return {"count": len(rows), "amount": amount}


def _describe_filters(
    db: Session, *, vendor_id, employee_id, account_id, payment_mode, is_cancelled,
    date_from, date_to, project_id, category_id, sub_category_id,
) -> str:
    """Human-readable summary of the active filters, printed at the top of
    the PDF so the export is self-documenting."""
    parts = []
    if date_from or date_to:
        parts.append(f"Date: {date_from or '…'} to {date_to or '…'}")
    if vendor_id:
        v = db.query(Vendor).filter(Vendor.id == vendor_id).first()
        parts.append(f"Vendor: {v.vendor_name if v else vendor_id}")
    if employee_id:
        e = db.query(Employee).filter(Employee.id == employee_id).first()
        parts.append(f"Employee: {e.employee_name if e else employee_id}")
    if account_id:
        a = db.query(Account).filter(Account.id == account_id).first()
        parts.append(f"Account: {a.account_name if a else account_id}")
    if payment_mode:
        parts.append(f"Mode: {payment_mode}")
    if project_id:
        p = db.query(Project).filter(Project.id == project_id).first()
        parts.append(f"Project: {p.name if p else project_id}")
    if category_id:
        c = db.query(ExpenseCategory).filter(ExpenseCategory.id == category_id).first()
        parts.append(f"Head: {c.name if c else category_id}")
    if sub_category_id:
        s = db.query(ExpenseSubCategory).filter(ExpenseSubCategory.id == sub_category_id).first()
        parts.append(f"Sub-Head: {s.name if s else sub_category_id}")
    if is_cancelled is not None:
        parts.append(f"Status: {'Cancelled' if is_cancelled else 'Active'}")
    return "Filters: " + " | ".join(parts) if parts else "Filters: none (all payments)"


@router.get("/export-pdf", dependencies=[Depends(require_non_employee)])
def export_payments_pdf(
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
    vendor_id: int | None = None, employee_id: int | None = None,
    account_id: int | None = None, payment_mode: str | None = None, is_cancelled: bool | None = None,
    date_from: str | None = None, date_to: str | None = None,
    project_id: int | None = None, category_id: int | None = None, sub_category_id: int | None = None,
    columns: str | None = Query(None, description="Comma-separated column keys - mirrors the frontend's visible (non-hidden) columns"),
):
    """PDF export of the Payments list - same filters and the same set of
    visible columns as the on-screen table. Always the full filtered result
    set, not just the current page."""
    rows = _filtered_rows(
        db, user, vendor_id=vendor_id, employee_id=employee_id, account_id=account_id,
        payment_mode=payment_mode, is_cancelled=is_cancelled, date_from=date_from, date_to=date_to,
        project_id=project_id, category_id=category_id, sub_category_id=sub_category_id,
    )
    amount = sum((p.amount for p in rows), Decimal("0"))
    summary = {"count": len(rows), "amount": amount}

    filters_desc = _describe_filters(
        db, vendor_id=vendor_id, employee_id=employee_id, account_id=account_id,
        payment_mode=payment_mode, is_cancelled=is_cancelled, date_from=date_from, date_to=date_to,
        project_id=project_id, category_id=category_id, sub_category_id=sub_category_id,
    )
    col_list = [c.strip() for c in columns.split(",") if c.strip()] if columns else None

    pdf_bytes = payment_pdf_service.build_payments_pdf(rows, col_list, filters_desc, summary, user.full_name or user.username)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="payments-{dt.date.today().isoformat()}.pdf"'},
    )


@router.get("/{payment_id}", response_model=PaymentOut, dependencies=[Depends(require_non_employee)])
def get_payment(payment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(Payment).filter(Payment.id == payment_id).first()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    if user.role.name == RoleName.ACCOUNTS:
        project_scope_service.assert_payment_in_scope(db, user, p)
    return _to_out(p)


@router.put("/{payment_id}", response_model=PaymentOut, dependencies=[Depends(require_accounts)])
def update_payment(payment_id: int, payload: PaymentUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Amount and allocations are not editable here (by design - see
    CLAUDE.md); only payment_date/account_id/payment_mode/reference_number/
    remarks. Admin/Super Admin edit directly and unconditionally. Accounts
    may also edit directly until the payment is verified (see
    POST .../verify), after which they must use POST /edit-requests instead."""
    changes = payload.model_dump(exclude_unset=True)
    if user.role.name == RoleName.ACCOUNTS:
        existing = db.query(Payment).filter(Payment.id == payment_id).first()
        if not existing:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
        project_scope_service.assert_payment_in_scope(db, user, existing)
        p = edit_request_service.accounts_edit(db, "PAYMENT", payment_id, changes, user)
    else:
        p = edit_request_service.direct_edit(db, "PAYMENT", payment_id, changes, user)
    db.commit()
    db.refresh(p)
    return _to_out(p)


@router.post("/{payment_id}/verify", response_model=PaymentOut, dependencies=[Depends(require_admin)])
def verify_payment(payment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = edit_request_service.set_verification(db, "PAYMENT", payment_id, user, True)
    db.commit()
    db.refresh(p)
    return _to_out(p)


@router.post("/{payment_id}/unverify", response_model=PaymentOut, dependencies=[Depends(require_admin)])
def unverify_payment(payment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = edit_request_service.set_verification(db, "PAYMENT", payment_id, user, False)
    db.commit()
    db.refresh(p)
    return _to_out(p)


@router.delete("/{payment_id}", dependencies=[Depends(require_accounts)])
def delete_payment(payment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Hard delete - only while unverified. Reverses the payment's
    allocations first, so the affected expense(s) fall back to UNPAID/
    PARTIALLY_PAID (see payment_service.delete_payment)."""
    p = db.query(Payment).filter(Payment.id == payment_id).first()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    if user.role.name == RoleName.ACCOUNTS:
        project_scope_service.assert_payment_in_scope(db, user, p)
        if edit_request_service.is_locked_for_accounts("PAYMENT", p):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This payment has been verified by Admin and can no longer be deleted")
    payment_service.delete_payment(db, p, user.id)
    db.commit()
    return {"detail": "Payment deleted"}


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
