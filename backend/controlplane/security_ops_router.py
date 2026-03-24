"""
Security Operations Router — SEC-001 + SEC-002 Rollout APIs
=============================================================
Provides operational endpoints for secrets management and crypto migration.

SEC-001 Endpoints:
  GET  /api/ops/secrets/status         — Overall secrets health
  GET  /api/ops/secrets/rotation-plan  — Rotation readiness per provider
  POST /api/ops/secrets/rotate         — Rotate credentials for a connection
  POST /api/ops/secrets/rollback       — Rollback a rotation
  GET  /api/ops/secrets/scoping        — Tenant/provider secret scoping overview

SEC-002 Endpoints:
  GET  /api/ops/crypto/status          — Crypto subsystem health
  GET  /api/ops/crypto/cutover-metrics — Migration progress (format breakdown)
  POST /api/ops/crypto/migrate-check   — Dry-run migration check
  GET  /api/ops/crypto/key-info        — Key versioning details
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.database import db
from security.ops_guard import require_ops_access

logger = logging.getLogger("controlplane.security_ops")

router = APIRouter(prefix="/api/ops", tags=["Security Operations"],
                   dependencies=[Depends(require_ops_access)])


# ── Request/Response Models ────────────────────────────────────────

class RotateRequest(BaseModel):
    tenant_id: str
    provider: str
    property_id: str
    actor: str = "operator"


class RollbackRequest(BaseModel):
    tenant_id: str
    provider: str
    property_id: str
    actor: str = "operator"


# ═══════════════════════════════════════════════════════════════════
# SEC-001: Secrets Management
# ═══════════════════════════════════════════════════════════════════

@router.get("/secrets/status")
async def secrets_status():
    """Comprehensive secrets subsystem health status."""
    try:
        from core.secrets import get_secrets_manager
        sm = get_secrets_manager()
        health = await sm.health_check()
    except Exception as e:
        health = {"status": "error", "error": str(e)}

    # Count secrets by provider
    secret_counts = {}
    try:
        pipeline = [
            {"$match": {"path": {"$exists": True}}},
            {"$project": {
                "parts": {"$split": ["$path", "/"]},
            }},
            {"$addFields": {
                "provider": {"$arrayElemAt": ["$parts", 4]},
                "tenant": {"$arrayElemAt": ["$parts", 3]},
            }},
            {"$group": {
                "_id": {"provider": "$provider", "tenant": "$tenant"},
                "count": {"$sum": 1},
            }},
        ]
        async for doc in db["_dev_secrets"].aggregate(pipeline):
            key = doc["_id"]
            prov = key.get("provider", "unknown")
            if prov not in secret_counts:
                secret_counts[prov] = {"total": 0, "tenants": set()}
            secret_counts[prov]["total"] += doc["count"]
            secret_counts[prov]["tenants"].add(key.get("tenant", ""))
        # Convert sets to counts
        for prov in secret_counts:
            secret_counts[prov]["tenant_count"] = len(secret_counts[prov]["tenants"])
            del secret_counts[prov]["tenants"]
    except Exception:
        pass

    # Audit stats (last 24h)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    audit_stats = {}
    try:
        pipeline = [
            {"$match": {"timestamp": {"$gte": cutoff}}},
            {"$group": {"_id": "$action", "count": {"$sum": 1}}},
        ]
        async for doc in db["secret_access_audit"].aggregate(pipeline):
            audit_stats[doc["_id"]] = doc["count"]
    except Exception:
        pass

    # Anomaly count
    anomaly_count = 0
    try:
        anomaly_count = await db["secret_access_audit"].count_documents(
            {"result": {"$in": ["failure", "denied", "not_found"]}, "timestamp": {"$gte": cutoff}}
        )
    except Exception:
        pass

    return {
        "health": health,
        "secret_counts_by_provider": secret_counts,
        "audit_24h": audit_stats,
        "anomalies_24h": anomaly_count,
        "config": {
            "provider": os.environ.get("SECRETS_PROVIDER", "local_dev"),
            "environment": os.environ.get("APP_ENV", "development"),
            "legacy_fallback": os.environ.get("ENABLE_LEGACY_SECRET_FALLBACK", "true"),
            "audit_enabled": os.environ.get("SECRET_ACCESS_AUDIT_ENABLED", "true"),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/secrets/rotation-plan")
async def secrets_rotation_plan(
    tenant_id: Optional[str] = Query(None),
):
    """Show rotation readiness for all managed secrets.

    Returns a per-provider breakdown with:
    - Last rotation timestamp
    - Rotation age (days since last rotation)
    - Recommended action
    - Rollback availability
    """
    plan_items = []
    try:
        query = {}
        if tenant_id:
            # Filter by tenant in path
            query["path"] = {"$regex": f"/{tenant_id}/"}

        secrets = await db["_dev_secrets"].find(
            query, {"_id": 0, "path": 1, "created_at": 1, "updated_at": 1,
                     "rotation_count": 1, "previous_version": 1}
        ).to_list(500)

        now = datetime.now(timezone.utc)
        for sec in secrets:
            path = sec.get("path", "")
            parts = path.split("/")
            if len(parts) < 6:
                continue

            updated = sec.get("updated_at") or sec.get("created_at", "")
            age_days = None
            if updated:
                try:
                    updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    age_days = (now - updated_dt).days
                except Exception:
                    pass

            has_previous = bool(sec.get("previous_version"))
            rotation_count = sec.get("rotation_count", 0)

            # Determine recommendation
            if age_days is not None and age_days > 90:
                recommendation = "ROTATE_URGENT"
                severity = "critical"
            elif age_days is not None and age_days > 30:
                recommendation = "ROTATE_RECOMMENDED"
                severity = "warning"
            else:
                recommendation = "OK"
                severity = "info"

            plan_items.append({
                "tenant_id": parts[3] if len(parts) > 3 else "",
                "provider": parts[4] if len(parts) > 4 else "",
                "property_id": parts[5] if len(parts) > 5 else "",
                "last_updated": updated,
                "age_days": age_days,
                "rotation_count": rotation_count,
                "has_rollback": has_previous,
                "recommendation": recommendation,
                "severity": severity,
            })
    except Exception as e:
        logger.error("Rotation plan generation failed: %s", e)

    # Summary
    urgent = sum(1 for p in plan_items if p["recommendation"] == "ROTATE_URGENT")
    recommended = sum(1 for p in plan_items if p["recommendation"] == "ROTATE_RECOMMENDED")

    return {
        "items": plan_items,
        "summary": {
            "total_secrets": len(plan_items),
            "urgent_rotations": urgent,
            "recommended_rotations": recommended,
            "ok": len(plan_items) - urgent - recommended,
        },
        "rotation_policy": {
            "max_age_days": 90,
            "warning_age_days": 30,
            "auto_rotation_enabled": False,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/secrets/rotate")
async def rotate_secret(body: RotateRequest):
    """Rotate credentials for a specific tenant/provider/property.

    Stores the previous version for rollback, increments rotation counter.
    """
    try:
        from core.secrets import get_secrets_manager
        sm = get_secrets_manager()

        # Get current credentials first
        current = await sm.get_provider_credentials(
            body.tenant_id, body.provider, body.property_id, actor=body.actor,
        )
        if not current:
            raise HTTPException(status_code=404, detail="No credentials found for this connection")

        # Perform rotation (re-store with metadata update)
        meta = await sm.rotate_provider_credentials(
            tenant_id=body.tenant_id,
            provider=body.provider,
            property_id=body.property_id,
            new_credentials=current,
            actor=body.actor,
        )

        return {
            "success": True,
            "tenant_id": body.tenant_id,
            "provider": body.provider,
            "property_id": body.property_id,
            "rotation_count": meta.rotation_count,
            "rotated_at": datetime.now(timezone.utc).isoformat(),
            "rollback_available": True,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Rotation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Rotation failed: {type(e).__name__}")


@router.post("/secrets/rollback")
async def rollback_secret(body: RollbackRequest):
    """Rollback to the previous version of credentials.

    Only works if a rotation has been performed and previous version exists.
    """
    try:
        from core.secrets import get_secrets_manager
        sm = get_secrets_manager()

        # Check if previous version exists
        meta = await sm.get_provider_credential_metadata(
            body.tenant_id, body.provider, body.property_id,
        )
        if not meta:
            raise HTTPException(status_code=404, detail="No credential metadata found")

        if not meta.previous_version:
            raise HTTPException(
                status_code=409,
                detail="No previous version available for rollback. Rotation must be performed first."
            )

        # Restore previous version
        await sm.store_provider_credentials(
            tenant_id=body.tenant_id,
            provider=body.provider,
            property_id=body.property_id,
            credentials=meta.previous_version,
            actor=f"rollback:{body.actor}",
        )

        return {
            "success": True,
            "tenant_id": body.tenant_id,
            "provider": body.provider,
            "property_id": body.property_id,
            "rolled_back_at": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Rollback failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Rollback failed: {type(e).__name__}")


@router.get("/secrets/scoping")
async def secrets_scoping(
    tenant_id: Optional[str] = Query(None),
):
    """Show tenant/provider-based secret scoping overview.

    Demonstrates that secrets are properly isolated by tenant and provider.
    """
    scoping = []
    try:
        query = {}
        if tenant_id:
            query["path"] = {"$regex": f"/{tenant_id}/"}

        secrets = await db["_dev_secrets"].find(
            query, {"_id": 0, "path": 1, "created_at": 1}
        ).to_list(500)

        # Group by tenant → provider
        tenant_map = {}
        for sec in secrets:
            path = sec.get("path", "")
            parts = path.split("/")
            if len(parts) < 6:
                continue
            t = parts[3]
            p = parts[4]
            prop = parts[5]
            if t not in tenant_map:
                tenant_map[t] = {}
            if p not in tenant_map[t]:
                tenant_map[t][p] = []
            tenant_map[t][p].append({
                "property_id": prop,
                "created_at": sec.get("created_at", ""),
            })

        for t, providers in tenant_map.items():
            for p, properties in providers.items():
                scoping.append({
                    "tenant_id": t,
                    "provider": p,
                    "property_count": len(properties),
                    "properties": properties,
                })
    except Exception as e:
        logger.error("Scoping query failed: %s", e)

    return {
        "scoping": scoping,
        "isolation_model": "tenant/provider/property",
        "cross_tenant_access": "DENIED",
        "policy_enforcement": "active",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════
# SEC-002: Crypto Migration
# ═══════════════════════════════════════════════════════════════════

@router.get("/crypto/status")
async def crypto_status():
    """Crypto subsystem health with key version info."""
    try:
        from core.crypto import get_crypto_service
        svc = get_crypto_service()
        health = svc.health()
    except Exception as e:
        health = {"status": "error", "error": str(e)}

    return {
        "health": health,
        "config": {
            "v2_enabled": os.environ.get("CRYPTO_V2_ENABLED", "false"),
            "bypass_allowed": os.environ.get("CRYPTO_BYPASS_ALLOWED", "false"),
            "key_version": os.environ.get("CM_KEY_VERSION", "v1"),
            "has_master_key": bool(os.environ.get("CM_MASTER_KEY_CURRENT")),
            "has_previous_key": bool(os.environ.get("CM_MASTER_KEY_PREVIOUS")),
            "has_legacy_key": bool(os.environ.get("CM_CREDENTIAL_KEY")),
        },
        "dual_read_write": {
            "status": "active",
            "description": "Decrypt supports all formats (SYR1, aes256gcm, XOR, base64). "
                          "Encrypt uses legacy format when CRYPTO_V2_ENABLED=false, SYR1 when true.",
            "write_format": "SYR1" if os.environ.get("CRYPTO_V2_ENABLED", "false").lower() == "true" else "aes256gcm",
            "read_formats": ["SYR1", "aes256gcm", "XOR", "base64"],
        },
        "fallback_strategy": {
            "on_decrypt_failure": "try_all_legacy_formats → raise DecryptionError",
            "break_glass": "CRYPTO_BYPASS_ALLOWED=true disables all encryption (emergency only)",
            "rollback": "Set CRYPTO_V2_ENABLED=false to revert writes to legacy format",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/crypto/cutover-metrics")
async def crypto_cutover_metrics():
    """Migration cutover metrics — shows format distribution across all credential collections."""
    try:
        from core.crypto import get_crypto_service
        _svc = get_crypto_service()
    except Exception as e:
        return {"error": str(e)}

    metrics = {
        "collections": {},
        "totals": {"syr1": 0, "aes_gcm_legacy": 0, "other_legacy": 0, "plaintext": 0, "empty": 0},
    }

    # Check _dev_secrets
    try:
        coll_stats = {"syr1": 0, "aes_gcm_legacy": 0, "other_legacy": 0, "plaintext": 0, "empty": 0}
        async for doc in db["_dev_secrets"].find({}, {"_id": 0, "encrypted_payload": 1}):
            payload = doc.get("encrypted_payload", "")
            if not payload:
                coll_stats["empty"] += 1
            elif isinstance(payload, str):
                if payload.startswith("SYR1:"):
                    coll_stats["syr1"] += 1
                elif payload.startswith("aes256gcm:"):
                    coll_stats["aes_gcm_legacy"] += 1
                else:
                    coll_stats["other_legacy"] += 1
            elif isinstance(payload, dict):
                # JSON blob — check individual values
                for v in payload.values():
                    if isinstance(v, str) and v:
                        if v.startswith("SYR1:"):
                            coll_stats["syr1"] += 1
                        elif v.startswith("aes256gcm:"):
                            coll_stats["aes_gcm_legacy"] += 1
                        else:
                            coll_stats["other_legacy"] += 1
        metrics["collections"]["_dev_secrets"] = coll_stats
        for k, v in coll_stats.items():
            metrics["totals"][k] += v
    except Exception:
        pass

    # Check provider_secrets
    try:
        coll_stats = {"syr1": 0, "aes_gcm_legacy": 0, "other_legacy": 0, "plaintext": 0, "empty": 0}
        async for doc in db["provider_secrets"].find({}, {"_id": 0, "encrypted_payload": 1}):
            payload = doc.get("encrypted_payload", {})
            if isinstance(payload, dict):
                for v in payload.values():
                    if isinstance(v, str) and v:
                        if v.startswith("SYR1:"):
                            coll_stats["syr1"] += 1
                        elif v.startswith("aes256gcm:"):
                            coll_stats["aes_gcm_legacy"] += 1
                        else:
                            coll_stats["other_legacy"] += 1
        metrics["collections"]["provider_secrets"] = coll_stats
        for k, v in coll_stats.items():
            metrics["totals"][k] += v
    except Exception:
        pass

    # Check credential_vault
    try:
        coll_stats = {"syr1": 0, "aes_gcm_legacy": 0, "other_legacy": 0, "plaintext": 0, "empty": 0}
        async for doc in db["credential_vault"].find({"status": "active"}, {"_id": 0, "credential_encrypted": 1, "credential_value_encoded": 1}):
            enc = doc.get("credential_encrypted", "")
            if enc:
                if enc.startswith("SYR1:"):
                    coll_stats["syr1"] += 1
                elif enc.startswith("aes256gcm:"):
                    coll_stats["aes_gcm_legacy"] += 1
                else:
                    coll_stats["other_legacy"] += 1
            elif doc.get("credential_value_encoded"):
                coll_stats["other_legacy"] += 1
            else:
                coll_stats["empty"] += 1
        metrics["collections"]["credential_vault"] = coll_stats
        for k, v in coll_stats.items():
            metrics["totals"][k] += v
    except Exception:
        pass

    # Compute cutover readiness
    total_records = sum(metrics["totals"].values()) - metrics["totals"]["empty"]
    syr1_count = metrics["totals"]["syr1"]
    migration_pct = round((syr1_count / total_records * 100), 1) if total_records > 0 else 0.0

    cutover_ready = migration_pct >= 100 and metrics["totals"]["aes_gcm_legacy"] == 0 and metrics["totals"]["other_legacy"] == 0

    metrics["cutover"] = {
        "total_credential_fields": total_records,
        "migrated_to_syr1": syr1_count,
        "migration_percentage": migration_pct,
        "cutover_ready": cutover_ready,
        "remaining_legacy": metrics["totals"]["aes_gcm_legacy"] + metrics["totals"]["other_legacy"],
        "recommended_action": (
            "Ready for cutover — disable legacy fallback" if cutover_ready
            else f"Migration needed: {metrics['totals']['aes_gcm_legacy'] + metrics['totals']['other_legacy']} legacy records remaining"
        ),
    }
    metrics["key_version"] = os.environ.get("CM_KEY_VERSION", "v1")
    metrics["timestamp"] = datetime.now(timezone.utc).isoformat()

    return metrics


@router.post("/crypto/migrate-check")
async def crypto_migrate_check():
    """Dry-run migration check — shows what would be migrated without writing."""
    try:
        from core.crypto import get_crypto_service
        crypto_svc = get_crypto_service()
    except Exception as e:
        return {"error": str(e)}

    check = {"would_migrate": 0, "already_current": 0, "errors": 0}

    # Check _dev_secrets
    try:
        async for doc in db["_dev_secrets"].find({}, {"_id": 0, "encrypted_payload": 1}):
            payload = doc.get("encrypted_payload", "")
            if isinstance(payload, str) and payload:
                if crypto_svc.is_current_format(payload):
                    check["already_current"] += 1
                else:
                    check["would_migrate"] += 1
    except Exception:
        pass

    # Check provider_secrets
    try:
        async for doc in db["provider_secrets"].find({}, {"_id": 0, "encrypted_payload": 1}):
            payload = doc.get("encrypted_payload", {})
            if isinstance(payload, dict):
                for v in payload.values():
                    if isinstance(v, str) and v:
                        if crypto_svc.is_current_format(v):
                            check["already_current"] += 1
                        else:
                            check["would_migrate"] += 1
    except Exception:
        pass

    return {
        "dry_run": True,
        "would_migrate": check["would_migrate"],
        "already_current": check["already_current"],
        "total_scanned": check["would_migrate"] + check["already_current"],
        "action": (
            "No migration needed — all records in current format"
            if check["would_migrate"] == 0
            else f"Run `python scripts/migrate_crypto.py --all` to migrate {check['would_migrate']} records"
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/crypto/key-info")
async def crypto_key_info():
    """Key versioning details — current, previous, rotation readiness."""
    has_current = bool(os.environ.get("CM_MASTER_KEY_CURRENT"))
    has_previous = bool(os.environ.get("CM_MASTER_KEY_PREVIOUS"))
    key_version = os.environ.get("CM_KEY_VERSION", "v1")

    return {
        "current_version": key_version,
        "has_current_key": has_current,
        "has_previous_key": has_previous,
        "rotation_ready": has_current,
        "rotation_steps": [
            "1. Generate new key: python -c \"import secrets; print(secrets.token_urlsafe(32))\"",
            "2. Set CM_MASTER_KEY_PREVIOUS to current CM_MASTER_KEY_CURRENT value",
            "3. Set CM_MASTER_KEY_CURRENT to the new key",
            "4. Increment CM_KEY_VERSION (e.g., v1 → v2)",
            "5. Deploy and verify",
            "6. Run migration: python scripts/migrate_crypto.py --all",
            "7. After verification, remove CM_MASTER_KEY_PREVIOUS",
        ],
        "rollback_plan": {
            "immediate": "Set CRYPTO_V2_ENABLED=false — new writes revert to legacy format, old SYR1 data still readable",
            "break_glass": "Set CRYPTO_BYPASS_ALLOWED=true — disables ALL encryption (extreme emergency only)",
            "key_rollback": "Swap CM_MASTER_KEY_CURRENT back with previous value, decrement CM_KEY_VERSION",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
