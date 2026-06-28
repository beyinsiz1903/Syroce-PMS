"""MongoDB collection access for the supplies marketplace.

Uses the cross-tenant raw DB because vendors and orders span tenants.
Collections:
  - mp_vendors
  - mp_products
  - mp_orders
"""

from __future__ import annotations

import logging

from core.database import _raw_db

logger = logging.getLogger(__name__)

vendors_col = _raw_db["mp_vendors"]
products_col = _raw_db["mp_products"]
orders_col = _raw_db["mp_orders"]


async def ensure_indexes() -> None:
    """Create indexes (idempotent)."""
    try:
        await vendors_col.create_index("email", unique=True, name="uniq_vendor_email")
        await vendors_col.create_index("status", name="idx_vendor_status")

        await products_col.create_index("vendor_id", name="idx_product_vendor")
        await products_col.create_index("category", name="idx_product_category")
        await products_col.create_index("is_active", name="idx_product_active")
        await products_col.create_index([("name", "text"), ("description", "text")], name="text_product")

        await orders_col.create_index("order_no", unique=True, name="uniq_order_no")
        await orders_col.create_index("hotel_tenant_id", name="idx_order_tenant")
        await orders_col.create_index("vendor_id", name="idx_order_vendor")
        await orders_col.create_index("status", name="idx_order_status")
        await orders_col.create_index("created_at", name="idx_order_created")
    except Exception:
        logger.warning("supplies_market: index creation failed", exc_info=True)
