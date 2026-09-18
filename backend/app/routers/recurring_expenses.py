from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from sqlalchemy import or_

import datetime as dt

from app.core.deps import get_current_user, require_accounts, require_admin
from app.db.session import get_db
from app.models.enums import AuditAction, RecurringAmountType, RecurringInstanceStatus, RecurringPayeeType, RoleName
from app.models.models import Project, RecurringExpense, RecurringExpenseInstance, User
from app.schemas.recurring_expenses import (
    InstanceRejectRequest, InstanceReviewRequest, RecurringExpenseCreate, RecurringExpenseInstanceOut, RecurringExpenseOut,
)
from app.services import audit_service, recurring_expense_service, recurring_expense_pdf_service

router = APIRouter(prefix="/api/v1/recurring-expenses", tags=["recurring-expenses"])


def _reviewer_name(u: User | None) -> str | None:
    return (u.full_name or u.username) if u else None


def _restrict_to_accounts_projects(q, user: User, project_id_column):
    """Accounts users only see recurring expenses for projects they're the
    assigned approver of (Project.accounts_approver_id), plus the fallback
    pool of projects with no approver assigned - same rule as claim
    approval routing. Admin/Super Admin keep full visibility."""
    if user.role.name == RoleName.ACCOUNTS:
        q = q.join(Project, project_id_column == Project.id).filter(
            or_(Project.accounts_approver_id == user.id, Project.accounts_approver_id.is_(None))
        )
    return q


def _authorize_template_access(tpl: RecurringExpense, user: User):
    if user.role.name in (RoleName.SUPER_ADMIN, RoleName.ADMIN):
        return
    project = tpl.project
    if project and project.accounts_approver_id and project.accounts_approver_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not the assigned approver for this project")


def _authorize_template_edit(tpl: RecurringExpense, user: User):
    """Same verification-freeze rule as a direct Expense: Accounts may edit
    the template freely until Admin/Super Admin verifies it, after which
    only Admin/Super Admin can change it directly."""
    _authorize_template_access(tpl, user)
    if user.role.name in (RoleName.ACCOUNTS, RoleName.SUPER_ACCOUNTS) and tpl.is_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This recurring expense has been verified by Admin and can no longer be edited directly")


def _instance_to_out(i: RecurringExpenseInstance) -> RecurringExpenseInstanceOut:
    tpl = i.recurring_expense
    return RecurringExpenseInstanceOut(
        id=i.id, recurring_expense_id=i.recurring_expense_id, recurring_expense_name=tpl.name if tpl else None,
        occurrence_date=i.occurrence_date, due_date=i.due_date, amount=i.amount, bill_number=i.bill_number, description=i.description,
        cgst=i.cgst, sgst=i.sgst, igst=i.igst, other_tax=i.other_tax,
        status=i.status, amount_type=tpl.amount_type if tpl else None,
        payee_type=tpl.payee_type if tpl else None, supplier_name=tpl.supplier_name if tpl else None,
        project_id=tpl.project_id if tpl else None, vendor_id=tpl.vendor_id if tpl else None,
        employee_id=tpl.employee_id if tpl else None, category_id=tpl.category_id if tpl else None,
        sub_category_id=tpl.sub_category_id if tpl else None,
        accounts_reviewed_by=i.accounts_reviewed_by, accounts_reviewed_by_name=_reviewer_name(i.accounts_reviewer),
        accounts_reviewed_at=i.accounts_reviewed_at, rejection_reason=i.rejection_reason,
        expense_id=i.expense_id, expense_number=i.expense.expense_number if i.expense else None,
        invoice_id=i.invoice_id, invoice_number=i.invoice.invoice_number if i.invoice else None,
        generated_at=i.generated_at,
    )


# ---------------------------------------------------------------------------
# Templates - Admin/Super Admin/Accounts may create & maintain them, same
# creation rights as other transactional records (expenses/invoices/payments).
# ---------------------------------------------------------------------------

@router.post("", response_model=RecurringExpenseOut, dependencies=[Depends(require_accounts)])
def create_recurring_expense(payload: RecurringExpenseCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.frequency not in ("WEEKLY", "BIWEEKLY", "MONTHLY", "QUARTERLY", "HALF_YEARLY", "ANNUALLY"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid frequency")
    if payload.amount_type not in RecurringAmountType.ALL:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid amount_type")
    if payload.payee_type not in RecurringPayeeType.ALL:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid payee_type")
    tpl = RecurringExpense(**payload.model_dump(), created_by=user.id)
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


@router.get("", response_model=list[RecurringExpenseOut], dependencies=[Depends(require_accounts)])
def list_recurring_expenses(db: Session = Depends(get_db), user: User = Depends(get_current_user), is_active: bool | None = None):
    recurring_expense_service.generate_due_instances(db)
    db.commit()
    q = db.query(RecurringExpense)
    q = _restrict_to_accounts_projects(q, user, RecurringExpense.project_id)
    if is_active is not None:
        q = q.filter(RecurringExpense.is_active == is_active)
    return q.order_by(RecurringExpense.name).all()


@router.delete("/{template_id}", dependencies=[Depends(require_accounts)])
def delete_recurring_expense(template_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Hard delete - only for a template with no generated instances yet
    (an already-billed template must be deactivated instead, so its history
    stays intact). Admin/Super Admin may delete regardless of verification;
    Accounts is locked out once Admin verifies it, same as the edit rule."""
    tpl = db.query(RecurringExpense).filter(RecurringExpense.id == template_id).first()
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recurring expense not found")
    _authorize_template_edit(tpl, user)
    if db.query(RecurringExpenseInstance).filter(RecurringExpenseInstance.recurring_expense_id == template_id).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This recurring expense has already generated billing instances - deactivate it instead of deleting")
    audit_service.record(db, "RECURRING_EXPENSE", tpl.id, AuditAction.DELETE, user.id, {"name": tpl.name})
    db.delete(tpl)
    db.commit()
    return {"detail": "Recurring expense deleted"}


@router.put("/{template_id}", response_model=RecurringExpenseOut, dependencies=[Depends(require_accounts)])
def update_recurring_expense(template_id: int, payload: RecurringExpenseCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = db.query(RecurringExpense).filter(RecurringExpense.id == template_id).first()
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recurring expense not found")
    _authorize_template_edit(tpl, user)
    if payload.frequency not in ("WEEKLY", "BIWEEKLY", "MONTHLY", "QUARTERLY", "HALF_YEARLY", "ANNUALLY"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid frequency")
    if payload.amount_type not in RecurringAmountType.ALL:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid amount_type")
    if payload.payee_type not in RecurringPayeeType.ALL:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid payee_type")
    for field, value in payload.model_dump().items():
        setattr(tpl, field, value)
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


@router.post("/{template_id}/verify", response_model=RecurringExpenseOut, dependencies=[Depends(require_admin)])
def verify_recurring_expense(template_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = db.query(RecurringExpense).filter(RecurringExpense.id == template_id).first()
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recurring expense not found")
    tpl.is_verified = True
    tpl.verified_by = user.id
    tpl.verified_at = dt.datetime.utcnow()
    db.add(tpl)
    audit_service.record(db, "RECURRING_EXPENSE", tpl.id, AuditAction.VERIFY, user.id, {})
    db.commit()
    db.refresh(tpl)
    return tpl


@router.post("/{template_id}/unverify", response_model=RecurringExpenseOut, dependencies=[Depends(require_admin)])
def unverify_recurring_expense(template_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = db.query(RecurringExpense).filter(RecurringExpense.id == template_id).first()
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recurring expense not found")
    tpl.is_verified = False
    tpl.verified_by = None
    tpl.verified_at = None
    db.add(tpl)
    audit_service.record(db, "RECURRING_EXPENSE", tpl.id, AuditAction.UNVERIFY, user.id, {})
    db.commit()
    db.refresh(tpl)
    return tpl


@router.post("/{template_id}/deactivate", response_model=RecurringExpenseOut, dependencies=[Depends(require_accounts)])
def deactivate_recurring_expense(template_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = db.query(RecurringExpense).filter(RecurringExpense.id == template_id).first()
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recurring expense not found")
    _authorize_template_access(tpl, user)
    tpl.is_active = False
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


@router.post("/{template_id}/activate", response_model=RecurringExpenseOut, dependencies=[Depends(require_accounts)])
def activate_recurring_expense(template_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = db.query(RecurringExpense).filter(RecurringExpense.id == template_id).first()
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recurring expense not found")
    _authorize_template_access(tpl, user)
    tpl.is_active = True
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


# ---------------------------------------------------------------------------
# Instances - the approval queue (Accounts review, then Admin approval).
# ---------------------------------------------------------------------------

@router.get("/instances/pending", response_model=list[RecurringExpenseInstanceOut], dependencies=[Depends(require_accounts)])
def list_pending_instances(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    recurring_expense_service.generate_due_instances(db)
    db.commit()
    q = db.query(RecurringExpenseInstance).join(RecurringExpense)
    q = _restrict_to_accounts_projects(q, user, RecurringExpense.project_id)
    q = q.filter(RecurringExpenseInstance.status == RecurringInstanceStatus.PENDING_ACCOUNTS_REVIEW)
    rows = q.order_by(RecurringExpenseInstance.occurrence_date).all()
    return [_instance_to_out(i) for i in rows]


@router.get("/instances", response_model=list[RecurringExpenseInstanceOut], dependencies=[Depends(require_accounts)])
def list_instances(db: Session = Depends(get_db), user: User = Depends(get_current_user), recurring_expense_id: int | None = None, status_: str | None = None):
    recurring_expense_service.generate_due_instances(db)
    db.commit()
    q = db.query(RecurringExpenseInstance).join(RecurringExpense)
    q = _restrict_to_accounts_projects(q, user, RecurringExpense.project_id)
    if recurring_expense_id:
        q = q.filter(RecurringExpenseInstance.recurring_expense_id == recurring_expense_id)
    if status_:
        q = q.filter(RecurringExpenseInstance.status == status_)
    rows = q.order_by(RecurringExpenseInstance.occurrence_date.desc()).limit(500).all()
    return [_instance_to_out(i) for i in rows]


@router.post("/instances/{instance_id}/accounts-review", response_model=RecurringExpenseInstanceOut, dependencies=[Depends(require_accounts)])
def review_instance(instance_id: int, payload: InstanceReviewRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    instance = db.query(RecurringExpenseInstance).filter(RecurringExpenseInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Instance not found")
    _authorize_template_access(instance.recurring_expense, user)
    recurring_expense_service.accounts_review(
        db, instance, user, payload.amount, payload.bill_number, payload.description, payload.remarks,
        payload.cgst, payload.sgst, payload.igst, payload.other_tax,
    )
    db.commit()
    db.refresh(instance)
    return _instance_to_out(instance)


@router.post("/instances/{instance_id}/reject", response_model=RecurringExpenseInstanceOut, dependencies=[Depends(require_accounts)])
def reject_instance(instance_id: int, payload: InstanceRejectRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    instance = db.query(RecurringExpenseInstance).filter(RecurringExpenseInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Instance not found")
    _authorize_template_access(instance.recurring_expense, user)
    recurring_expense_service.reject(db, instance, user, payload.reason)
    db.commit()
    db.refresh(instance)
    return _instance_to_out(instance)


def _describe_filters(is_active: bool | None) -> str:
    if is_active is None:
        return "Filters: none (all recurring expenses)"
    return f"Filters: Status: {'Active' if is_active else 'Inactive'}"


@router.get("/export-pdf", dependencies=[Depends(require_accounts)])
def export_recurring_expenses_pdf(
    db: Session = Depends(get_db), user: User = Depends(get_current_user), is_active: bool | None = None,
    columns: str | None = Query(None, description="Comma-separated column keys - mirrors the frontend's visible (non-hidden) columns"),
):
    """PDF export of the Recurring Expenses template list - same filters and
    the same set of visible columns as the on-screen table."""
    q = db.query(RecurringExpense)
    q = _restrict_to_accounts_projects(q, user, RecurringExpense.project_id)
    if is_active is not None:
        q = q.filter(RecurringExpense.is_active == is_active)
    rows = q.order_by(RecurringExpense.name).all()

    col_list = [c.strip() for c in columns.split(",") if c.strip()] if columns else None
    pdf_bytes = recurring_expense_pdf_service.build_recurring_expenses_pdf(
        rows, col_list, _describe_filters(is_active), len(rows), user.full_name or user.username,
    )
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="recurring-expenses-{dt.date.today().isoformat()}.pdf"'},
    )


# NOTE: this must stay below the more specific "/instances*" routes above -
# FastAPI matches path operations in declaration order, and "/{template_id}"
# would otherwise swallow "/instances" as if "instances" were an id.
@router.get("/{template_id}", response_model=RecurringExpenseOut, dependencies=[Depends(require_accounts)])
def get_recurring_expense(template_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = db.query(RecurringExpense).filter(RecurringExpense.id == template_id).first()
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recurring expense not found")
    _authorize_template_access(tpl, user)
    return tpl
