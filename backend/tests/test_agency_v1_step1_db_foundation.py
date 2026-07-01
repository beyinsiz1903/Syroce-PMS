"""
Agency v1 — Adim 1 DB temeli birim testleri (ADR Karar 4 + Karar 6).

Saf testtir: gercek Mongo/secret gerektirmez. Iki sinir kapsanir:
  1) ContractPropose.webhook_url opsiyonel + additive (zero-downtime) ve
     verildiginde https zorunlu (format kapisi; SSRF kapisi dispatch'te).
  2) ensure_performance_indexes idempotency_cache icin DONMUS scope unique
     (partial-on-string) + 48h TTL index'lerini background=True ile bildirir.

Sahte-yesil URETILMEZ: index davranisi gercek bootstrap kodundan, sahte bir
collection'a yapilan create_index cagrilari gozlenerek dogrulanir.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from routers.agency_contracts import ContractPropose


def _valid_contract_payload(**overrides) -> dict:
    base = {
        "tenant_id": "T-1",
        "valid_from": "2026-07-01",
        "valid_to": "2026-08-01",
    }
    base.update(overrides)
    return base


def test_webhook_url_optional_defaults_none():
    c = ContractPropose(**_valid_contract_payload())
    assert c.webhook_url is None


def test_webhook_url_valid_https_accepted():
    c = ContractPropose(**_valid_contract_payload(
        webhook_url="https://acente.example.com/syroce/hook"))
    assert c.webhook_url == "https://acente.example.com/syroce/hook"


def test_webhook_url_blank_coerced_to_none():
    c = ContractPropose(**_valid_contract_payload(webhook_url="   "))
    assert c.webhook_url is None


def test_webhook_url_http_rejected():
    with pytest.raises(ValidationError):
        ContractPropose(**_valid_contract_payload(
            webhook_url="http://acente.example.com/hook"))


def test_webhook_url_too_long_rejected():
    with pytest.raises(ValidationError):
        ContractPropose(**_valid_contract_payload(
            webhook_url="https://acente.example.com/" + "a" * 2100))


class _FakeCollection:
    def __init__(self, name, recorder):
        self._name = name
        self._recorder = recorder

    async def create_index(self, keys, **kwargs):
        self._recorder.append({"coll": self._name, "keys": keys, "kwargs": kwargs})


class _FakeDB:
    def __init__(self, recorder):
        self._recorder = recorder

    def __getitem__(self, name):
        return _FakeCollection(name, self._recorder)


@pytest.mark.asyncio
async def test_idempotency_cache_indexes_declared(monkeypatch):
    import bootstrap.phases.perf_indexes as perf

    recorder: list[dict] = []
    monkeypatch.setattr(perf, "_raw_db", _FakeDB(recorder))
    await perf.ensure_performance_indexes()

    cache_calls = [c for c in recorder if c["coll"] == "idempotency_cache"]
    assert len(cache_calls) == 2, "idempotency_cache iki index bildirmeli"

    # Hepsi background=True (boot'ta worker kilitlenmesi yok).
    assert all(c["kwargs"].get("background") is True for c in recorder)

    scope = next(c for c in cache_calls
                 if c["kwargs"].get("name") == "ux_idempotency_cache_scope")
    assert scope["keys"] == [
        ("tenant_id", 1), ("agency_id", 1), ("method", 1), ("path", 1),
        ("idempotency_key", 1),
    ], "ADR donmus scope birebir korunmali"
    assert scope["kwargs"].get("unique") is True
    assert scope["kwargs"].get("partialFilterExpression") == {
        "idempotency_key": {"$type": "string"}
    }, "partial-on-string: None key collision'a girmemeli (fake-green onlenir)"

    ttl = next(c for c in cache_calls
               if c["kwargs"].get("name") == "ttl_idempotency_cache")
    assert ttl["keys"] == [("expires_at", 1)]
    assert ttl["kwargs"].get("expireAfterSeconds") == 0
