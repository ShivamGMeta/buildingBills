"""Staff billing flows: periods, readings, charge templates, bill lifecycle,
and the dashboard summary. All scoped: superuser sees everything, admins see
only their assigned floors (404 outside scope)."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import check_unit_access, require_staff, require_superuser, scoped_unit_ids
from ..models import (Bill, BillingPeriod, BillStatus, ChargeLine,
                      ChargeTemplate, MeterReading, Role, Unit, User)
from ..schemas import (BillDetailOut, BillOut, ChargeLineIn, DashboardOut,
                       GenerateBillsRequest, PeriodCreate, PeriodOut,
                       PeriodUpdate, ReadingCreate, ReadingOut, TemplateIn,
                       TemplateOut)
from ..services import bill_service
from ..services.pdf import render_bill_pdf
from ..services.storage import get_storage
from datetime import datetime

router = APIRouter(prefix="/api", tags=["billing"])


# ---- Billing periods --------------------------------------------------------

@router.get("/periods", response_model=list[PeriodOut])
def list_periods(db: Session = Depends(get_db), _: User = Depends(require_staff)):
    return (db.query(BillingPeriod)
            .order_by(BillingPeriod.year.desc(), BillingPeriod.month.desc()).all())


@router.post("/periods", response_model=PeriodOut, status_code=201)
def create_period(body: PeriodCreate, db: Session = Depends(get_db),
                  _: User = Depends(require_staff)):
    """Admins may open a month, but the rate carries over from the latest
    period — only the Superuser can change it (row 12)."""
    if db.query(BillingPeriod).filter_by(year=body.year, month=body.month).first():
        raise HTTPException(409, "Period already exists")
    latest = (db.query(BillingPeriod)
              .order_by(BillingPeriod.year.desc(), BillingPeriod.month.desc()).first())
    period = BillingPeriod(year=body.year, month=body.month,
                           rate_paise=latest.rate_paise if latest else 900)
    db.add(period)
    db.commit()
    db.refresh(period)
    return period


@router.patch("/periods/{period_id}", response_model=PeriodOut)
def update_period(period_id: int, body: PeriodUpdate, db: Session = Depends(get_db),
                  _: User = Depends(require_superuser)):
    """Rate and building-wide common-area/EV units: Superuser only."""
    period = db.get(BillingPeriod, period_id)
    if period is None:
        raise HTTPException(404, "Not found")
    for f, v in body.model_dump(exclude_unset=True).items():
        setattr(period, f, v)
    db.commit()
    # Drafts recompute live; published bills stay frozen.
    for bill in db.query(Bill).filter(Bill.period_id == period.id,
                                      Bill.status == BillStatus.draft).all():
        bill_service.recompute_draft(db, bill)
    db.refresh(period)
    return period


# ---- Meter readings ---------------------------------------------------------

@router.get("/readings", response_model=list[ReadingOut])
def list_readings(period_id: int, db: Session = Depends(get_db),
                  user: User = Depends(require_staff)):
    q = db.query(MeterReading).filter(MeterReading.period_id == period_id)
    allowed = scoped_unit_ids(user, db)
    if allowed is not None:
        q = q.filter(MeterReading.unit_id.in_(allowed))
    return q.all()


@router.post("/readings", response_model=ReadingOut, status_code=201)
def upsert_reading(body: ReadingCreate, db: Session = Depends(get_db),
                   user: User = Depends(require_staff)):
    check_unit_access(user, body.unit_id, db)
    if db.get(Unit, body.unit_id) is None or db.get(BillingPeriod, body.period_id) is None:
        raise HTTPException(404, "Not found")
    reading = (db.query(MeterReading)
               .filter_by(unit_id=body.unit_id, period_id=body.period_id).first())
    if reading is None:
        reading = MeterReading(unit_id=body.unit_id, period_id=body.period_id,
                               recorded_by_id=user.id)
        db.add(reading)
    reading.reading = body.reading
    reading.reading_date = body.reading_date
    reading.note = body.note
    db.commit()
    # Keep any draft bill for this unit/period in sync.
    bill = (db.query(Bill).filter_by(unit_id=body.unit_id, period_id=body.period_id)
            .first())
    if bill and bill.status == BillStatus.draft:
        bill_service.recompute_draft(db, bill)
    db.refresh(reading)
    return reading


# ---- Charge templates (Superuser manages; staff read) -----------------------

@router.get("/charge-templates", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_db), _: User = Depends(require_staff)):
    return db.query(ChargeTemplate).order_by(ChargeTemplate.id).all()


@router.post("/charge-templates", response_model=TemplateOut, status_code=201)
def create_template(body: TemplateIn, db: Session = Depends(get_db),
                    _: User = Depends(require_superuser)):
    t = ChargeTemplate(**body.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.patch("/charge-templates/{template_id}", response_model=TemplateOut)
def update_template(template_id: int, body: TemplateIn, db: Session = Depends(get_db),
                    _: User = Depends(require_superuser)):
    t = db.get(ChargeTemplate, template_id)
    if t is None:
        raise HTTPException(404, "Not found")
    for f, v in body.model_dump().items():
        setattr(t, f, v)
    db.commit()
    db.refresh(t)
    return t


# ---- Bills ------------------------------------------------------------------

def _get_scoped_bill(bill_id: int, db: Session, user: User) -> Bill:
    bill = db.get(Bill, bill_id)
    if bill is None:
        raise HTTPException(404, "Not found")
    check_unit_access(user, bill.unit_id, db)
    return bill


def _bill_detail(db: Session, bill: Bill) -> BillDetailOut:
    tenant = (db.query(User)
              .filter(User.unit_id == bill.unit_id, User.role == Role.tenant,
                      User.is_active).first())
    return BillDetailOut(
        **BillOut.model_validate(bill).model_dump(),
        unit_name=bill.unit.name,
        tenant_name=tenant.name if tenant else None,
        period_year=bill.period.year,
        period_month=bill.period.month,
    )


@router.post("/periods/{period_id}/generate-bills", response_model=list[BillOut])
def generate_bills(period_id: int, body: GenerateBillsRequest,
                   db: Session = Depends(get_db), user: User = Depends(require_staff)):
    period = db.get(BillingPeriod, period_id)
    if period is None:
        raise HTTPException(404, "Not found")
    return bill_service.generate_drafts(db, period, scoped_unit_ids(user, db),
                                        body.charge_lines or None)


@router.get("/bills", response_model=list[BillDetailOut])
def list_bills(period_id: int | None = None, db: Session = Depends(get_db),
               user: User = Depends(require_staff)):
    q = db.query(Bill)
    if period_id is not None:
        q = q.filter(Bill.period_id == period_id)
    allowed = scoped_unit_ids(user, db)
    if allowed is not None:
        q = q.filter(Bill.unit_id.in_(allowed))
    return [_bill_detail(db, b) for b in q.order_by(Bill.id).all()]


@router.get("/bills/{bill_id}", response_model=BillDetailOut)
def get_bill(bill_id: int, db: Session = Depends(get_db),
             user: User = Depends(require_staff)):
    return _bill_detail(db, _get_scoped_bill(bill_id, db, user))


@router.put("/bills/{bill_id}/charges", response_model=BillDetailOut)
def set_charges(bill_id: int, lines: list[ChargeLineIn],
                db: Session = Depends(get_db), user: User = Depends(require_staff)):
    bill = _get_scoped_bill(bill_id, db, user)
    if bill.status == BillStatus.published:
        raise HTTPException(409, "Published bills are frozen — unpublish first")
    bill.charge_lines = [ChargeLine(label=l.label, amount_paise=l.amount_paise)
                         for l in lines]
    db.commit()
    bill_service.recompute_draft(db, bill)
    return _bill_detail(db, bill)


@router.post("/bills/{bill_id}/publish", response_model=BillDetailOut)
def publish(bill_id: int, db: Session = Depends(get_db),
            user: User = Depends(require_staff)):
    bill = _get_scoped_bill(bill_id, db, user)
    bill, _notified = bill_service.publish_bill(db, bill)
    return _bill_detail(db, bill)


@router.post("/bills/{bill_id}/unpublish", response_model=BillDetailOut)
def unpublish(bill_id: int, db: Session = Depends(get_db),
              user: User = Depends(require_staff)):
    bill = _get_scoped_bill(bill_id, db, user)
    return _bill_detail(db, bill_service.unpublish_bill(db, bill))


@router.post("/bills/{bill_id}/mark-paid", response_model=BillDetailOut)
def mark_paid(bill_id: int, db: Session = Depends(get_db),
              user: User = Depends(require_staff)):
    bill = _get_scoped_bill(bill_id, db, user)
    bill.is_paid = not bill.is_paid
    bill.paid_at = datetime.utcnow() if bill.is_paid else None
    db.commit()
    return _bill_detail(db, bill)


@router.get("/bills/{bill_id}/pdf")
def bill_pdf(bill_id: int, db: Session = Depends(get_db),
             user: User = Depends(require_staff)):
    bill = _get_scoped_bill(bill_id, db, user)
    data = get_storage().load(bill.pdf_path) if bill.pdf_path else None
    if data is None:
        tenant = (db.query(User)
                  .filter(User.unit_id == bill.unit_id, User.role == Role.tenant,
                          User.is_active).first())
        data = render_bill_pdf(bill, bill.unit, bill.period,
                               tenant.name if tenant else None)
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="bill-{bill_id}.pdf"'})


# ---- Dashboard --------------------------------------------------------------

@router.get("/dashboard", response_model=DashboardOut)
def dashboard(period_id: int | None = None, db: Session = Depends(get_db),
              user: User = Depends(require_staff)):
    period = (db.get(BillingPeriod, period_id) if period_id else
              db.query(BillingPeriod)
              .order_by(BillingPeriod.year.desc(), BillingPeriod.month.desc()).first())
    if period is None:
        return DashboardOut(period=None, total_units_consumed=0,
                            total_electricity_paise=0, total_other_charges_paise=0,
                            total_billed_paise=0, total_collected_paise=0,
                            bills_count=0, bills_paid=0)
    q = db.query(Bill).filter(Bill.period_id == period.id)
    allowed = scoped_unit_ids(user, db)
    if allowed is not None:
        q = q.filter(Bill.unit_id.in_(allowed))
    bills = q.all()
    return DashboardOut(
        period=period,
        total_units_consumed=sum(b.own_units for b in bills),
        total_electricity_paise=sum(b.electricity_paise for b in bills),
        total_other_charges_paise=sum(b.total_paise - b.electricity_paise for b in bills),
        total_billed_paise=sum(b.total_paise for b in bills),
        total_collected_paise=sum(b.total_paise for b in bills if b.is_paid),
        bills_count=len(bills),
        bills_paid=sum(1 for b in bills if b.is_paid),
    )
