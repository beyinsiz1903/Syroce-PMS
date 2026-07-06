"""Contact Center — Faz 2 sesli softphone PUBLIC webhook router uçtan uca testleri.

Mevcut ``test_contact_center_faz2_voice.py`` sağlayıcı/ingest/DTO seviyesinde birim
testidir; burada ``/api/voice/{inbound,outbound,status,recording}`` ROUTER uçlarının
güvenlik sınırı uçtan uca doğrulanır:

  - İmza geçersiz → 403 (fail-closed; çağrı işlenmez).
  - Giden çağrı: geçerli imza + sunucu-basılı client kimliği → outbound TwiML +
    outbound çağrı kaydı; kiracı YALNIZCA client kimliğinden türetilir (istemci
    ``To/From`` ile başka kiracıya geçemez).
  - Sahte/biçimsiz ``From`` kimliği → fail-closed fallback (çağrı başlatılmaz).
  - Gelen çağrı: numara eşlemesi yoksa kibar fallback; varsa ajan client'ına Dial.
  - status/recording callback'leri doğru kiracıya yazar — hem imzalı ``?tenant_id``
    sorgusu hem ``To`` numara-eşlemesi yoluyla; başka kiracının kaydına dokunulmaz.

Saf testtir: çalışan backend / canlı Mongo / Twilio gerektirmez. İmza doğrulama
sınırını izole test etmek için ``validate_signature`` monkeypatch'lenir (gerçek
RequestValidator ayrı birim testte kapsanır); sahte-yeşil ÜRETİLMEZ — TwiML/kayıt/
tenant davranışı gerçek handler kodundan gözlenir. PII (telefon) test sabitidir.
"""
from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from pymongo.errors import DuplicateKeyError
from starlette.requests import Request

from domains.contact_center import voice_router
from domains.contact_center.voice_provider import TwilioVoiceProvider

_TARGET = "+905551112233"  # giden çağrı hedefi (test sabiti, gerçek PII değil)
_CALLER_ID = "+902121234567"  # kiracının seedlenmiş Twilio numarası
_SID = "CA0123456789abcdef0123456789abcdef"


# ── Fake Mongo (saf birim) ─────────────────────────────────────────────


class _UpdRes:
    def __init__(self, matched=0):
        self.matched_count = matched
        self.upserted_id = None


class _FakeColl:
    def __init__(self):
        self.docs: list[dict] = []
        self.raise_on_upsert = False

    @staticmethod
    def _match(doc, flt):
        def _match_val(val, cond):
            if isinstance(cond, dict):
                if "$in" in cond:
                    return val in cond["$in"]
                if "$ne" in cond:
                    return val != cond["$ne"]
                if "$exists" in cond:
                    exists = cond["$exists"]
                    return (val is not None) if exists else (val is None)
            return val == cond

        for k, v in flt.items():
            if k == "$or":
                if not any(_FakeColl._match(doc, sub) for sub in v):
                    return False
            else:
                if not _match_val(doc.get(k), v):
                    return False
        return True

    @staticmethod
    def _clean(doc):
        out = dict(doc)
        out.pop("_id", None)
        return out

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if self._match(d, flt):
                return self._clean(d)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id="x")

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

    async def update_one(self, flt, update):
        for d in self.docs:
            if self._match(d, flt):
                d.update(update.get("$set", {}))
                return _UpdRes(matched=1)
        return _UpdRes(matched=0)


class _FakeDB:
    def __init__(self):
        self.contact_center_calls = _FakeColl()
        self.contact_center_voice_numbers = _FakeColl()

    def __getitem__(self, name):
        return getattr(self, name)


def _make_request(path: str, form: dict, *, signature: str = "", query: str = "") -> Request:
    """Gerçek Starlette ``Request`` kurar (urlencoded gövde + Twilio imza başlığı)."""
    body = urlencode(form).encode()
    headers = [(b"content-type", b"application/x-www-form-urlencoded")]
    if signature:
        headers.append((b"x-twilio-signature", signature.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": headers,
        "scheme": "https",
        "server": ("testserver", 443),
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(voice_router, "db", db)
    return db


@pytest.fixture
def sig_ok(monkeypatch):
    """İmza doğrulamayı geçer kıl (imza sınırı ayrı birim testte kapsanır)."""
    monkeypatch.setattr(
        TwilioVoiceProvider, "validate_signature", lambda self, **kw: True
    )


@pytest.fixture
def sig_bad(monkeypatch):
    monkeypatch.setattr(
        TwilioVoiceProvider, "validate_signature", lambda self, **kw: False
    )


# ── Giden çağrı (/api/voice/outbound) ──────────────────────────────────


def test_outbound_invalid_signature_returns_403(fake_db, sig_bad):
    req = _make_request(
        "/api/voice/outbound",
        {"From": "client:t1:u1", "To": _TARGET, "CallSid": _SID},
        signature="bad",
    )
    resp = asyncio.run(voice_router.voice_outbound(req))
    assert resp.status_code == 403
    assert resp.media_type == "application/xml"
    # Fail-closed: hiçbir çağrı kaydı oluşturulmaz.
    assert fake_db.contact_center_calls.docs == []


def test_outbound_valid_signature_records_call_and_returns_twiml(fake_db, sig_ok):
    # Kiracının caller ID (Twilio numarası) eşlemesi seedlenir.
    fake_db.contact_center_voice_numbers.docs.append(
        {"tenant_id": "t1", "to_number": _CALLER_ID}
    )
    req = _make_request(
        "/api/voice/outbound",
        {"From": "client:t1:u1", "To": _TARGET, "CallSid": _SID},
        signature="good",
    )
    resp = asyncio.run(voice_router.voice_outbound(req))
    assert resp.status_code == 200
    xml = resp.body.decode()
    assert "<Dial" in xml and f"<Number>{_TARGET}</Number>" in xml
    assert f'callerId="{_CALLER_ID}"' in xml
    # Giden çağrı kaydı doğru kiracıya yazıldı.
    docs = fake_db.contact_center_calls.docs
    assert len(docs) == 1
    assert docs[0]["tenant_id"] == "t1"
    assert docs[0]["direction"] == "outbound"
    # PII (hedef numara) açık-metin saklanmaz.
    assert _TARGET not in str(docs[0])


def test_outbound_tenant_from_client_identity_not_client_input(fake_db, sig_ok):
    """Kiracı SUNUCU-basılı client kimliğinden gelir; istemci ``To`` ile başka
    kiracının numarasını kullanamaz. ``From`` t1 iken yalnız t1 caller ID seedli."""
    fake_db.contact_center_voice_numbers.docs.append(
        {"tenant_id": "t1", "to_number": _CALLER_ID}
    )
    # Saldırgan farklı bir kiracı (t2) caller ID'si seedlese bile From=t1 olduğundan
    # t2'nin numarası KULLANILMAZ.
    fake_db.contact_center_voice_numbers.docs.append(
        {"tenant_id": "t2", "to_number": "+901112223344"}
    )
    req = _make_request(
        "/api/voice/outbound",
        {"From": "client:t1:u1", "To": _TARGET, "CallSid": _SID},
        signature="good",
    )
    resp = asyncio.run(voice_router.voice_outbound(req))
    xml = resp.body.decode()
    assert f'callerId="{_CALLER_ID}"' in xml
    assert "+901112223344" not in xml
    assert fake_db.contact_center_calls.docs[0]["tenant_id"] == "t1"


def test_outbound_empty_from_is_fail_closed(fake_db, sig_ok):
    req = _make_request(
        "/api/voice/outbound",
        {"From": "", "To": _TARGET, "CallSid": _SID},
        signature="good",
    )
    resp = asyncio.run(voice_router.voice_outbound(req))
    xml = resp.body.decode()
    # Kimlik çözülemez → güvenli sesli fallback; çevirme yok, kayıt yok.
    assert "<Dial" not in xml and "<Say" in xml and "<Hangup/>" in xml
    assert fake_db.contact_center_calls.docs == []


def test_outbound_unknown_tenant_without_caller_id_fail_closed(fake_db, sig_ok):
    # From geçerli biçimde ama kiracının seedlenmiş Twilio numarası YOK → fallback.
    req = _make_request(
        "/api/voice/outbound",
        {"From": "client:ghost:u1", "To": _TARGET, "CallSid": _SID},
        signature="good",
    )
    resp = asyncio.run(voice_router.voice_outbound(req))
    xml = resp.body.decode()
    assert "<Dial" not in xml and "<Say" in xml
    assert fake_db.contact_center_calls.docs == []


# ── Gelen çağrı (/api/voice/inbound) ───────────────────────────────────


def test_inbound_invalid_signature_returns_403(fake_db, sig_bad):
    req = _make_request(
        "/api/voice/inbound",
        {"From": _TARGET, "To": _CALLER_ID, "CallSid": _SID},
        signature="bad",
    )
    resp = asyncio.run(voice_router.voice_inbound(req))
    assert resp.status_code == 403
    assert fake_db.contact_center_calls.docs == []


def test_inbound_unknown_number_polite_fallback(fake_db, sig_ok):
    # Eşleme yok → kibar fallback, çağrı kaydı YOK (fake-green değil).
    req = _make_request(
        "/api/voice/inbound",
        {"From": _TARGET, "To": "+900000000000", "CallSid": _SID},
        signature="good",
    )
    resp = asyncio.run(voice_router.voice_inbound(req))
    xml = resp.body.decode()
    assert "<Dial" not in xml and "<Say" in xml
    assert fake_db.contact_center_calls.docs == []


def test_inbound_known_number_records_and_dials_agent(fake_db, sig_ok):
    fake_db.contact_center_voice_numbers.docs.append(
        {"tenant_id": "t1", "to_number": _CALLER_ID, "agent_identity": "t1:agent1"}
    )
    req = _make_request(
        "/api/voice/inbound",
        {"From": _TARGET, "To": _CALLER_ID, "CallSid": _SID},
        signature="good",
    )
    resp = asyncio.run(voice_router.voice_inbound(req))
    xml = resp.body.decode()
    assert "<Dial" in xml and "<Client>t1:agent1</Client>" in xml
    docs = fake_db.contact_center_calls.docs
    assert len(docs) == 1
    assert docs[0]["tenant_id"] == "t1" and docs[0]["direction"] == "inbound"
    assert _TARGET not in str(docs[0])  # arayan numarası açık-metin değil


# ── Durum callback (/api/voice/status) ─────────────────────────────────


def test_status_invalid_signature_returns_403(fake_db, sig_bad):
    req = _make_request(
        "/api/voice/status",
        {"CallSid": _SID, "CallStatus": "completed"},
        signature="bad",
    )
    resp = asyncio.run(voice_router.voice_status(req))
    assert resp.status_code == 403


def test_status_resolves_tenant_via_signed_query_param(fake_db, sig_ok):
    # Giden çağrı callback'i imzalı ?tenant_id taşır; mevcut t1 kaydını günceller.
    fake_db.contact_center_calls.docs.append(
        {"id": "c1", "tenant_id": "t1", "provider_call_sid": _SID, "status": "ringing"}
    )
    req = _make_request(
        "/api/voice/status",
        {"CallSid": _SID, "CallStatus": "completed", "CallDuration": "42"},
        signature="good",
        query="tenant_id=t1",
    )
    resp = asyncio.run(voice_router.voice_status(req))
    assert resp.status_code == 204
    doc = fake_db.contact_center_calls.docs[0]
    assert doc["status"] == "completed"
    assert doc["duration_seconds"] == 42


def test_status_resolves_tenant_via_number_mapping_and_isolates(fake_db, sig_ok):
    # Gelen çağrı callback'inde sorgu yok → To numarasından kiracı eşlenir (t2).
    fake_db.contact_center_voice_numbers.docs.append(
        {"tenant_id": "t2", "to_number": _CALLER_ID}
    )
    fake_db.contact_center_calls.docs.append(
        {"id": "c2", "tenant_id": "t2", "provider_call_sid": _SID, "status": "ringing"}
    )
    # Aynı SID ile FARKLI kiracının kaydı — tenant filtresi sayesinde dokunulmamalı.
    fake_db.contact_center_calls.docs.append(
        {"id": "cX", "tenant_id": "t1", "provider_call_sid": _SID, "status": "ringing"}
    )
    req = _make_request(
        "/api/voice/status",
        {"CallSid": _SID, "To": _CALLER_ID, "DialCallStatus": "in-progress"},
        signature="good",
    )
    resp = asyncio.run(voice_router.voice_status(req))
    assert resp.status_code == 204
    by_id = {d["id"]: d for d in fake_db.contact_center_calls.docs}
    assert by_id["c2"]["status"] == "answered"  # doğru kiracı güncellendi
    assert by_id["cX"]["status"] == "ringing"  # başka kiracı dokunulmadı (izolasyon)


# ── Kayıt callback (/api/voice/recording) ──────────────────────────────


@pytest.fixture
def recording_spy(monkeypatch):
    """``celery_tasks`` modülünü, ``.delay`` argümanlarını yakalayan sahte ile değiştir.

    Kayıt callback'i önce Celery'ye enqueue eder; spy ile hangi kiracıya gönderildiği
    deterministik gözlenir (broker/inline boru hattına bağımlılık olmadan)."""
    calls: list[tuple] = []
    fake_mod = SimpleNamespace(
        process_call_recording_task=SimpleNamespace(
            delay=lambda *args: calls.append(args)
        )
    )
    monkeypatch.setitem(sys.modules, "celery_tasks", fake_mod)
    return calls


def test_recording_invalid_signature_returns_403(fake_db, sig_bad, recording_spy):
    req = _make_request(
        "/api/voice/recording",
        {"CallSid": _SID, "RecordingUrl": "https://api.twilio.com/rec/RE1"},
        signature="bad",
    )
    resp = asyncio.run(voice_router.voice_recording(req))
    assert resp.status_code == 403
    assert recording_spy == []  # doğrulanmamış istek boru hattına geçmez


def test_recording_dispatches_to_tenant_via_query_param(fake_db, sig_ok, recording_spy):
    req = _make_request(
        "/api/voice/recording",
        {
            "CallSid": _SID,
            "RecordingUrl": "https://api.twilio.com/rec/RE1",
            "RecordingDuration": "30",
        },
        signature="good",
        query="tenant_id=t1",
    )
    resp = asyncio.run(voice_router.voice_recording(req))
    assert resp.status_code == 204
    assert len(recording_spy) == 1
    tenant_id, call_sid, rec_url, duration = recording_spy[0]
    assert tenant_id == "t1" and call_sid == _SID and duration == 30


def test_recording_dispatches_to_tenant_via_number_mapping(fake_db, sig_ok, recording_spy):
    fake_db.contact_center_voice_numbers.docs.append(
        {"tenant_id": "t2", "to_number": _CALLER_ID}
    )
    req = _make_request(
        "/api/voice/recording",
        {
            "CallSid": _SID,
            "To": _CALLER_ID,
            "RecordingUrl": "https://api.twilio.com/rec/RE2",
            "RecordingDuration": "12",
        },
        signature="good",
    )
    resp = asyncio.run(voice_router.voice_recording(req))
    assert resp.status_code == 204
    assert len(recording_spy) == 1
    assert recording_spy[0][0] == "t2"


def test_recording_without_url_does_not_dispatch(fake_db, sig_ok, recording_spy):
    # RecordingUrl yoksa boru hattı tetiklenmez (yine de Twilio'ya 204).
    req = _make_request(
        "/api/voice/recording",
        {"CallSid": _SID},
        signature="good",
        query="tenant_id=t1",
    )
    resp = asyncio.run(voice_router.voice_recording(req))
    assert resp.status_code == 204
    assert recording_spy == []


def test_recording_unresolved_tenant_does_not_dispatch(fake_db, sig_ok, recording_spy):
    # Ne sorgu ne numara eşlemesi var → kiracı çözülemez → boru hattı tetiklenmez.
    req = _make_request(
        "/api/voice/recording",
        {
            "CallSid": _SID,
            "To": "+900000000000",
            "RecordingUrl": "https://api.twilio.com/rec/RE3",
        },
        signature="good",
    )
    resp = asyncio.run(voice_router.voice_recording(req))
    assert resp.status_code == 204
    assert recording_spy == []


# ── İmza yüzeyi: imzalanan URL sorgu dizesini (tenant_id) korur ─────────


def test_signed_url_preserves_tenant_id_query(fake_db, monkeypatch):
    """Twilio tüm URL'i (sorgu dâhil) imzalar; giden çağrı callback'lerindeki imzalı
    ``?tenant_id`` imza yüzeyinin parçası olmalı. ``PUBLIC_APP_URL`` ayarlıyken
    doğrulayıcıya iletilen URL'in sorguyu koruduğu sabitlenir (sahteleme savunması)."""
    monkeypatch.setenv("PUBLIC_APP_URL", "https://pms.example.com")
    captured: dict = {}

    def _capture(self, *, url, params, signature):
        captured["url"] = url
        captured["params"] = params
        return True

    monkeypatch.setattr(TwilioVoiceProvider, "validate_signature", _capture)
    fake_db.contact_center_calls.docs.append(
        {"id": "c1", "tenant_id": "t1", "provider_call_sid": _SID, "status": "ringing"}
    )
    req = _make_request(
        "/api/voice/status",
        {"CallSid": _SID, "CallStatus": "completed"},
        signature="good",
        query="tenant_id=t1",
    )
    resp = asyncio.run(voice_router.voice_status(req))
    assert resp.status_code == 204
    # İmzalanan URL: dış taban + yol + KORUNMUŞ sorgu dizesi.
    assert captured["url"] == "https://pms.example.com/api/voice/status?tenant_id=t1"


# ── ASGI mount/method smoke testi (router_registry üzerinden) ──────────
#
# Yukarıdaki testler handler'ları DOĞRUDAN çağırır → iş mantığını ve güvenlik
# dallarını kapsar ama route MOUNT'unu, HTTP method'unu (POST) ve prefix
# bağlantısını doğrulamaz. Bir uç yanlışlıkla manifest'ten düşerse veya yanlış
# method'a bağlanırsa bu sessizce kaçabilir. Aşağıdaki ASGI smoke testi GERÇEK
# ``router_registry`` manifest'inden voice router'larını mount eder (tüm app'i ≈189
# router + DB ile boot etmeden) ve TestClient ile şunları sabitler:
#   - ``/api/voice/{inbound,outbound,status,recording}`` POST'a bağlı (404/405 değil),
#   - aynı uçlar GET'i 405 ile reddeder (yanlış-method regresyonu),
#   - ``public_router`` (``/api/voice/...``) entitlement DIŞINDADIR: kimliksiz istek
#     auth/entitlement 403'üne değil imza gate'ine (handler) ulaşır.

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from bootstrap import router_registry  # noqa: E402

_VOICE_MODULE = "domains.contact_center.voice_router"
_PUBLIC_PATHS = [
    "/api/voice/inbound",
    "/api/voice/outbound",
    "/api/voice/status",
    "/api/voice/recording",
]


def _voice_manifest_entries():
    return [e for e in router_registry._EXTRACTED_ROUTERS if e[0] == _VOICE_MODULE]


@pytest.fixture
def voice_app(monkeypatch):
    """``router_registry`` manifest'inden YALNIZCA voice router'larını mount eden minimal
    ASGI app. Gerçek manifest girişlerini ve ``include_router`` kwargs'ını kullanır →
    mount/method/prefix regresyonunu yakalar; tüm app'i boot etmez."""
    monkeypatch.setattr(voice_router, "db", _FakeDB())
    app = FastAPI()
    entries = _voice_manifest_entries()
    assert entries, "voice router girişleri manifest'ten düşmüş"
    for mod_path, attr, tags, prefix_override, _deps in entries:
        router = router_registry._safe_import(mod_path, attr)
        assert router is not None, f"{mod_path}.{attr} import edilemedi"
        kwargs = {"tags": tags}
        if prefix_override:
            kwargs["prefix"] = prefix_override
        app.include_router(router, **kwargs)
    return TestClient(app, raise_server_exceptions=True)


def test_manifest_registers_both_voice_routers():
    # Hem auth'lu ``router`` hem public webhook ``public_router`` manifest'te olmalı.
    attrs = {e[1] for e in _voice_manifest_entries()}
    assert {"router", "public_router"} <= attrs


@pytest.mark.parametrize("path", _PUBLIC_PATHS)
def test_public_voice_endpoint_mounted_as_post(voice_app, path):
    # POST erişilebilir: imza yok → fail-closed 403 (404=mount yok / 405=method yanlış DEĞİL).
    resp = voice_app.post(path)
    assert resp.status_code != 404, f"{path} mount edilmemiş"
    assert resp.status_code != 405, f"{path} POST'a bağlı değil"
    assert resp.status_code == 403


@pytest.mark.parametrize("path", _PUBLIC_PATHS)
def test_public_voice_endpoint_rejects_get(voice_app, path):
    # Yalnızca POST: GET 405 döner (yanlış-method'a bağlanma regresyonunu yakalar).
    resp = voice_app.get(path)
    assert resp.status_code == 405


def test_public_router_unauth_reaches_signature_gate_not_auth(voice_app):
    """Kimliksiz istek imza gate'ine ulaşır: 403 ama TwiML XML gövdesi (handler'ın
    fail-closed yanıtı) — entitlement/auth'tan gelen JSON 401/403 DEĞİL."""
    resp = voice_app.post(
        "/api/voice/inbound",
        data={"From": _TARGET, "To": _CALLER_ID, "CallSid": _SID},
    )
    assert resp.status_code == 403
    assert resp.headers["content-type"].startswith("application/xml")


def test_public_router_outside_entitlement_runs_handler(voice_app, monkeypatch):
    """İmza geçerli kılınınca handler ÇALIŞIR (entitlement 403 ile engellenmez):
    bilinmeyen numara → kibar fallback 200 XML. Entitlement olsaydı 401/403 olurdu."""
    monkeypatch.setattr(
        TwilioVoiceProvider, "validate_signature", lambda self, **kw: True
    )
    resp = voice_app.post(
        "/api/voice/inbound",
        data={"From": _TARGET, "To": "+900000000000", "CallSid": _SID},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")


# ── Yetkili (auth'lu) uçlar herkese AÇIK DEĞİL ─────────────────────────
#
# ``public_router`` (``/api/voice/...``) bilinçli olarak kimliksizdir (Twilio
# webhook'ları, imza ile korunur). Buna karşılık ``router`` (``/api/contact-center/
# voice/token``, ``/calls``, ``/voice/numbers`` CRUD) operatör/ajan uçlarıdır ve
# ASLA kimliksiz erişime açık olmamalıdır. Bir uçtan ``Depends(get_current_user)``
# yanlışlıkla düşerse veya yanlış router'a (public_router) taşınırsa, çağrı kaydı /
# numara eşlemesi / Twilio AccessToken kimliksiz sızabilirdi. Aşağıdaki testler iki
# tamamlayıcı mount üzerinden auth sınırını sabitler:
#   - voice_app (her iki router mount): kimliksiz istek → auth reddi (401/403; route
#     MATCH oldu → 404/405 değil, handler ÇALIŞMADI → 2xx değil) ve geçersiz bearer
#     token → 401 (get_current_user JWT zinciri gerçekten koşar; no-op'a indirgenmemiş).
#   - voice_auth_app (yalnız auth'lu router): kimliksiz istek → 401/403 ve ``numbers``
#     uçlarında yanlış method → 405 (mount/method/prefix + auth-gate regresyonu).
# Her iki durumda da DB/handler'a ulaşılmaz → fail-closed.
#
# ``HTTPBearer`` Authorization başlığı yokken otomatik 403 üretir; bu yüzden
# kimliksiz istek hiç bir DB/entitlement koduna ulaşmadan auth gate'te durur →
# saf, deterministik test (canlı backend/Mongo/Twilio gerektirmez).

_AUTH_MODULE = "domains.contact_center.voice_router"

# (method, path) — manifest'ten mount edilen auth'lu softphone uçları.
_AUTH_ENDPOINTS = [
    ("post", "/api/contact-center/voice/token"),
    ("get", "/api/contact-center/voice/readiness"),
    ("get", "/api/contact-center/calls"),
    ("get", "/api/contact-center/voice/numbers"),
    ("post", "/api/contact-center/voice/numbers"),
    ("put", "/api/contact-center/voice/numbers/n1"),
    ("delete", "/api/contact-center/voice/numbers/n1"),
]


@pytest.mark.parametrize("method,path", _AUTH_ENDPOINTS)
def test_authenticated_voice_endpoint_requires_credentials(voice_app, method, path):
    # Kimlik bilgisi YOK → auth reddi (401/403; FastAPI/HTTPBearer sürümüne göre değişir).
    # Route MATCH oldu (404/405 DEĞİL) → mount + method doğru; handler ÇALIŞMADI
    # (2xx YOK) → uç herkese açık değil.
    resp = getattr(voice_app, method)(path)
    assert resp.status_code in (401, 403), (
        f"{method.upper()} {path} kimliksiz erişime kapalı değil (kod={resp.status_code})"
    )
    assert resp.status_code not in (404, 405), f"{method.upper()} {path} mount/method regresyonu"
    assert resp.status_code not in (200, 201, 204), "kimliksiz çağrı handler'a ulaşmamalı"


@pytest.mark.parametrize("method,path", _AUTH_ENDPOINTS)
def test_authenticated_voice_endpoint_rejects_invalid_token(voice_app, method, path):
    # Geçersiz bearer token → 401: get_current_user JWT çözümü gerçekten koşar
    # (auth dependency no-op'a indirgenmiş olsaydı 2xx olurdu). DB/handler'a ulaşılmaz.
    resp = getattr(voice_app, method)(
        path, headers={"Authorization": "Bearer not-a-real-jwt"}
    )
    assert resp.status_code == 401, f"{method.upper()} {path} geçersiz token'ı reddetmiyor"
    assert resp.status_code not in (200, 201, 204), "geçersiz token handler'a ulaşmamalı"


def _auth_manifest_entry():
    for e in router_registry._EXTRACTED_ROUTERS:
        if e[0] == _AUTH_MODULE and e[1] == "router":
            return e
    return None


@pytest.fixture
def voice_auth_app(monkeypatch):
    """Manifest'ten YALNIZCA auth'lu ``router``ı mount eden minimal ASGI app.

    Gerçek manifest girişini ve ``include_router`` kwargs'ını kullanır → mount/
    method/prefix + auth-gate regresyonunu yakalar; tüm app'i boot etmez."""
    monkeypatch.setattr(voice_router, "db", _FakeDB())
    app = FastAPI()
    entry = _auth_manifest_entry()
    assert entry, "auth'lu voice 'router' girişi manifest'ten düşmüş"
    mod_path, attr, tags, prefix_override, _deps = entry
    router = router_registry._safe_import(mod_path, attr)
    assert router is not None, f"{mod_path}.{attr} import edilemedi"
    kwargs = {"tags": tags}
    if prefix_override:
        kwargs["prefix"] = prefix_override
    app.include_router(router, **kwargs)
    return TestClient(app, raise_server_exceptions=True)


@pytest.mark.parametrize("method,path", _AUTH_ENDPOINTS)
def test_auth_voice_endpoint_requires_credentials(voice_auth_app, method, path):
    # Kimliksiz istek: 401/403 (auth gate devrede) — 404=mount yok / 405=method
    # yanlış DEĞİL. Uç yanlışlıkla herkese açılırsa bu test KIRILIR.
    resp = getattr(voice_auth_app, method)(path)
    assert resp.status_code != 404, f"{method.upper()} {path} mount edilmemiş"
    assert resp.status_code != 405, f"{method.upper()} {path} yanlış method'a bağlı"
    assert resp.status_code in (401, 403), (
        f"{method.upper()} {path} kimliksiz erişime açık (status={resp.status_code})"
    )


@pytest.mark.parametrize(
    "method,path",
    [
        # Koleksiyon ucu yalnızca GET/POST tanımlar → PUT/DELETE 405.
        ("put", "/api/contact-center/voice/numbers"),
        ("delete", "/api/contact-center/voice/numbers"),
        # Tekil kayıt ucu yalnızca PUT/DELETE tanımlar → GET/POST 405.
        ("get", "/api/contact-center/voice/numbers/n1"),
        ("post", "/api/contact-center/voice/numbers/n1"),
    ],
)
def test_voice_numbers_rejects_wrong_method(voice_auth_app, method, path):
    # Method routing auth'tan ÖNCE çalışır → yanlış method kimliksizken bile 405.
    resp = getattr(voice_auth_app, method)(path)
    assert resp.status_code == 405, f"{method.upper()} {path} 405 vermedi"


# ── Per-tenant ENTITLEMENT (modül AÇIK/KAPALI) kapısı ──────────────────
#
# Yukarıdaki ``router`` üstündeki ``require_module("contact_center")`` bir ROL
# allowlist'idir (kullanıcının rolü modülde mi). Bir otelde ``contact_center``
# eklentisinin AÇIK/KAPALI olması ise AYRI bir katmandır: ``EntitlementMiddleware``
# bunu ``ROUTE_MODULE_MAP`` üzerinden yol-bazlı uygular. Modül KAPALIyken auth'lu
# softphone uçlarına kimlikli istek 403 ``ENTITLEMENT_DENIED`` almalı; aksi halde
# kapalı bir eklentinin uçları sessizce erişilebilir kalırdı (regresyon).
#
# Public Twilio webhook'ları (``/api/voice/*``) bilinçli olarak bu haritanın
# DIŞINDADIR (imza ile korunur) — kimliksiz Twilio çağrısı entitlement 403'üne
# değil imza gate'ine ulaşmalı. Aşağıdaki testler iki şeyi sabitler:
#   1) Üç softphone yol grubunun (token / calls / voice numbers CRUD) tümü
#      "contact_center" modülüne map'lenir ve EXEMPT değildir.
#   2) Modül KAPALI bir kiracı bağlamında bu uçlar 403 ENTITLEMENT_DENIED döner;
#      AÇIKken middleware kapısını geçer; super_admin kapıyı bypass eder; public
#      ``/api/voice/*`` haritanın dışında olduğu için middleware'ce engellenmez.
#
# Saf testtir: gerçek backend/Mongo/Twilio gerektirmez — entitlement DB erişimi
# sahte koleksiyonla, marketplace fallback ve metering monkeypatch'le izole edilir;
# JWT gerçek ``create_token`` ile basılır (aynı JWT_SECRET ile çözülür). Sahte-yeşil
# ÜRETİLMEZ: 403/200 davranışı GERÇEK middleware kodundan gözlenir.

from core import entitlement as _entitlement  # noqa: E402
from core.entitlement import (  # noqa: E402
    EXEMPT_PREFIXES,
    EntitlementMiddleware,
    _match_route_module,
)
from core.security import create_token  # noqa: E402

# Üç softphone yol grubu — entitlement haritasının "contact_center"a bağlaması
# gereken auth'lu uçlar (token / çağrı listesi / numara eşleme CRUD).
_SOFTPHONE_AUTH_PATHS = [
    "/api/contact-center/voice/token",
    "/api/contact-center/voice/readiness",
    "/api/contact-center/calls",
    "/api/contact-center/voice/numbers",
    "/api/contact-center/voice/numbers/n1",
]


def test_softphone_auth_paths_map_to_contact_center_module():
    # Üç yol grubunun tümü contact_center'a map'lenir ve EXEMPT değildir →
    # middleware bunlar için modül kontrolü uygular.
    for path in _SOFTPHONE_AUTH_PATHS:
        assert _match_route_module(path) == "contact_center", path
        assert not any(path.startswith(e) for e in EXEMPT_PREFIXES), path


def test_public_voice_webhook_paths_are_outside_entitlement_map():
    # Bilinçli istisna: /api/voice/* HİÇBİR modüle map'lenmez → imza-korumalı
    # Twilio webhook'u kimliksiz çağrı alabilsin (entitlement 403'ü olmasın).
    for path in _PUBLIC_PATHS:
        assert _match_route_module(path) is None, path


class _EntFakeColl:
    """Tek-belge döndüren sahte koleksiyon (entitlement DB okumalarını izole eder)."""

    def __init__(self, doc=None):
        self._doc = doc

    async def find_one(self, flt, proj=None):
        return dict(self._doc) if self._doc else None


class _EntFakeDB:
    def __init__(self, tenant_doc, user_doc):
        self.tenants = _EntFakeColl(tenant_doc)
        self.users = _EntFakeColl(user_doc)


async def _ok_downstream(scope, receive, send):
    """Middleware'i GEÇEN her istek için 200 dönen downstream ASGI stub'ı.

    Entitlement middleware route handler'dan ÖNCE çalışır; bu stub yalnızca
    "kapı geçildi mi?" sorusunu izole eder (auth/RBAC ayrı katmandır)."""
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": b'{"ok":true}'})


@pytest.fixture
def ent_client(monkeypatch):
    """``module_on``/``super_admin`` parametreli EntitlementMiddleware TestClient'ı kurar."""

    def _build(*, module_on, super_admin=False):
        tenant_doc = {
            "modules": {"contact_center": bool(module_on)},
            "subscription_tier": "basic",
        }
        user_doc = {"role": "super_admin"} if super_admin else {"role": "front_desk"}
        fake_ent_db = _EntFakeDB(tenant_doc, user_doc)
        monkeypatch.setattr(_entitlement, "db", fake_ent_db)
        from core import tenant_db
        monkeypatch.setattr(tenant_db, "get_system_db", lambda: fake_ent_db)

        async def _noop_usage(*a, **k):
            return None

        monkeypatch.setattr(_entitlement, "record_usage", _noop_usage)

        # Marketplace fallback: modül kapalıysa aktif abonelik de yok (fail-closed).
        import core.subscriptions as _subs

        async def _no_market(tenant_id, module_key):
            return False

        monkeypatch.setattr(_subs, "tenant_has_module", _no_market)
        # Süper-admin lookup cache'i testler arası deterministik kalsın.
        _entitlement._SUPER_ADMIN_CACHE.clear()
        app = EntitlementMiddleware(_ok_downstream)
        return TestClient(app, raise_server_exceptions=True)

    return _build


@pytest.mark.parametrize("path", _SOFTPHONE_AUTH_PATHS)
def test_softphone_endpoint_blocked_when_module_disabled(ent_client, path):
    # Modül KAPALI kiracı + geçerli JWT → 403 ENTITLEMENT_DENIED (uç sızmaz).
    client = ent_client(module_on=False)
    token = create_token("u1", "t1")
    resp = client.post(path, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403, f"{path} modül kapalıyken engellenmedi"
    body = resp.json()
    assert body["error_code"] == "ENTITLEMENT_DENIED"
    assert body["required_module"] == "contact_center"


@pytest.mark.parametrize("path", _SOFTPHONE_AUTH_PATHS)
def test_softphone_endpoint_passes_gate_when_module_enabled(ent_client, path):
    # Modül AÇIK → middleware modül kapısını GEÇER (downstream stub 200).
    # Gerçek app'te auth/RBAC bu noktadan sonra ayrıca uygulanır.
    client = ent_client(module_on=True)
    token = create_token("u1", "t1")
    resp = client.post(path, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, f"{path} modül açıkken kapıyı geçmeli"


def test_super_admin_bypasses_module_gate_even_when_disabled(ent_client):
    # Merkezi operatör (super_admin) modül kapalı olsa da kapıyı bypass eder.
    client = ent_client(module_on=False, super_admin=True)
    token = create_token("sa1", "t1")
    resp = client.post(
        "/api/contact-center/calls", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200


@pytest.mark.parametrize("path", _PUBLIC_PATHS)
def test_public_voice_webhook_not_blocked_by_entitlement(ent_client, path):
    # Modül KAPALI + kimliksiz: /api/voice/* haritada olmadığından middleware
    # engellemez (downstream stub 200). Gerçek app'te imza gate'i devreye girer.
    client = ent_client(module_on=False)
    resp = client.post(path)
    assert resp.status_code == 200, f"{path} entitlement tarafından engellenmemeli"


# ── Readiness teşhis ucu (YALNIZCA super_admin; secret SIZMAZ) ─────────
#
# Operatörün "sistem uyandı mı / neyi eksik" sorusunu sır sızdırmadan tek bakışta
# görmesi için salt-okunur bool teşhis ucu. Aşağıdaki testler iki şeyi sabitler:
#   (1) super_admin OLMAYAN kimlik (geçerli token bile) → 403 (uç merkezi
#       operatöre kapalı; kiracı ajanı env hazırlığını göremez).
#   (2) super_admin → 200, yanıt YALNIZCA bool içerir ve enjekte edilen sahte
#       secret değerlerinin hiçbiri (tam/parça) gövdeye SIZMAZ.
# get_current_user dependency_override ile sabitlenir → canlı backend/JWT gerekmez.
from core.security import get_current_user as _get_current_user  # noqa: E402

_READINESS_PATH = "/api/contact-center/voice/readiness"


def _readiness_app(user):
    """Auth'lu ``router``ı mount edip ``get_current_user``ı sabitleyen minimal app."""
    monkeypatch_db = _FakeDB()
    voice_router.db = monkeypatch_db  # readiness DB'ye dokunmaz; güvenli
    app = FastAPI()
    app.include_router(voice_router.router)
    app.dependency_overrides[_get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=True)


def test_readiness_forbidden_for_non_super_admin():
    user = SimpleNamespace(id="u1", tenant_id="t1", role=None, roles=[])
    resp = _readiness_app(user).get(_READINESS_PATH)
    assert resp.status_code == 403, "readiness super_admin olmayan kimliğe açık"


def test_readiness_super_admin_returns_only_booleans_no_secret_leak(monkeypatch):
    # Sahte secret değerleri enjekte et → yanıtta ASLA (tam veya parça) görünmemeli.
    fakes = {
        "TWILIO_ACCOUNT_SID": "AC_FAKE_SID_must_not_leak",
        "TWILIO_API_KEY_SID": "SK_FAKE_KEY_SID_must_not_leak",
        "TWILIO_API_KEY_SECRET": "FAKE_KEY_SECRET_must_not_leak",
        "TWILIO_TWIML_APP_SID": "AP_FAKE_TWIML_must_not_leak",
        "TWILIO_AUTH_TOKEN": "FAKE_AUTH_TOKEN_must_not_leak",
        "PUBLIC_APP_URL": "https://app.example.test",
        "CC_RECORDING_S3_BUCKET": "fake-bucket-must-not-leak",
        "CC_RECORDING_S3_ACCESS_KEY_ID": "FAKE_AKID_must_not_leak",
        "CC_RECORDING_S3_SECRET_ACCESS_KEY": "FAKE_SAK_must_not_leak",
    }
    for k, v in fakes.items():
        monkeypatch.setenv(k, v)
    user = SimpleNamespace(id="sa1", tenant_id="t1", role=None, roles=["super_admin"])
    resp = _readiness_app(user).get(_READINESS_PATH)
    assert resp.status_code == 200
    # Hiçbir secret/config değeri gövdeye sızmamalı (yalnızca bool dönülür).
    for v in fakes.values():
        assert v not in resp.text, "readiness yanıtına tam değer sızdı"
    # Kısmi/maske sızıntısı da olmamalı (değerin ayırt edici parçaları).
    for fragment in ("AC_FAKE", "SK_FAKE", "FAKE_KEY", "FAKE_AUTH", "FAKE_AKID",
                     "FAKE_SAK", "example.test", "fake-bucket"):
        assert fragment not in resp.text, f"readiness yanıtına parça sızdı: {fragment}"
    body = resp.json()
    # Yalnızca bool + iç içe bool sözlükleri.
    assert isinstance(body["ready"], bool)
    assert isinstance(body["public_app_url_set"], bool)
    for section in ("twilio", "recording_storage"):
        assert isinstance(body[section], dict)
        for val in body[section].values():
            assert isinstance(val, bool)
    # Enjekte edilen config ile tutarlı (env-türevli bool'lar doğru yansır).
    assert body["twilio"]["has_credentials"] is True
    assert body["twilio"]["can_validate_signatures"] is True
    assert body["public_app_url_set"] is True
    assert body["recording_storage"]["is_configured"] is True


def test_outbound_agent_specific_mapping_priority(fake_db, sig_ok):
    # Both default mapping and agent-specific mapping exist
    fake_db.contact_center_voice_numbers.docs.append(
        {"tenant_id": "t1", "to_number": "+11111111111", "agent_identity": None}
    )
    fake_db.contact_center_voice_numbers.docs.append(
        {"tenant_id": "t1", "to_number": "+22222222222", "agent_identity": "t1:u1"}
    )
    req = _make_request(
        "/api/voice/outbound",
        {"From": "client:t1:u1", "To": _TARGET, "CallSid": _SID},
        signature="good",
    )
    resp = asyncio.run(voice_router.voice_outbound(req))
    xml = resp.body.decode()
    # Should use the agent-specific mapping
    assert 'callerId="+22222222222"' in xml


def test_outbound_agent_mapping_absent_tenant_default_used(fake_db, sig_ok):
    # Only default mapping exists
    fake_db.contact_center_voice_numbers.docs.append(
        {"tenant_id": "t1", "to_number": "+11111111111", "agent_identity": None}
    )
    req = _make_request(
        "/api/voice/outbound",
        {"From": "client:t1:u1", "To": _TARGET, "CallSid": _SID},
        signature="good",
    )
    resp = asyncio.run(voice_router.voice_outbound(req))
    xml = resp.body.decode()
    # Should fall back to the default mapping
    assert 'callerId="+11111111111"' in xml


def test_outbound_no_mapping_exists_fails_closed(fake_db, sig_ok):
    # No mapping exists
    req = _make_request(
        "/api/voice/outbound",
        {"From": "client:t1:u1", "To": _TARGET, "CallSid": _SID},
        signature="good",
    )
    resp = asyncio.run(voice_router.voice_outbound(req))
    xml = resp.body.decode()
    assert "<Dial" not in xml and "<Say" in xml


def test_outbound_inactive_mapping_ignored(fake_db, sig_ok):
    # Inactive agent mapping and active default mapping
    fake_db.contact_center_voice_numbers.docs.append(
        {"tenant_id": "t1", "to_number": "+11111111111", "agent_identity": None, "is_active": True}
    )
    fake_db.contact_center_voice_numbers.docs.append(
        {"tenant_id": "t1", "to_number": "+22222222222", "agent_identity": "t1:u1", "is_active": False}
    )
    req = _make_request(
        "/api/voice/outbound",
        {"From": "client:t1:u1", "To": _TARGET, "CallSid": _SID},
        signature="good",
    )
    resp = asyncio.run(voice_router.voice_outbound(req))
    xml = resp.body.decode()
    # Should use the default mapping because agent mapping is inactive
    assert 'callerId="+11111111111"' in xml


def test_outbound_cross_tenant_mapping_rejected(fake_db, sig_ok):
    # Mapping for another tenant
    fake_db.contact_center_voice_numbers.docs.append(
        {"tenant_id": "other_tenant", "to_number": "+11111111111", "agent_identity": None}
    )
    req = _make_request(
        "/api/voice/outbound",
        {"From": "client:t1:u1", "To": _TARGET, "CallSid": _SID},
        signature="good",
    )
    resp = asyncio.run(voice_router.voice_outbound(req))
    xml = resp.body.decode()
    # Should fail because t1 has no mappings
    assert "<Dial" not in xml and "<Say" in xml


def test_outbound_safe_identity_format_parsing(fake_db, sig_ok):
    # Test safe format with double underscores: tenantId__userId
    fake_db.contact_center_voice_numbers.docs.append(
        {"tenant_id": "t1", "to_number": "+22222222222", "agent_identity": "t1__u1"}
    )
    req = _make_request(
        "/api/voice/outbound",
        {"From": "client:t1__u1", "To": _TARGET, "CallSid": _SID},
        signature="good",
    )
    resp = asyncio.run(voice_router.voice_outbound(req))
    xml = resp.body.decode()
    assert 'callerId="+22222222222"' in xml


def test_outbound_inactive_default_ignored(fake_db, sig_ok):
    # Default mapping exists but is inactive, no agent mapping exists
    fake_db.contact_center_voice_numbers.docs.append(
        {"tenant_id": "t1", "to_number": "+11111111111", "agent_identity": None, "is_active": False}
    )
    req = _make_request(
        "/api/voice/outbound",
        {"From": "client:t1__u1", "To": _TARGET, "CallSid": _SID},
        signature="good",
    )
    resp = asyncio.run(voice_router.voice_outbound(req))
    xml = resp.body.decode()
    # Should fail closed with controlled TwiML failure since the default mapping is inactive
    assert "<Dial" not in xml and "<Say" in xml


def test_parse_client_identity_cases():
    from domains.contact_center.voice_router import _parse_client_identity
    
    # 1. Legacy colon format
    assert _parse_client_identity("client:t1:u1") == ("t1", "u1")
    assert _parse_client_identity("t1:u1") == ("t1", "u1")
    
    # 2. Safe double-underscore format
    assert _parse_client_identity("client:t1__u1") == ("t1", "u1")
    assert _parse_client_identity("t1__u1") == ("t1", "u1")
    
    # 3. Safe single-underscore format (fallback)
    assert _parse_client_identity("client:t1_u1") == ("t1", "u1")
    assert _parse_client_identity("t1_u1") == ("t1", "u1")
    
    # 4. UUID tenant and user values (with hyphens recovered)
    t_uuid = "bb306859-9748-430f-b24a-5a0d0ea29309"
    u_uuid = "088e9171-59d6-4ff5-9065-e9d89cedb886"
    t_safe = t_uuid.replace("-", "_")
    u_safe = u_uuid.replace("-", "_")
    assert _parse_client_identity(f"client:{t_safe}__{u_safe}") == (t_uuid, u_uuid)
    assert _parse_client_identity(f"client:{t_safe}_{u_safe}") == (t_uuid, u_uuid)
    
    # 5. Values containing underscores (double-underscore solves ambiguity)
    assert _parse_client_identity("client:tenant_demo_user__user_123") == ("tenant_demo_user", "user_123")
    
    # 6. Malformed input
    assert _parse_client_identity("client:t1__u1__extra") == (None, None)
    assert _parse_client_identity("client:t1:u1:extra") == (None, None)
    assert _parse_client_identity("client:noseparator") == (None, None)
    assert _parse_client_identity("client:no-separator") == (None, None)
    assert _parse_client_identity("client:") == (None, None)
    assert _parse_client_identity("") == (None, None)
    assert _parse_client_identity(None) == (None, None)
