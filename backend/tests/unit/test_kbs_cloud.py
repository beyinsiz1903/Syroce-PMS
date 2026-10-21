"""Cloud KBS contract tests. All authority responses are synthetic; no network."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from defusedxml import ElementTree

from core import kbs_cloud as cloud
from core import kbs_jandarma as soap
from core.crypto.service import CredentialEncryptionService

CREDENTIALS = {"user_tc": "12345678901", "facility_code": "123", "password": "synthetic-fixture-not-a-real-secret"}
PAYLOAD = {"nationality": "TC", "id_number": "12345678901", "room_number": "101", "check_in": "2026-10-20T14:00:00", "check_out": "2026-10-21T11:00:00"}


def response(method, ok="true", code="Basarili", *, nested=False):
    result = f"<d:Basarili>{ok}</d:Basarili><d:HataKodu>{code}</d:HataKodu>"
    if nested:
        result = f"<d:sonuc>{result}</d:sonuc>"
    return (
        f'<s:Envelope xmlns:s="{soap.SOAP_NS}" xmlns:d="{soap.DATA_NS}"><s:Body><{method}Response xmlns="{soap.NS}"><{method}Result>{result}</{method}Result></{method}Response></s:Body></s:Envelope>'
    ).encode()


@pytest.mark.parametrize(
    "action,foreign,method",
    [
        ("checkin", False, "MusteriKimlikNoGiris"),
        ("checkout", False, "MusteriKimlikNoCikis"),
        ("checkin", True, "MusteriYabanciGiris"),
        ("checkout", True, "MusteriYabanciCikis"),
    ],
)
def test_real_wsdl_operation_and_member_order(action, foreign, method):
    payload = {**PAYLOAD, **({"nationality": "DE", "passport_number": "SYNTHETIC", "guest_name": "Example Guest", "gender": "F", "birth_date": "1990-01-01"} if foreign else {})}
    operation, xml = soap.build_request(CREDENTIALS, payload, action)
    assert operation == method
    root = ElementTree.fromstring(xml)
    fields = root.find(f".//{{{soap.NS}}}musteri")
    names = [node.tag.rsplit("}", 1)[-1] for node in fields]
    assert names == sorted(names)
    assert ("KIMLIKNO" in names) is not foreign
    assert ("CKSTRH" in names) is (action == "checkout")


def test_connection_verification_has_no_guest_record():
    method, xml = soap.build_request(CREDENTIALS)
    assert method == "ParametreListele"
    assert "musteri" not in xml
    assert "ULKELER" in xml


def test_user_input_is_xml_escaped_and_time_is_turkey_local():
    _, xml = soap.build_request({**CREDENTIALS, "password": "<&fixture>"}, PAYLOAD)
    assert "&lt;&amp;fixture&gt;" in xml
    assert "2026-10-20T11:00:00+00:00" in xml


@pytest.mark.parametrize(
    "change",
    [
        {"facility_code": "9223372036854775808"},
        {"facility_code": "0"},
        {"user_tc": "short"},
        {"password": ""},
    ],
)
def test_invalid_credentials_fail_before_network(change):
    with pytest.raises(soap.JandarmaError):
        soap.build_request({**CREDENTIALS, **change})


@pytest.mark.parametrize("ok,code", [("false", "Basarili"), ("true", "YetkiHatasi"), ("true", "")])
def test_success_requires_both_authority_success_fields(ok, code):
    with pytest.raises(soap.JandarmaError):
        soap.parse_response(response("ParametreListele", ok, code), "ParametreListele")


def test_parse_nested_success_and_dont_leak_response_fields():
    assert soap.parse_response(response("MusteriKimlikNoGiris", nested=True), "MusteriKimlikNoGiris") == {"method": "MusteriKimlikNoGiris", "code": "Basarili"}


@pytest.mark.parametrize("content", [b"not xml", b"<!DOCTYPE a [<!ENTITY e SYSTEM 'file:///etc/passwd'>]><a>&e;</a>", response("OtherOperation")])
def test_invalid_or_wrong_operation_response_is_uncertain(content):
    with pytest.raises(soap.JandarmaError) as exc:
        soap.parse_response(content, "ParametreListele")
    assert exc.value.uncertain


@pytest.mark.asyncio
async def test_timeout_is_not_silently_retried_or_reported_success(monkeypatch):
    send = AsyncMock(side_effect=TimeoutError("secret-value-must-not-escape"))
    monkeypatch.setattr(soap, "safe_post_async", send)
    with pytest.raises(soap.JandarmaError) as exc:
        await soap.call_jandarma(CREDENTIALS, PAYLOAD)
    assert exc.value.uncertain
    assert "secret" not in str(exc.value)
    send.assert_awaited_once()
    assert send.call_args.args == (soap.ENDPOINT,)


@pytest.fixture
def crypto(monkeypatch):
    monkeypatch.setenv("CM_CREDENTIAL_KEY", "synthetic-local-test-encryption-key-32-chars")
    monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "synthetic-local-test-master-key-at-least-32-chars")
    monkeypatch.setenv("CM_KEY_VERSION_CURRENT", "test1")
    monkeypatch.setenv("CRYPTO_V2_ENABLED", "true")
    monkeypatch.delenv("CM_KEY_VERSION", raising=False)
    monkeypatch.delenv("CM_MASTER_KEY_PREVIOUS", raising=False)
    monkeypatch.delenv("CM_KEY_VERSION_PREVIOUS", raising=False)
    monkeypatch.setenv("CRYPTO_BYPASS_ALLOWED", "false")
    svc = CredentialEncryptionService()
    monkeypatch.setattr(cloud, "get_crypto_service", lambda: svc)
    monkeypatch.setenv("KBS_PUBLIC_EGRESS_IP", "8.8.8.8")
    return svc


def test_credentials_are_encrypted_and_tenant_bound(crypto):
    encrypted = cloud.seal("tenant-a", CREDENTIALS)
    config = {"tenant_id": "tenant-a", "credentials_enc": encrypted}
    assert CREDENTIALS["password"] not in encrypted
    assert cloud.reveal("tenant-a", config) == CREDENTIALS
    with pytest.raises(soap.JandarmaError):
        cloud.reveal("tenant-b", {**config, "tenant_id": "tenant-b"})
    assert "credentials" not in str(cloud.public_status(config))


def test_secret_storage_has_no_plaintext_fallback(crypto, monkeypatch):
    monkeypatch.delenv("CM_MASTER_KEY_CURRENT")
    with pytest.raises(soap.JandarmaError, match="secure_storage"):
        cloud.seal("tenant-a", CREDENTIALS)


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_):
        return self

    def __aiter__(self):
        async def iterate():
            for row in self.rows:
                yield row

        return iterate()


def database(config=None, jobs=()):
    settings = SimpleNamespace(
        find_one=AsyncMock(return_value=config),
        find=MagicMock(return_value=Cursor([config] if config else [])),
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)),
    )
    reports = SimpleNamespace(
        count_documents=AsyncMock(return_value=0),
        find=MagicMock(return_value=Cursor([])),
        find_one_and_update=AsyncMock(side_effect=[*jobs, None]),
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1)),
        insert_one=AsyncMock(),
    )
    return SimpleNamespace(kbs_cloud_configs=settings, kbs_reports=reports, bookings=SimpleNamespace(update_one=AsyncMock()), kbs_alerts=SimpleNamespace(insert_one=AsyncMock()))


@pytest.mark.asyncio
async def test_new_credentials_cannot_enable_without_verification(crypto):
    db = database()
    with pytest.raises(soap.JandarmaError, match="connection_verification_required"):
        await cloud.save_config(db, "tenant-a", {**CREDENTIALS, "enabled": True, "live_confirmed": True}, "admin")
    db.kbs_cloud_configs.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_verification_is_tenant_scoped_and_does_not_enable_sender(crypto, monkeypatch):
    config = {"tenant_id": "tenant-a", "revision": "r1", "credentials_enc": cloud.seal("tenant-a", CREDENTIALS)}
    db = database(config)
    call = AsyncMock(return_value={"code": "Basarili"})
    monkeypatch.setattr(cloud, "call_jandarma", call)
    await cloud.verify_config(db, "tenant-a")
    call.assert_awaited_once_with(CREDENTIALS)
    query, update = db.kbs_cloud_configs.update_one.call_args.args
    assert query["tenant_id"] == "tenant-a" and query["revision"] == "r1"
    assert "enabled" not in update["$set"]


@pytest.mark.asyncio
async def test_missing_static_egress_blocks_verification(crypto, monkeypatch):
    monkeypatch.delenv("KBS_PUBLIC_EGRESS_IP")
    call = AsyncMock()
    monkeypatch.setattr(cloud, "call_jandarma", call)
    with pytest.raises(soap.JandarmaError, match="fixed_egress_ip_required"):
        await cloud.verify_config(database(), "tenant-a")
    call.assert_not_awaited()


@pytest.mark.parametrize("flag", ["KBS_TEST_MODE", "KBS_AUTO_DISPATCH"])
@pytest.mark.asyncio
async def test_test_mode_and_kill_switch_never_send(crypto, monkeypatch, flag):
    monkeypatch.setenv(flag, "1" if flag == "KBS_TEST_MODE" else "0")
    call = AsyncMock()
    monkeypatch.setattr(cloud, "call_jandarma", call)
    await cloud.dispatch_cloud_jobs(database())
    call.assert_not_awaited()


@pytest.mark.parametrize("uncertain", [True, False])
@pytest.mark.asyncio
async def test_delivery_failure_does_not_complete_or_automatically_retry(crypto, monkeypatch, uncertain):
    from core import kbs_dispatch, kbs_payload_builder

    monkeypatch.setenv("KBS_TEST_MODE", "0")
    monkeypatch.setenv("KBS_AUTO_DISPATCH", "1")
    config = {
        "tenant_id": "tenant-a",
        "revision": "r1",
        "verified_revision": "r1",
        "live_confirmed": True,
        "enabled": True,
        "verified_egress_ip": "8.8.8.8",
        "credentials_enc": cloud.seal("tenant-a", CREDENTIALS),
    }
    job = {"tenant_id": "tenant-a", "id": "j1", "booking_id": "b1", "action": "checkin", "worker_id": kbs_dispatch.WORKER_ID}
    db = database(config, [job])
    monkeypatch.setattr(kbs_payload_builder, "build_kbs_payload_snapshot", AsyncMock(return_value=({"guest_id": "g1"}, {}, PAYLOAD)))
    call = AsyncMock(side_effect=[{"code": "Basarili"}, soap.JandarmaError("delivery_unknown_check_authority", uncertain=uncertain)])
    monkeypatch.setattr(cloud, "call_jandarma", call)
    complete = AsyncMock()
    monkeypatch.setattr(kbs_dispatch, "_complete", complete)
    result = await cloud.dispatch_cloud_jobs(db)
    assert result["sent"] == 0 and result["blocked"] == 1
    complete.assert_not_awaited()
    assert call.await_count == 2
    assert call.await_args_list[0].args == (CREDENTIALS,)
    query = db.kbs_reports.find_one_and_update.call_args.args[0]
    assert query["tenant_id"] == "tenant-a" and len(query["$or"]) == 1
    hold = db.kbs_reports.update_one.call_args.args[1]
    assert hold["$set"]["status"] == "dead"
    assert hold["$set"]["delivery_uncertain"] is uncertain
    assert ("$unset" not in hold) is uncertain


@pytest.mark.asyncio
async def test_received_reply_is_preserved_as_local_receipt_not_official_reference(crypto, monkeypatch):
    from core import kbs_dispatch, kbs_payload_builder

    monkeypatch.setenv("KBS_TEST_MODE", "0")
    config = {
        "tenant_id": "tenant-a",
        "revision": "r1",
        "verified_revision": "r1",
        "live_confirmed": True,
        "enabled": True,
        "verified_egress_ip": "8.8.8.8",
        "credentials_enc": cloud.seal("tenant-a", CREDENTIALS),
    }
    job = {"tenant_id": "tenant-a", "id": "j1", "booking_id": "b1", "action": "checkout", "worker_id": kbs_dispatch.WORKER_ID}
    db = database(config, [job])
    monkeypatch.setattr(kbs_payload_builder, "build_kbs_payload_snapshot", AsyncMock(return_value=({"guest_id": "g1"}, {}, PAYLOAD)))
    monkeypatch.setattr(cloud, "call_jandarma", AsyncMock(return_value={"code": "Basarili", "method": "MusteriKimlikNoCikis"}))
    result = await cloud.dispatch_cloud_jobs(db)
    assert result["sent"] == 1
    stored = db.kbs_reports.update_one.call_args.args[1]["$set"]
    assert stored["official_reference"] is False
    assert stored["authority_response_code"] == "Basarili"
    booking_update = db.bookings.update_one.call_args.args[1]["$set"]
    assert booking_update["kbs_checkout_reported"] is True
    assert "kbs_reported" not in booking_update


@pytest.mark.parametrize("path,method", [("/api/kbs/cloud/settings", "put"), ("/api/kbs/cloud/verify", "post")])
def test_reception_cannot_configure_or_verify_authority_credentials(monkeypatch, path, method):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from core.security import get_current_user
    from routers import kbs

    db = database()
    monkeypatch.setattr(kbs, "db", db)
    app = FastAPI()
    app.include_router(kbs.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="staff", tenant_id="tenant-a", role="front_desk", permissions=[])
    with TestClient(app) as client:
        result = getattr(client, method)(path, json={})
    assert result.status_code == 403
    db.kbs_cloud_configs.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_pause_and_ip_change_never_consume_queued_jobs(crypto, monkeypatch):
    monkeypatch.setenv("KBS_TEST_MODE", "0")
    config = {"tenant_id": "tenant-a", "revision": "r1", "verified_revision": "r1", "live_confirmed": True, "enabled": True, "verified_egress_ip": "8.8.4.4"}
    db = database(config)
    call = AsyncMock()
    monkeypatch.setattr(cloud, "call_jandarma", call)
    await cloud.dispatch_cloud_jobs(db)
    call.assert_not_awaited()
    db.kbs_reports.find_one_and_update.assert_not_awaited()
    assert db.kbs_cloud_configs.update_one.call_args.args[1]["$set"]["enabled"] is False
