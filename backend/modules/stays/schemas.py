from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict


class StayDetailProjection(BaseModel):
    model_config = ConfigDict(extra="allow")

    stay_id: str
    reservation: Dict[str, Any]
    guest: Optional[Dict[str, Any]] = None
    room: Optional[Dict[str, Any]] = None
    folios: list[Dict[str, Any]] = []