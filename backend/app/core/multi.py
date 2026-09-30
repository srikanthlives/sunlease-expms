"""Multi-select filter helpers: list filters arrive as comma-separated
query strings (e.g. ``project_id=1,4``) and are parsed here."""
from fastapi import HTTPException, status


def ids(v) -> list[int]:
    try:
        return [int(x) for x in str(v or "").split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid id list")


def strs(v) -> list[str]:
    return [x.strip() for x in str(v or "").split(",") if x.strip()]


def names(db, model, attr: str, raw) -> str:
    """Comma-joined display names for a list of ids (falls back to the id)."""
    out = []
    for i in ids(raw):
        row = db.query(model).filter(model.id == i).first()
        out.append(str(getattr(row, attr)) if row else str(i))
    return ", ".join(out)
