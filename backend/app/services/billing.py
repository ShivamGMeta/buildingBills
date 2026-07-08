"""Pure bill-calculation functions. No DB, no HTTP — exhaustively unit-tested.

All money values are integer paise (₹6,651 -> 665100). All unit values are
integer kWh. The worked example that anchors everything (Mohit, 4th floor, May):

    own 664 + common share 75 = 739 units x ₹9 = ₹6,651
    + rent 41,600 + water 1,200 + DG(Apr) 98 + maintenance(May) 636
    = ₹50,185  (5_018_500 paise)
"""
from dataclasses import dataclass, field


class BillingError(Exception):
    pass


class MissingPreviousReading(BillingError):
    """Previous reading absent at bill time — a genuine error, never zeroed."""


class InvalidReading(BillingError):
    """Current reading below previous (meter can't run backwards)."""


@dataclass(frozen=True)
class ChargeInput:
    label: str
    amount_paise: int


@dataclass(frozen=True)
class BillCalc:
    prev_reading: int
    curr_reading: int
    own_units: int
    common_share_units: int
    ev_units: int
    billable_units: int
    rate_paise: int
    electricity_paise: int
    charges: tuple[ChargeInput, ...] = field(default_factory=tuple)
    charges_paise: int = 0
    total_paise: int = 0


def allocate_common_units(total_units: int, shares_bps: dict[int, int]) -> dict[int, int]:
    """Split common-area units across units by their share (basis points),
    using the largest-remainder method so allocations are integers that sum
    exactly to total_units. Shares are data on the flat, never hardcoded.
    """
    if total_units < 0:
        raise BillingError("Common-area units cannot be negative")
    total_bps = sum(shares_bps.values())
    if total_bps <= 0:
        return {uid: 0 for uid in shares_bps}

    exact = {uid: total_units * bps / total_bps for uid, bps in shares_bps.items()}
    floored = {uid: int(v) for uid, v in exact.items()}
    remainder = total_units - sum(floored.values())
    # Hand out leftover units to the largest fractional remainders,
    # breaking ties by larger share then by unit id for determinism.
    order = sorted(
        shares_bps,
        key=lambda uid: (exact[uid] - floored[uid], shares_bps[uid], -uid),
        reverse=True,
    )
    for uid in order[:remainder]:
        floored[uid] += 1
    return floored


def compute_bill(
    prev_reading: int | None,
    curr_reading: int,
    common_share_units: int,
    ev_units: int,
    rate_paise: int,
    charges: list[ChargeInput] | tuple[ChargeInput, ...] = (),
) -> BillCalc:
    """The core calculation, per flat, per month:

        own_units   = curr - prev
        electricity = (own_units + common_share + ev_units) x rate
        total       = electricity + sum(fixed charge lines)
    """
    if prev_reading is None:
        raise MissingPreviousReading(
            "No previous reading for this unit — enter the opening/previous "
            "reading before billing. It is never assumed to be zero."
        )
    if curr_reading < prev_reading:
        raise InvalidReading(
            f"Current reading {curr_reading} is below previous {prev_reading}"
        )
    if rate_paise < 0:
        raise BillingError("Rate cannot be negative")
    if common_share_units < 0 or ev_units < 0:
        raise BillingError("Unit counts cannot be negative")

    own_units = curr_reading - prev_reading
    billable_units = own_units + common_share_units + ev_units
    electricity_paise = billable_units * rate_paise
    charges = tuple(charges)
    charges_paise = sum(c.amount_paise for c in charges)
    return BillCalc(
        prev_reading=prev_reading,
        curr_reading=curr_reading,
        own_units=own_units,
        common_share_units=common_share_units,
        ev_units=ev_units,
        billable_units=billable_units,
        rate_paise=rate_paise,
        electricity_paise=electricity_paise,
        charges=charges,
        charges_paise=charges_paise,
        total_paise=electricity_paise + charges_paise,
    )
