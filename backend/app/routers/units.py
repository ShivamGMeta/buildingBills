"""Units (flats). Unit configuration — share %, EV flag, opening reading —
affects the whole building's math, so it is Superuser-only. Admins may view
their assigned units; tenants may view their own unit."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import (check_unit_access, get_current_user, require_staff,
                    require_superuser, scoped_unit_ids)
from ..models import Unit, UnitChargeDefault, User
from ..schemas import (ChargeDefaultIn, ChargeDefaultOut, ChargeDefaultUpdate,
                       UnitCreate, UnitOut, UnitUpdate)

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


# ---- Floor-wise fixed-charge defaults ---------------------------------------
# Every floor has its own rent/water/maintenance amounts. Superuser writes
# (unit config affects building math — row 11); staff read within scope.

def _get_unit_scoped(unit_id: int, db: Session, user: User) -> Unit:
    unit = db.get(Unit, unit_id)
    if unit is None:
        raise HTTPException(404, "Not found")
    check_unit_access(user, unit_id, db)
    return unit


@router.get("/{unit_id}/charge-defaults", response_model=list[ChargeDefaultOut])
def list_charge_defaults(unit_id: int, db: Session = Depends(get_db),
                         user: User = Depends(require_staff)):
    _get_unit_scoped(unit_id, db, user)
    return (db.query(UnitChargeDefault)
            .filter(UnitChargeDefault.unit_id == unit_id)
            .order_by(UnitChargeDefault.sort_order, UnitChargeDefault.id).all())


@router.post("/{unit_id}/charge-defaults", response_model=ChargeDefaultOut,
             status_code=201)
def create_charge_default(unit_id: int, body: ChargeDefaultIn,
                          db: Session = Depends(get_db),
                          user: User = Depends(require_superuser)):
    _get_unit_scoped(unit_id, db, user)
    row = UnitChargeDefault(unit_id=unit_id, **body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{unit_id}/charge-defaults/{cd_id}", response_model=ChargeDefaultOut)
def update_charge_default(unit_id: int, cd_id: int, body: ChargeDefaultUpdate,
                          db: Session = Depends(get_db),
                          user: User = Depends(require_superuser)):
    row = db.get(UnitChargeDefault, cd_id)
    if row is None or row.unit_id != unit_id:
        raise HTTPException(404, "Not found")
    for f, v in body.model_dump(exclude_unset=True).items():
        setattr(row, f, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{unit_id}/charge-defaults/{cd_id}", status_code=204)
def delete_charge_default(unit_id: int, cd_id: int, db: Session = Depends(get_db),
                          user: User = Depends(require_superuser)):
    row = db.get(UnitChargeDefault, cd_id)
    if row is None or row.unit_id != unit_id:
        raise HTTPException(404, "Not found")
    db.delete(row)
    db.commit()
