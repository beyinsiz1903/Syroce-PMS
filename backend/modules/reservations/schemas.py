from typing import Optional

from pydantic import BaseModel, ConfigDict


class ReservationReadFilters(BaseModel):
    model_config = ConfigDict(extra="ignore")

    limit: int = 30
    offset: int = 0
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None