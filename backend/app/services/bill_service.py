"""Orchestration around the pure billing engine: previous-reading lookup,
common-share allocation, draft generation/recompute, publish freeze."""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import (Bill, BillingPeriod, BillStatus, ChargeLine,
                      ChargeTemplate, MeterReading, Role, Unit, User)
from . import billing
from .notifier import notify_bill_published_safe
from .pdf import period_label, render_bill_pdf, rupees
from .storage import get_storage


def previous_reading_for(db: Session, unit: Unit, period: BillingPeriod) -> int | None:
    """Latest reading strictly before this period, else the unit's opening
    reading if this is the first billed period. Never assumed zero."""
    prev = (
        db.query(MeterReading)
        .join(BillingPeriod, MeterReading.period_id == BillingPeriod.id)
        .filter(
            MeterReading.unit_id == unit.id,
            (BillingPeriod.year * 100 + BillingPeriod.month)
            < (period.year * 100 + period.month),
        )
        .order_by((BillingPeriod.year * 100 + BillingPeriod.month).desc())
        .first()
    )
    if prev is not None:
        return prev.reading
    earlier = (
        db.query(MeterReading)
        .join(BillingPeriod, MeterReading.period_id == BillingPeriod.id)
        .filter(MeterReading.unit_id == unit.id)
        .count()
    )
    # Opening reading (captured at onboarding) backs the first billed month.
    return unit.opening_reading if earlier <= 1 else None


def common_allocation(db: Session, period: BillingPeriod) -> dict[int, int]:
    units = db.query(Unit).filter(Unit.is_active, Unit.common_share_bps > 0).all()
    return billing.allocate_common_units(
        period.common_area_units, {u.id: u.common_share_bps for u in units}
    )


def compute_for_unit(db: Session, unit: Unit, period: BillingPeriod) -> billing.BillCalc:
    reading = (
        db.query(MeterReading)
        .filter(MeterReading.unit_id == unit.id, MeterReading.period_id == period.id)
        .first()
    )
    if reading is None:
        raise HTTPException(422, f"No meter reading for {unit.name} in this period")
    prev = previous_reading_for(db, unit, period)
    share = common_allocation(db, period).get(unit.id, 0)
    ev = period.ev_units if unit.has_ev else 0
    try:
        return billing.compute_bill(
            prev_reading=prev,
            curr_reading=reading.reading,
            common_share_units=share,
            ev_units=ev,
            rate_paise=period.rate_paise,
        )
    except billing.BillingError as e:
        raise HTTPException(422, f"{unit.name}: {e}") from e


def default_charge_lines(db: Session) -> list[ChargeLine]:
    templates = db.query(ChargeTemplate).filter(ChargeTemplate.is_active).all()
    return [ChargeLine(label=t.label, amount_paise=t.default_amount_paise)
            for t in templates]


def generate_drafts(db: Session, period: BillingPeriod, unit_ids: set[int] | None,
                    extra_lines: list | None = None) -> list[Bill]:
    """Create/refresh draft bills for billable units. Published bills are
    frozen snapshots and are never touched."""
    q = db.query(Unit).filter(Unit.is_active, Unit.common_share_bps > 0)
    if unit_ids is not None:
        q = q.filter(Unit.id.in_(unit_ids))
    bills = []
    for unit in q.order_by(Unit.sort_order).all():
        existing = (
            db.query(Bill)
            .filter(Bill.unit_id == unit.id, Bill.period_id == period.id)
            .first()
        )
        if existing and existing.status == BillStatus.published:
            bills.append(existing)
            continue
        calc = compute_for_unit(db, unit, period)
        if existing is None:
            if extra_lines:
                lines = [ChargeLine(label=l.label, amount_paise=l.amount_paise)
                         for l in extra_lines]
            else:
                lines = default_charge_lines(db)
            existing = Bill(unit_id=unit.id, period_id=period.id,
                            charge_lines=lines)
            _apply_calc(existing, calc)
            db.add(existing)
        else:
            _apply_calc(existing, calc)
        bills.append(existing)
    db.commit()
    return bills


def _apply_calc(bill: Bill, calc: billing.BillCalc) -> None:
    bill.prev_reading = calc.prev_reading
    bill.curr_reading = calc.curr_reading
    bill.own_units = calc.own_units
    bill.common_share_units = calc.common_share_units
    bill.ev_units = calc.ev_units
    bill.billable_units = calc.billable_units
    bill.rate_paise = calc.rate_paise
    bill.electricity_paise = calc.electricity_paise
    charges = sum(l.amount_paise for l in bill.charge_lines)
    bill.total_paise = calc.electricity_paise + charges


def recompute_draft(db: Session, bill: Bill) -> Bill:
    """Drafts recompute live as inputs change; published bills never do."""
    if bill.status == BillStatus.published:
        return bill
    calc = compute_for_unit(db, bill.unit, bill.period)
    _apply_calc(bill, calc)
    db.commit()
    return bill


def publish_bill(db: Session, bill: Bill) -> tuple[Bill, bool]:
    """Freeze the snapshot, store the PDF, then notify (failure tolerated)."""
    if bill.status == BillStatus.published:
        raise HTTPException(409, "Bill is already published")
    recompute_draft(db, bill)
    bill.status = BillStatus.published
    bill.published_at = datetime.utcnow()

    tenant = _tenant_of(db, bill.unit_id)
    pdf_bytes = render_bill_pdf(bill, bill.unit, bill.period,
                                tenant.name if tenant else None)
    bill.pdf_path = get_storage().save(f"bills/bill-{bill.id}.pdf", pdf_bytes)
    db.commit()

    notified = False
    if tenant:
        notified = notify_bill_published_safe(
            to_email=tenant.email,
            tenant_name=tenant.name,
            unit_name=bill.unit.name,
            period_label=period_label(bill.period.year, bill.period.month),
            total_rupees=rupees(bill.total_paise),
        )
    return bill, notified


def unpublish_bill(db: Session, bill: Bill) -> Bill:
    if bill.status != BillStatus.published:
        raise HTTPException(409, "Bill is not published")
    bill.status = BillStatus.draft
    bill.published_at = None
    db.commit()
    return bill


def _tenant_of(db: Session, unit_id: int) -> User | None:
    return (
        db.query(User)
        .filter(User.unit_id == unit_id, User.role == Role.tenant, User.is_active)
        .first()
    )
