"""Idempotent operator super-admin seeder.

Provisions a dedicated super-admin account for the operator (Murat) that logs
in with EMAIL + PASSWORD. Credentials come from environment secrets:

  - OPERATOR_ADMIN_EMAIL     (required; lowercased)
  - OPERATOR_ADMIN_PASSWORD  (required)
  - OPERATOR_ADMIN_NAME      (optional; defaults to "Operator")

If either secret is missing the seeder is a NO-OP (fail-closed: no fake
account). Safe to run repeatedly:
  - missing user → created (email encrypted at rest via encrypt_user_doc,
    which also writes the _hash_email blind index used by email login).
  - existing user → role/active/tenant ensured, password NEVER overwritten.

Runs without tenant context, so it uses the raw system DB.
"""
import logging
import os
import uuid
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

DEMO_HOTEL_ID = "100001"


async def ensure_operator_admin(db=None) -> None:
    """Create or reconcile the operator super-admin. NO-OP without secrets."""
    try:
        email = (os.environ.get("OPERATOR_ADMIN_EMAIL") or "").strip().lower()
        password = os.environ.get("OPERATOR_ADMIN_PASSWORD") or ""
        if not email or not password:
            logger.info("ensure_operator_admin: secrets not set, skipping")
            return

        from core.tenant_db import get_system_db
        sys_db = get_system_db()

        # Resolve the pilot tenant (PILOT_TENANT_ID first, then demo hotel_id).
        tenant = None
        pilot_tid = os.environ.get("PILOT_TENANT_ID")
        if pilot_tid:
            tenant = await sys_db.tenants.find_one({"id": pilot_tid})
        if not tenant:
            tenant = await sys_db.tenants.find_one({"hotel_id": DEMO_HOTEL_ID})
        if not tenant:
            logger.warning("ensure_operator_admin: pilot tenant not found, skipping")
            return
        tenant_id = tenant.get("id") or tenant.get("tenant_id") or str(tenant.get("_id"))

        from core.security import hash_password
        from security.encrypted_lookup import build_user_email_query, encrypt_user_doc

        existing = await sys_db.users.find_one(build_user_email_query(email))
        if existing:
            updates = {}
            if existing.get("role") != "super_admin":
                updates["role"] = "super_admin"
            if not existing.get("is_active", False):
                updates["is_active"] = True
            if not existing.get("tenant_id"):
                updates["tenant_id"] = tenant_id
            if updates:
                key = {"id": existing["id"]} if existing.get("id") else {"_id": existing["_id"]}
                await sys_db.users.update_one(key, {"$set": updates})
                logger.info("ensure_operator_admin: reconciled existing operator (%s)", list(updates))
            else:
                logger.info("ensure_operator_admin: operator already provisioned")
            return

        now = datetime.now(UTC).isoformat()
        doc = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "agency_id": None,
            "email": email,
            "name": os.environ.get("OPERATOR_ADMIN_NAME") or "Operator",
            "role": "super_admin",
            "phone": "",
            "is_active": True,
            "email_verified": True,
            "email_verified_at": now,
            "hashed_password": hash_password(password),
            "created_at": now,
        }
        doc = encrypt_user_doc(doc)
        await sys_db.users.insert_one(doc)
        logger.info("ensure_operator_admin: created operator super_admin (tenant=%s)", tenant_id)
    except Exception as exc:
        logger.warning("ensure_operator_admin skipped: %s", exc)
