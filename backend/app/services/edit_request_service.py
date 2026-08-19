import datetime as dt
import json
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.models import (
    Expense, Invoice, Payment, Vendor, Project, ExpenseCategory, ExpenseSubCategory,
    Employee, Account, EditRequest, User,
)
from app.models.enums import EditableEntityType, EditRequestStatus, AuditAction
from app.services import audit_service
from app.services.payment_status_service import get_paid_amount, recalculate_payment_status

# Whitelisted editable fields per entity, with a type tag used for coercion.
# Structural fields (id, status, source_type/source_id, payment_status,
# expense_number/invoice_number-uniqueness-critical fields excluded where
# risky) are deliberately NOT editable through this path.
FIELD_TYPES = {
    EditableEntityType.EXPENSE: {
        "expense_date": "date", "project_id": "int", "vendor_id": "int", "employee_id": "int",
        "category_id": "int", "sub_category_id": "int", "description": "str",
        "supplier_name": "str", "bill_number": "str",
        "base_amount": "decimal", "gst_amount": "decimal", "other_amount": "decimal",
    },
    EditableEntityType.INVOICE: {
        "invoice_number": "str", "vendor_id": "int", "invoice_date": "date", "due_date": "date",
        "project_id": "int", "description": "str",
        "taxable_amount": "decimal", "cgst": "decimal", "sgst": "decimal", "igst": "decimal", "other_tax": "decimal",
        "category_id": "int", "sub_category_id": "int",
    },
    EditableEntityType.PAYMENT: {
        "payment_date": "date", "account_id": "int", "payment_mode": "str",
        "reference_number": "str", "remarks": "str",
    },
}

_AMOUNT_FIELDS = {
    EditableEntityType.EXPENSE: ["base_amount", "gst_amount", "other_amount"],
    EditableEntityType.INVOICE: ["taxable_amount", "cgst", "sgst", "igst", "other_tax"],
}


def _coerce(field_type: str, value):
    if value is None:
        return None
    try:
        if field_type == "decimal":
            return Decimal(str(value))
        if field_type == "int":
            return int(value)
        if field_type == "date":
            return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value))
        return str(value)
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid value for a {field_type} field: {value!r}")


def _json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def validate_fields(entity_type: str, changes: dict):
    if entity_type not in FIELD_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown entity_type '{entity_type}'")
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No changes provided")
    allowed = FIELD_TYPES[entity_type]
    unknown = set(changes.keys()) - set(allowed.keys())
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"These fields are not editable for {entity_type}: {', '.join(sorted(unknown))}")


def get_entity(db: Session, entity_type: str, entity_id: int):
    model = {EditableEntityType.EXPENSE: Expense, EditableEntityType.INVOICE: Invoice, EditableEntityType.PAYMENT: Payment}.get(entity_type)
    if model is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown entity_type '{entity_type}'")
    entity = db.query(model).filter(model.id == entity_id).first()
    if not entity:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{entity_type.title()} not found")
    return entity


def snapshot_values(entity, entity_type: str, fields: list[str]) -> dict:
    """Current values for exactly the fields being proposed for change -
    used as the 'previous_values' diff baseline on an edit request."""
    if entity_type == EditableEntityType.INVOICE:
        # category/sub_category live on the linked Expense, not the Invoice.
        expense = entity.expense
        out = {}
        for f in fields:
            if f in ("category_id", "sub_category_id"):
                out[f] = _json_safe(getattr(expense, f, None)) if expense else None
            else:
                out[f] = _json_safe(getattr(entity, f, None))
        return out
    return {f: _json_safe(getattr(entity, f, None)) for f in fields}


def _validate_references(db: Session, entity_type: str, changes: dict):
    checks = {
        "vendor_id": Vendor, "project_id": Project, "category_id": ExpenseCategory,
        "sub_category_id": ExpenseSubCategory, "employee_id": Employee, "account_id": Account,
    }
    for field, model in checks.items():
        if field in changes and changes[field] is not None:
            value = _coerce("int", changes[field])
            if not db.query(model).filter(model.id == value).first():
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{field} {value} does not exist")


def apply_changes(db: Session, entity_type: str, entity, changes: dict, actor_id: int):
    """Applies a validated changes dict to the ORM entity. Shared by both the
    direct-edit path (Admin/Super Admin) and approved edit requests (Accounts
    -> Admin approval), so the business rules only live in one place."""
    validate_fields(entity_type, changes)
    _validate_references(db, entity_type, changes)
    field_types = FIELD_TYPES[entity_type]

    if entity_type == EditableEntityType.EXPENSE:
        amount_fields = _AMOUNT_FIELDS[EditableEntityType.EXPENSE]
        if any(f in changes for f in amount_fields):
            new_base = _coerce("decimal", changes.get("base_amount", entity.base_amount))
            new_gst = _coerce("decimal", changes.get("gst_amount", entity.gst_amount))
            new_other = _coerce("decimal", changes.get("other_amount", entity.other_amount))
            new_total = new_base + new_gst + new_other
            if new_total <= 0:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Total amount must be greater than zero")
            paid = get_paid_amount(db, entity.id)
            if new_total < paid:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"New total ({new_total}) is less than the amount already paid ({paid})")
            entity.base_amount, entity.gst_amount, entity.other_amount, entity.total_amount = new_base, new_gst, new_other, new_total
            recalculate_payment_status(db, entity)
        for field, ftype in field_types.items():
            if field in changes and field not in amount_fields:
                setattr(entity, field, _coerce(ftype, changes[field]))
        db.add(entity)

    elif entity_type == EditableEntityType.INVOICE:
        expense = entity.expense
        amount_fields = _AMOUNT_FIELDS[EditableEntityType.INVOICE]
        if any(f in changes for f in amount_fields):
            new_taxable = _coerce("decimal", changes.get("taxable_amount", entity.taxable_amount))
            new_cgst = _coerce("decimal", changes.get("cgst", entity.cgst))
            new_sgst = _coerce("decimal", changes.get("sgst", entity.sgst))
            new_igst = _coerce("decimal", changes.get("igst", entity.igst))
            new_other_tax = _coerce("decimal", changes.get("other_tax", entity.other_tax))
            new_total = new_taxable + new_cgst + new_sgst + new_igst + new_other_tax
            if new_total <= 0:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Total amount must be greater than zero")
            paid = get_paid_amount(db, expense.id) if expense else Decimal("0")
            if new_total < paid:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"New total ({new_total}) is less than the amount already paid ({paid})")
            entity.taxable_amount, entity.cgst, entity.sgst, entity.igst, entity.other_tax = new_taxable, new_cgst, new_sgst, new_igst, new_other_tax
            entity.total_amount = new_total
            if expense:
                expense.base_amount = new_taxable
                expense.gst_amount = new_cgst + new_sgst + new_igst
                expense.other_amount = new_other_tax
                expense.total_amount = new_total
                recalculate_payment_status(db, expense)

        if "invoice_number" in changes or "vendor_id" in changes:
            new_number = changes.get("invoice_number", entity.invoice_number)
            new_vendor = _coerce("int", changes.get("vendor_id", entity.vendor_id))
            dupe = db.query(Invoice).filter(Invoice.invoice_number == new_number, Invoice.vendor_id == new_vendor, Invoice.id != entity.id).first()
            if dupe:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Another invoice with this number already exists for this vendor")

        for field in ("invoice_number", "vendor_id", "invoice_date", "due_date", "project_id", "description"):
            if field in changes:
                value = _coerce(field_types[field], changes[field])
                setattr(entity, field, value)
                # Keep the linked Expense (the reporting "hub") consistent.
                if expense and field in ("vendor_id", "project_id", "description"):
                    setattr(expense, field, value)
                if expense and field == "invoice_date":
                    expense.expense_date = value

        if expense:
            if "category_id" in changes:
                expense.category_id = _coerce("int", changes["category_id"])
            if "sub_category_id" in changes:
                expense.sub_category_id = _coerce("int", changes["sub_category_id"])

        db.add(entity)
        if expense:
            db.add(expense)

    elif entity_type == EditableEntityType.PAYMENT:
        for field, ftype in field_types.items():
            if field in changes:
                setattr(entity, field, _coerce(ftype, changes[field]))
        db.add(entity)

    db.flush()
    return entity


# ---------------------------------------------------------------------------
# Direct edit (Admin / Super Admin) - applies immediately, no approval hop.
# ---------------------------------------------------------------------------

def direct_edit(db: Session, entity_type: str, entity_id: int, changes: dict, actor: User):
    entity = get_entity(db, entity_type, entity_id)
    apply_changes(db, entity_type, entity, changes, actor.id)
    audit_service.record(db, entity_type, entity_id, AuditAction.UPDATE, actor.id, {"changes": changes, "direct": True})
    return entity


# ---------------------------------------------------------------------------
# Edit requests (Accounts proposes -> Admin/Super Admin reviews)
# ---------------------------------------------------------------------------

def create_edit_request(db: Session, entity_type: str, entity_id: int, changes: dict, actor: User) -> EditRequest:
    validate_fields(entity_type, changes)
    entity = get_entity(db, entity_type, entity_id)
    previous = snapshot_values(entity, entity_type, list(changes.keys()))

    req = EditRequest(
        entity_type=entity_type, entity_id=entity_id,
        changes=json.dumps(changes, default=str), previous_values=json.dumps(previous, default=str),
        status=EditRequestStatus.PENDING, requested_by=actor.id,
    )
    db.add(req)
    db.flush()
    audit_service.record(db, "EDIT_REQUEST", req.id, AuditAction.CREATE, actor.id, {"entity_type": entity_type, "entity_id": entity_id})
    return req


def approve_edit_request(db: Session, req: EditRequest, actor: User, remarks: str | None = None) -> EditRequest:
    if req.status != EditRequestStatus.PENDING:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This edit request has already been reviewed")

    changes = json.loads(req.changes)
    entity = get_entity(db, req.entity_type, req.entity_id)
    # Re-validate against the CURRENT state at approval time (not request
    # time) - e.g. more payments may have landed on the expense since the
    # request was submitted, changing what totals are still valid.
    apply_changes(db, req.entity_type, entity, changes, actor.id)

    req.status = EditRequestStatus.APPROVED
    req.reviewed_by = actor.id
    req.reviewed_at = dt.datetime.utcnow()
    req.review_remarks = remarks
    db.add(req)

    audit_service.record(db, "EDIT_REQUEST", req.id, AuditAction.APPROVE, actor.id, {"remarks": remarks})
    audit_service.record(db, req.entity_type, req.entity_id, AuditAction.UPDATE, actor.id, {"via_edit_request": req.id, "changes": changes})
    return req


def reject_edit_request(db: Session, req: EditRequest, actor: User, reason: str) -> EditRequest:
    if req.status != EditRequestStatus.PENDING:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This edit request has already been reviewed")
    if not reason:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A rejection reason is required")

    req.status = EditRequestStatus.REJECTED
    req.reviewed_by = actor.id
    req.reviewed_at = dt.datetime.utcnow()
    req.review_remarks = reason
    db.add(req)

    audit_service.record(db, "EDIT_REQUEST", req.id, AuditAction.REJECT, actor.id, {"reason": reason})
    return req
