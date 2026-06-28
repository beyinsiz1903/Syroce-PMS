"""
Enable the `mice` add-on module (Events & Banquets / sales-catering) for the
stress-test tenant so BEO-related stress specs can actually execute the
create → attach → generate → transition → kitchen-ticket happy path against
the live backend instead of hitting `ENTITLEMENT_DENIED` (403) at the door
and falling back to a SKIP under the "module-blocked SKIP" doctrine.

Specs unblocked by enabling `mice`:
  - frontend/e2e-stress/specs/14-mice-events.spec.js
  - frontend/e2e-stress/specs/15-sales-opportunities.spec.js
  - frontend/e2e-stress/specs/18-mice-execution-beo.spec.js
  - frontend/e2e-stress/specs/98-fnb-beo-generator.spec.js

Generalized companion to `backend/scripts/enable_spa_mice_for_demo.py`
(Yol 2 v106 follow-up). Idempotent — safe to re-run.

Usage (defaults to the stress-test tenant):
    cd backend && python -m scripts.enable_mice_for_stress

Override the tenant or extend the module set without editing the script:
    E2E_STRESS_TENANT_ID=<uuid> \
    STRESS_ENABLE_MODULES=mice,spa \
        python -m scripts.enable_mice_for_stress

Pilot guard: refuses to run when the resolved tenant id equals
`PILOT_TENANT_ID` — stress add-on enablement must never touch the pilot.
"""

from __future__ import annotations

import asyncio
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient

DEFAULT_STRESS_TENANT_ID = "23377306-a501-4232-adc8-8aea50e243c0"
DEFAULT_MODULES = ("mice",)


def _parse_modules(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return DEFAULT_MODULES
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return tuple(parts) if parts else DEFAULT_MODULES


async def main() -> int:
    mongo = os.environ.get("MONGO_ATLAS_URI") or os.environ.get("MONGO_URL")
    if not mongo:
        print("ERROR: MONGO_ATLAS_URI / MONGO_URL not set", file=sys.stderr)
        return 1

    tenant_id = os.environ.get("E2E_STRESS_TENANT_ID") or DEFAULT_STRESS_TENANT_ID
    pilot_tid = os.environ.get("PILOT_TENANT_ID") or ""
    if pilot_tid and tenant_id == pilot_tid:
        print(
            f"ERROR: refusing to enable add-on modules — resolved tenant {tenant_id} equals PILOT_TENANT_ID. Stress add-on enablement must not touch pilot.",
            file=sys.stderr,
        )
        return 3

    modules = _parse_modules(os.environ.get("STRESS_ENABLE_MODULES"))

    client = AsyncIOMotorClient(mongo)
    db = client["syroce-pms"]

    tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0, "name": 1, "modules": 1})
    if not tenant:
        print(f"ERROR: tenant {tenant_id} not found", file=sys.stderr)
        return 2

    current = tenant.get("modules") or {}
    missing = [m for m in modules if current.get(m) is not True]
    if not missing:
        print(f"OK: tenant '{tenant.get('name')}' ({tenant_id}) already has {', '.join(modules)} enabled — nothing to do.")
        return 0

    update = {f"modules.{m}": True for m in modules}
    res = await db.tenants.update_one({"id": tenant_id}, {"$set": update})
    print(f"Stress tenant '{tenant.get('name')}' ({tenant_id}): enabled add-ons {', '.join(modules)} (missing_before={missing}, matched={res.matched_count}, modified={res.modified_count}).")

    # Sanity check — confirm post-write state so a silent no-op surfaces.
    after = await db.tenants.find_one({"id": tenant_id}, {"_id": 0, "modules": 1})
    after_modules = (after or {}).get("modules") or {}
    still_off = [m for m in modules if after_modules.get(m) is not True]
    if still_off:
        print(
            f"ERROR: post-write verification failed — still OFF: {still_off}",
            file=sys.stderr,
        )
        return 4

    if "mice" in modules:
        events_count = await db.mice_events.count_documents({"tenant_id": tenant_id})
        menus_count = await db.mice_menus.count_documents({"tenant_id": tenant_id})
        spaces_count = await db.mice_spaces.count_documents({"tenant_id": tenant_id})
        print(f"mice data probe — events={events_count} menus={menus_count} spaces={spaces_count}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
