"""
DEPRECATED — Payment Gateway Integration Models

These models are superseded by the canonical definitions in:
  - models/enums.py  (PaymentMethod, PaymentStatus, etc.)
  - models/schemas.py  (PaymentIntent, PaymentTransaction, etc.)

This file is kept as a re-export shim so any stale imports continue to work.
It will be removed in a future cleanup pass.
"""
import warnings as _w
_w.warn(
    "payment_gateway_models is deprecated. "
    "Import from models.enums / models.schemas instead.",
    DeprecationWarning,
    stacklevel=2,
)

from models.enums import PaymentMethod, PaymentStatus

__all__ = ["PaymentMethod", "PaymentStatus"]
