import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_accounts, require_non_employee, require_admin
from app.db.session import get_db
from app.models.models import Expense, User, Project, ExpenseCategory, ExpenseSubCategory, Vendor, Employee
from app.schemas.transactions import DirectExpenseCreate, ExpenseOut, CancelRequest
from app.schemas.edit_requests import ExpenseUpdate
from app.services import expense_service, edit_request_service, project_scope_service, expense_pdf_service
from app.services.payment_status_service import get_paid_amount
from app.models.enums import SourceType, RoleName

router = APIRouter(prefix="/api/v1/expenses", tags=["expenses"])


def _to_out(db: Session, e: Expense) -> ExpenseOut:
    paid = get_paid_amount(db, e.id)
    out = ExpenseOut.model_validate(e)
    out.paid_amount = paid
    out.balance_due = e.total_amount - paid
    out.verified_by_name = (e.verifier.full_name or e.verifier.username) if e.verifier else None
    return out


def _payee_of(e: Expense) -> str:
    if e.source_type == SourceType.INVOICE:
        if not e.vendor:
            return ""
        return f"{e.vendor.vendor_name} ({e.vendor.location})" if e.vendor.location else e.vendor.vendor_name
    if e.source_type == SourceType.EMPLOYEE_CLAIM:
        return e.employee.employee_name if e.employee else ""
    return e.supplier_name or ""


_SORT_KEYS = {
    "expense_date", "source_type", "payee", "project_id", "category_id",
    "sub_category_id", "total_amount", "paid_amount", "balance_due", "payment_status",
}


def _sort_rows(db: Session, rows: list[Expense], sort_by: str, sort_dir: str) -> list[Expense]:
    """In-memory sort over the FULL filtered set (called before pagination
    slices it) - the only way to sort consistently by fields that aren't
    plain columns: `payee` is a vendor/employee/supplier-name blend that
    depends on source_type, and paid_amount/balance_due are derived from
    PaymentAllocation sums, not stored on Expense. Fine at this app's scale
    (SQLite, a single org's transactions) - not something to do this way
    against a large multi-tenant table."""
    if sort_by not in _SORT_KEYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown sort_by '{sort_by}'")

    paid_by_id = None
    if sort_by in ("paid_amount", "balance_due"):
        paid_by_id = {e.id: get_paid_amount(db, e.id) for e in rows}

    def key(e: Expense):
        if sort_by == "expense_date":
            return e.expense_date
        if sort_by == "source_type":
            return e.source_type or ""
        if sort_by == "payee":
            return _payee_of(e).lower()
        if sort_by == "project_id":
            return (e.project.name if e.project else "").lower()
        if sort_by == "category_id":
            return (e.category.name if e.category else "").lower()
        if sort_by == "sub_category_id":
            return (e.sub_category.name if e.sub_category else "").lower()
        if sort_by == "total_amount":
            return e.total_amount
        if sort_by == "paid_amount":
            return paid_by_id[e.id]
        if sort_by == "balance_due":
            return e.total_amount - paid_by_id[e.id]
        if sort_by == "payment_status":
            return e.payment_status or ""

    # None-valued keys (e.g. no project) always sort last, regardless of
    # direction - flipping direction only reorders the rows that actually
    # have a value.
    with_value = [e for e in rows if key(e) is not None]
    without_value = [e for e in rows if key(e) is None]
    with_value.sort(key=key, reverse=(sort_dir == "desc"))
    return with_value + without_value


def _apply_filters(
    q, *, project_id, vendor_id, employee_id, category_id, sub_category_id,
    source_type, payment_status, status_, date_from, date_to,
):
    if project_id:
        q = q.filter(Expense.project_id == project_id)
    if vendor_id:
        q = q.filter(Expense.vendor_id == vendor_id)
    if employee_id:
        q = q.filter(Expense.employee_id == employee_id)
    if category_id:
        q = q.filter(Expense.category_id == category_id)
    if sub_category_id:
        q = q.filter(Expense.sub_category_id == sub_category_id)
    if source_type:
        q = q.filter(Expense.source_type == source_type)
    if payment_status:
        q = q.filter(Expense.payment_status == payment_status)
    if status_:
        q = q.filter(Expense.status == status_)
    if date_from:
        q = q.filter(Expense.expense_date >= date_from)
    if date_to:
        q = q.filter(Expense.expense_date <= date_to)
    return q


@router.post("", response_model=ExpenseOut, dependencies=[Depends(require_accounts)])
def create_direct_expense(payload: DirectExpenseCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.pay_immediately and (not payload.account_id or not payload.payment_mode or not payload.payment_date):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "account_id, payment_mode, payment_date required to pay immediately")
    if user.role.name == RoleName.ACCOUNTS:
        project_scope_service.assert_project_in_scope(db, user, payload.project_id)

    expense = expense_service.create_expense_record(
        db, source_type=SourceType.EXPENSE, source_id=None, expense_date=payload.expense_date,
        project_id=payload.project_id, vendor_id=None, employee_id=None,
        category_id=payload.category_id, sub_category_id=payload.sub_category_id, description=payload.description,
        base_amount=payload.base_amount, gst_amount=payload.gst_amount, other_amount=payload.other_amount,
        created_by=user.id, supplier_name=payload.supplier_name, bill_number=payload.bill_number,
    )
    if payload.pay_immediately:
        expense_service.pay_expense_immediately(
            db, expense=expense, payment_date=payload.payment_date, account_id=payload.account_id,
            payment_mode=payload.payment_mode, reference_number=payload.reference_number,
            remarks=payload.remarks, created_by=user.id,
        )
    db.commit()
    db.refresh(expense)
    return _to_out(db, expense)


@router.get("", response_model=list[ExpenseOut], dependencies=[Depends(require_non_employee)])
def list_expenses(
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
    project_id: int | None = None, vendor_id: int | None = None, employee_id: int | None = None,
    category_id: int | None = None, sub_category_id: int | None = None,
    source_type: str | None = None, payment_status: str | None = None, status_: str | None = Query(None, alias="status"),
    date_from: str | None = None, date_to: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(500, ge=1, le=500),
    sort_by: str | None = None, sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
):
    # page_size defaults to the old hardcoded cap (500) so existing callers
    # that don't pass page/page_size (e.g. Payments' outstanding-expense
    # picker) keep seeing the full result set - only a caller that opts into
    # a smaller page_size (the Expenses list screen) gets truncated pages.
    q = _apply_filters(
        db.query(Expense), project_id=project_id, vendor_id=vendor_id, employee_id=employee_id,
        category_id=category_id, sub_category_id=sub_category_id, source_type=source_type,
        payment_status=payment_status, status_=status_, date_from=date_from, date_to=date_to,
    )
    if user.role.name == RoleName.ACCOUNTS:
        assigned = project_scope_service.get_accounts_assigned_project_ids(db, user)
        q = q.filter(Expense.project_id.in_(assigned)) if assigned else q.filter(False)
    rows = q.order_by(Expense.expense_date.desc(), Expense.id.desc()).all()
    if sort_by:
        # Sorting (and only then paginating) the FULL filtered set is what
        # makes this a global sort across pages, not just a per-page reorder.
        rows = _sort_rows(db, rows, sort_by, sort_dir)
    page_rows = rows[(page - 1) * page_size: (page - 1) * page_size + page_size]
    return [_to_out(db, e) for e in page_rows]


@router.get("/summary", dependencies=[Depends(require_non_employee)])
def expenses_summary(
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
    project_id: int | None = None, vendor_id: int | None = None, employee_id: int | None = None,
    category_id: int | None = None, sub_category_id: int | None = None,
    source_type: str | None = None, payment_status: str | None = None, status_: str | None = Query(None, alias="status"),
    date_from: str | None = None, date_to: str | None = None,
):
    """Aggregate totals over the FULL filtered result set (not just the
    current page) - backs the pagination count and the amounts summary row
    on the Expenses list screen. Same filters as GET /expenses."""
    q = _apply_filters(
        db.query(Expense), project_id=project_id, vendor_id=vendor_id, employee_id=employee_id,
        category_id=category_id, sub_category_id=sub_category_id, source_type=source_type,
        payment_status=payment_status, status_=status_, date_from=date_from, date_to=date_to,
    )
    if user.role.name == RoleName.ACCOUNTS:
        assigned = project_scope_service.get_accounts_assigned_project_ids(db, user)
        q = q.filter(Expense.project_id.in_(assigned)) if assigned else q.filter(False)
    rows = q.all()
    total_amount = sum((e.total_amount for e in rows), Decimal("0"))
    base_amount = sum((e.base_amount for e in rows), Decimal("0"))
    gst_amount = sum((e.gst_amount for e in rows), Decimal("0"))
    other_amount = sum((e.other_amount for e in rows), Decimal("0"))
    paid_amount = sum((get_paid_amount(db, e.id) for e in rows), Decimal("0"))
    return {
        "count": len(rows),
        "total_amount": total_amount,
        "base_amount": base_amount,
        "gst_amount": gst_amount,
        "other_amount": other_amount,
        "paid_amount": paid_amount,
        "balance_due": total_amount - paid_amount,
    }


def _describe_filters(
    db: Session, *, project_id, vendor_id, employee_id, category_id, sub_category_id,
    source_type, payment_status, status_, date_from, date_to,
) -> str:
    """Human-readable summary of the active filters, printed at the top of
    the PDF so the export is self-documenting (what you see is exactly what
    was selected on screen when it was generated)."""
    parts = []
    if date_from or date_to:
        parts.append(f"Date: {date_from or '…'} to {date_to or '…'}")
    if source_type:
        parts.append(f"Source: {source_type.replace('_', ' ')}")
    if project_id:
        p = db.query(Project).filter(Project.id == project_id).first()
        parts.append(f"Project: {p.name if p else project_id}")
    if vendor_id:
        v = db.query(Vendor).filter(Vendor.id == vendor_id).first()
        parts.append(f"Vendor: {v.vendor_name if v else vendor_id}")
    if employee_id:
        e = db.query(Employee).filter(Employee.id == employee_id).first()
        parts.append(f"Employee: {e.employee_name if e else employee_id}")
    if category_id:
        c = db.query(ExpenseCategory).filter(ExpenseCategory.id == category_id).first()
        parts.append(f"Head: {c.name if c else category_id}")
    if sub_category_id:
        s = db.query(ExpenseSubCategory).filter(ExpenseSubCategory.id == sub_category_id).first()
        parts.append(f"Sub-Head: {s.name if s else sub_category_id}")
    if payment_status:
        parts.append(f"Payment: {payment_status.replace('_', ' ')}")
    if status_:
        parts.append(f"Status: {status_}")
    return "Filters: " + " | ".join(parts) if parts else "Filters: none (all expenses)"


@router.get("/export-pdf", dependencies=[Depends(require_non_employee)])
def export_expenses_pdf(
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
    project_id: int | None = None, vendor_id: int | None = None, employee_id: int | None = None,
    category_id: int | None = None, sub_category_id: int | None = None,
    source_type: str | None = None, payment_status: str | None = None, status_: str | None = Query(None, alias="status"),
    date_from: str | None = None, date_to: str | None = None,
    columns: str | None = Query(None, description="Comma-separated column keys - mirrors the frontend's visible (non-hidden) columns"),
):
    """PDF export of the Expenses list - same filters and the same set of
    visible columns as the on-screen table (whatever the Columns picker has
    showing), not a fixed report layout. Always the full filtered result
    set, not just the current page."""
    q = _apply_filters(
        db.query(Expense), project_id=project_id, vendor_id=vendor_id, employee_id=employee_id,
        category_id=category_id, sub_category_id=sub_category_id, source_type=source_type,
        payment_status=payment_status, status_=status_, date_from=date_from, date_to=date_to,
    )
    if user.role.name == RoleName.ACCOUNTS:
        assigned = project_scope_service.get_accounts_assigned_project_ids(db, user)
        q = q.filter(Expense.project_id.in_(assigned)) if assigned else q.filter(False)
    rows = q.order_by(Expense.expense_date.desc(), Expense.id.desc()).all()

    total_amount = sum((e.total_amount for e in rows), Decimal("0"))
    base_amount = sum((e.base_amount for e in rows), Decimal("0"))
    gst_amount = sum((e.gst_amount for e in rows), Decimal("0"))
    other_amount = sum((e.other_amount for e in rows), Decimal("0"))
    paid_amount = sum((get_paid_amount(db, e.id) for e in rows), Decimal("0"))
    summary = {
        "count": len(rows), "total_amount": total_amount, "base_amount": base_amount,
        "gst_amount": gst_amount, "other_amount": other_amount,
        "paid_amount": paid_amount, "balance_due": total_amount - paid_amount,
    }

    filters_desc = _describe_filters(
        db, project_id=project_id, vendor_id=vendor_id, employee_id=employee_id,
        category_id=category_id, sub_category_id=sub_category_id, source_type=source_type,
        payment_status=payment_status, status_=status_, date_from=date_from, date_to=date_to,
    )
    col_list = [c.strip() for c in columns.split(",") if c.strip()] if columns else None

    pdf_bytes = expense_pdf_service.build_expenses_pdf(
        db, rows, col_list, filters_desc, summary, user.full_name or user.username,
    )
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="expenses-{dt.date.today().isoformat()}.pdf"'},
    )


@router.get("/{expense_id}", response_model=ExpenseOut, dependencies=[Depends(require_non_employee)])
def get_expense(expense_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    e = db.query(Expense).filter(Expense.id == expense_id).first()
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Expense not found")
    if user.role.name == RoleName.ACCOUNTS:
        project_scope_service.assert_project_in_scope(db, user, e.project_id)
    return _to_out(db, e)


@router.put("/{expense_id}", response_model=ExpenseOut, dependencies=[Depends(require_accounts)])
def update_expense(expense_id: int, payload: ExpenseUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Admin/Super Admin edit directly and unconditionally. Accounts may also
    edit directly, in full, as long as the expense hasn't been verified yet -
    once Admin/Super Admin verifies it (see POST .../verify), Accounts is
    locked out and must propose the same edit via POST /edit-requests instead."""
    changes = payload.model_dump(exclude_unset=True)
    if user.role.name == RoleName.ACCOUNTS:
        existing = db.query(Expense).filter(Expense.id == expense_id).first()
        if not existing:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Expense not found")
        project_scope_service.assert_project_in_scope(db, user, existing.project_id)
        e = edit_request_service.accounts_edit(db, "EXPENSE", expense_id, changes, user)
    else:
        e = edit_request_service.direct_edit(db, "EXPENSE", expense_id, changes, user)
    db.commit()
    db.refresh(e)
    return _to_out(db, e)


@router.post("/{expense_id}/verify", response_model=ExpenseOut, dependencies=[Depends(require_admin)])
def verify_expense(expense_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Admin/Super Admin freeze - once verified, Accounts can no longer edit
    this expense directly and must go through the edit-request workflow."""
    e = edit_request_service.set_verification(db, "EXPENSE", expense_id, user, True)
    db.commit()
    db.refresh(e)
    return _to_out(db, e)


@router.post("/{expense_id}/unverify", response_model=ExpenseOut, dependencies=[Depends(require_admin)])
def unverify_expense(expense_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Reverses verify_expense, restoring Accounts' ability to edit directly."""
    e = edit_request_service.set_verification(db, "EXPENSE", expense_id, user, False)
    db.commit()
    db.refresh(e)
    return _to_out(db, e)


@router.delete("/{expense_id}", dependencies=[Depends(require_accounts)])
def delete_expense(expense_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Hard delete - only for an unverified EXPENSE with no payment
    allocated to it (both enforced in expense_service.delete_expense).
    Admin/Super Admin may delete regardless of verification; Accounts is
    locked out once Admin verifies it, same as the edit rules."""
    e = db.query(Expense).filter(Expense.id == expense_id).first()
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Expense not found")
    if user.role.name == RoleName.ACCOUNTS:
        project_scope_service.assert_project_in_scope(db, user, e.project_id)
        if edit_request_service.is_locked_for_accounts("EXPENSE", e):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This expense has been verified by Admin and can no longer be deleted")
    expense_service.delete_expense(db, e, user.id)
    db.commit()
    return {"detail": "Expense deleted"}


@router.post("/{expense_id}/cancel", response_model=ExpenseOut, dependencies=[Depends(require_accounts)])
def cancel_expense(expense_id: int, payload: CancelRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    e = db.query(Expense).filter(Expense.id == expense_id).first()
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Expense not found")
    if user.role.name == RoleName.ACCOUNTS:
        project_scope_service.assert_project_in_scope(db, user, e.project_id)
    expense_service.cancel_expense(db, e, user.id, payload.reason)
    db.commit()
    db.refresh(e)
    return _to_out(db, e)
