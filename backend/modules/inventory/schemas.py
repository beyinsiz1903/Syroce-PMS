from typing import Optional

from pydantic import BaseModel, ConfigDict


class AvailabilityQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")

    check_in: str
    check_out: str
    room_type: Optional[str] = None
