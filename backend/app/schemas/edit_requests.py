import datetime as dt
from decimal import Decimal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Direct edit (Admin/Super Admin) - full field set, all optional so a PUT
# can send just the fields being changed. `exclude_unset=True` at the call
# site distinguishes "field omitted" from "field explicitly set to null".
# ---------------------------------------------------------------------------

class ExpenseUpdate(BaseModel):
    expense_date: dt.date | None = None
    project_id: int | None = None
    vendor_id: int | None = None
    employee_id: int | None = None
    category_id: int | None = None
    sub_category_id: int | None = None
    description: str | None = None
    supplier_name: str | None = None
    bill_number: str | None = None
    base_amount: Decimal | None = None
    gst_amount: Decimal | None = None
    other_amount: Decimal | None = None


class InvoiceUpdate(BaseModel):
    invoice_number: str | None = None
    vendor_id: int | None = None
    invoice_date: dt.date | None = None
    due_date: dt.date | None = None
    project_id: int | None = None
    description: str | None = None
    taxable_amount: Decimal | None = None
    cgst: Decimal | None = None
    sgst: Decimal | None = None
    igst: Decimal | None = None
    other_tax: Decimal | None = None
    category_id: int | None = None
    sub_category_id: int | None = None


class PaymentUpdate(BaseModel):
    payment_date: dt.date | None = None
    account_id: int | None = None
    payment_mode: str | None = None
    reference_number: str | None = None
    remarks: str | None = None


# ---------------------------------------------------------------------------
# Edit requests (Accounts proposes, Admin/Super Admin reviews)
# ---------------------------------------------------------------------------

class EditRequestCreate(BaseModel):
    entity_type: str  # EXPENSE | INVOICE | PAYMENT
    entity_id: int
    changes: dict


class EditRequestOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    changes: dict
    previous_values: dict
    status: str
    requested_by: int
    requested_by_name: str | None = None
    requested_at: dt.datetime
    reviewed_by: int | None = None
    reviewed_by_name: str | None = None
    reviewed_at: dt.datetime | None = None
    review_remarks: str | None = None


class EditRequestApprove(BaseModel):
    remarks: str | None = None


class EditRequestReject(BaseModel):
    reason: str
