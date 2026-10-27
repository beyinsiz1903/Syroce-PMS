"""SPA income is actual active folio debt, not catalog value or cash received."""
from types import SimpleNamespace

from domains.spa import router as spa

pytest_plugins = ('tests.test_report_ledger_mongo_acceptance',)
USER = SimpleNamespace(tenant_id='A')


async def test_comp_transfers_voids_and_native_currencies_reconcile_to_real_charges(ledger_db, monkeypatch):
    monkeypatch.setattr(spa, 'get_system_db', lambda: ledger_db)
    await ledger_db.spa_appointments.insert_many([{'tenant_id': 'A', 'id': aid, 'starts_at': '2026-10-25T10:00:00Z',
        'status': 'completed', 'price': price, 'currency': code}
        for aid, code, price in [('normal', 'TRY', 1500), ('comp', 'TRY', 1500), ('eur', 'EUR', 30), ('usd', 'USD', 30), ('void', 'TRY', 900)]])
    await ledger_db.folio_charges.insert_many([
        {'tenant_id': 'A', 'source_spa_appointment_id': 'normal', 'booking_id': 'first-room', 'total': 750, 'currency': 'TRY'},
        {'tenant_id': 'A', 'source_spa_appointment_id': 'normal', 'booking_id': 'other-room', 'total': 750, 'currency': 'TRY', 'split_from_charge_id': 'source'},
        {'tenant_id': 'A', 'source_spa_appointment_id': 'comp', 'total': 0, 'currency': 'TRY', 'is_complimentary': True, 'complimentary_original_amount': 1500},
        {'tenant_id': 'A', 'source_spa_appointment_id': 'eur', 'total': 30, 'currency': 'EUR'},
        {'tenant_id': 'A', 'source_spa_appointment_id': 'usd', 'total': 30, 'currency': 'USD'},
        {'tenant_id': 'A', 'source_spa_appointment_id': 'void', 'total': 900, 'currency': 'TRY', 'voided': True},
        {'tenant_id': 'B', 'source_spa_appointment_id': 'normal', 'total': 99999, 'currency': 'TRY'},
        {'tenant_id': 'A', 'source_spa_appointment_id': 'another-day', 'total': 99999, 'currency': 'TRY'},
    ])
    result = await spa.daily_summary('2026-10-25', USER)
    assert result['revenue_by_currency'] == {'EUR': 30, 'TRY': 1500, 'USD': 30}
    assert result['revenue'] is None
    assert result['complimentary_value_by_currency'] == {'TRY': 1500}
    assert result['catalog_value_by_currency'] == {'EUR': 30, 'TRY': 3900, 'USD': 30}
    assert result['revenue_complete'] and result['unposted_appointments'] == 0


async def test_completed_legacy_without_real_charge_is_visible_not_fabricated_income(ledger_db, monkeypatch):
    monkeypatch.setattr(spa, 'get_system_db', lambda: ledger_db)
    await ledger_db.spa_appointments.insert_one({'tenant_id': 'A', 'id': 'legacy', 'starts_at': '2026-10-25T10:00:00Z',
        'status': 'completed', 'charge_to_room': True, 'price': 1900, 'currency': 'TRY'})
    result = await spa.daily_summary('2026-10-25', USER)
    assert result['revenue'] == 0 and result['revenue_by_currency'] == {}
    assert not result['revenue_complete'] and result['unposted_appointments'] == 1
    assert result['unposted_value_by_currency'] == {'TRY': 1900}
    assert not await ledger_db.folio_charges.count_documents({}), 'Reporting must not repair history by guessing'
