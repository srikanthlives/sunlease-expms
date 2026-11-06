"""Bulk import of fund transfers / funding / repayments from an Excel
workbook.

Mirrors bulk_import_service's shape exactly (same row-result dict, same
dry-run-then-commit contract, same all-or-nothing rule), but routes every
row through `fund_transfer_service.resolve_transfer` / `apply_transfer` -
the very functions the single-record API uses - so a spreadsheet can never
create a transfer the UI would have rejected.

Accounts and funding entities are resolved by name (case-insensitive),
since a human-authored sheet won't have internal ids.
"""
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.models.models import Account, FundingEntity, FundTransfer
from app.schemas.common import TEXT_FIELD_MAX_LENGTH
from app.schemas.funds import TransferIn
from app.services import audit_service, fund_transfer_service as fts

HEADERS = [
    "Kind", "Date", "From Account", "To Account", "Funding Entity",
    "Funding Type", "Amount", "Reference Number", "Remarks",
]

_KIND_SYNONYMS = {
    "FUNDING": "FUNDING", "FUND": "FUNDING", "FUNDING IN": "FUNDING", "IN": "FUNDING",
    "REPAYMENT": "REPAYMENT", "REPAY": "REPAYMENT", "REPAYMENT OUT": "REPAYMENT", "OUT": "REPAYMENT",
    "TRANSFER": "TRANSFER", "MOVE": "TRANSFER",
}


@dataclass
class RowResult:
    row_number: int
    row_type: str | None = None
    status: str = "OK"  # OK | ERROR
    errors: list[str] = field(default_factory=list)
    transfer_number: str | None = None
    total_amount: str | None = None


def _norm(v) -> str:
    return str(v).strip() if v is not None else ""


def _cell_date(v, errors: list[str], label: str):
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = _norm(v)
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    errors.append(f"{label} '{s}' is not a valid date (use YYYY-MM-DD)")
    return None


def _cell_decimal(v, errors: list[str], label: str):
    if v is None or v == "":
        errors.append(f"{label} is required")
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        errors.append(f"{label} '{v}' is not a valid number")
        return None


def _read_rows(file_bytes: bytes) -> list[dict]:
    wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = [_norm(h).lower() for h in rows[0]]
    out = []
    for raw in rows[1:]:
        if raw is None or all(c is None or _norm(c) == "" for c in raw):
            continue
        out.append({header[i]: raw[i] for i in range(min(len(header), len(raw)))})
    return out


class _Lookups:
    def __init__(self, db: Session):
        self.accounts = {a.account_name.strip().lower(): a for a in db.query(Account).all()}
        self.entities = {e.name.strip().lower(): e for e in db.query(FundingEntity).all()}

    def account(self, name: str):
        return self.accounts.get(name.strip().lower()) if name else None

    def entity(self, name: str):
        return self.entities.get(name.strip().lower()) if name else None


def process_workbook(db: Session, file_bytes: bytes, user, dry_run: bool) -> dict:
    lookups = _Lookups(db)
    results: list[RowResult] = []
    any_error = False

    for i, raw in enumerate(_read_rows(file_bytes), start=2):  # +1 header, +1 1-index
        r = RowResult(row_number=i)
        errors = r.errors

        kind = _KIND_SYNONYMS.get(_norm(raw.get("kind")).upper())
        if not kind:
            errors.append(f"Kind '{_norm(raw.get('kind'))}' must be FUNDING, REPAYMENT or TRANSFER")
        r.row_type = kind

        transfer_date = _cell_date(raw.get("date"), errors, "Date")
        if not transfer_date:
            errors.append("Date is required")
        amount = _cell_decimal(raw.get("amount"), errors, "Amount")

        from_account = to_account = entity = None
        from_name, to_name = _norm(raw.get("from account")), _norm(raw.get("to account"))
        entity_name = _norm(raw.get("funding entity"))
        if from_name:
            from_account = lookups.account(from_name)
            if not from_account:
                errors.append(f"From Account '{from_name}' not found")
        if to_name:
            to_account = lookups.account(to_name)
            if not to_account:
                errors.append(f"To Account '{to_name}' not found")
        if entity_name:
            entity = lookups.entity(entity_name)
            if not entity:
                errors.append(f"Funding Entity '{entity_name}' not found")

        funding_type = _norm(raw.get("funding type")).upper() or None
        if funding_type and funding_type not in fts.FUNDING_TYPES:
            errors.append(f"Funding Type '{funding_type}' must be one of {', '.join(fts.FUNDING_TYPES)}")
        reference_number = _norm(raw.get("reference number")) or None
        remarks = _norm(raw.get("remarks")) or None
        if remarks and len(remarks) > TEXT_FIELD_MAX_LENGTH:
            errors.append(f"Remarks must be at most {TEXT_FIELD_MAX_LENGTH} characters")

        if errors:
            r.status = "ERROR"
            results.append(r)
            any_error = True
            continue

        # Same validation the API runs - a row that would be rejected by
        # POST /funds/transfers is rejected here, with the same message.
        try:
            payload = TransferIn(
                kind=kind, transfer_date=transfer_date,
                from_account_id=from_account.id if from_account else None,
                to_account_id=to_account.id if to_account else None,
                funding_entity_id=entity.id if entity else None,
                funding_type=funding_type, amount=amount,
                reference_number=reference_number, remarks=remarks,
            )
            entity_id, resolved_type = fts.resolve_transfer(db, payload)
            t = FundTransfer(transfer_number=fts.next_number(db), created_by=user.id)
            fts.apply_transfer(t, payload, entity_id, resolved_type)
            db.add(t)
            db.flush()
            audit_service.record(db, "FUND_TRANSFER", t.id, "CREATE", user.id,
                                 {**fts.transfer_audit(t), "source": "BULK_IMPORT"})
            r.transfer_number = t.transfer_number
            r.total_amount = str(t.amount)
        except Exception as exc:  # noqa: BLE001 - surface service validation as a row error
            r.status = "ERROR"
            r.errors.append(str(getattr(exc, "detail", exc)))
            any_error = True

        results.append(r)

    summary = {
        "total_rows": len(results),
        "ok_rows": sum(1 for r in results if r.status == "OK"),
        "error_rows": sum(1 for r in results if r.status == "ERROR"),
        "committed": False,
    }
    if dry_run or any_error:
        db.rollback()
    else:
        db.commit()
        summary["committed"] = True

    summary["rows"] = [
        {"row_number": r.row_number, "row_type": r.row_type, "status": r.status,
         "errors": r.errors, "transfer_number": r.transfer_number, "total_amount": r.total_amount}
        for r in results
    ]
    return summary


#: Informational columns appended to an export. They are NOT part of
#: HEADERS, so re-importing an exported sheet simply ignores them
#: (_read_rows keys by header name and unknown headers are unused).
EXPORT_EXTRA_HEADERS = ["Transfer #", "Verified", "Cancelled"]


def build_export_workbook(db: Session, date_from=None, date_to=None,
                          funding_entity_id: int | None = None, kind: str | None = None,
                          include_cancelled: bool = False) -> bytes:
    """Existing transfers written out in the import template's own column
    layout, so an export can be edited and fed straight back in.

    Cancelled rows are excluded by default: they are history, and
    re-importing one would silently resurrect it as a live entry."""
    q = db.query(FundTransfer)
    if not include_cancelled:
        q = q.filter(FundTransfer.is_cancelled.is_(False))
    if date_from:
        q = q.filter(FundTransfer.transfer_date >= date_from)
    if date_to:
        q = q.filter(FundTransfer.transfer_date <= date_to)
    if funding_entity_id:
        q = q.filter(FundTransfer.funding_entity_id == funding_entity_id)
    if kind:
        q = q.filter(FundTransfer.kind == kind)
    transfers = q.order_by(FundTransfer.transfer_date, FundTransfer.id).all()

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Transfers"
    ws.append(HEADERS + EXPORT_EXTRA_HEADERS)
    for t in transfers:
        ws.append([
            t.kind,
            t.transfer_date.isoformat() if t.transfer_date else "",
            t.from_account.account_name if t.from_account else "",
            t.to_account.account_name if t.to_account else "",
            t.funding_entity.name if t.funding_entity else "",
            t.funding_type or "",
            float(t.amount),
            t.reference_number or "",
            t.remarks or "",
            t.transfer_number,
            "Y" if t.is_verified else "N",
            "Y" if t.is_cancelled else "N",
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_template_workbook() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Transfers"
    ws.append(HEADERS)
    ws.append(["FUNDING", "2026-04-01", "", "HDFC Bank", "SRIKANTH", "LOAN", 500000,
               "UTR123456", "Unsecured loan from director"])
    ws.append(["REPAYMENT", "2026-04-15", "HDFC Bank", "", "SRIKANTH", "LOAN", 100000,
               "UTR123999", "Part repayment of director loan"])
    ws.append(["TRANSFER", "2026-04-20", "HDFC Bank", "Petty Cash", "", "", 25000,
               "", "Cash drawn for site expenses"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
