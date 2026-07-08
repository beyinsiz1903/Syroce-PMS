import pytest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
import domains.contact_center.voice_router as voice_router
import shared_kernel.audit_helper as audit_helper
from models.schemas import User
from models.enums import UserRole

_TENANT = "test_tenant_1"
_USER_ID = "user_1"


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
            val = doc.get(k)
            if isinstance(v, dict):
                # Handle operators
                for op, op_val in v.items():
                    if op == "$in":
                        if val not in op_val:
                            return False
                    elif op == "$nin":
                        if val in op_val:
                            return False
                    elif op == "$ne":
                        if val == op_val:
                            return False
                    elif op == "$gte":
                        if val is None or val < op_val:
                            return False
                    elif op == "$lte":
                        if val is None or val > op_val:
                            return False
                continue
            if isinstance(val, list):
                if v not in val:
                    return False
                continue
            if val != v:
                return False
        return True

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id"))

    async def update_one(self, flt, update, upsert=False):
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
        if upsert:
            new_doc = dict(flt)
            if "$set" in update:
                new_doc.update(update["$set"])
            self.docs.append(new_doc)
            return _UpdRes(matched=1)
        return _UpdRes(matched=0)

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if self._match(d, flt):
                return dict(d)
        return None

    def find(self, flt=None):
        matched = []
        for d in self.docs:
            if self._match(d, flt):
                matched.append(dict(d))

        class _Cursor:
            def __init__(self, items):
                self.items = items
            def sort(self, key, direction=1):
                if key == "abandoned_at":
                    self.items.sort(key=lambda x: x.get("abandoned_at", datetime.min), reverse=True)
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


class _FakeDB:
    def __init__(self):
        self.contact_center_queues = _FakeColl()
        self.contact_center_agent_states = _FakeColl()
        self.contact_center_calls = _FakeColl()
        self.contact_center_dispositions = _FakeColl()
        self.contact_center_callbacks = _FakeColl()
        self.audit_logs = _FakeColl()
        self.users = _FakeColl()

    def __getitem__(self, name):
        return getattr(self, name)


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(voice_router, "db", db)
    monkeypatch.setattr(audit_helper, "db", db)
    return db


def make_user(role, tenant_id=_TENANT, user_id=_USER_ID):
    return User(
        id=user_id,
        tenant_id=tenant_id,
        username="john_doe",
        email="john@example.com",
        name="John Doe",
        role=role,
        is_active=True,
    )


# ── Tests ──

@pytest.mark.asyncio
async def test_supervisor_dashboard_unauthorized(fake_db):
    """Test that agents cannot access supervisor dashboard."""
    agent_user = make_user(UserRole.CALL_CENTER_AGENT.value)
    with pytest.raises(HTTPException) as exc:
        await voice_router.get_supervisor_dashboard(agent_user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_supervisor_dashboard_success(fake_db):
    """Test dashboard metrics for active calls, queued callers, SLA calculations."""
    supervisor_user = make_user(UserRole.SUPERVISOR.value)
    
    # Insert test queue config
    queue_id = "q_reservations"
    fake_db.contact_center_queues.docs.append({
        "id": queue_id,
        "tenant_id": _TENANT,
        "name": "Rezervasyon",
        "extension": "1",
        "sla_threshold_seconds": 20,
        "sla_target_percentage": 80
    })

    now = datetime.now(UTC)
    # Insert test call documents
    fake_db.contact_center_calls.docs.extend([
        # Queued call (ringing, no agent)
        {
            "provider_call_sid": "CA_queued_1",
            "tenant_id": _TENANT,
            "status": "ringing",
            "agent_id": None,
            "queue_id": queue_id,
            "started_at": now - timedelta(seconds=15),
            "direction": "inbound"
        },
        # Answered call (answered within SLA)
        {
            "provider_call_sid": "CA_answered_1",
            "tenant_id": _TENANT,
            "status": "answered",
            "agent_id": "agent_1",
            "queue_id": queue_id,
            "started_at": now - timedelta(seconds=25),
            "answered_at": now - timedelta(seconds=15),
            "direction": "inbound"
        },
        # Completed call today (exceeded SLA)
        {
            "provider_call_sid": "CA_completed_1",
            "tenant_id": _TENANT,
            "status": "completed",
            "agent_id": "agent_1",
            "queue_id": queue_id,
            "started_at": now - timedelta(seconds=120),
            "answered_at": now - timedelta(seconds=60),
            "ended_at": now - timedelta(seconds=10),
            "duration_seconds": 50,
            "direction": "inbound"
        }
    ])

    # Insert active agent state
    fake_db.contact_center_agent_states.docs.append({
        "id": "state_1",
        "tenant_id": _TENANT,
        "agent_id": "agent_1",
        "state": "on_call",
        "started_at": now - timedelta(minutes=5),
        "ended_at": None
    })

    data = await voice_router.get_supervisor_dashboard(supervisor_user)
    assert data["active_calls_count"] == 2
    assert data["queued_callers_count"] == 1
    assert data["longest_wait_seconds"] >= 14
    assert data["agent_states"]["on_call"] == 1
    assert data["agent_states"]["ready"] == 0

    assert len(data["queue_slas"]) == 1
    q_sla = data["queue_slas"][0]
    assert q_sla["queue_id"] == queue_id
    assert q_sla["actual_percentage"] == 50.0
    assert q_sla["status"] == "red"


@pytest.mark.asyncio
async def test_supervisor_agents_metrics(fake_db):
    """Test fetching detailed agent rows with calls answered/missed metrics."""
    supervisor_user = make_user(UserRole.SUPERVISOR.value)

    # Insert agent users
    fake_db.users.docs.extend([
        {
            "id": "agent_1",
            "tenant_id": _TENANT,
            "username": "agent_one",
            "role": "call_center_agent"
        },
        {
            "id": "agent_2",
            "tenant_id": _TENANT,
            "username": "agent_two",
            "role": "call_center_agent"
        }
    ])

    now = datetime.now(UTC)
    fake_db.contact_center_agent_states.docs.append({
        "id": "state_1",
        "tenant_id": _TENANT,
        "agent_id": "agent_1",
        "state": "ready",
        "started_at": now - timedelta(minutes=10),
        "ended_at": None
    })

    # Agent 1 answered 1 completed call; Agent 2 missed 1 call (dialed_agents has agent_2, but agent_id is agent_1)
    fake_db.contact_center_calls.docs.append({
        "provider_call_sid": "CA_1",
        "tenant_id": _TENANT,
        "status": "completed",
        "agent_id": "agent_1",
        "dialed_agents": ["agent_1", "agent_2"],
        "started_at": now - timedelta(minutes=5),
        "answered_at": now - timedelta(minutes=4),
        "duration_seconds": 60,
        "direction": "inbound"
    })

    data = await voice_router.get_supervisor_agents(supervisor_user)
    agents_list = data["agents"]
    
    a1 = next(x for x in agents_list if x["agent_id"] == "agent_1")
    a2 = next(x for x in agents_list if x["agent_id"] == "agent_2")

    assert a1["state"] == "ready"
    assert a1["answered_today"] == 1
    assert a1["missed_today"] == 0
    assert a1["average_handle_time_seconds"] == 60.0

    assert a2["state"] == "offline"
    assert a2["answered_today"] == 0
    assert a2["missed_today"] == 1


@pytest.mark.asyncio
async def test_supervisor_force_state_and_intervention(fake_db):
    """Test supervisor action force_state and listen/whisper/barge intervention log."""
    supervisor_user = make_user(UserRole.SUPERVISOR.value)

    # 1. Test Force State
    payload = voice_router.SupervisorActionPayload(
        action="force_state",
        agent_id="agent_1",
        target_state="offline"
    )
    response = await voice_router.post_supervisor_action(payload, supervisor_user)
    assert response["success"] is True

    # Verify state in DB
    state_doc = await fake_db.contact_center_agent_states.find_one({
        "tenant_id": _TENANT,
        "agent_id": "agent_1",
        "ended_at": None
    })
    assert state_doc["state"] == "offline"

    # 2. Test Intervention (Listen)
    payload_intervene = voice_router.IntervenePayload(
        action="listen",
        call_sid="CA_test_call"
    )
    response_intervene = await voice_router.post_supervisor_intervene(payload_intervene, supervisor_user)
    assert response_intervene["success"] is True
    
    # Verify Audit Log was recorded
    audit_entry = await fake_db.audit_logs.find_one({
        "tenant_id": _TENANT,
        "action": "supervisor_listen"
    })
    assert audit_entry is not None
    assert audit_entry["entity_id"] == "CA_test_call"


@pytest.mark.asyncio
async def test_after_call_work_disposition(fake_db):
    """Test agent disposition submission and return to ready state."""
    agent_user = make_user(UserRole.CALL_CENTER_AGENT.value, user_id="agent_1")

    # Set agent in wrap_up
    fake_db.contact_center_agent_states.docs.append({
        "id": "state_1",
        "tenant_id": _TENANT,
        "agent_id": "agent_1",
        "state": "wrap_up",
        "started_at": datetime.now(UTC),
        "ended_at": None
    })

    payload = voice_router.CallDispositionPayload(
        call_id="CA_dispo_1",
        disposition="reservation_created",
        notes="Rezervasyon tamamlandı.",
        tags=["satış"]
    )
    response = await voice_router.post_agent_disposition(payload, agent_user)
    assert response["success"] is True

    # Verify agent is back to ready
    state_doc = await fake_db.contact_center_agent_states.find_one({
        "tenant_id": _TENANT,
        "agent_id": "agent_1",
        "ended_at": None
    })
    assert state_doc["state"] == "ready"

    # Verify disposition document is saved
    dispo_doc = await fake_db.contact_center_dispositions.find_one({
        "tenant_id": _TENANT,
        "call_id": "CA_dispo_1"
    })
    assert dispo_doc is not None
    assert dispo_doc["disposition"] == "reservation_created"


@pytest.mark.asyncio
async def test_callback_queue_flow(fake_db):
    """Test callback queue retrieve, assign, and resolve lifecycle."""
    agent_user = make_user(UserRole.CALL_CENTER_AGENT.value, user_id="agent_1")

    # Clean callbacks
    fake_db.contact_center_callbacks.docs.append({
        "id": "cb_1",
        "tenant_id": _TENANT,
        "phone": "+905551112233",
        "status": "pending",
        "priority": "high",
        "abandoned_at": datetime.now(UTC)
    })

    # 1. Retrieve callback queue
    response_list = await voice_router.get_callbacks(agent_user)
    assert len(response_list["callbacks"]) == 1

    # 2. Assign callback
    response_assign = await voice_router.post_callback_assign("cb_1", agent_user)
    assert response_assign["success"] is True

    # Verify assigned status
    cb = await fake_db.contact_center_callbacks.find_one({"id": "cb_1"})
    assert cb["status"] == "assigned"
    assert cb["assigned_agent_id"] == "agent_1"

    # 3. Complete callback
    response_complete = await voice_router.post_callback_complete("cb_1", "reached", agent_user)
    assert response_complete["success"] is True

    cb_completed = await fake_db.contact_center_callbacks.find_one({"id": "cb_1"})
    assert cb_completed["status"] == "completed"
    assert cb_completed["result"] == "reached"
