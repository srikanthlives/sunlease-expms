import datetime as dt
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.enums import (
    AuditAction, RecurrenceFrequency, RecurringAmountType, RecurringInstanceStatus, RoleName, SourceType,
)
from app.models.models import RecurringExpense, RecurringExpenseInstance, User
from app.services import audit_service, expense_service

_STEP = {
    RecurrenceFrequency.WEEKLY: relativedelta(weeks=1),
    RecurrenceFrequency.BIWEEKLY: relativedelta(weeks=2),
    RecurrenceFrequency.MONTHLY: relativedelta(months=1),
    RecurrenceFrequency.QUARTERLY: relativedelta(months=3),
    RecurrenceFrequency.HALF_YEARLY: relativedelta(months=6),
    RecurrenceFrequency.ANNUALLY: relativedelta(years=1),
}


def _advance(date_: dt.date, frequency: str) -> dt.date:
    return date_ + _STEP[frequency]


def generate_due_instances(db: Session) -> list[RecurringExpenseInstance]:
    """Lazily materializes an approval instance for any active
    RecurringExpense whose next occurrence has entered its lead window
    (today >= next_occurrence_date - lead_days). There is no background
    scheduler in this app, so this is called opportunistically at the top of
    the recurring-expenses list/pending-review endpoints instead of on a
    cron. A template can be more than one cycle behind (e.g. left inactive
    for a while) - catches up one occurrence at a time."""
    today = dt.date.today()
    created: list[RecurringExpenseInstance] = []
    templates = db.query(RecurringExpense).filter(RecurringExpense.is_active == True).all()  # noqa: E712
    for tpl in templates:
        while today >= tpl.next_occurrence_date - dt.timedelta(days=tpl.lead_days):
            exists = (
                db.query(RecurringExpenseInstance)
                .filter(
                    RecurringExpenseInstance.recurring_expense_id == tpl.id,
                    RecurringExpenseInstance.occurrence_date == tpl.next_occurrence_date,
                )
                .first()
            )
            if not exists:
                instance = RecurringExpenseInstance(
                    recurring_expense_id=tpl.id,
                    occurrence_date=tpl.next_occurrence_date,
                    due_date=(tpl.next_occurrence_date + dt.timedelta(days=tpl.due_in_days)) if tpl.due_in_days else None,
                    amount=tpl.fixed_amount if tpl.amount_type == RecurringAmountType.FIXED else None,
                    description=tpl.description,
                    status=RecurringInstanceStatus.PENDING_ACCOUNTS_REVIEW,
                )
                db.add(instance)
                created.append(instance)
            tpl.next_occurrence_date = _advance(tpl.next_occurrence_date, tpl.frequency)
            db.add(tpl)
    if created:
        db.flush()
    return created


def _assert_accounts_reviewer(user: User):
    if user.role.name not in (RoleName.SUPER_ADMIN, RoleName.ADMIN, RoleName.ACCOUNTS):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to review this instance")


def _assert_admin_reviewer(user: User):
    if user.role.name not in (RoleName.SUPER_ADMIN, RoleName.ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Admin/Super Admin may give final approval")


def accounts_review(
    db: Session, instance: RecurringExpenseInstance, actor: User, amount: Decimal | None,
    bill_number: str | None = None, remarks: str | None = None,
) -> RecurringExpenseInstance:
    """Accounts fills in (OPEN type) or corrects (FIXED type) the actual bill
    amount, records the voucher/bill number off the physical bill (not known
    until now, since the recurring template is set up ahead of any actual
    bill arriving), and sends it on to Admin for final approval."""
    if instance.status != RecurringInstanceStatus.PENDING_ACCOUNTS_REVIEW:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This instance is not awaiting Accounts review")
    _assert_accounts_reviewer(actor)
    if amount is not None:
        instance.amount = amount
    if instance.amount is None or instance.amount <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "An amount is required before this can go to Admin for approval")
    if bill_number is not None:
        instance.bill_number = bill_number
    instance.status = RecurringInstanceStatus.PENDING_ADMIN_APPROVAL
    instance.accounts_reviewed_by = actor.id
    instance.accounts_reviewed_at = dt.datetime.utcnow()
    db.add(instance)
    audit_service.record(
        db, "RECURRING_EXPENSE_INSTANCE", instance.id, AuditAction.APPROVE, actor.id,
        {"stage": "accounts", "amount": str(instance.amount), "bill_number": instance.bill_number, "remarks": remarks},
    )
    return instance


def admin_approve(db: Session, instance: RecurringExpenseInstance, actor: User) -> RecurringExpenseInstance:
    """Final approval - creates the actual Expense record, exactly like any
    other direct expense, ready for payment via the normal Payments flow."""
    if instance.status != RecurringInstanceStatus.PENDING_ADMIN_APPROVAL:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This instance is not awaiting Admin approval")
    _assert_admin_reviewer(actor)
    tpl = instance.recurring_expense
    expense = expense_service.create_expense_record(
        db, source_type=SourceType.RECURRING_EXPENSE, source_id=instance.id, expense_date=instance.occurrence_date,
        project_id=tpl.project_id, vendor_id=tpl.vendor_id, employee_id=tpl.employee_id,
        category_id=tpl.category_id, sub_category_id=tpl.sub_category_id,
        description=instance.description or tpl.description or tpl.name,
        base_amount=instance.amount, gst_amount=Decimal("0"), other_amount=Decimal("0"),
        created_by=actor.id, supplier_name=tpl.supplier_name, bill_number=instance.bill_number,
    )
    instance.status = RecurringInstanceStatus.APPROVED
    instance.admin_reviewed_by = actor.id
    instance.admin_reviewed_at = dt.datetime.utcnow()
    instance.expense_id = expense.id
    db.add(instance)
    audit_service.record(
        db, "RECURRING_EXPENSE_INSTANCE", instance.id, AuditAction.APPROVE, actor.id,
        {"stage": "admin", "expense_id": expense.id},
    )
    return instance


def reject(db: Session, instance: RecurringExpenseInstance, actor: User, reason: str) -> RecurringExpenseInstance:
    if instance.status not in (RecurringInstanceStatus.PENDING_ACCOUNTS_REVIEW, RecurringInstanceStatus.PENDING_ADMIN_APPROVAL):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This instance is not pending review")
    if instance.status == RecurringInstanceStatus.PENDING_ACCOUNTS_REVIEW:
        _assert_accounts_reviewer(actor)
    else:
        _assert_admin_reviewer(actor)
    instance.status = RecurringInstanceStatus.REJECTED
    instance.rejection_reason = reason
    db.add(instance)
    audit_service.record(db, "RECURRING_EXPENSE_INSTANCE", instance.id, AuditAction.REJECT, actor.id, {"reason": reason})
    return instance
