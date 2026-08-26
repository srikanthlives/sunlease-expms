"""Lightweight auto-migration for SQLite, since this project doesn't use
Alembic (it's listed as a dependency but never initialized).

Run this any time app/models/models.py changes:

    python -m app.migrate

What it does automatically (safe, additive-only operations):
  - Creates any table that exists on a model but not yet in the database.
  - Adds any column that exists on a model but not yet on the live table
    (ALTER TABLE ... ADD COLUMN), matching the column's type and, where
    possible, its nullability/default.

What it deliberately does NOT do (unsafe or ambiguous on SQLite - some of
these require rebuilding the whole table, and guessing wrong risks losing
data):
  - Drop a column that's been removed from a model.
  - Rename a column (this looks identical to "drop one, add another" and
    the script has no way to know your intent - handle renames by hand).
  - Change an existing column's type or nullability.
  - Add or remove constraints (unique, foreign key, check) on a table that
    already exists.
If you need any of those, either handle it by hand with a short SQL script
(back up expms.db first), or adopt Alembic properly (see CLAUDE.md). For a
disposable dev database, it's usually simplest to just reset instead:

    rm -f expms.db && python -m app.seed

This script is also called automatically on every app startup (see
app/main.py) so new columns/tables show up without a manual step in normal
development - the standalone command above is for explicit/CI use and
prints a readable summary of what it did.
"""
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.db.session import Base, engine
import app.models  # noqa: F401  (ensures every model is registered on Base.metadata)


def _add_column_ddl(table_name: str, column) -> str:
    col_type = str(column.type)  # SQLAlchemy renders a SQLite-compatible type string
    parts = [f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {col_type}']

    # SQLite requires a default when adding a NOT NULL column to a table
    # that may already have rows. If the model doesn't specify one, fall
    # back to nullable rather than guess a default and risk the ALTER
    # failing outright (or silently corrupting intent).
    if column.default is not None and getattr(column.default, "is_scalar", False):
        parts.append(f"DEFAULT {column.default.arg!r}")
        if not column.nullable:
            parts.append("NOT NULL")
    elif not column.nullable:
        pass  # would need a default to be NOT NULL on SQLite; leave nullable

    return " ".join(parts)


def migrate(target_engine: Engine = None, verbose: bool = True) -> dict:
    """Diffs the live database against the current models and applies any
    additive changes. Returns {"tables_created": [...], "columns_added": [(table, column), ...]}."""
    target_engine = target_engine or engine
    summary = {"tables_created": [], "columns_added": []}

    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())
    # Use metadata.tables (unordered) rather than sorted_tables - this
    # project has a genuine circular FK dependency (Project.accounts_
    # approver_id -> User -> Employee.user -> EmployeeProject -> Project),
    # which trips SQLAlchemy's topological sort. SQLite doesn't enforce FK ordering at
    # CREATE TABLE time (constraints are checked at DML time, if enabled at
    # all), so table creation order is safe to leave unordered here.
    all_tables = list(Base.metadata.tables.values())

    # 1. Create any brand-new tables (safe - only touches tables that don't exist yet).
    tables_to_create = [t for t in all_tables if t.name not in existing_tables]
    if tables_to_create:
        Base.metadata.create_all(bind=target_engine, tables=tables_to_create)
        summary["tables_created"] = [t.name for t in tables_to_create]
        inspector = inspect(target_engine)
        existing_tables = set(inspector.get_table_names())

    # 2. For tables that already existed, add any columns present on the
    #    model but missing from the live table.
    with target_engine.begin() as conn:
        for table in all_tables:
            if table.name not in existing_tables or table.name in summary["tables_created"]:
                continue  # brand new tables above already have every column
            live_columns = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in live_columns:
                    continue
                conn.execute(text(_add_column_ddl(table.name, column)))
                summary["columns_added"].append((table.name, column.name))

    # 3. One-off data backfill: Employee.project_id (single FK) was replaced
    # by the employee_projects many-to-many table. The old column is never
    # dropped (see module docstring), so on the first run after this change
    # - when employee_projects is freshly created but still empty - copy each
    # employee's existing single project assignment into the new table so no
    # employee silently loses their project link.
    if "employee_projects" in summary["tables_created"]:
        inspector = inspect(target_engine)
        employee_columns = {c["name"] for c in inspector.get_columns("employees")}
        if "project_id" in employee_columns:
            with target_engine.begin() as conn:
                rows = conn.execute(text('SELECT id, project_id FROM employees WHERE project_id IS NOT NULL')).fetchall()
                for employee_id, project_id in rows:
                    conn.execute(
                        text('INSERT INTO employee_projects (employee_id, project_id, created_at) VALUES (:e, :p, CURRENT_TIMESTAMP)'),
                        {"e": employee_id, "p": project_id},
                    )
                if rows:
                    summary["employee_projects_backfilled"] = len(rows)

    if verbose:
        if summary.get("employee_projects_backfilled"):
            print(f"Backfilled {summary['employee_projects_backfilled']} employee->project link(s) from the old Employee.project_id column.")
        if not summary["tables_created"] and not summary["columns_added"]:
            print("Database schema already matches the models - nothing to do.")
        else:
            if summary["tables_created"]:
                print(f"Created {len(summary['tables_created'])} new table(s):")
                for t in summary["tables_created"]:
                    print(f"  + {t}")
            if summary["columns_added"]:
                print(f"Added {len(summary['columns_added'])} new column(s):")
                for table_name, col_name in summary["columns_added"]:
                    print(f"  + {table_name}.{col_name}")
        print(
            "\nNote: this only ADDS tables/columns, never drops or renames. "
            "If a model removed a field or changed a type, handle that by "
            "hand (see CLAUDE.md) or reset the dev DB with "
            "'rm -f expms.db && python -m app.seed'."
        )

    return summary


if __name__ == "__main__":
    migrate()
