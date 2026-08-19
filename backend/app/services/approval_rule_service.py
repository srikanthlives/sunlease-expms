from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.models import ApprovalRule


def resolve_required_steps(db: Session, entity_type: str, amount: Decimal) -> list[str]:
    """Return the ordered list of role names required to approve an entity of
    this amount, based on configurable rules rather than hard-coded thresholds.
    Falls back to a single MANAGER step if no rule matches."""
    rules = (
        db.query(ApprovalRule)
        .filter(ApprovalRule.entity_type == entity_type, ApprovalRule.is_active.is_(True))
        .order_by(ApprovalRule.min_amount.asc())
        .all()
    )
    for rule in rules:
        lower_ok = amount >= Decimal(rule.min_amount)
        upper_ok = rule.max_amount is None or amount <= Decimal(rule.max_amount)
        if lower_ok and upper_ok:
            return [s.strip() for s in rule.required_steps.split(",") if s.strip()]
    return ["MANAGER"]
