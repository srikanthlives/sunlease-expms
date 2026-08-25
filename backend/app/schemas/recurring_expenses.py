import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, model_validator


class RecurringExpenseCreate(BaseModel):
    name: str
    frequency: str  # RecurrenceFrequency
    amount_type: str  # RecurringAmountType
    fixed_amount: Decimal | None = None
    lead_days: int = 7
    due_in_days: int | None = None
    payee_type: str  # RecurringPayeeType
    supplier_name: str | None = None
    project_id: int
    vendor_id: int | None = None
    employee_id: int | None = None
    category_id: int
    sub_category_id: int | None = None
    description: str | None = None
    next_occurrence_date: dt.date
    is_active: bool = True

    @model_validator(mode="after")
    def cross_field_requirements(self):
        # A field_validator on a field that's *missing* from the payload
        # (using its default) doesn't run by default in Pydantic v2 - a
        # model_validator(mode="after") always sees the fully-defaulted
        # model, so it's the reliable place for these cross-field checks.
        if self.amount_type == "FIXED" and (self.fixed_amount is None or self.fixed_amount <= 0):
            raise ValueError("fixed_amount is required and must be greater than zero for a FIXED recurring expense")
        if self.payee_type == "DIRECT" and not self.supplier_name:
            raise ValueError("supplier_name is required for a Direct Expense recurring expense")
        if self.payee_type == "VENDOR" and not self.vendor_id:
            raise ValueError("vendor_id is required for a Vendor Expense recurring expense")
        if self.payee_type == "EMPLOYEE" and not self.employee_id:
            raise ValueError("employee_id is required for an Employee Expense recurring expense")
        return self


class RecurringExpenseOut(BaseModel):
    id: int
    name: str
    frequency: str
    amount_type: str
    fixed_amount: Decimal | None = None
    lead_days: int
    due_in_days: int | None = None
    payee_type: str
    supplier_name: str | None = None
    project_id: int
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
    bill_number: str | None = None
    description: str | None = None
    status: str
    amount_type: str | None = None
    payee_type: str | None = None
    supplier_name: str | None = None
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
    bill_number: str | None = None
    remarks: str | None = None


class InstanceRejectRequest(BaseModel):
    reason: str
