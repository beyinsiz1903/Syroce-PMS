"""Alert Delivery Router — Channel configuration, delivery, and logs."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.security import get_current_user
from models.schemas import User
from ...application.alert_delivery_service import AlertDeliveryService

logger = logging.getLogger("channel_manager.routers.delivery")

router = APIRouter(tags=["CM Alert Delivery"])


class DeliveryChannelRequest(BaseModel):
    id: Optional[str] = None
    connector_id: str = "*"
    channel_type: str  # email, webhook, slack, teams
    name: str = ""
    enabled: bool = True
    min_severity: str = "warning"
    config: dict = Field(default_factory=dict)
    throttle_seconds: int = 300


@router.get("/delivery/channels")
async def list_delivery_channels(
    connector_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """List configured delivery channels."""
    svc = AlertDeliveryService()
    channels = await svc.get_channels(current_user.tenant_id, connector_id)
    return {"channels": channels, "count": len(channels)}


@router.post("/delivery/channels")
async def upsert_delivery_channel(
    req: DeliveryChannelRequest,
    current_user: User = Depends(get_current_user),
):
    """Create or update a delivery channel configuration."""
    svc = AlertDeliveryService()
    channel = await svc.upsert_channel(current_user.tenant_id, req.model_dump())
    return {"message": "Channel saved", "channel": channel}


@router.delete("/delivery/channels/{channel_id}")
async def delete_delivery_channel(
    channel_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete a delivery channel."""
    svc = AlertDeliveryService()
    deleted = await svc.delete_channel(current_user.tenant_id, channel_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Channel not found")
    return {"message": "Channel deleted"}


@router.post("/delivery/test/{channel_id}")
async def test_delivery_channel(
    channel_id: str,
    current_user: User = Depends(get_current_user),
):
    """Send a test alert through a specific delivery channel."""
    svc = AlertDeliveryService()
    channels = await svc.get_channels(current_user.tenant_id)
    channel = next((c for c in channels if c.get("id") == channel_id), None)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    test_alert = {
        "id": "test-alert",
        "severity": "info",
        "trigger": "delivery_channel_test",
        "connector_id": channel.get("connector_id", ""),
        "description": "Test alert from Syroce PMS",
        "created_at": "2026-02-01T00:00:00Z",
        "metadata": {"test": True},
    }
    result = await svc.deliver_alert(current_user.tenant_id, test_alert)
    return {"message": "Test delivery completed", "result": result}


@router.get("/delivery/log")
async def get_delivery_log(
    alert_id: Optional[str] = None,
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
):
    """Get delivery audit log."""
    svc = AlertDeliveryService()
    logs = await svc.get_delivery_log(current_user.tenant_id, alert_id, limit)
    return {"logs": logs, "count": len(logs)}
