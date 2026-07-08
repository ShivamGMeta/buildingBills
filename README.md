# Building Bills

Monthly electricity + fixed-charge billing for the building (4 floors, parking,
EV charging). One FastAPI backend, **two frontends**:

| App | Who | Port | What |
|---|---|---|---|
| `frontend-superuser/` | The single **Superuser** | 5173 | Everything: readings, bills, rate, common-area split, unit config, charge templates, **manage admins & floor assignments** |
| `frontend-tenant-admin/` | **Admins** + **Tenants** | 5174 | Admins: billing flows scoped to their assigned floors. Tenants: read-only own published bills + profile |

Full spec: [`docs/00-project-overview.md`](docs/00-project-overview.md) ·
[`docs/01-user-types.md`](docs/01-user-types.md) · decisions log in
[`CLAUDE.md`](CLAUDE.md).

## Quick start (local, no Docker)

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python seed.py                      # demo data, password: changeme123
.venv/bin/uvicorn app.main:app --reload       # API on :8000

# in two more terminals
cd frontend-superuser && npm install && npm run dev      # :5173
cd frontend-tenant-admin && npm install && npm run dev   # :5174
```

Demo logins (`changeme123`): superuser `owner@example.com`, admin
`admin@example.com` (1st+2nd floor), tenants `mohit@` / `amit@` / `neha@` /
`karan@example.com`.

## Docker (postgres + api + mailpit)

```bash
docker compose up --build
# API :8000 · Mailpit UI :8025 (bill-ready emails land here)
docker compose exec api python seed.py
```

## Tests

```bash
cd backend && .venv/bin/python -m pytest tests/
```

18 tests including the regression anchor: Mohit's May bill must total exactly
**₹50,185** (5,018,500 paise), plus admin floor-scoping (404 outside scope),
tenant isolation (drafts/others' bills = 404), frozen published snapshots, and
single-Superuser enforcement.
