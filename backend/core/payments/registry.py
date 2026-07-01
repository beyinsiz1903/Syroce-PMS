"""Tenant bazli saglayici kayit/secim katmani (fail-closed).

Cekirdek kod somut bir PSP'yi bilmez; aktif saglayici tenant ayarindan
(tenant_settings.active_payment_provider) okunur. Bos/gecersiz/kayitsiz veya
yapilandirilmamis saglayici -> ProviderNotConfigured (503). Sessiz fallback YOK.
"""

from __future__ import annotations

from collections.abc import Callable

from .contracts import PaymentProvider, ProviderNotConfigured

# Saglayici adi -> instance fabrikasi. Somut adaptorler import-time'da
# register_provider ile kendilerini kaydeder (Task #312+).
_REGISTRY: dict[str, Callable[[], PaymentProvider]] = {}


def register_provider(name: str, factory: Callable[[], PaymentProvider]) -> None:
    """Bir saglayici fabrikasini kanonik adiyla kaydet."""
    if not name:
        raise ValueError("provider name zorunlu")
    _REGISTRY[name.strip().lower()] = factory


def unregister_provider(name: str) -> None:
    """Test/temizlik icin kaydi kaldir."""
    _REGISTRY.pop(name.strip().lower(), None)


def available_providers() -> list[str]:
    """Kayitli saglayici adlari."""
    return sorted(_REGISTRY.keys())


async def get_active_provider_name(db, tenant_id: str) -> str | None:
    """Tenant'in aktif saglayici adini dondur (yoksa None)."""
    if not tenant_id:
        return None
    settings = (
        await db.tenant_settings.find_one(
            {"tenant_id": tenant_id},
            {"_id": 0, "active_payment_provider": 1},
        )
        or {}
    )
    raw = settings.get("active_payment_provider")
    if not raw or not isinstance(raw, str):
        return None
    return raw.strip().lower()


async def get_provider_for_tenant(db, tenant_id: str) -> PaymentProvider:
    """Tenant icin aktif, kayitli ve yapilandirilmis saglayiciyi dondur.

    Fail-closed: dort durumda da ProviderNotConfigured (503) atar —
    (1) tenant ayari bos, (2) bilinmeyen ad, (3) kayitsiz saglayici,
    (4) saglayici is_configured()=False (env/sir eksik).
    """
    name = await get_active_provider_name(db, tenant_id)
    if not name:
        raise ProviderNotConfigured("tenant icin aktif odeme saglayicisi ayarli degil")

    factory = _REGISTRY.get(name)
    if factory is None:
        raise ProviderNotConfigured(f"odeme saglayicisi kayitli degil: {name}")

    provider = factory()
    if not provider.is_configured():
        raise ProviderNotConfigured(f"odeme saglayicisi yapilandirilmamis: {name}")
    return provider
