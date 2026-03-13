"""
ARI (Availability, Rates, Inventory) Push Engine.

Event-driven push model:
  PMS change → ARI event → buffer → coalesce → delta compile → rate-limited push → ack/retry/drift
"""
