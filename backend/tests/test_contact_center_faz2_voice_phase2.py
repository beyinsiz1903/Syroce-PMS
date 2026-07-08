from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import domains.contact_center.voice_router as voice_router
from domains.contact_center.voice_provider import TwilioVoiceProvider
from models.schemas import User

_TENANT = "tenant-A"
_USER_ID = "user-abc"
_CUSTOMER_PHONE = "+905551112233"


class _UpdRes:
    def __init__(self, matched=0):
        self.matched_count = matched


class _FakeColl:
    def __init__(self):
        self.docs: list[dict] = []

    @staticmethod
    def _match(doc, flt):
        if not flt:
            return True
        for k, v in flt.items():
            if k == "agent_id" and isinstance(v, dict) and "$nin" in v:
                if doc.get("agent_id") in v["$nin"]:
                    return False
                continue
            if k.startswith("$"):
                continue
            if doc.get(k) != v:
                return False
        return True

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if self._match(d, flt):
                return dict(d)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id"))

    async def update_one(self, flt, update):
        for d in self.docs:
            if self._match(d, flt):
                if "$set" in update:
                    d.update(update["$set"])
                if "$addToSet" in update:
                    for k, v in update["$addToSet"].items():
                        if k not in d:
                            d[k] = []
                        if v not in d[k]:
                            d[k].append(v)
                return _UpdRes(matched=1)
        return _UpdRes(matched=0)

    async def delete_one(self, flt):
        for i, d in enumerate(self.docs):
            if self._match(d, flt):
                self.docs.pop(i)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)

    def find(self, flt=None):
        matched = []
        for d in self.docs:
            if self._match(d, flt):
                matched.append(dict(d))

        class _Cursor:
            def __init__(self, items):
                self.items = items
            def sort(self, key, direction=1):
                # Simple started_at sort
                if key == "started_at":
                    self.items.sort(key=lambda x: x.get("started_at", datetime.min))
                elif key == "extension":
                    self.items.sort(key=lambda x: x.get("extension", ""))
                return self
            async def to_list(self, length=100):
                return self.items[:length]
        return _Cursor(matched)

    async def count_documents(self, flt):
        count = 0
        for d in self.docs:
            if self._match(d, flt):
                count += 1
        return count

    def aggregate(self, pipeline):
        matched = []
        for d in self.docs:
            if d.get("ended_at") is None:
                matched.append({
                    "agent_id": d.get("agent_id"),
                    "state": d.get("state"),
                    "started_at": d.get("started_at"),
                    "agent_name": "Test Agent",
                    "agent_username": "testagent"
                })
        class _Cursor:
            async def to_list(self, length=100):
                return matched[:length]
        return _Cursor()


class _FakeDB:
    def __init__(self):
        self.contact_center_queues = _FakeColl()
        self.contact_center_agent_states = _FakeColl()
        self.contact_center_calls = _FakeColl()
        self.contact_center_voice_numbers = _FakeColl()
        self.guests = _FakeColl()
        self.bookings = _FakeColl()
        self.tenant_settings = _FakeColl()

    def __getitem__(self, name):
        return getattr(self, name)


def _make_request(path: str, form: dict, *, query: str = "") -> Request:
    body = urlencode(form).encode()
    headers = [(b"content-type", b"application/x-www-form-urlencoded")]
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
    monkeypatch.setattr(
        TwilioVoiceProvider, "validate_signature", lambda self, **kw: True
    )


# ── Tests ──

def test_queue_crud_and_validation(fake_db):
    user = User(id=_USER_ID, tenant_id=_TENANT, role="admin", name="Test Admin", email="admin@test.com", username="admin")
    
    # 1. Create Queue
    payload = voice_router.QueueConfigCreate(name="Reservations", extension="1")
    created = asyncio.run(voice_router.create_queue(payload, user))
    assert created["name"] == "Reservations"
    assert created["extension"] == "1"
    assert created["tenant_id"] == _TENANT
    assert created["id"] is not None

    # 2. Duplicate Extension Rejection
    with pytest.raises(HTTPException) as exc:
        asyncio.run(voice_router.create_queue(payload, user))
    assert exc.value.status_code == 409

    # 3. List Queues
    queues = asyncio.run(voice_router.list_queues(user))
    assert len(queues["queues"]) == 1
    assert queues["queues"][0]["name"] == "Reservations"

    # 4. Get Queue
    queue_id = created["id"]
    get_res = asyncio.run(voice_router.get_queue(queue_id, user))
    assert get_res["name"] == "Reservations"

    # 5. Update Queue
    update_payload = voice_router.QueueConfigUpdate(name="New Reservations", extension="2")
    updated = asyncio.run(voice_router.update_queue(queue_id, update_payload, user))
    assert updated["name"] == "New Reservations"
    assert updated["extension"] == "2"

    # 6. Delete Queue
    asyncio.run(voice_router.delete_queue(queue_id, user))
    assert len(fake_db.contact_center_queues.docs) == 0


def test_agent_states_transitions_and_list(fake_db):
    user = User(id=_USER_ID, tenant_id=_TENANT, role="call_center_agent", name="Test Agent", email="agent@test.com", username="agent")

    # 1. Update State
    state_payload = voice_router.AgentStateUpdate(state="ready")
    created_state = asyncio.run(voice_router.update_agent_state(state_payload, user))
    assert created_state["state"] == "ready"
    assert created_state["agent_id"] == _USER_ID
    assert created_state["ended_at"] is None

    # 2. Transition State (Closes last state)
    state_payload2 = voice_router.AgentStateUpdate(state="break_short")
    new_state = asyncio.run(voice_router.update_agent_state(state_payload2, user))
    assert new_state["state"] == "break_short"
    
    # Assert old state was ended
    old_state = fake_db.contact_center_agent_states.docs[0]
    assert old_state["ended_at"] is not None

    # 3. Get My State
    my_state = asyncio.run(voice_router.get_my_state(user))
    assert my_state["state"] == "break_short"

    # 4. List Agents States (Supervisor View)
    states_list = asyncio.run(voice_router.list_agents_states(user))
    assert len(states_list["agents"]) == 1
    assert states_list["agents"][0]["agent_id"] == _USER_ID
    assert states_list["agents"][0]["state"] == "break_short"


def test_guest_360_multiple_matches_masking(fake_db):
    user = User(id=_USER_ID, tenant_id=_TENANT, role="call_center_agent", name="Test Agent", email="agent@test.com", username="agent")
    
    from security.field_encryption import get_field_encryption_service
    svc = get_field_encryption_service()
    caller_id_enc = svc.encrypt_value(_CUSTOMER_PHONE)
    caller_id_hash = svc.compute_search_hash(_CUSTOMER_PHONE)
    
    call_doc = {
        "id": "call-123",
        "tenant_id": _TENANT,
        "provider_call_sid": "CA_test",
        "caller_id_enc": caller_id_enc,
        "caller_id_hash": caller_id_hash,
    }
    fake_db.contact_center_calls.docs.append(call_doc)

    # 1. Single match -> returns unmasked guest info
    guest1 = {
        "id": "guest-1",
        "tenant_id": _TENANT,
        "vip": True,
        "first_name": "John",
        "last_name": "Doe",
        "name": "John Doe",
        "email": "john@example.com",
        "phone": _CUSTOMER_PHONE,
        "phone_hash": svc.compute_search_hash(_CUSTOMER_PHONE),
    }
    fake_db.guests.docs.append(guest1)

    res = asyncio.run(voice_router.get_call_guest_360("call-123", user))
    assert res["guest"]["name"] == "John Doe"
    assert res["guest"]["vip"] is True

    # 2. Multiple matches -> returns masked info
    guest2 = {
        "id": "guest-2",
        "tenant_id": _TENANT,
        "vip": False,
        "first_name": "Jane",
        "last_name": "Doe",
        "name": "Jane Doe",
        "email": "jane@example.com",
        "phone": _CUSTOMER_PHONE,
        "phone_hash": svc.compute_search_hash(_CUSTOMER_PHONE),
    }
    fake_db.guests.docs.append(guest2)

    res_masked = asyncio.run(voice_router.get_call_guest_360("call-123", user))
    assert res_masked["guest"]["name"] == "Gizli Misafir (Çoklu Eşleşme)"
    assert res_masked["guest"]["vip"] is False
    assert "john@example.com" not in res_masked["guest"]["email"]


def test_ivr_inbound_routing_and_gather(fake_db, sig_ok):
    fake_db.contact_center_voice_numbers.docs.append({
        "to_number": "+908503334455",
        "tenant_id": _TENANT
    })
    fake_db.contact_center_queues.docs.append({
        "id": "q1",
        "tenant_id": _TENANT,
        "name": "Reservations",
        "extension": "1",
        "working_hours_start": "08:00",
        "working_hours_end": "22:00",
        "working_days": [1, 2, 3, 4, 5, 6, 7]
    })

    req = _make_request("/api/voice/inbound", {
        "To": "+908503334455",
        "From": _CUSTOMER_PHONE,
        "CallSid": "CA_inbound_test"
    })
    resp = asyncio.run(voice_router.voice_inbound(req))
    assert resp.status_code == 200
    assert resp.media_type == "application/xml"
    text = resp.body.decode()
    assert "<Gather" in text

    # Call Gather Webhook -> should redirect to route-queue
    req_gather = _make_request("/api/voice/inbound/gather", {
        "Digits": "1",
        "From": _CUSTOMER_PHONE,
        "CallSid": "CA_inbound_test"
    }, query=f"tenant_id={_TENANT}")
    resp_gather = asyncio.run(voice_router.voice_inbound_gather(req_gather))
    assert resp_gather.status_code == 200
    text_gather = resp_gather.body.decode()
    assert "/api/voice/inbound/route-queue" in text_gather


def test_route_queue_and_agent_selection(fake_db, sig_ok):
    # Setup call record
    fake_db.contact_center_calls.docs.append({
        "provider_call_sid": "CA_inbound_test",
        "tenant_id": _TENANT,
        "started_at": datetime.now(UTC),
        "dialed_agents": []
    })

    fake_db.contact_center_queues.docs.append({
        "id": "q1",
        "tenant_id": _TENANT,
        "name": "Reservations",
        "extension": "1"
    })

    # Setup ready agents
    now = datetime.now(UTC)
    fake_db.contact_center_agent_states.docs.append({
        "tenant_id": _TENANT,
        "agent_id": "agent-1",
        "state": "ready",
        "started_at": now - timedelta(minutes=5),  # Longest idle
        "ended_at": None
    })
    fake_db.contact_center_agent_states.docs.append({
        "tenant_id": _TENANT,
        "agent_id": "agent-2",
        "state": "ready",
        "started_at": now - timedelta(minutes=2),
        "ended_at": None
    })

    # Execute route-queue webhook
    req = _make_request("/api/voice/inbound/route-queue", {
        "CallSid": "CA_inbound_test"
    }, query=f"tenant_id={_TENANT}&queue_id=q1")

    resp = asyncio.run(voice_router.voice_route_queue(req))
    assert resp.status_code == 200
    text = resp.body.decode()
    # Should dial the longest idle agent (agent-1)
    assert "agent-1" in text

    # Next dial should roll over to agent-2 since agent-1 was dialed
    req2 = _make_request("/api/voice/inbound/route-queue", {
        "CallSid": "CA_inbound_test"
    }, query=f"tenant_id={_TENANT}&queue_id=q1")
    resp2 = asyncio.run(voice_router.voice_route_queue(req2))
    text2 = resp2.body.decode()
    assert "agent-2" in text2


def test_agent_status_callback_transitions(fake_db, sig_ok):
    # Setup ready agent
    fake_db.contact_center_agent_states.docs.append({
        "id": "state-1",
        "tenant_id": _TENANT,
        "agent_id": "agent-1",
        "state": "ready",
        "started_at": datetime.now(UTC),
        "ended_at": None
    })

    # 1. Answer call -> transitions to "on_call"
    req = _make_request("/api/voice/agent-status-callback", {
        "CallStatus": "in-progress"
    }, query=f"tenant_id={_TENANT}&agent_id=agent-1")
    resp = asyncio.run(voice_router.voice_agent_status_callback(req))
    assert resp.status_code == 204

    active_state = fake_db.contact_center_agent_states.docs[-1]
    assert active_state["state"] == "on_call"

    # 2. Hangup -> transitions to "wrap_up"
    req_completed = _make_request("/api/voice/agent-status-callback", {
        "CallStatus": "completed"
    }, query=f"tenant_id={_TENANT}&agent_id=agent-1")
    resp_completed = asyncio.run(voice_router.voice_agent_status_callback(req_completed))
    assert resp_completed.status_code == 204

    active_state_wrap = fake_db.contact_center_agent_states.docs[-1]
    assert active_state_wrap["state"] == "wrap_up"
