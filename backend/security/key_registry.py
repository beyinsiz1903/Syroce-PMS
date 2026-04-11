"""
Key Registry — Centralized encryption key lifecycle management.

Provides:
  - Key registration with versioning
  - State transitions: active → pending_rotation → retired → revoked
  - Emergency revoke with instant effect
  - Re-encryption tracking and progress
  - Audit trail for all key operations

State Machine:
  active ─────→ pending_rotation ─────→ retired
    │                                      │
    └──────────────→ revoked ←─────────────┘
                  (emergency path)

Usage:
  from security.key_registry import get_key_registry

  registry = get_key_registry()
  await registry.register_key(...)
  await registry.initiate_rotation(key_id, ...)
  await registry.emergency_revoke(key_id, reason, ...)
"""
import logging
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger("security.key_registry")

COLL_KEYS = "encryption_keys"
COLL_KEY_AUDIT = "encryption_key_audit"
COLL_REENC_JOBS = "reencryption_jobs"


class KeyState(str, Enum):
    """Encryption key lifecycle states."""
    ACTIVE = "active"
    PENDING_ROTATION = "pending_rotation"
    RETIRED = "retired"
    REVOKED = "revoked"


class KeyType(str, Enum):
    """Types of encryption keys."""
    MASTER = "master"          # Data encryption master key
    CONNECTOR = "connector"    # Channel connector credentials
    WEBHOOK = "webhook"        # Webhook signing secrets
    API = "api"                # API authentication keys
    PII = "pii"                # PII field encryption


# Valid state transitions
VALID_TRANSITIONS = {
    KeyState.ACTIVE: {KeyState.PENDING_ROTATION, KeyState.REVOKED},
    KeyState.PENDING_ROTATION: {KeyState.RETIRED, KeyState.REVOKED, KeyState.ACTIVE},
    KeyState.RETIRED: {KeyState.REVOKED},
    KeyState.REVOKED: set(),  # Terminal state
}


class KeyRegistry:
    """Centralized encryption key lifecycle manager."""

    def __init__(self):
        self._db = None

    def _get_db(self):
        if self._db is None:
            from core.tenant_db import get_system_db
            self._db = get_system_db()
        return self._db

    # ── Registration ───────────────────────────────────────────────

    async def register_key(
        self,
        *,
        key_id: str,
        key_type: KeyType,
        description: str = "",
        tenant_id: str = "",
        provider: str = "",
        metadata: dict | None = None,
        rotation_policy_days: int = 90,
        actor: str,
    ) -> dict[str, Any]:
        """Register a new encryption key in the registry.

        This does NOT store the actual key material — it tracks metadata,
        state, and rotation schedule.
        """
        db = self._get_db()
        now = datetime.now(UTC)

        existing = await db[COLL_KEYS].find_one({"key_id": key_id}, {"_id": 0})
        if existing:
            return {
                "success": False,
                "error": f"Key '{key_id}' already registered",
                "existing_state": existing.get("state"),
            }

        key_doc = {
            "key_id": key_id,
            "key_type": key_type.value,
            "description": description,
            "tenant_id": tenant_id,
            "provider": provider,
            "state": KeyState.ACTIVE.value,
            "version": 1,
            "metadata": metadata or {},
            "rotation_policy_days": rotation_policy_days,
            "next_rotation_due": (now + timedelta(days=rotation_policy_days)).isoformat(),
            "created_at": now.isoformat(),
            "created_by": actor,
            "activated_at": now.isoformat(),
            "last_used_at": None,
            "retired_at": None,
            "revoked_at": None,
            "revoke_reason": None,
        }

        await db[COLL_KEYS].insert_one(key_doc)
        await self._audit(
            key_id=key_id,
            action="key_registered",
            actor=actor,
            details={"key_type": key_type.value, "rotation_policy_days": rotation_policy_days},
        )

        logger.info("Key registered: %s (type=%s) by %s", key_id, key_type.value, actor)

        return {
            "success": True,
            "key_id": key_id,
            "state": KeyState.ACTIVE.value,
            "next_rotation_due": key_doc["next_rotation_due"],
        }

    # ── State Transitions ──────────────────────────────────────────

    async def initiate_rotation(
        self,
        key_id: str,
        *,
        actor: str,
        reason: str = "scheduled",
    ) -> dict[str, Any]:
        """Move key to pending_rotation state.

        This signals that rotation has started but not completed.
        The key remains usable during this state.
        """
        return await self._transition_state(
            key_id=key_id,
            new_state=KeyState.PENDING_ROTATION,
            actor=actor,
            reason=reason,
        )

    async def complete_rotation(
        self,
        key_id: str,
        *,
        actor: str,
        new_version: int | None = None,
    ) -> dict[str, Any]:
        """Move key from pending_rotation to retired.

        Called after successful re-encryption of all data using the new key.
        """
        db = self._get_db()
        now = datetime.now(UTC)

        key = await db[COLL_KEYS].find_one({"key_id": key_id}, {"_id": 0})
        if not key:
            return {"success": False, "error": "Key not found"}

        if key["state"] != KeyState.PENDING_ROTATION.value:
            return {
                "success": False,
                "error": f"Cannot complete rotation: key is in '{key['state']}' state",
            }

        version = new_version or (key.get("version", 1) + 1)

        await db[COLL_KEYS].update_one(
            {"key_id": key_id},
            {
                "$set": {
                    "state": KeyState.RETIRED.value,
                    "retired_at": now.isoformat(),
                    "version": version,
                }
            },
        )

        await self._audit(
            key_id=key_id,
            action="rotation_completed",
            actor=actor,
            details={"new_version": version},
        )

        logger.info("Key rotation completed: %s -> v%d by %s", key_id, version, actor)

        return {
            "success": True,
            "key_id": key_id,
            "state": KeyState.RETIRED.value,
            "version": version,
            "retired_at": now.isoformat(),
        }

    async def cancel_rotation(
        self,
        key_id: str,
        *,
        actor: str,
        reason: str = "manual_cancel",
    ) -> dict[str, Any]:
        """Cancel rotation and return key to active state."""
        return await self._transition_state(
            key_id=key_id,
            new_state=KeyState.ACTIVE,
            actor=actor,
            reason=reason,
        )

    async def emergency_revoke(
        self,
        key_id: str,
        *,
        actor: str,
        reason: str,
        notify_channels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Immediately revoke a key. Emergency path from any state.

        This is a CRITICAL security operation:
        - Key becomes immediately unusable
        - All dependent data must be re-encrypted with a new key
        - Alerts are fired to configured channels
        - Cannot be undone — requires new key registration
        """
        db = self._get_db()
        now = datetime.now(UTC)

        key = await db[COLL_KEYS].find_one({"key_id": key_id}, {"_id": 0})
        if not key:
            return {"success": False, "error": "Key not found"}

        if key["state"] == KeyState.REVOKED.value:
            return {"success": False, "error": "Key already revoked"}

        previous_state = key["state"]

        await db[COLL_KEYS].update_one(
            {"key_id": key_id},
            {
                "$set": {
                    "state": KeyState.REVOKED.value,
                    "revoked_at": now.isoformat(),
                    "revoke_reason": reason,
                }
            },
        )

        await self._audit(
            key_id=key_id,
            action="emergency_revoke",
            actor=actor,
            details={
                "previous_state": previous_state,
                "reason": reason,
                "notify_channels": notify_channels or [],
            },
            severity="critical",
        )

        # Fire critical alert
        await self._fire_alert(
            title=f"EMERGENCY KEY REVOKE: {key_id}",
            message=f"Key '{key_id}' revoked by {actor}. Reason: {reason}",
            severity="critical",
            tenant_id=key.get("tenant_id"),
            provider=key.get("provider"),
        )

        logger.critical(
            "EMERGENCY KEY REVOKE: %s (was %s) by %s — reason: %s",
            key_id, previous_state, actor, reason,
        )

        return {
            "success": True,
            "key_id": key_id,
            "state": KeyState.REVOKED.value,
            "revoked_at": now.isoformat(),
            "previous_state": previous_state,
            "action_required": "Re-encrypt all dependent data with new key immediately",
        }

    async def _transition_state(
        self,
        key_id: str,
        new_state: KeyState,
        actor: str,
        reason: str,
    ) -> dict[str, Any]:
        """Internal state transition with validation."""
        db = self._get_db()
        now = datetime.now(UTC)

        key = await db[COLL_KEYS].find_one({"key_id": key_id}, {"_id": 0})
        if not key:
            return {"success": False, "error": "Key not found"}

        current_state = KeyState(key["state"])
        if new_state not in VALID_TRANSITIONS.get(current_state, set()):
            return {
                "success": False,
                "error": f"Invalid transition: {current_state.value} -> {new_state.value}",
                "valid_transitions": [s.value for s in VALID_TRANSITIONS.get(current_state, set())],
            }

        update_fields: dict[str, Any] = {"state": new_state.value}

        if new_state == KeyState.PENDING_ROTATION:
            update_fields["rotation_started_at"] = now.isoformat()
        elif new_state == KeyState.RETIRED:
            update_fields["retired_at"] = now.isoformat()
        elif new_state == KeyState.ACTIVE:
            # Reactivation — update rotation schedule
            policy_days = key.get("rotation_policy_days", 90)
            update_fields["next_rotation_due"] = (now + timedelta(days=policy_days)).isoformat()
            update_fields["rotation_started_at"] = None

        await db[COLL_KEYS].update_one({"key_id": key_id}, {"$set": update_fields})

        await self._audit(
            key_id=key_id,
            action=f"state_transition_{new_state.value}",
            actor=actor,
            details={"from_state": current_state.value, "reason": reason},
        )

        logger.info(
            "Key state transition: %s %s -> %s by %s (%s)",
            key_id, current_state.value, new_state.value, actor, reason,
        )

        return {
            "success": True,
            "key_id": key_id,
            "previous_state": current_state.value,
            "new_state": new_state.value,
            "timestamp": now.isoformat(),
        }

    # ── Query / Dashboard ──────────────────────────────────────────

    async def get_key(self, key_id: str) -> dict[str, Any] | None:
        """Get key metadata by ID."""
        db = self._get_db()
        return await db[COLL_KEYS].find_one({"key_id": key_id}, {"_id": 0})

    async def list_keys(
        self,
        *,
        state: KeyState | None = None,
        key_type: KeyType | None = None,
        tenant_id: str | None = None,
        include_revoked: bool = False,
    ) -> list[dict[str, Any]]:
        """List keys with optional filters."""
        db = self._get_db()
        query: dict[str, Any] = {}

        if state:
            query["state"] = state.value
        elif not include_revoked:
            query["state"] = {"$ne": KeyState.REVOKED.value}

        if key_type:
            query["key_type"] = key_type.value
        if tenant_id:
            query["tenant_id"] = tenant_id

        cursor = db[COLL_KEYS].find(query, {"_id": 0}).sort("created_at", -1)
        return await cursor.to_list(500)

    async def get_active_key(
        self,
        key_type: KeyType,
        tenant_id: str = "",
        provider: str = "",
    ) -> dict[str, Any] | None:
        """Get the currently active key for a type/tenant/provider combination."""
        db = self._get_db()
        query = {
            "key_type": key_type.value,
            "state": KeyState.ACTIVE.value,
        }
        if tenant_id:
            query["tenant_id"] = tenant_id
        if provider:
            query["provider"] = provider

        return await db[COLL_KEYS].find_one(
            query,
            {"_id": 0},
            sort=[("version", -1)],
        )

    async def get_dashboard(self) -> dict[str, Any]:
        """Key registry dashboard — summary of all keys by state and type."""
        db = self._get_db()
        now = datetime.now(UTC)

        all_keys = await db[COLL_KEYS].find({}, {"_id": 0}).to_list(1000)

        # Group by state
        by_state = {s.value: [] for s in KeyState}
        for key in all_keys:
            state = key.get("state", KeyState.ACTIVE.value)
            by_state.setdefault(state, []).append(key)

        # Group by type
        by_type = {t.value: [] for t in KeyType}
        for key in all_keys:
            key_type = key.get("key_type", KeyType.MASTER.value)
            by_type.setdefault(key_type, []).append(key)

        # Find overdue rotations
        overdue = []
        warning = []
        for key in all_keys:
            if key.get("state") not in (KeyState.ACTIVE.value, KeyState.PENDING_ROTATION.value):
                continue
            next_due = key.get("next_rotation_due")
            if not next_due:
                continue
            try:
                due_dt = datetime.fromisoformat(next_due.replace("Z", "+00:00"))
                days_until = (due_dt - now).days
                if days_until < 0:
                    overdue.append({**key, "days_overdue": abs(days_until)})
                elif days_until <= 14:
                    warning.append({**key, "days_until_due": days_until})
            except Exception:
                pass

        return {
            "summary": {
                "total": len(all_keys),
                "active": len(by_state.get(KeyState.ACTIVE.value, [])),
                "pending_rotation": len(by_state.get(KeyState.PENDING_ROTATION.value, [])),
                "retired": len(by_state.get(KeyState.RETIRED.value, [])),
                "revoked": len(by_state.get(KeyState.REVOKED.value, [])),
                "overdue_count": len(overdue),
                "warning_count": len(warning),
            },
            "by_type": {k: len(v) for k, v in by_type.items()},
            "overdue_rotations": overdue,
            "rotation_warnings": warning,
            "keys": all_keys,
            "timestamp": now.isoformat(),
        }

    async def get_safe_summary(self, key_id: str) -> dict[str, Any]:
        """Get a safe summary of a key — no sensitive details."""
        key = await self.get_key(key_id)
        if not key:
            return {"error": "Key not found"}

        now = datetime.now(UTC)
        next_due = key.get("next_rotation_due")
        days_until_rotation = None
        is_overdue = False

        if next_due:
            try:
                due_dt = datetime.fromisoformat(next_due.replace("Z", "+00:00"))
                days_until_rotation = (due_dt - now).days
                is_overdue = days_until_rotation < 0
            except Exception:
                pass

        return {
            "key_id": key["key_id"],
            "key_type": key.get("key_type"),
            "state": key.get("state"),
            "version": key.get("version"),
            "description": key.get("description", ""),
            "tenant_id": key.get("tenant_id") or "(system)",
            "provider": key.get("provider") or "(all)",
            "created_at": key.get("created_at"),
            "activated_at": key.get("activated_at"),
            "last_used_at": key.get("last_used_at"),
            "next_rotation_due": next_due,
            "days_until_rotation": days_until_rotation,
            "is_overdue": is_overdue,
            "rotation_policy_days": key.get("rotation_policy_days"),
        }

    # ── Usage Tracking ─────────────────────────────────────────────

    async def record_key_usage(self, key_id: str) -> None:
        """Record that a key was used. Updates last_used_at."""
        db = self._get_db()
        await db[COLL_KEYS].update_one(
            {"key_id": key_id},
            {"$set": {"last_used_at": datetime.now(UTC).isoformat()}},
        )

    # ── Audit ──────────────────────────────────────────────────────

    async def get_audit_log(
        self,
        *,
        key_id: str | None = None,
        action: str | None = None,
        severity: str | None = None,
        limit: int = 100,
        skip: int = 0,
    ) -> dict[str, Any]:
        """Query key audit log."""
        db = self._get_db()
        query: dict[str, Any] = {}

        if key_id:
            query["key_id"] = key_id
        if action:
            query["action"] = action
        if severity:
            query["severity"] = severity

        total = await db[COLL_KEY_AUDIT].count_documents(query)
        items = await db[COLL_KEY_AUDIT].find(
            query, {"_id": 0}
        ).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)

        return {"items": items, "total": total, "limit": limit, "skip": skip}

    async def _audit(
        self,
        *,
        key_id: str,
        action: str,
        actor: str,
        details: dict[str, Any] | None = None,
        severity: str = "info",
    ) -> None:
        """Write audit log entry."""
        db = self._get_db()
        try:
            await db[COLL_KEY_AUDIT].insert_one({
                "key_id": key_id,
                "action": action,
                "actor": actor,
                "details": details or {},
                "severity": severity,
                "timestamp": datetime.now(UTC).isoformat(),
            })
        except Exception:
            logger.exception("Failed to write key audit log")

    # ── Alerts ─────────────────────────────────────────────────────

    async def _fire_alert(
        self,
        *,
        title: str,
        message: str,
        severity: str,
        tenant_id: str | None,
        provider: str | None,
    ) -> None:
        """Fire alert via controlplane alerting."""
        try:
            from controlplane.alerting import AlertingEngine

            engine = AlertingEngine()
            await engine.fire(
                trigger="key_registry_event",
                severity=severity,
                title=title,
                message=message,
                tenant_id=tenant_id,
                provider=provider,
            )
        except Exception:
            logger.exception("Failed to fire key registry alert")

    # ── Index Setup ────────────────────────────────────────────────

    async def ensure_indexes(self) -> None:
        """Create indexes for key registry collections."""
        db = self._get_db()

        keys = db[COLL_KEYS]
        await keys.create_index("key_id", unique=True)
        await keys.create_index([("state", 1), ("key_type", 1)])
        await keys.create_index([("tenant_id", 1), ("provider", 1), ("state", 1)])
        await keys.create_index("next_rotation_due")

        audit = db[COLL_KEY_AUDIT]
        await audit.create_index([("key_id", 1), ("timestamp", -1)])
        await audit.create_index("timestamp", expireAfterSeconds=365 * 86400)  # 1-year TTL


# ── Singleton ──────────────────────────────────────────────────────

_registry: KeyRegistry | None = None


def get_key_registry() -> KeyRegistry:
    """Get or create the singleton KeyRegistry."""
    global _registry
    if _registry is None:
        _registry = KeyRegistry()
    return _registry
