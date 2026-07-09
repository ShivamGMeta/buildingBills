"""Tenant-facing API. Read-only: own profile and own PUBLISHED bills.
Someone else's bill, or a draft, returns 404 — existence is never leaked."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_tenant
from ..models import (Bill, BillingPeriod, BillStatus, MeterReading,
                      ReadingPhoto, Role, User)
from ..schemas import (BillDetailOut, ReadingOut, ReadingPhotoOut,
                       TenantReadingOut, UnitOut, UserOut)
from ..services.bill_service import previous_reading_for
from ..services.pdf import render_bill_pdf
from ..services.storage import get_storage

router = APIRouter(prefix="/api/tenant", tags=["tenant"])


@router.get("/me", response_model=UserOut)
def my_profile(user: User = Depends(require_tenant)):
    return user


@router.get("/unit", response_model=UnitOut)
def my_unit(user: User = Depends(require_tenant), db: Session = Depends(get_db)):
    if user.unit is None:
        raise HTTPException(404, "Not found")
    return user.unit


def _detail(bill: Bill, user: User) -> BillDetailOut:
    from ..schemas import BillOut
    return BillDetailOut(
        **BillOut.model_validate(bill).model_dump(),
        unit_name=bill.unit.name,
        tenant_name=user.name,
        period_year=bill.period.year,
        period_month=bill.period.month,
    )


def _own_published_bill(bill_id: int, user: User, db: Session) -> Bill:
    bill = db.get(Bill, bill_id)
    if (bill is None or bill.unit_id != user.unit_id
            or bill.status != BillStatus.published):
        raise HTTPException(404, "Not found")
    return bill


@router.get("/bills", response_model=list[BillDetailOut])
def my_bills(user: User = Depends(require_tenant), db: Session = Depends(get_db)):
    bills = (db.query(Bill)
             .filter(Bill.unit_id == user.unit_id,
                     Bill.status == BillStatus.published)
             .order_by(Bill.id.desc()).all())
    return [_detail(b, user) for b in bills]


@router.get("/bills/{bill_id}", response_model=BillDetailOut)
def my_bill(bill_id: int, user: User = Depends(require_tenant),
            db: Session = Depends(get_db)):
    return _detail(_own_published_bill(bill_id, user, db), user)


# ---- Meter readings (read-only, own unit) -----------------------------------
# Decision (docs/02-gap-analysis.md §5): tenants see readings + photos for
# ALL months of their own unit, not only published-bill months — maximum
# transparency is the point of the feature. Other units' readings = 404.

@router.get("/readings", response_model=list[TenantReadingOut])
def my_readings(user: User = Depends(require_tenant),
                db: Session = Depends(get_db)):
    if user.unit_id is None:
        return []
    readings = (
        db.query(MeterReading)
        .join(BillingPeriod, MeterReading.period_id == BillingPeriod.id)
        .filter(MeterReading.unit_id == user.unit_id)
        .order_by((BillingPeriod.year * 100 + BillingPeriod.month).desc())
        .all()
    )
    out = []
    for r in readings:
        try:
            prev = previous_reading_for(db, r.unit, r.period)
        except Exception:
            prev = None
        consumed = r.reading - prev if prev is not None and r.reading >= prev else None
        out.append(TenantReadingOut(
            **ReadingOut.model_validate(r).model_dump(),
            period_year=r.period.year,
            period_month=r.period.month,
            units_consumed=consumed,
        ))
    return out


def _own_reading(reading_id: int, user: User, db: Session) -> MeterReading:
    reading = db.get(MeterReading, reading_id)
    if reading is None or reading.unit_id != user.unit_id:
        raise HTTPException(404, "Not found")
    return reading


@router.get("/readings/{reading_id}/photos", response_model=list[ReadingPhotoOut])
def my_reading_photos(reading_id: int, user: User = Depends(require_tenant),
                      db: Session = Depends(get_db)):
    return _own_reading(reading_id, user, db).photos


@router.get("/readings/{reading_id}/photos/{photo_id}")
def my_reading_photo(reading_id: int, photo_id: int,
                     user: User = Depends(require_tenant),
                     db: Session = Depends(get_db)):
    reading = _own_reading(reading_id, user, db)
    photo = db.get(ReadingPhoto, photo_id)
    if photo is None or photo.reading_id != reading.id:
        raise HTTPException(404, "Not found")
    data = get_storage().load(photo.storage_key)
    if data is None:
        raise HTTPException(404, "Not found")
    return Response(content=data, media_type=photo.content_type)


@router.get("/bills/{bill_id}/pdf")
def my_bill_pdf(bill_id: int, user: User = Depends(require_tenant),
                db: Session = Depends(get_db)):
    bill = _own_published_bill(bill_id, user, db)
    data = get_storage().load(bill.pdf_path) if bill.pdf_path else None
    if data is None:
        data = render_bill_pdf(bill, bill.unit, bill.period, user.name)
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="bill-{bill_id}.pdf"'})
