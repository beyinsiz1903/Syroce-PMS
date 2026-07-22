"""
Agency v1 — router iskeleti uctan uca testleri (ADR Karar 3).

Saf testtir: calisan backend / canli Mongo / secret gerektirmez. Minimal bir
FastAPI app'e yalniz agency_v1 router'i baglanir. Iki sinir dogrulanir:

  1. FAIL-CLOSED: kimligi DOGRULANMIS gecerli istek handler'a ulasir; bu uclarin
     alt sistemi (availability rate/restriction read-model; atomik modify diff
     primitifi) henuz baglanmadigi icin ADR ortak hata modeline gore 503
     not_configured doner (error_code UST seviyede). Sahte basari YOK. NOT: create
     ve cancel ARTIK baglidir (503 DEGIL) -> onlarin uctan uca davranisi
     tests/test_agency_v1_step3_router_wiring.py'de dogrulanir; burada KAPSAM DISI.
  2. KATI DTO/parametre dogrulamasi: gecersiz govde/parametre/eksik zorunlu
     header -> 422. Bilinmeyen alan sessizce yutulmaz. ADR (Karar 1) 422 govdesinin
     de ortak hata zarfini (error_code UST seviyede + schema_version, PII detay YOK)
     dondurmesini dondu; bunu uretmek icin minimal app'e production ile AYNI zarf
     kaynagi (routers.agency_v1.errors) baglanir.

Router artik `verify_agency_signature` dependency'sini TUM uclarda zorunlu kilar;
gercek imza dogrulamasi T3'te (test_agency_v1_step3_hmac_auth.py) ayri test edilir.
Burada amac AUTH SONRASI davranisi (fail-closed 503 + DTO 422 zarfi) izole etmek
oldugundan dependency, sabit bir kimlikle override edilir (auth zayiflatma DEGIL;
auth'un kendisi baska yerde test edilir). Sahte-yesil URETILMEZ.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.agency_v1 import router as agency_router
from routers.agency_v1.auth import verify_agency_signature
from routers.agency_v1.dtos import SCHEMA_VERSION
from routers.agency_v1.errors import install_agency_validation_handler
from tests.test_agency_v1_dtos import _valid_create_payload

_IDEMPOTENCY = {"Idempotency-Key": "idem-1"}


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(agency_router)
    # Production'da server.py global RequestValidationError handler'i agency
    # yollarinda ADR zarfini dondurur; izole app'te ayni zarf kaynagini bagla.
    install_agency_validation_handler(app)
    # Auth SONRASI davranisi izole et: imza dogrulamasi T3'te test edilir.
    app.dependency_overrides[verify_agency_signature] = lambda: {
        "key_id": "K",
        "tenant_id": "T-1",
        "agency_id": "A-1",
    }
    return TestClient(app, raise_server_exceptions=True)


def _assert_adr_error_envelope(resp, *, expected_status: int, expected_code: str) -> None:
    """ADR ortak hata zarfi: error_code UST seviyede + schema_version; PII/detay YOK."""
    assert resp.status_code == expected_status
    body = resp.json()
    assert body["error_code"] == expected_code
    assert body["schema_version"] == SCHEMA_VERSION
    assert "detail" not in body  # error_code UST seviyede, detail altinda DEGIL


# ── 1) Fail-closed: gecerli istek -> 503 not_configured (ust-seviye error_code) ──


_VALID_MODIFY = {"schema_version": SCHEMA_VERSION, "special_requests": "geç giris"}


@pytest.mark.parametrize(
    "method,path,body",
    [
        # Yalniz HENUZ baglanmamis uclar: availability (rate/restriction read-model
        # yok) + modify (atomik diff primitifi yok). create/cancel ARTIK bagli ->
        # buradan cikarildi (test_agency_v1_step3_router_wiring.py kapsar).
        ("get", "/api/agency/v1/availability"
            "?room_type_id=RT-1&arrival_date=2026-07-01&departure_date=2026-07-03", None),
        ("patch", "/api/agency/v1/reservations/AG-123", _VALID_MODIFY),
    ],
)
def test_endpoints_fail_closed_not_configured(method, path, body):
    with _make_client() as client:
        kwargs = {"headers": dict(_IDEMPOTENCY)}
        if body is not None:
            kwargs["json"] = body
        resp = getattr(client, method)(path, **kwargs)
        _assert_adr_error_envelope(resp, expected_status=503, expected_code="not_configured")


# ── 2) Strict dogrulama -> 422 (handler'a ulasmadan) ─────────────


def test_create_unknown_field_returns_422():
    with _make_client() as client:
        payload = _valid_create_payload()
        payload["totally_unknown"] = "x"
        resp = client.post("/api/agency/v1/reservations", json=payload, headers=_IDEMPOTENCY)
        _assert_adr_error_envelope(resp, expected_status=422, expected_code="validation_error")


def test_create_bad_date_returns_422():
    with _make_client() as client:
        payload = _valid_create_payload()
        payload["departure_date"] = payload["arrival_date"]
        resp = client.post("/api/agency/v1/reservations", json=payload, headers=_IDEMPOTENCY)
        _assert_adr_error_envelope(resp, expected_status=422, expected_code="validation_error")


def test_create_missing_idempotency_key_returns_422():
    with _make_client() as client:
        resp = client.post("/api/agency/v1/reservations", json=_valid_create_payload())
        _assert_adr_error_envelope(resp, expected_status=422, expected_code="validation_error")


def test_create_missing_currency_returns_422():
    with _make_client() as client:
        payload = _valid_create_payload()
        del payload["pricing"]["currency"]  # ADR: currency zorunlu
        resp = client.post("/api/agency/v1/reservations", json=payload, headers=_IDEMPOTENCY)
        _assert_adr_error_envelope(resp, expected_status=422, expected_code="validation_error")


def test_availability_missing_required_query_returns_422():
    with _make_client() as client:
        resp = client.get("/api/agency/v1/availability?room_type_id=RT-1")
        _assert_adr_error_envelope(resp, expected_status=422, expected_code="validation_error")


def test_availability_bad_date_pattern_returns_422():
    with _make_client() as client:
        resp = client.get(
            "/api/agency/v1/availability"
            "?room_type_id=RT-1&arrival_date=07-01-2026&departure_date=2026-07-03"
        )
        _assert_adr_error_envelope(resp, expected_status=422, expected_code="validation_error")


def test_modify_empty_body_returns_422():
    with _make_client() as client:
        resp = client.patch(
            "/api/agency/v1/reservations/AG-123",
            json={"schema_version": SCHEMA_VERSION},
            headers=_IDEMPOTENCY,
        )
        _assert_adr_error_envelope(resp, expected_status=422, expected_code="validation_error")


def test_delete_missing_idempotency_key_returns_422():
    with _make_client() as client:
        resp = client.delete("/api/agency/v1/reservations/AG-123")
        _assert_adr_error_envelope(resp, expected_status=422, expected_code="validation_error")


# ── 3) Kapsam siniri: agency disi 422 davranisi DEGISMEZ ─────────


def test_non_agency_path_keeps_default_422_shape():
    """install_agency_validation_handler agency DISI yollarda FastAPI varsayilan
    {"detail":[...]} seklini korumali; zarf yalniz agency yollarinda devreye girer.
    Boylece production'da diger rotalarin PII-scrub davranisi regresyona ugramaz."""
    from fastapi import Query

    app = FastAPI()

    @app.get("/api/other")
    async def _other(n: int = Query(...)):  # zorunlu int -> eksik/gecersiz olunca 422
        return {"n": n}

    install_agency_validation_handler(app)
    with TestClient(app, raise_server_exceptions=True) as client:

        resp = client.get("/api/other")  # zorunlu query eksik
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body  # varsayilan FastAPI sekli korunur
        assert "error_code" not in body  # agency zarfi DEGIL
