"""
Operator recovery script — disable 2FA on the stress admin account.

When to run
-----------
Stress CI suite (spec 98C — F8AG § 2FA TOTP Lifecycle) leaves the stress
admin account 2FA-enabled if the job is hard-cancelled (GitHub Actions
timeout, manual cancel, runner crash) before the spec's `afterAll` /
test H (`disable cleanup primary path`) finishes. The next CI run then
fails at `global-setup.js:128` with "stress admin token boş geldi" —
`/api/auth/login` returns `access_token=""` + `requires_2fa=true`.

This script directly clears the user's 2FA fields in MongoDB Atlas
(idempotent: harmless if 2FA is already disabled). It uses the SAME
encrypted-email lookup as the auth router, so it works against the live
encrypted-PII collection.

Required env vars (inherited from `backend/start.sh` / the running
Backend API workflow):
  - MONGO_URL              (Atlas connection string)
  - DB_NAME                (e.g. "syroce-pms")
  - E2E_STRESS_ADMIN_EMAIL (the account to clear)
  - any field-encryption keys the auth router uses for hashed-email
    lookup (FIELD_ENCRYPTION_KEY, FIELD_HASH_KEY, etc. — already in
    the Backend API process env)

Usage
-----
Dry-run (default — shows current state, no mutation):
    python backend/scripts/reset_stress_admin_2fa.py

Apply (clears two_factor_enabled + secret + backup codes):
    python backend/scripts/reset_stress_admin_2fa.py --apply

From a Replit shell where Backend API is running but env isn't sourced
into the current shell:
    PID=$(pgrep -f "uvicorn.*server:app" | head -1)
    while IFS='=' read -r k v; do
      case "$k" in
        MONGO_URL|DB_NAME|E2E_STRESS_ADMIN_EMAIL|FIELD_ENCRYPTION_KEY|FIELD_HASH_KEY|FIELD_ENC_KEY|SEARCH_HASH_SECRET|JWT_SECRET|ENCRYPTION_KEY)
          export "$k=$v" ;;
      esac
    done < <(tr '\0' '\n' < /proc/$PID/environ)
    python backend/scripts/reset_stress_admin_2fa.py --apply
"""

import asyncio
import os
import sys

# Ensure the backend package is importable when the script is run from the
# repo root (`python backend/scripts/reset_stress_admin_2fa.py`) instead of
# from inside `backend/`.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


async def main(apply: bool) -> int:
    email = os.environ.get("E2E_STRESS_ADMIN_EMAIL")
    if not email:
        print("ERROR: E2E_STRESS_ADMIN_EMAIL env var not set.", file=sys.stderr)
        return 2

    url = os.environ.get("MONGO_URL")
    if not url:
        print("ERROR: MONGO_URL env var not set.", file=sys.stderr)
        return 2

    db_name = os.environ.get("DB_NAME", "syroce-pms")

    cli = AsyncIOMotorClient(url, serverSelectionTimeoutMS=20_000)
    db = cli[db_name]

    try:
        await db.command("ping")
    except Exception as e:
        print(f"ERROR: MongoDB ping failed: {e}", file=sys.stderr)
        return 3

    # Use the SAME encrypted-email lookup the auth router uses so we find
    # the user regardless of whether the email is stored encrypted or in
    # legacy plaintext.
    try:
        from security.encrypted_lookup import build_user_email_query
    except Exception as e:
        print(f"ERROR: import build_user_email_query failed: {e}", file=sys.stderr)
        print(
            "HINT: run from the project root with the Backend API venv active, "
            "and ensure field-encryption env vars are in scope.",
            file=sys.stderr,
        )
        return 4

    q = build_user_email_query(email)

    user = await db.users.find_one(
        q,
        {
            "_id": 0,
            "id": 1,
            "role": 1,
            "is_active": 1,
            "two_factor_enabled": 1,
            "two_factor_secret_enc": 1,
            "two_factor_backup_codes": 1,
        },
    )

    if not user:
        print("FOUND: no user matched the configured stress admin email.")
        print("HINT: double-check E2E_STRESS_ADMIN_EMAIL spelling / case + that the")
        print("      Atlas DB env (MONGO_URL/DB_NAME) matches the deployed backend.")
        return 5

    backup_count = len(user.get("two_factor_backup_codes") or [])
    print(
        f"FOUND: role={user.get('role')} active={user.get('is_active')} "
        f"two_factor_enabled={user.get('two_factor_enabled')} "
        f"has_secret={'two_factor_secret_enc' in user} "
        f"backup_codes={backup_count}"
    )

    if not apply:
        print("\nDRY-RUN — no mutation performed. Re-run with --apply to clear 2FA.")
        return 0

    res = await db.users.update_one(
        q,
        {
            "$set": {"two_factor_enabled": False},
            "$unset": {
                "two_factor_secret_enc": "",
                "two_factor_secret": "",
                "two_factor_backup_codes": "",
                "two_factor_last_used_at": "",
            },
        },
    )
    print(f"APPLY: matched={res.matched_count} modified={res.modified_count}")

    after = await db.users.find_one(
        q,
        {"_id": 0, "two_factor_enabled": 1, "two_factor_secret_enc": 1, "two_factor_backup_codes": 1},
    )
    print(
        f"AFTER: two_factor_enabled={after.get('two_factor_enabled')} "
        f"has_secret={'two_factor_secret_enc' in after} "
        f"backup_codes={len(after.get('two_factor_backup_codes') or [])}"
    )
    return 0


if __name__ == "__main__":
    apply_flag = "--apply" in sys.argv
    sys.exit(asyncio.run(main(apply=apply_flag)))
