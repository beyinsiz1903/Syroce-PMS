"""Syroce Contact Center — Faz 0 doktrin değişmezleri (regresyon kilidi).

Bu testler omnichannel iskeletinin (Conversation/Message/CallLog + mock
sağlayıcı + entitlement/RBAC bağlantısı) güvenlik garantilerini bir regresyon
gemiye girmeden yakalar:

  1. PII at-rest açık metin YOK — modeller arayan telefonu/adını/mesaj
     gövdesini/ses kaydını ASLA açık alanda taşımaz; yalnızca ``_enc``/
     ``_hash``/``_ref`` türevleri bulunur.
  2. Mock sağlayıcı fail-closed — ``send_message`` sahte "gönderildi"
     dönmez (``success=False``, ``status=not_configured``).
  3. Add-on fail-closed — ``contact_center`` her plan kademesinde varsayılan
     KAPALI; entitlement route eşlemesi mevcut ve exempt değil.
  4. RBAC iskeleti additive ve doğru kapılı.

Saf birim testidir — çalışan backend / canlı DB gerektirmez
(``test_academy_security.py`` desenini izler).
"""
from __future__ import annotations

import asyncio

from core.entitlement import EXEMPT_PREFIXES, ROUTE_MODULE_MAP
from domains.admin.subscription_models import (
    PLAN_MODULE_DEFAULTS,
    FeatureFlag,
    get_all_module_keys,
)
from domains.contact_center.provider import (
    CommunicationProvider,
    MockProvider,
    WhatsAppCloudProvider,
    get_communication_provider,
)
from domains.contact_center.read_models import CONVERSATION_DTO_KEYS
from models.enums import (
    CallStatus,
    ContactCenterChannel,
    ConversationStatus,
    MessageDirection,
    MessageStatus,
    Permission,
    ROLE_PERMISSIONS,
    UserRole,
)
from models.schemas.contact_center import CallLog, Conversation, Message
from modules.pms_core.role_permission_service import (
    MODULE_ROLES,
    OPERATION_PERMISSIONS,
)

# Hiçbir koşulda bir belge modelinde görünmemesi gereken açık-metin PII alanları.
_FORBIDDEN_PLAINTEXT = {
    "caller_id",
    "caller_phone",
    "phone",
    "phone_number",
    "msisdn",
    "caller_display_name",
    "display_name",
    "name",
    "body",
    "text",
    "message",
    "content",
    "recording_url",
    "recording",
    "media_url",
}


def _fields(model_cls) -> set[str]:
    return set(model_cls.model_fields.keys())


# ── 1. PII at-rest açık metin YOK ────────────────────────────────────


def test_models_carry_no_plaintext_pii_fields():
    for model_cls in (Conversation, Message, CallLog):
        leaked = _fields(model_cls) & _FORBIDDEN_PLAINTEXT
        assert not leaked, f"{model_cls.__name__} açık-metin PII taşıyor: {leaked}"


def test_models_require_tenant_id():
    for model_cls in (Conversation, Message, CallLog):
        assert model_cls.model_fields["tenant_id"].is_required(), model_cls.__name__


def test_pii_is_only_present_in_encrypted_or_reference_form():
    conv = _fields(Conversation)
    assert {"caller_id_hash", "caller_id_enc", "caller_display_name_enc"} <= conv
    msg = _fields(Message)
    assert "body_enc" in msg and "media_refs" in msg
    call = _fields(CallLog)
    assert {"caller_id_hash", "caller_id_enc", "recording_ref"} <= call
    # Ses kaydı yalnızca referans; açık imzalı URL alanı yok.
    assert "recording_url" not in call


def test_list_dto_allowlist_excludes_all_pii_and_ciphertext():
    # Faz 1: liste ucu artık projection yerine allowlist DTO kullanır
    # (read_models.conversation_to_dto). Allowlist hiçbir şifreli/blind-index/
    # Mongo iç alanını dışarı vermemeli — garanti aynı, mekanizma değişti.
    for k in CONVERSATION_DTO_KEYS:
        assert not k.endswith("_enc"), k
        assert "_hash" not in k, k
        assert k != "_id", k
    for forbidden in (
        "caller_id_enc",
        "caller_id_hash",
        "caller_display_name_enc",
        "_id",
    ):
        assert forbidden not in CONVERSATION_DTO_KEYS, forbidden


# ── 2. Mock sağlayıcı fail-closed ────────────────────────────────────


def test_mock_provider_send_is_fail_closed():
    provider = get_communication_provider()
    assert isinstance(provider, CommunicationProvider)
    res = asyncio.run(
        provider.send_message(to_hash="h", channel="whatsapp", body="merhaba")
    )
    assert res["success"] is False
    assert res["status"] == "not_configured"


def test_known_whatsapp_resolves_real_provider_unknown_falls_back_to_mock():
    # Faz 1: "whatsapp" artık gerçek (fail-closed) WhatsAppCloudProvider'a çözülür.
    assert isinstance(get_communication_provider("whatsapp"), WhatsAppCloudProvider)
    assert isinstance(
        get_communication_provider("whatsapp_cloud"), WhatsAppCloudProvider
    )
    # Bilinmeyen anahtar HÂLÂ sessizce gerçek transport gibi davranmaz — mock'a düşer.
    assert isinstance(get_communication_provider("does-not-exist"), MockProvider)


# ── 3. Add-on entitlement fail-closed ────────────────────────────────


def test_contact_center_is_off_by_default_in_every_tier():
    assert FeatureFlag.CONTACT_CENTER.value == "contact_center"
    assert "contact_center" in get_all_module_keys()
    for tier, mods in PLAN_MODULE_DEFAULTS.items():
        assert mods.get("contact_center") is False, f"{tier} varsayılan açık olmamalı"


def test_entitlement_route_is_mapped_and_not_exempt():
    assert ROUTE_MODULE_MAP.get("/api/contact-center/") == "contact_center"
    path = "/api/contact-center/conversations"
    matched = [m for p, m in ROUTE_MODULE_MAP.items() if path.startswith(p)]
    assert matched == ["contact_center"], matched
    assert not any(path.startswith(e) for e in EXEMPT_PREFIXES)


# ── 4. RBAC iskeleti additive + doğru kapılı ─────────────────────────


def test_rbac_role_and_permissions_wired():
    assert UserRole.CALL_CENTER_AGENT.value == "call_center_agent"
    assert Permission.VIEW_CONTACT_CENTER.value == "view_contact_center"
    assert Permission.MANAGE_CONTACT_CENTER.value == "manage_contact_center"
    for role in (UserRole.CALL_CENTER_AGENT, UserRole.FRONT_DESK, UserRole.SUPERVISOR):
        perms = ROLE_PERMISSIONS[role]
        assert (
            Permission.VIEW_CONTACT_CENTER in perms
            or Permission.VIEW_CONTACT_CENTER.value in perms
        ), role


def test_module_roles_gate_is_least_privilege():
    roles = MODULE_ROLES["contact_center"]
    assert UserRole.CALL_CENTER_AGENT in roles
    assert {UserRole.FRONT_DESK, UserRole.SUPERVISOR, UserRole.ADMIN, UserRole.SUPER_ADMIN} <= roles
    # Modülle ilgisi olmayan roller kapı dışında kalmalı.
    assert UserRole.HOUSEKEEPING not in roles
    assert OPERATION_PERMISSIONS["view_contact_center"] == [Permission.VIEW_CONTACT_CENTER]
    assert OPERATION_PERMISSIONS["manage_contact_center"] == [Permission.MANAGE_CONTACT_CENTER]


# ── Yeni enum vokabüleri (sözleşme kilidi) ───────────────────────────


def test_new_enum_values_are_stable():
    assert ContactCenterChannel.WHATSAPP.value == "whatsapp"
    assert ContactCenterChannel.VOICE.value == "voice"
    assert ConversationStatus.OPEN.value == "open"
    assert MessageDirection.INBOUND.value == "inbound"
    assert MessageStatus.QUEUED.value == "queued"
    assert CallStatus.RINGING.value == "ringing"
