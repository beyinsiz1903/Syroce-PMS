"""
Connector Service - Manages connector account lifecycle (CRUD, activation, credential validation).
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from ..domain.models.connector_account import ConnectorAccount, ConnectorStatus, ConnectorProvider
from ..domain.models.audit import IntegrationAuditLog, AuditAction
from ..infrastructure.repository import ChannelManagerRepository
from ..connectors.hotelrunner.client import HotelRunnerClient
from ..connectors.hotelrunner.auth import HotelRunnerAuth
from ..connectors.hotelrunner.errors import AuthenticationError

logger = logging.getLogger("channel_manager.application.connector_service")


class ConnectorService:
    """Manages connector account lifecycle."""

    def __init__(self, repo: Optional[ChannelManagerRepository] = None):
        self._repo = repo or ChannelManagerRepository()

    async def create_connector(
        self,
        tenant_id: str,
        property_id: str,
        provider: str,
        display_name: str,
        credentials: Dict[str, Any],
        actor_id: Optional[str] = None,
        sync_config: Optional[Dict[str, bool]] = None,
    ) -> Dict[str, Any]:
        """Create a new connector account in DRAFT status."""
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

        await self._repo.upsert_connector(connector.to_doc())
        await self._audit(
            tenant_id, property_id, connector.id,
            AuditAction.CONNECTOR_CREATED, actor_id=actor_id,
            metadata={"provider": provider, "display_name": display_name},
        )
        return connector.to_doc()

    async def test_connection(self, tenant_id: str, connector_id: str) -> Dict[str, Any]:
        """Test connectivity with the external provider."""
        doc = await self._repo.get_connector(tenant_id, connector_id)
        if not doc:
            return {"success": False, "message": "Connector not found"}

        connector = ConnectorAccount.from_doc(doc)
        if connector.provider == ConnectorProvider.HOTELRUNNER:
            try:
                auth = HotelRunnerAuth.from_credentials(connector.credentials)
                client = HotelRunnerClient(auth=auth, sandbox=True)
                result = await client.test_connection()
                await client.close()
                return result
            except AuthenticationError:
                return {"success": False, "message": "Invalid HotelRunner credentials"}
            except Exception as e:
                return {"success": False, "message": str(e)}

        return {"success": False, "message": f"Provider {connector.provider} not yet supported"}

    async def activate_connector(self, tenant_id: str, connector_id: str, actor_id: Optional[str] = None) -> Dict[str, Any]:
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

    async def pause_connector(self, tenant_id: str, connector_id: str, actor_id: Optional[str] = None) -> Dict[str, Any]:
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

    async def get_connector(self, tenant_id: str, connector_id: str) -> Optional[Dict[str, Any]]:
        return await self._repo.get_connector(tenant_id, connector_id)

    async def list_connectors(self, tenant_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        return await self._repo.get_connectors_by_tenant(tenant_id, status)

    async def update_credentials(
        self,
        tenant_id: str, connector_id: str,
        credentials: Dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
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

    async def delete_connector(self, tenant_id: str, connector_id: str, actor_id: Optional[str] = None) -> bool:
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
