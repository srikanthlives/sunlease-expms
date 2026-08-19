import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Expense
# ---------------------------------------------------------------------------

class ExpenseOut(BaseModel):
    id: int
    expense_number: str
    source_type: str
    source_id: int | None = None
    expense_date: dt.date
    project_id: int | None = None
    vendor_id: int | None = None
    employee_id: int | None = None
    category_id: int | None = None
    sub_category_id: int | None = None
    supplier_name: str | None = None
    bill_number: str | None = None
    description: str | None = None
    base_amount: Decimal
    gst_amount: Decimal
    other_amount: Decimal
    total_amount: Decimal
    status: str
    payment_status: str
    paid_amount: Decimal = Decimal("0")
    balance_due: Decimal = Decimal("0")
    created_at: dt.datetime

    class Config:
        from_attributes = True


class DirectExpenseCreate(BaseModel):
    expense_date: dt.date
    project_id: int | None = None
    category_id: int
    sub_category_id: int | None = None
    supplier_name: str | None = None
    bill_number: str | None = None
    description: str | None = None
    base_amount: Decimal
    gst_amount: Decimal = Decimal("0")
    other_amount: Decimal = Decimal("0")

    pay_immediately: bool = False
    payment_date: dt.date | None = None
    account_id: int | None = None
    payment_mode: str | None = None
    reference_number: str | None = None
    remarks: str | None = None

    @field_validator("base_amount")
    @classmethod
    def base_amount_positive(cls, v):
        if v <= 0:
            raise ValueError("base_amount must be greater than zero")
        return v


class CancelRequest(BaseModel):
    reason: str | None = None


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------

class InvoiceCreate(BaseModel):
    invoice_number: str
    vendor_id: int
    invoice_date: dt.date
    due_date: dt.date | None = None
    project_id: int | None = None
    category_id: int
    sub_category_id: int | None = None
    description: str | None = None
    taxable_amount: Decimal
    cgst: Decimal = Decimal("0")
    sgst: Decimal = Decimal("0")
    igst: Decimal = Decimal("0")
    other_tax: Decimal = Decimal("0")

    pay_immediately: bool = False
    payment_date: dt.date | None = None
    account_id: int | None = None
    payment_mode: str | None = None
    reference_number: str | None = None
    remarks: str | None = None


class InvoiceOut(BaseModel):
    id: int
    invoice_number: str
    vendor_id: int
    invoice_date: dt.date
    due_date: dt.date | None = None
    project_id: int | None = None
    category_id: int | None = None
    sub_category_id: int | None = None
    description: str | None = None
    taxable_amount: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    other_tax: Decimal
    total_amount: Decimal
    status: str
    expense_id: int

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Employee Claims
# ---------------------------------------------------------------------------

class ClaimLineIn(BaseModel):
    expense_date: dt.date
    expense_head_id: int
    expense_sub_head_id: int | None = None
    description: str | None = None
    amount: Decimal


class ClaimLineOut(ClaimLineIn):
    id: int
    expense_id: int | None = None

    class Config:
        from_attributes = True


class ClaimCreate(BaseModel):
    employee_id: int
    project_id: int | None = None
    category_id: int
    description: str | None = None
    lines: list[ClaimLineIn]


class ClaimUpdate(BaseModel):
    project_id: int | None = None
    category_id: int
    description: str | None = None
    lines: list[ClaimLineIn]


class ClaimOut(BaseModel):
    id: int
    claim_number: str
    employee_id: int
    claim_date: dt.date
    project_id: int | None = None
    category_id: int | None = None
    description: str | None = None
    total_amount: Decimal
    status: str
    submitted_at: dt.datetime | None = None
    approved_at: dt.datetime | None = None
    rejected_at: dt.datetime | None = None
    rejection_reason: str | None = None
    expense_id: int | None = None
    expense_number: str | None = None
    lines: list[ClaimLineOut] = []

    class Config:
        from_attributes = True


class RejectRequest(BaseModel):
    reason: str


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

class AllocationIn(BaseModel):
    expense_id: int
    allocated_amount: Decimal


class PaymentCreate(BaseModel):
    payment_date: dt.date
    vendor_id: int | None = None
    employee_id: int | None = None
    account_id: int
    payment_mode: str
    reference_number: str | None = None
    remarks: str | None = None
    allocations: list[AllocationIn]


class AllocationOut(BaseModel):
    id: int
    expense_id: int
    allocated_amount: Decimal

    class Config:
        from_attributes = True


class PaymentOut(BaseModel):
    id: int
    payment_number: str
    payment_date: dt.date
    vendor_id: int | None = None
    employee_id: int | None = None
    account_id: int
    payment_mode: str
    amount: Decimal
    reference_number: str | None = None
    remarks: str | None = None
    is_cancelled: bool
    allocations: list[AllocationOut] = []

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

class DocumentOut(BaseModel):
    id: int
    document_type: str
    original_filename: str
    mime_type: str
    file_size: int
    uploaded_at: dt.datetime
    expense_id: int | None = None
    claim_id: int | None = None
    claim_line_id: int | None = None
    invoice_id: int | None = None
    payment_id: int | None = None

    class Config:
        from_attributes = True
