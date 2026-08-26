"""Seed initial roles + users + sample masters, including a working
manager-employee hierarchy and a project accounts-approver assignment, so
the two-level claim approval flow is testable immediately after a fresh
seed. Safe to re-run (idempotent)."""
from app.core.security import hash_password
from app.db.session import Base, SessionLocal, engine
from app.migrate import migrate
from app.models.models import Role, User, Project, ProjectAccountsUser, ExpenseCategory, ExpenseSubCategory, Account, Vendor, Employee, EmployeeProject, ApprovalRule
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

    travel = db.query(ExpenseCategory).filter(ExpenseCategory.name == "Travel").first()
    if travel and not db.query(ExpenseSubCategory).filter(ExpenseSubCategory.name == "Taxi").first():
        db.add(ExpenseSubCategory(category_id=travel.id, name="Taxi"))
        db.add(ExpenseSubCategory(category_id=travel.id, name="Flight"))

    # Sample account
    if not db.query(Account).filter(Account.account_name == "IDFC FIRST Bank").first():
        db.add(Account(account_name="IDFC FIRST Bank", account_type="BANK", account_number="XXXXXXXXXX", ifsc="IDFB0000001"))
    if not db.query(Account).filter(Account.account_name == "Petty Cash").first():
        db.add(Account(account_name="Petty Cash", account_type="PETTY_CASH"))

    # Sample vendor
    if not db.query(Vendor).filter(Vendor.vendor_code == "V-0001").first():
        db.add(Vendor(vendor_code="V-0001", vendor_name="ABC Motors"))

    # Accounts user - this is who gets assigned as the GEN project's final
    # (level-2) claim approver below.
    if not db.query(User).filter(User.username == "accounts").first():
        db.add(User(username="accounts", full_name="Accounts User", hashed_password=hash_password("Accounts@123"), role_id=role_map[RoleName.ACCOUNTS].id))
    db.flush()
    accounts_user = db.query(User).filter(User.username == "accounts").first()

    if gen_project and accounts_user and gen_project.accounts_approver_id is None:
        gen_project.accounts_approver_id = accounts_user.id
        db.add(gen_project)

    # ACCOUNTS is now always project-restricted (see project_accounts_users) -
    # without this, a fresh seed would leave the "accounts" user with zero
    # assigned projects and every expense/invoice/payment/claim list would
    # look empty/broken out of the box.
    if gen_project and accounts_user and not db.query(ProjectAccountsUser).filter(
        ProjectAccountsUser.project_id == gen_project.id, ProjectAccountsUser.user_id == accounts_user.id
    ).first():
        db.add(ProjectAccountsUser(project_id=gen_project.id, user_id=accounts_user.id))

    # Manager - a Manager IS an employee record too, so they can submit
    # their own claims. They sit at the top of this small hierarchy (no
    # manager of their own).
    if not db.query(Employee).filter(Employee.employee_code == "EMP-0000").first():
        mgr_emp = Employee(employee_code="EMP-0000", employee_name="Priya Sharma", designation="Engineering Manager")
        db.add(mgr_emp)
        db.flush()
        if gen_project:
            db.add(EmployeeProject(employee_id=mgr_emp.id, project_id=gen_project.id))
        if not db.query(User).filter(User.username == "manager").first():
            db.add(User(username="manager", full_name="Priya Sharma", hashed_password=hash_password("Manager@123"),
                        role_id=role_map[RoleName.MANAGER].id, employee_id=mgr_emp.id))
    db.flush()
    manager_employee = db.query(Employee).filter(Employee.employee_code == "EMP-0000").first()

    # Employee - reports to the manager above, so /claims submitted by this
    # user route to "manager" for level-1 approval.
    if not db.query(Employee).filter(Employee.employee_code == "EMP-0001").first():
        emp = Employee(
            employee_code="EMP-0001", employee_name="Ajai Kumar", designation="Executive",
            manager_id=manager_employee.id if manager_employee else None,
        )
        db.add(emp)
        db.flush()
        if gen_project:
            db.add(EmployeeProject(employee_id=emp.id, project_id=gen_project.id))
        if not db.query(User).filter(User.username == "ajai").first():
            db.add(User(username="ajai", full_name="Ajai Kumar", hashed_password=hash_password("Employee@123"),
                        role_id=role_map[RoleName.EMPLOYEE].id, employee_id=emp.id))

    # Default approval rule (kept for the generic ApprovalRule admin screen;
    # the claim workflow itself now routes via the manager/project hierarchy
    # rather than this table).
    if not db.query(ApprovalRule).filter(ApprovalRule.name == "Standard Claim Approval").first():
        db.add(ApprovalRule(name="Standard Claim Approval", entity_type="CLAIM", min_amount=0, max_amount=None, required_steps="MANAGER,ACCOUNTS"))

    db.commit()
    print("Seed complete.")
    print("Login credentials:")
    print("  superadmin / SuperAdmin@123 (SUPER_ADMIN)")
    print("  admin / Admin@123           (ADMIN)")
    print("  accounts / Accounts@123     (ACCOUNTS - assigned as GEN project's claim approver)")
    print("  manager / Manager@123       (MANAGER - Priya Sharma, manages Ajai)")
    print("  ajai / Employee@123         (EMPLOYEE - Ajai Kumar, reports to Priya)")
finally:
    db.close()
