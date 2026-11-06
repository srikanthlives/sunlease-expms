"""Validation and field-writing for fund transfers, in one place.

Three callers share this: the create endpoint, the edit endpoint and the
bulk spreadsheet import. Keeping the rules here (rather than in the
router, where they started) is what stops the import from drifting into
accepting rows the UI would reject - the same reasoning as
`edit_request_service.apply_changes`.
"""
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import Account, FundingEntity, FundTransfer

#: How a FUNDING/REPAYMENT row is classified. Null on a TRANSFER row.
FUNDING_TYPES = ("LOAN", "CAPITAL", "ADVANCE", "OTHER")

KINDS = ("FUNDING", "REPAYMENT", "TRANSFER")


def validate_entity(db: Session, entity_id: int | None) -> None:
    if entity_id is not None and not db.get(FundingEntity, entity_id):
        raise HTTPException(400, "Funding entity not found")


def next_number(db: Session) -> str:
    n = (db.query(func.max(FundTransfer.id)).scalar() or 0) + 1
    while db.query(FundTransfer).filter(FundTransfer.transfer_number == f"FT-{n:05d}").first():
        n += 1
    return f"FT-{n:05d}"


def resolve_transfer(db: Session, p) -> tuple[int | None, str | None]:
    """Validates a create/update payload (anything with the TransferIn
    attributes) and resolves the funding entity and funding type.
    Returns (funding_entity_id, funding_type)."""
    if p.amount <= 0:
        raise HTTPException(400, "Amount must be greater than zero")
    if p.kind not in KINDS:
        raise HTTPException(400, "kind must be FUNDING, REPAYMENT or TRANSFER")
    if p.funding_type and p.funding_type not in FUNDING_TYPES:
        raise HTTPException(400, f"funding_type must be one of {', '.join(FUNDING_TYPES)}")

    from_acc = db.get(Account, p.from_account_id) if p.from_account_id else None
    to_acc = db.get(Account, p.to_account_id) if p.to_account_id else None

    if p.kind == "TRANSFER":
        if not to_acc:
            raise HTTPException(400, "Destination account not found")
        if not p.from_account_id or not from_acc:
            raise HTTPException(400, "Source account is required for a transfer")
        if p.from_account_id == p.to_account_id:
            raise HTTPException(400, "Source and destination accounts must differ")
        return None, None
    if p.kind == "FUNDING":
        if not to_acc:
            raise HTTPException(400, "Destination account not found")
        if p.from_account_id:
            raise HTTPException(400, "Funding has no source account")
        entity_id = p.funding_entity_id or to_acc.funding_entity_id
        if not entity_id:
            raise HTTPException(400, "Select the funding entity (this account has none assigned)")
    else:  # REPAYMENT - money going back out to a funding entity
        if not from_acc:
            raise HTTPException(400, "Source account is required for a repayment")
        if p.to_account_id:
            raise HTTPException(400, "A repayment has no destination account - it leaves the business")
        entity_id = p.funding_entity_id or from_acc.funding_entity_id
        if not entity_id:
            raise HTTPException(400, "Select the funding entity being repaid (this account has none assigned)")
    validate_entity(db, entity_id)
    return entity_id, (p.funding_type or "LOAN")


def apply_transfer(t: FundTransfer, p, entity_id, funding_type) -> None:
    """Writes a validated payload onto a transfer row, nulling whichever
    account side the kind doesn't use."""
    t.transfer_date = p.transfer_date
    t.kind = p.kind
    t.from_account_id = p.from_account_id if p.kind in ("TRANSFER", "REPAYMENT") else None
    t.to_account_id = p.to_account_id if p.kind in ("TRANSFER", "FUNDING") else None
    t.funding_entity_id = entity_id
    t.funding_type = funding_type
    t.amount = p.amount
    t.reference_number = p.reference_number
    t.remarks = p.remarks


def transfer_audit(t: FundTransfer) -> dict:
    return {"kind": t.kind, "funding_type": t.funding_type, "amount": float(t.amount),
            "date": str(t.transfer_date), "from": t.from_account_id, "to": t.to_account_id,
            "entity": t.funding_entity_id, "reference_number": t.reference_number,
            "remarks": t.remarks}
