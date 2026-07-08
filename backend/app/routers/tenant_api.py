"""Tenant-facing API. Read-only: own profile and own PUBLISHED bills.
Someone else's bill, or a draft, returns 404 — existence is never leaked."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_tenant
from ..models import Bill, BillStatus, Role, User
from ..schemas import BillDetailOut, UnitOut, UserOut
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


@router.get("/bills/{bill_id}/pdf")
def my_bill_pdf(bill_id: int, user: User = Depends(require_tenant),
                db: Session = Depends(get_db)):
    bill = _own_published_bill(bill_id, user, db)
    data = get_storage().load(bill.pdf_path) if bill.pdf_path else None
    if data is None:
        data = render_bill_pdf(bill, bill.unit, bill.period, user.name)
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="bill-{bill_id}.pdf"'})
