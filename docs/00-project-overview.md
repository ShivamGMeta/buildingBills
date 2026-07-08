# Building Bills — Project Overview & Memory

> The billing system that replaces your manual paper process for the building
> (4 floors + parking + EV charging). This document is both the **idea** of the
> application and the **project memory (`CLAUDE.md`)** that keeps the build faithful
> to the decisions we locked in. When an instruction here conflicts with a request,
> surface the conflict instead of silently following one.

---

## 1. The problem we're solving

Today, every month, you:

1. Photograph the electricity meters (4 floors + parking + EV charging).
2. Write the readings on paper.
3. For each floor: subtract last month's reading from this month's to get units used,
   multiply by the rate (₹9/unit), add each flat's share of common-area (lift/parking) units,
   then add fixed charges (rent, water, DG backup, society maintenance).
4. Repeat by hand for every floor and produce a final total.

The worked example that anchors everything (Mohit, 4th floor, May):

```
1st May reading   = 5040
31st May reading  = 5704
Own units         = 664
Common-area share = 75
Billed units      = 664 + 75 = 739  →  739 × ₹9 = ₹6,651
Rent + water      = ₹42,800
DG backup (Apr)   = ₹98
Society maint (May)= ₹636
TOTAL             = ₹50,185
```

That ₹50,185 is the **regression anchor** — the engine must reproduce it exactly.

---

## 2. What we're building

A billing system for the building where:

- **You (admin)** enter meter readings + common-area units for the month, review the
  auto-computed draft bills, adjust fixed charges, then publish.
- **Each tenant** logs in to view/download only their own published bills, and gets an
  email when a new bill is ready.

### The core calculation, per flat, per month

```
own_units      = this_reading − previous_reading
common_share   = flat's share of the metered common-area units
ev_units       = EV charger units (billed 100% to the EV-owning flat)
electricity    = (own_units + common_share + ev_units) × period_rate
total          = electricity + sum(fixed charge lines)
```

- **Common-area split** across the four floors: **4th 35% / 3rd 30% / 2nd 20% / 1st 15%.**
- **EV** is billed 100% to the flat that owns the charger (currently 3rd floor).
- Shares and EV ownership are **DATA on the flat**, never hardcoded branching on a name.

---

## 3. Build path (phased)

**Phase 1 — Digitize the calculation** (biggest time saver, do first)
Type in this month's readings; the app stores last month's automatically, does all the
subtraction, splits common-area units, multiplies by the rate, adds per-flat fixed charges,
and produces a formatted, shareable bill. *(A self-contained mobile-friendly HTML
prototype of this already exists from early in the project.)*

**Phase 2 — Auto-read the meter photo** (harder, add later)
OCR on meter photos. Finicky with 7-segment/mechanical displays, so it's added after
Phase 1 works, always with manual override.

**Explicitly deferred (do not build yet):** WhatsApp notifier, native mobile app, push
notifications, tenant self-set password via email link, payments, complaints.

---

## 4. Architecture & non-negotiables

- **Backend built ONCE; frontends are disposable.** A native app later reuses the same API.
- **Stack:** FastAPI backend, PostgreSQL, Alembic migrations, Docker Compose for local dev
  (postgres + api + Mailpit for email), two vanilla-JS + Vite frontends (admin + tenant).
- **Bill math lives ONLY in `backend/app/services/billing.py`** as pure functions
  (no DB, no HTTP), and is exhaustively unit-tested. Routes stay thin: validate → call a
  service → shape the response. Money is **computed server-side only**.
- **Money is stored as integer paise, never floats** (₹6,651 → `665100`); display divides
  by 100. Prevents cumulative rounding errors.
- **Rate lives on the billing period (the month)**, so old bills keep the rate they were
  billed at when you raise it later.
- **Draft → Published lifecycle.** A draft recomputes live as you edit; the moment you
  publish, the bill stores its own frozen snapshot of readings, rate, and totals — so
  changing a share or next month's rate can never silently rewrite a bill a tenant saw.
- **Opening reading captured at onboarding**, so the first billed month always has a
  previous value. A missing previous reading at bill time is a genuine ERROR, never zeroed.
- **Auth:** email + password login (not name); passwords always hashed; tenant sees their
  name in the UI.
- **Tenant isolation:** a tenant can only read their own **published** bills. Requests for
  someone else's bill, or a draft, return **404** (not 403) so existence isn't leaked.
- **Publish is decoupled from email:** the bill publishes even if the notification fails
  (retryable).
- **Notifications go through a swappable `Notifier` interface** (`services/notifier.py`) —
  email first, WhatsApp/push later — never a concrete import inside bill logic.
- **PDFs** stored on the local filesystem in dev behind a `Storage` abstraction (object
  storage later).

---

## 5. Data model (essentials)

- **Unit** (the flat) is the durable billing object: carries `common_share %`, `has_ev`,
  `opening_reading`, `sort_order`, `is_active`, and owns readings + bills. History survives
  when occupants change.
- **Tenant** (the person) occupies a Unit and logs in — separate from the Unit.
- **billing_period** anchors each month and carries that month's **rate**.
- **charge_line** — arbitrary label + amount, many per bill; per-unit, per-month. Seeded
  from reusable **charge_template**s (label + optional default amount, overridable).
- All amount fields are integer paise.

---

## 6. The four design docs (authoritative spec)

The planning phase produced a complete, self-consistent spec, in order:

1. `docs/01-architecture.md` — architecture & stack.
2. `docs/02-data-model.md` — full data model (Unit/Tenant split, per-unit charges,
   charge templates, baseline rule).
3. `docs/03-api-spec.md` — every endpoint, who can call it, request/response shape, and the
   authorization rules (especially tenants-see-only-their-own-published-bills).
4. `docs/04-build-plan.md` — 13 ordered, agent-executable milestones (M0–M12), each with a
   concrete "Done when" check.

### Build order (risk front-loaded)

- **M0–M1:** local stack + schema.
- **M2 (the pivot):** the billing engine is built and proven with exhaustive tests —
  including the ₹50,185 regression anchor — **before anything depends on it.** Nothing
  else proceeds until it's green.
- **M3–M9:** backend outward from that core — auth → admin flows → publish → PDF → email
  → tenant API.
- **M10–M11:** the two web frontends.
- **M12:** end-to-end tests + seed your real 1–2 months of history.

Each milestone ends by running tests, invoking the `code-reviewer`, updating docs, and
staging a conventional commit.

---

## 7. Agent tooling (`.claude/`)

The project ships with a Claude Code scaffold so the CLI agent already knows the
architecture and enforces the rules:

- **Subagents:** `architect` (design authority; writes docs, not feature code),
  `code-reviewer` (read-only diff review), `e2e-tester` (**read-only** — runs tests and
  reports; never edits code or tests, so it can't cheat its way to green), `docs-keeper`.
- **Slash commands:** `/load-project`, `/new-feature`, `/add-provider`, `/review`,
  `/test-phase`.
- **Hooks** on Write/Edit; `CLAUDE.md` + `.claude/PLAN.md` provide constant context and the
  decisions log; a `bill-calculation` skill encodes the exact formula, edge cases, and
  worked example so any calc work loads the authoritative rules.

*(Caveat: the `.claude/` config reflects Claude Code as documented at build time; that
product updates often. If a hook/setting errors on first run, it's likely a schema tweak in
a newer version — the four design docs are version-independent; only the tooling wrapper is
exposed to that drift.)*

---

## 8. How to start building

1. Unzip the scaffold into `building-bills/` (fills `CLAUDE.md` and `.claude/`).
2. Copy `settings.local.json.example` → `settings.local.json` and set the `model` line to
   your Claude Code version's model string (or delete it).
3. Open the folder in Claude Code and run `/load-project` — it reads all four docs + the plan.
4. Then `/new-feature Milestone 0: repo skeleton and local stack`, or just tell it to start M0.

---

## 9. Decisions log (so we don't relitigate)

- Backend built once; frontends disposable; native later reuses the API.
- Bill math = pure functions in `services/billing.py`; money server-side only; integer paise.
- Common-area split 35/30/20/15; EV 100% to its owning flat; shares are data, not code.
- Rate lives on the month; published bills are frozen snapshots.
- Opening reading at onboarding; missing previous reading = error, never zeroed.
- Draft → Published; tenants see only their own published bills (404 on others/drafts).
- Login = email + password; passwords hashed.
- Notifications via swappable `Notifier`; email first; publish decoupled from email.
- Dev runs fully local (Docker Compose + Mailpit); tests never hit hosted free tiers.
- Tester agent is read-only — it can never touch the billing engine or tests to force green.
