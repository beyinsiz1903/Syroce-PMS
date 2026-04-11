
from pydantic import BaseModel, ConfigDict


class ReservationReadFilters(BaseModel):
    model_config = ConfigDict(extra="ignore")

    limit: int = 30
    offset: int = 0
    start_date: str | None = None
    end_date: str | None = None
    status: str | None = None
