"""
Enable the `hidden_marketplace` feature flag for the stress-test tenant so the
marketplace deep-lifecycle stress spec can actually execute the purchase-order
create → cancel happy path against the live backend instead of hitting a 404
at the `require_feature("hidden_marketplace")` door and falling back to a
REVIEW/SKIP.

`hidden_marketplace` is an OPT-IN extra feature: it belongs to no subscription
plan (default OFF for every tenant) and ships dark. It can only be turned on by
an explicit per-tenant `features` override — see `OPT_IN_EXTRA_FEATURES` in
`backend/core/helpers.py`. Flipping it ON for one tenant does NOT affect any
other tenant or production default.

Specs unblocked by enabling `hidden_marketplace`:
  - frontend/e2e-stress/specs/98-marketplace-deep-lifecycle.spec.js
    (F inventory probe + H purchase-order create + I purchase-order cancel)

Companion to `backend/scripts/enable_mice_for_stress.py`. The stress seed
endpoint (`POST /api/admin/stress/seed`) already sets this flag idempotently on
every run, so this script is the manual/operator escape hatch (e.g. when seed
ran before this change shipped). Idempotent — safe to re-run.

Usage (defaults to the stress-test tenant):
    cd backend && python -m scripts.enable_marketplace_for_stress

Override the tenant without editing the script:
    E2E_STRESS_TENANT_ID=<uuid> \
        python -m scripts.enable_marketplace_for_stress

Pilot guard: refuses to run when the resolved tenant id equals
`PILOT_TENANT_ID` — stress entitlement must never touch the pilot.
"""

from __future__ import annotations

import asyncio
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient

DEFAULT_STRESS_TENANT_ID = "23377306-a501-4232-adc8-8aea50e243c0"
FEATURE_KEY = "hidden_marketplace"


async def main() -> int:
    mongo = os.environ.get("MONGO_ATLAS_URI") or os.environ.get("MONGO_URL")
    if not mongo:
        print("ERROR: MONGO_ATLAS_URI / MONGO_URL not set", file=sys.stderr)
        return 1

    tenant_id = os.environ.get("E2E_STRESS_TENANT_ID") or DEFAULT_STRESS_TENANT_ID
    pilot_tid = os.environ.get("PILOT_TENANT_ID") or ""
    if pilot_tid and tenant_id == pilot_tid:
        print(
            f"ERROR: refusing to enable {FEATURE_KEY} — resolved tenant {tenant_id} equals PILOT_TENANT_ID. Stress entitlement must not touch pilot.",
            file=sys.stderr,
        )
        return 3

    client = AsyncIOMotorClient(mongo)
    db_name = os.environ.get("DB_NAME", "syroce-pms")
    db = client[db_name]

    tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0, "name": 1, "features": 1})
    if not tenant:
        print(f"ERROR: tenant {tenant_id} not found", file=sys.stderr)
        return 2

    current = tenant.get("features") or {}
    if current.get(FEATURE_KEY) is True:
        print(f"OK: tenant '{tenant.get('name')}' ({tenant_id}) already has {FEATURE_KEY} enabled — nothing to do.")
        return 0

    res = await db.tenants.update_one({"id": tenant_id}, {"$set": {f"features.{FEATURE_KEY}": True}})
    print(f"Stress tenant '{tenant.get('name')}' ({tenant_id}): enabled feature {FEATURE_KEY} (matched={res.matched_count}, modified={res.modified_count}).")

    # Sanity check — confirm post-write state so a silent no-op surfaces.
    after = await db.tenants.find_one({"id": tenant_id}, {"_id": 0, "features": 1})
    after_features = (after or {}).get("features") or {}
    if after_features.get(FEATURE_KEY) is not True:
        print(
            f"ERROR: post-write verification failed — {FEATURE_KEY} still OFF",
            file=sys.stderr,
        )
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
