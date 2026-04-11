"""
AI Features Models
Chatbot, sentiment analysis, predictive analytics
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
import uuid

class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: Optional[str] = None
    session_id: str
    message: str
    sender: str  # guest or assistant
    intent: Optional[str] = None
    sentiment: Optional[str] = None  # positive, neutral, negative
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class GuestSentiment(BaseModel):
    guest_id: str
    tenant_id: str
    overall_sentiment: str  # positive, neutral, negative
    sentiment_score: float  # -1.0 to 1.0
    based_on_reviews: int
    based_on_interactions: int
    last_negative_incident: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class PredictiveInsight(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    insight_type: str  # no_show_risk, churn_risk, upsell_opportunity
    target_id: str  # guest_id or booking_id
    prediction: str
    confidence: float
    recommended_action: Optional[str] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
