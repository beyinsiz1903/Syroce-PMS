"""
WebSocket Real-Time Admin Updates Service.

Broadcasts real-time events to connected admin clients:
  - alert_triggered
  - connector_health_change
  - sync_job_update
  - reservation_import_batch_update
  - scheduler_job_state_change

Uses a simple in-process pub/sub pattern with connected WebSocket clients.
"""
import logging
import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Set
from fastapi import WebSocket

logger = logging.getLogger("channel_manager.application.ws_realtime")


class ConnectionManager:
    """Manages WebSocket connections for real-time admin updates."""

    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, tenant_id: str):
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            if tenant_id not in self._connections:
                self._connections[tenant_id] = set()
            self._connections[tenant_id].add(websocket)
        logger.info("WS client connected for tenant %s (total: %d)",
                     tenant_id, len(self._connections.get(tenant_id, set())))

    async def disconnect(self, websocket: WebSocket, tenant_id: str):
        """Remove a WebSocket connection."""
        async with self._lock:
            if tenant_id in self._connections:
                self._connections[tenant_id].discard(websocket)
                if not self._connections[tenant_id]:
                    del self._connections[tenant_id]
        logger.info("WS client disconnected for tenant %s", tenant_id)

    async def broadcast(self, tenant_id: str, event: Dict[str, Any]):
        """Broadcast an event to all connections for a tenant."""
        async with self._lock:
            connections = self._connections.get(tenant_id, set()).copy()

        if not connections:
            return

        payload = json.dumps({
            **event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        dead = []
        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    if tenant_id in self._connections:
                        self._connections[tenant_id].discard(ws)

    def get_connection_count(self, tenant_id: str) -> int:
        return len(self._connections.get(tenant_id, set()))


# Global singleton
ws_manager = ConnectionManager()


class RealtimeEventService:
    """Publishes domain events to connected WebSocket clients."""

    @staticmethod
    async def emit_alert_triggered(tenant_id: str, alert: Dict[str, Any]):
        await ws_manager.broadcast(tenant_id, {
            "type": "alert_triggered",
            "data": {
                "alert_id": alert.get("id", ""),
                "severity": alert.get("severity", ""),
                "trigger": alert.get("trigger", ""),
                "message": alert.get("message", ""),
                "connector_id": alert.get("connector_id", ""),
            },
        })

    @staticmethod
    async def emit_health_change(tenant_id: str, connector_id: str, health_data: Dict[str, Any]):
        await ws_manager.broadcast(tenant_id, {
            "type": "connector_health_change",
            "data": {
                "connector_id": connector_id,
                "health_score": health_data.get("health_score", 0),
                "classification": health_data.get("classification", ""),
                "sync_success_rate": health_data.get("sync_success_rate", 0),
            },
        })

    @staticmethod
    async def emit_sync_job_update(tenant_id: str, job: Dict[str, Any]):
        await ws_manager.broadcast(tenant_id, {
            "type": "sync_job_update",
            "data": {
                "job_id": job.get("job_id", job.get("id", "")),
                "status": job.get("status", ""),
                "sync_type": job.get("sync_type", ""),
                "completed_events": job.get("completed_events", 0),
                "failed_events": job.get("failed_events", 0),
            },
        })

    @staticmethod
    async def emit_import_batch_update(tenant_id: str, batch: Dict[str, Any]):
        await ws_manager.broadcast(tenant_id, {
            "type": "reservation_import_batch_update",
            "data": {
                "batch_id": batch.get("batch_id", ""),
                "status": batch.get("status", ""),
                "total": batch.get("total", 0),
                "new": batch.get("new", 0),
                "modified": batch.get("modified", 0),
                "cancelled": batch.get("cancelled", 0),
            },
        })

    @staticmethod
    async def emit_scheduler_job_change(tenant_id: str, job: Dict[str, Any]):
        await ws_manager.broadcast(tenant_id, {
            "type": "scheduler_job_state_change",
            "data": {
                "job_id": job.get("job_id", ""),
                "job_type": job.get("job_type", ""),
                "status": job.get("status", ""),
                "message": job.get("message", ""),
            },
        })
