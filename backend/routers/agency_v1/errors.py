"""
Agency v1 — ADR donmus hata zarfi (Karar 1 / hata modeli).

FastAPI'nin varsayilan istek-dogrulama (RequestValidationError) ciktisi
`{"detail": [...]}` seklindedir ve ham `input` (PII tasiyabilir) ekolar. ADR ise
acente uclarinda `error_code`'un UST seviyede olmasini ve PII sizmamasini dondurdu.
Bu modul tek dogruluk kaynagidir: hem `server.py` global handler'i hem de izole
testler ayni zarfi uretmek icin buradan beslenir.

Yalniz sekil/zarf uretir; DB/secret/IO icermez.
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from .dtos import SCHEMA_VERSION

# Acente sozlesme yuzeyi. server.py global validation handler'i bu prefix'te
# ADR zarfina gecer; disindaki tum uclar mevcut (PII-scrub) davranisini korur.
AGENCY_PREFIX = "/api/agency/v1"


def is_agency_path(request: Request) -> bool:
    # Tam segment eslesme: salt `startswith` gelecekte `/api/agency/v10` gibi
    # FARKLI bir major surumu yanlislikla v1 zarfina dusururdu. v1'in kendisi veya
    # alt yollari (`/api/agency/v1/...`) kapsanir; baska bir sey kapsanmaz.
    path = request.url.path
    return path == AGENCY_PREFIX or path.startswith(AGENCY_PREFIX + "/")


def agency_validation_response() -> JSONResponse:
    """ADR 422 zarfi: error_code UST seviyede + schema_version. Alan-bazli detay
    (PII iceren `input`) acente uclarinda DISARI VERILMEZ (donmus karar)."""
    return JSONResponse(
        status_code=422,
        content={"error_code": "validation_error", "schema_version": SCHEMA_VERSION},
    )


def install_agency_validation_handler(app) -> None:
    """Path-scoped RequestValidationError handler kurar (izole test/app icin).

    server.py'de ZATEN global bir RequestValidationError handler'i var; orada bu
    fonksiyon CAGRILMAZ (ikinci kayit global PII-scrub davranisini ezerdi) —
    bunun yerine handler icinde `agency_validation_response()` cagrilir. Bu helper
    yalniz agency_v1 router'ini tek basina baglayan minimal app'ler icindir.
    """
    from fastapi.encoders import jsonable_encoder
    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def _agency_validation(request: Request, exc: RequestValidationError):
        if is_agency_path(request):
            return agency_validation_response()
        # Agency disi yollar: FastAPI varsayilan sekli (faithful fallback).
        return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})
