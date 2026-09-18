import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_accounts, require_non_employee, require_admin
from app.db.session import get_db
from app.models.models import Invoice, Expense, User, Project, Vendor, ExpenseCategory, ExpenseSubCategory
from app.schemas.transactions import InvoiceCreate, InvoiceOut, CancelRequest
from app.schemas.edit_requests import InvoiceUpdate
from app.services import invoice_service, edit_request_service, project_scope_service, invoice_pdf_service
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


_SORT_KEYS = {
    "invoice_number", "vendor_id", "invoice_date", "due_date", "project_id",
    "category_id", "sub_category_id", "taxable_amount", "total_amount", "status",
}


def _sort_rows(rows: list[Invoice], sort_by: str, sort_dir: str) -> list[Invoice]:
    """In-memory sort over the FULL filtered set (called before pagination
    slices it) - needed for name-derived keys (vendor/project/category live
    on related rows, not plain Invoice columns). Mirrors expenses.py's
    _sort_rows for the same reason and at the same small-scale assumption."""
    if sort_by not in _SORT_KEYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown sort_by '{sort_by}'")

    def key(inv: Invoice):
        if sort_by == "invoice_number":
            return inv.invoice_number or ""
        if sort_by == "vendor_id":
            return (inv.vendor.vendor_name if inv.vendor else "").lower()
        if sort_by == "invoice_date":
            return inv.invoice_date
        if sort_by == "due_date":
            return inv.due_date
        if sort_by == "project_id":
            return (inv.project.name if inv.project else "").lower()
        if sort_by == "category_id":
            return (inv.expense.category.name if inv.expense and inv.expense.category else "").lower()
        if sort_by == "sub_category_id":
            return (inv.expense.sub_category.name if inv.expense and inv.expense.sub_category else "").lower()
        if sort_by == "taxable_amount":
            return inv.taxable_amount
        if sort_by == "total_amount":
            return inv.total_amount
        if sort_by == "status":
            return inv.status or ""

    with_value = [r for r in rows if key(r) is not None]
    without_value = [r for r in rows if key(r) is None]
    with_value.sort(key=key, reverse=(sort_dir == "desc"))
    return with_value + without_value


def _apply_filters(
    q, *, vendor_id, project_id, category_id, sub_category_id, status_, date_from, date_to,
):
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
    if category_id or sub_category_id:
        # Category/Sub-Category live on the linked Expense, not Invoice itself.
        q = q.join(Expense, Invoice.expense_id == Expense.id)
        if category_id:
            q = q.filter(Expense.category_id == category_id)
        if sub_category_id:
            q = q.filter(Expense.sub_category_id == sub_category_id)
    return q


@router.post("", response_model=InvoiceOut, dependencies=[Depends(require_accounts)])
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role.name in (RoleName.ACCOUNTS, RoleName.SUPER_ACCOUNTS):
        project_scope_service.assert_project_in_scope(db, user, payload.project_id)
    invoice = invoice_service.create_invoice(
        db, invoice_number=payload.invoice_number, po_number=payload.po_number, vendor_id=payload.vendor_id, invoice_date=payload.invoice_date,
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
    sub_category_id: int | None = None,
    status_: str | None = None, date_from: dt.date | None = None, date_to: dt.date | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(500, ge=1, le=500),
    sort_by: str | None = None, sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
):
    # page_size defaults to the old hardcoded cap (500) so existing callers
    # that don't pass page/page_size keep seeing the full result set - only a
    # caller that opts into a smaller page_size (the Invoices list screen)
    # gets truncated pages.
    q = _apply_filters(
        db.query(Invoice), vendor_id=vendor_id, project_id=project_id, category_id=category_id,
        sub_category_id=sub_category_id, status_=status_, date_from=date_from, date_to=date_to,
    )
    if user.role.name in (RoleName.ACCOUNTS, RoleName.SUPER_ACCOUNTS):
        assigned = project_scope_service.get_accounts_assigned_project_ids(db, user)
        q = q.filter(Invoice.project_id.in_(assigned)) if assigned else q.filter(False)
    rows = q.order_by(Invoice.invoice_date.desc(), Invoice.id.desc()).all()
    if sort_by:
        rows = _sort_rows(rows, sort_by, sort_dir)
    page_rows = rows[(page - 1) * page_size: (page - 1) * page_size + page_size]
    return [_to_out(inv) for inv in page_rows]


@router.get("/summary", dependencies=[Depends(require_non_employee)])
def invoices_summary(
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
    vendor_id: int | None = None, project_id: int | None = None, category_id: int | None = None,
    sub_category_id: int | None = None,
    status_: str | None = None, date_from: dt.date | None = None, date_to: dt.date | None = None,
):
    """Aggregate totals over the FULL filtered result set (not just the
    current page) - backs the pagination count and the amounts summary row
    on the Invoices list screen. Same filters as GET /invoices."""
    q = _apply_filters(
        db.query(Invoice), vendor_id=vendor_id, project_id=project_id, category_id=category_id,
        sub_category_id=sub_category_id, status_=status_, date_from=date_from, date_to=date_to,
    )
    if user.role.name in (RoleName.ACCOUNTS, RoleName.SUPER_ACCOUNTS):
        assigned = project_scope_service.get_accounts_assigned_project_ids(db, user)
        q = q.filter(Invoice.project_id.in_(assigned)) if assigned else q.filter(False)
    rows = q.all()
    taxable_amount = sum((r.taxable_amount for r in rows), Decimal("0"))
    tax_amount = sum((r.cgst + r.sgst + r.igst + r.other_tax for r in rows), Decimal("0"))
    total_amount = sum((r.total_amount for r in rows), Decimal("0"))
    return {
        "count": len(rows), "taxable_amount": taxable_amount,
        "tax_amount": tax_amount, "total_amount": total_amount,
    }


def _describe_filters(
    db: Session, *, vendor_id, project_id, category_id, sub_category_id, status_, date_from, date_to,
) -> str:
    """Human-readable summary of the active filters, printed at the top of
    the PDF so the export is self-documenting."""
    parts = []
    if date_from or date_to:
        parts.append(f"Date: {date_from or '…'} to {date_to or '…'}")
    if vendor_id:
        v = db.query(Vendor).filter(Vendor.id == vendor_id).first()
        parts.append(f"Vendor: {v.vendor_name if v else vendor_id}")
    if project_id:
        p = db.query(Project).filter(Project.id == project_id).first()
        parts.append(f"Project: {p.name if p else project_id}")
    if category_id:
        c = db.query(ExpenseCategory).filter(ExpenseCategory.id == category_id).first()
        parts.append(f"Head: {c.name if c else category_id}")
    if sub_category_id:
        s = db.query(ExpenseSubCategory).filter(ExpenseSubCategory.id == sub_category_id).first()
        parts.append(f"Sub-Head: {s.name if s else sub_category_id}")
    if status_:
        parts.append(f"Status: {status_}")
    return "Filters: " + " | ".join(parts) if parts else "Filters: none (all invoices)"


@router.get("/export-pdf", dependencies=[Depends(require_non_employee)])
def export_invoices_pdf(
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
    vendor_id: int | None = None, project_id: int | None = None, category_id: int | None = None,
    sub_category_id: int | None = None,
    status_: str | None = None, date_from: dt.date | None = None, date_to: dt.date | None = None,
    columns: str | None = Query(None, description="Comma-separated column keys - mirrors the frontend's visible (non-hidden) columns"),
):
    """PDF export of the Invoices list - same filters and the same set of
    visible columns as the on-screen table. Always the full filtered result
    set, not just the current page."""
    q = _apply_filters(
        db.query(Invoice), vendor_id=vendor_id, project_id=project_id, category_id=category_id,
        sub_category_id=sub_category_id, status_=status_, date_from=date_from, date_to=date_to,
    )
    if user.role.name in (RoleName.ACCOUNTS, RoleName.SUPER_ACCOUNTS):
        assigned = project_scope_service.get_accounts_assigned_project_ids(db, user)
        q = q.filter(Invoice.project_id.in_(assigned)) if assigned else q.filter(False)
    rows = q.order_by(Invoice.invoice_date.desc(), Invoice.id.desc()).all()

    taxable_amount = sum((r.taxable_amount for r in rows), Decimal("0"))
    tax_amount = sum((r.cgst + r.sgst + r.igst + r.other_tax for r in rows), Decimal("0"))
    total_amount = sum((r.total_amount for r in rows), Decimal("0"))
    summary = {"count": len(rows), "taxable_amount": taxable_amount, "tax_amount": tax_amount, "total_amount": total_amount}

    filters_desc = _describe_filters(
        db, vendor_id=vendor_id, project_id=project_id, category_id=category_id,
        sub_category_id=sub_category_id, status_=status_, date_from=date_from, date_to=date_to,
    )
    col_list = [c.strip() for c in columns.split(",") if c.strip()] if columns else None

    pdf_bytes = invoice_pdf_service.build_invoices_pdf(rows, col_list, filters_desc, summary, user.full_name or user.username)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="invoices-{dt.date.today().isoformat()}.pdf"'},
    )


@router.get("/{invoice_id}", response_model=InvoiceOut, dependencies=[Depends(require_non_employee)])
def get_invoice(invoice_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    if user.role.name in (RoleName.ACCOUNTS, RoleName.SUPER_ACCOUNTS):
        project_scope_service.assert_project_in_scope(db, user, inv.project_id)
    return _to_out(inv)


@router.put("/{invoice_id}", response_model=InvoiceOut, dependencies=[Depends(require_accounts)])
def update_invoice(invoice_id: int, payload: InvoiceUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Admin/Super Admin edit directly and unconditionally. Accounts may also
    edit directly, in full, until the underlying expense is verified (see
    POST /expenses/{id}/verify) - after that, Accounts must propose the same
    edit via POST /edit-requests instead."""
    changes = payload.model_dump(exclude_unset=True)
    if user.role.name in (RoleName.ACCOUNTS, RoleName.SUPER_ACCOUNTS):
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


@router.delete("/{invoice_id}", dependencies=[Depends(require_accounts)])
def delete_invoice(invoice_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Hard delete - only while unverified. Deletes the invoice and its
    linked Expense together (see invoice_service.delete_invoice). If a
    payment has been recorded against it, 400s asking to delete the payment
    first - see DELETE /payments/{id}."""
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    if user.role.name in (RoleName.ACCOUNTS, RoleName.SUPER_ACCOUNTS):
        project_scope_service.assert_project_in_scope(db, user, inv.project_id)
        if edit_request_service.is_locked_for_accounts("INVOICE", inv):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This invoice has been verified by Admin and can no longer be deleted")
    invoice_service.delete_invoice(db, inv, user.id)
    db.commit()
    return {"detail": "Invoice deleted"}


@router.post("/{invoice_id}/cancel", response_model=InvoiceOut, dependencies=[Depends(require_accounts)])
def cancel_invoice(invoice_id: int, payload: CancelRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    if user.role.name in (RoleName.ACCOUNTS, RoleName.SUPER_ACCOUNTS):
        project_scope_service.assert_project_in_scope(db, user, inv.project_id)
    invoice_service.cancel_invoice(db, inv, user.id, payload.reason)
    db.commit()
    db.refresh(inv)
    return inv
