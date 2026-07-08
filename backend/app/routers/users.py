"""Admin & tenant management.

- Admins (add/remove/edit, floor assignment, promote/demote): Superuser ONLY.
- Tenants: Superuser anywhere; Admins on their assigned floors only.
- There can be only one Superuser — enforced here.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import check_unit_access, require_staff, require_superuser, scoped_unit_ids
from ..models import AdminScope, Role, Unit, User
from ..schemas import (AdminCreate, AdminOut, AdminUpdate, RoleChange,
                       TenantCreate, TenantOut, TenantUpdate)
from ..security import hash_password

router = APIRouter(prefix="/api", tags=["users"])


def _admin_out(user: User) -> AdminOut:
    out = AdminOut.model_validate(user)
    out.unit_ids = [s.unit_id for s in user.admin_scopes]
    return out


def _set_scopes(db: Session, admin: User, unit_ids: list[int]) -> None:
    units = db.query(Unit).filter(Unit.id.in_(unit_ids)).all() if unit_ids else []
    if len(units) != len(set(unit_ids)):
        raise HTTPException(422, "Unknown unit id in floor assignment")
    admin.admin_scopes = [AdminScope(unit_id=u.id) for u in units]


# ---- Admins: superuser only ------------------------------------------------

@router.get("/admins", response_model=list[AdminOut])
def list_admins(db: Session = Depends(get_db), _: User = Depends(require_superuser)):
    admins = db.query(User).filter(User.role == Role.admin).order_by(User.name).all()
    return [_admin_out(a) for a in admins]


@router.post("/admins", response_model=AdminOut, status_code=201)
def create_admin(body: AdminCreate, db: Session = Depends(get_db),
                 _: User = Depends(require_superuser)):
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(409, "Email already registered")
    admin = User(email=body.email.lower(), name=body.name, phone=body.phone,
                 password_hash=hash_password(body.password), role=Role.admin)
    _set_scopes(db, admin, body.unit_ids)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return _admin_out(admin)


@router.patch("/admins/{admin_id}", response_model=AdminOut)
def update_admin(admin_id: int, body: AdminUpdate, db: Session = Depends(get_db),
                 _: User = Depends(require_superuser)):
    admin = db.get(User, admin_id)
    if admin is None or admin.role != Role.admin:
        raise HTTPException(404, "Not found")
    for f in ("name", "phone", "is_active"):
        v = getattr(body, f)
        if v is not None:
            setattr(admin, f, v)
    if body.unit_ids is not None:
        _set_scopes(db, admin, body.unit_ids)
    db.commit()
    db.refresh(admin)
    return _admin_out(admin)


@router.post("/users/{user_id}/role", response_model=AdminOut)
def change_role(user_id: int, body: RoleChange, db: Session = Depends(get_db),
                _: User = Depends(require_superuser)):
    """Promote/demote between admin and tenant. Superuser is unique and
    cannot be created or removed here."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Not found")
    if user.role == Role.superuser or body.role == Role.superuser:
        raise HTTPException(409, "There can be only one Superuser")
    if body.role == Role.tenant:
        if body.unit_id is None:
            raise HTTPException(422, "unit_id required when demoting to tenant")
        user.unit_id = body.unit_id
        user.admin_scopes = []
    else:  # -> admin
        user.unit_id = None
    user.role = body.role
    db.commit()
    db.refresh(user)
    return _admin_out(user)


# ---- Tenants: superuser anywhere, admins on their floors -------------------

@router.get("/tenants", response_model=list[TenantOut])
def list_tenants(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    q = db.query(User).filter(User.role == Role.tenant)
    allowed = scoped_unit_ids(user, db)
    if allowed is not None:
        q = q.filter(User.unit_id.in_(allowed))
    return q.order_by(User.name).all()


@router.post("/tenants", response_model=TenantOut, status_code=201)
def create_tenant(body: TenantCreate, db: Session = Depends(get_db),
                  user: User = Depends(require_staff)):
    check_unit_access(user, body.unit_id, db)
    if db.get(Unit, body.unit_id) is None:
        raise HTTPException(404, "Not found")
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(409, "Email already registered")
    tenant = User(email=body.email.lower(), name=body.name, phone=body.phone,
                  password_hash=hash_password(body.password),
                  role=Role.tenant, unit_id=body.unit_id)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


@router.patch("/tenants/{tenant_id}", response_model=TenantOut)
def update_tenant(tenant_id: int, body: TenantUpdate, db: Session = Depends(get_db),
                  user: User = Depends(require_staff)):
    tenant = db.get(User, tenant_id)
    if tenant is None or tenant.role != Role.tenant:
        raise HTTPException(404, "Not found")
    check_unit_access(user, tenant.unit_id, db)
    if body.unit_id is not None:
        check_unit_access(user, body.unit_id, db)
        tenant.unit_id = body.unit_id
    for f in ("name", "phone", "is_active"):
        v = getattr(body, f)
        if v is not None:
            setattr(tenant, f, v)
    db.commit()
    db.refresh(tenant)
    return tenant
