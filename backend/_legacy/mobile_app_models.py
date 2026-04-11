"""  
Mobile App Backend API
Native mobile app support (iOS/Android)
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
import uuid

class MobileDeviceRegistration(BaseModel):
    """Mobil cihaz kaydı"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    device_id: str
    device_type: str  # ios, android
    push_token: Optional[str] = None
    app_version: str
    os_version: str
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class PushNotification(BaseModel):
    """Push notification"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    user_id: Optional[str] = None
    title: str
    body: str
    data: Optional[dict] = None
    sent_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    delivered: bool = False
    opened: bool = False
