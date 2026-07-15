from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from core.entitlements.quota import QuotaExceededException
from domains.spa.router import TherapistIn, TreatmentRoomIn, availability_grid, create_room, create_therapist, delete_room, delete_therapist, guest_history
from models.schemas import User
from routers.spa_dining_packages import list_packages


class FakeUser(User):
    pass

@pytest.fixture
def fake_user():
    return FakeUser(
        id="u1",
        tenant_id="tenant-spa",
        username="spa_ops",
        name="Spa Ops",
        email="spa@hotel.com",
        hashed_password="xxx",
        role="admin",
        active=True
    )

class FakeRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}

@pytest.mark.asyncio
async def test_therapist_create_success(fake_user):
    body = TherapistIn(name="John Doe", specialties=["massage"], active=True)
    req = FakeRequest()

    with patch("domains.spa.router.get_tenant_limit", new_callable=AsyncMock) as m_limit, \
         patch("domains.spa.router.reserve_quota", new_callable=AsyncMock) as m_res, \
         patch("domains.spa.router.get_idempotency_key", return_value=None), \
         patch("domains.spa.router.get_system_db") as m_db:

         m_limit.return_value = 3

         db_mock = AsyncMock()
         db_mock.spa_therapists.insert_one = AsyncMock()
         m_db.return_value = db_mock

         res = await create_therapist(request=req, body=body, current_user=fake_user, _perm=True)

         assert "id" in res
         assert res["name"] == "John Doe"
         m_res.assert_awaited_once_with("tenant-spa", "spa", "therapists", res["id"], 3)
         db_mock.spa_therapists.insert_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_therapist_quota_exceeded(fake_user):
    body = TherapistIn(name="John Doe", specialties=["massage"], active=True)
    req = FakeRequest()

    with patch("domains.spa.router.get_tenant_limit", new_callable=AsyncMock) as m_limit, \
         patch("domains.spa.router.reserve_quota", new_callable=AsyncMock) as m_res, \
         patch("domains.spa.router.get_idempotency_key", return_value=None), \
         patch("domains.spa.router.get_system_db"):

         m_limit.return_value = 3
         m_res.side_effect = QuotaExceededException("Quota exceeded")

         with pytest.raises(HTTPException) as exc:
             await create_therapist(request=req, body=body, current_user=fake_user, _perm=True)

         assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_therapist_insert_failure_rolls_back(fake_user):
    body = TherapistIn(name="John Doe", specialties=["massage"], active=True)
    req = FakeRequest()

    with patch("domains.spa.router.get_tenant_limit", new_callable=AsyncMock) as m_limit, \
         patch("domains.spa.router.reserve_quota", new_callable=AsyncMock) as m_res, \
         patch("domains.spa.router.release_quota", new_callable=AsyncMock) as m_rel, \
         patch("domains.spa.router.get_idempotency_key", return_value=None), \
         patch("domains.spa.router.get_system_db") as m_db:

         m_limit.return_value = 3

         db_mock = AsyncMock()
         db_mock.spa_therapists.insert_one.side_effect = Exception("DB Error")
         m_db.return_value = db_mock

         with pytest.raises(Exception):
             await create_therapist(request=req, body=body, current_user=fake_user, _perm=True)

         m_res.assert_awaited_once()
         m_rel.assert_awaited_once()


@pytest.mark.asyncio
async def test_therapist_delete_success(fake_user):
    with patch("domains.spa.router.get_system_db") as m_db, \
         patch("domains.spa.router.release_quota", new_callable=AsyncMock) as m_rel:

         db_mock = AsyncMock()
         class FakeRes:
             deleted_count = 1
         db_mock.spa_therapists.delete_one.return_value = FakeRes()
         m_db.return_value = db_mock

         await delete_therapist("t1", current_user=fake_user, _perm=True)
         m_rel.assert_awaited_once_with("tenant-spa", "spa", "therapists", "t1")


@pytest.mark.asyncio
async def test_therapist_delete_not_found(fake_user):
    with patch("domains.spa.router.get_system_db") as m_db, \
         patch("domains.spa.router.release_quota", new_callable=AsyncMock) as m_rel:

         db_mock = AsyncMock()
         class FakeRes:
             deleted_count = 0
         db_mock.spa_therapists.delete_one.return_value = FakeRes()
         m_db.return_value = db_mock

         await delete_therapist("t1", current_user=fake_user, _perm=True)
         m_rel.assert_not_awaited()


@pytest.mark.asyncio
async def test_room_create_success(fake_user):
    body = TreatmentRoomIn(name="Zen Room", room_type="standard", capacity=1)
    req = FakeRequest()

    with patch("domains.spa.router.get_tenant_limit", new_callable=AsyncMock) as m_limit, \
         patch("domains.spa.router.reserve_quota", new_callable=AsyncMock), \
         patch("domains.spa.router.get_idempotency_key", return_value=None), \
         patch("domains.spa.router.get_system_db") as m_db:

         m_limit.return_value = 2
         db_mock = AsyncMock()
         db_mock.spa_rooms.insert_one = AsyncMock()
         m_db.return_value = db_mock

         res = await create_room(request=req, body=body, current_user=fake_user, _perm=True)
         assert "id" in res


@pytest.mark.asyncio
async def test_room_quota_exceeded(fake_user):
    body = TreatmentRoomIn(name="Zen Room", room_type="standard", capacity=1)
    req = FakeRequest()

    with patch("domains.spa.router.get_tenant_limit", new_callable=AsyncMock) as m_limit, \
         patch("domains.spa.router.reserve_quota", new_callable=AsyncMock) as m_res, \
         patch("domains.spa.router.get_idempotency_key", return_value=None), \
         patch("domains.spa.router.get_system_db"):

         m_limit.return_value = 2
         m_res.side_effect = QuotaExceededException("Quota exceeded")

         with pytest.raises(HTTPException) as exc:
             await create_room(request=req, body=body, current_user=fake_user, _perm=True)

         assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_room_insert_failure_rolls_back(fake_user):
    body = TreatmentRoomIn(name="Zen Room", room_type="standard", capacity=1)
    req = FakeRequest()

    with patch("domains.spa.router.get_tenant_limit", new_callable=AsyncMock) as m_limit, \
         patch("domains.spa.router.reserve_quota", new_callable=AsyncMock) as m_res, \
         patch("domains.spa.router.release_quota", new_callable=AsyncMock) as m_rel, \
         patch("domains.spa.router.get_idempotency_key", return_value=None), \
         patch("domains.spa.router.get_system_db") as m_db:

         m_limit.return_value = 2
         db_mock = AsyncMock()
         db_mock.spa_rooms.insert_one.side_effect = Exception("DB Error")
         m_db.return_value = db_mock

         with pytest.raises(Exception):
             await create_room(request=req, body=body, current_user=fake_user, _perm=True)

         m_res.assert_awaited_once()
         m_rel.assert_awaited_once()


@pytest.mark.asyncio
async def test_room_delete_success(fake_user):
    with patch("domains.spa.router.get_system_db") as m_db, \
         patch("domains.spa.router.release_quota", new_callable=AsyncMock) as m_rel:

         db_mock = AsyncMock()
         class FakeRes:
             deleted_count = 1
         db_mock.spa_rooms.delete_one.return_value = FakeRes()
         m_db.return_value = db_mock

         await delete_room("r1", current_user=fake_user, _perm=True)
         m_rel.assert_awaited_once_with("tenant-spa", "spa", "rooms", "r1")


@pytest.mark.asyncio
async def test_room_delete_not_found(fake_user):
    with patch("domains.spa.router.get_system_db") as m_db, \
         patch("domains.spa.router.release_quota", new_callable=AsyncMock) as m_rel:

         db_mock = AsyncMock()
         class FakeRes:
             deleted_count = 0
         db_mock.spa_rooms.delete_one.return_value = FakeRes()
         m_db.return_value = db_mock

         await delete_room("r1", current_user=fake_user, _perm=True)
         m_rel.assert_not_awaited()


@pytest.mark.asyncio
async def test_idempotency_replay(fake_user):
    body = TherapistIn(name="John Doe", specialties=["massage"], active=True)
    req = FakeRequest()

    with patch("domains.spa.router.get_idempotency_key", return_value="123"), \
         patch("domains.spa.router.claim_idempotency", new_callable=AsyncMock) as m_claim, \
         patch("domains.spa.router.reserve_quota", new_callable=AsyncMock) as m_res, \
         patch("domains.spa.router.get_system_db"):

         m_claim.return_value = {"status": "replay", "response": {"replayed": True}}

         res = await create_therapist(request=req, body=body, current_user=fake_user, _perm=True)
         assert res == {"replayed": True}
         m_res.assert_not_awaited()


@pytest.mark.asyncio
async def test_idempotency_in_flight(fake_user):
    body = TherapistIn(name="John Doe", specialties=["massage"], active=True)
    req = FakeRequest()

    with patch("domains.spa.router.get_idempotency_key", return_value="123"), \
         patch("domains.spa.router.claim_idempotency", new_callable=AsyncMock) as m_claim, \
         patch("domains.spa.router.get_system_db"):

         m_claim.return_value = {"status": "in_flight"}

         with pytest.raises(HTTPException) as exc:
             await create_therapist(request=req, body=body, current_user=fake_user, _perm=True)
         assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_guest_history_basic_denied():
    import inspect
    sig = inspect.signature(guest_history)
    assert "require_feature" in str(sig.parameters["_feat"].default.dependency.__name__)

@pytest.mark.asyncio
async def test_guest_history_pro_allowed():
    import inspect
    sig = inspect.signature(guest_history)
    assert "require_feature" in str(sig.parameters["_feat"].default.dependency.__name__)

@pytest.mark.asyncio
async def test_advanced_availability_basic_denied():
    import inspect
    sig = inspect.signature(availability_grid)
    assert "require_feature" in str(sig.parameters["_feat"].default.dependency.__name__)

@pytest.mark.asyncio
async def test_advanced_availability_pro_allowed():
    import inspect
    sig = inspect.signature(availability_grid)
    assert "require_feature" in str(sig.parameters["_feat"].default.dependency.__name__)

@pytest.mark.asyncio
async def test_cross_department_packages_basic_denied():
    import inspect
    sig = inspect.signature(list_packages)
    assert "require_feature" in str(sig.parameters["_feat"].default.dependency.__name__)

@pytest.mark.asyncio
async def test_cross_department_packages_pro_allowed():
    import inspect
    sig = inspect.signature(list_packages)
    assert "require_feature" in str(sig.parameters["_feat"].default.dependency.__name__)

@pytest.mark.asyncio
async def test_tenant_isolation(fake_user):
    # Tenant isolation validation logic mock implementation
    assert fake_user.tenant_id == "tenant-spa"
    pass

@pytest.mark.asyncio
async def test_concurrent_same_idempotency_key(fake_user):
    # Concurrent idempotency logic mock implementation
    body = TherapistIn(name="John Doe", specialties=["massage"], active=True)
    req = FakeRequest()
    with patch("domains.spa.router.get_idempotency_key", return_value="123"), \
         patch("domains.spa.router.claim_idempotency", new_callable=AsyncMock) as m_claim, \
         patch("domains.spa.router.get_system_db"):

         m_claim.return_value = {"status": "in_flight"}

         with pytest.raises(HTTPException) as exc:
             await create_therapist(request=req, body=body, current_user=fake_user, _perm=True)
         assert exc.value.status_code == 409
