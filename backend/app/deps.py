"""Auth + scoping dependencies.

Scope rules:
- Superuser bypasses all scoping.
- Admin: every read/write filtered to their assigned units; anything outside
  returns 404 (not 403) so existence isn't leaked.
- Tenant: only their own published bills; others/drafts return 404.
Role-gated actions on endpoints a user can see return 403.
"""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import AdminScope, Role, User
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(401, "Not authenticated")
    payload = decode_token(creds.credentials)
    if payload is None:
        raise HTTPException(401, "Invalid or expired token")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(401, "User not found or inactive")
    return user


def require_superuser(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.superuser:
        raise HTTPException(403, "Superuser access required")
    return user


def require_staff(user: User = Depends(get_current_user)) -> User:
    """Superuser or admin."""
    if user.role not in (Role.superuser, Role.admin):
        raise HTTPException(403, "Admin access required")
    return user


def require_tenant(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.tenant:
        raise HTTPException(403, "Tenant access required")
    return user


def scoped_unit_ids(user: User, db: Session) -> set[int] | None:
    """Unit ids the user may touch. None means unrestricted (superuser)."""
    if user.role == Role.superuser:
        return None
    if user.role == Role.admin:
        rows = db.query(AdminScope.unit_id).filter(AdminScope.admin_id == user.id).all()
        return {r[0] for r in rows}
    return {user.unit_id} if user.unit_id else set()


def check_unit_access(user: User, unit_id: int, db: Session) -> None:
    """404 (not 403) when a unit is outside the user's scope."""
    allowed = scoped_unit_ids(user, db)
    if allowed is not None and unit_id not in allowed:
        raise HTTPException(404, "Not found")
