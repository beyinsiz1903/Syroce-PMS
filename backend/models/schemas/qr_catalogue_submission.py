from pydantic import BaseModel, ConfigDict, Field


class StructuredItemValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity: int | None = Field(None, ge=1)
    selected_options: list[str] | None = Field(None, max_length=10)
    date_value: str | None = None
    time_value: str | None = None
    datetime_value: str | None = None

class CatalogueItemSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_code: str = Field(..., max_length=64)
    value: StructuredItemValue | None = None
    note: str | None = Field(None, max_length=1000)

class StructuredRequestSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: str = "tr"
    idempotency_key: str = Field(..., min_length=1, max_length=64)
    items: list[CatalogueItemSubmission] = Field(..., min_length=1, max_length=10)

class LegacyRequestSubmit(BaseModel):
    category: str
    description: str = Field(..., min_length=1, max_length=2000)
    priority: str = "normal"
    language: str = "tr"
    guest_name: str | None = None
    guest_phone: str | None = None
