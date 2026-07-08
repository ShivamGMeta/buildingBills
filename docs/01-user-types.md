# Building Bills — User Types & Permissions

> Defines the three roles in the application and exactly what each can do.
> This supersedes the earlier two-role (admin + tenant) model: it adds a
> **Superuser** on top and scopes **Admins** to specific floors. That change
> affects the data model and API authorization rules — see the open decisions
> at the end before implementation.

---

## 1. User types

### a) Superuser
- Has access to **everything** in the application.
- **There can be only one Superuser.**
- Can do anything an Admin or Tenant can, plus manage Admins (add/remove, assign
  floors, promote/demote) and set building-wide values (rate, common-area split).

### b) Admin
- Scoped to their **assigned floor(s)** and the tenants on those floors.
- Can generate bills for their scope.
- **Cannot** promote or demote anyone.
- Can add tenants to their **allowed floors only**.

### c) Tenant
- **Read-only** on their own data.
- Can view and download their **own** bills.
- Can view (read only) their own personal details.

---

## 2. Functionality matrix

Legend: ✅ full · ⚠️ conditional (see notes) · ❌ none

| #  | Functionality                                         | Superuser      | Admin              | Tenant            |
|----|-------------------------------------------------------|----------------|--------------------|-------------------|
| 1  | Create / generate bill                                | ✅ all floors  | ✅ own floors only | ❌                |
| 2  | View bill                                             | ✅ all         | ✅ own floors      | ✅ own bills only |
| 3  | Download bill PDF                                     | ✅ all         | ✅ own floors      | ✅ own bills only |
| 4  | Add tenant                                            | ✅ any floor   | ✅ own floors only | ❌                |
| 5  | Remove / deactivate tenant                            | ✅ any         | ✅ own floors      | ❌                |
| 6  | Edit tenant details                                   | ✅ any         | ✅ own floors      | ❌ (read-only self)|
| 7  | View own personal details                             | ✅             | ✅                 | ✅ (read only)    |
| 8  | Enter monthly meter readings                          | ✅ all         | ✅ own floors      | ❌                |
| 9  | Edit fixed charges on a bill                          | ✅             | ✅ own floors      | ❌                |
| 10 | Publish / unpublish bill                              | ✅             | ✅ own floors      | ❌                |
| 11 | Manage units/flats (share %, EV flag, opening reading)| ✅             | ⚠️ view only       | ❌                |
| 12 | Set the monthly electricity rate                      | ✅ only        | ❌ (consumes it)   | ❌                |
| 13 | Add / remove / edit Admins                            | ✅ only        | ❌                 | ❌                |
| 14 | Assign floors to an Admin                             | ✅ only        | ❌                 | ❌                |
| 15 | Promote / demote users                                | ✅ only        | ❌                 | ❌                |
| 16 | View all floors / building-wide data                  | ✅             | ❌ (own scope)     | ❌                |
| 17 | Manage charge templates                               | ✅             | ⚠️ see decision 1  | ❌                |
| 18 | Enter building-wide common-area units                 | ✅             | ⚠️ see decision 2  | ❌                |
| 19 | Receive bill-ready email notification                 | —              | —                  | ✅                |

**Notes on conditional (⚠️) rows**
- **Row 11:** Unit configuration (common-area share %, EV ownership, opening reading)
  affects the math for the whole building, so Admins can view their flats but not
  change these — Superuser manages them.
- **Row 12 / 17 / 18:** Building-wide inputs — see open decisions below.

---

## 3. Scope rules (how "own floors" is enforced)

- An Admin is linked to one or more floors/units. Every read and write they perform is
  filtered to that set; anything outside it returns **404** (not 403), consistent with the
  tenant-isolation rule, so existence isn't leaked.
- A Tenant is linked to exactly one Unit and can only ever see their own **published**
  bills; other tenants' bills or any draft return **404**.
- The Superuser bypasses all scoping.