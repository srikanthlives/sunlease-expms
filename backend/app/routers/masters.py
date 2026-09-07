from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models.enums import RoleName
from app.models.models import (
    Project, ProjectAccountsUser, Employee, EmployeeProject, Vendor, VendorProject, ExpenseCategory, ExpenseSubCategory,
    Account, User, Expense, EmployeeClaim, EmployeeClaimLine, RecurringExpense,
)
from app.schemas.masters import (
    ProjectCreate, ProjectOut, AssignApproverRequest, AssignAccountsUsersRequest, EmployeeCreate, EmployeeOut, EmployeeDetailOut, VendorCreate, VendorOut,
    CategoryCreate, CategoryOut, SubCategoryCreate, SubCategoryOut, AccountCreate, AccountOut,
)
from app.services import project_scope_service

router = APIRouter(prefix="/api/v1", tags=["masters"])

# The Masters section (projects, employees, vendors, accounts, expense
# categories) is Admin-controlled only - create AND edit. Accounts staff use
# these records (via the GET endpoints, open to any authenticated user) but
# cannot create or modify them - that keeps org structure and vendor/account
# data under a single administrative authority.


# Projects
@router.post("/projects", response_model=ProjectOut, dependencies=[Depends(require_admin)])
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    if db.query(Project).filter(Project.code == payload.code).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Project code already exists")
    p = Project(**payload.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Project).order_by(Project.name)
    if user.role.name == RoleName.ACCOUNTS:
        assigned_ids = project_scope_service.get_accounts_assigned_project_ids(db, user)
        if not assigned_ids:
            return []
        query = query.filter(Project.id.in_(assigned_ids))
    return query.all()


@router.put("/projects/{project_id}", response_model=ProjectOut, dependencies=[Depends(require_admin)])
def update_project(project_id: int, payload: ProjectCreate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    dupe = db.query(Project).filter(Project.code == payload.code, Project.id != project_id).first()
    if dupe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Project code already exists")
    for field, value in payload.model_dump().items():
        setattr(project, field, value)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.post("/projects/{project_id}/assign-approver", response_model=ProjectOut, dependencies=[Depends(require_admin)])
def assign_project_approver(project_id: int, payload: AssignApproverRequest, db: Session = Depends(get_db)):
    """Assigns the Accounts user responsible for final (level-2) approval of
    employee claims charged to this project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    if payload.user_id is not None:
        user = db.query(User).filter(User.id == payload.user_id).first()
        if not user:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "User not found")
        if user.role.name not in (RoleName.ACCOUNTS, RoleName.ADMIN, RoleName.SUPER_ADMIN):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "The approver must have the Accounts, Admin, or Super Admin role")
    project.accounts_approver_id = payload.user_id
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.post("/projects/{project_id}/assign-accounts-users", response_model=ProjectOut, dependencies=[Depends(require_admin)])
def assign_project_accounts_users(project_id: int, payload: AssignAccountsUsersRequest, db: Session = Depends(get_db)):
    """Full-replace: sets exactly which Accounts (or Admin/Super Admin)
    users can see/act on this project's expenses/invoices/payments/claims.
    Distinct from assign-approver (that's only for claim level-2 approval
    routing)."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    user_ids = set(payload.user_ids)
    if user_ids:
        users = db.query(User).filter(User.id.in_(user_ids)).all()
        if len(users) != len(user_ids):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "One or more users not found")
        for u in users:
            if u.role.name not in (RoleName.ACCOUNTS, RoleName.ADMIN, RoleName.SUPER_ADMIN):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Assigned users must have the Accounts, Admin, or Super Admin role")
    db.query(ProjectAccountsUser).filter(ProjectAccountsUser.project_id == project_id).delete()
    for uid in user_ids:
        db.add(ProjectAccountsUser(project_id=project_id, user_id=uid))
    db.commit()
    db.refresh(project)
    return project


# Employees
def _set_employee_projects(db: Session, employee: Employee, project_ids: list[int]):
    project_ids = set(project_ids)
    if project_ids:
        found = db.query(Project.id).filter(Project.id.in_(project_ids)).count()
        if found != len(project_ids):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "One or more projects not found")
    db.query(EmployeeProject).filter(EmployeeProject.employee_id == employee.id).delete()
    for pid in project_ids:
        db.add(EmployeeProject(employee_id=employee.id, project_id=pid))


@router.post("/employees", response_model=EmployeeOut, dependencies=[Depends(require_admin)])
def create_employee(payload: EmployeeCreate, db: Session = Depends(get_db)):
    if db.query(Employee).filter(Employee.employee_code == payload.employee_code).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Employee code already exists")
    if payload.manager_id:
        manager = db.query(Employee).filter(Employee.id == payload.manager_id).first()
        if not manager:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Manager not found")
    data = payload.model_dump()
    project_ids = data.pop("project_ids")
    e = Employee(**data)
    db.add(e)
    db.flush()
    _set_employee_projects(db, e, project_ids)
    db.commit()
    db.refresh(e)
    return e


@router.get("/employees", response_model=list[EmployeeOut])
def list_employees(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(Employee).order_by(Employee.employee_name).all()


@router.get("/employees/{employee_id}", response_model=EmployeeDetailOut)
def get_employee(employee_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    e = db.query(Employee).filter(Employee.id == employee_id).first()
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    out = EmployeeDetailOut.model_validate(e)
    if user.role.name not in (RoleName.ADMIN, RoleName.SUPER_ADMIN, RoleName.ACCOUNTS):
        out.bank_name = None
        out.account_number = None
        out.ifsc = None
    return out


@router.put("/employees/{employee_id}", response_model=EmployeeOut, dependencies=[Depends(require_admin)])
def update_employee(employee_id: int, payload: EmployeeCreate, db: Session = Depends(get_db)):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    dupe = db.query(Employee).filter(Employee.employee_code == payload.employee_code, Employee.id != employee_id).first()
    if dupe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Employee code already exists")
    if payload.manager_id:
        if payload.manager_id == employee_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "An employee cannot be their own manager")
        manager = db.query(Employee).filter(Employee.id == payload.manager_id).first()
        if not manager:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Manager not found")
    data = payload.model_dump()
    project_ids = data.pop("project_ids")
    for field, value in data.items():
        setattr(employee, field, value)
    db.add(employee)
    _set_employee_projects(db, employee, project_ids)
    db.commit()
    db.refresh(employee)
    return employee


# Vendors
def _set_vendor_projects(db: Session, vendor: Vendor, project_ids: list[int]):
    project_ids = set(project_ids)
    if project_ids:
        found = db.query(Project.id).filter(Project.id.in_(project_ids)).count()
        if found != len(project_ids):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "One or more projects not found")
    db.query(VendorProject).filter(VendorProject.vendor_id == vendor.id).delete()
    for pid in project_ids:
        db.add(VendorProject(vendor_id=vendor.id, project_id=pid))


@router.post("/vendors", response_model=VendorOut, dependencies=[Depends(require_admin)])
def create_vendor(payload: VendorCreate, db: Session = Depends(get_db)):
    if db.query(Vendor).filter(Vendor.vendor_code == payload.vendor_code).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Vendor code already exists")
    data = payload.model_dump()
    project_ids = data.pop("project_ids")
    v = Vendor(**data)
    db.add(v)
    db.flush()
    _set_vendor_projects(db, v, project_ids)
    db.commit()
    db.refresh(v)
    return v


@router.get("/vendors", response_model=list[VendorOut])
def list_vendors(db: Session = Depends(get_db), user: User = Depends(get_current_user), project_id: int | None = None):
    """Vendors with no project links are general/universal - always visible.
    Otherwise: a project_id filter narrows to vendors linked to that project;
    an ACCOUNTS user with no project_id filter is narrowed to vendors
    reachable from any project they're assigned to (mirrors how they're
    scoped everywhere else - see project_scope_service)."""
    q = db.query(Vendor)
    has_links = Vendor.project_links.any()

    if project_id is not None:
        if user.role.name == RoleName.ACCOUNTS:
            assigned = project_scope_service.get_accounts_assigned_project_ids(db, user)
            if project_id not in assigned:
                return []
        q = q.filter(or_(Vendor.project_links.any(VendorProject.project_id == project_id), ~has_links))
    elif user.role.name == RoleName.ACCOUNTS:
        assigned = project_scope_service.get_accounts_assigned_project_ids(db, user)
        if assigned:
            q = q.filter(or_(Vendor.project_links.any(VendorProject.project_id.in_(assigned)), ~has_links))
        else:
            q = q.filter(~has_links)

    return q.order_by(Vendor.vendor_name).distinct().all()


@router.put("/vendors/{vendor_id}", response_model=VendorOut, dependencies=[Depends(require_admin)])
def update_vendor(vendor_id: int, payload: VendorCreate, db: Session = Depends(get_db)):
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vendor not found")
    dupe = db.query(Vendor).filter(Vendor.vendor_code == payload.vendor_code, Vendor.id != vendor_id).first()
    if dupe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Vendor code already exists")
    data = payload.model_dump()
    project_ids = data.pop("project_ids")
    for field, value in data.items():
        setattr(vendor, field, value)
    db.add(vendor)
    _set_vendor_projects(db, vendor, project_ids)
    db.commit()
    db.refresh(vendor)
    return vendor


# Categories
def _category_ids_in_use(db: Session) -> set[int]:
    """Every ExpenseCategory id referenced anywhere - deleting one of these
    would orphan real transactional data, so it's never allowed."""
    ids: set[int] = set()
    for row in db.query(Expense.category_id).filter(Expense.category_id.isnot(None)).distinct():
        ids.add(row[0])
    for row in db.query(EmployeeClaim.category_id).filter(EmployeeClaim.category_id.isnot(None)).distinct():
        ids.add(row[0])
    for row in db.query(EmployeeClaimLine.expense_head_id).distinct():
        ids.add(row[0])
    for row in db.query(RecurringExpense.category_id).distinct():
        ids.add(row[0])
    return ids


def _sub_category_ids_in_use(db: Session) -> set[int]:
    ids: set[int] = set()
    for row in db.query(Expense.sub_category_id).filter(Expense.sub_category_id.isnot(None)).distinct():
        ids.add(row[0])
    for row in db.query(EmployeeClaimLine.expense_sub_head_id).filter(EmployeeClaimLine.expense_sub_head_id.isnot(None)).distinct():
        ids.add(row[0])
    for row in db.query(RecurringExpense.sub_category_id).filter(RecurringExpense.sub_category_id.isnot(None)).distinct():
        ids.add(row[0])
    return ids


@router.post("/categories", response_model=CategoryOut, dependencies=[Depends(require_admin)])
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)):
    c = ExpenseCategory(name=payload.name)
    db.add(c)
    db.commit()
    db.refresh(c)
    out = CategoryOut.model_validate(c)
    out.in_use = False
    return out


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db), _=Depends(get_current_user)):
    categories = db.query(ExpenseCategory).order_by(ExpenseCategory.name).all()
    in_use = _category_ids_in_use(db)
    out = []
    for c in categories:
        o = CategoryOut.model_validate(c)
        o.in_use = c.id in in_use
        out.append(o)
    return out


@router.get("/categories/export")
def export_categories(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Every Head with its Sub-Heads as an .xlsx, one row per Head/Sub-Head
    pair (a Head with no sub-categories still gets a row, sub-head blank) -
    a quick reference sheet of everything usable in the Head/Sub-Head
    dropdowns across expenses, invoices, claims and recurring expenses."""
    import io
    from openpyxl import Workbook
    from fastapi.responses import StreamingResponse

    categories = db.query(ExpenseCategory).order_by(ExpenseCategory.name).all()
    sub_categories = db.query(ExpenseSubCategory).order_by(ExpenseSubCategory.category_id, ExpenseSubCategory.name).all()
    subs_by_category: dict[int, list[ExpenseSubCategory]] = {}
    for s in sub_categories:
        subs_by_category.setdefault(s.category_id, []).append(s)

    wb = Workbook()
    ws = wb.active
    ws.title = "Categories"
    ws.append(["Head", "Sub-Head"])
    for c in categories:
        subs = subs_by_category.get(c.id, [])
        if not subs:
            ws.append([c.name, ""])
        else:
            for s in subs:
                ws.append([c.name, s.name])
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 32

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=expense_categories.xlsx"},
    )


@router.put("/categories/{category_id}", response_model=CategoryOut, dependencies=[Depends(require_admin)])
def update_category(category_id: int, payload: CategoryCreate, db: Session = Depends(get_db)):
    category = db.query(ExpenseCategory).filter(ExpenseCategory.id == category_id).first()
    if not category:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    dupe = db.query(ExpenseCategory).filter(ExpenseCategory.name == payload.name, ExpenseCategory.id != category_id).first()
    if dupe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A category with this name already exists")
    category.name = payload.name
    db.add(category)
    db.commit()
    db.refresh(category)
    out = CategoryOut.model_validate(category)
    out.in_use = category.id in _category_ids_in_use(db)
    return out


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
def delete_category(category_id: int, db: Session = Depends(get_db)):
    category = db.query(ExpenseCategory).filter(ExpenseCategory.id == category_id).first()
    if not category:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    if category_id in _category_ids_in_use(db):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This category has expenses, claims or recurring expenses recorded against it and cannot be deleted")
    sub_ids_in_use = _sub_category_ids_in_use(db)
    subs = db.query(ExpenseSubCategory).filter(ExpenseSubCategory.category_id == category_id).all()
    blocked = [s for s in subs if s.id in sub_ids_in_use]
    if blocked:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Sub-category '{blocked[0].name}' under this category is in use and must be cleared first")
    for s in subs:
        db.delete(s)
    db.delete(category)
    db.commit()


@router.post("/categories/{category_id}/sub-categories", response_model=SubCategoryOut, dependencies=[Depends(require_admin)])
def create_sub_category(category_id: int, payload: SubCategoryCreate, db: Session = Depends(get_db)):
    if not db.query(ExpenseCategory).filter(ExpenseCategory.id == category_id).first():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    s = ExpenseSubCategory(category_id=category_id, name=payload.name)
    db.add(s)
    db.commit()
    db.refresh(s)
    out = SubCategoryOut.model_validate(s)
    out.in_use = False
    return out


@router.get("/categories/{category_id}/sub-categories", response_model=list[SubCategoryOut])
def list_sub_categories(category_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    subs = db.query(ExpenseSubCategory).filter(ExpenseSubCategory.category_id == category_id).all()
    in_use = _sub_category_ids_in_use(db)
    out = []
    for s in subs:
        o = SubCategoryOut.model_validate(s)
        o.in_use = s.id in in_use
        out.append(o)
    return out


@router.put("/categories/{category_id}/sub-categories/{sub_category_id}", response_model=SubCategoryOut, dependencies=[Depends(require_admin)])
def update_sub_category(category_id: int, sub_category_id: int, payload: SubCategoryCreate, db: Session = Depends(get_db)):
    sub = db.query(ExpenseSubCategory).filter(ExpenseSubCategory.id == sub_category_id, ExpenseSubCategory.category_id == category_id).first()
    if not sub:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sub-category not found")
    dupe = db.query(ExpenseSubCategory).filter(
        ExpenseSubCategory.category_id == payload.category_id, ExpenseSubCategory.name == payload.name, ExpenseSubCategory.id != sub_category_id
    ).first()
    if dupe:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A sub-category with this name already exists under that category")
    sub.name = payload.name
    if payload.category_id != category_id:
        if not db.query(ExpenseCategory).filter(ExpenseCategory.id == payload.category_id).first():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Target category not found")
        sub.category_id = payload.category_id
    db.add(sub)
    db.commit()
    db.refresh(sub)
    out = SubCategoryOut.model_validate(sub)
    out.in_use = sub.id in _sub_category_ids_in_use(db)
    return out


@router.delete("/categories/{category_id}/sub-categories/{sub_category_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
def delete_sub_category(category_id: int, sub_category_id: int, db: Session = Depends(get_db)):
    sub = db.query(ExpenseSubCategory).filter(ExpenseSubCategory.id == sub_category_id, ExpenseSubCategory.category_id == category_id).first()
    if not sub:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sub-category not found")
    if sub_category_id in _sub_category_ids_in_use(db):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This sub-category has expenses, claims or recurring expenses recorded against it and cannot be deleted")
    db.delete(sub)
    db.commit()


@router.post("/categories/import", dependencies=[Depends(require_admin)])
async def import_categories(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Bulk-add Heads/Sub-Heads from an .xlsx with "Head"/"Sub-Head" columns
    (the same shape GET /categories/export produces). A Head that already
    exists (case-insensitive name match) is left alone - only its NEW
    sub-heads from the sheet get added under it. A Head not seen before is
    created, along with any sub-head the sheet lists for it. Never deletes
    or renames anything - purely additive, safe to re-run."""
    if not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only .xlsx/.xlsm files are supported")
    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty")

    import io
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not read workbook: {exc}")
    if not rows:
        return {"categories_created": [], "sub_categories_created": []}

    header = [str(h or "").strip().lower() for h in rows[0]]
    try:
        head_idx = header.index("head")
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing required 'Head' column")
    sub_idx = header.index("sub-head") if "sub-head" in header else None

    categories_by_name = {c.name.strip().lower(): c for c in db.query(ExpenseCategory).all()}
    sub_categories_by_category: dict[int, dict[str, ExpenseSubCategory]] = {}
    for s in db.query(ExpenseSubCategory).all():
        sub_categories_by_category.setdefault(s.category_id, {})[s.name.strip().lower()] = s

    categories_created: list[str] = []
    sub_categories_created: list[str] = []

    for raw in rows[1:]:
        if raw is None:
            continue
        head_name = str(raw[head_idx] or "").strip() if head_idx < len(raw) else ""
        if not head_name:
            continue
        sub_name = ""
        if sub_idx is not None and sub_idx < len(raw):
            sub_name = str(raw[sub_idx] or "").strip()

        category = categories_by_name.get(head_name.lower())
        if not category:
            category = ExpenseCategory(name=head_name)
            db.add(category)
            db.flush()
            categories_by_name[head_name.lower()] = category
            sub_categories_by_category[category.id] = {}
            categories_created.append(head_name)

        if sub_name:
            existing_subs = sub_categories_by_category.setdefault(category.id, {})
            if sub_name.lower() not in existing_subs:
                sub = ExpenseSubCategory(category_id=category.id, name=sub_name)
                db.add(sub)
                db.flush()
                existing_subs[sub_name.lower()] = sub
                sub_categories_created.append(f"{head_name} / {sub_name}")

    db.commit()
    return {"categories_created": categories_created, "sub_categories_created": sub_categories_created}


# Accounts (bank/cash accounts used for payments)
@router.post("/accounts", response_model=AccountOut, dependencies=[Depends(require_admin)])
def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    a = Account(**payload.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(Account).order_by(Account.account_name).all()


@router.put("/accounts/{account_id}", response_model=AccountOut, dependencies=[Depends(require_admin)])
def update_account(account_id: int, payload: AccountCreate, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    for field, value in payload.model_dump().items():
        setattr(account, field, value)
    db.add(account)
    db.commit()
    db.refresh(account)
    return account
