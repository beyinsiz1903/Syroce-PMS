"""
Domain Router: Syroce Contact Center (omnichannel) — Faz 0 iskelet.

Çift kapı:
1. Entitlement: ``/api/contact-center/`` yolu ROUTE_MODULE_MAP üzerinden
   ``contact_center`` modülüne bağlı (kiracı planı/abonelik kontrolü ASGI
   middleware'de — entitled değilse 403 ENTITLEMENT_DENIED).
2. RBAC: ``require_module("contact_center")`` rol allowlist'i (call_center_agent,
   front_desk/resepsiyon, supervisor, admin, super_admin).

Faz 0'da yalnızca okuma/sağlık uçları; gönderim ucu YOK (gerçek transport Faz 1).
Tüm sorgular kiracıya göre filtrelenir; fake veri döndürülmez.
"""
from fastapi import APIRouter, Depends

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_module

from domains.contact_center.provider import get_communication_provider

router = APIRouter(prefix="/api", tags=["contact-center-domain"])

# Açık-metin PII / şifreli alanlar (telefon + görünen ad) listeden ASLA
# dışarı verilmez; çözme yalnızca Faz 1 read-boundary'sinde yapılacak.
_CONVERSATION_PROJECTION = {
    "_id": 0,
    "caller_id_enc": 0,
    "caller_id_hash": 0,
    "caller_display_name_enc": 0,
}


@router.get("/contact-center/health")
async def contact_center_health(
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    """Modül + sağlayıcı sağlığı (sır/PII içermez)."""
    provider = get_communication_provider()
    return {
        "module": "contact_center",
        "status": "ok",
        "phase": "0",
        "provider": await provider.check_health(),
    }


@router.get("/contact-center/conversations")
async def list_conversations(
    status: str | None = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    _mod=Depends(require_module("contact_center")),
):
    """Kiracıya ait konuşmaları listeler (açık-metin PII döndürmez).

    Faz 0: gerçek veriden okur; kayıt yoksa boş liste döner (fake data YOK).
    """
    safe_limit = max(1, min(int(limit or 50), 200))
    query: dict = {"tenant_id": current_user.tenant_id}
    if status:
        query["status"] = status
    cursor = (
        db.contact_center_conversations.find(query, _CONVERSATION_PROJECTION)
        .sort("last_message_at", -1)
        .limit(safe_limit)
    )
    items = await cursor.to_list(length=safe_limit)
    return {"count": len(items), "items": items}
