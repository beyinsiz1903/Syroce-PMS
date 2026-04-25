"""Normalize legacy purchase-request department values to canonical Turkish.

Background:
    `PRIn.department` was historically a free-text str field (no enum). Some PRs
    written before v112 may carry English/legacy values like "Housekeeping",
    "F&B", "Engineering", etc. As of v112 the PR Modal forces 8 canonical
    Turkish values (Kat Hizmetleri, F&B, Teknik, Ön Büro, Bakım, Güvenlik,
    Yönetim, Diğer). This one-shot migration normalises old rows so the
    department filter (procurement.py L300) and reports group cleanly.

Usage:
    python -m backend.scripts.normalize_pr_departments              # all tenants
    python -m backend.scripts.normalize_pr_departments --dry-run    # preview
    python -m backend.scripts.normalize_pr_departments --tenant <uuid>

Behaviour:
- Reads `purchase_requests` collection.
- For each doc whose `department` matches a legacy/aliased value (case-insensitive),
  writes the canonical Turkish value via `$set`.
- Unknown values are mapped to "Diğer" (only logged, not changed unless --aggressive).
- Idempotent: re-running is safe.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

# Allow running as a script (python backend/scripts/normalize_pr_departments.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

# Load backend/.env so MONGO_URL / DB_NAME match the running API.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Canonical (current) values come from ProcurementPage.jsx PR Modal dropdown.
CANONICAL = {
    "Kat Hizmetleri",
    "F&B",
    "Teknik",
    "Ön Büro",
    "Bakım",
    "Güvenlik",
    "Yönetim",
    "Diğer",
}

# Aliases — left side normalised lowercase, right side canonical.
ALIASES: dict[str, str] = {
    # English
    "housekeeping": "Kat Hizmetleri",
    "house keeping": "Kat Hizmetleri",
    "rooms": "Kat Hizmetleri",
    "f&b": "F&B",
    "fnb": "F&B",
    "food and beverage": "F&B",
    "food & beverage": "F&B",
    "kitchen": "F&B",
    "engineering": "Teknik",
    "technical": "Teknik",
    "front office": "Ön Büro",
    "frontdesk": "Ön Büro",
    "front desk": "Ön Büro",
    "reception": "Ön Büro",
    "maintenance": "Bakım",
    "security": "Güvenlik",
    "management": "Yönetim",
    "admin": "Yönetim",
    "administration": "Yönetim",
    "other": "Diğer",
    "misc": "Diğer",
    # Turkish casing fixes
    "kat hizmetleri": "Kat Hizmetleri",
    "teknik": "Teknik",
    "ön büro": "Ön Büro",
    "on buro": "Ön Büro",
    "bakım": "Bakım",
    "bakim": "Bakım",
    "güvenlik": "Güvenlik",
    "guvenlik": "Güvenlik",
    "yönetim": "Yönetim",
    "yonetim": "Yönetim",
    "diğer": "Diğer",
    "diger": "Diğer",
}


def canonicalize(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if s in CANONICAL:
        return s  # Already canonical, no change.
    key = s.lower()
    return ALIASES.get(key)


async def run(tenant: str | None, dry_run: bool, aggressive: bool) -> None:
    # Mirror backend/start.sh precedence: MONGO_URL wins, else MONGO_ATLAS_URI.
    mongo_url = (
        os.environ.get("MONGO_URL")
        or os.environ.get("MONGO_ATLAS_URI")
        or "mongodb://localhost:27017"
    )
    db_name = os.environ.get("DB_NAME", "syroce-pms")
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    db = client[db_name]
    print(f"Connected: db={db_name}")
    # Active runtime collection — see backend/routers/procurement.py.
    coll = db["proc_purchase_requests"]
    query: dict[str, Any] = {}
    if tenant:
        query["tenant_id"] = tenant

    cursor = coll.find(query, projection={"_id": 1, "department": 1, "tenant_id": 1, "pr_no": 1})
    total = updated = skipped_canonical = unknown = 0
    unknown_samples: list[str] = []

    async for doc in cursor:
        total += 1
        current = doc.get("department")
        if isinstance(current, str) and current in CANONICAL:
            skipped_canonical += 1
            continue

        target = canonicalize(current)
        if target is None:
            unknown += 1
            if len(unknown_samples) < 10:
                unknown_samples.append(f"{doc.get('pr_no')}={current!r}")
            if aggressive:
                target = "Diğer"
            else:
                continue

        if target == current:
            skipped_canonical += 1
            continue

        print(
            f"  {'[DRY] ' if dry_run else ''}{doc.get('pr_no', doc['_id'])}: "
            f"{current!r} → {target!r}"
        )
        if not dry_run:
            await coll.update_one({"_id": doc["_id"]}, {"$set": {"department": target}})
        updated += 1

    print()
    print(f"Total scanned:        {total}")
    print(f"Already canonical:    {skipped_canonical}")
    print(f"Updated{' (planned)' if dry_run else '':<13}{updated}")
    print(f"Unknown (left as-is): {unknown}")
    if unknown_samples:
        print("Samples:", ", ".join(unknown_samples))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tenant", help="Limit to a single tenant_id (uuid).")
    ap.add_argument("--dry-run", action="store_true", help="Print without writing.")
    ap.add_argument(
        "--aggressive",
        action="store_true",
        help="Map unknown values to 'Diğer' instead of leaving them.",
    )
    args = ap.parse_args()
    asyncio.run(run(args.tenant, args.dry_run, args.aggressive))


if __name__ == "__main__":
    main()
