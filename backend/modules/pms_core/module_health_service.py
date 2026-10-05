"""Tenant-scoped, honest operational health for product modules.

The health centre is intentionally a read model.  It never infers that an
integration is live merely because its code exists, and it never exposes
credentials.  Unknown telemetry remains ``unknown`` until an integration or
module starts emitting a health/usage event.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db

MODULE_CATALOG: tuple[dict[str, Any], ...] = (
    {"key": "frontdesk", "name": "Ön büro", "core": True, "usage_collection": "bookings", "usage_field": "updated_at"},
    {"key": "housekeeping", "name": "Kat hizmetleri", "core": True, "usage_collection": "housekeeping_tasks", "usage_field": "updated_at"},
    {"key": "maintenance", "name": "Bakım", "core": True, "usage_collection": "maintenance_requests", "usage_field": "updated_at"},
    {"key": "finance", "name": "Finans ve folyo", "core": True, "usage_collection": "folio_transactions", "usage_field": "created_at"},
    {"key": "reports", "name": "Raporlar", "core": True, "usage_collection": "report_exports", "usage_field": "created_at"},
    {"key": "guest_crm", "name": "Misafir ve CRM", "core": True, "usage_collection": "guests", "usage_field": "updated_at"},
    {"key": "revenue", "name": "Gelir yönetimi", "core": True, "usage_collection": "rate_change_audit", "usage_field": "created_at"},
    {
        "key": "channel_manager",
        "name": "Kanal yöneticisi",
        "entitlement_keys": (
            "channel_manager",
            "pro_channel_manager",
            "mini_channel_manager_lite",
            "channel_exely",
            "channel_hotelrunner",
            "channel_sabre",
        ),
        "usage_collection": "channel_manager_syncs",
        "usage_field": "sync_timestamp",
        "config_collection": "channel_integrations",
    },
    {
        "key": "whatsapp",
        "name": "WhatsApp Business",
        "entitlement_keys": ("messaging_whatsapp",),
        "usage_collection": "messaging_logs",
        "usage_field": "created_at",
        "config_collection": "messaging_provider_configs",
    },
    {
        "key": "e_invoice",
        "name": "E-Fatura",
        "entitlement_keys": ("e_invoice", "einvoice", "nilvera"),
        "usage_collection": "invoice_sync_logs",
        "usage_field": "created_at",
        "config_collection": "invoice_integrations",
    },
)


def _date_value(document: dict[str, Any], field: str) -> str | None:
    value = document.get(field) or document.get("last_used_at") or document.get("updated_at") or document.get("created_at")
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return value if isinstance(value, str) and value else None


class ModuleHealthService:
    """Build a bounded, tenant-isolated module health read model."""

    async def _latest_usage(self, tenant_id: str, module: dict[str, Any], usage_by_module: dict[str, dict[str, Any]]) -> str | None:
        event = usage_by_module.get(module["key"])
        if event:
            return _date_value(event, "occurred_at")

        collection = getattr(db, module["usage_collection"])
        row = await collection.find_one(
            {"tenant_id": tenant_id},
            {"_id": 0, module["usage_field"]: 1, "last_used_at": 1, "updated_at": 1, "created_at": 1},
            sort=[(module["usage_field"], -1)],
        )
        return _date_value(row or {}, module["usage_field"])

    @staticmethod
    def _license_status(module: dict[str, Any], enabled_modules: dict[str, Any], active_products: set[str], expired_products: set[str]) -> str:
        if module.get("core"):
            return "included"
        keys = set(module.get("entitlement_keys") or (module["key"],))
        if any(enabled_modules.get(key) for key in keys) or keys & active_products:
            return "licensed"
        if keys & expired_products:
            return "expired"
        return "not_licensed"

    async def _channel_evidence(self, tenant_id: str) -> dict[str, Any]:
        """Read the same provider records as the channel connections screen."""

        from domains.channel_manager.channel_connections_router import build_channel_operational_status

        async def one(collection_name: str, query: dict[str, Any]) -> dict[str, Any] | None:
            collection = getattr(db, collection_name, None)
            if collection is None:
                return None
            return await collection.find_one(query, {"_id": 0, "token": 0, "password": 0, "username": 0, "credentials": 0})

        hr = await one("hotelrunner_connections", {"tenant_id": tenant_id})
        exely = await one("exely_connections", {"tenant_id": tenant_id})
        provider_collection = getattr(db, "provider_connections", None)
        provider_rows = []
        if provider_collection is not None:
            provider_rows = await provider_collection.find(
                {"tenant_id": tenant_id, "provider": {"$in": ["hotelrunner", "exely"]}, "status": "active"},
                {"_id": 0, "credentials": 0},
            ).to_list(20)
        provider_by_key = {row.get("provider"): row for row in provider_rows}

        evidence = []
        for key, legacy, mapping_collection in (
            ("hotelrunner", hr, "hotelrunner_room_mappings"),
            ("exely", exely, "exely_room_mappings"),
        ):
            modern = provider_by_key.get(key) or {}
            legacy = legacy or {}
            connected = bool(legacy.get("is_active") or modern.get("status") == "active")
            mappings = 0
            collection = getattr(db, mapping_collection, None)
            if collection is not None:
                mappings = await collection.count_documents({"tenant_id": tenant_id})
            if mappings == 0:
                cm_mappings = getattr(db, "cm_mappings", None)
                if cm_mappings is not None:
                    connector_pattern = "hotel|hr" if key == "hotelrunner" else "ex"
                    mappings = await cm_mappings.count_documents(
                        {
                            "tenant_id": tenant_id,
                            "entity_type": "room_type",
                            "connector_id": {"$regex": connector_pattern, "$options": "i"},
                            "status": "active",
                        }
                    )
            provider = {
                "provider": key,
                "connected": connected,
                "room_mappings_count": mappings,
                "auto_sync_reservations": legacy.get("auto_sync_reservations", modern.get("sync_reservations", False)),
                "sync_interval_minutes": legacy.get("sync_interval_minutes", modern.get("sync_interval_minutes", 15)),
                "last_successful_sync": legacy.get("last_successful_sync") or legacy.get("last_sync_at") or modern.get("last_successful_sync"),
                "last_error": legacy.get("last_error") or modern.get("last_error"),
                "last_error_at": legacy.get("last_error_at") or modern.get("last_error_at"),
                "environment": legacy.get("environment") or modern.get("environment") or legacy.get("mode"),
            }
            provider["operational_status"] = build_channel_operational_status(provider)
            evidence.append(provider)

        configured = any(item["connected"] for item in evidence)
        statuses = [item["operational_status"]["key"] for item in evidence if item["connected"]]
        if "error" in statuses:
            state = "error"
        elif "stale" in statuses:
            state = "stale"
        elif "production" in statuses:
            state = "production"
        elif statuses:
            state = statuses[0]
        else:
            state = "setup_pending"
        last_syncs = [item["operational_status"].get("last_successful_sync") for item in evidence]
        last_sync = max((value for value in last_syncs if value), default=None)
        errors = [item for item in evidence if item["operational_status"].get("last_error")]
        latest_error = max(errors, key=lambda item: item["operational_status"].get("last_error_at") or "", default=None)
        return {
            "configured": configured,
            "state": state,
            "last_used_at": last_sync,
            "last_error": (latest_error or {}).get("operational_status", {}).get("last_error"),
            "last_error_at": (latest_error or {}).get("operational_status", {}).get("last_error_at"),
            "providers": [
                {
                    "provider": item["provider"],
                    "connected": item["connected"],
                    "operational_status": item["operational_status"],
                }
                for item in evidence
            ],
        }

    async def get_snapshot(self, tenant_id: str) -> dict[str, Any]:
        tenant = await db.tenants.find_one(
            {"id": tenant_id},
            {"_id": 0, "modules": 1, "subscription_status": 1, "subscription_plan": 1, "plan": 1},
        ) or {}
        modules_value = tenant.get("modules") or {}
        enabled_modules = modules_value if isinstance(modules_value, dict) else {key: True for key in modules_value if isinstance(key, str)}
        now = datetime.now(UTC)
        subscriptions = await db.tenant_subscriptions.find(
            {"tenant_id": tenant_id},
            {"_id": 0, "product_key": 1, "status": 1, "end_date": 1},
        ).to_list(500)
        active_products: set[str] = set()
        expired_products: set[str] = set()
        for subscription in subscriptions:
            product_key = subscription.get("product_key")
            if not product_key:
                continue
            end_date = subscription.get("end_date")
            active = subscription.get("status") == "active" and (not end_date or end_date > now.isoformat())
            (active_products if active else expired_products).add(product_key)

        since = (now - timedelta(days=30)).isoformat()
        events = await db.module_health_events.find(
            {"tenant_id": tenant_id, "created_at": {"$gte": since}},
            {"_id": 0, "module_key": 1, "status": 1, "message": 1, "created_at": 1, "occurred_at": 1},
        ).sort("created_at", -1).to_list(1000)
        usage_by_module: dict[str, dict[str, Any]] = {}
        error_by_module: dict[str, dict[str, Any]] = {}
        for event in events:
            key = event.get("module_key")
            if not key:
                continue
            if event.get("status") == "error" and key not in error_by_module:
                error_by_module[key] = event
            if event.get("status") in {"used", "success", "healthy"} and key not in usage_by_module:
                usage_by_module[key] = event

        rows: list[dict[str, Any]] = []
        for module in MODULE_CATALOG:
            license_status = self._license_status(module, enabled_modules, active_products, expired_products)
            config_state = "not_applicable"
            channel_evidence = None
            if module["key"] == "channel_manager":
                channel_evidence = await self._channel_evidence(tenant_id)
                config_state = "configured" if channel_evidence["configured"] else "not_configured"
            elif module.get("config_collection"):
                config = await getattr(db, module["config_collection"]).find_one(
                    {"tenant_id": tenant_id, "status": {"$nin": ["disabled", "revoked"]}}, {"_id": 0, "status": 1}
                )
                config_state = "configured" if config else "not_configured"
            error = error_by_module.get(module["key"])
            last_used_at = channel_evidence["last_used_at"] if channel_evidence else await self._latest_usage(tenant_id, module, usage_by_module)
            channel_state = channel_evidence["state"] if channel_evidence else None
            if license_status in {"not_licensed", "expired"}:
                status = "attention"
            elif error or channel_state == "error":
                status = "error"
            elif channel_state == "stale":
                status = "attention"
            elif config_state == "not_configured":
                status = "setup_required"
            elif channel_state and channel_state != "production":
                status = "setup_required"
            elif last_used_at:
                status = "healthy"
            else:
                status = "unknown"
            rows.append(
                {
                    "key": module["key"],
                    "name": module["name"],
                    "status": status,
                    "installation_status": "installed" if module.get("core") or license_status == "licensed" or config_state == "configured" else "not_installed",
                    "license_status": license_status,
                    "integration_status": config_state,
                    "last_used_at": last_used_at,
                    "last_error": (error or {}).get("message") or (channel_evidence or {}).get("last_error"),
                    "last_error_at": _date_value(error or {}, "occurred_at") or (channel_evidence or {}).get("last_error_at"),
                    "operational_status": channel_state,
                    "providers": (channel_evidence or {}).get("providers", []),
                }
            )
        counts = {status: sum(row["status"] == status for row in rows) for status in ("healthy", "unknown", "setup_required", "attention", "error")}
        return {
            "tenant_id": tenant_id,
            "subscription": {"status": tenant.get("subscription_status", "unknown"), "plan": tenant.get("subscription_plan") or tenant.get("plan")},
            "modules": rows,
            "summary": {"total": len(rows), **counts},
            "generated_at": now.isoformat(),
            "telemetry_window_days": 30,
        }
