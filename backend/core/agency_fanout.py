"""
Agency v1 — Karar 7: Fan-Out (dagitim) kablolama (SXI kenari).
==============================================================
ADR docs/adr/2026-06-agency-pms-integration.md Karar 7.

PMS cekirdegindeki bir IC OTA outbox event'i (envanter blok/kaldirma, fiyat,
restriksiyon, rezervasyon) dispatch edilirken; bu modul o tenant'in AKTIF
sozlesmeli acentelerine **anonim** bir webhook event'i kuyruga atar (fan-out).
Gercek teslim Adim 4'teki core/agency_webhook.dispatch_agency_webhook ile yapilir.

Mimari (operatorun "Hibrit Yurutme Emri"):
  - Kapsam = Secenek B (rezervasyon kaynakli musaitlik degisimi DAHIL — aksi halde
    otel kendi sattiginda acente overbooking yapar).
  - Guvenlik = Secenek A (SIFIR PII). Booking event'lerinden misafir verisine
    (isim/telefon/kart/folio/guest_id) ASLA dokunulmaz; yalniz room_type_id, tarih
    ve envanter degisim yonu (+1/-1) cimbizlanir. Acenteye giden olay HER ZAMAN
    anonim `agency.inventory.availability.updated.v1`'dir; asla bir rezervasyon
    olayi (agency.booking.*) degildir.

Doktrin / izolasyon:
  - Emission servisleri (create_room_block, ai_pricing, reservation_state_machine,
    create_reservation, import_bridge) DEGISTIRILMEZ (Zero Bloat — cekirdek her yeni
    acente icin haritalama tablosu tasimaz; Karar 7).
  - agency_id<->tenant_id eslemesi cekirdege gomulmez; aktif acente listesi b2b
    sinirindaki routers.agency_contracts.list_active_agencies_for_tenant'tan cozulur.
  - Kaynak payload room_id+tarih tasir (room_type_id DEGIL). rooms.room_type ==
    agency dunyasindaki room_type_id (availability sorgusu da boyle eslestirir).
  - Fail-closed: room_type/tarih cozulemezse acente event'i ATILMAZ (room_id'yi
    acenteye SIZDIRMAKTANSA atla + uyar). allow_sell=True blok/kaldirma satilabilir
    envanteri degistirmez -> fan-out yok.
  - Idempotent: agency event entity_id = KAYNAK outbox event_id; (kaynak+agency)
    basina tek idempotency_key -> worker retry'inda cift fan-out olmaz, partial-crash
    sonrasi tamamlanir.
  - fan_out_agency_events ASLA raise ETMEZ ve kaynak event'in dispatch sonucundan
    BAGIMSIZDIR (acente, OTA teslimi basarisiz olsa bile bilgilendirilir). agency.*
    event'lerinde tetiklenmez (rekursiyon yok).
  - PII/secret loglanmaz; hata loglarinda yalniz exception SINIF adi kullanilir.
"""
from __future__ import annotations

import logging
from typing import Any

from core.agency_webhook import (
    AGENCY_INVENTORY_UPDATED,
    AGENCY_RATE_UPDATED,
    AGENCY_RESTRICTION_UPDATED,
)
from core.outbox_service import (
    BOOKING_CANCELLED,
    BOOKING_CREATED,
    BOOKING_NOSHOW,
    INVENTORY_AVAILABILITY_UPDATED,
    INVENTORY_BLOCKED,
    INVENTORY_RELEASED,
    RATE_UPDATED,
    RESTRICTION_UPDATED,
)

logger = logging.getLogger("core.agency_fanout")


# Hangi IC OTA event'leri acente fan-out'unu tetikler.
FANOUT_SOURCE_EVENT_TYPES = frozenset(
    {
        INVENTORY_BLOCKED,
        INVENTORY_RELEASED,
        INVENTORY_AVAILABILITY_UPDATED,
        RESTRICTION_UPDATED,
        RATE_UPDATED,
        BOOKING_CREATED,
        BOOKING_CANCELLED,
        BOOKING_NOSHOW,
    }
)

# Envanter degisim yonu: musaitligi DUSUREN vs ARTIRAN kaynaklar.
_DECREASE_EVENTS = frozenset({INVENTORY_BLOCKED, BOOKING_CREATED})
_INCREASE_EVENTS = frozenset({INVENTORY_RELEASED, BOOKING_CANCELLED, BOOKING_NOSHOW})
_BOOKING_EVENTS = frozenset({BOOKING_CREATED, BOOKING_CANCELLED, BOOKING_NOSHOW})


async def _resolve_room_type(db, tenant_id: str, room_id: str | None) -> str | None:
    """room_id -> rooms.room_type (== agency room_type_id). tenant-scoped, salt-okunur."""
    if not room_id:
        return None
    room = await db.rooms.find_one(
        {"id": room_id, "tenant_id": tenant_id},
        {"_id": 0, "room_type": 1},
    )
    if not room:
        return None
    return room.get("room_type") or None


async def _booking_room_and_dates(
    db, tenant_id: str, event: dict[str, Any]
) -> tuple[str | None, str | None, str | None]:
    """Booking event'i icin (room_id, check_in, check_out) cozer. Once payload'a bakar
    (zengin emitter'lar bunlari tasir); eksikse booking dokumanini SADECE bu uc alanin
    projeksiyonuyla okur (PII alanlari PROJE EDILMEZ -> loglara/akisa misafir verisi
    sizmaz). import_bridge gibi seyrek payload'lar bu yoldan tamamlanir."""
    payload = event.get("payload") or {}
    room_id = payload.get("room_id")
    date_from = payload.get("check_in")
    date_to = payload.get("check_out")
    if room_id and date_from and date_to:
        return room_id, date_from, date_to

    booking_id = event.get("entity_id") or payload.get("booking_id")
    if not booking_id:
        return room_id, date_from, date_to
    doc = await db.bookings.find_one(
        {"id": booking_id, "tenant_id": tenant_id},
        {"_id": 0, "room_id": 1, "check_in": 1, "check_out": 1},
    )
    if doc:
        room_id = room_id or doc.get("room_id")
        date_from = date_from or doc.get("check_in")
        date_to = date_to or doc.get("check_out")
    return room_id, date_from, date_to


async def _derive_agency_event(
    db, event: dict[str, Any]
) -> tuple[str, dict[str, Any]] | None:
    """Bir kaynak event'i (agency_event_type, anonim_payload) ikilisine cevirir.
    Mappable degilse / no-op ise None doner. Donen payload'a agency_id EKLENMEZ
    (enqueue_agency_webhook_event ekler) ve ASLA PII tasimaz."""
    event_type = event.get("event_type")
    tenant_id = event.get("tenant_id") or ""
    payload = event.get("payload") or {}

    # ── Fiyat: tenant+tarih seviyesi (AI auto-publish); room_type tasimaz. ──
    if event_type == RATE_UPDATED:
        date = payload.get("date")
        if not date:
            return None
        base: dict[str, Any] = {"date": date, "source_event_type": event_type}
        if payload.get("recommended_rate") is not None:
            base["rate"] = payload.get("recommended_rate")
        if payload.get("strategy") is not None:
            base["strategy"] = payload.get("strategy")
        return AGENCY_RATE_UPDATED, base

    # ── Restriksiyon: su an ic emitter yok; guvenli alanlari passthrough. ──
    if event_type == RESTRICTION_UPDATED:
        base = {"source_event_type": event_type}
        room_type_id = payload.get("room_type") or payload.get("room_type_id")
        if room_type_id:
            base["room_type_id"] = room_type_id
        for k in ("date", "date_start", "date_end", "restriction_type", "value"):
            if payload.get(k) is not None:
                base[k] = payload.get(k)
        return AGENCY_RESTRICTION_UPDATED, base

    # ── Envanter degisimi ailesi (blok/kaldirma + rezervasyon) ──
    if event_type in (INVENTORY_BLOCKED, INVENTORY_RELEASED):
        # allow_sell=True -> satilabilir envanter degismez -> acenteye sinyal yok.
        if payload.get("allow_sell"):
            return None
        room_id = payload.get("room_id")
        date_from = payload.get("date_start") or payload.get("start_date")
        date_to = payload.get("date_end") or payload.get("end_date")
    elif event_type in _BOOKING_EVENTS:
        room_id, date_from, date_to = await _booking_room_and_dates(db, tenant_id, event)
    elif event_type == INVENTORY_AVAILABILITY_UPDATED:
        room_id = payload.get("room_id")
        date_from = payload.get("date_start") or payload.get("check_in")
        date_to = payload.get("date_end") or payload.get("check_out")
    else:
        return None

    room_type_id = await _resolve_room_type(db, tenant_id, room_id)
    if not room_type_id or not date_from or not date_to:
        # Fail-closed: room_id'yi acenteye sizdirmaktansa bu sinyali atla.
        logger.warning(
            "Agency fan-out skipped (unresolved room_type/date): event=%s type=%s",
            event.get("id"), event_type,
        )
        return None

    if event_type in _DECREASE_EVENTS:
        change_kind, change = "decrease", -1
    elif event_type in _INCREASE_EVENTS:
        change_kind, change = "increase", 1
    else:  # INVENTORY_AVAILABILITY_UPDATED (yon bilinmiyor -> acente yeniden sorgular)
        change_kind, change = "unknown", 0

    base = {
        "room_type_id": room_type_id,
        "date_from": date_from,
        "date_to": date_to,
        "change_kind": change_kind,
        "change": change,
        "source_event_type": event_type,
    }
    return AGENCY_INVENTORY_UPDATED, base


async def fan_out_agency_events(event: dict[str, Any]) -> int:
    """Bir kaynak OTA outbox event'i icin aktif acentelere anonim webhook event'i
    kuyruga atar. Kuyruga eklenen agency event sayisini doner.

    Sozlesme: ASLA raise ETMEZ (kaynak dispatch'i bozmaz), kaynak dispatch sonucundan
    BAGIMSIZDIR, agency.* event'lerinde tetiklenmez (rekursiyon yok), PII tasimaz.
    """
    try:
        event_type = event.get("event_type")
        if event_type not in FANOUT_SOURCE_EVENT_TYPES:
            return 0
        tenant_id = event.get("tenant_id")
        source_event_id = event.get("id")
        if not tenant_id or not source_event_id:
            return 0

        from core.database import db

        derived = await _derive_agency_event(db, event)
        if not derived:
            return 0
        agency_event_type, base_payload = derived

        from routers.agency_contracts import list_active_agencies_for_tenant

        agency_ids = await list_active_agencies_for_tenant(tenant_id)
        if not agency_ids:
            return 0

        from core.agency_webhook import enqueue_agency_webhook_event

        correlation_id = event.get("correlation_id")
        count = 0
        for agency_id in agency_ids:
            # Idempotency: payload'dan BAGIMSIZ, stabil dedup key. (kaynak event_id,
            # agency_id) basina tek kayit; worker retry'inda turetilmis payload
            # (orn. import_bridge'de canli booking read'i) degisse bile DuplicateKey
            # -> no-op, cift fan-out olmaz.
            dedup_key = (
                f"agency_fanout:{tenant_id}:{agency_id}:"
                f"{source_event_id}:{agency_event_type}"
            )
            try:
                await enqueue_agency_webhook_event(
                    db,
                    tenant_id=tenant_id,
                    agency_id=agency_id,
                    event_type=agency_event_type,
                    entity_type="agency_fanout",
                    entity_id=source_event_id,
                    payload=dict(base_payload),
                    correlation_id=correlation_id,
                    idempotency_key=dedup_key,
                )
                count += 1
            except Exception as e:  # bir acente hatasi digerlerini engellemez
                logger.warning(
                    "Agency fan-out enqueue failed: source=%s agency=%s err=%s",
                    source_event_id, agency_id, type(e).__name__,
                )
        return count
    except Exception as e:  # fan-out kaynak teslimini ASLA bozmaz
        logger.warning(
            "Agency fan-out error: event=%s err=%s",
            event.get("id"), type(e).__name__,
        )
        return 0
