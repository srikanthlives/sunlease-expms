import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import require_super_admin
from app.db.session import get_db
from app.models.models import Account, FundingEntity, FundTransfer, Payment, ReceivablePayment, User
from app.services import audit_service

# Entire module is Super Admin only.
router = APIRouter(prefix="/api/v1/funds", tags=["funds"], dependencies=[Depends(require_super_admin)])

D = Decimal


class EntityIn(BaseModel):
    name: str
    notes: str | None = None
    is_active: bool = True


class FundAccountIn(BaseModel):
    account_name: str
    account_type: str
    account_number: str | None = None
    bank_name: str | None = None
    ifsc: str | None = None
    funding_entity_id: int | None = None
    opening_balance: Decimal = D(0)
    is_active: bool = True


class TransferIn(BaseModel):
    kind: str  # FUNDING / TRANSFER
    transfer_date: dt.date
    from_account_id: int | None = None
    to_account_id: int
    funding_entity_id: int | None = None  # FUNDING only; defaults to the account's entity
    amount: Decimal
    reference_number: str | None = None
    remarks: str | None = None


class CancelIn(BaseModel):
    reason: str


def _entity_out(e: FundingEntity):
    return {"id": e.id, "name": e.name, "notes": e.notes, "is_active": e.is_active,
            "account_count": len(e.accounts)}


def _account_out(a: Account):
    return {
        "id": a.id, "account_name": a.account_name, "account_type": a.account_type,
        "account_number": a.account_number, "bank_name": a.bank_name, "ifsc": a.ifsc,
        "is_active": a.is_active, "funding_entity_id": a.funding_entity_id,
        "funding_entity_name": a.funding_entity.name if a.funding_entity else None,
        "opening_balance": float(a.opening_balance or 0),
    }


def _transfer_out(t: FundTransfer):
    return {
        "id": t.id, "transfer_number": t.transfer_number, "transfer_date": t.transfer_date,
        "kind": t.kind, "amount": float(t.amount),
        "from_account_id": t.from_account_id,
        "from_account_name": t.from_account.account_name if t.from_account else None,
        "to_account_id": t.to_account_id, "to_account_name": t.to_account.account_name,
        "funding_entity_id": t.funding_entity_id,
        "funding_entity_name": t.funding_entity.name if t.funding_entity else None,
        "reference_number": t.reference_number, "remarks": t.remarks,
        "is_cancelled": t.is_cancelled, "cancel_reason": t.cancel_reason,
    }


# ---- Funding entities ----
@router.get("/entities")
def list_entities(db: Session = Depends(get_db)):
    return [_entity_out(e) for e in db.query(FundingEntity).order_by(FundingEntity.name)]


def _check_entity_name(db, name, exclude_id=None):
    q = db.query(FundingEntity).filter(func.lower(FundingEntity.name) == name.strip().lower())
    if exclude_id:
        q = q.filter(FundingEntity.id != exclude_id)
    if q.first():
        raise HTTPException(400, "A funding entity with this name already exists")


@router.post("/entities")
def create_entity(p: EntityIn, db: Session = Depends(get_db), user: User = Depends(require_super_admin)):
    if not p.name.strip():
        raise HTTPException(400, "Name is required")
    _check_entity_name(db, p.name)
    e = FundingEntity(name=p.name.strip(), notes=p.notes, is_active=p.is_active)
    db.add(e)
    db.flush()
    audit_service.record(db, "FUNDING_ENTITY", e.id, "CREATE", user.id, {"name": e.name})
    db.commit()
    db.refresh(e)
    return _entity_out(e)


@router.put("/entities/{entity_id}")
def update_entity(entity_id: int, p: EntityIn, db: Session = Depends(get_db), user: User = Depends(require_super_admin)):
    e = db.get(FundingEntity, entity_id)
    if not e:
        raise HTTPException(404, "Funding entity not found")
    _check_entity_name(db, p.name, entity_id)
    e.name, e.notes, e.is_active = p.name.strip(), p.notes, p.is_active
    audit_service.record(db, "FUNDING_ENTITY", e.id, "UPDATE", user.id, p.model_dump())
    db.commit()
    db.refresh(e)
    return _entity_out(e)


# ---- Accounts (with entity + opening balance) ----
def _validate_entity(db, entity_id):
    if entity_id is not None and not db.get(FundingEntity, entity_id):
        raise HTTPException(400, "Funding entity not found")


@router.get("/accounts")
def list_accounts(db: Session = Depends(get_db)):
    return [_account_out(a) for a in db.query(Account).order_by(Account.account_name)]


@router.post("/accounts")
def create_account(p: FundAccountIn, db: Session = Depends(get_db), user: User = Depends(require_super_admin)):
    _validate_entity(db, p.funding_entity_id)
    a = Account(**p.model_dump())
    db.add(a)
    db.flush()
    audit_service.record(db, "ACCOUNT", a.id, "CREATE", user.id, p.model_dump())
    db.commit()
    db.refresh(a)
    return _account_out(a)


@router.put("/accounts/{account_id}")
def update_account(account_id: int, p: FundAccountIn, db: Session = Depends(get_db), user: User = Depends(require_super_admin)):
    a = db.get(Account, account_id)
    if not a:
        raise HTTPException(404, "Account not found")
    _validate_entity(db, p.funding_entity_id)
    for k, v in p.model_dump().items():
        setattr(a, k, v)
    audit_service.record(db, "ACCOUNT", a.id, "UPDATE", user.id, p.model_dump())
    db.commit()
    db.refresh(a)
    return _account_out(a)


# ---- Transfers / funding ----
@router.get("/transfers")
def list_transfers(
    account_id: int | None = None, funding_entity_id: int | None = None,
    date_from: dt.date | None = None, date_to: dt.date | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(FundTransfer)
    if account_id:
        q = q.filter((FundTransfer.from_account_id == account_id) | (FundTransfer.to_account_id == account_id))
    if funding_entity_id:
        q = q.filter(FundTransfer.funding_entity_id == funding_entity_id)
    if date_from:
        q = q.filter(FundTransfer.transfer_date >= date_from)
    if date_to:
        q = q.filter(FundTransfer.transfer_date <= date_to)
    return [_transfer_out(t) for t in q.order_by(FundTransfer.transfer_date.desc(), FundTransfer.id.desc())]


def _next_number(db: Session) -> str:
    n = (db.query(func.max(FundTransfer.id)).scalar() or 0) + 1
    while db.query(FundTransfer).filter(FundTransfer.transfer_number == f"FT-{n:05d}").first():
        n += 1
    return f"FT-{n:05d}"


@router.post("/transfers")
def create_transfer(p: TransferIn, db: Session = Depends(get_db), user: User = Depends(require_super_admin)):
    if p.amount <= 0:
        raise HTTPException(400, "Amount must be greater than zero")
    if p.kind not in ("FUNDING", "TRANSFER"):
        raise HTTPException(400, "kind must be FUNDING or TRANSFER")
    to_acc = db.get(Account, p.to_account_id)
    if not to_acc:
        raise HTTPException(400, "Destination account not found")
    entity_id = None
    if p.kind == "TRANSFER":
        if not p.from_account_id or not db.get(Account, p.from_account_id):
            raise HTTPException(400, "Source account is required for a transfer")
        if p.from_account_id == p.to_account_id:
            raise HTTPException(400, "Source and destination accounts must differ")
    else:
        if p.from_account_id:
            raise HTTPException(400, "Funding has no source account")
        entity_id = p.funding_entity_id or to_acc.funding_entity_id
        if not entity_id:
            raise HTTPException(400, "Select the funding entity (this account has none assigned)")
        _validate_entity(db, entity_id)
    t = FundTransfer(
        transfer_number=_next_number(db), transfer_date=p.transfer_date, kind=p.kind,
        from_account_id=p.from_account_id if p.kind == "TRANSFER" else None,
        to_account_id=p.to_account_id, funding_entity_id=entity_id, amount=p.amount,
        reference_number=p.reference_number, remarks=p.remarks, created_by=user.id,
    )
    db.add(t)
    db.flush()
    audit_service.record(db, "FUND_TRANSFER", t.id, "CREATE", user.id,
                         {"kind": t.kind, "amount": p.amount, "from": t.from_account_id, "to": t.to_account_id})
    db.commit()
    db.refresh(t)
    return _transfer_out(t)


@router.post("/transfers/{transfer_id}/cancel")
def cancel_transfer(transfer_id: int, p: CancelIn, db: Session = Depends(get_db), user: User = Depends(require_super_admin)):
    t = db.get(FundTransfer, transfer_id)
    if not t:
        raise HTTPException(404, "Transfer not found")
    if t.is_cancelled:
        raise HTTPException(400, "Already cancelled")
    if not p.reason.strip():
        raise HTTPException(400, "Reason is required")
    t.is_cancelled, t.cancel_reason = True, p.reason.strip()
    audit_service.record(db, "FUND_TRANSFER", t.id, "CANCEL", user.id, {"reason": t.cancel_reason})
    db.commit()
    db.refresh(t)
    return _transfer_out(t)


# ---- Balance sheet ----
@router.get("/balance-sheet")
def balance_sheet(as_of: dt.date | None = Query(None), db: Session = Depends(get_db)):
    """Per-account balance = opening + funding in + transfers in + receipts
    - transfers out - payments, grouped under each funding entity."""
    as_of = as_of or dt.date.today()
    accounts = db.query(Account).order_by(Account.account_name).all()
    rows = {a.id: {
        "id": a.id, "account_name": a.account_name, "account_type": a.account_type,
        "is_active": a.is_active, "funding_entity_id": a.funding_entity_id,
        "opening_balance": D(a.opening_balance or 0), "funded": D(0), "transfers_in": D(0),
        "transfers_out": D(0), "receipts": D(0), "payments": D(0),
    } for a in accounts}

    for t in db.query(FundTransfer).filter(FundTransfer.is_cancelled.is_(False), FundTransfer.transfer_date <= as_of):
        amt = D(t.amount)
        if t.kind == "FUNDING":
            rows[t.to_account_id]["funded"] += amt
        else:
            rows[t.to_account_id]["transfers_in"] += amt
            rows[t.from_account_id]["transfers_out"] += amt
    for acc_id, amt in db.query(Payment.account_id, func.sum(Payment.amount)).filter(
            Payment.is_cancelled.is_(False), Payment.payment_date <= as_of).group_by(Payment.account_id):
        rows[acc_id]["payments"] += D(amt)
    for acc_id, amt in db.query(ReceivablePayment.account_id, func.sum(ReceivablePayment.amount)).filter(
            ReceivablePayment.is_cancelled.is_(False), ReceivablePayment.payment_date <= as_of).group_by(ReceivablePayment.account_id):
        rows[acc_id]["receipts"] += D(amt)

    for r in rows.values():
        r["balance"] = (r["opening_balance"] + r["funded"] + r["transfers_in"] + r["receipts"]
                        - r["transfers_out"] - r["payments"])

    # Funding contributed per entity (the explicit entity on each FUNDING row,
    # which can differ from the receiving account's own entity).
    funded_by_entity: dict[int, Decimal] = {}
    for eid, amt in db.query(FundTransfer.funding_entity_id, func.sum(FundTransfer.amount)).filter(
            FundTransfer.kind == "FUNDING", FundTransfer.is_cancelled.is_(False),
            FundTransfer.transfer_date <= as_of).group_by(FundTransfer.funding_entity_id):
        funded_by_entity[eid] = D(amt)

    keys = ["opening_balance", "funded", "transfers_in", "transfers_out", "receipts", "payments", "balance"]
    def pack(r):
        return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in r.items()}

    groups = []
    entities = db.query(FundingEntity).order_by(FundingEntity.name).all()
    for e in entities:
        accs = [r for r in rows.values() if r["funding_entity_id"] == e.id]
        g = {"entity_id": e.id, "entity_name": e.name,
             "total_funded": float(funded_by_entity.get(e.id, 0)),
             "accounts": [pack(r) for r in accs]}
        for k in keys:
            g[k] = float(sum((r[k] for r in accs), D(0)))
        groups.append(g)
    unassigned = [r for r in rows.values() if r["funding_entity_id"] is None]
    if unassigned or None in funded_by_entity:
        g = {"entity_id": None, "entity_name": "Unassigned",
             "total_funded": float(funded_by_entity.get(None, 0)),
             "accounts": [pack(r) for r in unassigned]}
        for k in keys:
            g[k] = float(sum((r[k] for r in unassigned), D(0)))
        groups.append(g)

    totals = {k: float(sum((r[k] for r in rows.values()), D(0))) for k in keys}
    totals["total_funded"] = float(sum(funded_by_entity.values(), D(0)))
    return {"as_of": as_of, "groups": groups, "totals": totals}
