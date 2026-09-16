import re

from pydantic import BaseModel, field_validator


class ProjectBase(BaseModel):
    code: str
    name: str
    description: str | None = None
    is_active: bool = True


class ProjectCreate(ProjectBase):
    pass


class ProjectOut(ProjectBase):
    id: int
    accounts_approver_id: int | None = None
    accounts_user_ids: list[int] = []

    class Config:
        from_attributes = True


class AssignApproverRequest(BaseModel):
    user_id: int | None = None  # null clears the assignment


class AssignAccountsUsersRequest(BaseModel):
    user_ids: list[int] = []  # full-replace; empty list clears all assignments


class EmployeeBase(BaseModel):
    employee_code: str
    employee_name: str
    designation: str | None = None
    department: str | None = None
    manager_id: int | None = None
    email: str | None = None
    phone: str | None = None


class EmployeeCreate(EmployeeBase):
    bank_name: str | None = None
    account_number: str | None = None
    ifsc: str | None = None
    # Which projects this employee belongs to - they may only raise Employee
    # Claims against a project they're linked to here.
    project_ids: list[int] = []


class EmployeeOut(EmployeeBase):
    id: int
    status: str
    project_ids: list[int] = []

    class Config:
        from_attributes = True


class EmployeeDetailOut(EmployeeOut):
    """Includes bank details - only served to ACCOUNTS/ADMIN."""
    bank_name: str | None = None
    account_number: str | None = None
    ifsc: str | None = None


class VendorBase(BaseModel):
    vendor_code: str
    vendor_name: str
    location: str | None = None
    pincode: str | None = None
    gstin: str | None = None
    contact_person: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    products_services: str | None = None


class VendorCreate(VendorBase):
    bank_name: str | None = None
    account_number: str | None = None
    ifsc: str | None = None
    is_active: bool = True
    # Which projects this vendor belongs to. Empty = general/universal
    # vendor, visible regardless of project.
    project_ids: list[int] = []

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        if v is None or v.strip() == "":
            return v
        digits = re.sub(r"[\s\-()]", "", v)
        digits = re.sub(r"^(\+91|91|0)", "", digits)
        if not re.fullmatch(r"[6-9]\d{9}", digits):
            raise ValueError("Contact number must be a valid 10-digit mobile number")
        return digits


class VendorOut(VendorBase):
    id: int
    bank_name: str | None = None
    account_number: str | None = None
    ifsc: str | None = None
    has_qr_image: bool = False
    is_active: bool
    project_ids: list[int] = []

    class Config:
        from_attributes = True


class CategoryCreate(BaseModel):
    name: str


class CategoryOut(CategoryCreate):
    id: int
    in_use: bool = False

    class Config:
        from_attributes = True


class SubCategoryCreate(BaseModel):
    category_id: int
    name: str


class SubCategoryOut(SubCategoryCreate):
    id: int
    in_use: bool = False

    class Config:
        from_attributes = True


class AccountCreate(BaseModel):
    account_name: str
    account_type: str
    account_number: str | None = None
    bank_name: str | None = None
    ifsc: str | None = None


class AccountOut(AccountCreate):
    id: int
    is_active: bool

    class Config:
        from_attributes = True
