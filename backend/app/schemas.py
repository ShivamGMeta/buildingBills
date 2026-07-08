from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import BillStatus, Role


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role
    name: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    name: str
    role: Role
    unit_id: int | None
    phone: str | None
    is_active: bool


class TenantOut(UserOut):
    pass


class AdminOut(UserOut):
    unit_ids: list[int] = []


class AdminCreate(BaseModel):
    email: EmailStr
    name: str
    password: str = Field(min_length=8)
    phone: str | None = None
    unit_ids: list[int] = []


class AdminUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    unit_ids: list[int] | None = None


class RoleChange(BaseModel):
    role: Role
    # Required when promoting/demoting to tenant
    unit_id: int | None = None


class TenantCreate(BaseModel):
    email: EmailStr
    name: str
    password: str = Field(min_length=8)
    phone: str | None = None
    unit_id: int


class TenantUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    unit_id: int | None = None


class UnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    meter_no: str
    common_share_bps: int
    has_ev: bool
    opening_reading: int
    sort_order: int
    is_active: bool


class UnitCreate(BaseModel):
    name: str
    meter_no: str = ""
    common_share_bps: int = 0
    has_ev: bool = False
    opening_reading: int = 0
    sort_order: int = 0


class UnitUpdate(BaseModel):
    name: str | None = None
    meter_no: str | None = None
    common_share_bps: int | None = None
    has_ev: bool | None = None
    opening_reading: int | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class ChargeDefaultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    unit_id: int
    label: str
    default_amount_paise: int
    is_active: bool
    sort_order: int


class ChargeDefaultIn(BaseModel):
    label: str
    default_amount_paise: int = Field(ge=0)
    is_active: bool = True
    sort_order: int = 0


class ChargeDefaultUpdate(BaseModel):
    label: str | None = None
    default_amount_paise: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    sort_order: int | None = None


class PeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    year: int
    month: int
    rate_paise: int
    common_area_units: int
    ev_units: int


class PeriodCreate(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class PeriodUpdate(BaseModel):
    rate_paise: int | None = Field(default=None, ge=0)
    common_area_units: int | None = Field(default=None, ge=0)
    ev_units: int | None = Field(default=None, ge=0)


class ReadingPhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    reading_id: int
    content_type: str
    byte_size: int
    uploaded_at: datetime


class ReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    unit_id: int
    period_id: int
    reading: int
    reading_date: date
    note: str
    photos: list[ReadingPhotoOut] = []


class TenantReadingOut(ReadingOut):
    """Tenant read surface: own unit's readings with period info and the
    consumption already computed server-side."""
    period_year: int
    period_month: int
    units_consumed: int | None


class ReadingCreate(BaseModel):
    unit_id: int
    period_id: int
    reading: int = Field(ge=0)
    reading_date: date
    note: str = ""


class ChargeLineIn(BaseModel):
    label: str
    amount_paise: int = Field(ge=0)


class ChargeLineOut(ChargeLineIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class BillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    unit_id: int
    period_id: int
    status: BillStatus
    prev_reading: int
    curr_reading: int
    own_units: int
    common_share_units: int
    ev_units: int
    billable_units: int
    rate_paise: int
    electricity_paise: int
    total_paise: int
    is_paid: bool
    published_at: datetime | None
    charge_lines: list[ChargeLineOut] = []


class BillDetailOut(BillOut):
    unit_name: str
    tenant_name: str | None
    period_year: int
    period_month: int


class GenerateBillsRequest(BaseModel):
    charge_lines: list[ChargeLineIn] = []


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    label: str
    default_amount_paise: int
    is_active: bool


class TemplateIn(BaseModel):
    label: str
    default_amount_paise: int = Field(ge=0)
    is_active: bool = True


class DashboardOut(BaseModel):
    period: PeriodOut | None
    total_units_consumed: int
    total_electricity_paise: int
    total_other_charges_paise: int
    total_billed_paise: int
    total_collected_paise: int
    bills_count: int
    bills_paid: int
