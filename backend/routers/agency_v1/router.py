"""
Agency v1 — router (ADR Karar 3).

Adim 3 kapsami: gercek HMAC kimlik dogrulama (Karar 2, `verify_agency_signature`
dependency) + idempotency (Karar 4) + atomik FLOATING envanter claim (Karar 5,
operatör onayli "Floating + ertelenmis otomatik atama" modeli) BAGLANIR.

Bagli uclar:
  - POST /reservations  -> tam: HMAC -> DTO -> idempotency begin (in-flight) ->
    atomik floating envanter claim -> complete. Sira DONMUS; envanter ASLA
    idempotency slotundan ONCE dusmez (overbooking yok).
  - DELETE /reservations/{id} -> tam: HMAC -> idempotency -> booking bul (tenant+
    agency scope) -> terminal-state guard -> DB-atomik release -> complete.

Bu turda fail-closed 503 (not_configured) KALAN uclar — sahte basari URETILMEZ:
  - GET /availability  -> `available` (sellable) icin kaynak HAZIR (room_type
    inventory view) ANCAK ADR sozlesmesi `sell_rate` + `restrictions` (stop-sale/
    min-stay) da ister; bunlarin guvenilir OKUMA read-model'i henuz YOK. Uydurma
    fiyat/kisitlama dondurmek fail-closed/no-fake-green doktrinini ihlal eder
    (acik stop-sale gunune satis acabilir) -> bu uc, rate/restriction read-model
    karari verilene dek fail-closed 503.
  - PATCH /reservations/{id} -> envanter boyutu (tarih/oda_tipi/oda_sayisi)
    degisen modify, atomik "yeni-claim-sonra-eski-release" diff primitifi
    gerektirir (kismi durum/overbooking riski olmadan). Bu primitif ayri/dikkatli
    bir adim; o gelene dek modify fail-closed 503 (yarim-pisirme YOK).

Tum uclar `verify_agency_signature` ile kimlik dogrular (kimlik sunucu tarafinda
key_id'den cozulur; govdeye guvenilmez). Secret/imza/PII loglanmaz.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, Path, Query, Request
from fastapi.responses import JSONResponse

from core.database import db
from shared_kernel.idempotency import build_request_hash

from .auth import verify_agency_signature
from .dtos import (
    SCHEMA_VERSION,
    AgencyReservationCreate,
    AgencyReservationModify,
)
from .errors import agency_error_response
from .idempotency_runtime import begin_agency_idempotency
from .inventory import (
    InventoryConflict,
    claim_floating_inventory,
    release_reservation_inventory,
)

router = APIRouter(prefix="/api/agency/v1")

logger = logging.getLogger("agency_v1.router")

_ISO_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"

# Iptale kapali (terminal/devam eden) durumlar: acente bunlari geri alamaz.
_TERMINAL_OR_INHOUSE = frozenset(
    {"checked_in", "in_house", "checked_out", "no_show"}
)


def _not_configured() -> JSONResponse:
    """Fail-closed 503: alt sistem henuz baglanmadi. ADR ortak hata modeli."""
    return JSONResponse(
        status_code=503,
        content={"error_code": "not_configured", "schema_version": SCHEMA_VERSION},
    )


def _idempotency_dispatch(result) -> JSONResponse | None:
    """begin_agency_idempotency sonucunu ADR zarfina esler. `acquired` -> None
    (cagiran devam eder); diger durumlar -> hazir JSONResponse."""
    if result.status == "replay":
        # Tamamlanmis islemin sifreli-cozulmus yaniti (crypto yoksa {} olabilir).
        return JSONResponse(
            status_code=int(result.status_code or 200),
            content=result.response or {
                "error_code": "not_configured",
                "schema_version": SCHEMA_VERSION,
            },
        )
    if result.status == "conflict":
        return agency_error_response(422, "idempotency_conflict")
    if result.status == "in_progress":
        return agency_error_response(409, "idempotency_in_progress")
    return None


async def _finalize_complete(lock, response_body: dict, status_code: int) -> None:
    """Idempotency slotunu tamamla (soguk cache yaz). `complete()` False donerse
    (processing slot TTL/sweep nedeniyle kayip) bu EXPLICIT ele alinir: islem
    KALICI (booking persist edildi) oldugundan basari yaniti DOGRUDUR; sahte hata
    URETILMEZ. Replay cache yazilamadigi gozlemlenir/loglanir (PII/secret YOK) —
    ayni-anahtar retry'da mukerrer uretim, create'teki external_id domain-guard ve
    cancel'in idempotent (status=cancelled) dogasi ile zaten kapalidir."""
    cached = await lock.complete(response_body, status_code=status_code)
    if cached is False:
        logger.warning(
            "agency idempotency completion not cached (slot swept); response "
            "served from live result, replay will re-resolve via domain guard"
        )


def _map_create_to_booking(
    payload: AgencyReservationCreate, *, tenant_id: str, agency_id: str
) -> dict:
    """KATI DTO -> kanonik PMS booking dokumani (floating; room_id check-in'de).

    Misafir PII alanlari dokumanda tasinir; claim_floating_inventory persist'ten
    ONCE field-level sifreler (create_booking_atomic ile ayni semantik). Burada
    PII LOGLANMAZ.
    """
    g = payload.guest
    guest_name = (
        f"{g.first_name} {g.last_name}".strip()
        or g.company_name
        or "Agency Guest"
    )
    booking_id = str(uuid.uuid4())
    meal_plan = getattr(payload.meal_plan, "value", payload.meal_plan)
    return {
        "id": booking_id,
        "tenant_id": tenant_id,
        "agency_id": agency_id,
        "source": "agency",
        "external_id": payload.agency_reservation_id,
        "confirmation_number": payload.confirmation_number or "",
        "room_type": payload.room_type_id,
        "rate_plan_id": payload.rate_plan_id,
        "check_in": payload.arrival_date,
        "check_out": payload.departure_date,
        "room_count": payload.room_count,
        "adults": payload.occupancy.adults,
        "children": payload.occupancy.children,
        "child_ages": list(payload.occupancy.child_ages),
        "meal_plan": meal_plan,
        "status": "confirmed",
        "allocation_source": "agency_floating",
        "guest_name": guest_name,
        "guest": payload.guest.model_dump(),
        "pricing": payload.pricing.model_dump(),
        "commission": payload.commission.model_dump() if payload.commission else None,
        "payment_type": (
            payload.payment_type.value if payload.payment_type else None
        ),
        "special_requests": payload.special_requests,
        "created_at": datetime.now(UTC).isoformat(),
        "correlation_id": booking_id,
    }


@router.get("/availability")
async def get_availability(
    room_type_id: str = Query(..., min_length=1, max_length=120),
    arrival_date: str = Query(..., pattern=_ISO_DATE_PATTERN),
    departure_date: str = Query(..., pattern=_ISO_DATE_PATTERN),
    adults: int = Query(2, ge=1, le=30),
    children: int = Query(0, ge=0, le=30),
    identity: dict = Depends(verify_agency_signature),
):
    """Musaitlik + fiyat sorgusu (ADR Karar 3.1). Baglayici teklif DEGILDIR.

    Kimlik dogrulanir; ANCAK ADR yaniti `sell_rate` + `restrictions` icin guvenilir
    read-model henuz yok -> fail-closed 503 (uydurma fiyat/kisitlama YOK)."""
    return _not_configured()


@router.post("/reservations")
async def create_reservation(
    payload: AgencyReservationCreate,
    request: Request,
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=1, max_length=200
    ),
    identity: dict = Depends(verify_agency_signature),
):
    """Rezervasyon olusturma (ADR Karar 3.2) — FLOATING model.

    Sira (DONMUS): HMAC (dependency) -> DTO (FastAPI) -> idempotency begin
    (in-flight slot) -> atomik floating envanter claim -> complete. Envanter ASLA
    idempotency slotundan ONCE dusmez (overbooking yok)."""
    tenant_id = identity["tenant_id"]
    agency_id = identity["agency_id"]

    fingerprint = build_request_hash(payload.model_dump())
    begin = await begin_agency_idempotency(
        db,
        tenant_id=tenant_id,
        agency_id=agency_id,
        method="POST",
        path=request.url.path,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
    )
    dispatched = _idempotency_dispatch(begin)
    if dispatched is not None:
        return dispatched

    lock = begin.lock
    try:
        # Domain-level idempotency: agency_reservation_id rezervasyonun DOGAL
        # anahtaridir. Idempotency-Key cache'i kisa "processing grace" sonrasi
        # sweep edilebilir; bu durumda ayni anahtarla retry yeni slot "acquired"
        # alip MUKERRER booking/claim uretebilir. Bu guard, ayni (tenant, agency,
        # external_id) icin iptal-edilmemis bir booking varsa onu IDEMPOTENT
        # dondurur (yeni claim YOK) -> sweep-retry duplicate riski kapanir.
        existing = await db.bookings.find_one(
            {
                "tenant_id": tenant_id,
                "agency_id": agency_id,
                "source": "agency",
                "external_id": payload.agency_reservation_id,
                "status": {"$ne": "cancelled"},
            },
            {"_id": 0, "id": 1, "confirmation_number": 1},
        )
        if existing:
            response_body = {
                "pms_reservation_id": existing["id"],
                "confirmation_number": existing.get("confirmation_number")
                or (payload.confirmation_number or ""),
                "status": "confirmed",
                "schema_version": SCHEMA_VERSION,
            }
            await _finalize_complete(lock, response_body, 201)
            return JSONResponse(status_code=201, content=response_body)

        booking_doc = _map_create_to_booking(
            payload, tenant_id=tenant_id, agency_id=agency_id
        )
        try:
            await claim_floating_inventory(booking_doc)
        except InventoryConflict as ic:
            # Henuz kalici booking yazilmadi (claim compensation yapti) -> slot
            # serbest birak; acente conflict_date/available ile bilgilendirilir.
            await lock.release()
            return agency_error_response(
                409,
                "inventory_conflict",
                conflict_date=ic.conflict_date,
                room_type_id=payload.room_type_id,
                available=ic.available,
            )

        response_body = {
            "pms_reservation_id": booking_doc["id"],
            "confirmation_number": payload.confirmation_number or "",
            "status": "confirmed",
            "schema_version": SCHEMA_VERSION,
        }
        await _finalize_complete(lock, response_body, 201)
        return JSONResponse(status_code=201, content=response_body)
    except Exception:
        # Beklenmeyen hata: slotu serbest birak (booking persist edilmediyse
        # acente retry edebilir) ve global handler'a birak (PII-scrub).
        await lock.release()
        raise


@router.patch("/reservations/{agency_reservation_id}")
async def modify_reservation(
    payload: AgencyReservationModify,
    agency_reservation_id: str = Path(..., min_length=1, max_length=120),
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=1, max_length=200
    ),
    identity: dict = Depends(verify_agency_signature),
):
    """Rezervasyon degisikligi (ADR Karar 3.3).

    Kimlik dogrulanir; ANCAK envanter boyutu degisen modify atomik diff primitifi
    gerektirir (kismi durum/overbooking riski olmadan) -> bu primitif gelene dek
    fail-closed 503 (yarim-pisirme YOK)."""
    return _not_configured()


@router.delete("/reservations/{agency_reservation_id}")
async def cancel_reservation(
    request: Request,
    agency_reservation_id: str = Path(..., min_length=1, max_length=120),
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=1, max_length=200
    ),
    identity: dict = Depends(verify_agency_signature),
):
    """Rezervasyon iptali (ADR Karar 3.3). Envanter serbest birakma DB-atomik.

    Sira: HMAC -> idempotency begin -> booking bul (tenant+agency scope) ->
    terminal-state guard -> DB-atomik release -> status=cancelled -> complete."""
    tenant_id = identity["tenant_id"]
    agency_id = identity["agency_id"]

    fingerprint = build_request_hash({"agency_reservation_id": agency_reservation_id})
    begin = await begin_agency_idempotency(
        db,
        tenant_id=tenant_id,
        agency_id=agency_id,
        method="DELETE",
        path=request.url.path,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
    )
    dispatched = _idempotency_dispatch(begin)
    if dispatched is not None:
        return dispatched

    lock = begin.lock
    try:
        # Tenant + agency scope: baska tenant/agency'nin rezervasyonu GORUNMEZ
        # (cross-tenant/agency IDOR kapali).
        booking = await db.bookings.find_one(
            {
                "tenant_id": tenant_id,
                "agency_id": agency_id,
                "source": "agency",
                "external_id": agency_reservation_id,
            },
            {"_id": 0, "id": 1, "status": 1},
        )
        if not booking:
            await lock.release()
            return agency_error_response(404, "not_found")

        status = booking.get("status")
        if status in _TERMINAL_OR_INHOUSE:
            await lock.release()
            return agency_error_response(409, "terminal_state")

        if status != "cancelled":
            await release_reservation_inventory(
                tenant_id, booking["id"], reason="agency_cancelled"
            )
            await db.bookings.update_one(
                {"tenant_id": tenant_id, "id": booking["id"]},
                {
                    "$set": {
                        "status": "cancelled",
                        "cancel_source": "agency",
                        "cancelled_at": datetime.now(UTC).isoformat(),
                    }
                },
            )

        response_body = {
            "pms_reservation_id": booking["id"],
            "status": "cancelled",
            "schema_version": SCHEMA_VERSION,
        }
        await _finalize_complete(lock, response_body, 200)
        return JSONResponse(status_code=200, content=response_body)
    except Exception:
        await lock.release()
        raise
