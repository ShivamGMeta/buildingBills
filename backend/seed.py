"""Seed the dev database with the real building: 4 floors (35/30/20/15),
EV on the 3rd floor, April+May 2025 readings from the meter screen, and the
default charge templates. Idempotent — safe to re-run.

    python seed.py

Default logins (password: changeme123):
  superuser  owner@example.com
  admin      admin@example.com   (scoped to 1st + 2nd floor)
  tenants    mohit@ / amit@ / neha@ / karan@ example.com
"""
from datetime import date

from app.database import Base, SessionLocal, engine
from app.models import (AdminScope, BillingPeriod, ChargeTemplate,
                        MeterReading, Role, Unit, User)
from app.security import hash_password
from app.services import bill_service

PASSWORD = "changeme123"


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    if db.query(User).count():
        print("Database already seeded — nothing to do.")
        return

    units = [
        Unit(name="4th Floor", meter_no="MTR-001", common_share_bps=3500,
             opening_reading=4376, sort_order=1),
        Unit(name="3rd Floor", meter_no="MTR-002", common_share_bps=3000,
             has_ev=True, opening_reading=3923, sort_order=2),
        Unit(name="2nd Floor", meter_no="MTR-003", common_share_bps=2000,
             opening_reading=3350, sort_order=3),
        Unit(name="1st Floor", meter_no="MTR-004", common_share_bps=1500,
             opening_reading=2608, sort_order=4),
    ]
    db.add_all(units)
    db.flush()
    u4, u3, u2, u1 = units

    pw = hash_password(PASSWORD)
    superuser = User(email="owner@example.com", name="Building Owner",
                     password_hash=pw, role=Role.superuser)
    admin = User(email="admin@example.com", name="Floor Admin",
                 password_hash=pw, role=Role.admin)
    db.add_all([superuser, admin])
    db.flush()
    db.add_all([AdminScope(admin_id=admin.id, unit_id=u1.id),
                AdminScope(admin_id=admin.id, unit_id=u2.id)])

    for email, name, unit in [("mohit@example.com", "Mohit", u4),
                              ("amit@example.com", "Amit", u3),
                              ("neha@example.com", "Neha", u2),
                              ("karan@example.com", "Karan", u1)]:
        db.add(User(email=email, name=name, password_hash=pw,
                    role=Role.tenant, unit_id=unit.id))

    apr = BillingPeriod(year=2025, month=4, rate_paise=900)
    may = BillingPeriod(year=2025, month=5, rate_paise=900,
                        common_area_units=214, ev_units=120)
    db.add_all([apr, may])
    db.flush()

    for unit, r in [(u4, 5040), (u3, 3923), (u2, 3350), (u1, 2608)]:
        db.add(MeterReading(unit_id=unit.id, period_id=apr.id, reading=r,
                            reading_date=date(2025, 5, 1)))
    for unit, r in [(u4, 5704), (u3, 4521), (u2, 3890), (u1, 3120)]:
        db.add(MeterReading(unit_id=unit.id, period_id=may.id, reading=r,
                            reading_date=date(2025, 5, 31)))

    db.add_all([
        ChargeTemplate(label="Rent", default_amount_paise=41_600_00),
        ChargeTemplate(label="Water Charges", default_amount_paise=1_200_00),
        ChargeTemplate(label="Society Maintenance", default_amount_paise=636_00),
        ChargeTemplate(label="DG Backup", default_amount_paise=98_00),
    ])
    db.commit()

    bills = bill_service.generate_drafts(db, may, None)
    print(f"Seeded 4 units, 6 users, 2 periods, {len(bills)} draft May bills.")
    for b in bills:
        print(f"  {b.unit.name}: ₹{b.total_paise / 100:,.2f} "
              f"({b.billable_units} units)")
    db.close()


if __name__ == "__main__":
    main()
