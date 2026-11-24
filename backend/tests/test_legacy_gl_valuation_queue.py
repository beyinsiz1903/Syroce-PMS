from types import SimpleNamespace
from unittest.mock import AsyncMock

from domains.accounting import gl_router
from tests.test_report_ledger_mongo_acceptance import ledger_db  # noqa: F401


async def test_old_posted_unvalued_runs_remain_actionable_but_closed_scope_and_permissions_hold(ledger_db, monkeypatch):  # noqa: F811
    base = {'tenant_id': 'hotel', 'status': 'completed', 'business_date': '2026-10-26', 'gl_bridge_status': 'posted'}
    await ledger_db.night_audit_runs.insert_many([
        {**base, 'id': 'legacy'},
        {**base, 'id': 'valued', 'gl_valued_entry_id': 'journal'},
        {**base, 'id': 'dry', 'dry_run': True},
        {**base, 'id': 'dry-old', 'is_dry_run': True},
        {**base, 'id': 'incomplete', 'status': 'running'},
        {**base, 'id': 'foreign', 'tenant_id': 'other'},
        {**base, 'id': 'pending', 'gl_bridge_status': 'valuation_required'},
        {**base, 'id': 'failed', 'gl_bridge_status': 'failed'},
    ])
    monkeypatch.setattr(gl_router, 'db', ledger_db)
    monkeypatch.setattr(gl_router, 'get_operational_mapping', AsyncMock(return_value={'enabled': True}))
    result = await gl_router.operational_gl_status(SimpleNamespace(role='finance', tenant_id='hotel'))
    assert {r['id'] for r in result['pending_night_audits']} == {'legacy', 'pending', 'failed'}
    assert result['source_valuation_pending'] == 2
    read_only = await gl_router.operational_gl_status(SimpleNamespace(role='supervisor', tenant_id='hotel'))
    assert not read_only['can_value_night_audit'] and read_only['pending_night_audits'] == []
    assert await ledger_db.night_audit_runs.count_documents({'gl_valued_entry_id': {'$exists': True}}) == 1
