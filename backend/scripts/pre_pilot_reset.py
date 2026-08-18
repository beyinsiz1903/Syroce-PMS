#!/usr/bin/env python3
"""Dry-run-first CLI for the Syroce pre-pilot reset and module-user seed.

Examples (read-only):

    python scripts/pre_pilot_reset.py reset
    python scripts/pre_pilot_reset.py seed-module-users \
        --tenant-id <tenant-id> --email-domain pilot.example.com

Write modes are intentionally inconvenient and require separate environment
flags, exact confirmation strings, expected database name and (for reset)
expected super-admin count.  This script never calls provider APIs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ops.pre_pilot_reset import (  # noqa: E402
    PRODUCTION_CONFIRMATION,
    RESET_CONFIRMATION,
    SEED_CONFIRMATION,
    build_module_user_specs,
    build_reset_plan,
    execute_reset,
    seed_module_users,
    validate_reset_execution_guard,
    validate_seed_execution_guard,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Syroce pre-pilot reset and RBAC seed")
    subparsers = parser.add_subparsers(dest="command", required=True)

    reset = subparsers.add_parser("reset", help="Plan or execute the pre-pilot reset")
    reset.add_argument("--execute", action="store_true", help="Enable the guarded write path")
    reset.add_argument("--confirm", help=f"Exact token required for writes: {RESET_CONFIRMATION}")
    reset.add_argument(
        "--production-confirm",
        help=f"Additional production token: {PRODUCTION_CONFIRMATION}",
    )
    reset.add_argument("--expected-database", help="Exact MongoDB database name")
    reset.add_argument("--expected-super-admin-count", type=int, default=1)

    seed = subparsers.add_parser(
        "seed-module-users",
        help="Plan or idempotently seed module-scoped test users into an existing tenant",
    )
    seed.add_argument("--tenant-id", required=True)
    seed.add_argument("--email-domain", required=True)
    seed.add_argument("--execute", action="store_true", help="Enable the guarded write path")
    seed.add_argument("--confirm", help=f"Exact token required for writes: {SEED_CONFIRMATION}")
    seed.add_argument("--expected-database", help="Exact MongoDB database name")

    return parser


def _database_name(database: Any) -> str:
    return str(getattr(database, "name", None) or "unknown")


async def _run_reset(args: argparse.Namespace, database: Any) -> dict[str, Any]:
    plan = await build_reset_plan(database)
    validate_reset_execution_guard(
        execute=args.execute,
        confirmation=args.confirm,
        production_confirmation=args.production_confirm,
        expected_database_name=args.expected_database,
        expected_super_admin_count=args.expected_super_admin_count,
        plan=plan,
    )
    output = plan.public_summary()
    if not args.execute:
        output["mode"] = "dry-run"
        output["next_step"] = "Review blockers and candidate counts; no records were changed."
        return output

    deleted = await execute_reset(database, plan)
    output.update(
        {
            "mode": "execute",
            "deleted_counts": deleted,
            "write_count": sum(deleted.values()),
        }
    )
    return output


async def _run_seed(args: argparse.Namespace, database: Any) -> dict[str, Any]:
    specs = build_module_user_specs(args.tenant_id, args.email_domain)
    tenant_exists = bool(
        await database.tenants.find_one(
            {"$or": [{"id": args.tenant_id}, {"_id": args.tenant_id}]},
            {"_id": 0, "id": 1},
        )
    )
    existing_count = await database.users.count_documents(
        {"id": {"$in": [spec.id for spec in specs]}}
    )
    output: dict[str, Any] = {
        "mode": "execute" if args.execute else "dry-run",
        "database_name": _database_name(database),
        "tenant_exists": tenant_exists,
        "profile_count": len(specs),
        "existing_seed_user_count": existing_count,
        "create_candidate_count": len(specs) - existing_count,
        "update_candidate_count": existing_count,
        "profiles": [spec.public_summary() for spec in specs],
        "write_count": 0,
    }

    validate_seed_execution_guard(
        execute=args.execute,
        confirmation=args.confirm,
        expected_database_name=args.expected_database,
        actual_database_name=_database_name(database),
    )
    if not args.execute:
        output["next_step"] = "Create the pilot tenant, review scopes, then use separately approved execute mode."
        return output

    password = os.environ.get("PRE_PILOT_MODULE_USER_PASSWORD", "")
    result = await seed_module_users(
        database,
        tenant_id=args.tenant_id,
        email_domain=args.email_domain,
        password=password,
    )
    output.update(result)
    output["write_count"] = result["total"]
    return output


async def _async_main(args: argparse.Namespace) -> dict[str, Any]:
    # Importing the application database is delayed until after argument
    # parsing; importing this module for tests cannot connect or mutate.
    from core.database import _raw_db

    if args.command == "reset":
        return await _run_reset(args, _raw_db)
    if args.command == "seed-module-users":
        return await _run_seed(args, _raw_db)
    raise RuntimeError("BLOCKED_UNKNOWN_PRE_PILOT_COMMAND")


def main() -> int:
    args = _build_parser().parse_args()
    try:
        result = asyncio.run(_async_main(args))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
