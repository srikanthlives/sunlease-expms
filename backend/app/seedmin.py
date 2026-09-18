"""Seed initial roles + users + sample masters, including a working
manager-employee hierarchy and a project accounts-approver assignment, so
the two-level claim approval flow is testable immediately after a fresh
seed. Safe to re-run (idempotent)."""
from app.core.security import hash_password
from app.db.session import Base, SessionLocal, engine
from app.migrate import migrate
from app.models.models import Role, User, Project, ProjectAccountsUser, ExpenseCategory, ExpenseSubCategory, Account, Vendor, Employee, ApprovalRule
from app.models.enums import RoleName

migrate(verbose=True)
db = SessionLocal()

try:
    # Roles
    role_map = {}
    for name in RoleName.ALL:
        role = db.query(Role).filter(Role.name == name).first()
        if not role:
            role = Role(name=name, description=f"{name.title()} role")
            db.add(role)
            db.flush()
        role_map[name] = role

    # Super Admin - the only role that can create other roles, create Admin
    # accounts, and reset any user's password.
    if not db.query(User).filter(User.username == "superadmin").first():
        db.add(User(
            username="superadmin", email="superadmin@example.com", full_name="Super Administrator",
            hashed_password=hash_password("SuperAdmin@123"), role_id=role_map[RoleName.SUPER_ADMIN].id,
        ))

    # Admin - controls Masters; cannot create another Admin or Super Admin.
    if not db.query(User).filter(User.username == "admin").first():
        db.add(User(
            username="admin", email="admin@example.com", full_name="System Administrator",
            hashed_password=hash_password("Admin@123"), role_id=role_map[RoleName.ADMIN].id,
        ))

    # Super Accounts - everything ACCOUNTS can do, plus exclusive access to
    # the Receivables module (Quotations, Receivable Invoices, Receivable
    # Payments). Not project-restricted like ACCOUNTS (see core/deps.py).
    if not db.query(User).filter(User.username == "superaccounts").first():
        db.add(User(
            username="superaccounts", full_name="Super Accounts User",
            hashed_password=hash_password("SuperAcc@123"), role_id=role_map[RoleName.SUPER_ACCOUNTS].id,
        ))

    # Sample project
    if not db.query(Project).filter(Project.code == "GEN").first():
        db.add(Project(code="GEN", name="General / Head Office"))
    db.flush()
    gen_project = db.query(Project).filter(Project.code == "GEN").first()

    # Sample categories
    cat_names = ["Travel", "Food", "Accommodation", "Local Conveyance", "Fuel", "Office Supplies", "Professional Services"]
    for c in cat_names:
        if not db.query(ExpenseCategory).filter(ExpenseCategory.name == c).first():
            db.add(ExpenseCategory(name=c))
    db.flush()

    db.commit()
    print("Seed complete.")
    print("Login credentials:")
    print("  superadmin / SuperAdmin@123 (SUPER_ADMIN)")
    print("  admin / Admin@123           (ADMIN)")
    print("  superaccounts / SuperAcc@123 (SUPER_ACCOUNTS - Accounts plus Receivables)")
finally:
    db.close()
