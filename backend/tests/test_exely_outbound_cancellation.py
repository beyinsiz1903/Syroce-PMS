"""Offline acceptance of operator cancellations, including uncertain deliveries."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from lxml import etree
from pymongo.errors import DuplicateKeyError

from core.outbox_dispatcher import dispatch_outbox_event
from core.outbox_service import EXELY_RESERVATION_CANCEL
from domains.channel_manager.providers.exely import factory
from domains.channel_manager.providers.exely import reservation_cancellation as cancel
from domains.channel_manager.providers.exely.errors import ExelyTemporaryError
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.provider_quota import QuotaDecision
from domains.channel_manager.providers.exely.response_parser import parse_cancel_rs
from domains.channel_manager.providers.exely.soap_builder import build_cancel_rq, get_soap_action_uri
from domains.channel_manager.providers.hotelrunner.schemas import ProviderResult

pytestmark = pytest.mark.exely_failure_stress
OTA = "http://www.opentravel.org/OTA/2003/05"
SOAP = "http://schemas.xmlsoap.org/soap/envelope/"


def response(body='<Success/>', token="echo", operation="OTA_CancelRS"):
    return (f'<s:Envelope xmlns:s="{SOAP}"><s:Body><{operation} xmlns="{OTA}" EchoToken="{token}">'
            f'{body}</{operation}></s:Body></s:Envelope>').encode()


def test_documented_request_preserves_original_id_and_escapes_reason():
    xml = build_cancel_rq("user", "password", "TEST-PROPERTY", "provider-original", 'Guest & hotel "agreed"', "echo")
    root = etree.fromstring(xml.encode())
    rq = root.find(f"{{{SOAP}}}Body/{{{OTA}}}OTA_CancelRQ")
    assert rq.attrib == {"Version": "1.17", "EchoToken": "echo"}
    assert len(rq) == 1
    assert rq[0].attrib == {"ID": "provider-original", "ID_Context": "PMSCONNECT", "Reason": 'Guest & hotel "agreed"'}
    assert "CancellationOverrides" not in xml
    assert get_soap_action_uri("OTA_CancelRQ") == "https://www.hopenapi.com/Api/PMSConnect/CancelRQ"


@pytest.mark.parametrize("xml", [b"bad XML", response(token="other"), response(operation="OTA_NotifReportRS"),
    response(body=""), response(body="<Warnings/>"), b'<Envelope><Success/></Envelope>',
    f'<s:Envelope xmlns:s="{SOAP}"><s:Body><s:Fault/></s:Body></s:Envelope>'.encode()])
def test_only_matching_explicit_cancel_success_confirms_delivery(xml):
    result = parse_cancel_rs(xml, "echo")
    assert result["success"] is False
    assert result["result_class"] == "AMBIGUOUS"


def test_parser_success_and_safe_rejection():
    assert parse_cancel_rs(response(), "echo")["success"] is True
    result = parse_cancel_rs(response('<Errors><Error Code="402">private details</Error></Errors>'), "echo")
    assert result["success"] is False
    assert result["result_class"] == "REJECTED"
    assert "private details" not in str(result)


@pytest.mark.asyncio
async def test_provider_sends_cancel_once_and_does_not_retry_uncertain_timeout(monkeypatch):
    monkeypatch.setattr("domains.channel_manager.providers.exely.provider.reservation_sync_block_reason", lambda: None)
    provider = ExelyProvider(username="user", password="password", hotel_code="test", max_retries=3)
    provider._transport.send_soap = AsyncMock(side_effect=ExelyTemporaryError("timeout"))
    result = await provider.cancel_reservation("external", "Guest request", "echo")
    assert not result.success
    assert result.metadata["provider_write_count"] == 1
    provider._transport.send_soap.assert_awaited_once()


@pytest.mark.asyncio
async def test_provider_confirms_matching_response(monkeypatch):
    monkeypatch.setattr("domains.channel_manager.providers.exely.provider.reservation_sync_block_reason", lambda: None)
    provider = ExelyProvider(username="user", password="password", hotel_code="test")
    provider._transport.send_soap = AsyncMock(return_value=response())
    result = await provider.cancel_reservation("external", "Guest request", "echo")
    assert result.success
    assert result.metadata["provider_write_count"] == 1
    assert provider._transport.send_soap.call_args.args[1].endswith("/CancelRQ")


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", ["runtime", "quota"])
async def test_provider_gates_block_before_io(monkeypatch, blocked):
    monkeypatch.setattr("domains.channel_manager.providers.exely.provider.reservation_sync_block_reason",
                        lambda: "DRY_RUN" if blocked == "runtime" else None)
    quota = SimpleNamespace(reserve=AsyncMock(return_value=QuotaDecision(False, "QUOTA", 60)))
    provider = ExelyProvider(username="user", password="password", hotel_code="test", quota_guard=quota)
    provider._transport.send_soap = AsyncMock()
    result = await provider.cancel_reservation("external", "Guest request", "echo")
    assert not result.success
    assert result.metadata["provider_write_count"] == 0
    provider._transport.send_soap.assert_not_awaited()


def get(row, path):
    for key in path.split("."):
        if not isinstance(row, dict) or key not in row:
            return None
        row = row[key]
    return row


def matches(row, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(matches(row, clause) for clause in expected):
                return False
            continue
        actual = get(row, key)
        if isinstance(expected, dict):
            for op, value in expected.items():
                if op == "$in" and actual not in value:
                    return False
                if op == "$exists" and (actual is not None) != value:
                    return False
                if op == "$lte" and (actual is None or actual > value):
                    return False
        elif actual != expected:
            return False
    return True


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, key, _direction):
        self.rows.sort(key=lambda row: get(row, key) or "")
        return self

    async def to_list(self, length):
        return deepcopy(self.rows[:length])


class Collection:
    def __init__(self, rows=()):
        self.rows = deepcopy(list(rows))

    async def find_one(self, query, *_):
        return deepcopy(next((row for row in self.rows if matches(row, query)), None))

    def find(self, query):
        return Cursor([deepcopy(row) for row in self.rows if matches(row, query)])

    async def insert_one(self, document):
        for key in ("_id", "idempotency_key"):
            if key in document and any(row.get(key) == document[key] for row in self.rows):
                raise DuplicateKeyError("duplicate")
        self.rows.append(deepcopy(document))

    async def update_one(self, query, update):
        row = next((row for row in self.rows if matches(row, query)), None)
        if row is None:
            return SimpleNamespace(modified_count=0, matched_count=0)
        original = deepcopy(row)
        for path, value in update.get("$set", {}).items():
            node = row
            keys = path.split(".")
            for key in keys[:-1]:
                node = node.setdefault(key, {})
            node[keys[-1]] = deepcopy(value)
        return SimpleNamespace(modified_count=int(original != row), matched_count=1)


@pytest.fixture
def scenario(monkeypatch):
    rows = [{"id": f"room-{index}", "tenant_id": "tenant", "property_id": "property", "status": "cancelled",
             "source": {"provider": "exely", "external_reservation_id": f"wrong-slot-{index}"},
             "provider_group_reservation_id": "original-provider-booking", "provider_version_key": "version"}
            for index in range(2)]
    for row in rows:
        row.update(cancel.operator_intent(row, "operator", "Guest requested cancellation"))
    db = SimpleNamespace(bookings=Collection(rows), exely_cancel_requests=Collection(), outbox_events=Collection(),
        exely_reservations=Collection([{"tenant_id": "tenant", "property_id": "property",
            "external_id": "original-provider-booking", "pms_booking_ids": [row["id"] for row in rows],
            "provider_version_key": "version", "durable_version_key": "version", "pms_status": "imported"}]))
    provider = SimpleNamespace(cancel_reservation=AsyncMock(return_value=ProviderResult(success=True)))
    resolver = AsyncMock(return_value=(provider, {"auto_sync_reservations": True}))
    monkeypatch.setattr(factory, "get_exely_provider", resolver)
    return db, provider, resolver


async def queued(db):
    await cancel.enqueue(db, "tenant", "room-0")
    event = deepcopy(db.outbox_events.rows[0])
    event["attempt_count"] = 1
    return event


@pytest.mark.asyncio
async def test_whole_booking_deduplicates_room_intents_and_confirmed_replay(scenario):
    db, provider, resolver = scenario
    event = await queued(db)
    await cancel.enqueue(db, "tenant", "room-1")
    assert len(db.outbox_events.rows) == len(db.exely_cancel_requests.rows) == 1
    assert (await cancel.deliver(db, event))[0]
    assert (await cancel.deliver(db, event))[0]
    provider.cancel_reservation.assert_awaited_once()
    assert provider.cancel_reservation.call_args.args[0] == "original-provider-booking"
    resolver.assert_awaited_once_with("tenant", property_id="property", actor="exely_reservation_cancel")
    result = await cancel.status(db, "tenant", "room-1")
    assert result["state"] == "CONFIRMED" and result["confirmed_at"] and not result["can_send"]


@pytest.mark.asyncio
async def test_partial_room_cancel_blocks_then_last_room_cancel_sends_whole_booking(scenario):
    db, provider, _ = scenario
    db.bookings.rows[1]["status"] = "confirmed"
    result = await cancel.queue_after_local_cancel(db, "tenant", "room-0")
    assert result["code"] == "EXELY_WHOLE_BOOKING_REQUIRED"
    assert not db.outbox_events.rows
    db.bookings.rows[1]["status"] = "cancelled"
    assert (await cancel.deliver(db, await queued(db)))[0]
    provider.cancel_reservation.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["version", "missing_room", "tenant", "property", "reactivated"])
async def test_stale_or_incomplete_source_never_cancels_provider(scenario, change):
    db, provider, _ = scenario
    event = await queued(db)
    if change == "version":
        db.exely_reservations.rows[0]["provider_version_key"] = "new-version"
    elif change == "missing_room":
        db.bookings.rows.pop()
    elif change == "tenant":
        event["tenant_id"] = "other-tenant"
    elif change == "property":
        event["property_id"] = "other-property"
    else:
        db.bookings.rows[1]["status"] = "confirmed"
    assert not (await cancel.deliver(db, event))[0]
    provider.cancel_reservation.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_workers_only_one_provider_request(scenario):
    db, provider, _ = scenario
    event = await queued(db)
    entered, release = asyncio.Event(), asyncio.Event()

    async def pending(*_):
        entered.set()
        await release.wait()
        return ProviderResult(success=True)

    provider.cancel_reservation.side_effect = pending
    first = asyncio.create_task(cancel.deliver(db, event))
    await entered.wait()
    assert not (await cancel.deliver(db, event))[0]
    release.set()
    assert (await first)[0]
    provider.cancel_reservation.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("result,state", [
    (RuntimeError("timeout"), "UNKNOWN"),
    (ProviderResult(success=False, metadata={"classification": "AMBIGUOUS", "provider_write_count": 1}), "UNKNOWN"),
    (ProviderResult(success=False, metadata={"classification": "REJECTED", "provider_write_count": 1}), "REJECTED"),
])
async def test_uncertain_or_rejected_write_is_not_replayed(scenario, result, state):
    db, provider, _ = scenario
    event = await queued(db)
    if isinstance(result, Exception):
        provider.cancel_reservation.side_effect = result
    else:
        provider.cancel_reservation.return_value = result
    assert not (await cancel.deliver(db, event))[0]
    assert not (await cancel.deliver(db, event))[0]
    provider.cancel_reservation.assert_awaited_once()
    assert db.exely_cancel_requests.rows[0]["state"] == state


@pytest.mark.asyncio
async def test_connection_resolution_failure_can_retry_without_writing(scenario):
    db, provider, resolver = scenario
    event = await queued(db)
    resolver.side_effect = RuntimeError("temporarily unavailable")
    assert "retryable" in (await cancel.deliver(db, event))[1]
    provider.cancel_reservation.assert_not_awaited()
    resolver.side_effect = None
    assert (await cancel.deliver(db, event))[0]


@pytest.mark.asyncio
async def test_rate_limit_can_retry_but_exhaustion_is_visible(scenario):
    db, provider, _ = scenario
    event = await queued(db)
    provider.cancel_reservation.return_value = ProviderResult(success=False,
        metadata={"classification": "RATE_LIMITED", "provider_write_count": 0})
    assert "retryable" in (await cancel.deliver(db, event))[1]
    event["attempt_count"] = 5
    assert "permanent" in (await cancel.deliver(db, event))[1]
    assert db.exely_cancel_requests.rows[0]["state"] == "REJECTED"


@pytest.mark.asyncio
async def test_recovery_only_replays_explicit_operator_intents(scenario, monkeypatch):
    db, _, _ = scenario
    del db.bookings.rows[1]["exely_cancel_intent"]
    real_enqueue = cancel.enqueue_outbox_event
    monkeypatch.setattr(cancel, "enqueue_outbox_event", AsyncMock(side_effect=RuntimeError("database unavailable")))
    assert (await cancel.queue_after_local_cancel(db, "tenant", "room-0"))["state"] == "PENDING"
    assert db.bookings.rows[0]["exely_cancel_intent"]["state"] == "PENDING"
    monkeypatch.setattr(cancel, "enqueue_outbox_event", real_enqueue)
    await cancel.recover_pending(db, "tenant", "property")
    assert len(db.outbox_events.rows) == 1
    assert "exely_cancel_intent" not in db.bookings.rows[1]
    assert db.bookings.rows[0]["exely_cancel_intent"]["state"] == "QUEUED"


@pytest.mark.asyncio
async def test_inbound_cancel_and_unmarked_history_never_echo(scenario):
    db, provider, _ = scenario
    del db.bookings.rows[0]["exely_cancel_intent"]
    with pytest.raises(ValueError, match="OPERATOR_INTENT_REQUIRED"):
        await cancel.enqueue(db, "tenant", "room-0")
    db.exely_reservations.rows[0]["pms_status"] = "cancellation_done"
    assert (await cancel.enqueue(db, "tenant", "room-1"))["state"] == "REMOTE_CANCELLED"
    assert not db.outbox_events.rows
    provider.cancel_reservation.assert_not_awaited()


@pytest.mark.asyncio
async def test_dedicated_event_dispatch_does_not_fan_out(monkeypatch):
    dispatch = AsyncMock(return_value=(True, "confirmed"))
    monkeypatch.setattr(cancel, "dispatch", dispatch)
    event = {"event_type": EXELY_RESERVATION_CANCEL, "tenant_id": "tenant"}
    assert await dispatch_outbox_event(event) == (True, "confirmed")
    dispatch.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_local_cancellation_persists_intent_before_enqueue(scenario, monkeypatch):
    from core import atomic_booking
    from modules.pms_core import reservation_state_machine as rsm

    db, _, _ = scenario
    db.bookings.rows[0]["status"] = "confirmed"
    db.bookings.rows[0].pop("exely_cancel_intent")
    db.notifications = Collection()
    db.pms_audit_trail = Collection()
    monkeypatch.setattr(rsm, "db", db)
    monkeypatch.setattr(atomic_booking, "release_booking_nights", AsyncMock())
    result = await rsm.ReservationStateMachine().handle_cancellation("tenant", deepcopy(db.bookings.rows[0]), "operator", " ")
    assert result["success"] and result["exely_cancellation"]["state"] == "PENDING"
    assert db.bookings.rows[0]["exely_cancel_intent"]["reason"] == "Cancelled by hotel operator"
    assert db.bookings.rows[0]["status"] == "cancelled"
    assert len([event for event in db.outbox_events.rows if event["event_type"] == EXELY_RESERVATION_CANCEL]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("noshow", [False, True])
async def test_legacy_operator_route_queues_cancellation_but_not_no_show(scenario, monkeypatch, noshow):
    from core import atomic_booking
    from domains.channel_manager import availability_auto_sync
    from routers.hotel_services_pkg import reservations_misc as route

    db, _, _ = scenario
    db.bookings.rows[0]["status"] = "confirmed"
    db.bookings.rows[0].pop("exely_cancel_intent")
    db.reservation_history = Collection()
    monkeypatch.setattr(route, "db", db)
    monkeypatch.setattr(route, "_ensure_hotel_context", lambda *_: None)
    monkeypatch.setattr(route._role_permissions, "enforce_user_permission", lambda *_: None)
    monkeypatch.setattr(atomic_booking, "release_booking_nights", AsyncMock(return_value=0))
    monkeypatch.setattr(availability_auto_sync, "sync_availability_after_booking", AsyncMock())
    user = SimpleNamespace(id="operator", tenant_id="tenant", name="Operator")
    result = await route.cancel_reservation("room-0", route.CancelReservationRequest(reason="Guest request", apply_noshow=noshow), user, None)
    await asyncio.sleep(0)
    assert result["status"] == ("no_show" if noshow else "cancelled")
    assert bool(db.outbox_events.rows) is not noshow
    assert ("exely_cancel_intent" in db.bookings.rows[0]) is not noshow


@pytest.mark.asyncio
async def test_historical_send_endpoint_is_explicit_idempotent_and_tenant_scoped(scenario, monkeypatch):
    from fastapi import HTTPException

    from routers import pms_hardening as route

    db, provider, _ = scenario
    for row in db.bookings.rows:
        row.pop("exely_cancel_intent")
    monkeypatch.setattr(route, "db", db)
    permission_calls = []
    monkeypatch.setattr(route.perm_svc, "enforce_user_permission", lambda user, permission: permission_calls.append((user.id, permission)))
    user = SimpleNamespace(id="operator", tenant_id="tenant")
    other = SimpleNamespace(id="other", tenant_id="other-tenant")
    req = route.ExelyCancellationRequest(reason="Guest requested cancellation")
    assert (await route.api_exely_cancellation_status("room-0", user))["can_send"]
    assert not db.outbox_events.rows
    with pytest.raises(HTTPException) as denied:
        await route.api_send_exely_cancellation("room-0", req, other)
    assert denied.value.status_code == 409
    assert not db.outbox_events.rows
    assert (await route.api_send_exely_cancellation("room-0", req, user))["state"] == "PENDING"
    assert (await route.api_send_exely_cancellation("room-0", req, user))["state"] == "PENDING"
    assert len(db.exely_cancel_requests.rows) == len(db.outbox_events.rows) == 1
    assert db.bookings.rows[0]["exely_cancel_intent"]["actor"] == "operator"
    assert all(permission == "cancel_booking" for _, permission in permission_calls)
    provider.cancel_reservation.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_endpoint_enforces_permission_before_any_mutation(scenario, monkeypatch):
    from fastapi import HTTPException

    from routers import pms_hardening as route

    db, _, _ = scenario
    monkeypatch.setattr(route, "db", db)
    def deny(*_):
        raise HTTPException(status_code=403, detail="Forbidden")
    monkeypatch.setattr(route.perm_svc, "enforce_user_permission", deny)
    before = deepcopy(db.bookings.rows)
    with pytest.raises(HTTPException) as denied:
        await route.api_send_exely_cancellation("room-0", route.ExelyCancellationRequest(reason="Guest request"),
                                                SimpleNamespace(id="operator", tenant_id="tenant"))
    assert denied.value.status_code == 403
    assert db.bookings.rows == before
    assert not db.exely_cancel_requests.rows and not db.outbox_events.rows


@pytest.mark.asyncio
async def test_factory_selects_requested_property_and_rejects_credential_mismatch(monkeypatch):
    connections = Collection([
        {"tenant_id": "tenant", "hotel_code": "other-property", "is_active": True},
        {"tenant_id": "other-tenant", "hotel_code": "property", "is_active": True},
        {"tenant_id": "tenant", "hotel_code": "property", "is_active": True},
    ])
    monkeypatch.setattr(factory, "db", SimpleNamespace(exely_connections=connections))
    monkeypatch.setattr(factory, "provider_io_block_reason", lambda: None)
    resolver = AsyncMock(return_value={"hotel_code": "property", "username": "synthetic-user",
        "password": "synthetic-password", "endpoint_url": "https://pmsconnect.prod.hopenapi.com/api/PMSConnect.svc"})
    monkeypatch.setattr(factory, "resolve_exely_credentials", resolver)
    _, connection = await factory.get_exely_provider("tenant", property_id="property", actor="exely_reservation_cancel")
    assert connection["tenant_id"] == "tenant" and connection["hotel_code"] == "property"
    resolver.assert_awaited_once_with("tenant", connection, actor="exely_reservation_cancel")
    resolver.return_value["hotel_code"] = "wrong-property"
    with pytest.raises(RuntimeError, match="EXELY_PROPERTY_MISMATCH"):
        await factory.get_exely_provider("tenant", property_id="property")
