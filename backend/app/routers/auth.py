from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin, require_super_admin
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.enums import AuditAction, RoleName
from app.models.models import User, Role
from app.schemas.auth import (
    Token, UserOut, UserCreate, UserUpdate, RoleCreate, RoleUpdate, RoleOut,
    PasswordResetRequest, SetActiveRequest,
)
from app.services import audit_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _to_user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id, username=user.username, email=user.email, full_name=user.full_name,
        role=user.role.name, employee_id=user.employee_id, is_active=user.is_active,
    )


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User account is disabled")
    token = create_access_token(subject=str(user.id), extra_claims={"role": user.role.name})
    audit_service.record(db, "USER", user.id, AuditAction.LOGIN, user.id)
    db.commit()
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _to_user_out(user)


@router.post("/users", response_model=UserOut, dependencies=[Depends(require_admin)])
def create_user(payload: UserCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username already exists")
    role = db.query(Role).filter(Role.id == payload.role_id).first()
    if not role:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role_id")
    # Only a Super Admin may grant the Admin or Super Admin role - otherwise
    # an ordinary Admin (who can also call this endpoint) could self-escalate
    # by creating another Admin or a Super Admin account.
    if role.name in (RoleName.ADMIN, RoleName.SUPER_ADMIN) and actor.role.name != RoleName.SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a Super Admin can grant the Admin or Super Admin role")
    user = User(
        username=payload.username, email=payload.email, full_name=payload.full_name,
        hashed_password=hash_password(payload.password), role_id=payload.role_id,
        employee_id=payload.employee_id,
    )
    db.add(user)
    db.flush()
    audit_service.record(db, "USER", user.id, AuditAction.CREATE, actor.id, {"role": role.name})
    db.commit()
    db.refresh(user)
    return _to_user_out(user)


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require_admin)])
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.username).all()
    return [_to_user_out(u) for u in users]


@router.post("/users/{user_id}/set-active", response_model=UserOut, dependencies=[Depends(require_admin)])
def set_user_active(user_id: int, payload: SetActiveRequest, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    # Only a Super Admin may enable/disable Admin or Super Admin accounts -
    # an ordinary Admin can manage everyone below that.
    if user.role.name in (RoleName.ADMIN, RoleName.SUPER_ADMIN) and actor.role.name != RoleName.SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a Super Admin can change this user's status")
    if user.id == actor.id and not payload.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot disable your own account")
    user.is_active = payload.is_active
    db.add(user)
    audit_service.record(db, "USER", user.id, AuditAction.UPDATE, actor.id, {"is_active": payload.is_active})
    db.commit()
    db.refresh(user)
    return _to_user_out(user)


@router.put("/users/{user_id}", response_model=UserOut, dependencies=[Depends(require_admin)])
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    # Only a Super Admin may edit Admin or Super Admin accounts - mirrors the
    # same guard used by set-active/reset-password.
    if user.role.name in (RoleName.ADMIN, RoleName.SUPER_ADMIN) and actor.role.name != RoleName.SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a Super Admin can edit this user")
    changes = payload.model_dump(exclude_unset=True)
    if "username" in changes and changes["username"] != user.username:
        if db.query(User).filter(User.username == changes["username"], User.id != user_id).first():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username already exists")
    if "email" in changes and changes["email"] and changes["email"] != user.email:
        if db.query(User).filter(User.email == changes["email"], User.id != user_id).first():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already exists")
    if "role_id" in changes and changes["role_id"] != user.role_id:
        new_role = db.query(Role).filter(Role.id == changes["role_id"]).first()
        if not new_role:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role_id")
        # This endpoint only supports toggling EMPLOYEE <-> MANAGER (e.g.
        # promoting an employee to a manager, or demoting one back) - not a
        # general role reassignment. Escalating to/from Admin/Accounts/etc
        # still requires disabling the account and creating a new one, same
        # as before this feature.
        switchable = (RoleName.EMPLOYEE, RoleName.MANAGER)
        if user.role.name not in switchable or new_role.name not in switchable:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only switching a user between Employee and Manager is supported here")
        if new_role.name == RoleName.MANAGER and not user.employee_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A Manager must be linked to an Employee record first")
    for field, value in changes.items():
        setattr(user, field, value)
    db.add(user)
    audit_service.record(db, "USER", user.id, AuditAction.UPDATE, actor.id, changes)
    db.commit()
    db.refresh(user)
    return _to_user_out(user)


@router.post("/users/{user_id}/reset-password", dependencies=[Depends(require_super_admin)])
def reset_password(user_id: int, payload: PasswordResetRequest, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.hashed_password = hash_password(payload.new_password)
    db.add(user)
    # Never write the new password itself into the audit trail.
    audit_service.record(db, "USER", user.id, AuditAction.UPDATE, actor.id, {"action": "password_reset"})
    db.commit()
    return {"detail": f"Password reset for {user.username}"}


@router.get("/roles", response_model=list[RoleOut], dependencies=[Depends(require_admin)])
def list_roles(db: Session = Depends(get_db)):
    return db.query(Role).order_by(Role.name).all()


@router.post("/roles", response_model=RoleOut, dependencies=[Depends(require_super_admin)])
def create_role(payload: RoleCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if db.query(Role).filter(Role.name == payload.name.upper()).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A role with this name already exists")
    role = Role(name=payload.name.upper(), description=payload.description)
    db.add(role)
    db.flush()
    audit_service.record(db, "ROLE", role.id, AuditAction.CREATE, actor.id, {"name": role.name})
    db.commit()
    db.refresh(role)
    return role


@router.put("/roles/{role_id}", response_model=RoleOut, dependencies=[Depends(require_super_admin)])
def update_role(role_id: int, payload: RoleUpdate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Role not found")
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        new_name = changes["name"].upper()
        if db.query(Role).filter(Role.name == new_name, Role.id != role_id).first():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A role with this name already exists")
        changes["name"] = new_name
    for field, value in changes.items():
        setattr(role, field, value)
    db.add(role)
    audit_service.record(db, "ROLE", role.id, AuditAction.UPDATE, actor.id, changes)
    db.commit()
    db.refresh(role)
    return role
