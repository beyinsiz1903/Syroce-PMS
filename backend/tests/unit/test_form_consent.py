from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from modules.messaging import form_consent as consent


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(consent, "seal_recipient", lambda phone: {"recipient_enc": "sealed", "recipient_hash": "hash"})
    monkeypatch.setattr(consent, "get_field_encryption_service", lambda: SimpleNamespace(decrypt_document=lambda doc, **kw: doc))
    return SimpleNamespace(guests=SimpleNamespace(find_one=AsyncMock(return_value={"phone": "+905551112233"})), messaging_consents=SimpleNamespace(update_one=AsyncMock(), find_one=AsyncMock(return_value=None)))


@pytest.mark.asyncio
async def test_unchecked_never_reads_or_changes_consent(db):
    await consent.record_booking_consent(db, "hotel", "guest", "staff", False)
    db.guests.find_one.assert_not_awaited()
    db.messaging_consents.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_consent_scoped_encrypted_and_documented(db):
    await consent.record_booking_consent(db, "hotel", "guest", "staff", True, "+90 555 111 22 33")
    db.guests.find_one.assert_awaited_once_with({"tenant_id": "hotel", "id": "guest"})
    query, update = db.messaging_consents.update_one.call_args.args
    assert query["tenant_id"] == "hotel"
    data = update["$set"]
    assert data["purpose"] == "transactional"
    assert data["source"] == "reservation_form"
    assert data["updated_by"] == "staff"
    assert data["updated_at"] and data["text_version"]
    assert "recipient" not in data
    assert data["recipient_enc"] == "sealed"


@pytest.mark.asyncio
async def test_phone_changed_or_missing_fails_closed(db):
    for phone in ("", "+905559999999"):
        with pytest.raises(HTTPException) as exc:
            await consent.record_booking_consent(db, "hotel", "guest", "staff", True, phone)
        assert exc.value.status_code == 422
    db.messaging_consents.update_one.assert_not_awaited()


def test_string_true_not_consent():
    with pytest.raises(ValidationError):
        consent.WhatsAppFormConsent(whatsapp_consent="true")


@pytest.mark.asyncio
async def test_existing_withdrawal_is_not_silently_overridden(db):
    db.messaging_consents.find_one.return_value = {"status": "opt_out"}
    with pytest.raises(HTTPException) as exc:
        await consent.record_booking_consent(db, "hotel", "guest", "staff", True, "+905551112233")
    assert exc.value.status_code == 409
    db.messaging_consents.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_consent_uses_issuer_not_payload(monkeypatch):
    from routers import quick_id_proxy as proxy
    binding = SimpleNamespace(find_one=AsyncMock(return_value={"tenant_id": "issuer"}))
    monkeypatch.setattr(proxy, "raw_db", SimpleNamespace(precheckin_consent_bindings=binding))
    validate = AsyncMock(return_value={"status": "active"})
    monkeypatch.setattr(proxy, "precheckin_info_public", validate)
    record = AsyncMock()
    monkeypatch.setattr(consent, "record_form_consent", record)
    await proxy.precheckin_whatsapp_consent(Mock(), "token-123456789012", {"consent": True, "phone": "+905551112233", "tenant_id": "attacker"})
    assert record.call_args.args[1] == "issuer"
    assert "token-123456789012" not in str(binding.find_one.call_args)
    validate.assert_awaited_once()


@pytest.mark.asyncio
async def test_unknown_or_expired_token_cannot_consent(monkeypatch):
    from routers import quick_id_proxy as proxy
    binding = SimpleNamespace(find_one=AsyncMock(return_value=None))
    monkeypatch.setattr(proxy, "raw_db", SimpleNamespace(precheckin_consent_bindings=binding))
    validate = AsyncMock(return_value={})
    monkeypatch.setattr(proxy, "precheckin_info_public", validate)
    record = AsyncMock()
    monkeypatch.setattr(consent, "record_form_consent", record)
    with pytest.raises(HTTPException):
        await proxy.precheckin_whatsapp_consent(Mock(), "token-123456789012", {"consent": True, "phone": "+905551112233"})
    validate.side_effect = HTTPException(400, "used token")
    with pytest.raises(HTTPException):
        await proxy.precheckin_whatsapp_consent(Mock(), "token-123456789012", {"consent": True, "phone": "+905551112233"})
    record.assert_not_awaited()


@pytest.mark.asyncio
async def test_created_qr_binds_hashed_token_to_authenticated_tenant(monkeypatch):
    from routers import quick_id_proxy as proxy
    token = "123e4567-e89b-12d3-a456-426614174000"
    response = Mock(status_code=200)
    response.json.return_value = {"success": True, "token": {"token_id": token}}
    client = AsyncMock()
    client.post.return_value = response
    context = AsyncMock()
    context.__aenter__.return_value = client
    monkeypatch.setattr(proxy.httpx, "AsyncClient", lambda **kw: context)
    monkeypatch.setattr(proxy, "QUICKID_URL", "https://quickid.test")
    monkeypatch.setattr(proxy, "QUICKID_SERVICE_KEY", "test-key")
    monkeypatch.setattr(proxy, "_service_headers", lambda user: {})
    binding = SimpleNamespace(update_one=AsyncMock())
    monkeypatch.setattr(proxy, "raw_db", SimpleNamespace(precheckin_consent_bindings=binding))
    await proxy.precheckin_create({"tenant_id": "forged"}, SimpleNamespace(tenant_id="issuer"))
    query, update = binding.update_one.call_args.args
    assert query["_id"] == proxy.hashlib.sha256(token.encode()).hexdigest()
    assert update["$setOnInsert"]["tenant_id"] == "issuer"
