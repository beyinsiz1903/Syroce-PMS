"""
Agency v1 — router iskeleti (ADR Karar 3).

Adim 2 kapsami: KATI DTO dogrulamasi (bilinmeyen alan -> 422) + uc imzalari +
fail-closed davranis. Cekirdek is mantigi (atomik kilit, idempotency, HMAC imza
dogrulama — ADR Karar 2/4/5) ve DB gocu SONRAKI adimlarda baglanir; o zamana
kadar dort uc da (availability GET, reservations POST/PATCH/DELETE) ADR ortak
hata modeline gore fail-closed `not_configured` (503) doner — sahte basari
URETILMEZ.

Dogrulama sirasi: FastAPI istek dogrulamasi (govde/parametre/zorunlu header)
handler'dan ONCE calisir; gecersiz govde/eksik header -> 422. Gecerli istek
handler'a ulasir ve henuz hicbir alt sistem baglanmadigi icin fail-closed 503
not_configured doner. Kimlik/imza dogrulama bagimliligi (ADR Karar 2) Adim 3'te
eklenir.
"""
from __future__ import annotations

from fastapi import APIRouter, Header, Path, Query
from fastapi.responses import JSONResponse

from .dtos import (
    SCHEMA_VERSION,
    AgencyReservationCreate,
    AgencyReservationModify,
)

router = APIRouter(prefix="/api/agency/v1")

_ISO_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


def _not_configured() -> JSONResponse:
    """Fail-closed 503: alt sistem henuz baglanmadi. ADR ortak hata modeli —
    `error_code` UST seviyede (detail altinda DEGIL)."""
    return JSONResponse(
        status_code=503,
        content={"error_code": "not_configured", "schema_version": SCHEMA_VERSION},
    )


# Not: kimlik/imza header'lari (ADR Karar 2) her handler imzasinda opsiyonel
# tanimli (OpenAPI sozlesme belgelemesi). Gercek HMAC dogrulamasi Adim 3'te bir
# bagimlilik olarak baglanir; su an her uc kosulsuz fail-closed 503 doner.


@router.get("/availability")
async def get_availability(
    room_type_id: str = Query(..., min_length=1, max_length=120),
    arrival_date: str = Query(..., pattern=_ISO_DATE_PATTERN),
    departure_date: str = Query(..., pattern=_ISO_DATE_PATTERN),
    adults: int = Query(2, ge=1, le=30),
    children: int = Query(0, ge=0, le=30),
    authorization: str | None = Header(None),
    x_agency_timestamp: str | None = Header(None, alias="X-Agency-Timestamp"),
    x_agency_nonce: str | None = Header(None, alias="X-Agency-Nonce"),
    x_agency_signature: str | None = Header(None, alias="X-Agency-Signature"),
):
    """Musaitlik + fiyat sorgusu (ADR Karar 3.1). Baglayici teklif DEGILDIR.
    Cekirdek sorgu mantigi + imza dogrulama Adim 3'te baglanir; su an fail-closed 503."""
    return _not_configured()


@router.post("/reservations")
async def create_reservation(
    payload: AgencyReservationCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=200),
    authorization: str | None = Header(None),
    x_agency_timestamp: str | None = Header(None, alias="X-Agency-Timestamp"),
    x_agency_nonce: str | None = Header(None, alias="X-Agency-Nonce"),
    x_agency_signature: str | None = Header(None, alias="X-Agency-Signature"),
):
    """Rezervasyon olusturma (ADR Karar 3.2).

    DTO dogrulamasi burada gerceklesir (bilinmeyen alan/gecersiz tarih/uyumsuz
    schema_version/gecersiz status -> 422). Atomik envanter kilidi + idempotency +
    imza dogrulama Adim 1/3'te baglanir; su an fail-closed 503."""
    return _not_configured()


@router.patch("/reservations/{agency_reservation_id}")
async def modify_reservation(
    payload: AgencyReservationModify,
    agency_reservation_id: str = Path(..., min_length=1, max_length=120),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=200),
    authorization: str | None = Header(None),
    x_agency_timestamp: str | None = Header(None, alias="X-Agency-Timestamp"),
    x_agency_nonce: str | None = Header(None, alias="X-Agency-Nonce"),
    x_agency_signature: str | None = Header(None, alias="X-Agency-Signature"),
):
    """Rezervasyon degisikligi (ADR Karar 3.3). Cekirdek mantik + imza Adim 3; fail-closed 503."""
    return _not_configured()


@router.delete("/reservations/{agency_reservation_id}")
async def cancel_reservation(
    agency_reservation_id: str = Path(..., min_length=1, max_length=120),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=200),
    authorization: str | None = Header(None),
    x_agency_timestamp: str | None = Header(None, alias="X-Agency-Timestamp"),
    x_agency_nonce: str | None = Header(None, alias="X-Agency-Nonce"),
    x_agency_signature: str | None = Header(None, alias="X-Agency-Signature"),
):
    """Rezervasyon iptali (ADR Karar 3.3). Envanter serbest birakma DB-atomik
    (Adim 3) + imza dogrulama; su an fail-closed 503."""
    return _not_configured()
