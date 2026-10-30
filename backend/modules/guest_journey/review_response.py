"""Shared JSON contract for staff review replies (storage, not provider delivery)."""
from pydantic import BaseModel, Field, field_validator


class ReviewResponsePayload(BaseModel):
    response: str = Field(strict=True, min_length=1, max_length=2000)

    @field_validator("response")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Response must not be blank")
        return value
