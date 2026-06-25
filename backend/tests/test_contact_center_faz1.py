"""Syroce Contact Center — Faz 1 (WhatsApp MVP) doktrin değişmezleri.

Saf birim testidir — çalışan backend / canlı Mongo gerektirmez. PII-kripto için
GERÇEK ``FieldEncryptionService`` kullanılır (bu ortamda gerçek ``aes256gcm:``
zarfı üretir); fake/bypass ile sahte-yeşil (fake-green) ÜRETİLMEZ.

Kapsanan garantiler:
  1. Kripto köprüsü gerçek zarf üretir — arayan telefonu/gövde açık metin
     SAKLANMAZ; ``_is_encrypted`` doğru; roundtrip ve blind-index kararlı.
  2. Gelen mesaj belgesi açık-metin PII anahtarı (from/text/raw/...) taşımaz.
  3. Read-boundary DTO allowlist — ciphertext/_id/_hash dışarı verilmez;
     telefon varsayılan maskeli; tam numara yalnızca açık yetkiyle açılır.
  4. İdempotency anahtarı kararlı (sentetik ``id`` değil provider_message_id'ye
     dayanır).
  5. Teslimat-durum eşlemesi.
  6. Sağlayıcı fail-closed — gerçek transport'a gitmeden not_configured /
     session_expired / context_required döner; sahte başarı YOK.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from domains.contact_center.provider import (
    MockProvider,
    WhatsAppCloudProvider,
    get_communication_provider,
)
from domains.contact_center.read_models import (
    CONVERSATION_DTO_KEYS,
    MESSAGE_DTO_KEYS,
    conversation_to_dto,
    mask_phone,
    message_to_dto,
)
from domains.contact_center.whatsapp_ingest import (
    build_caller_crypto,
    build_inbound_message_doc,
    ingest_whatsapp_inbound,
    map_status,
    sync_whatsapp_status,
)
from models.enums import UserRole
from security.field_encryption import get_field_encryption_service

_PHONE = "+905551112233"
_FORBIDDEN_DOC_KEYS = {
    "from",
    "text",
    "raw",
    "caller_id",
    "caller_phone",
    "phone",
    "phone_number",
    "body",
}


def _svc():
    return get_field_encryption_service()


# ── 1. Kripto köprüsü gerçek zarf üretir ─────────────────────────────


def test_build_caller_crypto_produces_real_envelope_not_plaintext():
    svc = _svc()
    caller_hash, caller_enc = build_caller_crypto(svc, _PHONE)
    # Açık metin DEĞİL.
    assert caller_enc != _PHONE
    assert _PHONE not in caller_enc
    # Gerçek zarf (SYR1:/aes256gcm:) — bypass plaintext kabul edilmez.
    assert svc._is_encrypted(caller_enc)
    # Roundtrip.
    assert svc.decrypt_value(caller_enc) == _PHONE
    # Blind-index: boş değil, ham telefon sızdırmaz, kararlı (normalize edilmiş).
    assert caller_hash and _PHONE not in caller_hash
    assert caller_hash == build_caller_crypto(svc, f"  {_PHONE}  ")[0]
    # Farklı telefon → farklı hash.
    assert caller_hash != build_caller_crypto(svc, "+905559998877")[0]


def test_build_caller_crypto_empty_is_noop():
    svc = _svc()
    assert build_caller_crypto(svc, "") == ("", "")
    assert build_caller_crypto(svc, None) == ("", "")


# ── 2. Gelen mesaj belgesi açık-metin PII taşımaz ────────────────────


def test_inbound_message_doc_has_no_plaintext_pii_and_encrypts_body():
    svc = _svc()
    body = "Merhaba, rezervasyonumu sormak istiyorum"
    doc = build_inbound_message_doc(
        svc,
        tenant_id="t1",
        conversation_id="c1",
        provider_message_id="wamid.X",
        text_body=body,
        msg_type="text",
    )
    # Hiçbir açık-metin PII anahtarı yok.
    assert not (set(doc.keys()) & _FORBIDDEN_DOC_KEYS)
    # Gövde şifreli + roundtrip.
    assert doc["body_enc"] != body
    assert svc._is_encrypted(doc["body_enc"])
    assert svc.decrypt_value(doc["body_enc"]) == body
    # Yön/durum/gönderen sözleşmesi.
    assert doc["direction"] == "inbound"
    assert doc["status"] == "received"
    assert doc["sender_agent_id"] is None
    assert doc["provider_message_id"] == "wamid.X"
    assert doc["channel"] == "whatsapp"


# ── 3. Read-boundary DTO allowlist ───────────────────────────────────


def test_conversation_dto_is_allowlisted_and_emits_no_ciphertext():
    svc = _svc()
    raw = {
        "_id": "mongo-objectid",
        "id": "c1",
        "tenant_id": "t1",
        "channel": "whatsapp",
        "status": "open",
        "unread_count": 2,
        "caller_id_hash": "DEADBEEF",
        "caller_id_enc": svc.encrypt_value(_PHONE),
        "caller_display_name_enc": svc.encrypt_value("Ahmet Yılmaz"),
        "secret_junk": "should-not-appear",
    }
    dto = conversation_to_dto(raw, svc)
    # Anahtarlar allowlist'in alt kümesi.
    assert set(dto.keys()) <= CONVERSATION_DTO_KEYS
    # Hiçbir şifreli/blind-index/Mongo iç alanı yok.
    for k in dto:
        assert not k.endswith("_enc"), k
        assert "_hash" not in k, k
        assert k not in ("_id", "secret_junk"), k
    # Ad çözülür; telefon VARSAYILAN maskeli (tam numara açılmaz).
    assert dto["caller_name"] == "Ahmet Yılmaz"
    assert dto["caller_phone"] is None
    assert dto["caller_phone_masked"] and dto["caller_phone_masked"] != _PHONE
    assert dto["caller_phone_masked"].endswith("2233")


def test_conversation_dto_reveal_phone_only_when_authorized():
    svc = _svc()
    raw = {"id": "c1", "caller_id_enc": svc.encrypt_value(_PHONE)}
    revealed = conversation_to_dto(raw, svc, reveal_phone=True)
    assert revealed["caller_phone"] == _PHONE


def test_message_dto_is_allowlisted_and_decrypts_body():
    svc = _svc()
    raw = {
        "_id": "mongo-objectid",
        "id": "m1",
        "direction": "outbound",
        "status": "sent",
        "body_enc": svc.encrypt_value("yanıt metni"),
        "provider_message_id": "wamid.Y",
        "raw": {"leak": True},
    }
    dto = message_to_dto(raw, svc)
    assert set(dto.keys()) <= MESSAGE_DTO_KEYS
    for k in dto:
        assert not k.endswith("_enc"), k
        assert k not in ("_id", "raw"), k
    assert dto["body"] == "yanıt metni"


def test_mask_phone_hides_middle_keeps_last4():
    masked = mask_phone(_PHONE)
    assert masked.endswith("2233")
    # Ortadaki haneler açık değil (son 4 hariç ham hane sızmaz).
    assert "5551112" not in masked
    assert mask_phone(None) is None
    assert mask_phone("12") is not None  # kısa numara çökmez


# ── 4. İdempotency anahtarı kararlı ──────────────────────────────────


def test_inbound_idempotency_key_is_provider_id_not_synthetic_id():
    svc = _svc()
    common = dict(
        tenant_id="t1",
        conversation_id="c1",
        provider_message_id="wamid.SAME",
        text_body="x",
        msg_type="text",
    )
    a = build_inbound_message_doc(svc, **common)
    b = build_inbound_message_doc(svc, **common)
    # Sentetik id farklı (upsert idempotency'si buna DAYANMAZ)...
    assert a["id"] != b["id"]
    # ...ama upsert anahtar bileşenleri kararlı.
    key = ("tenant_id", "channel", "provider_message_id")
    assert {k: a[k] for k in key} == {k: b[k] for k in key}


# ── 5. Teslimat-durum eşlemesi ───────────────────────────────────────


def test_map_status_covers_meta_lifecycle():
    assert map_status("sent") == "sent"
    assert map_status("delivered") == "delivered"
    assert map_status("read") == "read"
    assert map_status("failed") == "failed"
    assert map_status("DELIVERED") == "delivered"  # case-insensitive
    assert map_status("bogus") is None
    assert map_status("") is None
    assert map_status(None) is None


# ── 6. Sağlayıcı fail-closed (transport'a gitmeden) ──────────────────


class _FakeColl:
    def __init__(self, doc):
        self._doc = doc

    async def find_one(self, *a, **k):
        return self._doc


class _FakeDB:
    def __init__(self, cfg):
        self.messaging_provider_configs = _FakeColl(cfg)


def test_registry_resolves_real_provider_and_unknown_falls_back():
    assert isinstance(get_communication_provider("whatsapp"), WhatsAppCloudProvider)
    assert isinstance(get_communication_provider("whatsapp_cloud"), WhatsAppCloudProvider)
    assert isinstance(get_communication_provider("nope"), MockProvider)


def test_generic_send_message_is_fail_closed_context_required():
    p = WhatsAppCloudProvider()
    res = asyncio.run(p.send_message(to_hash="h", channel="whatsapp", body="x"))
    assert res["success"] is False
    assert res["status"] == "context_required"


def test_send_whatsapp_not_configured_when_no_config():
    p = WhatsAppCloudProvider()
    # db=None ve cfg yok → not_configured (gerçek transport YOK).
    res = asyncio.run(
        p.send_whatsapp(db=None, tenant_id="t1", recipient=_PHONE, body="x")
    )
    assert res["success"] is False
    assert res["status"] == "not_configured"

    res2 = asyncio.run(
        p.send_whatsapp(db=_FakeDB(None), tenant_id="t1", recipient=_PHONE, body="x")
    )
    assert res2["status"] == "not_configured"


def test_send_whatsapp_session_expired_requires_template_out_of_window():
    p = WhatsAppCloudProvider()
    cfg = {
        "tenant_id": "t1",
        "provider_type": "whatsapp",
        "enabled": True,
        "credentials_encrypted": {
            "access_token": "tok",
            "phone_number_id": "PN1",
        },
    }
    # Pencere kapalı (in_session=False) + template yok → transport'a GİTMEDEN
    # session_expired döner (fail-closed; canlı Meta çağrısı yok).
    res = asyncio.run(
        p.send_whatsapp(
            db=_FakeDB(cfg),
            tenant_id="t1",
            recipient=_PHONE,
            body=None,
            in_session=False,
            template_name=None,
        )
    )
    assert res["success"] is False
    assert res["status"] == "session_expired"


# ── 7. Açık-konuşma yarış idempotency'si (DuplicateKeyError retry) ────


class _UpdRes:
    def __init__(self, upserted_id):
        self.upserted_id = upserted_id


class _RaceConvColl:
    """find_one_and_update yarışta DuplicateKeyError atar; find_one kazananı döner."""

    def __init__(self, winner):
        self._winner = winner
        self.update_one_calls: list = []

    async def find_one_and_update(self, *a, **k):
        raise DuplicateKeyError("dup open conversation")

    async def find_one(self, *a, **k):
        return self._winner

    async def update_one(self, flt, upd, **k):
        self.update_one_calls.append((flt, upd))
        return _UpdRes(None)


class _RaceMsgColl:
    def __init__(self):
        self.upsert_set_on_insert: dict | None = None

    async def find_one(self, *a, **k):
        return None  # pre-check: provider_message_id henüz yok

    async def update_one(self, flt, upd, upsert=False):
        self.upsert_set_on_insert = upd.get("$setOnInsert")
        return _UpdRes("new-msg-id")  # yeni eklendi


class _RaceDB:
    def __init__(self, winner):
        self.contact_center_conversations = _RaceConvColl(winner)
        self.contact_center_messages = _RaceMsgColl()


def test_ingest_open_conversation_race_reuses_winner_not_duplicate():
    db = _RaceDB({"id": "conv-winner", "tenant_id": "t1"})
    wa_message = {
        "id": "wamid.RACE",
        "from": _PHONE,
        "type": "text",
        "text": {"body": "selam"},
    }
    # Yarış: find_one_and_update DuplicateKeyError → ingest RAISE ETMEDEN kazananı
    # okur (webhook 200-fast sözleşmesi korunur; çift/orphan açık konuşma yok).
    asyncio.run(
        ingest_whatsapp_inbound(
            db, tenant_id="t1", phone_number_id="PN1", wa_message=wa_message
        )
    )
    # Mesaj kazanan konuşmaya bağlanır.
    assert db.contact_center_messages.upsert_set_on_insert["conversation_id"] == (
        "conv-winner"
    )
    # Yeni mesaj eklendiği için konuşma aktivitesi (unread/last_message) güncellenir.
    assert db.contact_center_conversations.update_one_calls


# ── 8. Kapanış-sonrası retry: mevcut mesaj orphan konuşma yaratmamalı ──


class _PrecheckConvColl:
    def __init__(self):
        self.find_one_and_update_called = False

    async def find_one_and_update(self, *a, **k):
        self.find_one_and_update_called = True
        return {"id": "should-not-happen"}

    async def find_one(self, *a, **k):
        return None

    async def update_one(self, *a, **k):
        return _UpdRes(None)


class _PrecheckMsgColl:
    def __init__(self):
        self.update_one_called = False

    async def find_one(self, *a, **k):
        return {"_id": "existing"}  # provider_message_id ZATEN var

    async def update_one(self, *a, **k):
        self.update_one_called = True
        return _UpdRes(None)


class _PrecheckDB:
    def __init__(self):
        self.contact_center_conversations = _PrecheckConvColl()
        self.contact_center_messages = _PrecheckMsgColl()


def test_ingest_existing_message_after_close_does_not_create_orphan_conversation():
    db = _PrecheckDB()
    wa_message = {
        "id": "wamid.RETRY",
        "from": _PHONE,
        "type": "text",
        "text": {"body": "tekrar"},
    }
    # Mesaj zaten işlendi (ilk konuşma sonradan kapanmış olabilir) → Meta retry'sinde
    # pre-check devreye girer: ne yeni AÇIK konuşma yaratılır ne de mesaj yeniden
    # upsert edilir (orphan boş konuşma YOK).
    asyncio.run(
        ingest_whatsapp_inbound(
            db, tenant_id="t1", phone_number_id="PN1", wa_message=wa_message
        )
    )
    assert db.contact_center_conversations.find_one_and_update_called is False
    assert db.contact_center_messages.update_one_called is False


# ── 9. Webhook → contact_center köprü sözleşmesi (entegrasyon) ────────
#
# Saf birim testlerinin ötesinde: webhook'un teslimat-durum geri çağrısının
# tükettiği sync_whatsapp_status() davranışını GERÇEK filtre semantiğiyle
# kilitler — yalnızca (tenant + outbound + provider_message_id) eşleşen giden
# mesaj mutasyona uğrar; gelen aynı id ve başka kiracı ASLA dokunulmaz.


class _FilterColl:
    """update_one'ı gerçek Mongo tek-belge semantiğiyle uygular.

    İlk TAM-eşleşen belgeye ``$set`` uygular (yön + tenant + provider id filtresini
    gerçekten değerlendirir; sahte "çağrı kaydı" değil).
    """

    def __init__(self, docs: list[dict]):
        self.docs = docs

    @staticmethod
    def _match(doc: dict, flt: dict) -> bool:
        return all(doc.get(k) == v for k, v in flt.items())

    async def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if self._match(d, flt):
                d.update(update.get("$set", {}))
                return _UpdRes(None)
        return _UpdRes(None)


class _StatusDB:
    def __init__(self, docs: list[dict]):
        self.contact_center_messages = _FilterColl(docs)


def test_status_sync_updates_only_matching_outbound_message():
    out_doc = {
        "id": "m-out", "tenant_id": "t1", "channel": "whatsapp",
        "provider_message_id": "wamid.OUT", "direction": "outbound", "status": "sent",
    }
    # Aynı provider id'li GELEN mesaj — yön muhafızı nedeniyle dokunulmamalı.
    in_doc = {
        "id": "m-in", "tenant_id": "t1", "channel": "whatsapp",
        "provider_message_id": "wamid.OUT", "direction": "inbound", "status": "received",
    }
    # Başka kiracının giden mesajı — tenant izolasyonu nedeniyle dokunulmamalı.
    other_tenant = {
        "id": "m-x", "tenant_id": "t2", "channel": "whatsapp",
        "provider_message_id": "wamid.OUT", "direction": "outbound", "status": "sent",
    }
    db = _StatusDB([in_doc, other_tenant, out_doc])

    # Meta yaşam döngüsü: delivered → read → failed.
    asyncio.run(sync_whatsapp_status(
        db, tenant_id="t1", provider_message_id="wamid.OUT", meta_status="delivered"
    ))
    assert out_doc["status"] == "delivered"
    assert "delivered_at" in out_doc

    asyncio.run(sync_whatsapp_status(
        db, tenant_id="t1", provider_message_id="wamid.OUT", meta_status="read"
    ))
    assert out_doc["status"] == "read"
    assert "read_at" in out_doc

    asyncio.run(sync_whatsapp_status(
        db, tenant_id="t1", provider_message_id="wamid.OUT",
        meta_status="failed", error_message="undeliverable",
    ))
    assert out_doc["status"] == "failed"
    assert out_doc["error"] == "undeliverable"

    # İzolasyon: gelen aynı id + başka kiracı orijinal halinde kaldı.
    assert in_doc["status"] == "received"
    assert other_tenant["status"] == "sent"


def test_status_sync_ignores_unknown_meta_status():
    out_doc = {
        "id": "m", "tenant_id": "t1", "channel": "whatsapp",
        "provider_message_id": "wamid.Z", "direction": "outbound", "status": "sent",
    }
    db = _StatusDB([out_doc])
    asyncio.run(sync_whatsapp_status(
        db, tenant_id="t1", provider_message_id="wamid.Z", meta_status="bogus"
    ))
    # Tanınmayan durum → no-op (mevcut durum korunur; sahte ilerleme yok).
    assert out_doc["status"] == "sent"


# ── 10. reveal_phone izin kapısı (operatör seviyesi MANAGE gerekli) ──


class _StubUser:
    def __init__(self, *, tenant_id, uid, role, granted_permissions=None):
        self.tenant_id = tenant_id
        self.id = uid
        self.role = role
        self.granted_permissions = granted_permissions


def test_reveal_phone_gate_requires_manage_permission():
    from domains.contact_center.router import _can_reveal_phone

    # MANAGE_CONTACT_CENTER taşıyan operatör rolleri → tam numarayı açabilir.
    agent = _StubUser(tenant_id="t1", uid="a", role=UserRole.CALL_CENTER_AGENT)
    front = _StubUser(tenant_id="t1", uid="f", role=UserRole.FRONT_DESK)
    assert _can_reveal_phone(agent) is True
    assert _can_reveal_phone(front) is True

    # MANAGE olmayan rol → açamaz (PII varsayılan maskeli kalır).
    hk = _StubUser(tenant_id="t1", uid="h", role=UserRole.HOUSEKEEPING)
    assert _can_reveal_phone(hk) is False

    # Salt-görüntüleme izni TEK BAŞINA yetmez (MANAGE şart).
    viewer = _StubUser(
        tenant_id="t1", uid="v", role=UserRole.STAFF,
        granted_permissions=["view_contact_center"],
    )
    assert _can_reveal_phone(viewer) is False

    # Super admin → tam yetki.
    sa = _StubUser(tenant_id="t1", uid="s", role=UserRole.SUPER_ADMIN)
    assert _can_reveal_phone(sa) is True


# ── 11. Send route: sağlayıcı istisnasında FAILED kalıcılaşır (502) ──


class _SendFakeMsgColl:
    def __init__(self, inbound_doc):
        self._inbound = inbound_doc
        self.inserted: dict | None = None

    async def find_one(self, *a, **k):
        # _is_within_session_window okuması: güncel gelen mesaj → pencere AÇIK.
        return self._inbound

    async def insert_one(self, doc):
        self.inserted = doc
        return _UpdRes(None)


class _SendFakeConvColl:
    def __init__(self, conv):
        self._conv = conv
        self.update_called = False

    async def find_one(self, *a, **k):
        return self._conv

    async def update_one(self, *a, **k):
        self.update_called = True
        return _UpdRes(None)


class _SendFakeDB:
    def __init__(self, conv, inbound_doc):
        self.contact_center_conversations = _SendFakeConvColl(conv)
        self.contact_center_messages = _SendFakeMsgColl(inbound_doc)


# Sağlayıcı istisnası, mesajında PII (alıcı telefonu) + secret (token) taşır;
# bunların log/HTTP detail/persist edilen error'a SIZMADIĞINI kanıtlamak için.
_LEAK_TOKEN = "EAAG-SECRET-TOKEN-XYZ"
_LEAK_MSG = f"transport failed url=https://graph/?access_token={_LEAK_TOKEN} to={_PHONE}"


class _RaisingProvider:
    async def send_whatsapp(self, **k):
        raise RuntimeError(_LEAK_MSG)


def test_send_route_persists_failed_on_provider_exception(monkeypatch, caplog):
    from domains.contact_center import router as cc_router
    from domains.contact_center.router import (
        SendWhatsAppMessage,
        send_conversation_message,
    )

    svc = _svc()
    conv = {
        "id": "c1", "tenant_id": "t1", "channel": "whatsapp",
        "caller_id_enc": svc.encrypt_value(_PHONE),
    }
    inbound = {
        "id": "m0", "tenant_id": "t1", "conversation_id": "c1",
        "direction": "inbound", "created_at": datetime.now(UTC),
    }
    fake_db = _SendFakeDB(conv, inbound)
    monkeypatch.setattr(cc_router, "db", fake_db)
    monkeypatch.setattr(
        cc_router, "get_communication_provider", lambda *a, **k: _RaisingProvider()
    )

    user = _StubUser(tenant_id="t1", uid="agent1", role=UserRole.CALL_CENTER_AGENT)
    payload = SendWhatsAppMessage(body="merhaba")

    raised: HTTPException | None = None
    with caplog.at_level(logging.DEBUG, logger="domains.contact_center.router"):
        try:
            asyncio.run(
                send_conversation_message("c1", payload, current_user=user)
            )
        except HTTPException as e:
            raised = e

    # Sağlayıcı patladı → 502 (sahte başarı YOK).
    assert raised is not None
    assert raised.status_code == 502
    # ...ama kayıt FAILED olarak KALICILAŞTIRILDI (ajan "iletilemedi" görür).
    inserted = fake_db.contact_center_messages.inserted
    assert inserted is not None
    assert inserted["status"] == "failed"
    assert inserted["direction"] == "outbound"
    # Başarı yan-etkisi (konuşma aktivite güncellemesi) ÇALIŞMADI.
    assert fake_db.contact_center_conversations.update_called is False

    # PII/secret sızıntısı YOK: istisna metni (token + alıcı telefonu) ne log'a,
    # ne HTTP detail'e, ne de persist edilen error'a girer (generic kalır).
    surfaces = [caplog.text, str(raised.detail), str(inserted.get("error"))]
    for s in surfaces:
        assert _LEAK_TOKEN not in s, s
        assert _PHONE not in s, s
        assert _LEAK_MSG not in s, s
    # Yine de hata gerçekten loglandı (yalnız istisna sınıf adıyla).
    assert "RuntimeError" in caplog.text


class _DecryptRaisingSvc:
    """decrypt_value PII içeren bir mesajla patlar; encrypt çağrılmamalı."""

    def decrypt_value(self, *a, **k):
        raise RuntimeError(f"decrypt boom {_PHONE}")


def test_send_route_decrypt_failure_returns_409_no_failed_record(monkeypatch, caplog):
    from domains.contact_center import router as cc_router
    from domains.contact_center.router import (
        SendWhatsAppMessage,
        send_conversation_message,
    )

    conv = {
        "id": "c1", "tenant_id": "t1", "channel": "whatsapp",
        "caller_id_enc": "bozuk-zarf",
    }
    inbound = {
        "id": "m0", "tenant_id": "t1", "conversation_id": "c1",
        "direction": "inbound", "created_at": datetime.now(UTC),
    }
    fake_db = _SendFakeDB(conv, inbound)
    monkeypatch.setattr(cc_router, "db", fake_db)
    monkeypatch.setattr(
        cc_router, "get_field_encryption_service", lambda: _DecryptRaisingSvc()
    )

    user = _StubUser(tenant_id="t1", uid="agent1", role=UserRole.CALL_CENTER_AGENT)
    payload = SendWhatsAppMessage(body="merhaba")

    raised: HTTPException | None = None
    with caplog.at_level(logging.DEBUG, logger="domains.contact_center.router"):
        try:
            asyncio.run(
                send_conversation_message("c1", payload, current_user=user)
            )
        except HTTPException as e:
            raised = e

    # Decrypt patladı → 409 (500 sızdırma YOK), gönderim denenmedi.
    assert raised is not None
    assert raised.status_code == 409
    # Gönderim denenmediği için FAILED kaydı YAZILMAZ.
    assert fake_db.contact_center_messages.inserted is None
    # Decrypt istisnasındaki alıcı telefonu log'a SIZMAZ (yalnız conv id).
    assert _PHONE not in caplog.text
