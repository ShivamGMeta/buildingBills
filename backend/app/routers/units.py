"""Units (flats). Unit configuration — share %, EV flag, opening reading —
affects the whole building's math, so it is Superuser-only. Admins may view
their assigned units; tenants may view their own unit."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_superuser, scoped_unit_ids
from ..models import Unit, User
from ..schemas import UnitCreate, UnitOut, UnitUpdate

router = APIRouter(prefix="/api/units", tags=["units"])


@router.get("", response_model=list[UnitOut])
def list_units(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Unit)
    allowed = scoped_unit_ids(user, db)
    if allowed is not None:
        q = q.filter(Unit.id.in_(allowed))
    return q.order_by(Unit.sort_order).all()


@router.post("", response_model=UnitOut, status_code=201)
def create_unit(body: UnitCreate, db: Session = Depends(get_db),
                _: User = Depends(require_superuser)):
    unit = Unit(**body.model_dump())
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return unit


@router.patch("/{unit_id}", response_model=UnitOut)
def update_unit(unit_id: int, body: UnitUpdate, db: Session = Depends(get_db),
                _: User = Depends(require_superuser)):
    unit = db.get(Unit, unit_id)
    if unit is None:
        raise HTTPException(404, "Not found")
    for f, v in body.model_dump(exclude_unset=True).items():
        setattr(unit, f, v)
    db.commit()
    db.refresh(unit)
    return unit
