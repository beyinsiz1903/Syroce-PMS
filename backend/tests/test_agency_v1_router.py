"""
Agency v1 — router iskeleti uctan uca testleri (ADR Karar 3).

Saf testtir: calisan backend / canli Mongo / secret gerektirmez. Minimal bir
FastAPI app'e yalniz agency_v1 router'i baglanir. Iki sinir dogrulanir:

  1. FAIL-CLOSED: gecerli istek handler'a ulasir; hicbir alt sistem baglanmadigi
     icin ADR ortak hata modeline gore 503 not_configured doner (error_code UST
     seviyede). Sahte basari YOK; uc su an hicbir privileged is yapmaz.
  2. KATI DTO/parametre dogrulamasi: gecersiz govde/parametre/eksik zorunlu
     header -> 422 (handler'a ulasmadan once, FastAPI istek dogrulamasi). Bilinmeyen
     alan sessizce yutulmaz.

422, FastAPI istek dogrulamasi handler'dan once kostugu icin auth durumundan
bagimsiz gozlenir; bu yuzden override gerekmez. Sahte-yesil URETILMEZ.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.agency_v1 import router as agency_router
from routers.agency_v1.dtos import SCHEMA_VERSION
from tests.test_agency_v1_dtos import _valid_create_payload

_IDEMPOTENCY = {"Idempotency-Key": "idem-1"}


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(agency_router)
    return TestClient(app, raise_server_exceptions=True)


# ── 1) Fail-closed: gecerli istek -> 503 not_configured (ust-seviye error_code) ──


_VALID_MODIFY = {"schema_version": SCHEMA_VERSION, "special_requests": "geç giris"}


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/api/agency/v1/availability"
            "?room_type_id=RT-1&arrival_date=2026-07-01&departure_date=2026-07-03", None),
        ("post", "/api/agency/v1/reservations", _valid_create_payload()),
        ("patch", "/api/agency/v1/reservations/AG-123", _VALID_MODIFY),
        ("delete", "/api/agency/v1/reservations/AG-123", None),
    ],
)
def test_endpoints_fail_closed_not_configured(method, path, body):
    client = _make_client()
    kwargs = {"headers": dict(_IDEMPOTENCY)}
    if body is not None:
        kwargs["json"] = body
    resp = getattr(client, method)(path, **kwargs)
    assert resp.status_code == 503
    body = resp.json()
    assert body["error_code"] == "not_configured"
    assert body["schema_version"] == SCHEMA_VERSION
    assert "detail" not in body  # error_code UST seviyede, detail altinda DEGIL


# ── 2) Strict dogrulama -> 422 (handler'a ulasmadan) ─────────────


def test_create_unknown_field_returns_422():
    client = _make_client()
    payload = _valid_create_payload()
    payload["totally_unknown"] = "x"
    resp = client.post("/api/agency/v1/reservations", json=payload, headers=_IDEMPOTENCY)
    assert resp.status_code == 422


def test_create_bad_date_returns_422():
    client = _make_client()
    payload = _valid_create_payload()
    payload["departure_date"] = payload["arrival_date"]
    resp = client.post("/api/agency/v1/reservations", json=payload, headers=_IDEMPOTENCY)
    assert resp.status_code == 422


def test_create_missing_idempotency_key_returns_422():
    client = _make_client()
    resp = client.post("/api/agency/v1/reservations", json=_valid_create_payload())
    assert resp.status_code == 422


def test_create_missing_currency_returns_422():
    client = _make_client()
    payload = _valid_create_payload()
    del payload["pricing"]["currency"]  # ADR: currency zorunlu
    resp = client.post("/api/agency/v1/reservations", json=payload, headers=_IDEMPOTENCY)
    assert resp.status_code == 422


def test_availability_missing_required_query_returns_422():
    client = _make_client()
    resp = client.get("/api/agency/v1/availability?room_type_id=RT-1")
    assert resp.status_code == 422


def test_availability_bad_date_pattern_returns_422():
    client = _make_client()
    resp = client.get(
        "/api/agency/v1/availability"
        "?room_type_id=RT-1&arrival_date=07-01-2026&departure_date=2026-07-03"
    )
    assert resp.status_code == 422


def test_modify_empty_body_returns_422():
    client = _make_client()
    resp = client.patch(
        "/api/agency/v1/reservations/AG-123",
        json={"schema_version": SCHEMA_VERSION},
        headers=_IDEMPOTENCY,
    )
    assert resp.status_code == 422


def test_delete_missing_idempotency_key_returns_422():
    client = _make_client()
    resp = client.delete("/api/agency/v1/reservations/AG-123")
    assert resp.status_code == 422
