"""  
IoT Integration Models  
Smart room devices, energy management
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
import uuid

class SmartRoomDevice(BaseModel):
    """Akıllı oda cihazı"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_id: str
    device_type: str  # thermostat, light, curtain, tv, minibar
    device_id: str  # MAC address or unique ID
    manufacturer: str
    status: str = "online"  # online, offline, error
    last_communication: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class EnergyConsumption(BaseModel):
    """Enerji tüketim kaydı"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_id: Optional[str] = None
    area: str  # room, lobby, restaurant, spa
    consumption_kwh: float
    cost: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
class RoomAutomation(BaseModel):
    """Oda otomasyon kuralları"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_id: str
    
    # Automation rules
    auto_ac_on_checkin: bool = True
    preferred_temperature: int = 22
    auto_curtains: bool = True
    auto_lights: bool = True
    
    # Energy saving
    eco_mode_when_vacant: bool = True
    
    active: bool = True
