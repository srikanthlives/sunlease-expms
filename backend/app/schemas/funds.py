"""Request bodies for the Funds module. Kept out of routers/funds.py so the
bulk-import service can build the same TransferIn the API uses, and so run
through exactly the same validation."""
import datetime as dt
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.common import LongText, OptLongText


class EntityIn(BaseModel):
    name: str
    notes: OptLongText = None
    is_active: bool = True


class FundAccountIn(BaseModel):
    account_name: str
    account_type: str
    account_number: str | None = None
    bank_name: str | None = None
    ifsc: str | None = None
    funding_entity_id: int | None = None
    opening_balance: Decimal = Decimal(0)
    is_active: bool = True


class TransferIn(BaseModel):
    kind: str  # FUNDING / REPAYMENT / TRANSFER
    transfer_date: dt.date
    from_account_id: int | None = None
    to_account_id: int | None = None
    # FUNDING/REPAYMENT only; defaults to the involved account's own entity
    funding_entity_id: int | None = None
    funding_type: str | None = None  # LOAN / CAPITAL / ADVANCE / OTHER
    amount: Decimal
    # Mandatory when editing a VERIFIED transfer; ignored otherwise.
    edit_reason: OptLongText = None
    reference_number: str | None = None
    remarks: OptLongText = None


class CancelIn(BaseModel):
    reason: LongText
