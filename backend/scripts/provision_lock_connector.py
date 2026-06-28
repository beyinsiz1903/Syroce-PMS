"""Provision an on-prem lock-bridge connector for a tenant.

Registers a connector record and prints its plaintext key EXACTLY ONCE. Only the
salted hash is stored; the key cannot be recovered later. Run this on the server
(or via the Replit shell) when installing the Brassco connector at a hotel.

Usage:
    python -m scripts.provision_lock_connector --tenant <TENANT_ID> --name "Resepsiyon PC"

The printed key goes into the on-prem connector config as LOCK_BRIDGE_KEY.
Do not paste the key into chat, tickets, or commits.
"""

import argparse
import asyncio
import sys


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Provision a lock-bridge connector key")
    parser.add_argument("--tenant", required=True, help="Tenant id (hotel) the connector serves")
    parser.add_argument("--name", required=True, help="Human label, e.g. 'Resepsiyon PC'")
    args = parser.parse_args()

    from core.database import db
    from domains.pms.lock_bridge.service import (
        ensure_lock_bridge_indexes,
        register_connector,
    )

    await ensure_lock_bridge_indexes(db)
    key = await register_connector(db, tenant_id=args.tenant, name=args.name)

    print("Connector registered.")
    print(f"  tenant : {args.tenant}")
    print(f"  name   : {args.name}")
    print("  KEY    : " + key)
    print("\nStore this KEY in the on-prem connector config (LOCK_BRIDGE_KEY).")
    print("It is shown only once and cannot be recovered.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
