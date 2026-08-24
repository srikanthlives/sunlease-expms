import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, field_validator


class RecurringExpenseCreate(BaseModel):
    name: str
    frequency: str  # RecurrenceFrequency
    amount_type: str  # RecurringAmountType
    fixed_amount: Decimal | None = None
    lead_days: int = 7
    due_in_days: int | None = None
    project_id: int | None = None
    vendor_id: int | None = None
    employee_id: int | None = None
    category_id: int
    sub_category_id: int | None = None
    description: str | None = None
    next_occurrence_date: dt.date
    is_active: bool = True

    @field_validator("fixed_amount")
    @classmethod
    def fixed_amount_required(cls, v, info):
        if info.data.get("amount_type") == "FIXED" and (v is None or v <= 0):
            raise ValueError("fixed_amount is required and must be greater than zero for a FIXED recurring expense")
        return v


class RecurringExpenseOut(BaseModel):
    id: int
    name: str
    frequency: str
    amount_type: str
    fixed_amount: Decimal | None = None
    lead_days: int
    due_in_days: int | None = None
    project_id: int | None = None
    vendor_id: int | None = None
    employee_id: int | None = None
    category_id: int
    sub_category_id: int | None = None
    description: str | None = None
    next_occurrence_date: dt.date
    is_active: bool
    created_at: dt.datetime

    class Config:
        from_attributes = True


class RecurringExpenseInstanceOut(BaseModel):
    id: int
    recurring_expense_id: int
    recurring_expense_name: str | None = None
    occurrence_date: dt.date
    due_date: dt.date | None = None
    amount: Decimal | None = None
    description: str | None = None
    status: str
    amount_type: str | None = None
    project_id: int | None = None
    vendor_id: int | None = None
    employee_id: int | None = None
    category_id: int | None = None
    sub_category_id: int | None = None
    accounts_reviewed_by: int | None = None
    accounts_reviewed_by_name: str | None = None
    accounts_reviewed_at: dt.datetime | None = None
    admin_reviewed_by: int | None = None
    admin_reviewed_by_name: str | None = None
    admin_reviewed_at: dt.datetime | None = None
    rejection_reason: str | None = None
    expense_id: int | None = None
    expense_number: str | None = None
    generated_at: dt.datetime


class InstanceReviewRequest(BaseModel):
    amount: Decimal | None = None
    remarks: str | None = None


class InstanceRejectRequest(BaseModel):
    reason: str
