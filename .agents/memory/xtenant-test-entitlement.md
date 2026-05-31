---
name: Cross-tenant integration test on entitled surface
description: How to write a live cross-tenant 404 test against a module-gated PMS surface, and which seeded role to use for a 403.
---

Live integration tests that need a *second* tenant owning a record on an
entitlement-gated surface (e.g. /api/sales/* requires the `sales_crm` module)
cannot use a tenant created via `POST /api/auth/register`: new tenants land on
the `basic`/`core_small_hotel` plan and lack the module, so even creating the
victim record returns 403 `ENTITLEMENT_DENIED` (not the cross-tenant 404 you
want to assert).

**How to apply:** seed the victim row directly with pymongo under a fabricated
`tenant_id` (mirrors `test_cross_tenant_isolation_e2e.py`), have the *entitled*
demo tenant attempt the action, assert 404, verify the foreign row is untouched
(side-effect check), and delete the row in `finally`. conftest wires `MONGO_URL`
from `MONGO_ATLAS_URI` and `DB_NAME=syroce-pms`.

**403 (missing-permission) tests:** the seeded FRONT_DESK user *has*
`VIEW_COMPANIES`, so it PASSES `manage_sales` (no 403). Use the seeded
HOUSEKEEPING-role user (no VIEW_COMPANIES) to get a real 403. The seeded staff
users, their roles, and their credentials live in `backend/seed/tenant_users.py`
— read that file for the exact email/password rather than hardcoding them here.

**Why:** wasted a run discovering register→basic-plan→entitlement 403 masks the
isolation 404; and FRONT_DESK silently passing manage_sales would have made a
403 assertion impossible.
