from typing import Any

from pydantic import BaseModel, ConfigDict


class StayDetailProjection(BaseModel):
    model_config = ConfigDict(extra="allow")

    stay_id: str
    reservation: dict[str, Any]
    guest: dict[str, Any] | None = None
    room: dict[str, Any] | None = None
    folios: list[dict[str, Any]] = []
