"""Tests for the gap-analysis features: one tenant per floor (Gap 1),
floor-wise fixed charges (Gap 2), meter-reading photos (Gap 3)."""
import io

from .conftest import login

JPEG = ("photo.jpg", io.BytesIO(b"\xff\xd8\xff\xe0fake-jpeg-bytes"), "image/jpeg")


# ---- Gap 1: one active tenant per floor -------------------------------------

def test_second_active_tenant_on_floor_rejected(client, seed):
    su = login(client, "owner@example.com")
    res = client.post("/api/tenants", json={
        "email": "second@example.com", "name": "Second",
        "password": "secret-pass-123", "unit_id": seed["units"]["u4"]},
        headers=su)
    assert res.status_code == 409
    assert "active tenant" in res.json()["detail"]


def test_moving_tenant_onto_occupied_floor_rejected(client, seed):
    su = login(client, "owner@example.com")
    tenants = client.get("/api/tenants", headers=su).json()
    amit = next(t for t in tenants if t["name"] == "Amit")
    res = client.patch(f"/api/tenants/{amit['id']}",
                       json={"unit_id": seed["units"]["u4"]}, headers=su)
    assert res.status_code == 409


def test_deactivate_then_new_tenant_allowed(client, seed):
    su = login(client, "owner@example.com")
    tenants = client.get("/api/tenants", headers=su).json()
    mohit = next(t for t in tenants if t["name"] == "Mohit")
    assert client.patch(f"/api/tenants/{mohit['id']}",
                        json={"is_active": False}, headers=su).status_code == 200
    res = client.post("/api/tenants", json={
        "email": "newtenant@example.com", "name": "New Tenant",
        "password": "secret-pass-123", "unit_id": seed["units"]["u4"]},
        headers=su)
    assert res.status_code == 201
    # reactivating the old tenant on the now-occupied floor -> 409
    res = client.patch(f"/api/tenants/{mohit['id']}",
                       json={"is_active": True}, headers=su)
    assert res.status_code == 409


def test_demote_admin_onto_occupied_floor_rejected(client, seed):
    su = login(client, "owner@example.com")
    admins_email = "admin12@example.com"
    admin = [u for u in client.get("/api/admins", headers=su).json()
             if u["email"] == admins_email][0]
    res = client.post(f"/api/users/{admin['id']}/role",
                      json={"role": "tenant", "unit_id": seed["units"]["u4"]},
                      headers=su)
    assert res.status_code == 409


# ---- Gap 2: floor-wise fixed charges -----------------------------------------

def test_drafts_seed_from_per_floor_defaults(client, seed):
    su = login(client, "owner@example.com")
    bills = client.post(f"/api/periods/{seed['periods']['may']}/generate-bills",
                        json={}, headers=su).json()
    by_unit = {b["unit_id"]: b for b in bills}
    rent_of = lambda b: next(l["amount_paise"] for l in b["charge_lines"]
                             if l["label"] == "Rent")
    assert rent_of(by_unit[seed["units"]["u4"]]) == 41_600_00
    assert rent_of(by_unit[seed["units"]["u3"]]) == 38_500_00  # differs per floor
    # anchor still exact
    assert by_unit[seed["units"]["u4"]]["total_paise"] == 5_018_500


def test_charge_defaults_permissions_and_scope(client, seed):
    u2, u4 = seed["units"]["u2"], seed["units"]["u4"]
    admin = login(client, "admin12@example.com")
    # admin reads defaults on own floor, 404 outside scope
    assert client.get(f"/api/units/{u2}/charge-defaults",
                      headers=admin).status_code == 200
    assert client.get(f"/api/units/{u4}/charge-defaults",
                      headers=admin).status_code == 404
    # writes are superuser-only -> 403 for admins even in scope
    res = client.post(f"/api/units/{u2}/charge-defaults",
                      json={"label": "Extra", "default_amount_paise": 100},
                      headers=admin)
    assert res.status_code == 403

    su = login(client, "owner@example.com")
    created = client.post(f"/api/units/{u2}/charge-defaults",
                          json={"label": "Extra", "default_amount_paise": 100},
                          headers=su)
    assert created.status_code == 201
    cd_id = created.json()["id"]
    assert client.patch(f"/api/units/{u2}/charge-defaults/{cd_id}",
                        json={"default_amount_paise": 200},
                        headers=su).json()["default_amount_paise"] == 200
    assert client.delete(f"/api/units/{u2}/charge-defaults/{cd_id}",
                         headers=su).status_code == 204
    # wrong unit/id pairing -> 404
    assert client.delete(f"/api/units/{u4}/charge-defaults/{cd_id}",
                         headers=su).status_code == 404


def test_apply_template_to_floors(client, seed):
    su = login(client, "owner@example.com")
    templates = client.get("/api/charge-templates", headers=su).json()
    water = next(t for t in templates if t["label"] == "Water Charges")
    res = client.post(f"/api/charge-templates/{water['id']}/apply-to-floors",
                      headers=su)
    assert res.status_code == 200
    assert res.json()["applied_to_floors"] == 4
    # per-floor rows exist (updated in place, not duplicated)
    rows = client.get(f"/api/units/{seed['units']['u1']}/charge-defaults",
                      headers=su).json()
    assert sum(1 for r in rows if r["label"] == "Water Charges") == 1


# ---- Gap 3: meter-reading photos ---------------------------------------------

def _may_reading_id(client, headers, seed, unit_key):
    readings = client.get(f"/api/readings?period_id={seed['periods']['may']}",
                          headers=headers).json()
    return next(r["id"] for r in readings if r["unit_id"] == seed["units"][unit_key])


def test_photo_upload_view_delete_lifecycle(client, seed):
    su = login(client, "owner@example.com")
    rid = _may_reading_id(client, su, seed, "u4")

    up = client.post(f"/api/readings/{rid}/photos",
                     files={"photo": JPEG}, headers=su)
    assert up.status_code == 201, up.text
    pid = up.json()["id"]
    assert up.json()["content_type"] == "image/jpeg"

    listed = client.get(f"/api/readings/{rid}/photos", headers=su).json()
    assert [p["id"] for p in listed] == [pid]
    got = client.get(f"/api/readings/{rid}/photos/{pid}", headers=su)
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("image/jpeg")
    assert got.content.startswith(b"\xff\xd8")

    assert client.delete(f"/api/readings/{rid}/photos/{pid}",
                         headers=su).status_code == 204
    assert client.get(f"/api/readings/{rid}/photos/{pid}",
                      headers=su).status_code == 404


def test_photo_validation(client, seed):
    su = login(client, "owner@example.com")
    rid = _may_reading_id(client, su, seed, "u4")
    bad_type = client.post(f"/api/readings/{rid}/photos",
                           files={"photo": ("x.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
                           headers=su)
    assert bad_type.status_code == 415
    huge = client.post(f"/api/readings/{rid}/photos",
                       files={"photo": ("big.jpg", io.BytesIO(b"x" * (10 * 1024 * 1024 + 1)),
                                        "image/jpeg")},
                       headers=su)
    assert huge.status_code == 413


def test_admin_cannot_upload_outside_scope(client, seed):
    su = login(client, "owner@example.com")
    rid_u4 = _may_reading_id(client, su, seed, "u4")
    admin = login(client, "admin12@example.com")  # scoped to u1+u2
    res = client.post(f"/api/readings/{rid_u4}/photos",
                      files={"photo": JPEG}, headers=admin)
    assert res.status_code == 404  # not 403 — no existence leak


def test_tenant_sees_only_own_unit_photos(client, seed):
    su = login(client, "owner@example.com")
    rid_u4 = _may_reading_id(client, su, seed, "u4")
    rid_u3 = _may_reading_id(client, su, seed, "u3")
    up = client.post(f"/api/readings/{rid_u4}/photos",
                     files={"photo": JPEG}, headers=su)
    pid = up.json()["id"]

    mohit = login(client, "mohit@example.com")  # tenant on u4
    readings = client.get("/api/tenant/readings", headers=mohit).json()
    # all months of their own unit, even though no bill is published
    assert {r["period_month"] for r in readings} == {4, 5}
    may = next(r for r in readings if r["period_month"] == 5)
    assert may["units_consumed"] == 664
    assert [p["id"] for p in may["photos"]] == [pid]

    got = client.get(f"/api/tenant/readings/{rid_u4}/photos/{pid}", headers=mohit)
    assert got.status_code == 200
    # a neighbour's reading/photos -> 404
    assert client.get(f"/api/tenant/readings/{rid_u3}/photos",
                      headers=mohit).status_code == 404
    assert client.get(f"/api/tenant/readings/{rid_u3}/photos/{pid}",
                      headers=mohit).status_code == 404
