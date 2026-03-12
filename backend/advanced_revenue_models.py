"""
Advanced Revenue Management Models
AI-powered pricing, forecasting, yield management
"""
from enum import Enum

class PricingStrategy(str, Enum):
    """Fiyatlandırma stratejisi"""
    AGGRESSIVE = "aggressive"  # Yüksek fiyat, yüksek gelir
    BALANCED = "balanced"  # Dengeli
    OCCUPANCY_FOCUSED = "occupancy_focused"  # Doluluk odaklı

class DemandLevel(str, Enum):
    """Talep seviyesi"""
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"
