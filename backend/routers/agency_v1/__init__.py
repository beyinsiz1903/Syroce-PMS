"""
Agency <-> PMS v1 — Servisler-arasi (S2S) entegrasyon sozlesmesi.

Donmus kontrat: docs/adr/2026-06-agency-pms-integration.md

Bu paket, ADR'nin Adim 2 cektirmesidir: Karar 1 tel-formatina (kanonik modele
1:1 hizali) birebir karsilik gelen KATI (strict) DTO'lar + router iskeleti.
Bilinmeyen alan -> 422 (fail-closed, sessiz yutma YOK). Cekirdek is mantigi
(atomik kilit, idempotency, imza dogrulama) ile veritabani gocu sonraki
adimlarda baglanir; o zamana kadar uclar fail-closed `not_configured` (503)
doner — sahte basari URETILMEZ.

Public API: from routers.agency_v1 import router
"""

from .router import router

__all__ = ["router"]
