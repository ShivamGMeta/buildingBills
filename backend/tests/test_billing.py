"""Exhaustive tests for the pure billing engine, anchored on the worked
example: Mohit, 4th floor, May -> TOTAL ₹50,185 (5_018_500 paise)."""
import pytest

from app.services.billing import (BillingError, ChargeInput, InvalidReading,
                                  MissingPreviousReading,
                                  allocate_common_units, compute_bill)

RATE = 900  # ₹9.00/unit in paise


def test_regression_anchor_mohit_may_50185():
    calc = compute_bill(
        prev_reading=5040,
        curr_reading=5704,
        common_share_units=75,
        ev_units=0,
        rate_paise=RATE,
        charges=[
            ChargeInput("Rent", 41_600_00),
            ChargeInput("Water Charges", 1_200_00),
            ChargeInput("DG Backup (April)", 98_00),
            ChargeInput("Society Maintenance (May)", 636_00),
        ],
    )
    assert calc.own_units == 664
    assert calc.billable_units == 739
    assert calc.electricity_paise == 665_100      # ₹6,651
    assert calc.total_paise == 5_018_500          # ₹50,185 — THE anchor
    assert isinstance(calc.total_paise, int)


def test_missing_previous_reading_is_error_never_zero():
    with pytest.raises(MissingPreviousReading):
        compute_bill(None, 5704, 0, 0, RATE)


def test_meter_cannot_run_backwards():
    with pytest.raises(InvalidReading):
        compute_bill(5704, 5040, 0, 0, RATE)


def test_zero_consumption_is_valid():
    calc = compute_bill(5040, 5040, 0, 0, RATE)
    assert calc.own_units == 0
    assert calc.total_paise == 0


def test_ev_units_billed_to_owner():
    calc = compute_bill(1000, 1100, 20, 120, RATE)
    assert calc.billable_units == 100 + 20 + 120
    assert calc.electricity_paise == 240 * RATE


def test_charges_only_no_negative_rate():
    with pytest.raises(BillingError):
        compute_bill(0, 10, 0, 0, -1)
    with pytest.raises(BillingError):
        compute_bill(0, 10, -1, 0, RATE)


def test_allocation_exact_split():
    # 35/30/20/15 over 200 units splits exactly: 70/60/40/30.
    shares = {1: 3500, 2: 3000, 3: 2000, 4: 1500}
    alloc = allocate_common_units(200, shares)
    assert alloc == {1: 70, 2: 60, 3: 40, 4: 30}


def test_allocation_sums_exactly_with_rounding():
    shares = {1: 3500, 2: 3000, 3: 2000, 4: 1500}
    for total in (75, 101, 214, 999, 1):
        alloc = allocate_common_units(total, shares)
        assert sum(alloc.values()) == total
        assert all(v >= 0 for v in alloc.values())


def test_allocation_zero_and_empty():
    assert allocate_common_units(0, {1: 3500, 2: 6500}) == {1: 0, 2: 0}
    assert allocate_common_units(100, {}) == {}
    assert allocate_common_units(100, {1: 0, 2: 0}) == {1: 0, 2: 0}


def test_allocation_negative_total_rejected():
    with pytest.raises(BillingError):
        allocate_common_units(-1, {1: 10000})


def test_money_is_integer_paise_no_floats():
    calc = compute_bill(0, 3, 0, 0, 333, [ChargeInput("x", 1)])
    assert calc.electricity_paise == 999
    assert calc.total_paise == 1000
    assert isinstance(calc.electricity_paise, int)
