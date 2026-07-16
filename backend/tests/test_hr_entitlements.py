import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request
from pymongo.results import UpdateResult

from core.entitlements.quota import QuotaExceededException
from domains.hr.router import (
    StaffUpdatePayload,
    TerminationPayload,
    add_staff_member,
    delete_staff_member,
    terminate_staff,
    update_staff_member,
)


class MockUser:
    def __init__(self, tenant_id="tenant_123", id="user_123", role="manage_hr"):
        self.tenant_id = tenant_id
        self.id = id
        self.role = role


@pytest.fixture
def current_user():
    return MockUser()


@pytest.fixture
def mock_db():
    with patch("domains.hr.router.db") as mock:
        mock.idempotency_keys = AsyncMock()
        mock.tenant_quotas = AsyncMock()
        mock.tenant_limits = AsyncMock()
        mock.staff_members = AsyncMock()
        mock.staff_terminations = AsyncMock()
        mock.users = AsyncMock()
        yield mock


@pytest.fixture
def mock_idempotency():
    # Router uses begin_idempotency(db, request, ...) -> (guard, replay).
    # guard.complete(result) and guard.release(error=...) are called by the router.
    # We patch begin_idempotency to return a controllable (guard, replay) tuple.
    guard = MagicMock()
    guard.complete = AsyncMock()
    guard.release = AsyncMock()

    with patch("domains.hr.router.begin_idempotency", new_callable=AsyncMock) as mock_begin:
        # Default: first-time acquisition — no replay, active guard
        mock_begin.return_value = (guard, None)
        yield mock_begin, guard.complete, guard.release


@pytest.fixture
def mock_quota():
    with patch("domains.hr.router.reserve_quota", new_callable=AsyncMock) as mock_res, \
         patch("domains.hr.router.release_quota", new_callable=AsyncMock) as mock_rel, \
         patch("domains.hr.router.get_tenant_limit", new_callable=AsyncMock) as mock_limit, \
         patch("domains.hr.router.bootstrap_hr_active_employees", new_callable=AsyncMock) as mock_boot:

        mock_limit.return_value = 25
        # Bootstrap always succeeds as a no-op in router-level tests.
        # The bootstrap unit tests (test_hr_quota_bootstrap.py) cover its internals.
        mock_boot.return_value = {"skipped": True, "reason": "already_bootstrapped"}
        yield mock_res, mock_rel, mock_limit


@pytest.fixture
def mock_bootstrap():
    """Standalone bootstrap patch — used by tests that want to control boot outcome."""
    with patch("domains.hr.router.bootstrap_hr_active_employees", new_callable=AsyncMock) as mock:
        mock.return_value = {"skipped": True, "reason": "already_bootstrapped"}
        yield mock


def _make_request(tenant_id: str = "tenant_123") -> MagicMock:
    """Return a minimal FastAPI Request mock sufficient for the router."""
    req = MagicMock(spec=Request)
    req.headers = {"X-Idempotency-Key": f"test-key-{uuid.uuid4()}"}
    req.state = MagicMock()
    req.state.tenant_id = tenant_id
    return req


@pytest.fixture
def mock_audit():
    with patch("domains.hr.router._audit", new_callable=AsyncMock) as mock:
        yield mock


# ─── CREATE TESTS ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_success(current_user, mock_db, mock_idempotency, mock_quota, mock_audit):
    """Başarılı personel ekleme: reserve çağrılır, insert yapılır, complete çağrılır."""
    mock_begin, mock_complete, mock_release = mock_idempotency
    mock_res, mock_rel, mock_limit = mock_quota

    mock_db.staff_members.insert_one = AsyncMock()

    payload = {"name": "John Doe", "client_request_id": "req_123"}
    req = _make_request(current_user.tenant_id)
    res = await add_staff_member(req, payload, current_user=current_user)

    assert res["success"] is True
    mock_res.assert_called_once()
    mock_db.staff_members.insert_one.assert_called_once()
    mock_complete.assert_called_once()
    mock_rel.assert_not_called()
    mock_release.assert_not_called()


@pytest.mark.asyncio
async def test_create_quota_exceeded_403(current_user, mock_db, mock_idempotency, mock_quota, mock_audit):
    """Kota aşıldığında 403 döner, idem lock serbest bırakılır, insert yapılmaz."""
    mock_begin, mock_complete, mock_release = mock_idempotency
    mock_res, mock_rel, mock_limit = mock_quota

    mock_res.side_effect = QuotaExceededException("Quota exceeded")

    payload = {"name": "John Doe", "client_request_id": "req_123"}
    req = _make_request(current_user.tenant_id)
    with pytest.raises(HTTPException) as exc:
        await add_staff_member(req, payload, current_user=current_user)

    assert exc.value.status_code == 403
    mock_release.assert_called_once()
    mock_db.staff_members.insert_one.assert_not_called()
    mock_complete.assert_not_called()


@pytest.mark.asyncio
async def test_create_insert_failure_rolls_back_quota(current_user, mock_db, mock_idempotency, mock_quota, mock_audit):
    """DB insert başarısız olursa quota serbest bırakılır ve idem lock release edilir."""
    mock_begin, mock_complete, mock_release = mock_idempotency
    mock_res, mock_rel, mock_limit = mock_quota

    mock_db.staff_members.insert_one = AsyncMock(side_effect=Exception("DB Error"))

    payload = {"name": "John Doe", "client_request_id": "req_123"}
    req = _make_request(current_user.tenant_id)
    with pytest.raises(Exception, match="DB Error"):
        await add_staff_member(req, payload, current_user=current_user)

    mock_res.assert_called_once()
    mock_rel.assert_called_once()
    mock_release.assert_called_once()
    mock_complete.assert_not_called()


@pytest.mark.asyncio
async def test_idempotency_replay_skips_reserve_and_insert(current_user, mock_db, mock_idempotency, mock_quota, mock_audit):
    """Aynı Idempotency-Key ile tekrar çağrıldığında kayıtlı yanıt döner, reserve ve insert atlanır."""
    mock_begin, mock_complete, mock_release = mock_idempotency
    mock_res, mock_rel, mock_limit = mock_quota

    # begin_idempotency returns (guard, replay) where replay is the cached response
    from unittest.mock import MagicMock
    inactive_guard = MagicMock()
    inactive_guard.complete = AsyncMock()
    inactive_guard.release = AsyncMock()
    mock_begin.return_value = (
        inactive_guard,
        {"success": True, "staff_id": "existing-123", "source": "idempotent"},
    )

    payload = {"name": "John Doe", "client_request_id": "req_123"}
    req = _make_request(current_user.tenant_id)
    res = await add_staff_member(req, payload, current_user=current_user)

    assert res["source"] == "idempotent"
    assert res["staff_id"] == "existing-123"
    mock_res.assert_not_called()
    mock_db.staff_members.insert_one.assert_not_called()


@pytest.mark.asyncio
async def test_idempotency_in_flight_returns_409(current_user, mock_db, mock_idempotency, mock_quota, mock_audit):
    """Aynı key ile concurrent istek gelirse 409 döner, reserve ve insert yapılmaz."""
    mock_begin, mock_complete, mock_release = mock_idempotency
    mock_res, mock_rel, mock_limit = mock_quota

    # begin_idempotency itself raises 409 when status is in_flight
    mock_begin.side_effect = HTTPException(
        status_code=409,
        detail="Ayni Idempotency-Key ile baska bir istek isleniyor",
    )

    payload = {"name": "John Doe", "client_request_id": "req_123"}
    req = _make_request(current_user.tenant_id)
    with pytest.raises(HTTPException) as exc:
        await add_staff_member(req, payload, current_user=current_user)

    assert exc.value.status_code == 409
    mock_res.assert_not_called()
    mock_db.staff_members.insert_one.assert_not_called()


@pytest.mark.asyncio
async def test_create_without_client_request_id_no_idempotency(current_user, mock_db, mock_idempotency, mock_quota, mock_audit):
    """client_request_id olmadan çağrıldığında idem claim atlanır, reserve ve insert yapılır."""
    mock_begin, mock_complete, mock_release = mock_idempotency
    mock_res, mock_rel, mock_limit = mock_quota

    # No header → begin_idempotency returns (inactive_guard, None)
    # We simulate the inactive guard by ensuring complete is not called
    inactive_guard = MagicMock()
    inactive_guard.complete = AsyncMock()
    inactive_guard.release = AsyncMock()
    mock_begin.return_value = (inactive_guard, None)

    mock_db.staff_members.insert_one = AsyncMock()

    payload = {"name": "John Doe"}  # Idempotency-Key header yok
    req = _make_request(current_user.tenant_id)
    req.headers = {}  # no header
    res = await add_staff_member(req, payload, current_user=current_user)

    assert res["success"] is True
    mock_res.assert_called_once()
    mock_db.staff_members.insert_one.assert_called_once()


# ─── UPDATE TESTS ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_inactive_to_active_reserves(current_user, mock_db, mock_quota, mock_audit):
    """inactive → active geçişinde quota reserve edilir, update başarılıysa release yapılmaz."""
    mock_res, mock_rel, mock_limit = mock_quota

    mock_db.staff_members.find_one = AsyncMock(
        return_value={"id": "123", "active": False, "client_request_id": "req"}
    )
    mock_db.staff_members.update_one = AsyncMock(
        return_value=UpdateResult({"n": 1, "nModified": 1}, True)
    )

    payload = StaffUpdatePayload(active=True)
    res = await update_staff_member("123", payload, current_user=current_user)

    assert res["success"] is True
    mock_res.assert_called_once()
    mock_rel.assert_not_called()


@pytest.mark.asyncio
async def test_reactivation_quota_exceeded_keeps_db_unchanged(current_user, mock_db, mock_quota, mock_audit):
    """Reactivation sırasında quota aşılırsa DB update yapılmaz."""
    mock_res, mock_rel, mock_limit = mock_quota

    mock_db.staff_members.find_one = AsyncMock(
        return_value={"id": "123", "active": False, "client_request_id": "req"}
    )
    mock_res.side_effect = QuotaExceededException("Quota exceeded")

    payload = StaffUpdatePayload(active=True)
    with pytest.raises(HTTPException) as exc:
        await update_staff_member("123", payload, current_user=current_user)

    assert exc.value.status_code == 403
    mock_db.staff_members.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_reactivation_db_failure_rolls_back_quota(current_user, mock_db, mock_quota, mock_audit):
    """inactive → active geçişinde DB exception alınırsa quota release edilir."""
    mock_res, mock_rel, mock_limit = mock_quota

    mock_db.staff_members.find_one = AsyncMock(
        return_value={"id": "123", "active": False, "client_request_id": "req"}
    )
    mock_db.staff_members.update_one = AsyncMock(side_effect=Exception("DB Error"))

    payload = StaffUpdatePayload(active=True)
    with pytest.raises(Exception, match="DB Error"):
        await update_staff_member("123", payload, current_user=current_user)

    mock_res.assert_called_once()
    mock_rel.assert_called_once()


@pytest.mark.asyncio
async def test_active_to_inactive_releases(current_user, mock_db, mock_quota, mock_audit):
    """active → inactive geçişinde update başarılıysa quota release edilir."""
    mock_res, mock_rel, mock_limit = mock_quota

    mock_db.staff_members.find_one = AsyncMock(
        return_value={"id": "123", "active": True, "client_request_id": "req"}
    )
    mock_db.staff_members.update_one = AsyncMock(
        return_value=UpdateResult({"n": 1, "nModified": 1}, True)
    )

    payload = StaffUpdatePayload(active=False)
    res = await update_staff_member("123", payload, current_user=current_user)

    assert res["success"] is True
    mock_db.staff_members.update_one.assert_called_once()
    mock_rel.assert_called_once()
    mock_res.assert_not_called()


@pytest.mark.asyncio
async def test_active_to_inactive_db_failure_does_not_release(current_user, mock_db, mock_quota, mock_audit):
    """active → inactive geçişinde DB exception alınırsa release yapılmaz."""
    mock_res, mock_rel, mock_limit = mock_quota

    mock_db.staff_members.find_one = AsyncMock(
        return_value={"id": "123", "active": True, "client_request_id": "req"}
    )
    mock_db.staff_members.update_one = AsyncMock(side_effect=Exception("DB Error"))

    payload = StaffUpdatePayload(active=False)
    with pytest.raises(Exception, match="DB Error"):
        await update_staff_member("123", payload, current_user=current_user)

    mock_rel.assert_not_called()


@pytest.mark.asyncio
async def test_active_to_active_no_quota_change(current_user, mock_db, mock_quota, mock_audit):
    """active → active güncellemede (alan değişimi) quota çağrısı yapılmaz."""
    mock_res, mock_rel, mock_limit = mock_quota

    mock_db.staff_members.find_one = AsyncMock(
        return_value={"id": "123", "active": True, "client_request_id": "req"}
    )
    mock_db.staff_members.update_one = AsyncMock(
        return_value=UpdateResult({"n": 1, "nModified": 1}, True)
    )

    payload = StaffUpdatePayload(name="Updated Name")  # active flag yok
    res = await update_staff_member("123", payload, current_user=current_user)

    assert res["success"] is True
    mock_res.assert_not_called()
    mock_rel.assert_not_called()


@pytest.mark.asyncio
async def test_inactive_to_inactive_no_quota_change(current_user, mock_db, mock_quota, mock_audit):
    """inactive → inactive güncellemede (alan değişimi) quota çağrısı yapılmaz."""
    mock_res, mock_rel, mock_limit = mock_quota

    mock_db.staff_members.find_one = AsyncMock(
        return_value={"id": "123", "active": False, "client_request_id": "req"}
    )
    mock_db.staff_members.update_one = AsyncMock(
        return_value=UpdateResult({"n": 1, "nModified": 1}, True)
    )

    payload = StaffUpdatePayload(name="Updated Name")  # active flag yok
    res = await update_staff_member("123", payload, current_user=current_user)

    assert res["success"] is True
    mock_res.assert_not_called()
    mock_rel.assert_not_called()


# ─── DELETE TESTS ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_active_releases_once(current_user, mock_db, mock_quota, mock_audit):
    """Aktif personel silindiğinde quota release edilir — bir kez."""
    mock_res, mock_rel, mock_limit = mock_quota

    mock_db.staff_members.find_one = AsyncMock(
        return_value={"id": "123", "active": True, "client_request_id": "req"}
    )
    mock_db.staff_members.update_one = AsyncMock(
        return_value=UpdateResult({"n": 1, "nModified": 1}, True)
    )

    res = await delete_staff_member("123", current_user=current_user)

    assert res["success"] is True
    mock_rel.assert_called_once()


@pytest.mark.asyncio
async def test_delete_inactive_does_not_release(current_user, mock_db, mock_quota, mock_audit):
    """Pasif personel silindiğinde release yapılmaz."""
    mock_res, mock_rel, mock_limit = mock_quota

    mock_db.staff_members.find_one = AsyncMock(
        return_value={"id": "123", "active": False, "client_request_id": "req"}
    )
    mock_db.staff_members.update_one = AsyncMock(
        return_value=UpdateResult({"n": 1, "nModified": 1}, True)
    )

    res = await delete_staff_member("123", current_user=current_user)

    assert res["success"] is True
    mock_rel.assert_not_called()


@pytest.mark.asyncio
async def test_delete_not_found_does_not_release(current_user, mock_db, mock_quota, mock_audit):
    """staff_members'da bulunmayan personel silinmeye çalışıldığında release yapılmaz."""
    mock_res, mock_rel, mock_limit = mock_quota

    # staff_members'da yok, users'da da yok
    mock_db.staff_members.find_one = AsyncMock(return_value=None)
    mock_db.staff_members.update_one = AsyncMock(
        return_value=UpdateResult({"n": 0, "nModified": 0}, True)
    )
    mock_db.users.update_one = AsyncMock(
        return_value=UpdateResult({"n": 0, "nModified": 0}, True)
    )

    # 404 dönmeli
    with pytest.raises(HTTPException) as exc:
        await delete_staff_member("nonexistent", current_user=current_user)

    assert exc.value.status_code == 404
    mock_rel.assert_not_called()


# ─── TERMINATE TESTS ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_terminate_active_releases_once(current_user, mock_db, mock_quota, mock_audit):
    """Aktif personel işten çıkarıldığında quota release edilir — bir kez."""
    mock_res, mock_rel, mock_limit = mock_quota

    with patch("domains.hr.router._verify_staff_in_tenant", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = {
            "id": "123",
            "active": True,
            "client_request_id": "req",
            "name": "Test User",
        }
        mock_db.staff_members.find_one = AsyncMock(
            return_value={"id": "123", "active": True, "client_request_id": "req"}
        )
        mock_db.staff_members.update_one = AsyncMock(
            return_value=UpdateResult({"n": 1, "nModified": 1}, True)
        )
        mock_db.staff_terminations.insert_one = AsyncMock()
        mock_db.staff_equipment.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
        mock_db.tenant_settings.find_one = AsyncMock(return_value={})

        payload = TerminationPayload(reason="resign", last_day="2026-07-16")
        res = await terminate_staff("123", payload, force_release=True, current_user=current_user)

        assert res["success"] is True
        mock_rel.assert_called_once()


@pytest.mark.asyncio
async def test_terminate_inactive_does_not_release(current_user, mock_db, mock_quota, mock_audit):
    """Pasif personel işten çıkarıldığında quota release yapılmaz."""
    mock_res, mock_rel, mock_limit = mock_quota

    with patch("domains.hr.router._verify_staff_in_tenant", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = {
            "id": "123",
            "active": False,
            "client_request_id": "req",
            "name": "Test User",
        }
        mock_db.staff_members.find_one = AsyncMock(
            return_value={"id": "123", "active": False, "client_request_id": "req"}
        )
        mock_db.staff_members.update_one = AsyncMock(
            return_value=UpdateResult({"n": 1, "nModified": 1}, True)
        )
        mock_db.staff_terminations.insert_one = AsyncMock()
        mock_db.staff_equipment.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
        mock_db.tenant_settings.find_one = AsyncMock(return_value={})

        payload = TerminationPayload(reason="resign", last_day="2026-07-16")
        res = await terminate_staff("123", payload, force_release=True, current_user=current_user)

        assert res["success"] is True
        mock_rel.assert_not_called()


@pytest.mark.asyncio
async def test_terminate_already_terminated_no_double_release(current_user, mock_db, mock_quota, mock_audit):
    """terminated_at alanı olan personel için terminate çağrısı 400 döner, release yapılmaz."""
    mock_res, mock_rel, mock_limit = mock_quota

    with patch("domains.hr.router._verify_staff_in_tenant", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = {
            "id": "123",
            "active": False,
            "terminated_at": "2026-07-10T10:00:00Z",
            "name": "Test User",
        }

        payload = TerminationPayload(reason="resign", last_day="2026-07-16")
        with pytest.raises(HTTPException) as exc:
            await terminate_staff("123", payload, force_release=True, current_user=current_user)

        assert exc.value.status_code == 400
        mock_rel.assert_not_called()


@pytest.mark.asyncio
async def test_delete_after_terminate_no_double_release(current_user, mock_db, mock_quota, mock_audit):
    """terminate sonrası delete çağrıldığında release iki kez yapılmaz (personel active=False)."""
    mock_res, mock_rel, mock_limit = mock_quota

    # Terminate sonrası personel active=False durumda
    mock_db.staff_members.find_one = AsyncMock(
        return_value={"id": "123", "active": False, "terminated_at": "2026-07-10T10:00:00Z"}
    )
    mock_db.staff_members.update_one = AsyncMock(
        return_value=UpdateResult({"n": 1, "nModified": 1}, True)
    )

    res = await delete_staff_member("123", current_user=current_user)

    assert res["success"] is True
    # active=False olduğu için release yapılmaz
    mock_rel.assert_not_called()


# ─── ISOLATION AND DERIVED USER TESTS ────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_isolation(mock_db, mock_quota, mock_audit):
    """Farklı tenant_id'li kullanıcı başka tenant'ın personeline erişemez."""
    mock_res, mock_rel, mock_limit = mock_quota

    tenant_a_user = MockUser(tenant_id="tenant_A")

    # tenant_B'nin personeli
    def find_one_side_effect(query, *args, **kwargs):
        if query.get("tenant_id") == "tenant_A":
            return AsyncMock(return_value=None)()
        return AsyncMock(return_value={"id": "staff_B", "active": True, "tenant_id": "tenant_B"})()

    mock_db.staff_members.find_one = MagicMock(side_effect=find_one_side_effect)
    mock_db.staff_members.update_one = AsyncMock(
        return_value=UpdateResult({"n": 0, "nModified": 0}, True)
    )
    mock_db.users.update_one = AsyncMock(
        return_value=UpdateResult({"n": 0, "nModified": 0}, True)
    )

    # tenant_A, tenant_B'nin personelini silmeye çalışır → 404
    with pytest.raises(HTTPException) as exc:
        await delete_staff_member("staff_B", current_user=tenant_a_user)

    assert exc.value.status_code == 404
    mock_rel.assert_not_called()


@pytest.mark.asyncio
async def test_users_collection_does_not_consume_staff_quota(current_user, mock_db, mock_idempotency, mock_quota, mock_audit):
    """Users-derived (sistem kullanıcıları) kayıtlar staff quota'sını tüketmemeli.

    add_staff_member yalnız staff_members koleksiyonuna yazar.
    quota sistemi reserve_quota ile takip eder — users koleksiyonu bunun dışında.
    Bu test reserve_quota'nın staff_members insert'iyle birlikte çağrıldığını,
    users.insert_one'ın hiç çağrılmadığını doğrular.
    """
    mock_claim, mock_complete, mock_release = mock_idempotency
    mock_res, mock_rel, mock_limit = mock_quota

    mock_db.staff_members.insert_one = AsyncMock()
    mock_db.users.insert_one = AsyncMock()

    payload = {"name": "System Admin Clone", "client_request_id": "req_user_derived"}
    req = _make_request(current_user.tenant_id)
    res = await add_staff_member(req, payload, current_user=current_user)

    assert res["success"] is True
    # Quota sadece staff_members için reserve edilmeli
    mock_res.assert_called_once()
    # users koleksiyonuna hiç yazılmamalı
    mock_db.users.insert_one.assert_not_called()


# ─── ROUTER BOOTSTRAP ENTEGRASYON TESTLERİ ────────────────────────────────────
# Bu testler talep edilen özel isimlerle:
# test_create_calls_reconciliation_before_reserve
# test_reactivation_calls_reconciliation_before_reserve

@pytest.mark.asyncio
async def test_create_calls_reconciliation_before_reserve(current_user, mock_db, mock_idempotency, mock_audit):
    """add_staff_member: bootstrap_hr_active_employees, reserve_quota'dan önce çağrılmalı.

    Reconciliation sırası: bootstrap → reserve → insert → complete.
    Bootstrap hiç atlanmamalı — her create isteğinde çağrılır (fast-path'e düşse bile).
    """
    mock_claim, mock_complete, mock_release = mock_idempotency
    call_order: list[str] = []

    async def boot_side_effect(*a, **kw):
        call_order.append("bootstrap")
        return {"skipped": True, "reason": "already_bootstrapped"}

    async def reserve_side_effect(*a, **kw):
        call_order.append("reserve")
        return {}

    with patch("domains.hr.router.bootstrap_hr_active_employees", side_effect=boot_side_effect), \
         patch("domains.hr.router.reserve_quota", side_effect=reserve_side_effect), \
         patch("domains.hr.router.get_tenant_limit", new_callable=AsyncMock, return_value=25):

        mock_db.staff_members.insert_one = AsyncMock()
        payload = {"name": "Bootstrap Test", "client_request_id": "req_bootstrap"}
        req = _make_request(current_user.tenant_id)
        await add_staff_member(req, payload, current_user=current_user)

    assert call_order == ["bootstrap", "reserve"], (
        f"Beklenen sıra: ['bootstrap', 'reserve'], Gerçek: {call_order}"
    )


@pytest.mark.asyncio
async def test_reactivation_calls_reconciliation_before_reserve(current_user, mock_db, mock_quota, mock_audit):
    """update_staff_member inactive→active: bootstrap_hr_active_employees, reserve'den önce çağrılmalı."""
    mock_res, mock_rel, mock_limit = mock_quota
    call_order: list[str] = []

    async def boot_side_effect(*a, **kw):
        call_order.append("bootstrap")
        return {"skipped": True, "reason": "already_bootstrapped"}

    async def reserve_side_effect(*a, **kw):
        call_order.append("reserve")
        return {}

    mock_db.staff_members.find_one = AsyncMock(
        return_value={"id": "staff-react", "active": False, "tenant_id": "tenant_123"}
    )
    mock_db.staff_members.update_one = AsyncMock(
        return_value=UpdateResult({"n": 1, "nModified": 1}, True)
    )
    mock_db.users.update_one = AsyncMock(
        return_value=UpdateResult({"n": 0, "nModified": 0}, True)
    )

    with patch("domains.hr.router.bootstrap_hr_active_employees", side_effect=boot_side_effect), \
         patch("domains.hr.router.reserve_quota", side_effect=reserve_side_effect), \
         patch("domains.hr.router.get_tenant_limit", new_callable=AsyncMock, return_value=25):

        payload = StaffUpdatePayload(active=True)
        await update_staff_member("staff-react", payload, current_user=current_user)

    assert "bootstrap" in call_order, "bootstrap hiç çağrılmadı"
    assert "reserve" in call_order, "reserve hiç çağrılmadı"
    bootstrap_idx = call_order.index("bootstrap")
    reserve_idx = call_order.index("reserve")
    assert bootstrap_idx < reserve_idx, (
        f"bootstrap ({bootstrap_idx}) reserve'den ({reserve_idx}) önce çağrılmalıydı"
    )
