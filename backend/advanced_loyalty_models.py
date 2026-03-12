"""
Advanced Loyalty Program Models
Gamification, tiers, perks, referrals
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
from enum import Enum
import uuid

class LoyaltyTier(str, Enum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"
    DIAMOND = "diamond"

class PointsTransaction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    points: int
    transaction_type: str  # earn, redeem, expire, bonus
    description: str
    booking_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class LoyaltyMember(BaseModel):
    guest_id: str
    tenant_id: str
    current_tier: LoyaltyTier
    total_points: int = 0
    lifetime_points: int = 0
    nights_stayed: int = 0
    total_spent: float = 0.0
    member_since: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tier_expiry: Optional[datetime] = None

class ReferralProgram(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    referrer_id: str
    referee_email: str
    referral_code: str
    status: str = "pending"  # pending, completed, rewarded
    reward_points: int = 500
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
