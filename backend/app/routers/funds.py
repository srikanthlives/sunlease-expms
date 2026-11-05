import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import require_admin, require_super_admin
from app.db.session import get_db
from app.models.models import Account, FundingEntity, FundTransfer, Payment, ReceivablePayment, User
from app.services import audit_service

# Entire module is Admin / Super Admin only (fund tracking is a
# management view - Accounts, Manager, Employee and Viewer have no access).
router = APIRouter(prefix="/api/v1/funds", tags=["funds"], dependencies=[Depends(require_admin)])

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


FUNDING_TYPES = ("LOAN", "CAPITAL", "ADVANCE", "OTHER")


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
    edit_reason: str | None = None
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
        "to_account_id": t.to_account_id,
        "to_account_name": t.to_account.account_name if t.to_account else None,
        "funding_entity_id": t.funding_entity_id, "funding_type": t.funding_type,
        "funding_entity_name": t.funding_entity.name if t.funding_entity else None,
        "reference_number": t.reference_number, "remarks": t.remarks,
        "is_cancelled": t.is_cancelled, "cancel_reason": t.cancel_reason,
        "is_verified": bool(t.is_verified),
        "verified_by_name": (t.verifier.full_name or t.verifier.username) if t.verifier else None,
        "verified_at": t.verified_at, "last_edit_reason": t.last_edit_reason,
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
def create_entity(p: EntityIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
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
def update_entity(entity_id: int, p: EntityIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
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
def create_account(p: FundAccountIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    _validate_entity(db, p.funding_entity_id)
    a = Account(**p.model_dump())
    db.add(a)
    db.flush()
    audit_service.record(db, "ACCOUNT", a.id, "CREATE", user.id, p.model_dump())
    db.commit()
    db.refresh(a)
    return _account_out(a)


@router.put("/accounts/{account_id}")
def update_account(account_id: int, p: FundAccountIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
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
    kind: str | None = None, funding_type: str | None = None,
    verified: bool | None = None,
    date_from: dt.date | None = None, date_to: dt.date | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(FundTransfer)
    if account_id:
        q = q.filter((FundTransfer.from_account_id == account_id) | (FundTransfer.to_account_id == account_id))
    if funding_entity_id:
        q = q.filter(FundTransfer.funding_entity_id == funding_entity_id)
    if kind:
        q = q.filter(FundTransfer.kind == kind)
    if funding_type:
        q = q.filter(FundTransfer.funding_type == funding_type)
    if verified is not None:
        q = q.filter(FundTransfer.is_verified.is_(verified))
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


def _resolve_transfer(db: Session, p: TransferIn) -> tuple[int | None, str | None]:
    """Validates a create/update payload and resolves the funding entity and
    funding type. Shared by both paths so they can never drift apart in what
    they accept. Returns (funding_entity_id, funding_type)."""
    if p.amount <= 0:
        raise HTTPException(400, "Amount must be greater than zero")
    if p.kind not in ("FUNDING", "REPAYMENT", "TRANSFER"):
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
    _validate_entity(db, entity_id)
    return entity_id, (p.funding_type or "LOAN")


def _apply_transfer(t: FundTransfer, p: TransferIn, entity_id, funding_type) -> None:
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


def _guard_verified(t: FundTransfer, actor: User, reason: str | None, what: str) -> None:
    """A verified transfer is locked. Only a Super Admin may change it, and
    only with a reason - which is stored on the row and in the audit log, so
    there is always a record of why a verified entry was touched."""
    if not t.is_verified:
        return
    if actor.role.name != "SUPER_ADMIN":
        raise HTTPException(403, f"This transfer is verified - only a Super Admin can {what} it")
    if not (reason or "").strip():
        raise HTTPException(400, f"A reason is required to {what} a verified transfer")


def _transfer_audit(t: FundTransfer) -> dict:
    return {"kind": t.kind, "funding_type": t.funding_type, "amount": float(t.amount),
            "date": str(t.transfer_date), "from": t.from_account_id, "to": t.to_account_id,
            "entity": t.funding_entity_id, "reference_number": t.reference_number,
            "remarks": t.remarks}


@router.post("/transfers")
def create_transfer(p: TransferIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    entity_id, funding_type = _resolve_transfer(db, p)
    t = FundTransfer(transfer_number=_next_number(db), created_by=user.id)
    _apply_transfer(t, p, entity_id, funding_type)
    db.add(t)
    db.flush()
    audit_service.record(db, "FUND_TRANSFER", t.id, "CREATE", user.id, _transfer_audit(t))
    db.commit()
    db.refresh(t)
    return _transfer_out(t)


@router.put("/transfers/{transfer_id}")
def update_transfer(transfer_id: int, p: TransferIn, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    """Full-payload edit of a transfer, including switching its kind. The
    transfer number is immutable. A cancelled row is history - it can't be
    edited (record a fresh transfer instead). A VERIFIED row is locked: only
    a Super Admin can edit it, and only with `edit_reason` set. Every edit
    keeps an audit entry holding both the previous and the new values."""
    t = db.get(FundTransfer, transfer_id)
    if not t:
        raise HTTPException(404, "Transfer not found")
    if t.is_cancelled:
        raise HTTPException(400, "A cancelled transfer cannot be edited")
    _guard_verified(t, user, p.edit_reason, "edit")
    entity_id, funding_type = _resolve_transfer(db, p)
    before = _transfer_audit(t)
    was_verified = bool(t.is_verified)
    _apply_transfer(t, p, entity_id, funding_type)
    if was_verified:
        t.last_edit_reason = p.edit_reason.strip()
    db.flush()
    audit_service.record(db, "FUND_TRANSFER", t.id, "UPDATE", user.id,
                         {"before": before, "after": _transfer_audit(t),
                          "verified_at_edit": was_verified,
                          "edit_reason": t.last_edit_reason if was_verified else None})
    db.commit()
    db.refresh(t)
    return _transfer_out(t)


@router.post("/transfers/{transfer_id}/cancel")
def cancel_transfer(transfer_id: int, p: CancelIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    t = db.get(FundTransfer, transfer_id)
    if not t:
        raise HTTPException(404, "Transfer not found")
    if t.is_cancelled:
        raise HTTPException(400, "Already cancelled")
    if not p.reason.strip():
        raise HTTPException(400, "Reason is required")
    # Cancelling is a bigger change than editing, so a verified row is
    # locked against it on the same terms - otherwise the lock would be
    # trivially bypassable by cancel-and-re-enter.
    _guard_verified(t, user, p.reason, "cancel")
    t.is_cancelled, t.cancel_reason = True, p.reason.strip()
    audit_service.record(db, "FUND_TRANSFER", t.id, "CANCEL", user.id, {"reason": t.cancel_reason})
    db.commit()
    db.refresh(t)
    return _transfer_out(t)


# ---- Verification (Super Admin only) ----
@router.post("/transfers/{transfer_id}/verify")
def verify_transfer(transfer_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_super_admin)):
    """Super Admin sign-off. Once verified the transfer is locked: Admin can
    no longer edit or cancel it, and Super Admin may only do so by giving a
    reason (see update_transfer / cancel_transfer)."""
    t = db.get(FundTransfer, transfer_id)
    if not t:
        raise HTTPException(404, "Transfer not found")
    if t.is_cancelled:
        raise HTTPException(400, "A cancelled transfer cannot be verified")
    if t.is_verified:
        raise HTTPException(400, "Already verified")
    t.is_verified, t.verified_by, t.verified_at = True, user.id, dt.datetime.utcnow()
    audit_service.record(db, "FUND_TRANSFER", t.id, "VERIFY", user.id, _transfer_audit(t))
    db.commit()
    db.refresh(t)
    return _transfer_out(t)


@router.post("/transfers/{transfer_id}/unverify")
def unverify_transfer(transfer_id: int, p: CancelIn, db: Session = Depends(get_db),
                      user: User = Depends(require_super_admin)):
    """Reverses verify_transfer, unlocking the row for Admin again. Needs a
    reason, for the same audit-trail reasons as editing a verified row."""
    t = db.get(FundTransfer, transfer_id)
    if not t:
        raise HTTPException(404, "Transfer not found")
    if not t.is_verified:
        raise HTTPException(400, "Not verified")
    if not p.reason.strip():
        raise HTTPException(400, "A reason is required to un-verify a transfer")
    t.is_verified, t.verified_by, t.verified_at = False, None, None
    audit_service.record(db, "FUND_TRANSFER", t.id, "UNVERIFY", user.id, {"reason": p.reason.strip()})
    db.commit()
    db.refresh(t)
    return _transfer_out(t)


# ---- Balance sheet ----
@router.get("/balance-sheet")
def balance_sheet(as_of: dt.date | None = Query(None), db: Session = Depends(get_db)):
    """Per-account balance = opening + funding in + transfers in + receipts
    - transfers out - repayments out - payments, grouped under each funding
    entity. Each entity group also reports total_funded / total_repaid and
    net_funded (what the business still owes / holds from that entity)."""
    as_of = as_of or dt.date.today()
    accounts = db.query(Account).order_by(Account.account_name).all()
    rows = {a.id: {
        "id": a.id, "account_name": a.account_name, "account_type": a.account_type,
        "is_active": a.is_active, "funding_entity_id": a.funding_entity_id,
        "opening_balance": D(a.opening_balance or 0), "funded": D(0), "transfers_in": D(0),
        "transfers_out": D(0), "repaid": D(0), "receipts": D(0), "payments": D(0),
    } for a in accounts}

    for t in db.query(FundTransfer).filter(FundTransfer.is_cancelled.is_(False), FundTransfer.transfer_date <= as_of):
        amt = D(t.amount)
        if t.kind == "FUNDING":
            rows[t.to_account_id]["funded"] += amt
        elif t.kind == "REPAYMENT":
            rows[t.from_account_id]["repaid"] += amt
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
                        - r["transfers_out"] - r["repaid"] - r["payments"])

    # Funding contributed per entity (the explicit entity on each FUNDING row,
    # which can differ from the receiving account's own entity).
    funded_by_entity: dict[int, Decimal] = {}
    repaid_by_entity: dict[int, Decimal] = {}
    for kind, target in (("FUNDING", funded_by_entity), ("REPAYMENT", repaid_by_entity)):
        for eid, amt in db.query(FundTransfer.funding_entity_id, func.sum(FundTransfer.amount)).filter(
                FundTransfer.kind == kind, FundTransfer.is_cancelled.is_(False),
                FundTransfer.transfer_date <= as_of).group_by(FundTransfer.funding_entity_id):
            target[eid] = D(amt)

    # Funding broken down by type (loan vs capital vs advance), per entity.
    by_type: dict[tuple, Decimal] = {}
    for eid, ftype, kind, amt in db.query(
            FundTransfer.funding_entity_id, FundTransfer.funding_type, FundTransfer.kind,
            func.sum(FundTransfer.amount)).filter(
            FundTransfer.kind.in_(("FUNDING", "REPAYMENT")), FundTransfer.is_cancelled.is_(False),
            FundTransfer.transfer_date <= as_of).group_by(
            FundTransfer.funding_entity_id, FundTransfer.funding_type, FundTransfer.kind):
        key = (eid, ftype or "OTHER")
        by_type[key] = by_type.get(key, D(0)) + (D(amt) if kind == "FUNDING" else -D(amt))

    def types_for(eid):
        return [{"funding_type": t, "net_funded": float(v)}
                for (e, t), v in sorted(by_type.items(), key=lambda kv: kv[0][1]) if e == eid]

    keys = ["opening_balance", "funded", "transfers_in", "transfers_out", "repaid", "receipts", "payments", "balance"]
    def pack(r):
        return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in r.items()}

    groups = []
    entities = db.query(FundingEntity).order_by(FundingEntity.name).all()
    for e in entities:
        accs = [r for r in rows.values() if r["funding_entity_id"] == e.id]
        funded, repaid = funded_by_entity.get(e.id, D(0)), repaid_by_entity.get(e.id, D(0))
        g = {"entity_id": e.id, "entity_name": e.name,
             "total_funded": float(funded), "total_repaid": float(repaid),
             "net_funded": float(funded - repaid), "by_funding_type": types_for(e.id),
             "accounts": [pack(r) for r in accs]}
        for k in keys:
            g[k] = float(sum((r[k] for r in accs), D(0)))
        groups.append(g)
    unassigned = [r for r in rows.values() if r["funding_entity_id"] is None]
    if unassigned or None in funded_by_entity or None in repaid_by_entity:
        funded, repaid = funded_by_entity.get(None, D(0)), repaid_by_entity.get(None, D(0))
        g = {"entity_id": None, "entity_name": "Unassigned",
             "total_funded": float(funded), "total_repaid": float(repaid),
             "net_funded": float(funded - repaid), "by_funding_type": types_for(None),
             "accounts": [pack(r) for r in unassigned]}
        for k in keys:
            g[k] = float(sum((r[k] for r in unassigned), D(0)))
        groups.append(g)

    totals = {k: float(sum((r[k] for r in rows.values()), D(0))) for k in keys}
    totals["total_funded"] = float(sum(funded_by_entity.values(), D(0)))
    totals["total_repaid"] = float(sum(repaid_by_entity.values(), D(0)))
    totals["net_funded"] = totals["total_funded"] - totals["total_repaid"]
    return {"as_of": as_of, "groups": groups, "totals": totals}
