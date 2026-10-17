"""Link existing hotels to their property profile's menu (``nav_profile``).

Hotels created before ``nav_profile`` carry a copy of their profile's menu
lists (hidden / visible items, groups, labels) taken at creation, so pages
added to a profile later never reach them. With ``nav_profile`` set the menu
is read from the profile as it is now (``resolve_tenant_nav``).

What it does
------------
For every hotel without ``nav_profile`` it finds the profile for its
``property_type`` (aliases such as ``boutique`` -> ``boutique_hotel``, as in
onboarding) and links it **only if** the stored lists are exactly the profile's
current lists, i.e. an untouched copy. Hotels whose lists differ (edited, or
copied from an older profile) are reported and left as they are. Nothing but
``nav_profile`` (and the run id) is written; the stored lists stay.

Safety contract
---------------
* Default is a dry run that prints every hotel and the decision.
* ``--apply`` / ``--undo`` additionally require ``ALLOW_NAV_PROFILE_LINK=true``.
* ``--apply`` writes with a compare-and-set on the property type and lists it
  compared, and on ``nav_profile`` still being absent; changed hotels are skipped.
* ``--undo <run_id>`` removes ``nav_profile`` only where this run set it.
* Every run writes a summary to ``nav_profile_link_runs``.

Usage
-----
    python -m scripts.link_tenant_nav_profiles
    ALLOW_NAV_PROFILE_LINK=true python -m scripts.link_tenant_nav_profiles --apply
    ALLOW_NAV_PROFILE_LINK=true python -m scripts.link_tenant_nav_profiles --undo <run_id>
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("link_tenant_nav_profiles")

# Same aliases as onboarding (routers/onboarding.py _PROPERTY_TYPE_ALIASES).
PROPERTY_TYPE_ALIASES = {
    "hotel": "city_hotel",
    "boutique": "boutique_hotel",
    "butik": "boutique_hotel",
    "apart": "apart_hotel",
    "resort": "resort_summer",
    "pansiyon": "pension",
}


def profile_key_for(property_type: str | None) -> str | None:
    from domains.admin.property_profiles import get_property_profile

    key = str(property_type or "").strip().lower()
    key = PROPERTY_TYPE_ALIASES.get(key, key)
    return key if key and get_property_profile(key) else None


def _normalized(field: str, value):
    if field.endswith("labels"):
        return dict(value or {})
    return sorted(value or [])


def decide(tenant: dict) -> tuple[str, str | None]:
    """('link', profile) for an untouched copy; otherwise (reason, profile)."""
    from domains.admin.property_profiles import NAV_CONFIG_FIELDS, get_hidden_nav_config

    if tenant.get("nav_profile"):
        return "already_linked", tenant["nav_profile"]
    profile = profile_key_for(tenant.get("property_type"))
    if not profile:
        return "no_profile", None
    current = get_hidden_nav_config(profile)
    for field in NAV_CONFIG_FIELDS:
        if _normalized(field, tenant.get(field)) != _normalized(field, current.get(field)):
            return f"differs:{field}", profile
    return "link", profile


def _cas_filter(tenant: dict) -> dict:
    from domains.admin.property_profiles import NAV_CONFIG_FIELDS

    query = {"id": tenant["id"], "nav_profile": {"$exists": False}}
    # The selected profile depends on this exact stored type, before aliases
    # are resolved. Reject an onboarding edit between the read and the write.
    for field in ("property_type", *NAV_CONFIG_FIELDS):
        query[field] = tenant[field] if field in tenant else {"$exists": False}
    return query


async def run(db, *, apply: bool, undo: str | None) -> dict:
    run_id = undo or str(uuid.uuid4())
    summary = {"run_id": run_id, "mode": "undo" if undo else ("apply" if apply else "dry_run"),
               "started_at": datetime.now(UTC).isoformat(), "linked": 0, "skipped_changed": 0, "decisions": {}}

    if undo:
        result = await db.tenants.update_many({"nav_profile_link_run": run_id},
                                              {"$unset": {"nav_profile": "", "nav_profile_link_run": ""}})
        summary["unlinked"] = result.modified_count
        logger.info("undo %s: %s hotels unlinked", run_id, result.modified_count)
    else:
        async for tenant in db.tenants.find({}, {"_id": 0}):
            decision, profile = decide(tenant)
            summary["decisions"][decision] = summary["decisions"].get(decision, 0) + 1
            logger.info("%-34s type=%-16s -> %s %s", (tenant.get("property_name") or tenant.get("id"))[:34],
                        tenant.get("property_type"), decision, profile or "")
            if decision != "link" or not apply:
                continue
            result = await db.tenants.update_one(_cas_filter(tenant), {"$set": {
                "nav_profile": profile, "nav_profile_link_run": run_id}})
            if result.modified_count:
                summary["linked"] += 1
            else:
                summary["skipped_changed"] += 1

    summary["finished_at"] = datetime.now(UTC).isoformat()
    if apply or undo:
        await db.nav_profile_link_runs.insert_one(dict(summary))
    logger.info("summary: %s", {k: v for k, v in summary.items() if k != "started_at"})
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--undo", metavar="RUN_ID")
    args = parser.parse_args()
    if (args.apply or args.undo) and os.environ.get("ALLOW_NAV_PROFILE_LINK") != "true":
        sys.exit("--apply / --undo require ALLOW_NAV_PROFILE_LINK=true")
    if args.apply and args.undo:
        sys.exit("--apply and --undo are exclusive")

    from core.database import _raw_db

    asyncio.run(run(_raw_db, apply=args.apply, undo=args.undo))


if __name__ == "__main__":
    main()
