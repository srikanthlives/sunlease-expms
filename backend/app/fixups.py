"""One-off, hand-written schema fixes that app/migrate.py deliberately
won't do automatically (it is additive-only and never rebuilds a table).

Each fixup is idempotent and checks the live schema before doing anything,
so running this on an already-correct database is a no-op. Called from
main.py straight after migrate(), and runnable directly:

    python -m app.fixups
"""
from sqlalchemy import inspect, text

from app.db.session import engine


def _to_account_nullable(conn, verbose: bool) -> bool:
    """fund_transfers.to_account_id was NOT NULL when transfers could only be
    FUNDING (money in) or TRANSFER (between our accounts). The REPAYMENT kind
    (money going back out to a funding entity) has no destination account, so
    the column has to allow NULL. SQLite can't ALTER a column's nullability -
    rebuild the table, copying every existing row across."""
    cols = {c["name"]: c for c in inspect(conn).get_columns("fund_transfers")}
    if not cols or cols["to_account_id"]["nullable"]:
        return False

    names = [c for c in (
        "id", "transfer_number", "transfer_date", "kind", "from_account_id",
        "to_account_id", "funding_entity_id", "funding_type", "amount",
        "reference_number", "remarks", "is_cancelled", "cancel_reason",
        "created_by", "created_at") if c in cols]
    cols_sql = ", ".join(names)
    conn.execute(text("ALTER TABLE fund_transfers RENAME TO fund_transfers_old"))
    # SQLite keeps indexes (and their names) attached across a table rename,
    # so drop them before recreating the table or the names collide.
    for idx in inspect(conn).get_indexes("fund_transfers_old"):
        if idx.get("name"):
            conn.execute(text(f'DROP INDEX IF EXISTS "{idx["name"]}"'))
    from app.models.models import FundTransfer
    FundTransfer.__table__.create(bind=conn)
    conn.execute(text(f"INSERT INTO fund_transfers ({cols_sql}) SELECT {cols_sql} FROM fund_transfers_old"))
    conn.execute(text("DROP TABLE fund_transfers_old"))
    if verbose:
        print("Rebuilt fund_transfers so to_account_id allows NULL (REPAYMENT rows)")
    return True


FIXUPS = [_to_account_nullable]


def run_fixups(verbose: bool = True) -> int:
    applied = 0
    # One transaction per fixup, so a failure rolls that fixup back entirely
    # rather than leaving the schema half-rebuilt.
    for fn in FIXUPS:
        try:
            with engine.begin() as conn:
                if fn(conn, verbose):
                    applied += 1
        except Exception as exc:  # a missing table just means nothing to fix yet
            if verbose:
                print(f"Fixup {fn.__name__} skipped: {exc}")
    if verbose and not applied:
        print("Schema fixups: nothing to do")
    return applied


if __name__ == "__main__":
    run_fixups(verbose=True)
