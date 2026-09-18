import datetime as dt
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.enums import (
    AuditAction, RecurrenceFrequency, RecurringAmountType, RecurringInstanceStatus, RecurringPayeeType, RoleName, SourceType,
)
from app.models.models import RecurringExpense, RecurringExpenseInstance, User
from app.services import audit_service, expense_service, invoice_service

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
    if user.role.name not in (RoleName.SUPER_ADMIN, RoleName.ADMIN, RoleName.ACCOUNTS, RoleName.SUPER_ACCOUNTS):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to review this instance")


def accounts_review(
    db: Session, instance: RecurringExpenseInstance, actor: User, amount: Decimal | None,
    bill_number: str | None = None, description: str | None = None, remarks: str | None = None,
    cgst: Decimal | None = None, sgst: Decimal | None = None, igst: Decimal | None = None, other_tax: Decimal | None = None,
) -> RecurringExpenseInstance:
    """Accounts fills in (OPEN type) or corrects (FIXED type) the actual bill
    amount, records the voucher/bill number off the physical bill (not known
    until now, since the recurring template is set up ahead of any actual
    bill arriving), can adjust the description and GST/other-tax breakdown,
    and confirms it - this is final, no separate Admin approval step. Posts
    as an Invoice (VENDOR payee) or a direct Expense (DIRECT payee),
    depending on the template's payee_type."""
    if instance.status != RecurringInstanceStatus.PENDING_ACCOUNTS_REVIEW:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This instance is not awaiting Accounts review")
    _assert_accounts_reviewer(actor)
    if amount is not None:
        instance.amount = amount
    if instance.amount is None or instance.amount <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "An amount is required to confirm this instance")
    if bill_number is not None:
        instance.bill_number = bill_number
    if description is not None:
        instance.description = description
    if cgst is not None:
        instance.cgst = cgst
    if sgst is not None:
        instance.sgst = sgst
    if igst is not None:
        instance.igst = igst
    if other_tax is not None:
        instance.other_tax = other_tax

    tpl = instance.recurring_expense
    description_final = instance.description or tpl.description or tpl.name

    if tpl.payee_type == RecurringPayeeType.VENDOR:
        if not instance.bill_number:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "An invoice/bill number is required to record this as an Invoice")
        invoice = invoice_service.create_invoice(
            db, invoice_number=instance.bill_number, vendor_id=tpl.vendor_id, invoice_date=instance.occurrence_date,
            due_date=instance.due_date, project_id=tpl.project_id, description=description_final,
            taxable_amount=instance.amount, cgst=instance.cgst, sgst=instance.sgst, igst=instance.igst, other_tax=instance.other_tax,
            category_id=tpl.category_id, sub_category_id=tpl.sub_category_id, created_by=actor.id,
        )
        instance.invoice_id = invoice.id
        instance.expense_id = invoice.expense_id
        audit_detail = {"stage": "accounts", "invoice_id": invoice.id}
    else:
        expense = expense_service.create_expense_record(
            db, source_type=SourceType.EXPENSE, source_id=instance.id, expense_date=instance.occurrence_date,
            project_id=tpl.project_id, vendor_id=None, employee_id=None,
            category_id=tpl.category_id, sub_category_id=tpl.sub_category_id,
            description=description_final,
            base_amount=instance.amount, gst_amount=instance.cgst, other_amount=instance.other_tax,
            created_by=actor.id, supplier_name=tpl.supplier_name, bill_number=instance.bill_number,
        )
        instance.expense_id = expense.id
        audit_detail = {"stage": "accounts", "expense_id": expense.id}

    instance.status = RecurringInstanceStatus.APPROVED
    instance.accounts_reviewed_by = actor.id
    instance.accounts_reviewed_at = dt.datetime.utcnow()
    db.add(instance)
    audit_detail.update({"amount": str(instance.amount), "bill_number": instance.bill_number, "remarks": remarks})
    audit_service.record(db, "RECURRING_EXPENSE_INSTANCE", instance.id, AuditAction.APPROVE, actor.id, audit_detail)
    return instance


def reject(db: Session, instance: RecurringExpenseInstance, actor: User, reason: str) -> RecurringExpenseInstance:
    if instance.status != RecurringInstanceStatus.PENDING_ACCOUNTS_REVIEW:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This instance is not pending review")
    _assert_accounts_reviewer(actor)
    instance.status = RecurringInstanceStatus.REJECTED
    instance.rejection_reason = reason
    db.add(instance)
    audit_service.record(db, "RECURRING_EXPENSE_INSTANCE", instance.id, AuditAction.REJECT, actor.id, {"reason": reason})
    return instance
