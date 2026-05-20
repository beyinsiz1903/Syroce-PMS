"""
F8O Task #214 (P0) — AI no-show cross-tenant isolation regression.

Pins the fix for the stress-suite finding `44-ai-noshow-risk-dryrun.spec.js
§ C — leak_hits=2/2 sample=["BK001…","BK002…"]`. The GET
`/api/predictions/no-shows` endpoint previously returned hardcoded mock
booking IDs (`BK001`/`BK002`) for every caller, which collapsed the
tenant boundary: any tenant's token surfaced the same fabricated IDs and
tripped cross-tenant leak detectors (and would have leaked real IDs if
the resolver had been wired to a shared store).

These tests call the route handler directly (bypassing the FastAPI
Depends layer) with two distinct fake tenant identities and assert:
  1) No hardcoded `BK001`/`BK002` placeholder ever appears.
  2) Tenant A only sees Tenant A bookings; Tenant B only sees Tenant B.
  3) Empty arrival list returns an empty `predictions` array (no mock
     fallback).
  4) The defence-in-depth post-filter rejects a doc whose `tenant_id`
     somehow diverges from the requesting user's tenant (simulates a
     future cache/shared-resolver regression).
"""
from datetime import UTC, datetime

import pytest

from domains.ai.router import predictions as predictions_module


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, _limit):
        return list(self._docs)


class _FakeBookings:
    def __init__(self, docs):
        self._docs = docs
        self.last_query = None

    def find(self, query, _projection=None):
        self.last_query = query
        tenant_id = query.get('tenant_id')
        check_in = query.get('check_in')
        statuses = (query.get('status') or {}).get('$in') or []
        out = []
        for d in self._docs:
            if tenant_id is not None and d.get('tenant_id') != tenant_id:
                continue
            if check_in is not None and d.get('check_in') != check_in:
                continue
            if statuses and d.get('status') not in statuses:
                continue
            out.append(d)
        return _FakeCursor(out)


class _FakeDB:
    def __init__(self, bookings):
        self.bookings = _FakeBookings(bookings)


class _FakeUser:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id


def _seed():
    return [
        {'id': 'A-001', 'tenant_id': 'tenantA', 'check_in': '2026-06-01',
         'status': 'confirmed', 'ota_channel': 'booking_com',
         'payment_model': 'agency', 'total_amount': 50},
        {'id': 'A-002', 'tenant_id': 'tenantA', 'check_in': '2026-06-01',
         'status': 'guaranteed', 'payment_model': 'prepaid',
         'total_amount': 250},
        {'id': 'B-001', 'tenant_id': 'tenantB', 'check_in': '2026-06-01',
         'status': 'confirmed', 'ota_channel': 'expedia',
         'payment_model': 'hotel_collect', 'total_amount': 75},
        {'id': 'B-002', 'tenant_id': 'tenantB', 'check_in': '2026-06-01',
         'status': 'confirmed', 'payment_model': 'prepaid',
         'total_amount': 400},
        # Different date — must not appear in 2026-06-01 results.
        {'id': 'A-OOB', 'tenant_id': 'tenantA', 'check_in': '2026-07-15',
         'status': 'confirmed', 'total_amount': 100},
    ]


@pytest.fixture
def patch_db(monkeypatch):
    fake = _FakeDB(_seed())
    monkeypatch.setattr(predictions_module, 'db', fake)
    return fake


@pytest.mark.asyncio
async def test_no_mock_placeholders_returned(patch_db):
    """Regression: BK001/BK002 hardcoded mocks must never appear."""
    result = await predictions_module.predict_no_shows(
        target_date='2026-06-01', current_user=_FakeUser('tenantA'),
    )
    ids = {p['booking_id'] for p in result['predictions']}
    assert 'BK001' not in ids
    assert 'BK002' not in ids


@pytest.mark.asyncio
async def test_risk_score_is_fractional_0_to_1(patch_db):
    """Pin the GET contract: frontend PredictiveAnalytics.jsx renders
    `Math.round(pred.risk_score * 100)`, so risk_score MUST be in
    [0, 1]. If someone reverts to percentage-scale (0..100), users
    would see e.g. "2500%". This test fails loudly on that regression.
    """
    result = await predictions_module.predict_no_shows(
        target_date='2026-06-01', current_user=_FakeUser('tenantA'),
    )
    assert result['predictions'], 'fixture should produce at least one prediction'
    for p in result['predictions']:
        assert isinstance(p['risk_score'], float), \
            f"risk_score must be float (fractional), got {type(p['risk_score'])}"
        assert 0.0 <= p['risk_score'] <= 1.0, \
            f"risk_score must be in [0,1] (fractional), got {p['risk_score']}"
        assert p['risk_level'] in {'low', 'medium', 'high'}


@pytest.mark.asyncio
async def test_tenant_a_sees_only_tenant_a_bookings(patch_db):
    result = await predictions_module.predict_no_shows(
        target_date='2026-06-01', current_user=_FakeUser('tenantA'),
    )
    ids = {p['booking_id'] for p in result['predictions']}
    assert ids == {'A-001', 'A-002'}
    # Verify the Mongo filter actually included tenant_id (catches future
    # resolver/cache regression that drops the filter).
    assert patch_db.bookings.last_query.get('tenant_id') == 'tenantA'


@pytest.mark.asyncio
async def test_tenant_b_sees_only_tenant_b_bookings(patch_db):
    result = await predictions_module.predict_no_shows(
        target_date='2026-06-01', current_user=_FakeUser('tenantB'),
    )
    ids = {p['booking_id'] for p in result['predictions']}
    assert ids == {'B-001', 'B-002'}
    assert all('A-' not in i for i in ids)


@pytest.mark.asyncio
async def test_empty_arrivals_returns_empty_predictions_not_mocks(patch_db):
    """No bookings on date X → empty list, never a fallback mock payload."""
    result = await predictions_module.predict_no_shows(
        target_date='2030-01-01', current_user=_FakeUser('tenantA'),
    )
    assert result['predictions'] == []
    assert result['high_risk_count'] == 0
    assert result['total_at_risk'] == 0


@pytest.mark.asyncio
async def test_defence_in_depth_filter_drops_mismatched_tenant_doc(monkeypatch):
    """If a future shared cache returns a cross-tenant doc despite the
    Mongo filter, the in-handler tenant_id check must still drop it.
    """
    # Poisoned cursor: pretends the DB returned a tenantB doc even though
    # the query asked for tenantA.
    poisoned = [
        {'id': 'A-OK', 'tenant_id': 'tenantA', 'check_in': '2026-06-01',
         'status': 'confirmed', 'total_amount': 150},
        {'id': 'B-LEAK', 'tenant_id': 'tenantB', 'check_in': '2026-06-01',
         'status': 'confirmed', 'total_amount': 200},
    ]

    class _PoisonedBookings:
        last_query = None

        def find(self, query, _projection=None):
            _PoisonedBookings.last_query = query
            return _FakeCursor(poisoned)

    class _PoisonedDB:
        bookings = _PoisonedBookings()

    monkeypatch.setattr(predictions_module, 'db', _PoisonedDB())
    result = await predictions_module.predict_no_shows(
        target_date='2026-06-01', current_user=_FakeUser('tenantA'),
    )
    ids = {p['booking_id'] for p in result['predictions']}
    assert 'B-LEAK' not in ids
    assert ids == {'A-OK'}


@pytest.mark.asyncio
async def test_default_target_date_is_today_and_tenant_scoped(patch_db):
    """No target_date → defaults to today; still tenant-scoped."""
    result = await predictions_module.predict_no_shows(
        target_date=None, current_user=_FakeUser('tenantA'),
    )
    today = datetime.now().strftime('%Y-%m-%d')
    assert result['target_date'] == today
    # Default-date probe must still have used the tenant filter.
    assert patch_db.bookings.last_query.get('tenant_id') == 'tenantA'
