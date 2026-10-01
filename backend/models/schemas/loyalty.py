"""Auto-split from schemas.py — domain: loyalty."""

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from models.enums import (
    LoyaltyTier,
)


# Loyalty Models
class LoyaltyProgramCreate(BaseModel):
    guest_id: str
    tier: LoyaltyTier = LoyaltyTier.BRONZE
    points: int = 0
    lifetime_points: int = 0


class LoyaltyProgram(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    tier: LoyaltyTier = LoyaltyTier.BRONZE
    points: int = 0
    lifetime_points: int = 0
    last_activity: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LoyaltyTransactionCreate(BaseModel):
    guest_id: str
    points: int = Field(..., gt=0, le=10_000_000)
    transaction_type: Literal["earned", "redeemed"]
    description: str = Field(..., min_length=2, max_length=500)


class LoyaltyTransaction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    points: int
    transaction_type: str
    description: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
