"""
PMS Shared Helpers — Pure utility functions used by multiple PMS sub-routers.

Rules (per project convention):
- Pure helpers ONLY — no side effects, no domain logic.
- No business rules, no cross-domain dependencies.
"""

from core.database import db


async def get_guest_name(guest_id: str, tenant_id: str) -> str:
    """Look up guest name by ID."""
    guest = await db.guests.find_one(
        {"id": guest_id, "tenant_id": tenant_id},
        {"_id": 0, "first_name": 1, "last_name": 1, "name": 1},
    )
    if not guest:
        return "Unknown Guest"
    if guest.get("name"):
        return guest["name"]
    return f"{guest.get('first_name', '')} {guest.get('last_name', '')}".strip() or "Unknown Guest"
