from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_accounts, require_admin
from app.db.session import get_db
from app.models.enums import RecurringAmountType, RecurringInstanceStatus, RoleName
from app.models.models import RecurringExpense, RecurringExpenseInstance, User
from app.schemas.recurring_expenses import (
    InstanceRejectRequest, InstanceReviewRequest, RecurringExpenseCreate, RecurringExpenseInstanceOut, RecurringExpenseOut,
)
from app.services import recurring_expense_service

router = APIRouter(prefix="/api/v1/recurring-expenses", tags=["recurring-expenses"])


def _reviewer_name(u: User | None) -> str | None:
    return (u.full_name or u.username) if u else None


def _instance_to_out(i: RecurringExpenseInstance) -> RecurringExpenseInstanceOut:
    tpl = i.recurring_expense
    return RecurringExpenseInstanceOut(
        id=i.id, recurring_expense_id=i.recurring_expense_id, recurring_expense_name=tpl.name if tpl else None,
        occurrence_date=i.occurrence_date, due_date=i.due_date, amount=i.amount, description=i.description,
        status=i.status, amount_type=tpl.amount_type if tpl else None,
        project_id=tpl.project_id if tpl else None, vendor_id=tpl.vendor_id if tpl else None,
        employee_id=tpl.employee_id if tpl else None, category_id=tpl.category_id if tpl else None,
        sub_category_id=tpl.sub_category_id if tpl else None,
        accounts_reviewed_by=i.accounts_reviewed_by, accounts_reviewed_by_name=_reviewer_name(i.accounts_reviewer),
        accounts_reviewed_at=i.accounts_reviewed_at,
        admin_reviewed_by=i.admin_reviewed_by, admin_reviewed_by_name=_reviewer_name(i.admin_reviewer),
        admin_reviewed_at=i.admin_reviewed_at, rejection_reason=i.rejection_reason,
        expense_id=i.expense_id, expense_number=i.expense.expense_number if i.expense else None,
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
    tpl = RecurringExpense(**payload.model_dump(), created_by=user.id)
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


@router.get("", response_model=list[RecurringExpenseOut], dependencies=[Depends(require_accounts)])
def list_recurring_expenses(db: Session = Depends(get_db), is_active: bool | None = None):
    recurring_expense_service.generate_due_instances(db)
    db.commit()
    q = db.query(RecurringExpense)
    if is_active is not None:
        q = q.filter(RecurringExpense.is_active == is_active)
    return q.order_by(RecurringExpense.name).all()


@router.get("/{template_id}", response_model=RecurringExpenseOut, dependencies=[Depends(require_accounts)])
def get_recurring_expense(template_id: int, db: Session = Depends(get_db)):
    tpl = db.query(RecurringExpense).filter(RecurringExpense.id == template_id).first()
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recurring expense not found")
    return tpl


@router.put("/{template_id}", response_model=RecurringExpenseOut, dependencies=[Depends(require_accounts)])
def update_recurring_expense(template_id: int, payload: RecurringExpenseCreate, db: Session = Depends(get_db)):
    tpl = db.query(RecurringExpense).filter(RecurringExpense.id == template_id).first()
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recurring expense not found")
    if payload.frequency not in ("WEEKLY", "BIWEEKLY", "MONTHLY", "QUARTERLY", "HALF_YEARLY", "ANNUALLY"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid frequency")
    if payload.amount_type not in RecurringAmountType.ALL:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid amount_type")
    for field, value in payload.model_dump().items():
        setattr(tpl, field, value)
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


@router.post("/{template_id}/deactivate", response_model=RecurringExpenseOut, dependencies=[Depends(require_accounts)])
def deactivate_recurring_expense(template_id: int, db: Session = Depends(get_db)):
    tpl = db.query(RecurringExpense).filter(RecurringExpense.id == template_id).first()
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recurring expense not found")
    tpl.is_active = False
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


@router.post("/{template_id}/activate", response_model=RecurringExpenseOut, dependencies=[Depends(require_accounts)])
def activate_recurring_expense(template_id: int, db: Session = Depends(get_db)):
    tpl = db.query(RecurringExpense).filter(RecurringExpense.id == template_id).first()
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recurring expense not found")
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
    q = db.query(RecurringExpenseInstance)
    if user.role.name == RoleName.ACCOUNTS:
        q = q.filter(RecurringExpenseInstance.status == RecurringInstanceStatus.PENDING_ACCOUNTS_REVIEW)
    else:
        q = q.filter(RecurringExpenseInstance.status.in_(
            [RecurringInstanceStatus.PENDING_ACCOUNTS_REVIEW, RecurringInstanceStatus.PENDING_ADMIN_APPROVAL]
        ))
    rows = q.order_by(RecurringExpenseInstance.occurrence_date).all()
    return [_instance_to_out(i) for i in rows]


@router.get("/instances", response_model=list[RecurringExpenseInstanceOut], dependencies=[Depends(require_accounts)])
def list_instances(db: Session = Depends(get_db), recurring_expense_id: int | None = None, status_: str | None = None):
    recurring_expense_service.generate_due_instances(db)
    db.commit()
    q = db.query(RecurringExpenseInstance)
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
    recurring_expense_service.accounts_review(db, instance, user, payload.amount, payload.remarks)
    db.commit()
    db.refresh(instance)
    return _instance_to_out(instance)


@router.post("/instances/{instance_id}/admin-approve", response_model=RecurringExpenseInstanceOut, dependencies=[Depends(require_admin)])
def approve_instance(instance_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    instance = db.query(RecurringExpenseInstance).filter(RecurringExpenseInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Instance not found")
    recurring_expense_service.admin_approve(db, instance, user)
    db.commit()
    db.refresh(instance)
    return _instance_to_out(instance)


@router.post("/instances/{instance_id}/reject", response_model=RecurringExpenseInstanceOut, dependencies=[Depends(require_accounts)])
def reject_instance(instance_id: int, payload: InstanceRejectRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    instance = db.query(RecurringExpenseInstance).filter(RecurringExpenseInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Instance not found")
    recurring_expense_service.reject(db, instance, user, payload.reason)
    db.commit()
    db.refresh(instance)
    return _instance_to_out(instance)
