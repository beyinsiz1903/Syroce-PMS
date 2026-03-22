"""
Payment Gateway Integration Models
Stripe, PayPal, Crypto payments
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
from enum import Enum
import uuid

class PaymentMethod(str, Enum):
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    PAYPAL = "paypal"
    CRYPTO = "crypto"
    BANK_TRANSFER = "bank_transfer"
    CASH = "cash"

class PaymentIntent(BaseModel):
    """Payment intent for Stripe/PayPal"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    booking_id: str
    amount: float
    currency: str = "EUR"
    payment_method: PaymentMethod
    
    # Gateway specific
    stripe_payment_intent_id: Optional[str] = None
    paypal_order_id: Optional[str] = None
    crypto_address: Optional[str] = None
    
    # Status
    status: str = "pending"  # pending, processing, succeeded, failed
    
    # Installment
    installment_count: Optional[int] = None
    installment_amount: Optional[float] = None
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
