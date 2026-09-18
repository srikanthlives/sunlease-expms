import datetime as dt
from decimal import Decimal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Quotations
# ---------------------------------------------------------------------------

class QuotationCreate(BaseModel):
    quotation_number: str
    customer_name: str
    project_id: int | None = None
    quotation_date: dt.date
    valid_until: dt.date | None = None
    description: str | None = None
    taxable_amount: Decimal
    cgst: Decimal = Decimal("0")
    sgst: Decimal = Decimal("0")
    igst: Decimal = Decimal("0")
    other_tax: Decimal = Decimal("0")


class QuotationOut(BaseModel):
    id: int
    quotation_number: str
    customer_name: str
    project_id: int | None = None
    project_name: str | None = None
    quotation_date: dt.date
    valid_until: dt.date | None = None
    description: str | None = None
    taxable_amount: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    other_tax: Decimal
    total_amount: Decimal
    status: str
    rejection_reason: str | None = None
    receivable_invoice_id: int | None = None
    receivable_invoice_number: str | None = None
    created_at: dt.datetime

    class Config:
        from_attributes = True


class QuotationRejectRequest(BaseModel):
    reason: str | None = None


class QuotationConvertRequest(BaseModel):
    invoice_number: str
    invoice_date: dt.date
    due_date: dt.date | None = None


# ---------------------------------------------------------------------------
# Receivable Invoices
# ---------------------------------------------------------------------------

class ReceivableInvoiceCreate(BaseModel):
    invoice_number: str
    customer_name: str
    project_id: int | None = None
    invoice_date: dt.date
    due_date: dt.date | None = None
    po_number: str | None = None
    description: str | None = None
    taxable_amount: Decimal
    cgst: Decimal = Decimal("0")
    sgst: Decimal = Decimal("0")
    igst: Decimal = Decimal("0")
    other_tax: Decimal = Decimal("0")


class ReceivableInvoiceOut(BaseModel):
    id: int
    invoice_number: str
    customer_name: str
    project_id: int | None = None
    project_name: str | None = None
    invoice_date: dt.date
    due_date: dt.date | None = None
    quotation_id: int | None = None
    quotation_number: str | None = None
    po_number: str | None = None
    description: str | None = None
    taxable_amount: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    other_tax: Decimal
    total_amount: Decimal
    status: str
    payment_status: str
    paid_amount: Decimal = Decimal("0")
    balance_due: Decimal = Decimal("0")
    created_at: dt.datetime

    class Config:
        from_attributes = True


class ReceivableCancelRequest(BaseModel):
    reason: str | None = None


# ---------------------------------------------------------------------------
# Receivable Payments
# ---------------------------------------------------------------------------

class ReceivablePaymentAllocationIn(BaseModel):
    receivable_invoice_id: int
    allocated_amount: Decimal


class ReceivablePaymentCreate(BaseModel):
    payment_date: dt.date
    account_id: int
    payment_mode: str
    reference_number: str | None = None
    remarks: str | None = None
    allocations: list[ReceivablePaymentAllocationIn]


class ReceivablePaymentUpdate(BaseModel):
    # Amount and allocations are deliberately not editable here, same rule
    # as the outgoing Payment module - changing them would require
    # re-validating every allocation against each invoice's current
    # outstanding balance. Amount corrections go through delete + re-record.
    payment_date: dt.date | None = None
    account_id: int | None = None
    payment_mode: str | None = None
    reference_number: str | None = None
    remarks: str | None = None


class ReceivablePaymentAllocationOut(BaseModel):
    id: int
    receivable_invoice_id: int
    invoice_number: str | None = None
    allocated_amount: Decimal

    class Config:
        from_attributes = True


class ReceivablePaymentOut(BaseModel):
    id: int
    payment_number: str
    payment_date: dt.date
    account_id: int
    payment_mode: str
    amount: Decimal
    reference_number: str | None = None
    remarks: str | None = None
    is_cancelled: bool
    allocations: list[ReceivablePaymentAllocationOut] = []
    created_at: dt.datetime

    class Config:
        from_attributes = True
