"""Tenant-isolated, opt-in Jandarma sender configuration and dispatch.

Credentials never leave the server or fall back to plaintext storage. A saved
configuration owns this tenant's queue even while paused/unverified; neither
the generic integration nor a browser may silently send it by another path.
"""

from __future__ import annotations

import ipaddress
import json
import os
import uuid
from datetime import UTC, datetime

from core.crypto.engine import AADContext
from core.crypto.service import get_crypto_service
from core.kbs_jandarma import JandarmaError, build_request, call_jandarma

CONFIG_ID = "kbs_cloud_jandarma"


def config_query(tenant_id: str) -> dict:
    return {"tenant_id": tenant_id, "id": CONFIG_ID}


def _crypto():
    try:
        svc = get_crypto_service()
    except Exception:
        raise JandarmaError("secure_storage_unavailable") from None
    if svc.health().get("bypass_active"):
        raise JandarmaError("secure_storage_unavailable")
    key = os.environ.get("CM_MASTER_KEY_CURRENT") if svc.health().get("v2_enabled") else os.environ.get("CM_CREDENTIAL_KEY")
    if not key or len(key) < 32:
        raise JandarmaError("secure_storage_unavailable")
    return svc


def _aad(tenant_id: str) -> AADContext:
    return AADContext(tenant_id=tenant_id, provider="kbs_jandarma", context_type="credential")


def seal(tenant_id: str, credentials: dict) -> str:
    value = _crypto().encrypt(json.dumps({**credentials, "tenant_id": tenant_id}), aad=_aad(tenant_id))
    if not value.startswith(("SYR1:", "aes256gcm:")):
        raise JandarmaError("secure_storage_unavailable")
    return value


def reveal(tenant_id: str, config: dict) -> dict:
    try:
        credentials = json.loads(_crypto().decrypt(config["credentials_enc"], aad=_aad(tenant_id)))
        if credentials.pop("tenant_id") != tenant_id or config.get("tenant_id") != tenant_id:
            raise ValueError("tenant mismatch")
        return credentials
    except Exception:
        raise JandarmaError("secure_storage_unavailable") from None


def public_status(config: dict | None) -> dict:
    config = config or {}
    return {
        "configured": bool(config.get("credentials_enc")),
        "managed": bool(config),
        "authority": "jandarma",
        "enabled": bool(config.get("enabled")),
        "verified": bool(config.get("verified_revision") == config.get("revision") and config.get("revision") and config.get("verified_egress_ip") == os.environ.get("KBS_PUBLIC_EGRESS_IP", "")),
        "last_verified_at": config.get("last_verified_at"),
        "last_error": config.get("last_error"),
        "last_worker_at": config.get("last_worker_at"),
        "egress_ip": os.environ.get("KBS_PUBLIC_EGRESS_IP", ""),
        "requires_registered_ip": True,
        "requires_browser": False,
    }


async def save_config(db, tenant_id: str, data: dict, actor_id: str) -> dict:
    query = config_query(tenant_id)
    current = await db.kbs_cloud_configs.find_one(query) or {}
    credentials = reveal(tenant_id, current) if current.get("credentials_enc") else {}
    changed = False
    for key in ("user_tc", "facility_code", "password"):
        if data.get(key) and data[key] != credentials.get(key):
            credentials[key] = data[key]
            changed = True
    build_request(credentials)  # Validate before persistence; NO external call.
    revision = str(uuid.uuid4()) if changed or not current.get("revision") else current["revision"]
    enabled = data.get("enabled", False)
    if enabled and (changed or current.get("verified_revision") != revision):
        raise JandarmaError("connection_verification_required")
    if enabled and current.get("verified_egress_ip") != os.environ.get("KBS_PUBLIC_EGRESS_IP", ""):
        raise JandarmaError("connection_verification_required")
    if enabled and not data.get("live_confirmed"):
        raise JandarmaError("live_confirmation_required")
    encrypted = seal(tenant_id, credentials)
    record_id = f"kbs-cloud:{tenant_id}"
    # Establish ownership BEFORE checking for old workers. A browser that raced
    # this switch rechecks ownership after claiming and releases its lease.
    await db.kbs_cloud_configs.update_one(
        {**query, "_id": record_id},
        {"$setOnInsert": {**query, "_id": record_id, "enabled": False, "revision": None}},
        upsert=True,
    )
    if await db.kbs_reports.count_documents({"tenant_id": tenant_id, "_kind": "queue_job", "status": "in_progress"}):
        raise JandarmaError("sender_busy_retry_later")
    update = {
        "credentials_enc": encrypted,
        "revision": revision,
        "enabled": enabled,
        "updated_by": actor_id,
        "updated_at": datetime.now(UTC).isoformat(),
        "live_confirmed": bool(data.get("live_confirmed")),
    }
    if changed:
        update.update(verified_revision=None, last_verified_at=None, last_error=None)
    # Deterministic _id serializes first-time creation without a separate index.
    result = await db.kbs_cloud_configs.update_one(
        {**query, "_id": record_id, "revision": current.get("revision")},
        {"$set": update},
    )
    if not result.matched_count:
        raise JandarmaError("configuration_changed_retry_save")
    return public_status(await db.kbs_cloud_configs.find_one(query))


async def verify_config(db, tenant_id: str) -> dict:
    try:
        if not ipaddress.ip_address(os.environ.get("KBS_PUBLIC_EGRESS_IP", "")).is_global:
            raise ValueError("not public")
    except ValueError:
        raise JandarmaError("fixed_egress_ip_required") from None
    config = await db.kbs_cloud_configs.find_one(config_query(tenant_id))
    if not config:
        raise JandarmaError("configuration_required")
    try:
        await call_jandarma(reveal(tenant_id, config))
    except JandarmaError as exc:
        await db.kbs_cloud_configs.update_one(
            {**config_query(tenant_id), "revision": config["revision"]},
            {"$set": {"enabled": False, "verified_revision": None, "last_error": exc.code}},
        )
        raise
    result = await db.kbs_cloud_configs.update_one(
        {**config_query(tenant_id), "revision": config["revision"]},
        {"$set": {"verified_revision": config["revision"], "verified_egress_ip": os.environ["KBS_PUBLIC_EGRESS_IP"], "last_verified_at": datetime.now(UTC).isoformat(), "last_error": None}},
    )
    if not result.matched_count:
        raise JandarmaError("configuration_changed_retry_verification")
    return public_status(await db.kbs_cloud_configs.find_one(config_query(tenant_id)))


async def managed_tenants(db) -> list[str]:
    return [row["tenant_id"] async for row in db.kbs_cloud_configs.find({"id": CONFIG_ID}, {"tenant_id": 1})]


async def dispatch_cloud_jobs(db, *, limit: int = 50) -> dict:
    from core.kbs_dispatch import _claim_one, _complete, _handle_missing_data, _raise_alert
    from core.kbs_payload_builder import build_kbs_payload_snapshot
    from core.kbs_payload_validation import validate_kbs_payload

    summary = {"processed": 0, "sent": 0, "blocked": 0}
    if os.environ.get("KBS_AUTO_DISPATCH", "1") == "0" or os.environ.get("KBS_TEST_MODE", "0") == "1":
        return summary
    # Fair bounded batches; a paused tenant never consumes attempts.
    async for config in db.kbs_cloud_configs.find({"id": CONFIG_ID, "enabled": True}).sort("last_worker_at", 1):
        tenant_id = config["tenant_id"]
        if config.get("verified_revision") != config.get("revision") or not config.get("live_confirmed"):
            continue
        if not config.get("verified_egress_ip") or config["verified_egress_ip"] != os.environ.get("KBS_PUBLIC_EGRESS_IP"):
            await db.kbs_cloud_configs.update_one(config_query(tenant_id), {"$set": {"enabled": False, "last_error": "fixed_egress_ip_required"}})
            continue
        now = datetime.now(UTC)
        await db.kbs_cloud_configs.update_one(config_query(tenant_id), {"$set": {"last_worker_at": now.isoformat()}})
        # Expired leases may represent a request accepted just before a crash.
        # Never reclaim/re-send them without an operator checking the authority.
        async for stale in db.kbs_reports.find(
            {
                "tenant_id": tenant_id,
                "_kind": "queue_job",
                "status": "in_progress",
                "leased_until": {"$lt": now.isoformat()},
            }
        ):
            await _hold_delivery(db, stale, "delivery_unknown_check_authority", uncertain=True)
        # The Celery worker may run behind a different NAT from the API server.
        # Verify its own authority access without sending a guest record.
        try:
            await call_jandarma(reveal(tenant_id, config))
        except JandarmaError as exc:
            await db.kbs_cloud_configs.update_one(
                {**config_query(tenant_id), "revision": config["revision"]},
                {"$set": {"enabled": False, "last_error": exc.code}},
            )
            summary["blocked"] += 1
            continue
        for _ in range(min(10, max(0, limit - summary["processed"]))):
            fresh = await db.kbs_cloud_configs.find_one(config_query(tenant_id))
            if not fresh or not fresh.get("enabled") or fresh.get("revision") != config.get("revision"):
                break
            job = await _claim_one(db, datetime.now(UTC), tenant_id=tenant_id, recover_expired=False)
            if not job:
                break
            summary["processed"] += 1
            try:
                _booking, _guest, payload = await build_kbs_payload_snapshot(db, tenant_id, job["booking_id"], job.get("guest_id"))
                if not payload:
                    raise JandarmaError("source_guest_missing")
                if job.get("guest_id") and job["guest_id"] != _booking.get("guest_id"):
                    linked = await db.booking_guests.find_one({"tenant_id": tenant_id, "booking_id": job["booking_id"], "guest_id": job["guest_id"]})
                    if not linked:
                        raise JandarmaError("source_guest_missing")
                valid, missing = validate_kbs_payload(payload, job.get("action", "checkin"))
                if not valid:
                    await _handle_missing_data(db, job, missing)
                    summary["blocked"] += 1
                    continue
                job["payload"] = payload
                outcome = await call_jandarma(reveal(tenant_id, fresh), payload, job.get("action", "checkin"))
            except JandarmaError as exc:
                await _hold_delivery(db, job, exc.code, uncertain=exc.uncertain)
                await _raise_alert(db, tenant_id, kind="cloud_delivery_blocked", job=job, error=exc.code)
                summary["blocked"] += 1
                continue
            except Exception:
                await _hold_delivery(db, job, "delivery_unknown_check_authority", uncertain=True)
                summary["blocked"] += 1
                continue
            receipt = f"JANDARMA-CLOUD-{uuid.uuid4().hex}"
            await _complete(
                db,
                job,
                receipt,
                receipt_metadata={
                    "authority": "jandarma",
                    "official_reference": False,
                    "authority_response_code": outcome["code"],
                    "authority_method": outcome["method"],
                    "transport": "cloud_jandarma",
                    "payload": payload,
                },
            )
            summary["sent"] += 1
        if summary["processed"] >= limit:
            break
    return summary


async def _hold_delivery(db, job: dict, code: str, *, uncertain: bool):
    await db.kbs_reports.update_one(
        {"tenant_id": job["tenant_id"], "id": job["id"], "status": "in_progress", "worker_id": job.get("worker_id")},
        {
            "$set": {
                "status": "dead",
                "delivery_uncertain": uncertain,
                "last_error": code,
                "updated_at": datetime.now(UTC).isoformat(),
                "transport": "cloud_jandarma",
            },
            **({} if uncertain else {"$unset": {"_open_lock": ""}}),
        },
    )
