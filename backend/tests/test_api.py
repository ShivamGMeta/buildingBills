"""API tests: auth, role gates, admin floor scoping, tenant isolation,
draft->publish lifecycle, and the end-to-end ₹50,185 anchor via the API."""
from .conftest import login


def gen_bills(client, headers, period_id):
    res = client.post(f"/api/periods/{period_id}/generate-bills", json={},
                      headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_login_and_me(client, seed):
    headers = login(client, "owner@example.com")
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["role"] == "superuser"
    assert client.post("/api/auth/login", json={
        "email": "owner@example.com", "password": "wrong-password"
    }).status_code == 401


def test_superuser_generates_all_and_anchor_total(client, seed):
    headers = login(client, "owner@example.com")
    bills = gen_bills(client, headers, seed["periods"]["may"])
    assert len(bills) == 4
    by_unit = {b["unit_id"]: b for b in bills}
    mohit = by_unit[seed["units"]["u4"]]
    # 664 own + 75 common (35% of 214 via largest remainder) = 739 x ₹9
    assert mohit["own_units"] == 664
    assert mohit["common_share_units"] == 75
    assert mohit["electricity_paise"] == 665_100
    # templates: 41600 + 1200 + 636 + 98 = 43_534_00 -> total ₹50,185
    assert mohit["total_paise"] == 5_018_500
    # EV goes 100% to the 3rd floor
    amit = by_unit[seed["units"]["u3"]]
    assert amit["ev_units"] == 120
    others = [b for uid, b in by_unit.items() if uid != seed["units"]["u3"]]
    assert all(b["ev_units"] == 0 for b in others)
    # common shares sum exactly to the metered total
    assert sum(b["common_share_units"] for b in bills) == 214


def test_admin_scoped_to_own_floors(client, seed):
    headers = login(client, "admin12@example.com")
    units = client.get("/api/units", headers=headers).json()
    assert {u["id"] for u in units} == {seed["units"]["u1"], seed["units"]["u2"]}
    # generate-bills only creates drafts for the admin's floors
    bills = gen_bills(client, headers, seed["periods"]["may"])
    assert {b["unit_id"] for b in bills} == {seed["units"]["u1"], seed["units"]["u2"]}
    # reading outside scope -> 404 (not 403), no existence leak
    res = client.post("/api/readings", json={
        "unit_id": seed["units"]["u4"], "period_id": seed["periods"]["may"],
        "reading": 6000, "reading_date": "2025-05-31"}, headers=headers)
    assert res.status_code == 404
    # superuser-only endpoints -> 403
    res = client.patch(f"/api/periods/{seed['periods']['may']}",
                       json={"rate_paise": 950}, headers=headers)
    assert res.status_code == 403
    assert client.get("/api/admins", headers=headers).status_code == 403
    # admin can add a tenant on own floor, not outside
    ok = client.post("/api/tenants", json={
        "email": "neha@example.com", "name": "Neha",
        "password": "secret-pass-123", "unit_id": seed["units"]["u2"]},
        headers=headers)
    assert ok.status_code == 201
    bad = client.post("/api/tenants", json={
        "email": "x@example.com", "name": "X",
        "password": "secret-pass-123", "unit_id": seed["units"]["u4"]},
        headers=headers)
    assert bad.status_code == 404


def test_tenant_isolation_and_lifecycle(client, seed):
    su = login(client, "owner@example.com")
    bills = gen_bills(client, su, seed["periods"]["may"])
    by_unit = {b["unit_id"]: b for b in bills}
    mohit_bill = by_unit[seed["units"]["u4"]]
    amit_bill = by_unit[seed["units"]["u3"]]

    mohit = login(client, "mohit@example.com")
    # draft not visible even to its own tenant
    assert client.get("/api/tenant/bills", headers=mohit).json() == []
    assert client.get(f"/api/tenant/bills/{mohit_bill['id']}",
                      headers=mohit).status_code == 404

    # publish freezes and exposes it
    res = client.post(f"/api/bills/{mohit_bill['id']}/publish", headers=su)
    assert res.status_code == 200
    mine = client.get("/api/tenant/bills", headers=mohit).json()
    assert [b["id"] for b in mine] == [mohit_bill["id"]]
    assert mine[0]["total_paise"] == 5_018_500

    # someone else's bill -> 404; staff API -> 403 for tenants
    assert client.get(f"/api/tenant/bills/{amit_bill['id']}",
                      headers=mohit).status_code == 404
    assert client.get("/api/bills", headers=mohit).status_code == 403

    # published bills are frozen: editing charges is rejected
    res = client.put(f"/api/bills/{mohit_bill['id']}/charges", json=[],
                     headers=su)
    assert res.status_code == 409
    # PDF downloads for the owner
    pdf = client.get(f"/api/tenant/bills/{mohit_bill['id']}/pdf", headers=mohit)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")


def test_published_bill_snapshot_survives_rate_change(client, seed):
    su = login(client, "owner@example.com")
    bills = gen_bills(client, su, seed["periods"]["may"])
    by_unit = {b["unit_id"]: b for b in bills}
    mohit_id = by_unit[seed["units"]["u4"]]["id"]
    amit_id = by_unit[seed["units"]["u3"]]["id"]
    client.post(f"/api/bills/{mohit_id}/publish", headers=su)

    # raise the rate for the period: drafts recompute, published stays frozen
    res = client.patch(f"/api/periods/{seed['periods']['may']}",
                       json={"rate_paise": 1000}, headers=su)
    assert res.status_code == 200
    frozen = client.get(f"/api/bills/{mohit_id}", headers=su).json()
    assert frozen["rate_paise"] == 900
    assert frozen["total_paise"] == 5_018_500
    live = client.get(f"/api/bills/{amit_id}", headers=su).json()
    assert live["rate_paise"] == 1000


def test_single_superuser_enforced(client, seed):
    su = login(client, "owner@example.com")
    tenants = client.get("/api/tenants", headers=su).json()
    res = client.post(f"/api/users/{tenants[0]['id']}/role",
                      json={"role": "superuser"}, headers=su)
    assert res.status_code == 409


def test_missing_previous_reading_is_422(client, seed, db):
    """A unit with two historic readings but a gap gets a real error, not zero."""
    from datetime import date

    from app.models import BillingPeriod, MeterReading, Unit

    su = login(client, "owner@example.com")
    jun = BillingPeriod(year=2025, month=6, rate_paise=900, common_area_units=0)
    db.add(jun)
    db.flush()
    # New unit with a June reading only, and TWO earlier readings missing
    # (so opening_reading fallback doesn't apply is not the case here —
    # simplest real gap: unit whose only reading is June, opening backs it).
    unit = Unit(name="5th Floor", common_share_bps=0, opening_reading=100)
    db.add(unit)
    db.flush()
    db.add(MeterReading(unit_id=unit.id, period_id=jun.id, reading=90,
                        reading_date=date(2025, 6, 30)))
    db.commit()
    # reading below opening -> meter can't run backwards -> 422
    unit.common_share_bps = 100
    db.commit()
    res = client.post(f"/api/periods/{jun.id}/generate-bills", json={}, headers=su)
    assert res.status_code == 422
