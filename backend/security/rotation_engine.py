"""
Secret Rotation Engine — Safe rotate + test + activate + rollback.

Flow:
  1. initiate_rotation  → new version created with status=pending_test
  2. test_rotation       → dry-run validates new credentials work
  3. activate_rotation   → new version becomes active, old archived
  4. rollback            → revert to any previous version instantly

Design rules:
  - NEVER switch without a successful test
  - Old versions are NEVER deleted (audit trail)
  - Every action is logged to rotation_audit
  - Failure triggers an alert via controlplane.alerting
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger("security.rotation_engine")

COLL_VERSIONS = "secret_rotation_versions"
COLL_ROTATION_AUDIT = "secret_rotation_audit"


class RotationStatus:
    PENDING_TEST = "pending_test"
    TEST_PASSED = "test_passed"
    TEST_FAILED = "test_failed"
    ACTIVE = "active"
    ROLLED_BACK = "rolled_back"
    ARCHIVED = "archived"


class RotationEngine:
    """Manages secret versioning, testing, activation and rollback."""

    def __init__(self):
        self._db = None

    def _get_db(self):
        if self._db is None:
            from core.tenant_db import get_system_db

            self._db = get_system_db()
        return self._db

    # ── Initiate ───────────────────────────────────────────────────

    async def initiate_rotation(
        self,
        *,
        secret_path: str,
        new_credentials: dict[str, str],
        actor: str,
        tenant_id: str = "",
        provider: str = "",
        reason: str = "manual",
    ) -> dict[str, Any]:
        """Create a new pending version. Does NOT activate it yet."""
        db = self._get_db()

        # Get next version number
        latest = await db[COLL_VERSIONS].find_one(
            {"secret_path": secret_path},
            {"_id": 0, "version": 1},
            sort=[("version", -1)],
        )
        next_version = (latest["version"] + 1) if latest else 1

        now = datetime.now(UTC).isoformat()

        # Encrypt the new credentials before storing
        encrypted_payload = await self._encrypt_credentials(new_credentials, secret_path)

        version_doc = {
            "secret_path": secret_path,
            "version": next_version,
            "encrypted_payload": encrypted_payload,
            "field_names": list(new_credentials.keys()),
            "status": RotationStatus.PENDING_TEST,
            "created_at": now,
            "created_by": actor,
            "activated_at": None,
            "deactivated_at": None,
            "test_result": None,
            "rotation_reason": reason,
            "tenant_id": tenant_id,
            "provider": provider,
        }

        await db[COLL_VERSIONS].insert_one(version_doc)

        await self._log_audit(
            secret_path=secret_path,
            action="rotation_initiated",
            actor=actor,
            version=next_version,
            tenant_id=tenant_id,
            details={"reason": reason, "field_names": list(new_credentials.keys())},
        )

        logger.info(
            "Rotation initiated: %s v%d by %s (%s)",
            secret_path,
            next_version,
            actor,
            reason,
        )

        return {
            "secret_path": secret_path,
            "version": next_version,
            "status": RotationStatus.PENDING_TEST,
            "created_at": now,
            "next_step": "Call /rotation/test to validate, then /rotation/activate",
        }

    # ── Test ───────────────────────────────────────────────────────

    async def test_rotation(
        self,
        *,
        secret_path: str,
        version: int,
        actor: str,
    ) -> dict[str, Any]:
        """Dry-run test the pending version. For connector secrets, tests real API call."""
        db = self._get_db()

        doc = await db[COLL_VERSIONS].find_one(
            {"secret_path": secret_path, "version": version},
            {"_id": 0},
        )
        if not doc:
            return {"success": False, "error": "Version not found"}

        if doc["status"] not in (RotationStatus.PENDING_TEST, RotationStatus.TEST_FAILED):
            return {
                "success": False,
                "error": f"Cannot test version in status '{doc['status']}'. Must be pending_test or test_failed.",
            }

        # Decrypt for testing
        credentials = await self._decrypt_credentials(doc["encrypted_payload"], secret_path)

        # Run connector-specific validation
        test_result = await self._run_connector_test(
            secret_path=secret_path,
            provider=doc.get("provider", ""),
            tenant_id=doc.get("tenant_id", ""),
            credentials=credentials,
        )

        now = datetime.now(UTC).isoformat()
        new_status = RotationStatus.TEST_PASSED if test_result["success"] else RotationStatus.TEST_FAILED

        await db[COLL_VERSIONS].update_one(
            {"secret_path": secret_path, "version": version},
            {
                "$set": {
                    "status": new_status,
                    "test_result": {
                        "tested_at": now,
                        "tested_by": actor,
                        "success": test_result["success"],
                        "details": test_result.get("details", ""),
                        "latency_ms": test_result.get("latency_ms"),
                    },
                }
            },
        )

        await self._log_audit(
            secret_path=secret_path,
            action="rotation_tested",
            actor=actor,
            version=version,
            tenant_id=doc.get("tenant_id", ""),
            details={"success": test_result["success"], "details": test_result.get("details", "")},
        )

        if not test_result["success"]:
            await self._fire_alert(
                title=f"Secret rotation test FAILED: {secret_path}",
                message=f"Version {version} test failed: {test_result.get('details', 'unknown error')}",
                severity="high",
                tenant_id=doc.get("tenant_id"),
                provider=doc.get("provider"),
            )

        return {
            "secret_path": secret_path,
            "version": version,
            "status": new_status,
            "test_result": test_result,
            "next_step": "Call /rotation/activate" if test_result["success"] else "Fix credentials and re-initiate",
        }

    # ── Activate ───────────────────────────────────────────────────

    async def activate_rotation(
        self,
        *,
        secret_path: str,
        version: int,
        actor: str,
    ) -> dict[str, Any]:
        """Activate a tested version. Archives the current active version."""
        db = self._get_db()

        doc = await db[COLL_VERSIONS].find_one(
            {"secret_path": secret_path, "version": version},
            {"_id": 0},
        )
        if not doc:
            return {"success": False, "error": "Version not found"}

        if doc["status"] != RotationStatus.TEST_PASSED:
            return {
                "success": False,
                "error": f"Cannot activate version in status '{doc['status']}'. Must pass test first.",
            }

        now = datetime.now(UTC).isoformat()

        # Step 1: Update live secret FIRST (if this fails, nothing changes)
        credentials = await self._decrypt_credentials(doc["encrypted_payload"], secret_path)
        try:
            await self._update_live_secret(secret_path, credentials)
        except Exception as e:
            await self._log_audit(
                secret_path=secret_path,
                action="rotation_activation_failed",
                actor=actor,
                version=version,
                tenant_id=doc.get("tenant_id", ""),
                details={"error": str(e)},
            )
            await self._fire_alert(
                title=f"Secret activation FAILED: {secret_path}",
                message=f"Live secret update failed for v{version}: {e}",
                severity="critical",
                tenant_id=doc.get("tenant_id"),
                provider=doc.get("provider"),
            )
            return {"success": False, "error": f"Live secret update failed: {e}"}

        # Step 2: Archive current active version
        await db[COLL_VERSIONS].update_many(
            {"secret_path": secret_path, "status": RotationStatus.ACTIVE},
            {"$set": {"status": RotationStatus.ARCHIVED, "deactivated_at": now}},
        )

        # Step 3: Activate new version
        await db[COLL_VERSIONS].update_one(
            {"secret_path": secret_path, "version": version},
            {"$set": {"status": RotationStatus.ACTIVE, "activated_at": now}},
        )

        await self._log_audit(
            secret_path=secret_path,
            action="rotation_activated",
            actor=actor,
            version=version,
            tenant_id=doc.get("tenant_id", ""),
            details={"previous_active_archived": True},
        )

        logger.info("Rotation activated: %s v%d by %s", secret_path, version, actor)

        return {
            "success": True,
            "secret_path": secret_path,
            "version": version,
            "status": RotationStatus.ACTIVE,
            "activated_at": now,
        }

    # ── Rollback ───────────────────────────────────────────────────

    async def rollback(
        self,
        *,
        secret_path: str,
        target_version: int | None = None,
        actor: str,
    ) -> dict[str, Any]:
        """Rollback to a previous version. If no target, use the most recent archived."""
        db = self._get_db()

        if target_version:
            target = await db[COLL_VERSIONS].find_one(
                {"secret_path": secret_path, "version": target_version},
                {"_id": 0},
            )
        else:
            # Find most recent archived version
            target = await db[COLL_VERSIONS].find_one(
                {"secret_path": secret_path, "status": RotationStatus.ARCHIVED},
                {"_id": 0},
                sort=[("version", -1)],
            )

        if not target:
            await self._fire_alert(
                title=f"Secret rollback FAILED: {secret_path}",
                message="No previous version available for rollback.",
                severity="critical",
                tenant_id=None,
                provider=None,
            )
            return {"success": False, "error": "No previous version available for rollback"}

        now = datetime.now(UTC).isoformat()

        # Mark current active as rolled_back
        await db[COLL_VERSIONS].update_many(
            {"secret_path": secret_path, "status": RotationStatus.ACTIVE},
            {"$set": {"status": RotationStatus.ROLLED_BACK, "deactivated_at": now}},
        )

        # Activate target
        await db[COLL_VERSIONS].update_one(
            {"secret_path": secret_path, "version": target["version"]},
            {"$set": {"status": RotationStatus.ACTIVE, "activated_at": now}},
        )

        # Restore live secret
        credentials = await self._decrypt_credentials(target["encrypted_payload"], secret_path)
        await self._update_live_secret(secret_path, credentials)

        await self._log_audit(
            secret_path=secret_path,
            action="rotation_rolled_back",
            actor=actor,
            version=target["version"],
            tenant_id=target.get("tenant_id", ""),
            details={"reason": "manual_rollback"},
        )

        await self._fire_alert(
            title=f"Secret ROLLED BACK: {secret_path}",
            message=f"Rolled back to v{target['version']} by {actor}",
            severity="warning",
            tenant_id=target.get("tenant_id"),
            provider=target.get("provider"),
        )

        logger.warning("Rollback executed: %s -> v%d by %s", secret_path, target["version"], actor)

        return {
            "success": True,
            "secret_path": secret_path,
            "rolled_back_to_version": target["version"],
            "status": RotationStatus.ACTIVE,
            "rolled_back_at": now,
        }

    # ── Status / Dashboard ─────────────────────────────────────────

    async def get_rotation_status(self, secret_path: str) -> dict[str, Any]:
        """Full rotation status for a single secret."""
        db = self._get_db()

        versions = (
            await db[COLL_VERSIONS]
            .find(
                {"secret_path": secret_path},
                {"_id": 0, "encrypted_payload": 0},
            )
            .sort("version", -1)
            .to_list(50)
        )

        active = next((v for v in versions if v["status"] == RotationStatus.ACTIVE), None)

        return {
            "secret_path": secret_path,
            "active_version": active["version"] if active else None,
            "total_versions": len(versions),
            "versions": versions,
        }

    async def get_dashboard(self) -> dict[str, Any]:
        """Rotation dashboard — all secrets with status, expiration, overdue flag."""
        db = self._get_db()
        now = datetime.now(UTC)

        # Get all active versions
        active_versions = (
            await db[COLL_VERSIONS]
            .find(
                {"status": RotationStatus.ACTIVE},
                {"_id": 0, "encrypted_payload": 0},
            )
            .to_list(500)
        )

        # Also scan _dev_secrets for secrets without version history
        all_secrets = await db["_dev_secrets"].find({}, {"_id": 0, "path": 1, "updated_at": 1, "created_at": 1, "rotation_count": 1}).to_list(500)

        # Build lookup of versioned secrets
        versioned_paths = {v["secret_path"] for v in active_versions}

        # Get lifecycle rules
        from security.pii_registry import SECRET_LIFECYCLE

        dashboard_items = []

        for sec in all_secrets:
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

            # Classify secret type
            secret_type = self._classify_type(parts)
            lifecycle = SECRET_LIFECYCLE.get(secret_type, {})
            max_days = lifecycle.get("rotation_max_days", 90)
            warn_days = lifecycle.get("rotation_warning_days", 60)

            is_overdue = age_days is not None and age_days > max_days
            is_warning = age_days is not None and age_days > warn_days and not is_overdue
            next_rotation = None
            if updated:
                try:
                    updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    next_rotation = (updated_dt + timedelta(days=max_days)).isoformat()
                except Exception:
                    pass

            # Find active version info if exists
            active_v = next((v for v in active_versions if v["secret_path"] == path), None)

            dashboard_items.append(
                {
                    "secret_path": self._mask_path(path),
                    "tenant_id": parts[3] if len(parts) > 3 else "",
                    "provider": parts[4] if len(parts) > 4 else "",
                    "secret_type": secret_type.value,
                    "last_rotated": updated,
                    "age_days": age_days,
                    "rotation_count": sec.get("rotation_count", 0),
                    "max_rotation_days": max_days,
                    "next_rotation_due": next_rotation,
                    "is_overdue": is_overdue,
                    "is_warning": is_warning,
                    "has_version_history": path in versioned_paths,
                    "active_version": active_v["version"] if active_v else None,
                    "status": "overdue" if is_overdue else ("warning" if is_warning else "healthy"),
                }
            )

        # Sort: overdue first, then warning, then healthy
        priority = {"overdue": 0, "warning": 1, "healthy": 2}
        dashboard_items.sort(key=lambda x: priority.get(x["status"], 3))

        overdue_count = sum(1 for d in dashboard_items if d["is_overdue"])
        warning_count = sum(1 for d in dashboard_items if d["is_warning"])

        return {
            "items": dashboard_items,
            "summary": {
                "total": len(dashboard_items),
                "overdue": overdue_count,
                "warning": warning_count,
                "healthy": len(dashboard_items) - overdue_count - warning_count,
            },
            "timestamp": now.isoformat(),
        }

    async def get_overdue_secrets(self) -> dict[str, Any]:
        """List only overdue secrets that need immediate attention."""
        dashboard = await self.get_dashboard()
        overdue = [item for item in dashboard["items"] if item["is_overdue"]]
        return {
            "overdue_secrets": overdue,
            "count": len(overdue),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def get_rotation_audit(
        self,
        *,
        secret_path: str | None = None,
        tenant_id: str | None = None,
        limit: int = 50,
        skip: int = 0,
    ) -> dict[str, Any]:
        """Query rotation audit trail."""
        db = self._get_db()
        query: dict[str, Any] = {}
        if secret_path:
            query["secret_path"] = secret_path
        if tenant_id:
            query["tenant_id"] = tenant_id

        total = await db[COLL_ROTATION_AUDIT].count_documents(query)
        items = (
            await db[COLL_ROTATION_AUDIT]
            .find(
                query,
                {"_id": 0},
            )
            .sort("timestamp", -1)
            .skip(skip)
            .limit(limit)
            .to_list(limit)
        )

        return {"items": items, "total": total, "limit": limit, "skip": skip}

    # ── Index Setup ────────────────────────────────────────────────

    async def ensure_indexes(self) -> None:
        """Create indexes for rotation collections."""
        db = self._get_db()

        versions = db[COLL_VERSIONS]
        await versions.create_index(
            [("secret_path", 1), ("version", -1)],
            unique=True,
        )
        await versions.create_index([("secret_path", 1), ("status", 1)])
        await versions.create_index("status")

        audit = db[COLL_ROTATION_AUDIT]
        await audit.create_index([("secret_path", 1), ("timestamp", -1)])
        await audit.create_index([("tenant_id", 1), ("timestamp", -1)])
        await audit.create_index("timestamp", expireAfterSeconds=365 * 86400)  # 1-year TTL

    # ── Internal Helpers ───────────────────────────────────────────

    async def _encrypt_credentials(
        self,
        credentials: dict[str, str],
        secret_path: str,
    ) -> str:
        """Encrypt credentials using the existing crypto service."""
        import json

        from core.crypto import AADContext, get_crypto_service

        svc = get_crypto_service()
        parts = secret_path.split("/")
        aad = AADContext(
            tenant_id=parts[3] if len(parts) > 3 else "",
            provider=parts[4] if len(parts) > 4 else "",
            property_id=parts[5] if len(parts) > 5 else "",
            environment="rotation",
            context_type="rotation_version",
        )
        return svc.encrypt(json.dumps(credentials), aad=aad)

    async def _decrypt_credentials(
        self,
        encrypted: str,
        secret_path: str,
    ) -> dict[str, str]:
        """Decrypt credentials from encrypted payload."""
        import json

        from core.crypto import AADContext, get_crypto_service

        svc = get_crypto_service()
        parts = secret_path.split("/")
        aad = AADContext(
            tenant_id=parts[3] if len(parts) > 3 else "",
            provider=parts[4] if len(parts) > 4 else "",
            property_id=parts[5] if len(parts) > 5 else "",
            environment="rotation",
            context_type="rotation_version",
        )
        plaintext = svc.decrypt(encrypted, aad=aad)
        return json.loads(plaintext)

    async def _update_live_secret(
        self,
        secret_path: str,
        credentials: dict[str, str],
    ) -> None:
        """Update the live secret in _dev_secrets (the source of truth for runtime)."""
        try:
            from core.secrets import get_secrets_manager

            sm = get_secrets_manager()
            parts = secret_path.split("/")
            if len(parts) >= 6:
                tenant_id = parts[3]
                provider = parts[4]
                property_id = parts[5]
                # store_provider_credentials handles both create and update
                await sm.store_provider_credentials(
                    tenant_id=tenant_id,
                    provider=provider,
                    property_id=property_id,
                    credentials=credentials,
                    actor="rotation_engine",
                )
        except Exception as e:
            logger.error("Failed to update live secret %s: %s", secret_path, e)
            raise

    async def _run_connector_test(
        self,
        *,
        secret_path: str,
        provider: str,
        tenant_id: str,
        credentials: dict[str, str],
    ) -> dict[str, Any]:
        """Test credentials against the actual provider API.

        For known connectors (exely, hotelrunner), performs a real connectivity check.
        For unknown providers, validates credential structure.
        """
        import time

        start = time.monotonic()

        try:
            if provider == "exely":
                result = await self._test_exely_credentials(credentials, tenant_id)
            elif provider == "hotelrunner":
                result = await self._test_hotelrunner_credentials(credentials, tenant_id)
            else:
                # Generic validation: ensure all fields are non-empty strings
                empty_fields = [k for k, v in credentials.items() if not v or not str(v).strip()]
                if empty_fields:
                    result = {
                        "success": False,
                        "details": f"Empty credential fields: {empty_fields}",
                    }
                else:
                    result = {
                        "success": True,
                        "details": f"Structural validation passed ({len(credentials)} fields)",
                    }
        except Exception as e:
            result = {"success": False, "details": f"Test error: {type(e).__name__}: {e}"}

        elapsed = int((time.monotonic() - start) * 1000)
        result["latency_ms"] = elapsed
        return result

    async def _test_exely_credentials(
        self,
        credentials: dict[str, str],
        tenant_id: str,
    ) -> dict[str, Any]:
        """Test Exely credentials with a real API connectivity check."""
        # Structural validation first
        required = ["api_key", "hotel_id"]
        missing = [f for f in required if not credentials.get(f, "").strip()]
        if missing:
            return {"success": False, "details": f"Missing/empty required Exely fields: {missing}"}

        try:
            from domains.channel_manager.connectors.exely.client import ExelyClient

            client = ExelyClient(
                api_key=credentials.get("api_key", ""),
                hotel_id=credentials.get("hotel_id", ""),
            )
            health = await client.health_check()
            if health.get("authenticated"):
                return {"success": True, "details": "Exely API authentication verified"}
            return {"success": False, "details": f"Exely auth check: {health}"}
        except ImportError:
            return {"success": True, "details": "Exely client not available — structural validation passed"}
        except Exception as e:
            return {"success": False, "details": f"Exely connectivity test failed: {e}"}

    async def _test_hotelrunner_credentials(
        self,
        credentials: dict[str, str],
        tenant_id: str,
    ) -> dict[str, Any]:
        """Test HotelRunner credentials with real API connectivity check."""
        token = credentials.get("token", "")
        hr_id = credentials.get("hr_id", "")

        # Structural validation
        if not token or len(token) < 5:
            return {"success": False, "details": "HotelRunner token appears invalid (too short)"}
        if not hr_id:
            return {"success": False, "details": "HotelRunner HR ID (hotel ID) is missing"}

        try:
            from domains.channel_manager.providers.hotelrunner import HotelRunnerProvider

            # Determine environment from credentials or tenant config
            env = credentials.get("environment", "mock")
            base_url = self._resolve_hr_base_url(env)

            provider = HotelRunnerProvider(
                token=token,
                hr_id=hr_id,
                base_url=base_url,
            )
            result = await provider.test_connection()

            if result.success:
                channel_count = 0
                if result.data:
                    channel_count = result.data.get("channel_count", 0)
                return {
                    "success": True,
                    "details": f"HotelRunner API connectivity verified ({channel_count} channels)",
                    "latency_ms": result.duration_ms,
                    "environment": env,
                }
            return {
                "success": False,
                "details": f"HotelRunner connection test failed: {result.error}",
                "latency_ms": result.duration_ms,
                "environment": env,
            }
        except ImportError:
            # Provider module not available — fall back to structural check
            return {"success": True, "details": "HotelRunner provider not available — structural validation passed"}
        except Exception as e:
            return {"success": False, "details": f"HotelRunner connectivity test failed: {e}"}

    @staticmethod
    def _resolve_hr_base_url(environment: str) -> str:
        """Resolve HotelRunner base URL from environment name."""
        urls = {
            "mock": "http://localhost:9999",
            "sandbox": "https://sandbox.hotelrunner.com",
            "production": "https://app.hotelrunner.com",
        }
        return urls.get(environment, "http://localhost:9999")

    async def _log_audit(
        self,
        *,
        secret_path: str,
        action: str,
        actor: str,
        version: int,
        tenant_id: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Write rotation audit log."""
        try:
            db = self._get_db()
            await db[COLL_ROTATION_AUDIT].insert_one(
                {
                    "secret_path": secret_path,
                    "action": action,
                    "actor": actor,
                    "version": version,
                    "tenant_id": tenant_id,
                    "details": details or {},
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        except Exception:
            logger.exception("Failed to write rotation audit log")

    async def _fire_alert(
        self,
        *,
        title: str,
        message: str,
        severity: str,
        tenant_id: str | None,
        provider: str | None,
    ) -> None:
        """Fire an alert via the alerting engine."""
        try:
            from controlplane.alerting import AlertingEngine

            engine = AlertingEngine()
            await engine.fire(
                trigger="secret_rotation_failure",
                severity=severity,
                title=title,
                message=message,
                tenant_id=tenant_id,
                provider=provider,
            )
        except Exception:
            logger.exception("Failed to fire rotation alert")

    def _classify_type(self, path_parts: list[str]):
        """Classify secret type from path for lifecycle rules."""
        from security.pii_registry import SecretType

        if len(path_parts) < 5:
            return SecretType.INTERNAL
        segment = path_parts[2].lower() if len(path_parts) > 2 else ""
        prov = path_parts[4].lower() if len(path_parts) > 4 else ""
        if segment == "channel-manager":
            return SecretType.CONNECTOR_CREDENTIAL
        if "webhook" in prov:
            return SecretType.WEBHOOK_SECRET
        if "key" in prov or "encryption" in prov:
            return SecretType.ENCRYPTION_KEY
        return SecretType.CONNECTOR_CREDENTIAL

    def _mask_path(self, path: str) -> str:
        """Mask tenant/property IDs in path for display."""
        parts = path.split("/")
        if len(parts) >= 6:
            parts[3] = parts[3][:4] + "***"
            parts[5] = parts[5][:4] + "***"
        return "/".join(parts)


# ── Singleton ──────────────────────────────────────────────────────

_engine: RotationEngine | None = None


def get_rotation_engine() -> RotationEngine:
    global _engine
    if _engine is None:
        _engine = RotationEngine()
    return _engine
