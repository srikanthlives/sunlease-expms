from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_roles(*role_names: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role.name not in role_names:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(role_names)}",
            )
        return user

    return checker


# Convenience shorthands used across routers.
# SUPER_ADMIN is a superset of ADMIN everywhere ADMIN is allowed, plus has
# exclusive access to role management, creating Admin accounts, and password
# resets (see auth router).
require_super_admin = require_roles("SUPER_ADMIN")
require_admin = require_roles("SUPER_ADMIN", "ADMIN")
require_accounts = require_roles("SUPER_ADMIN", "ADMIN", "ACCOUNTS")
require_manager = require_roles("SUPER_ADMIN", "ADMIN", "MANAGER")
# Claim approve/reject: Manager (level 1, their own reports) and Accounts
# (level 2, their assigned projects) both call the same endpoints - the
# service layer enforces exactly *which* claims each caller may act on.
require_approver = require_roles("SUPER_ADMIN", "ADMIN", "MANAGER", "ACCOUNTS")
require_any = require_roles("SUPER_ADMIN", "ADMIN", "ACCOUNTS", "MANAGER", "EMPLOYEE", "VIEWER")
# Company-wide transaction ledgers, dashboards and reports (expenses,
# invoices, payments, financial reports) are for Admin/Super Admin/Accounts/
# Viewer only. Employees only see their own claims; Managers only see their
# team's approvals and their own claims - neither needs or should see
# company-wide financial data.
require_non_employee = require_roles("SUPER_ADMIN", "ADMIN", "ACCOUNTS", "VIEWER")
