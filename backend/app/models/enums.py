"""Plain string constants used as 'status'/'type' values.

SQLite has no native enum type and enum migrations are painful, so these
are stored as plain strings (validated at the Pydantic/service layer)
rather than DB-level enums. This keeps the schema easy to extend later
(e.g. adding TDS/GST modules) without an Alembic enum-altering migration.
"""


class RoleName:
    EMPLOYEE = "EMPLOYEE"
    MANAGER = "MANAGER"
    ACCOUNTS = "ACCOUNTS"
    ADMIN = "ADMIN"
    VIEWER = "VIEWER"
    SUPER_ADMIN = "SUPER_ADMIN"

    ALL = [EMPLOYEE, MANAGER, ACCOUNTS, ADMIN, VIEWER, SUPER_ADMIN]


class SourceType:
    INVOICE = "INVOICE"
    DIRECT_EXPENSE = "DIRECT_EXPENSE"
    EMPLOYEE_CLAIM = "EMPLOYEE_CLAIM"
    RECURRING_EXPENSE = "RECURRING_EXPENSE"


class ExpenseStatus:
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"


class PaymentStatus:
    UNPAID = "UNPAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"


class InvoiceStatus:
    DRAFT = "DRAFT"
    RECORDED = "RECORDED"
    CANCELLED = "CANCELLED"


class ClaimStatus:
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"                        # awaiting the employee's manager (level 1)
    PENDING_ACCOUNTS_APPROVAL = "PENDING_ACCOUNTS_APPROVAL"  # manager approved, awaiting the project's accounts approver (level 2)
    APPROVED = "APPROVED"                          # accounts approved - final; expenses created
    REJECTED = "REJECTED"                          # rejected at either level; employee edits & resubmits
    CANCELLED = "CANCELLED"


class DocumentType:
    EXPENSE = "EXPENSE"
    INVOICE = "INVOICE"
    CLAIM = "CLAIM"
    CLAIM_LINE = "CLAIM_LINE"
    PAYMENT = "PAYMENT"


class ApprovalEntityType:
    CLAIM = "CLAIM"
    EXPENSE = "EXPENSE"


class ApprovalAction:
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class AuditAction:
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    CANCEL = "CANCEL"
    SUBMIT = "SUBMIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    PAY = "PAY"
    LOGIN = "LOGIN"


class EditRequestStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class EditableEntityType:
    EXPENSE = "EXPENSE"
    INVOICE = "INVOICE"
    PAYMENT = "PAYMENT"


class RecurrenceFrequency:
    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    HALF_YEARLY = "HALF_YEARLY"
    ANNUALLY = "ANNUALLY"

    ALL = [WEEKLY, BIWEEKLY, MONTHLY, QUARTERLY, HALF_YEARLY, ANNUALLY]


class RecurringAmountType:
    FIXED = "FIXED"
    OPEN = "OPEN"

    ALL = [FIXED, OPEN]


class RecurringPayeeType:
    DIRECT = "DIRECT"      # free-text payee, no vendor/employee master record
    VENDOR = "VENDOR"
    EMPLOYEE = "EMPLOYEE"

    ALL = [DIRECT, VENDOR, EMPLOYEE]


class RecurringInstanceStatus:
    # Awaiting Accounts: for OPEN amount type they must fill in the actual
    # bill amount; for FIXED they may correct it if the bill changed. Either
    # way Accounts must act before it goes to Admin.
    PENDING_ACCOUNTS_REVIEW = "PENDING_ACCOUNTS_REVIEW"
    PENDING_ADMIN_APPROVAL = "PENDING_ADMIN_APPROVAL"
    APPROVED = "APPROVED"  # Expense created
    REJECTED = "REJECTED"
