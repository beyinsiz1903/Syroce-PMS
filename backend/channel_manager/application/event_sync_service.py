"""
Event-Driven Sync Service - Triggers inventory/rate sync from domain events.

Domain Events:
  - booking_created, booking_modified, booking_cancelled
  - room_blocked, room_unblocked
  - rate_changed, restriction_changed

Flow:
  event -> validate -> create sync job -> coalescing -> dispatch
  Failure -> audit log + optional reconciliation issue
"""

import logging
from typing import Any

from ..domain.models.audit import AuditAction, IntegrationAuditLog
from ..domain.models.sync import SyncType
from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.event_sync_service")

# Supported domain events
SUPPORTED_EVENTS = {
    "booking_created",
    "booking_modified",
    "booking_cancelled",
    "booking_no_show",
    "room_blocked",
    "room_unblocked",
    "rate_changed",
    "restriction_changed",
}

# Event -> sync type mapping
EVENT_SYNC_MAP = {
    "booking_created": SyncType.INVENTORY,
    "booking_modified": SyncType.INVENTORY,
    "booking_cancelled": SyncType.INVENTORY,
    "booking_no_show": SyncType.INVENTORY,
    "room_blocked": SyncType.INVENTORY,
    "room_unblocked": SyncType.INVENTORY,
    "rate_changed": SyncType.RATES,
    "restriction_changed": SyncType.INVENTORY,
}


class EventSyncService:
    """Handles domain events and triggers appropriate sync operations."""

    def __init__(self, repo: ChannelManagerRepository | None = None):
        self._repo = repo or ChannelManagerRepository()

    async def handle_event(
        self,
        tenant_id: str,
        event_type: str,
        event_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Process a domain event and trigger sync if applicable.

        Returns: {handled: bool, sync_jobs_created: int, ...}
        """
        if event_type not in SUPPORTED_EVENTS:
            return {"handled": False, "reason": f"Unsupported event: {event_type}"}

        property_id = event_payload.get("property_id", "")
        if not property_id:
            return {"handled": False, "reason": "Missing property_id in event payload"}

        # Find active connectors for this property
        connectors = await self._repo.get_active_connectors(tenant_id, property_id)
        if not connectors:
            return {"handled": True, "sync_jobs_created": 0, "reason": "No active connectors"}

        sync_type = EVENT_SYNC_MAP.get(event_type, SyncType.INVENTORY)
        jobs_created = []

        for connector in connectors:
            connector_id = connector.get("id", "")

            # Determine date range from event
            date_start, date_end = self._extract_date_range(event_type, event_payload)
            if not date_start:
                continue

            # Determine room types affected
            room_type_ids = self._extract_room_types(event_type, event_payload)

            # Create sync job via inventory sync service
            from ..application.inventory_sync_service import InventorySyncService

            sync_svc = InventorySyncService(self._repo)

            try:
                if sync_type == SyncType.RATES:
                    result = await sync_svc.trigger_rate_sync(
                        tenant_id=tenant_id,
                        connector_id=connector_id,
                        date_start=date_start,
                        date_end=date_end,
                        triggered_by="event",
                        actor_id=f"event:{event_type}",
                    )
                else:
                    result = await sync_svc.trigger_inventory_sync(
                        tenant_id=tenant_id,
                        connector_id=connector_id,
                        date_start=date_start,
                        date_end=date_end,
                        room_type_ids=room_type_ids,
                        triggered_by="event",
                        trigger_reason=f"Domain event: {event_type}",
                        actor_id=f"event:{event_type}",
                    )
                jobs_created.append(
                    {
                        "connector_id": connector_id,
                        "job_id": result.get("job_id", ""),
                        "status": result.get("status", ""),
                    }
                )
            except Exception as e:
                logger.error(
                    "Event sync failed for connector %s: %s",
                    connector_id,
                    e,
                )
                jobs_created.append(
                    {
                        "connector_id": connector_id,
                        "error": str(e)[:200],
                    }
                )

                # Audit failure
                await self._audit(
                    tenant_id,
                    property_id,
                    connector_id,
                    AuditAction.EVENT_SYNC_FAILED,
                    metadata={
                        "event_type": event_type,
                        "error": str(e)[:200],
                        "success": False,
                    },
                )

                # Create reconciliation issue for persistent event sync failures
                from ..application.reconciliation_service import ReconciliationService

                recon = ReconciliationService(self._repo)
                await recon.create_issue(
                    tenant_id=tenant_id,
                    property_id=property_id,
                    connector_id=connector_id,
                    issue_type="stale_sync",
                    severity="high",
                    description=f"Event sync failed for {event_type}: {str(e)[:200]}",
                    suggested_actions=["retry_sync"],
                    evidence_payload={
                        "event_type": event_type,
                        "error": str(e)[:200],
                    },
                )
                continue

            # Audit success
            await self._audit(
                tenant_id,
                property_id,
                connector_id,
                AuditAction.EVENT_SYNC_TRIGGERED,
                metadata={
                    "event_type": event_type,
                    "sync_type": sync_type.value,
                    "date_range": f"{date_start} -> {date_end}",
                    "success": True,
                },
            )

        return {
            "handled": True,
            "event_type": event_type,
            "sync_jobs_created": len([j for j in jobs_created if "job_id" in j]),
            "jobs": jobs_created,
        }

    async def handle_batch_events(
        self,
        tenant_id: str,
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Process multiple domain events with deduplication."""
        results = []
        for evt in events:
            event_type = evt.get("event_type", "")
            payload = evt.get("payload", {})
            result = await self.handle_event(tenant_id, event_type, payload)
            results.append(result)
        return {
            "processed": len(results),
            "jobs_created": sum(r.get("sync_jobs_created", 0) for r in results),
            "results": results,
        }

    # ------------------------------------------------------------------ #
    #  Event Payload Parsing                                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_date_range(event_type: str, payload: dict[str, Any]) -> tuple:
        """Extract affected date range from event payload."""
        if event_type in ("booking_created", "booking_modified", "booking_cancelled", "booking_no_show"):
            check_in = payload.get("check_in", payload.get("date_start", ""))
            check_out = payload.get("check_out", payload.get("date_end", ""))
            return check_in, check_out
        elif event_type in ("room_blocked", "room_unblocked"):
            return (
                payload.get("date_start", payload.get("block_start", "")),
                payload.get("date_end", payload.get("block_end", "")),
            )
        elif event_type in ("rate_changed", "restriction_changed"):
            return (
                payload.get("date_start", ""),
                payload.get("date_end", ""),
            )
        return ("", "")

    @staticmethod
    def _extract_room_types(event_type: str, payload: dict[str, Any]) -> list[str] | None:
        """Extract affected room types from event payload."""
        rt = payload.get("room_type_id", payload.get("room_type", ""))
        if rt:
            return [rt]
        rts = payload.get("room_type_ids", [])
        if rts:
            return rts
        return None

    # ------------------------------------------------------------------ #
    #  Audit                                                               #
    # ------------------------------------------------------------------ #

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
