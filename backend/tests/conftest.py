import os
import sys
from datetime import date

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["NOTIFIER"] = "console"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (AdminScope, BillingPeriod, ChargeTemplate,
                        MeterReading, Role, Unit, User)
from app.security import hash_password

engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                       poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


PASSWORD = "secret-pass-123"


@pytest.fixture()
def seed(db):
    """4 floors (35/30/20/15), EV on 3rd, superuser, one admin scoped to
    floors 1-2, tenants on floors 3-4, April+May 2025 with readings."""
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
    admin12 = User(email="admin12@example.com", name="Admin Lower Floors",
                   password_hash=pw, role=Role.admin)
    mohit = User(email="mohit@example.com", name="Mohit",
                 password_hash=pw, role=Role.tenant, unit_id=u4.id)
    amit = User(email="amit@example.com", name="Amit",
                password_hash=pw, role=Role.tenant, unit_id=u3.id)
    db.add_all([superuser, admin12, mohit, amit])
    db.flush()
    db.add_all([AdminScope(admin_id=admin12.id, unit_id=u1.id),
                AdminScope(admin_id=admin12.id, unit_id=u2.id)])

    apr = BillingPeriod(year=2025, month=4, rate_paise=900,
                        common_area_units=0, ev_units=0)
    may = BillingPeriod(year=2025, month=5, rate_paise=900,
                        common_area_units=214, ev_units=120)
    db.add_all([apr, may])
    db.flush()

    # April readings = May's "previous"
    for unit, r in [(u4, 5040), (u3, 3923), (u2, 3350), (u1, 2608)]:
        db.add(MeterReading(unit_id=unit.id, period_id=apr.id, reading=r,
                            reading_date=date(2025, 5, 1)))
    # May readings (from the meter screen mock)
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
    return {"units": {"u1": u1.id, "u2": u2.id, "u3": u3.id, "u4": u4.id},
            "periods": {"apr": apr.id, "may": may.id}}


def login(client, email):
    res = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}
