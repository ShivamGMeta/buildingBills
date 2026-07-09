# Building Bills — Gap Analysis & Build Spec

> **Purpose of this document.** It is a handoff brief for the agent (or developer)
> who will extend the existing Building Bills app. It captures (1) what already
> works, (2) three functional gaps the owner needs closed, and (3) the storage /
> hosting decisions that must be settled **before** the photo feature is built.
> Every section references the real files and models in this repo so the work can
> start immediately.
>
> Author: audit of the codebase as it stands (backend read in full: `models.py`,
> all `routers/*`, all `services/*`, `schemas.py`, `deps.py`, `config.py`, `seed.py`).

---

## 0. Ground rules the build MUST NOT break

These are locked decisions (see `CLAUDE.md` and `docs/00-project-overview.md §9`).
Preserve them through every change below.

- **Bill math stays pure.** All calculation lives in `backend/app/services/billing.py`
  as pure functions (no DB, no HTTP). Routes stay thin. Money is computed server-side only.
- **Money is integer paise, never floats.** Readings are integer kWh.
- **The regression anchor must still pass.** Mohit, 4th floor, May 2025 =
  664 own + 75 common = 739 × ₹9 = ₹6,651, plus rent ₹41,600 + water ₹1,200 +
  DG ₹98 + maintenance ₹636 = **₹50,185 (`5_018_500` paise)**. `backend/tests/test_billing.py`
  must reproduce this exactly, both as a pure function and end-to-end. Any change to
  how charges are seeded (Gap 2) must keep this green.
- **Common-area split & EV ownership are DATA on the Unit** (`common_share_bps`,
  `has_ev`), never hardcoded branching on a name. Allocation uses largest-remainder.
- **Rate lives on the billing period.** Raising it later never rewrites old bills.
- **Draft → Published.** Drafts recompute live; publish freezes the snapshot on the
  bill row. Editing a published bill = 409.
- **404, not 403, for out-of-scope reads** (no existence leak). Role-gated actions
  on a visible endpoint = 403.
- **Publish is decoupled from notifications** — a failed email never blocks publish.
- **PDFs (and now photos) go behind the `Storage` abstraction** (`services/storage.py`).

---

## 1. Current state (what already works — do not rebuild)

**Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2. SQLite in dev (`buildingbills.db`),
PostgreSQL-ready via `config.py`. Two Vite + vanilla-JS frontends (superuser :5173,
tenant/admin :5174). JWT auth, bcrypt passwords.

**Roles & permissions — all correct:**
- Superuser: full access, exactly one enforced (`routers/users.py::change_role`
  rejects any second superuser with 409).
- Admin: scoped to assigned floors via `admin_scopes`; can generate bills, enter
  readings, edit charges, add tenants on assigned floors only; cannot promote/demote
  (superuser-only → 403); out-of-scope = 404.
- Tenant: read-only own profile + own **published** bills + PDF; drafts/others = 404.

**Billing engine — solid:** previous-reading lookup (opening reading backs first
month; missing = 422), common-area largest-remainder split, EV billed 100% to owner,
draft/publish freeze, per-bill charge lines, PDF generation, tenant email on publish,
mark-as-paid, dashboard totals (billed vs collected).

**Data model today (`backend/app/models.py`):**
`User`, `AdminScope`, `Unit`, `BillingPeriod`, `MeterReading`, `Bill`, `ChargeLine`,
`ChargeTemplate`. All amounts are integer paise.

---

## 2. STORAGE & HOSTING DECISION (settle this first)

The owner asked: *"Can I use MongoDB, or my personal Google Drive (2 TB), to store
the data / bills / photos?"* Answer both explicitly; the photo feature (Gap 3) depends
on the outcome.

### 2.1 Database engine — recommendation: PostgreSQL, NOT MongoDB

The data is **relational**: bills reference readings reference periods; "one tenant per
floor" and "one reading per unit per month" are uniqueness rules; publish is a
transaction; the previous-reading lookup joins across periods. The whole app is built on
SQLAlchemy and its correctness leans on foreign keys, unique constraints, and joins.

- **Recommended:** keep the relational model, switch the dev SQLite file to **PostgreSQL**
  for anything multi-user / hosted. This is a **one-line change** (`config.py` →
  `database_url`, e.g. `postgresql+psycopg2://user:pass@host/db`); `psycopg2-binary` is
  already in `requirements.txt`, and `docker-compose` already provisions Postgres. No
  code rewrite. Add Alembic migrations (already a dependency) for schema changes instead
  of `create_all`.
- **MongoDB — possible but not recommended.** It would mean removing SQLAlchemy and
  remodelling every entity as documents, hand-rolling the uniqueness/consistency rules
  the DB currently guarantees, and rewriting `bill_service.py`'s cross-period queries.
  Large effort, and it *loses* guarantees the billing correctness depends on. Only revisit
  if there is a hard external reason (e.g. an existing Mongo ops stack the owner must use).
- **Google Drive is NOT a database.** It cannot store or query the structured records
  (users, bills, readings). Those must live in Postgres/SQLite regardless. Drive is only a
  candidate for the **file blobs** — see next.

### 2.2 File storage (PDFs + meter photos) — Google Drive is viable via the `Storage` layer

The app already abstracts blob storage behind `services/storage.py`
(`Storage` Protocol with `save()` / `load()`; `LocalStorage` writes under `./storage`).
PDFs already flow through it (`bill_service.publish_bill` → `get_storage().save(...)`).
Meter photos (Gap 3) will use the same interface. So swapping local disk for Google Drive
is an **additive backend**, not a rewrite.

**Implement a `GoogleDriveStorage(Storage)` class** with the same `save(rel_path, data)` /
`load(rel_path)` (add `delete(rel_path)` and a `content_type` arg — see §2.4). Select it
via a new `settings.storage_backend = "local" | "gdrive"` in `config.py`.

**CRITICAL quota caveat — read before promising the 2 TB works:**
- The 2 TB is on a **personal Google One** plan attached to the owner's Google account.
- A **service account** (the usual "server app" auth) has its **own separate 15 GB quota**
  and **cannot** consume the owner's 2 TB. Files it uploads count against the service
  account, not the owner. So a plain service account will hit 15 GB and stop.
- To actually use the 2 TB, the app must upload **as the owner's user account** via
  **OAuth 2.0 with a stored refresh token** (one-time consent, token refreshed
  automatically thereafter). Then uploaded files land in the owner's My Drive and count
  against the 2 TB. This is the recommended path for a personal Google One account.
  (A Google **Shared Drive** would also work but requires Google Workspace, which a
  personal account doesn't have.)
- **Serving files to tenants:** do **not** hand out raw Drive share links (that bypasses
  the app's permission model and leaks existence). Instead the app **downloads the bytes
  from Drive and streams them** through the existing scoped endpoints
  (`GET /bills/{id}/pdf`, and the new photo endpoints in Gap 3). The permission check stays
  in FastAPI; Drive is just the byte store.
- **Trade-offs to accept:** extra latency per file (API round-trip), Drive API rate limits/
  quotas, OAuth token lifecycle to maintain. For a single building's volume this is fine,
  but it is more moving parts than object storage.

**Honest recommendation for the owner:** the simplest robust setup is a small cloud host
(or NAS/VPS) running the API + Postgres, with photos/PDFs either on the server disk or an
S3-compatible object store. **Google Drive is a legitimate option specifically for the
blobs** if the owner prefers to keep everything in their Drive and accepts the OAuth setup
and latency. Either way, **only files go to Drive; records stay in the database.**

### 2.3 Hosting so phones can reach it (why this matters now)

Today everything is bound to `localhost` on one PC (`main.py` CORS allows only
`localhost:5173/5174`; Vite proxies `/api` to `localhost:8000`). Wing managers uploading
meter photos from their phones and tenants viewing them require the API to be reachable off
that machine. Before/with Gap 3:
- Deploy the API + Postgres to a reachable host over **HTTPS** (a small VPS or a managed
  platform; managed Postgres is fine).
- Update CORS `allow_origins` and the frontend `BASE`/proxy to the deployed origins.
- Put blobs on server disk, object storage, or Google Drive per §2.2.
- The two web apps are mobile-**friendly** (responsive), which covers "use it on a phone"
  for now; a **native app** is still deferred and would reuse the same API.

### 2.4 Extend the `Storage` Protocol (needed by Gap 3 regardless of backend)

```python
class Storage(Protocol):
    def save(self, rel_path: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...
    def load(self, rel_path: str) -> bytes | None: ...
    def delete(self, rel_path: str) -> None: ...
    def content_type_of(self, rel_path: str) -> str | None: ...   # optional; for streaming photos
```
`LocalStorage` keeps content-type in a sidecar or infers from extension. `GoogleDriveStorage`
maps `rel_path` → a folder path under a dedicated app root folder in Drive, remembering the
Drive `fileId` (store the mapping in a tiny table or derive by path lookup).

---

## 3. GAP 1 — Enforce ONE tenant per floor

**Owner's requirement:** "register a tenant against a floor — one tenant per floor."

**Current behaviour:** `Unit.tenants` is a one-to-**many** relationship; `User.unit_id`
has no uniqueness. Nothing stops two active tenants on the same floor. `bill_service._tenant_of`
and `billing_api._bill_detail` already assume one by calling `.first()` — so the assumption
exists but is unenforced.

**Definition to enforce:** *at most one **active** tenant (`role='tenant'`, `is_active=true`)
per unit.* Deactivated/past tenants may remain in history on that unit.

**Changes:**
1. **Application guard (primary).** In `routers/users.py`:
   - `create_tenant`: before insert, if an active tenant already exists on `body.unit_id`
     → `409 "This floor already has an active tenant"`.
   - `update_tenant`: when `body.unit_id` moves a tenant onto a unit that already has a
     different active tenant → same 409.
   - `change_role` (demote → tenant, which sets `unit_id`): same check.
   Factor the check into one helper, e.g. `_assert_floor_free(db, unit_id, exclude_user_id=None)`.
2. **DB constraint (hard guarantee).** Add a **partial unique index** so the rule holds even
   under races / direct writes:
   - Postgres: `CREATE UNIQUE INDEX uq_active_tenant_per_unit ON users (unit_id) WHERE role='tenant' AND is_active;`
   - SQLite (dev) supports partial indexes too. Express via Alembic migration (preferred) or
     an `Index(..., sqlite_where=..., postgresql_where=...)` on the model.
3. **Tests:** second active tenant on a floor → 409; moving a tenant onto an occupied floor
   → 409; deactivating the first then adding a second → allowed.

---

## 4. GAP 2 — Floor-wise fixed charges (per-floor rent / water / maintenance)

**Owner's requirement:** "the building setting for fixed charges should be floor-wise —
every floor has different rent and supply charges." A separate superuser screen sets these
values.

**Current behaviour:** `ChargeTemplate` is **building-wide** — one "Rent = ₹41,600" default
for *every* floor. `bill_service.default_charge_lines` seeds every draft from the same global
templates, so different rents must be re-typed on each floor's bill every month. There is no
persistent per-floor charge configuration.

**Design — per-unit charge defaults become the seeding source of truth:**

1. **New model `UnitChargeDefault`** (per floor, superuser-managed):
   ```
   id, unit_id (FK units), label (str), default_amount_paise (int, paise),
   is_active (bool), sort_order (int)
   ```
   One row per fixed charge per floor (e.g. 4th floor: Rent 41 60 000 paise, Water 1 20 000,
   Society Maintenance 63 600, DG Backup 9 800).
2. **Seeding change.** `bill_service.default_charge_lines(db, unit)` should read
   **that unit's** active `UnitChargeDefault` rows instead of the global `ChargeTemplate`s.
   Update `generate_drafts` to pass the unit. Amounts remain editable per bill afterwards
   (existing `PUT /bills/{id}/charges` unchanged) — the per-floor rows are just the defaults.
3. **Keep `ChargeTemplate`** only as an optional "apply this label to all floors" convenience
   for the superuser (bulk-create `UnitChargeDefault` rows), or deprecate it. Do **not** let
   it silently override per-floor values.
4. **Permissions.** Writing `UnitChargeDefault` is **Superuser-only** (consistent with row 11
   — unit config affects building math). Admins **read/consume** them. New endpoints:
   - `GET  /api/units/{unit_id}/charge-defaults`  (staff, scoped read)
   - `POST /api/units/{unit_id}/charge-defaults`  (superuser)
   - `PATCH /api/units/{unit_id}/charge-defaults/{id}` (superuser)
   - `DELETE /api/units/{unit_id}/charge-defaults/{id}` (superuser)
5. **Superuser UI:** a "Floor Charges" screen — pick a floor, edit its rent/water/maintenance/
   DG rows. (Separate from the readings screen, as the owner described.)
6. **Anchor preservation (must-do).** Update `seed.py` so the 4th-floor `UnitChargeDefault`
   rows are exactly Rent 41 60 000 + Water 1 20 000 + Society Maintenance 63 600 + DG Backup
   9 800 paise, so Mohit's May bill still totals ₹50,185. Update `test_billing.py` /
   `test_api.py` seeding accordingly; the anchor assertion itself does not change.

---

## 5. GAP 3 — Meter-reading PHOTO capture, storage & sharing

**Owner's requirement:** "the admin can upload a photo of the meter reading, which will be
stored in the app and accessible to the super user, admin, and the specific tenant." This is
the feature that removes the owner's monthly pain (today he manually compares meter photos and
forwards them to tenants who ask).

**Scope note:** This is photo **upload + storage + viewing**, NOT OCR. OCR ("auto-read the
meter") remains deferred to Phase 2 (`docs/00 §3`). Build only capture/store/share now, with
the number still typed in manually (with the photo as the evidence beside it).

**Current behaviour:** `MeterReading` stores only the number (`reading`, `note`, `reading_date`,
`recorded_by_id`). No image field, no upload endpoint, and **tenants cannot see readings at
all** — only finished bills. So this is a new read surface for tenants plus a new write surface
for staff.

**Design:**

1. **New model `ReadingPhoto`** (allow one or more photos per reading):
   ```
   id, reading_id (FK meter_readings, cascade delete),
   storage_key (str — the Storage rel_path), content_type (str),
   uploaded_by_id (FK users), uploaded_at (datetime), byte_size (int)
   ```
   (Alternatively a single `photo_key` column on `MeterReading` if one photo per reading is
   enough — but a child table is cleaner and future-proof. Prefer the child table.)
2. **Upload endpoint (staff, floor-scoped):**
   `POST /api/readings/{reading_id}/photos` — `multipart/form-data`, `UploadFile`
   (`python-multipart` already in `requirements.txt`).
   - Resolve the reading → its unit → `check_unit_access(user, unit_id, db)` (404 if
     out-of-scope).
   - Validate content-type in {`image/jpeg`, `image/png`, `image/webp`, `image/heic`} and
     size ≤ ~10 MB (return 415 / 413 otherwise).
   - Save bytes: `key = get_storage().save(f"readings/unit-{unit_id}/{yyyymm}/{uuid4()}.<ext>", data, content_type)`.
   - Insert `ReadingPhoto` row; return its metadata (id, uploaded_at, a fetch URL).
   - **Tip:** allow attaching a photo at reading-entry time too — extend the readings screen
     so the wing manager types the number and uploads the photo in one step.
3. **List / fetch endpoints:**
   - Staff: `GET /api/readings/{reading_id}/photos` (metadata list, scoped);
     `GET /api/readings/{reading_id}/photos/{photo_id}` streams bytes (scoped).
   - **Tenant (new read surface):** tenants currently have no readings access. Add:
     - `GET /api/tenant/readings` — readings for **their own unit only** (so they can see
       this and previous months' meter photos and verify their consumption).
     - `GET /api/tenant/readings/{reading_id}/photos` and
       `.../photos/{photo_id}` — bytes streamed, only if the reading's `unit_id == user.unit_id`,
       else 404.
     - **Decision to confirm with owner:** should tenants see photos for *all* periods, or only
       periods where their bill is **published**? Default recommendation: show all readings for
       their own unit (maximum transparency — this is the whole point of the feature). Note the
       decision in code comments.
   - **Delete** (staff, scoped): `DELETE /api/readings/{reading_id}/photos/{photo_id}` →
     remove row + `get_storage().delete(key)`.
4. **Streaming.** Return `Response(content=bytes, media_type=content_type)`. When the backend
   is Google Drive, the endpoint downloads from Drive then streams — the app's scope check is
   the gatekeeper; never expose Drive links (see §2.2).
5. **UI:**
   - Admin/superuser readings screen: an upload control + thumbnail next to each floor's reading;
     click to view full size; show "entered by / on".
   - Tenant app: a "Meter readings" view showing their floor's photo(s) per month beside the
     units consumed — this is what stops tenants from messaging the owner for meter proof.
6. **Storage backend:** works with `LocalStorage` today; switches to `GoogleDriveStorage`
   (§2.2) with no endpoint changes. Photos live under `readings/unit-{id}/{yyyymm}/…`.
7. **Tests:** upload happy path; non-image rejected; oversize rejected; admin cannot upload to
   a floor outside scope (404); tenant sees only their own floor's photos (404 on others);
   delete removes both row and blob.

---

## 6. Suggested build order

1. **Decide storage/hosting (§2)** — pick Postgres (recommended) and choose blob backend
   (local for now vs Google Drive OAuth). This gates Gap 3's storage work.
2. **Gap 1 (one tenant per floor)** — small, isolated, no math impact. Do first.
3. **Gap 2 (floor-wise charges)** — touches seeding; re-run the anchor test immediately after.
4. **Gap 3 (meter photos)** — largest; needs the extended `Storage` (§2.4) and, for phones,
   the hosting from §2.3.
5. If Google Drive chosen: implement `GoogleDriveStorage` behind the flag and migrate the
   existing PDF path to it too (same interface).

Each step: keep `backend/tests/` green (especially the ₹50,185 anchor), add the new tests
listed, and run the app end-to-end (`docker compose up` or the local flow in `CLAUDE.md`).

---

## 7. Migrations note

The app currently uses `Base.metadata.create_all` on startup (`main.py`) — fine for a fresh
SQLite dev DB, but it will **not** alter existing tables for the new columns/tables above.
Introduce **Alembic** (already a dependency) before shipping these to any database with real
data, so `UnitChargeDefault`, `ReadingPhoto`, and the partial unique index are applied as
versioned migrations rather than a destructive recreate.

---

## 8. One-line summary for each ask

| Owner's question / need | Verdict |
|---|---|
| Store everything in **MongoDB** | Not recommended — data is relational; use **PostgreSQL** (1-line switch, already supported). |
| Store **bills + photos on personal Google Drive (2 TB)** | Yes for the **files** via the `Storage` abstraction, **but** must upload as the owner's account via **OAuth** (a service account can't use the 2 TB). Records stay in the DB. Stream bytes through the app, never share raw Drive links. |
| **One tenant per floor** | Add app guard + partial unique index (Gap 1). |
| **Floor-wise fixed charges** | Add `UnitChargeDefault` per floor; seed drafts from it; superuser-managed screen (Gap 2). Keep the ₹50,185 anchor green. |
| **Meter photo upload + share with tenant** | Add `ReadingPhoto`, scoped upload/fetch endpoints, new tenant readings read surface, behind `Storage` (Gap 3). No OCR yet. |
| **Use it from phones** | Deploy API + Postgres over HTTPS, fix CORS/origins; web apps are already responsive; native app still deferred. |
