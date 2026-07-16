import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from core.security import get_current_user
from server import app

client = TestClient(app, raise_server_exceptions=True)

class FakeCursor:
    def __init__(self, items):
        self.items = items
    def __aiter__(self):
        self.idx = 0
        return self
    async def __anext__(self):
        import asyncio
        await asyncio.sleep(0)
        if self.idx < len(self.items):
            val = self.items[self.idx]
            self.idx += 1
            return val
        raise StopAsyncIteration
    async def to_list(self, length=None):
        return self.items
    def sort(self, *args, **kwargs):
        return self
    def limit(self, *args, **kwargs):
        return self

@pytest.fixture(autouse=True)
def mock_resource_locks():
    with patch("routers.mice.with_resource_locks") as m_lock:
        async def fake_lock(client, db, tenant_id, locks_collection, resources, callback, **kwargs):
            return await callback(session=None)
        m_lock.side_effect = fake_lock
        yield m_lock

@pytest.fixture
def mock_db():
    with patch("routers.mice.get_system_db") as m_db, \
         patch("core.tenant_db.get_system_db") as m_db_tenant, \
         patch("core.database.db") as m_db_default, \
         patch("routers.sales_catering.db", create=True) as m_sales_db, \
         patch("core.entitlements.quota.db", create=True) as m_quota_db:

        db = MagicMock()
        db.mice_spaces.find_one = AsyncMock(return_value=None)
        db.mice_spaces.insert_one = AsyncMock()
        db.mice_spaces.delete_one = AsyncMock()
        db.mice_spaces.find = MagicMock(return_value=FakeCursor([]))

        db.mice_events.find_one = AsyncMock(return_value=None)
        db.mice_events.insert_one = AsyncMock()
        db.mice_events.update_one = AsyncMock()
        db.mice_events.delete_one = AsyncMock()
        db.mice_events.find = MagicMock(return_value=FakeCursor([]))

        db.audit_logs.insert_one = AsyncMock()
        db.tenant_features.find_one = AsyncMock(return_value=None)
        db.sales_opportunities.find = MagicMock(return_value=FakeCursor([]))
        db.entitlement_quota_usage.update_one = AsyncMock()

        m_db.return_value = db
        m_db_tenant.return_value = db

        # for module level globals
        for m in (m_db_default, m_sales_db, m_quota_db):
            m.mice_spaces = db.mice_spaces
            m.mice_events = db.mice_events
            m.audit_logs = db.audit_logs
            m.tenant_features = db.tenant_features
            m.sales_opportunities = db.sales_opportunities
            m.entitlement_quota_usage = db.entitlement_quota_usage

        yield db

@pytest.fixture
def mock_get_tenant_limit():
    with patch("routers.mice.get_tenant_limit", new_callable=AsyncMock) as m_limit:
        m_limit.return_value = 5  # arbitrary
        yield m_limit

@pytest.fixture
def mock_quota():
    with patch("routers.mice.reserve_quota", new_callable=AsyncMock) as m_res, \
         patch("routers.mice.release_quota", new_callable=AsyncMock) as m_rel, \
         patch("core.entitlements.quota.release_quota", new=m_rel), \
         patch("core.entitlements.quota.reserve_quota", new=m_res):
        yield m_res, m_rel

@pytest.fixture
def override_auth_basic():
    from models.schemas.identity import User
    async def override():
        return User(
            id="usr1",
            username="testuser",
            tenant_id="t1",
            roles=["admin"],
            email="test@test.com",
            name="Test User",
            role="admin",
            subscription_tier="basic",
            is_active=True,
            created_at=datetime.now(UTC)
        )
    app.dependency_overrides[get_current_user] = override
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def override_auth_pro():
    from models.schemas.identity import User
    async def override():
        return User(
            id="usr_pro",
            username="testpro",
            tenant_id="t1-pro",
            roles=["admin"],
            email="pro@test.com",
            name="Pro User",
            role="admin",
            subscription_tier="pro",
            is_active=True,
            created_at=datetime.now(UTC)
        )
    app.dependency_overrides[get_current_user] = override
    yield
    app.dependency_overrides.pop(get_current_user, None)

@pytest.fixture
def mock_feature():
    with patch("core.entitlements.enforcement.tenant_has_feature", new_callable=AsyncMock) as m:
        async def fake_has_feature(tenant_id, module, feature):
            return True if "pro" in tenant_id else False
        m.side_effect = fake_has_feature
        yield m

def test_space_idempotency(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    from pymongo.errors import DuplicateKeyError
    m_res, m_rel = mock_quota

    req_id = str(uuid.uuid4())
    mock_db.mice_spaces.insert_one.side_effect = DuplicateKeyError("dup")
    async def fake_find_one(query, *args, **kwargs):
        if "client_request_id" in query:
            return {"id": "space123", "client_request_id": req_id}
        return None
    mock_db.mice_spaces.find_one.side_effect = fake_find_one

    res = client.post("/api/mice/spaces", json={"name": "Idem", "area_m2": 100, "client_request_id": req_id})
    assert res.status_code == 200
    assert res.json()["id"] == "space123"

    m_rel.assert_not_called()

def test_event_insert_failure_rollback(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota

    with patch("routers.mice.with_resource_locks") as m_lock:
        async def fake_lock(client, db, tenant_id, locks_collection, resources, callback, **kwargs):
            raise Exception("DB lock error")
        m_lock.side_effect = fake_lock

        try:
            client.post("/api/mice/events", json={"name": "Fail", "client_name": "Test", "start_date": "2026-08-01", "end_date": "2026-08-02", "status": "tentative"})
        except Exception:
            pass

        m_rel.assert_called_once()


def test_event_status_counted_to_uncounted_release(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota

    async def fake_find_one(query, *args, **kwargs):
        return {"id": "ev123", "status": "confirmed"}
    mock_db.mice_events.find_one.side_effect = fake_find_one
    mock_db.mice_events.update_one = AsyncMock()

    class FakeResult:
        modified_count = 1
    mock_db.mice_events.update_one.return_value = FakeResult()

    res = client.post("/api/mice/events/ev123/status", json={"status": "completed"})
    assert res.status_code == 200
    m_rel.assert_called_once()
    m_res.assert_not_called()

def test_event_status_counted_to_uncounted_cancelled_release(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota

    async def fake_find_one(query, *args, **kwargs):
        return {"id": "ev123", "status": "tentative"}
    mock_db.mice_events.find_one.side_effect = fake_find_one
    mock_db.mice_events.update_one = AsyncMock()

    class FakeResult:
        modified_count = 1
    mock_db.mice_events.update_one.return_value = FakeResult()

    res = client.post("/api/mice/events/ev123/status", json={"status": "cancelled", "reason": "İptal nedeni en az 10 karakter"})
    assert res.status_code == 200
    m_rel.assert_called_once()
    m_res.assert_not_called()

def test_event_status_counted_to_uncounted_lead_release(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota

    async def fake_find_one(query, *args, **kwargs):
        return {"id": "ev123", "status": "tentative"}
    mock_db.mice_events.find_one.side_effect = fake_find_one
    mock_db.mice_events.update_one = AsyncMock()

    class FakeResult:
        modified_count = 1
    mock_db.mice_events.update_one.return_value = FakeResult()

    res = client.post("/api/mice/events/ev123/status", json={"status": "lead"})
    assert res.status_code == 200
    m_rel.assert_called_once()
    m_res.assert_not_called()

def test_basic_spaces_limit(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota

    mock_get_tenant_limit.return_value = 2
    mock_db.mice_spaces.insert_one = AsyncMock()

    res = client.post("/api/mice/spaces", json={"name": "Space 1", "capacity": 100})
    assert res.status_code == 200
    m_res.assert_called_with('t1', 'mice', 'spaces_limit', res.json()["id"], 2)

    from core.entitlements.quota import QuotaExceededException
    m_res.side_effect = QuotaExceededException()
    try:
        client.post("/api/mice/spaces", json={"name": "Space 3", "capacity": 100})
    except Exception as e:
        assert getattr(e, "status_code", 403) == 403
    m_res.side_effect = None

def test_pro_spaces_limit(override_auth_pro, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota

    mock_get_tenant_limit.return_value = 10
    res = client.post("/api/mice/spaces", json={"name": "Space 10", "capacity": 100})
    assert res.status_code == 200
    m_res.assert_called_with('t1-pro', 'mice', 'spaces_limit', res.json()["id"], 10)

def test_basic_events_limit(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota

    mock_get_tenant_limit.return_value = 5
    res = client.post("/api/mice/events", json={"name": "Ev 5", "client_name": "Test", "start_date": "2026-08-01", "end_date": "2026-08-02", "status": "tentative"})
    assert res.status_code == 200
    m_res.assert_called_with('t1', 'mice', 'concurrent_events', res.json()["id"], 5)

def test_pro_events_limit(override_auth_pro, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota

    mock_get_tenant_limit.return_value = 50
    res = client.post("/api/mice/events", json={"name": "Ev 50", "client_name": "Test", "start_date": "2026-08-01", "end_date": "2026-08-02", "status": "tentative"})
    assert res.status_code == 200
    m_res.assert_called_with('t1-pro', 'mice', 'concurrent_events', res.json()["id"], 50)

def test_proposals_feature_basic(override_auth_basic, mock_db, mock_feature):
    mock_feature.side_effect = None
    mock_feature.return_value = False
    try:
        res = client.get("/api/mice/sales/opportunities")
        assert res.status_code == 403
    except Exception as e:
        assert getattr(e, "status_code", 403) == 403

def test_proposals_feature_pro(override_auth_pro, mock_db, mock_feature):
    mock_feature.side_effect = None
    mock_feature.return_value = True
    res = client.get("/api/mice/sales/opportunities")
    assert res.status_code == 200

def test_banquet_feature_basic(override_auth_basic, mock_db, mock_feature):
    mock_feature.side_effect = None
    mock_feature.return_value = False
    try:
        res = client.get("/api/mice/events/123/beo")
        assert res.status_code == 403
    except Exception as e:
        assert getattr(e, "status_code", 403) == 403

def test_banquet_feature_pro(override_auth_pro, mock_db, mock_feature):
    mock_feature.side_effect = None
    mock_feature.return_value = True
    async def fake_find_one(*args, **kwargs):
        return {"id": "123", "status": "confirmed"}
    mock_db.mice_events.find_one.side_effect = fake_find_one
    res = client.get("/api/mice/events/123/beo")
    assert res.status_code == 200

def test_space_delete_releases_quota(override_auth_basic, mock_db, mock_quota):
    m_res, m_rel = mock_quota
    class FakeResult:
        deleted_count = 1
    mock_db.mice_spaces.delete_one = AsyncMock(return_value=FakeResult())
    res = client.delete("/api/mice/spaces/sp123")
    assert res.status_code == 200
    m_rel.assert_called_with('t1', 'mice', 'spaces_limit', 'sp123')


# ── delete_event quota release tests ──────────────────────────────────────────


def test_delete_event_active_status_releases_quota(override_auth_basic, mock_db, mock_quota):
    """Aktif (tentative/definite/confirmed) event silinince concurrent_events kotası serbest bırakılmalı."""
    m_res, m_rel = mock_quota

    class FakeDeleteResult:
        deleted_count = 1

    for active_status in ("tentative", "definite", "confirmed"):
        m_rel.reset_mock()
        mock_db.mice_events.find_one = AsyncMock(
            return_value={"id": "ev1", "tenant_id": "t1", "name": "Test Event", "status": active_status}
        )
        mock_db.mice_events.delete_one = AsyncMock(return_value=FakeDeleteResult())

        res = client.delete("/api/mice/events/ev1")

        assert res.status_code == 200, f"status={active_status} için 200 beklendi"
        m_rel.assert_called_once_with("t1", "mice", "concurrent_events", "ev1")


def test_delete_event_inactive_status_no_release(override_auth_basic, mock_db, mock_quota):
    """Cancelled/completed event silinince release_quota ÇAĞRILMAMALI (zaten status geçişinde bırakıldı)."""
    m_res, m_rel = mock_quota

    class FakeDeleteResult:
        deleted_count = 1

    for inactive_status in ("cancelled", "completed"):
        m_rel.reset_mock()
        mock_db.mice_events.find_one = AsyncMock(
            return_value={"id": "ev2", "tenant_id": "t1", "name": "Old Event", "status": inactive_status}
        )
        mock_db.mice_events.delete_one = AsyncMock(return_value=FakeDeleteResult())

        res = client.delete("/api/mice/events/ev2")

        assert res.status_code == 200, f"status={inactive_status} için 200 beklendi"
        m_rel.assert_not_called()


def test_delete_event_not_found_no_release(override_auth_basic, mock_db, mock_quota):
    """Event bulunamazsa 404 dönmeli ve release_quota çağrılmamalı."""
    m_res, m_rel = mock_quota

    class FakeDeleteResult:
        deleted_count = 0

    mock_db.mice_events.find_one = AsyncMock(return_value=None)
    mock_db.mice_events.delete_one = AsyncMock(return_value=FakeDeleteResult())

    res = client.delete("/api/mice/events/nonexistent")

    assert res.status_code == 404
    m_rel.assert_not_called()


def test_delete_event_before_none_no_release(override_auth_basic, mock_db, mock_quota):
    """before=None (event DB'de yok ama delete_count=0) durumunda release olmamalı."""
    m_res, m_rel = mock_quota

    class FakeDeleteResult:
        deleted_count = 0

    # find_one None döner (event bulunamadı), delete de 0 döner
    mock_db.mice_events.find_one = AsyncMock(return_value=None)
    mock_db.mice_events.delete_one = AsyncMock(return_value=FakeDeleteResult())

    res = client.delete("/api/mice/events/ghost_ev")

    assert res.status_code == 404
    m_rel.assert_not_called()


def test_delete_event_tenant_isolation(override_auth_basic, mock_db, mock_quota):
    """delete_event DB sorgusu tenant_id ile scope'lanmış olmalı."""
    m_res, m_rel = mock_quota

    class FakeDeleteResult:
        deleted_count = 1

    mock_db.mice_events.find_one = AsyncMock(
        return_value={"id": "ev_other", "tenant_id": "t1", "name": "Event", "status": "confirmed"}
    )
    mock_db.mice_events.delete_one = AsyncMock(return_value=FakeDeleteResult())

    client.delete("/api/mice/events/ev_other")

    # Her iki DB çağrısı tenant_id="t1" ile yapılmış olmalı
    find_call_kwargs = mock_db.mice_events.find_one.call_args[0][0]
    assert find_call_kwargs["tenant_id"] == "t1"
    del_call_kwargs = mock_db.mice_events.delete_one.call_args[0][0]
    assert del_call_kwargs["tenant_id"] == "t1"


# ── Additional delete_event edge-case tests ────────────────────────────────────


def test_delete_event_db_failure_does_not_release(override_auth_basic, mock_db, mock_quota):
    """delete_one DB exception → 500 döner; release_quota ÇAĞRILMAMALI.

    Quota must only be released if the delete actually succeeded.  A DB
    exception before deleted_count is inspected must not leak a phantom
    release that would permanently under-count the tenant's slot usage.

    Uses a test-local client with raise_server_exceptions=False so the
    unhandled exception surfaces as a 500 HTTP response rather than a
    pytest exception propagation.
    """
    from fastapi.testclient import TestClient as _TC

    from server import app as _app

    m_res, m_rel = mock_quota

    mock_db.mice_events.find_one = AsyncMock(
        return_value={"id": "ev_db_err", "tenant_id": "t1", "status": "confirmed"}
    )
    mock_db.mice_events.delete_one = AsyncMock(side_effect=Exception("Mongo write error"))

    _client = _TC(_app, raise_server_exceptions=False)
    res = _client.delete("/api/mice/events/ev_db_err")

    assert res.status_code == 500
    m_rel.assert_not_called()



def test_delete_cancelled_event_does_not_release(override_auth_basic, mock_db, mock_quota):
    """Cancelled event silinince release_quota ÇAĞRILMAMALI (status geçişinde zaten yapıldı)."""
    m_res, m_rel = mock_quota

    class FakeDeleteResult:
        deleted_count = 1

    mock_db.mice_events.find_one = AsyncMock(
        return_value={"id": "ev_cancelled", "tenant_id": "t1", "status": "cancelled"}
    )
    mock_db.mice_events.delete_one = AsyncMock(return_value=FakeDeleteResult())

    res = client.delete("/api/mice/events/ev_cancelled")

    assert res.status_code == 200
    m_rel.assert_not_called()


def test_cancel_then_delete_does_not_double_release(override_auth_basic, mock_db, mock_quota):
    """Status 'cancelled' → delete akışı: toplam 0 release (delete aşamasında).

    Bu test, status geçişi sırasında zaten release yapılmış bir event'in
    sonradan silinmesinin ikinci bir release tetiklemediğini kanıtlar.
    (Status geçişindeki release bu testte scope dışı; sadece delete_event kontrol edilir.)
    """
    m_res, m_rel = mock_quota

    class FakeDeleteResult:
        deleted_count = 1

    mock_db.mice_events.find_one = AsyncMock(
        return_value={"id": "ev_was_cancelled", "tenant_id": "t1", "status": "cancelled"}
    )
    mock_db.mice_events.delete_one = AsyncMock(return_value=FakeDeleteResult())

    res = client.delete("/api/mice/events/ev_was_cancelled")

    assert res.status_code == 200
    # delete_event must NOT release — cancelled events were already released
    # when the status transition happened.
    m_rel.assert_not_called()


def test_delete_event_uses_event_id_as_resource_id(override_auth_basic, mock_db, mock_quota):
    """release_quota resource_id parametresi create sırasındaki event_id ile aynı olmalı.

    Quota ledger'i event_id key'i altında tutar; farklı bir resource_id ile
    release yapılırsa slot sonsuza dek tutulur.
    """
    m_res, m_rel = mock_quota

    class FakeDeleteResult:
        deleted_count = 1

    _EVENT_ID = "ev_resource_check"
    mock_db.mice_events.find_one = AsyncMock(
        return_value={"id": _EVENT_ID, "tenant_id": "t1", "status": "definite"}
    )
    mock_db.mice_events.delete_one = AsyncMock(return_value=FakeDeleteResult())

    res = client.delete(f"/api/mice/events/{_EVENT_ID}")

    assert res.status_code == 200
    m_rel.assert_called_once_with("t1", "mice", "concurrent_events", _EVENT_ID)
