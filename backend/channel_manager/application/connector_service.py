"""
Connector Service - Manages connector account lifecycle (CRUD, activation, credential validation).
"""
import logging
from datetime import UTC, datetime
from typing import Any

from ..connectors.hotelrunner.auth import HotelRunnerAuth
from ..connectors.hotelrunner.client import HotelRunnerClient
from ..connectors.hotelrunner.errors import AuthenticationError
from ..domain.models.audit import AuditAction, IntegrationAuditLog
from ..domain.models.connector_account import ConnectorAccount, ConnectorProvider, ConnectorStatus
from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.connector_service")


class ConnectorService:
    """Manages connector account lifecycle."""

    def __init__(self, repo: ChannelManagerRepository | None = None):
        self._repo = repo or ChannelManagerRepository()

    async def create_connector(
        self,
        tenant_id: str,
        property_id: str,
        provider: str,
        display_name: str,
        credentials: dict[str, Any],
        actor_id: str | None = None,
        sync_config: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        """Create a new connector account in DRAFT status."""
        from pymongo.errors import DuplicateKeyError

        connector = ConnectorAccount(
            tenant_id=tenant_id,
            property_id=property_id,
            provider=ConnectorProvider(provider),
            display_name=display_name,
            credentials=credentials,
            status=ConnectorStatus.DRAFT,
            created_by=actor_id,
        )
        if sync_config:
            connector.sync_inventory = sync_config.get("inventory", True)
            connector.sync_rates = sync_config.get("rates", True)
            connector.sync_reservations = sync_config.get("reservations", True)
            connector.sync_restrictions = sync_config.get("restrictions", True)

        try:
            await self._repo.upsert_connector(connector.to_doc())
        except DuplicateKeyError:
            raise ValueError("A connector for this provider already exists on this property")

        await self._audit(
            tenant_id, property_id, connector.id,
            AuditAction.CONNECTOR_CREATED, actor_id=actor_id,
            metadata={"provider": provider, "display_name": display_name},
        )
        return connector.to_doc()

    async def test_connection(self, tenant_id: str, connector_id: str) -> dict[str, Any]:
        """
        Production-grade connection test.
        Validates auth, property access, room types, rate plans, and XML connectivity.
        Logs result to audit trail.
        """

        doc = await self._repo.get_connector(tenant_id, connector_id)
        if not doc:
            return {"success": False, "message": "Connector not found", "tested_at": datetime.now(UTC).isoformat()}

        connector = ConnectorAccount.from_doc(doc)

        if connector.provider == ConnectorProvider.HOTELRUNNER:
            result = None
            try:
                auth = HotelRunnerAuth.from_credentials(connector.credentials)
                client = HotelRunnerClient(auth=auth, sandbox=True)
                result = await client.test_connection_detailed()
                await client.close()
            except AuthenticationError:
                result = {
                    "success": False,
                    "tested_at": datetime.now(UTC).isoformat(),
                    "total_latency_ms": 0,
                    "summary": "Kimlik bilgileri eksik veya geçersiz",
                    "auth_status": {"status": "fail", "latency_ms": 0, "error_code": "CRED_MISSING", "message": "Token veya HR ID eksik"},
                    "inventory_read_status": {"status": "fail", "latency_ms": 0, "error_code": "SKIPPED", "message": "Auth başarısız olduğu için atlandı"},
                    "rate_read_status": {"status": "fail", "latency_ms": 0, "error_code": "SKIPPED", "message": "Auth başarısız olduğu için atlandı"},
                    "property_access_status": {"status": "fail", "latency_ms": 0, "error_code": "SKIPPED", "message": "Auth başarısız olduğu için atlandı"},
                    "xml_connectivity_status": {"status": "fail", "latency_ms": 0, "error_code": "SKIPPED", "message": "Auth başarısız olduğu için atlandı"},
                }
            except Exception as e:
                result = {
                    "success": False,
                    "tested_at": datetime.now(UTC).isoformat(),
                    "total_latency_ms": 0,
                    "summary": f"Test sırasında beklenmeyen hata: {str(e)[:200]}",
                    "auth_status": {"status": "fail", "latency_ms": 0, "error_code": "UNKNOWN", "message": str(e)[:200]},
                    "inventory_read_status": {"status": "fail", "latency_ms": 0, "error_code": "SKIPPED", "message": "Önceki adım başarısız"},
                    "rate_read_status": {"status": "fail", "latency_ms": 0, "error_code": "SKIPPED", "message": "Önceki adım başarısız"},
                    "property_access_status": {"status": "fail", "latency_ms": 0, "error_code": "SKIPPED", "message": "Önceki adım başarısız"},
                    "xml_connectivity_status": {"status": "fail", "latency_ms": 0, "error_code": "SKIPPED", "message": "Önceki adım başarısız"},
                }

            # Write to audit log
            await self._audit(
                tenant_id,
                connector.property_id,
                connector_id,
                AuditAction.CONNECTION_TESTED,
                actor_id=None,
                metadata={
                    "success": result["success"],
                    "summary": result.get("summary", ""),
                    "total_latency_ms": result.get("total_latency_ms", 0),
                    "provider": connector.provider.value,
                },
            )

            # Add connector context to result
            result["connector_id"] = connector_id
            result["provider"] = connector.provider.value
            result["display_name"] = connector.display_name
            return result

        return {
            "success": False,
            "message": f"Provider {connector.provider} not yet supported",
            "tested_at": datetime.now(UTC).isoformat(),
            "connector_id": connector_id,
            "provider": connector.provider.value,
        }

    async def activate_connector(self, tenant_id: str, connector_id: str, actor_id: str | None = None) -> dict[str, Any]:
        """Activate a connector (allows sync operations)."""
        doc = await self._repo.get_connector(tenant_id, connector_id)
        if not doc:
            raise ValueError("Connector not found")

        doc["status"] = ConnectorStatus.ACTIVE.value
        doc["updated_by"] = actor_id
        await self._repo.upsert_connector(doc)
        await self._audit(
            tenant_id, doc.get("property_id", ""), connector_id,
            AuditAction.CONNECTOR_ACTIVATED, actor_id=actor_id,
        )
        return doc

    async def pause_connector(self, tenant_id: str, connector_id: str, actor_id: str | None = None) -> dict[str, Any]:
        """Pause a connector (stops sync operations)."""
        doc = await self._repo.get_connector(tenant_id, connector_id)
        if not doc:
            raise ValueError("Connector not found")

        doc["status"] = ConnectorStatus.PAUSED.value
        doc["updated_by"] = actor_id
        await self._repo.upsert_connector(doc)
        await self._audit(
            tenant_id, doc.get("property_id", ""), connector_id,
            AuditAction.CONNECTOR_PAUSED, actor_id=actor_id,
        )
        return doc

    async def get_connector(self, tenant_id: str, connector_id: str) -> dict[str, Any] | None:
        return await self._repo.get_connector(tenant_id, connector_id)

    async def list_connectors(self, tenant_id: str, status: str | None = None) -> list[dict[str, Any]]:
        return await self._repo.get_connectors_by_tenant(tenant_id, status)

    async def update_credentials(
        self,
        tenant_id: str, connector_id: str,
        credentials: dict[str, Any],
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        doc = await self._repo.get_connector(tenant_id, connector_id)
        if not doc:
            raise ValueError("Connector not found")
        doc["credentials"] = credentials
        doc["updated_by"] = actor_id
        await self._repo.upsert_connector(doc)
        await self._audit(
            tenant_id, doc.get("property_id", ""), connector_id,
            AuditAction.CREDENTIALS_UPDATED, actor_id=actor_id,
        )
        return doc

    async def delete_connector(self, tenant_id: str, connector_id: str, actor_id: str | None = None) -> bool:
        doc = await self._repo.get_connector(tenant_id, connector_id)
        if doc:
            await self._audit(
                tenant_id, doc.get("property_id", ""), connector_id,
                AuditAction.CONNECTOR_DISABLED, actor_id=actor_id,
            )
        return await self._repo.delete_connector(tenant_id, connector_id)

    async def _audit(self, tenant_id, property_id, connector_id, action, actor_id=None, metadata=None):
        log = IntegrationAuditLog(
            tenant_id=tenant_id,
            property_id=property_id,
            connector_id=connector_id,
            action=action,
            actor_id=actor_id,
            metadata=metadata or {},
        )
        await self._repo.create_audit_log(log.to_doc())
