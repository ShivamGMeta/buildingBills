# Building Bills — Project Memory

> Monthly billing for the building (4 floors + parking + EV charging).
> The authoritative spec lives in `docs/`. When an instruction here conflicts
> with a request, surface the conflict instead of silently following one.

## The regression anchor

Mohit, 4th floor, May: own 664 units + common share 75 = 739 × ₹9 = ₹6,651;
plus rent ₹41,600 + water ₹1,200 + DG (Apr) ₹98 + maintenance (May) ₹636
= **₹50,185** (`5_018_500` paise). `backend/tests/test_billing.py` must always
reproduce this exactly — both as a pure function and end-to-end via the API.

## Architecture (three roles, two frontends, one backend)

- **Backend** (`backend/`): FastAPI + SQLAlchemy + PostgreSQL (SQLite in dev/tests).
  Built once; frontends are disposable and a native app later reuses the same API.
- **`frontend-superuser/`** (Vite + vanilla JS, port 5173): the Superuser console —
  everything, plus admin management and building-wide settings.
- **`frontend-tenant-admin/`** (Vite + vanilla JS, port 5174): one app, two faces.
  Admins get scoped billing flows; tenants get read-only own-bills + profile.

## Roles (see docs/01-user-types.md for the full matrix)

- **Superuser** — exactly ONE exists (enforced in `routers/users.py`). Manages
  admins, floor assignments, promote/demote, rate, common-area split, unit
  config, charge templates, building-wide common/EV units.
- **Admin** — scoped to assigned floors via `admin_scopes`. Bills, readings,
  tenants on those floors only. Out-of-scope = **404** (never 403 — no
  existence leak). Superuser-only actions = 403.
- **Tenant** — read-only: own profile, own **published** bills. Drafts and
  others' bills = 404.

## Non-negotiables (do not relitigate — see docs/00-project-overview.md §9)

- Bill math lives ONLY in `backend/app/services/billing.py` as pure functions
  (no DB/HTTP), exhaustively unit-tested. Routes stay thin. Money computed
  server-side only.
- Money is integer **paise**, never floats. Readings are integer kWh.
- Common-area split (35/30/20/15) and EV ownership are **data on the Unit**
  (`common_share_bps`, `has_ev`) — never hardcoded branching on a name.
  Allocation uses largest-remainder so shares sum exactly to the metered total.
- Rate lives on the **billing period**; raising it later never rewrites old bills.
- **Draft → Published**: drafts recompute live; publish freezes the snapshot
  (readings, rate, totals) on the bills row. Editing a published bill = 409.
- Missing previous reading is an **error** (422), never zeroed. Opening reading
  is captured at unit onboarding and backs the first billed month.
- Publish is decoupled from email — notification failure never blocks publish
  (`services/notifier.py`, swappable `Notifier`; Mailpit in dev).
- PDFs behind a `Storage` abstraction (`services/storage.py`), local FS in dev.
- Auth: email + password, bcrypt-hashed, JWT bearer.

## Decisions made in this build (open items from docs/01-user-types.md)

- Row 17 (charge templates) and row 18 (building-wide common-area/EV units):
  **Superuser-only** to write; admins read/consume them. Revisit if needed.
- Admins MAY open a new billing month, but its rate carries over from the
  latest period; only the Superuser can change a rate.
- "Mark as paid" (from the mock) is on staff bills as a toggle + `paid_at`.

## Dev workflow

```bash
docker compose up                  # postgres + api + mailpit (localhost:8025)
# or local:
cd backend && pip install -r requirements.txt
python seed.py && uvicorn app.main:app --reload   # seeds demo logins, pw: changeme123
cd frontend-superuser && npm i && npm run dev     # :5173
cd frontend-tenant-admin && npm i && npm run dev  # :5174
cd backend && python -m pytest tests/             # must stay green, esp. the anchor
```

Deferred (do not build yet): meter-photo OCR (Phase 2), WhatsApp/push, native
app, payments, complaints, tenant self-set password.
