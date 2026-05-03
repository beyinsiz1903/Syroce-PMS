"""Shared helpers/models for misc_router sub-modules."""
import logging
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from core.database import db
from models.enums import ROLE_PERMISSIONS, Permission
from models.schemas import User

logger = logging.getLogger(__name__)

DEFAULT_PUSH_CHANNELS = ["reservations", "housekeeping", "maintenance", "system"]


class PingTestRequest(BaseModel):
    target: str = "8.8.8.8"
    count: int = 4


def has_permission(role: Any, permission: Permission) -> bool:
    try:
        return permission in ROLE_PERMISSIONS.get(role, set())
    except Exception:
        return False


async def calculate_folio_balance(folio_id: str, tenant_id: str) -> float:
    from core.utils import calculate_folio_balance as _calc
    return await _calc(folio_id, tenant_id)


async def get_folio_details(folio_id: str, current_user: User) -> dict:
    tenant_id = current_user.tenant_id
    folio = await db.folios.find_one({'id': folio_id, 'tenant_id': tenant_id}, {'_id': 0})
    if not folio:
        raise HTTPException(status_code=404, detail="Folio not found")
    charges = await db.folio_charges.find(
        {'folio_id': folio_id, 'tenant_id': tenant_id}, {'_id': 0}
    ).to_list(1000)
    payments = await db.payments.find(
        {'folio_id': folio_id, 'tenant_id': tenant_id}, {'_id': 0}
    ).to_list(1000)
    return {'folio': folio, 'charges': charges, 'payments': payments}


def _scrub_encrypted(value):
    if isinstance(value, str) and value.startswith('aes256gcm:'):
        return ''
    return value or ''


try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator
