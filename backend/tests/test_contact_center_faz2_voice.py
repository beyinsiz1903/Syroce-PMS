"""Syroce Contact Center — Faz 2 (sesli softphone, Twilio Voice) doktrin değişmezleri.

Saf birim testidir — çalışan backend / canlı Mongo / Twilio gerektirmez. PII-kripto
için GERÇEK ``FieldEncryptionService`` + gerçek AES-GCM keyring kullanılır; fake/bypass
ile sahte-yeşil (fake-green) ÜRETİLMEZ.

Kapsanan garantiler:
  1. Sağlayıcı fail-closed — Twilio yapılandırılmadan token üretmez (not_configured);
     boş kimlik reddedilir; imza doğrulanamıyorsa fail-closed False.
  2. Gelen TwiML — ajan varsa Dial+Client (kayıt açık); yoksa güvenli sesli fallback;
     enjeksiyon güvenli (XML kaçış).
  3. Durum makinesi — Twilio status eşlemesi; idempotent inbound (çift satır yok);
     answered/ended zaman damgaları; recording_ref bağlama.
  4. PII at-rest — arayan numarası düz saklanmaz (hash+enc); çağrı belgesi açık-metin
     PII anahtarı taşımaz.
  5. Read-boundary DTO allowlist — recording_ref ASLA sızmaz (yalnız has_recording);
     telefon varsayılan maskeli; tam numara yalnız açık yetkiyle; ciphertext/_id/_hash yok.
  6. Kayıt şifreleme — AES-GCM blob roundtrip; AAD bağlama (yanlış call_id çözülmez);
     tamper tespiti.
  7. Kayıt boru hattı + depo fail-closed — yapılandırma yoksa kayıt saklanmaz.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from pymongo.errors import DuplicateKeyError

from domains.contact_center.read_models import CALL_DTO_KEYS, call_to_dto
from domains.contact_center.recording_storage import (
    _decrypt_blob,
    _encrypt_blob,
    store_recording_bytes,
)
from domains.contact_center.recording_pipeline import process_call_recording
from domains.contact_center.voice_ingest import (
    attach_recording_ref,
    map_twilio_status,
    record_inbound_call,
    update_call_status,
)
from domains.contact_center.voice_provider import TwilioVoiceProvider
from models.enums import CallStatus
from security.field_encryption import get_field_encryption_service

_PHONE = "+905551112233"
_SID = "CA1234567890abcdef"
_FORBIDDEN_DOC_KEYS = {
    "from",
    "caller_id",
    "caller_phone",
    "phone",
    "phone_number",
    "From",
}


def _svc():
    return get_field_encryption_service()


# ── Fake Mongo (saf birim) ─────────────────────────────────────────────


class _UpdRes:
    def __init__(self, matched=0, upserted=None):
        self.matched_count = matched
        self.upserted_id = upserted


class _FakeCallsColl:
    def __init__(self):
        self.docs: list[dict] = []
        self.raise_on_upsert = False

    @staticmethod
    def _match(doc, flt):
        return all(doc.get(k) == v for k, v in flt.items())

    async def find_one_and_update(self, flt, update, upsert=False, return_document=None):
        for d in self.docs:
            if self._match(d, flt):
                d.update(update.get("$set", {}))
                return dict(d)
        if self.raise_on_upsert:
            raise DuplicateKeyError("dup")
        if upsert:
            newd = dict(update.get("$setOnInsert", {}))
            newd.update(update.get("$set", {}))
            self.docs.append(newd)
            return dict(newd)
        return None

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if self._match(d, flt):
                return dict(d)
        return None

    async def update_one(self, flt, update):
        for d in self.docs:
            if self._match(d, flt):
                d.update(update.get("$set", {}))
                return _UpdRes(matched=1)
        return _UpdRes(matched=0)


class _FakeDB:
    def __init__(self):
        self.contact_center_calls = _FakeCallsColl()

    def __getitem__(self, name):
        return getattr(self, name)


# ── 1. Sağlayıcı fail-closed ───────────────────────────────────────────


def test_token_fail_closed_when_not_configured(monkeypatch):
    for k in (
        "TWILIO_ACCOUNT_SID",
        "TWILIO_API_KEY_SID",
        "TWILIO_API_KEY_SECRET",
        "TWILIO_TWIML_APP_SID",
    ):
        monkeypatch.delenv(k, raising=False)
    res = TwilioVoiceProvider().generate_access_token(identity="t1:u1")
    assert res["success"] is False
    assert res["status"] == "not_configured"
    assert "token" not in res  # sahte token ASLA üretilmez


def test_token_rejects_empty_identity(monkeypatch):
    for k, v in {
        "TWILIO_ACCOUNT_SID": "AC_x",
        "TWILIO_API_KEY_SID": "SK_x",
        "TWILIO_API_KEY_SECRET": "secret_x",
        "TWILIO_TWIML_APP_SID": "AP_x",
    }.items():
        monkeypatch.setenv(k, v)
    res = TwilioVoiceProvider().generate_access_token(identity="")
    assert res["success"] is False
    assert res["status"] == "invalid_identity"


def test_validate_signature_fail_closed(monkeypatch):
    # Auth token / account yokken imza doğrulanamaz → fail-closed False.
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    assert (
        TwilioVoiceProvider().validate_signature(
            url="https://x/api/voice/inbound", params={"a": "b"}, signature="sig"
        )
        is False
    )
    # Konfig olsa bile imza boşsa fail-closed.
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_x")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok_x")
    assert (
        TwilioVoiceProvider().validate_signature(
            url="https://x/api/voice/inbound", params={"a": "b"}, signature=""
        )
        is False
    )


# ── 2. Gelen TwiML ─────────────────────────────────────────────────────


def test_inbound_twiml_dials_agent_with_recording():
    xml = TwilioVoiceProvider().build_inbound_twiml(
        agent_identity="t1:agent1",
        recording_status_callback="https://x/api/voice/recording",
    )
    assert "<Dial" in xml and "<Client>t1:agent1</Client>" in xml
    assert 'record="record-from-answer-dual"' in xml
    assert "recordingStatusCallback=" in xml


def test_inbound_twiml_fallback_without_agent():
    xml = TwilioVoiceProvider().build_inbound_twiml(agent_identity=None)
    assert "<Say" in xml and "<Hangup/>" in xml
    assert "<Dial" not in xml


def test_inbound_twiml_escapes_injection():
    xml = TwilioVoiceProvider().build_inbound_twiml(
        agent_identity='evil"/><Hangup/><Client>x'
    )
    # Ham enjeksiyon kapanış etiketi olarak GÖRÜNMEZ (kaçışlandı).
    assert "/><Hangup/><Client>x</Client>" not in xml
    assert "&lt;Hangup/&gt;" in xml or "&quot;" in xml


# ── 3. Durum makinesi ──────────────────────────────────────────────────


def test_map_twilio_status():
    assert map_twilio_status("ringing") == CallStatus.RINGING
    assert map_twilio_status("in-progress") == CallStatus.ANSWERED
    assert map_twilio_status("completed") == CallStatus.COMPLETED
    assert map_twilio_status("no-answer") == CallStatus.MISSED
    assert map_twilio_status("failed") == CallStatus.FAILED
    assert map_twilio_status("weird-unknown") is None


def test_record_inbound_is_idempotent_and_seals_pii():
    db = _FakeDB()
    cid1 = asyncio.run(
        record_inbound_call(
            db, tenant_id="t1", provider_call_sid=_SID, from_phone=_PHONE
        )
    )
    cid2 = asyncio.run(
        record_inbound_call(
            db, tenant_id="t1", provider_call_sid=_SID, from_phone=_PHONE
        )
    )
    assert cid1 == cid2  # retry çift satır üretmez
    assert len(db.contact_center_calls.docs) == 1
    doc = db.contact_center_calls.docs[0]
    # PII düz saklanmaz: hash+enc var, açık-metin numara YOK.
    assert doc["caller_id_hash"] and doc["caller_id_enc"]
    assert _PHONE not in str(doc)
    for k in _FORBIDDEN_DOC_KEYS:
        assert k not in doc
    assert doc["status"] == CallStatus.RINGING.value
    assert doc["direction"] == "inbound"


def test_record_inbound_duplicate_key_race_reads_existing():
    db = _FakeDB()
    # Önce kazanan satırı oluştur.
    asyncio.run(
        record_inbound_call(
            db, tenant_id="t1", provider_call_sid=_SID, from_phone=_PHONE
        )
    )
    # Sonra upsert DuplicateKeyError fırlatsın → kaybeden mevcut satırı okur.
    db.contact_center_calls.raise_on_upsert = True
    cid = asyncio.run(
        record_inbound_call(
            db, tenant_id="t1", provider_call_sid=_SID, from_phone=_PHONE
        )
    )
    assert cid == db.contact_center_calls.docs[0]["id"]
    assert len(db.contact_center_calls.docs) == 1


def test_status_transitions_set_timestamps():
    db = _FakeDB()
    asyncio.run(
        record_inbound_call(
            db, tenant_id="t1", provider_call_sid=_SID, from_phone=_PHONE
        )
    )
    asyncio.run(
        update_call_status(
            db, tenant_id="t1", provider_call_sid=_SID, twilio_status="in-progress"
        )
    )
    doc = db.contact_center_calls.docs[0]
    assert doc["status"] == CallStatus.ANSWERED.value
    assert doc["answered_at"] is not None
    asyncio.run(
        update_call_status(
            db,
            tenant_id="t1",
            provider_call_sid=_SID,
            twilio_status="completed",
            duration_seconds=42,
        )
    )
    doc = db.contact_center_calls.docs[0]
    assert doc["status"] == CallStatus.COMPLETED.value
    assert doc["ended_at"] is not None
    assert doc["duration_seconds"] == 42


def test_attach_recording_ref():
    db = _FakeDB()
    asyncio.run(
        record_inbound_call(
            db, tenant_id="t1", provider_call_sid=_SID, from_phone=_PHONE
        )
    )
    ok = asyncio.run(
        attach_recording_ref(
            db,
            tenant_id="t1",
            provider_call_sid=_SID,
            recording_ref="call_recordings/t1/CA.../rec.enc",
            duration_seconds=30,
        )
    )
    assert ok is True
    assert db.contact_center_calls.docs[0]["recording_ref"].endswith(".enc")


# ── 5. Read-boundary DTO allowlist ─────────────────────────────────────


def test_call_dto_never_leaks_recording_ref_or_ciphertext():
    svc = _svc()
    doc = {
        "id": "call1",
        "tenant_id": "t1",
        "_id": "mongo_oid",
        "channel": "voice",
        "direction": "inbound",
        "status": "completed",
        "provider_call_sid": _SID,
        "caller_id_hash": svc.compute_search_hash(_PHONE),
        "caller_id_enc": svc.encrypt_value(_PHONE),
        "recording_ref": "call_recordings/t1/CA/rec.enc",
        "duration_seconds": 10,
    }
    dto = call_to_dto(doc, svc)
    # recording_ref ASLA sızmaz — yalnız varlık bilgisi.
    assert "recording_ref" not in dto
    assert dto["has_recording"] is True
    # Ciphertext / blind-index / _id / provider_sid DTO'da YOK.
    for forbidden in (
        "caller_id_enc",
        "caller_id_hash",
        "_id",
        "provider_call_sid",
        "tenant_id",
    ):
        assert forbidden not in dto
    # Telefon varsayılan maskeli, tam numara kapalı.
    assert dto["caller_phone"] is None
    assert dto["caller_phone_masked"] and _PHONE != dto["caller_phone_masked"]
    assert "2233" in dto["caller_phone_masked"]  # son 4 hane görünür
    # Anahtarlar allowlist alt kümesi.
    assert set(dto.keys()).issubset(CALL_DTO_KEYS)


def test_call_dto_reveal_phone_only_when_authorized():
    svc = _svc()
    doc = {"id": "c", "caller_id_enc": svc.encrypt_value(_PHONE)}
    revealed = call_to_dto(doc, svc, reveal_phone=True)
    assert revealed["caller_phone"] == _PHONE
    masked = call_to_dto(doc, svc, reveal_phone=False)
    assert masked["caller_phone"] is None


# ── 6. Kayıt şifreleme ─────────────────────────────────────────────────


def test_recording_blob_roundtrip_and_aad_binding():
    audio = b"\x00\x01RIFF-fake-audio-bytes" * 64
    blob = _encrypt_blob(audio, tenant_id="t1", call_id="c1", recording_id="r1")
    assert blob != audio and audio not in blob  # at-rest şifreli
    out = _decrypt_blob(blob, tenant_id="t1", call_id="c1", recording_id="r1")
    assert out == audio
    # AAD bağlama: yanlış call_id ile çözülemez (tamper/file-swap savunması).
    import pytest

    with pytest.raises(Exception):
        _decrypt_blob(blob, tenant_id="t1", call_id="OTHER", recording_id="r1")


def test_recording_blob_tamper_detected():
    import pytest

    audio = b"secret-call-audio" * 16
    blob = bytearray(
        _encrypt_blob(audio, tenant_id="t1", call_id="c1", recording_id="r1")
    )
    blob[-1] ^= 0xFF  # ciphertext'i boz
    with pytest.raises(Exception):
        _decrypt_blob(bytes(blob), tenant_id="t1", call_id="c1", recording_id="r1")


# ── 7. Kayıt boru hattı + depo fail-closed ─────────────────────────────


def test_store_recording_fail_closed_without_config(monkeypatch):
    for k in (
        "CC_RECORDING_S3_BUCKET",
        "CC_RECORDING_S3_ACCESS_KEY_ID",
        "CC_RECORDING_S3_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    ref = store_recording_bytes(b"audio", tenant_id="t1", call_id="c1")
    assert ref is None  # depo yoksa kayıt saklanmaz


def test_pipeline_fail_closed_without_config(monkeypatch):
    for k in (
        "CC_RECORDING_S3_BUCKET",
        "CC_RECORDING_S3_ACCESS_KEY_ID",
        "CC_RECORDING_S3_SECRET_ACCESS_KEY",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
    ):
        monkeypatch.delenv(k, raising=False)
    db = _FakeDB()
    res = asyncio.run(
        process_call_recording(
            db,
            tenant_id="t1",
            provider_call_sid=_SID,
            recording_url="https://api.twilio.com/rec/RE123",
            duration_seconds=5,
        )
    )
    assert res["status"] in {
        "fetch_not_configured_or_unavailable",
        "storage_not_configured",
    }
