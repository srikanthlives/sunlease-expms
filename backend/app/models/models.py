import datetime as dt

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


def now():
    return dt.datetime.utcnow()


# ---------------------------------------------------------------------------
# Auth / Identity
# ---------------------------------------------------------------------------

class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(255))
    created_at = Column(DateTime, default=now)

    users = relationship("User", back_populates="role")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    role = relationship("Role", back_populates="users")
    employee = relationship("Employee", back_populates="user", foreign_keys=[employee_id])


# ---------------------------------------------------------------------------
# Masters
# ---------------------------------------------------------------------------

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    # The Accounts user responsible for second-level (final) approval of
    # employee claims charged to this project. Nullable - a project without
    # an assigned approver falls back to any Accounts user or Admin/Super Admin.
    accounts_approver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    accounts_approver = relationship("User", foreign_keys=[accounts_approver_id])
    accounts_user_links = relationship("ProjectAccountsUser", foreign_keys="ProjectAccountsUser.project_id")

    @property
    def accounts_user_ids(self):
        return [link.user_id for link in self.accounts_user_links]


class ProjectAccountsUser(Base):
    """Many-to-many: which ACCOUNTS (or Admin/Super Admin) users are allowed
    to see/act on this project's expenses, invoices, payments and claims.
    Distinct from Project.accounts_approver_id (single field, only used for
    claim level-2 approval routing) - this table controls general
    transactional visibility/scope for Accounts users, who (per this
    feature) always operate project-scoped rather than company-wide."""

    __tablename__ = "project_accounts_users"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=now)

    project = relationship("Project", foreign_keys=[project_id], overlaps="accounts_user_links")
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_accounts_user"),)


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True)
    employee_code = Column(String(50), unique=True, nullable=False)
    employee_name = Column(String(255), nullable=False)
    designation = Column(String(150))
    department = Column(String(150))
    manager_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    email = Column(String(255))
    phone = Column(String(50))
    # Restricted bank details - only exposed to ACCOUNTS/ADMIN in schemas.
    bank_name = Column(String(255))
    account_number = Column(String(100))
    ifsc = Column(String(20))
    status = Column(String(20), default="ACTIVE")
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    manager = relationship("Employee", remote_side=[id])
    user = relationship("User", back_populates="employee", uselist=False, foreign_keys=[User.employee_id])
    project_links = relationship("EmployeeProject", foreign_keys="EmployeeProject.employee_id")

    @property
    def project_ids(self):
        return [link.project_id for link in self.project_links]


class EmployeeProject(Base):
    """Many-to-many: which projects an employee belongs to. An employee may
    only raise Employee Claims against a project they're linked to here
    (enforced in claims.py::_assert_claim_project_allowed) - mirrors the
    VendorProject / ProjectAccountsUser pattern used elsewhere."""

    __tablename__ = "employee_projects"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    created_at = Column(DateTime, default=now)

    employee = relationship("Employee", foreign_keys=[employee_id], overlaps="project_links")
    project = relationship("Project", foreign_keys=[project_id])

    __table_args__ = (UniqueConstraint("employee_id", "project_id", name="uq_employee_project"),)


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)

    sub_categories = relationship("ExpenseSubCategory", back_populates="category")


class ExpenseSubCategory(Base):
    __tablename__ = "expense_sub_categories"

    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("expense_categories.id"), nullable=False)
    name = Column(String(150), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)

    category = relationship("ExpenseCategory", back_populates="sub_categories")
    __table_args__ = (UniqueConstraint("category_id", "name", name="uq_subcat_per_cat"),)


class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True)
    vendor_code = Column(String(50), unique=True, nullable=False)
    vendor_name = Column(String(255), nullable=False)
    location = Column(String(255))
    gstin = Column(String(20))
    contact_person = Column(String(150))
    phone = Column(String(50))
    email = Column(String(255))
    address = Column(Text)
    bank_name = Column(String(255))
    account_number = Column(String(100))
    ifsc = Column(String(20))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    project_links = relationship("VendorProject", foreign_keys="VendorProject.vendor_id")

    @property
    def project_ids(self):
        return [link.project_id for link in self.project_links]


class VendorProject(Base):
    """Many-to-many: which projects a vendor belongs to. A vendor tied to no
    project is a general/universal vendor, visible regardless of project.
    Otherwise expense/invoice vendor pickers only offer vendors linked to the
    project in hand, and an ACCOUNTS user (project-scoped, see
    project_scope_service) only ever sees vendors reachable from a project
    they're assigned to."""

    __tablename__ = "vendor_projects"

    id = Column(Integer, primary_key=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    created_at = Column(DateTime, default=now)

    vendor = relationship("Vendor", foreign_keys=[vendor_id], overlaps="project_links")
    project = relationship("Project", foreign_keys=[project_id])

    __table_args__ = (UniqueConstraint("vendor_id", "project_id", name="uq_vendor_project"),)


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    account_name = Column(String(255), nullable=False)
    account_type = Column(String(30), nullable=False)  # BANK, CASH, UPI, PETTY_CASH
    account_number = Column(String(100))
    bank_name = Column(String(255))
    ifsc = Column(String(20))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

class Expense(Base):
    """Unified accounting expense record - the hub every transaction source
    (invoice / direct expense / employee-claim line) resolves into."""

    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True)
    expense_number = Column(String(50), unique=True, nullable=False, index=True)
    source_type = Column(String(30), nullable=False)  # SourceType
    source_id = Column(Integer, nullable=True)  # id of invoice / claim_line (null for direct expense)

    expense_date = Column(Date, nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    category_id = Column(Integer, ForeignKey("expense_categories.id"), nullable=True)
    sub_category_id = Column(Integer, ForeignKey("expense_sub_categories.id"), nullable=True)

    # Free-text payee identity for DIRECT_EXPENSE (no vendor master record
    # required) - vendor_id stays null for that source_type.
    supplier_name = Column(String(255), nullable=True)
    bill_number = Column(String(100), nullable=True)

    description = Column(Text)
    base_amount = Column(Numeric(14, 2), nullable=False, default=0)
    gst_amount = Column(Numeric(14, 2), nullable=False, default=0)
    other_amount = Column(Numeric(14, 2), nullable=False, default=0)
    total_amount = Column(Numeric(14, 2), nullable=False)

    status = Column(String(20), default="ACTIVE")  # ACTIVE / CANCELLED
    payment_status = Column(String(20), default="UNPAID")  # derived; never set directly by API

    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    project = relationship("Project", foreign_keys=[project_id])
    vendor = relationship("Vendor", foreign_keys=[vendor_id])
    employee = relationship("Employee", foreign_keys=[employee_id])
    category = relationship("ExpenseCategory", foreign_keys=[category_id])
    sub_category = relationship("ExpenseSubCategory", foreign_keys=[sub_category_id])
    allocations = relationship("PaymentAllocation", back_populates="expense")
    documents = relationship("Document", back_populates="expense", foreign_keys="Document.expense_id")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    invoice_number = Column(String(100), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    description = Column(Text)

    taxable_amount = Column(Numeric(14, 2), nullable=False, default=0)
    cgst = Column(Numeric(14, 2), nullable=False, default=0)
    sgst = Column(Numeric(14, 2), nullable=False, default=0)
    igst = Column(Numeric(14, 2), nullable=False, default=0)
    other_tax = Column(Numeric(14, 2), nullable=False, default=0)
    total_amount = Column(Numeric(14, 2), nullable=False)

    status = Column(String(20), default="RECORDED")  # RECORDED / CANCELLED
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=False)

    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    vendor = relationship("Vendor", foreign_keys=[vendor_id])
    project = relationship("Project", foreign_keys=[project_id])
    expense = relationship("Expense", foreign_keys=[expense_id])
    __table_args__ = (UniqueConstraint("vendor_id", "invoice_number", name="uq_invoice_per_vendor"),)


class EmployeeClaim(Base):
    __tablename__ = "employee_claims"

    id = Column(Integer, primary_key=True)
    claim_number = Column(String(50), unique=True, nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    claim_date = Column(Date, nullable=False)  # accounting/submission date, per business rule
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    # Overall Expense Head for the whole claim - carried through directly to
    # the consolidated Expense created on final approval (see claim_service),
    # rather than only inferring a category when every line happens to agree.
    category_id = Column(Integer, ForeignKey("expense_categories.id"), nullable=True)
    description = Column(Text)
    total_amount = Column(Numeric(14, 2), nullable=False, default=0)

    status = Column(String(20), default="DRAFT")  # ClaimStatus
    submitted_at = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    # Set once accounts gives final approval - the whole claim (all lines
    # combined) becomes ONE Expense record, not one per line.
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=True)

    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    employee = relationship("Employee", foreign_keys=[employee_id])
    project = relationship("Project", foreign_keys=[project_id])
    category = relationship("ExpenseCategory", foreign_keys=[category_id])
    lines = relationship("EmployeeClaimLine", back_populates="claim", cascade="all, delete-orphan")
    expense = relationship("Expense", foreign_keys=[expense_id])

    @property
    def expense_number(self):
        return self.expense.expense_number if self.expense_id and self.expense else None


class EmployeeClaimLine(Base):
    __tablename__ = "employee_claim_lines"

    id = Column(Integer, primary_key=True)
    claim_id = Column(Integer, ForeignKey("employee_claims.id"), nullable=False)
    expense_date = Column(Date, nullable=False)  # original date, kept for reference only
    expense_head_id = Column(Integer, ForeignKey("expense_categories.id"), nullable=False)
    expense_sub_head_id = Column(Integer, ForeignKey("expense_sub_categories.id"), nullable=True)
    description = Column(Text)
    amount = Column(Numeric(14, 2), nullable=False)
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=True)  # set once claim is approved

    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    claim = relationship("EmployeeClaim", back_populates="lines")
    expense_head = relationship("ExpenseCategory", foreign_keys=[expense_head_id])
    expense_sub_head = relationship("ExpenseSubCategory", foreign_keys=[expense_sub_head_id])
    expense = relationship("Expense", foreign_keys=[expense_id])


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    payment_number = Column(String(50), unique=True, nullable=False, index=True)
    payment_date = Column(Date, nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    payment_mode = Column(String(30), nullable=False)  # NEFT / RTGS / IMPS / UPI / CASH / CHEQUE
    amount = Column(Numeric(14, 2), nullable=False)
    reference_number = Column(String(150))
    remarks = Column(Text)
    is_cancelled = Column(Boolean, default=False)

    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    vendor = relationship("Vendor", foreign_keys=[vendor_id])
    employee = relationship("Employee", foreign_keys=[employee_id])
    account = relationship("Account", foreign_keys=[account_id])
    allocations = relationship("PaymentAllocation", back_populates="payment", cascade="all, delete-orphan")


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"

    id = Column(Integer, primary_key=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False)
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=False)
    allocated_amount = Column(Numeric(14, 2), nullable=False)
    created_at = Column(DateTime, default=now)

    payment = relationship("Payment", back_populates="allocations")
    expense = relationship("Expense", back_populates="allocations")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=True)
    claim_id = Column(Integer, ForeignKey("employee_claims.id"), nullable=True)
    claim_line_id = Column(Integer, ForeignKey("employee_claim_lines.id"), nullable=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True)

    document_type = Column(String(30), nullable=False)  # DocumentType
    original_filename = Column(String(500), nullable=False)
    stored_filename = Column(String(255), nullable=False, unique=True)
    file_path = Column(String(1000), nullable=False)
    mime_type = Column(String(150), nullable=False)
    file_size = Column(Integer, nullable=False)

    uploaded_by = Column(Integer, ForeignKey("users.id"))
    uploaded_at = Column(DateTime, default=now)

    expense = relationship("Expense", back_populates="documents", foreign_keys=[expense_id])


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True)
    entity_type = Column(String(30), nullable=False)  # ApprovalEntityType
    entity_id = Column(Integer, nullable=False)
    action = Column(String(20), nullable=False)  # ApprovalAction
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    remarks = Column(Text)
    step_name = Column(String(100))  # e.g. MANAGER, PROJECT_MANAGER, MANAGEMENT
    created_at = Column(DateTime, default=now)


class ApprovalRule(Base):
    """Configurable approval thresholds instead of hard-coded amounts."""

    __tablename__ = "approval_rules"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    entity_type = Column(String(30), nullable=False, default="CLAIM")
    min_amount = Column(Numeric(14, 2), nullable=False, default=0)
    max_amount = Column(Numeric(14, 2), nullable=True)  # null = no upper bound
    required_steps = Column(String(500), nullable=False)  # comma-separated role names, in order
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Integer, nullable=False)
    action = Column(String(30), nullable=False)  # AuditAction
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    details = Column(Text)  # JSON string snapshot / diff
    created_at = Column(DateTime, default=now)


class RecurringExpense(Base):
    """Template for a bill that recurs on a fixed schedule (rent, internet,
    power bill, etc.). Does not itself post to the ledger - each cycle it
    spawns a RecurringExpenseInstance a configurable number of days ahead of
    the actual bill date, which goes through Accounts review + Admin
    approval before becoming a real Expense (see recurring_expense_service)."""

    __tablename__ = "recurring_expenses"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    frequency = Column(String(20), nullable=False)  # RecurrenceFrequency
    amount_type = Column(String(10), nullable=False)  # RecurringAmountType
    # Required (and used to pre-fill each instance) when amount_type=FIXED.
    # Still editable per-instance by Accounts if a particular bill changed.
    fixed_amount = Column(Numeric(14, 2), nullable=True)
    # How many days before next_occurrence_date an approval instance is
    # generated - the "goes to approval a few days before the actual bill
    # date" lead time, configurable per recurring expense.
    lead_days = Column(Integer, nullable=False, default=7)
    # Bill due date = occurrence_date + due_in_days. Null = no due date tracked.
    due_in_days = Column(Integer, nullable=True)

    # Who the bill is paid to - mirrors Expense's source_type distinction:
    # DIRECT (no vendor master record, free-text payee), VENDOR (vendor
    # master) or EMPLOYEE (reimbursement-style, e.g. guesthouse rent paid by
    # an employee). Exactly one of vendor_id/employee_id/supplier_name is set,
    # matching payee_type.
    payee_type = Column(String(10), nullable=False, default="DIRECT")  # RecurringPayeeType
    supplier_name = Column(String(255), nullable=True)  # used when payee_type=DIRECT
    # No bill/voucher number here - it isn't known until an actual bill
    # arrives, so it's captured per-instance by Accounts at review time
    # instead (see RecurringExpenseInstance.bill_number).

    # Every recurring expense must be tied to a project.
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    category_id = Column(Integer, ForeignKey("expense_categories.id"), nullable=False)
    sub_category_id = Column(Integer, ForeignKey("expense_sub_categories.id"), nullable=True)
    description = Column(Text)

    # Next bill date this template will generate an instance for. Advances by
    # one `frequency` step every time an instance is generated for it.
    next_occurrence_date = Column(Date, nullable=False)
    is_active = Column(Boolean, default=True)

    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    project = relationship("Project", foreign_keys=[project_id])
    vendor = relationship("Vendor", foreign_keys=[vendor_id])
    employee = relationship("Employee", foreign_keys=[employee_id])
    category = relationship("ExpenseCategory", foreign_keys=[category_id])
    sub_category = relationship("ExpenseSubCategory", foreign_keys=[sub_category_id])


class RecurringExpenseInstance(Base):
    """One generated occurrence of a RecurringExpense, working through the
    two-stage approval (Accounts, then Admin/Super Admin) before becoming an
    actual Expense."""

    __tablename__ = "recurring_expense_instances"

    id = Column(Integer, primary_key=True)
    recurring_expense_id = Column(Integer, ForeignKey("recurring_expenses.id"), nullable=False)
    occurrence_date = Column(Date, nullable=False)  # the bill date this instance represents
    due_date = Column(Date, nullable=True)
    # Pre-filled with the template's fixed_amount for FIXED; null (Accounts
    # must fill it in) for OPEN.
    amount = Column(Numeric(14, 2), nullable=True)
    # Voucher/bill number off the actual physical bill - unknowable at
    # template-creation time (the bill hasn't arrived yet), so Accounts
    # enters it here at review time, right before sending to Admin.
    bill_number = Column(String(100), nullable=True)
    description = Column(Text)

    status = Column(String(30), nullable=False, default="PENDING_ACCOUNTS_REVIEW")  # RecurringInstanceStatus

    accounts_reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    accounts_reviewed_at = Column(DateTime, nullable=True)
    admin_reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    admin_reviewed_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=True)  # set once Admin-approved
    generated_at = Column(DateTime, default=now)

    recurring_expense = relationship("RecurringExpense", foreign_keys=[recurring_expense_id])
    expense = relationship("Expense", foreign_keys=[expense_id])
    accounts_reviewer = relationship("User", foreign_keys=[accounts_reviewed_by])
    admin_reviewer = relationship("User", foreign_keys=[admin_reviewed_by])

    __table_args__ = (UniqueConstraint("recurring_expense_id", "occurrence_date", name="uq_recurring_instance_occurrence"),)


class EditRequest(Base):
    """A proposed edit to an already-posted Expense/Invoice/Payment, made by
    an Accounts user, pending Admin/Super Admin review. Admin/Super Admin
    edit these entities directly (no row created here) - this table exists
    specifically so Accounts edits go through approval, and so there's a
    durable history of what was approved vs rejected and by whom."""

    __tablename__ = "edit_requests"

    id = Column(Integer, primary_key=True)
    entity_type = Column(String(30), nullable=False)  # EditableEntityType
    entity_id = Column(Integer, nullable=False)
    changes = Column(Text, nullable=False)  # JSON: {field: new_value}
    previous_values = Column(Text, nullable=False)  # JSON: {field: old_value} snapshot at request time

    status = Column(String(20), default="PENDING")  # EditRequestStatus
    requested_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    requested_at = Column(DateTime, default=now)

    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_remarks = Column(Text, nullable=True)

    requester = relationship("User", foreign_keys=[requested_by])
    reviewer = relationship("User", foreign_keys=[reviewed_by])
