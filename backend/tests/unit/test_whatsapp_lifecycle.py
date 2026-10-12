"""Offline behavioral tests; no network or guest sends."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from modules.messaging import whatsapp_lifecycle as lifecycle
from modules.messaging.automation import _build_template_variables, process_booking_event
from modules.messaging.service import MessagingService


@pytest.mark.asyncio
@pytest.mark.parametrize("error,status", [(httpx.ConnectError("secret host"), 503), (httpx.ReadTimeout("secret token"), 504)])
async def test_template_network_failure_is_actionable(monkeypatch, error, status):
    monkeypatch.setattr(MessagingService, "_get_provider_config", AsyncMock(return_value={"is_sandbox": False}))
    monkeypatch.setattr(MessagingService, "_load_credentials", AsyncMock(return_value={"waba_id": "123", "access_token": "secret"}))
    monkeypatch.setattr(lifecycle, "safe_request_async", AsyncMock(side_effect=error))
    with pytest.raises(HTTPException) as caught:
        await lifecycle.approved_templates(object(), "tenant")
    assert caught.value.status_code == status
    assert "secret" not in caught.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize("status,body,expected", [
    (401, {"error": {"code": 190, "error_subcode": 463, "message": "secret"}}, "Meta 190, alt kod 463"),
    (403, {"error": {"code": 10}}, "whatsapp_business_management"),
    (400, {"error": {"code": 100}}, "WABA ID"),
    (429, {"error": {"code": 130429}}, "istek sınırına"),
    (503, {"error": {"message": "secret"}}, "geçici hata"),
    (400, {"error": {"code": "secret", "error_subcode": True}}, "HTTP 400"),
    (502, None, "HTTP 502"),
])
async def test_mapping_validation_exposes_safe_meta_diagnostics(monkeypatch, status, body, expected):
    monkeypatch.setattr(MessagingService, "_get_provider_config", AsyncMock(return_value={"is_sandbox": False}))
    monkeypatch.setattr(MessagingService, "_load_credentials", AsyncMock(return_value={"waba_id": "123", "access_token": "secret"}))
    response = httpx.Response(status, json=body) if body is not None else httpx.Response(status, text="<html>secret</html>")
    monkeypatch.setattr(lifecycle, "safe_request_async", AsyncMock(return_value=response))
    with pytest.raises(HTTPException) as caught:
        await lifecycle.validate_mapping(object(), "tenant", {"name": "welcome", "language": "tr", "variables": []})
    assert caught.value.status_code == 502
    assert expected in caught.value.detail
    assert "secret" not in caught.value.detail


class Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, _limit):
        return deepcopy(self.docs)

    def __aiter__(self):
        async def rows():
            for doc in self.docs:
                yield doc
        return rows()


class Logs:
    def __init__(self):
        self.docs = {}

    async def insert_one(self, doc):
        if doc["_id"] in self.docs:
            raise DuplicateKeyError("duplicate intent")
        self.docs[doc["_id"]] = deepcopy(doc)

    async def find_one(self, query, *_args):
        return next((deepcopy(d) for d in self.docs.values() if self.matches(d, query)), None)

    @staticmethod
    def matches(doc, query):
        return all(doc.get(k) == v for k, v in query.items())

    async def update_one(self, query, update):
        doc = next((d for d in self.docs.values() if self.matches(d, query)), None)
        if doc is None:
            return SimpleNamespace(modified_count=0)
        doc.update(update.get("$set", {}))
        for key, value in update.get("$inc", {}).items():
            doc[key] = doc.get(key, 0) + value
        return SimpleNamespace(modified_count=1)


@pytest.fixture
def system(monkeypatch):
    logs = Logs()
    db = SimpleNamespace(messaging_delivery_logs=logs, messaging_consents=SimpleNamespace(find=lambda *_a, **_k: Cursor([{"status": "opt_in", "source": "operator_recorded"}])))
    delivery = lifecycle.WhatsAppDelivery(db)
    config = {"provider_type": "whatsapp", "is_sandbox": False}
    delivery.service._get_provider_config = AsyncMock(return_value=config)
    delivery.service._load_credentials = AsyncMock(return_value={"access_token": "decrypted"})
    delivery.service._check_consent = AsyncMock(return_value=True)
    provider = SimpleNamespace(send_template=AsyncMock(return_value={"success": True, "provider_message_id": "wamid.1"}))
    monkeypatch.setitem(lifecycle.PROVIDER_MAP, "whatsapp", provider)
    return delivery, logs, provider, config


@pytest.mark.parametrize("raw,expected", [("+90 (555) 123-45-67", "905551234567"), ("00905551234567", "905551234567"), ("905551234567", "905551234567")])
def test_normalize_phone(raw, expected):
    assert lifecycle.normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "05551234567", "not a phone", "+123"])
def test_bad_numbers_rejected(raw):
    with pytest.raises(ValueError):
        lifecycle.normalize_phone(raw)


def test_template_shapes_fail_closed():
    simple = {"components": [{"type": "BODY", "text": "Hello {{1}} {{2}} {{1}}"}]}
    assert lifecycle.describe_template(simple)["variables_count"] == 2
    assert lifecycle.describe_template(simple)["supported"]
    for extra in [{"type": "HEADER", "format": "IMAGE"}, {"type": "BUTTONS", "buttons": [{"type": "URL", "url": "https://test/{{1}}"}]}]:
        assert not lifecycle.describe_template({"components": simple["components"] + [extra]})["supported"]
    assert not lifecycle.describe_template({"components": [{"type": "BODY", "text": "{{name}}"}]})["supported"]
    assert not lifecycle.describe_template({"components": [{"type": "BODY", "text": "{{2}}"}]})["supported"]


async def enqueue(delivery, **kw):
    return await delivery.enqueue("tenant", "+905551234567", "welcome", "tr",
                                  [{"type": "body", "parameters": [{"type": "text", "text": "Guest"}]}], key="event:rule", **kw)


@pytest.mark.asyncio
async def test_duplicate_event_and_concurrent_workers_send_once(system):
    delivery, logs, provider, _ = system
    await asyncio.gather(enqueue(delivery), enqueue(delivery))
    assert len(logs.docs) == 1
    await asyncio.gather(delivery.deliver("tenant", "event:rule"), delivery.deliver("tenant", "event:rule"))
    provider.send_template.assert_awaited_once()
    doc = logs.docs["event:rule"]
    assert doc["status"] == "sent"
    assert not doc.get("delivered_at")
    assert "recipient" not in doc
    assert "Guest" not in doc["template_components_enc"]


@pytest.mark.asyncio
async def test_unknown_outcome_is_not_retried(system):
    delivery, logs, provider, _ = system
    provider.send_template.return_value = {"success": False, "outcome_unknown": True}
    await enqueue(delivery)
    await delivery.deliver("tenant", "event:rule")
    await delivery.deliver("tenant", "event:rule")
    assert logs.docs["event:rule"]["status"] == "unknown"
    provider.send_template.assert_awaited_once()


@pytest.mark.asyncio
async def test_confirmed_rejection_retries_template_not_text(system):
    delivery, logs, provider, _ = system
    provider.send_template.return_value = {"success": False, "error": "Meta rejected"}
    await enqueue(delivery)
    await delivery.deliver("tenant", "event:rule")
    provider.send_template.return_value = {"success": True}
    await delivery.deliver("tenant", "event:rule")
    assert provider.send_template.await_count == 2
    assert provider.send_template.call_args.kwargs["components"][0]["parameters"][0]["text"] == "Guest"
    assert logs.docs["event:rule"]["status"] == "sent"


@pytest.mark.asyncio
async def test_tenant_isolation(system):
    delivery, logs, provider, _ = system
    await enqueue(delivery)
    await delivery.deliver("another-tenant", "event:rule")
    provider.send_template.assert_not_awaited()
    assert logs.docs["event:rule"]["status"] == "queued"


@pytest.mark.asyncio
async def test_optout_blocks_send(system):
    delivery, logs, provider, _ = system
    delivery.service._check_consent.return_value = False
    await enqueue(delivery)
    await delivery.deliver("tenant", "event:rule")
    assert logs.docs["event:rule"]["status"] == "rejected"
    provider.send_template.assert_not_awaited()


@pytest.mark.asyncio
async def test_live_requires_explicit_optin_not_just_inbound(system):
    delivery, logs, provider, _ = system
    delivery.db.messaging_consents.find = lambda *_a, **_k: Cursor([{"status": "opt_in", "source": "wa_inbound"}])
    await enqueue(delivery)
    await delivery.deliver("tenant", "event:rule")
    assert logs.docs["event:rule"]["status"] == "rejected"
    provider.send_template.assert_not_awaited()


@pytest.mark.asyncio
async def test_sandbox_does_not_claim_delivery_and_cannot_be_promoted(system):
    delivery, logs, provider, config = system
    config["is_sandbox"] = True
    await enqueue(delivery)
    config["is_sandbox"] = False
    await delivery.deliver("tenant", "event:rule")
    provider.send_template.assert_not_awaited()
    assert logs.docs["event:rule"]["status"] == "rejected"


@pytest.mark.asyncio
async def test_sandbox_result_is_simulated(system):
    delivery, logs, _, config = system
    config["is_sandbox"] = True
    await enqueue(delivery)
    await delivery.deliver("tenant", "event:rule")
    assert logs.docs["event:rule"]["status"] == "simulated"


def test_no_fabricated_hotel_information():
    variables = _build_template_variables({"id": "booking"}, None, None, None)
    for name in ("wifi_sifre", "restoran_saatleri", "havuz_saatleri", "spa_saatleri", "harita_link", "degerlendirme_link", "fatura_no"):
        assert variables[name] == ""
    assert _build_template_variables({}, None, None, {"messaging_info": {"wifi_sifre": "actual"}})["wifi_sifre"] == "actual"


@pytest.mark.asyncio
async def test_event_errors_propagate_for_dispatch_retry():
    db = SimpleNamespace(messaging_automation_rules=SimpleNamespace(find=lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("db down"))))
    with pytest.raises(RuntimeError):
        await process_booking_event("tenant", "checked_in", {"id": "booking"}, db=db)


@pytest.mark.asyncio
async def test_mapping_requires_all_variables(monkeypatch):
    monkeypatch.setattr(lifecycle, "approved_templates", AsyncMock(return_value=[{"name": "welcome", "language": "tr", "supported": True, "variables_count": 1}]))
    with pytest.raises(HTTPException):
        await lifecycle.validate_mapping(None, "tenant", {"name": "welcome", "language": "tr", "variables": []})


@pytest.mark.asyncio
async def test_retry_routes_hsm_to_template_dispatch(monkeypatch):
    mock = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(lifecycle.WhatsAppDelivery, "deliver", mock)
    db = SimpleNamespace(messaging_delivery_logs=SimpleNamespace(find_one=AsyncMock(return_value={"template_components_enc": "encrypted"})))
    await MessagingService(db).retry_failed("tenant", "delivery")
    mock.assert_awaited_once_with("tenant", "delivery")



@pytest.mark.asyncio
async def test_scheduled_delivery_cannot_be_sent_early(system):
    delivery, logs, provider, _ = system
    await enqueue(delivery, delay_minutes=60)
    await delivery.deliver("tenant", "event:rule")
    provider.send_template.assert_not_awaited()
    assert logs.docs["event:rule"]["status"] == "queued"


@pytest.mark.asyncio
async def test_event_materializes_rejected_log_without_missing_variable_send(monkeypatch):
    db = SimpleNamespace(
        messaging_automation_rules=SimpleNamespace(find=lambda *_a, **_k: Cursor([{
            "id": "rule", "channel": "whatsapp", "template_id": "meta:welcome:tr",
            "meta_template": {"name": "welcome", "language": "tr", "variables": ["wifi_sifre"]}}])),
        guests=SimpleNamespace(find_one=AsyncMock(return_value=None)),
        rooms=SimpleNamespace(find_one=AsyncMock(return_value=None)),
        tenants=SimpleNamespace(find_one=AsyncMock(return_value=None)),
    )
    queue = AsyncMock()
    monkeypatch.setattr(lifecycle.WhatsAppDelivery, "enqueue", queue)
    await process_booking_event("tenant", "checked_in", {"id": "booking"}, db=db)
    assert queue.call_args.kwargs["initial_status"] == "rejected"
    assert queue.call_args.kwargs["key"] == "tenant:checked_in:booking:rule"
