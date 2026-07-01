"""Contact Center — Faz 2 sesli softphone PUBLIC webhook entegrasyon testleri.

Bu dosya, birim testlerin (``test_contact_center_faz2_voice.py``) aksine, gerçek
FastAPI yönlendiricileri üzerinden uçtan uca akışı kanıtlar:

    HTTP POST → ``X-Twilio-Signature`` GERÇEK doğrulama (twilio SDK RequestValidator)
    → sunucu-tarafı kiracı eşleme (``contact_center_voice_numbers``)
    → durum makinesi / kayıt boru hattı.

Doktrin (no fake-green):
- İmza, twilio ``RequestValidator`` ile gerçekten hesaplanır ve gerçekten doğrulanır;
  imza doğrulaması monkeypatch ile ATLANMAZ. Geçersiz imza GERÇEKTEN 403 alır.
- Kiracı ASLA istemci girdisinden alınmaz; çağrılan ``To`` numarasından sunucu tarafı
  eşlenir. Eşleşme yoksa kibar fallback TwiML (çağrı kaydı OLUŞMAZ).
- PII (telefon) ve sır (imzalı kayıt URL'i) hiçbir yüzeyde (yanıt gövdesi, kalıcı
  belge, log) sızmaz.

Mongo, ``motor`` benzeri küçük bir sahte ile değiştirilir (canlı DB gerekmez); ancak
PII-kripto için GERÇEK ``FieldEncryptionService`` kullanılır.
"""
from __future__ import annotations

import logging
import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

import domains.contact_center.voice_router as voice_router
from domains.contact_center import recording_pipeline
from domains.contact_center.read_models import call_to_dto
from domains.contact_center.voice_ingest import attach_recording_ref, record_inbound_call
from models.enums import CallStatus
from security.field_encryption import get_field_encryption_service

_AUTH_TOKEN = "test_twilio_auth_token_abc123"
_ACCOUNT_SID = "ACtestaccountsid000000000000000000"
_PUBLIC_BASE = "https://pms.example.com"
_TENANT = "tenant-A"
_OTHER_TENANT = "tenant-B"
_AGENT = "tenant-A:agent1"
_TO_NUMBER = "+908503334455"
_OTHER_TO = "+908509998877"
_FROM_PHONE = "+905551112233"
_SID = "CA0000000000000000000000000000aaaa"
# Twilio kayıt URL'i imzalı/erişilebilir olabilir → ASLA persist/log edilmemeli.
_RECORDING_URL = "https://api.twilio.com/2010-04-01/Recordings/RE_secret_signed_xyz"

_PHONE_DIGITS = "905551112233"


# ── motor benzeri sahte Mongo ──────────────────────────────────────────


class _UpdRes:
    def __init__(self, matched=0):
        self.matched_count = matched


class _Coll:
    def __init__(self):
        self.docs: list[dict] = []

    @staticmethod
    def _match(doc, flt):
        return all(doc.get(k) == v for k, v in flt.items())

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if self._match(d, flt):
                return dict(d)
        return None

    async def find_one_and_update(self, flt, update, upsert=False, return_document=None):
        for d in self.docs:
            if self._match(d, flt):
                d.update(update.get("$set", {}))
                return dict(d)
        if upsert:
            newd = dict(update.get("$setOnInsert", {}))
            newd.update(update.get("$set", {}))
            self.docs.append(newd)
            return dict(newd)
        return None

    async def update_one(self, flt, update):
        for d in self.docs:
            if self._match(d, flt):
                d.update(update.get("$set", {}))
                return _UpdRes(matched=1)
        return _UpdRes(matched=0)


class _FakeDB:
    def __init__(self):
        self.contact_center_calls = _Coll()
        self.contact_center_voice_numbers = _Coll()

    def __getitem__(self, name):
        return getattr(self, name)


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture()
def fake_db(monkeypatch):
    db = _FakeDB()
    # Yönlendirici modül-düzeyi ``db``yi kullanır → sahte ile değiştir.
    monkeypatch.setattr(voice_router, "db", db)
    return db


@pytest.fixture()
def configured_signature(monkeypatch):
    """Gerçek imza doğrulamasını mümkün kılan asgari Twilio yapılandırması.

    Yalnızca account SID + auth token (imza doğrulama için yeter); token üretimi
    için gereken API key/secret bilinçli olarak verilmez (bu testler webhook'lara
    odaklı). ``PUBLIC_APP_URL`` imzanın hesaplanacağı dış URL'i sabitler.
    """
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", _ACCOUNT_SID)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", _AUTH_TOKEN)
    monkeypatch.setenv("PUBLIC_APP_URL", _PUBLIC_BASE)


@pytest.fixture()
def client(fake_db, configured_signature):
    app = FastAPI()
    app.include_router(voice_router.public_router)
    return TestClient(app)


def _seed_voice_number(db, *, to_number=_TO_NUMBER, tenant_id=_TENANT, agent=_AGENT):
    db.contact_center_voice_numbers.docs.append(
        {"to_number": to_number, "tenant_id": tenant_id, "agent_identity": agent}
    )


def _sign(path: str, params: dict) -> str:
    """``path`` için GERÇEK Twilio imzası üretir (PUBLIC_APP_URL tabanlı)."""
    url = f"{_PUBLIC_BASE}{path}"
    return RequestValidator(_AUTH_TOKEN).compute_signature(url, params)


def _post(client, path, params, *, signature=None):
    headers = {}
    if signature is not None:
        headers["X-Twilio-Signature"] = signature
    return client.post(path, data=params, headers=headers)


# ── 1. inbound: geçerli imza → çağrı kaydı + Dial TwiML ────────────────


def test_inbound_valid_signature_records_call_and_dials_agent(client, fake_db):
    _seed_voice_number(fake_db)
    params = {
        "CallSid": _SID,
        "From": _FROM_PHONE,
        "To": _TO_NUMBER,
        "CallStatus": "ringing",
        "AccountSid": _ACCOUNT_SID,
        "Direction": "inbound",
    }
    sig = _sign("/api/voice/inbound", params)
    resp = _post(client, "/api/voice/inbound", params, signature=sig)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    body = resp.text
    assert "<Dial" in body
    assert f"<Client>{_AGENT}</Client>" in body
    assert 'record="record-from-answer-dual"' in body
    # PII (arayan numarası) yanıt gövdesine ASLA sızmaz.
    assert _FROM_PHONE not in body
    assert _PHONE_DIGITS not in body

    # Çağrı kaydı doğru kiracı altında oluştu; düz-metin telefon YOK.
    calls = fake_db.contact_center_calls.docs
    assert len(calls) == 1
    doc = calls[0]
    assert doc["tenant_id"] == _TENANT
    assert doc["provider_call_sid"] == _SID
    assert doc["status"] == CallStatus.RINGING.value
    assert doc["direction"] == "inbound"
    assert doc["caller_id_hash"] and doc["caller_id_enc"]
    assert _FROM_PHONE not in str(doc)
    assert _PHONE_DIGITS not in str(doc)


def test_inbound_idempotent_under_twilio_retry(client, fake_db):
    _seed_voice_number(fake_db)
    params = {"CallSid": _SID, "From": _FROM_PHONE, "To": _TO_NUMBER}
    sig = _sign("/api/voice/inbound", params)
    r1 = _post(client, "/api/voice/inbound", params, signature=sig)
    r2 = _post(client, "/api/voice/inbound", params, signature=sig)
    assert r1.status_code == 200 and r2.status_code == 200
    # Twilio aynı inbound'u yeniden gönderse de tek satır oluşur.
    assert len(fake_db.contact_center_calls.docs) == 1


# ── 2. inbound: geçersiz imza → 403, kayıt YOK ─────────────────────────


def test_inbound_invalid_signature_rejected_403_and_no_record(client, fake_db):
    _seed_voice_number(fake_db)
    params = {"CallSid": _SID, "From": _FROM_PHONE, "To": _TO_NUMBER}
    resp = _post(client, "/api/voice/inbound", params, signature="bogus-signature")
    assert resp.status_code == 403
    assert "<Say" in resp.text  # fail-closed sesli mesaj
    assert "<Dial" not in resp.text
    # Doğrulanmamış istek hiçbir çağrı kaydı yaratmaz (spoofing savunması).
    assert fake_db.contact_center_calls.docs == []


def test_inbound_missing_signature_header_rejected(client, fake_db):
    _seed_voice_number(fake_db)
    params = {"CallSid": _SID, "From": _FROM_PHONE, "To": _TO_NUMBER}
    resp = _post(client, "/api/voice/inbound", params, signature=None)
    assert resp.status_code == 403
    assert fake_db.contact_center_calls.docs == []


# ── 3. inbound: bilinmeyen numara → kibar fallback, kayıt YOK ───────────


def test_inbound_unknown_number_returns_fallback_no_record(client, fake_db):
    # Numara eşlemesi YOK (seed edilmedi) → kiracı çözülemez.
    params = {"CallSid": _SID, "From": _FROM_PHONE, "To": _TO_NUMBER}
    sig = _sign("/api/voice/inbound", params)
    resp = _post(client, "/api/voice/inbound", params, signature=sig)
    assert resp.status_code == 200
    assert "<Say" in resp.text and "<Hangup/>" in resp.text
    assert "<Dial" not in resp.text
    assert fake_db.contact_center_calls.docs == []


def test_inbound_resolves_correct_tenant_for_number(client, fake_db):
    # İki numara iki farklı kiracıya; gelen çağrı yalnız eşleşen kiracıya yazılır.
    _seed_voice_number(fake_db, to_number=_TO_NUMBER, tenant_id=_TENANT, agent=_AGENT)
    _seed_voice_number(
        fake_db, to_number=_OTHER_TO, tenant_id=_OTHER_TENANT, agent="tenant-B:agent9"
    )
    params = {"CallSid": _SID, "From": _FROM_PHONE, "To": _OTHER_TO}
    sig = _sign("/api/voice/inbound", params)
    resp = _post(client, "/api/voice/inbound", params, signature=sig)
    assert resp.status_code == 200
    assert "<Client>tenant-B:agent9</Client>" in resp.text
    calls = fake_db.contact_center_calls.docs
    assert len(calls) == 1
    assert calls[0]["tenant_id"] == _OTHER_TENANT


# ── 4. status callback: durum geçişleri ────────────────────────────────


def _prerecord(fake_db):
    import asyncio

    asyncio.run(
        record_inbound_call(
            fake_db, tenant_id=_TENANT, provider_call_sid=_SID, from_phone=_FROM_PHONE
        )
    )


def test_status_callback_transitions_in_progress_then_completed(client, fake_db):
    _seed_voice_number(fake_db)
    _prerecord(fake_db)

    p1 = {"CallSid": _SID, "To": _TO_NUMBER, "CallStatus": "in-progress"}
    r1 = _post(client, "/api/voice/status", p1, signature=_sign("/api/voice/status", p1))
    assert r1.status_code == 204
    doc = fake_db.contact_center_calls.docs[0]
    assert doc["status"] == CallStatus.ANSWERED.value
    assert doc["answered_at"] is not None

    p2 = {
        "CallSid": _SID,
        "To": _TO_NUMBER,
        "CallStatus": "completed",
        "CallDuration": "42",
    }
    r2 = _post(client, "/api/voice/status", p2, signature=_sign("/api/voice/status", p2))
    assert r2.status_code == 204
    doc = fake_db.contact_center_calls.docs[0]
    assert doc["status"] == CallStatus.COMPLETED.value
    assert doc["ended_at"] is not None
    assert doc["duration_seconds"] == 42


def test_status_callback_invalid_signature_403_no_state_change(client, fake_db):
    _seed_voice_number(fake_db)
    _prerecord(fake_db)
    before = fake_db.contact_center_calls.docs[0]["status"]
    p = {"CallSid": _SID, "To": _TO_NUMBER, "CallStatus": "completed"}
    resp = _post(client, "/api/voice/status", p, signature="bad")
    assert resp.status_code == 403
    assert fake_db.contact_center_calls.docs[0]["status"] == before


# ── 5. recording callback: recording_ref bağlama + imzalı URL sızmaz ────


def test_recording_callback_binds_ref_and_never_leaks_signed_url(
    client, fake_db, monkeypatch
):
    _seed_voice_number(fake_db)
    _prerecord(fake_db)

    # Celery enqueue'yu zorla başarısız kıl → inline boru hattı yolu çalışsın.
    fake_celery = types.ModuleType("celery_tasks")

    class _Task:
        @staticmethod
        def delay(*a, **k):
            raise RuntimeError("broker yok (test)")

    fake_celery.process_call_recording_task = _Task()
    monkeypatch.setitem(sys.modules, "celery_tasks", fake_celery)

    captured = {}

    async def _stub_pipeline(
        db, *, tenant_id, provider_call_sid, recording_url, duration_seconds=0
    ):
        # Yönlendiricinin doğru argümanları geçtiğini doğrula (wiring kanıtı)...
        captured["tenant_id"] = tenant_id
        captured["provider_call_sid"] = provider_call_sid
        captured["recording_url"] = recording_url
        captured["duration_seconds"] = duration_seconds
        # ...ve GERÇEK ingest ile yalnızca nesne-anahtarı (ref) bağla — imzalı URL DEĞİL.
        await attach_recording_ref(
            db,
            tenant_id=tenant_id,
            provider_call_sid=provider_call_sid,
            recording_ref=f"call_recordings/{tenant_id}/{provider_call_sid}/rec.enc",
            duration_seconds=duration_seconds,
        )
        return {"status": "stored"}

    monkeypatch.setattr(recording_pipeline, "process_call_recording", _stub_pipeline)

    params = {
        "CallSid": _SID,
        "To": _TO_NUMBER,
        "RecordingUrl": _RECORDING_URL,
        "RecordingDuration": "37",
        "RecordingStatus": "completed",
    }
    resp = _post(
        client, "/api/voice/recording", params, signature=_sign("/api/voice/recording", params)
    )
    assert resp.status_code == 204

    # Yönlendirici kiracıyı To'dan çözüp boru hattını doğru argümanlarla çağırdı.
    assert captured["tenant_id"] == _TENANT
    assert captured["provider_call_sid"] == _SID
    assert captured["recording_url"] == _RECORDING_URL
    assert captured["duration_seconds"] == 37

    doc = fake_db.contact_center_calls.docs[0]
    # Yalnızca nesne-deposu anahtarı saklanır; imzalı URL ASLA persist edilmez.
    assert doc["recording_ref"].endswith(".enc")
    assert _RECORDING_URL not in str(doc)
    assert "api.twilio.com" not in str(doc)

    # Okuma sınırında recording_ref sızmaz; yalnızca has_recording.
    svc = get_field_encryption_service()
    dto = call_to_dto(doc, svc)
    assert "recording_ref" not in dto
    assert dto["has_recording"] is True


def test_recording_callback_invalid_signature_403_pipeline_not_called(
    client, fake_db, monkeypatch
):
    _seed_voice_number(fake_db)
    _prerecord(fake_db)

    called = {"hit": False}

    async def _stub_pipeline(*a, **k):
        called["hit"] = True
        return {"status": "stored"}

    monkeypatch.setattr(recording_pipeline, "process_call_recording", _stub_pipeline)

    params = {"CallSid": _SID, "To": _TO_NUMBER, "RecordingUrl": _RECORDING_URL}
    resp = _post(client, "/api/voice/recording", params, signature="nope")
    assert resp.status_code == 403
    assert called["hit"] is False
    assert fake_db.contact_center_calls.docs[0].get("recording_ref") in (None, "")


# ── 6. PII / sır log sızıntısı yok ─────────────────────────────────────


def test_no_pii_or_signed_url_in_logs(client, fake_db, monkeypatch, caplog):
    _seed_voice_number(fake_db)

    # Recording inline yolunu da kapsa.
    fake_celery = types.ModuleType("celery_tasks")

    class _Task:
        @staticmethod
        def delay(*a, **k):
            raise RuntimeError("broker yok (test)")

    fake_celery.process_call_recording_task = _Task()
    monkeypatch.setitem(sys.modules, "celery_tasks", fake_celery)

    async def _stub_pipeline(db, *, tenant_id, provider_call_sid, recording_url, duration_seconds=0):
        return {"status": "stored"}

    monkeypatch.setattr(recording_pipeline, "process_call_recording", _stub_pipeline)

    with caplog.at_level(logging.DEBUG):
        ip = {"CallSid": _SID, "From": _FROM_PHONE, "To": _TO_NUMBER}
        _post(client, "/api/voice/inbound", ip, signature=_sign("/api/voice/inbound", ip))
        sp = {"CallSid": _SID, "To": _TO_NUMBER, "CallStatus": "completed"}
        _post(client, "/api/voice/status", sp, signature=_sign("/api/voice/status", sp))
        rp = {"CallSid": _SID, "To": _TO_NUMBER, "RecordingUrl": _RECORDING_URL}
        _post(client, "/api/voice/recording", rp, signature=_sign("/api/voice/recording", rp))

    text = caplog.text
    assert _FROM_PHONE not in text
    assert _PHONE_DIGITS not in text
    assert _RECORDING_URL not in text
    assert _AUTH_TOKEN not in text
