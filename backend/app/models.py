import enum
from datetime import datetime, date

from sqlalchemy import (
    Boolean, Date, DateTime, Enum, ForeignKey, Integer, String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Role(str, enum.Enum):
    superuser = "superuser"
    admin = "admin"
    tenant = "tenant"


class BillStatus(str, enum.Enum):
    draft = "draft"
    published = "published"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.tenant)
    # Tenants occupy exactly one unit; null for admins/superuser.
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    unit: Mapped["Unit | None"] = relationship(back_populates="tenants")
    admin_scopes: Mapped[list["AdminScope"]] = relationship(
        back_populates="admin", cascade="all, delete-orphan"
    )


class AdminScope(Base):
    """Links an admin to a unit (floor) they may manage."""
    __tablename__ = "admin_scopes"
    __table_args__ = (UniqueConstraint("admin_id", "unit_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"))

    admin: Mapped[User] = relationship(back_populates="admin_scopes")
    unit: Mapped["Unit"] = relationship()


class Unit(Base):
    """The flat/floor — the durable billing object."""
    __tablename__ = "units"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    meter_no: Mapped[str] = mapped_column(String(40), default="")
    # Share of common-area units in basis points (35% -> 3500). Data, not code.
    common_share_bps: Mapped[int] = mapped_column(Integer, default=0)
    has_ev: Mapped[bool] = mapped_column(Boolean, default=False)
    opening_reading: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    tenants: Mapped[list[User]] = relationship(back_populates="unit")


class BillingPeriod(Base):
    """One billed month. Carries the rate so old bills keep theirs."""
    __tablename__ = "billing_periods"
    __table_args__ = (UniqueConstraint("year", "month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    rate_paise: Mapped[int] = mapped_column(Integer)  # paise per kWh
    common_area_units: Mapped[int] = mapped_column(Integer, default=0)
    ev_units: Mapped[int] = mapped_column(Integer, default=0)


class MeterReading(Base):
    __tablename__ = "meter_readings"
    __table_args__ = (UniqueConstraint("unit_id", "period_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"))
    period_id: Mapped[int] = mapped_column(ForeignKey("billing_periods.id"))
    reading: Mapped[int] = mapped_column(Integer)  # kWh, cumulative
    reading_date: Mapped[date] = mapped_column(Date)
    note: Mapped[str] = mapped_column(String(500), default="")
    recorded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    unit: Mapped[Unit] = relationship()
    period: Mapped[BillingPeriod] = relationship()


class Bill(Base):
    """A bill for one unit in one period. Published bills are frozen snapshots."""
    __tablename__ = "bills"
    __table_args__ = (UniqueConstraint("unit_id", "period_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"))
    period_id: Mapped[int] = mapped_column(ForeignKey("billing_periods.id"))
    status: Mapped[BillStatus] = mapped_column(Enum(BillStatus), default=BillStatus.draft)

    # Snapshot fields — frozen on publish, recomputed while draft.
    prev_reading: Mapped[int] = mapped_column(Integer)
    curr_reading: Mapped[int] = mapped_column(Integer)
    own_units: Mapped[int] = mapped_column(Integer)
    common_share_units: Mapped[int] = mapped_column(Integer)
    ev_units: Mapped[int] = mapped_column(Integer, default=0)
    billable_units: Mapped[int] = mapped_column(Integer)
    rate_paise: Mapped[int] = mapped_column(Integer)
    electricity_paise: Mapped[int] = mapped_column(Integer)
    total_paise: Mapped[int] = mapped_column(Integer)

    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    unit: Mapped[Unit] = relationship()
    period: Mapped[BillingPeriod] = relationship()
    charge_lines: Mapped[list["ChargeLine"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan"
    )


class ChargeLine(Base):
    """Arbitrary label + amount attached to a bill (rent, water, DG, ...)."""
    __tablename__ = "charge_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id"))
    label: Mapped[str] = mapped_column(String(200))
    amount_paise: Mapped[int] = mapped_column(Integer)

    bill: Mapped[Bill] = relationship(back_populates="charge_lines")


class ChargeTemplate(Base):
    """Reusable charge label + default amount, seeds draft bills."""
    __tablename__ = "charge_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(200))
    default_amount_paise: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
