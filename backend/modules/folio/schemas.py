from pydantic import BaseModel, ConfigDict


class FolioBalanceProjection(BaseModel):
    model_config = ConfigDict(extra="allow")

    folio_id: str
    balance: float