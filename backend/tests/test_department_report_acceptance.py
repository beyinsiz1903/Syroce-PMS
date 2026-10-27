"""Department report acceptance (report audit 2026-10-19), as regressions.

Written by the audit against merged code, where these failed; kept here so
the fixes stay fixed. Only a disposable local Mongo database is used
(tests.test_report_ledger_mongo_acceptance.ledger_db).
"""
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.contact_center import reports_router as contact
from domains.hr import router as hr
from domains.revenue.analytics_router import maintenance
from domains.spa import router as spa
from routers import mice, procurement

pytest_plugins = ('tests.test_report_ledger_mongo_acceptance',)
USER = SimpleNamespace(tenant_id='A', id='audit-admin', role='admin', name='Artificial Admin', granted_permissions=[])


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 19, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def context(ledger_db, monkeypatch):
    for module in (maintenance, contact, hr):
        monkeypatch.setattr(module, 'db', ledger_db)
    monkeypatch.setattr(maintenance, 'datetime', Clock)
    monkeypatch.setattr(maintenance, 'get_current_user', AsyncMock(return_value=USER))
    for module in (spa, mice, procurement):
        monkeypatch.setattr(module, 'get_system_db', lambda: ledger_db)
    monkeypatch.setattr(mice, '_tenant_currency_code', AsyncMock(return_value='TRY'))
    monkeypatch.setattr(hr, '_attendance_business_date', AsyncMock(return_value=date(2026, 10, 19)))


async def task(db, **extra):
    await db.maintenance_tasks.insert_one({'tenant_id': 'A', 'id': 't', 'created_at': '2026-10-19T14:00:00+00:00', 'status': 'completed', 'cost': 100, 'currency': 'EUR', **extra})


async def test_maintenance_week_includes_monday_midnight_and_sunday_evening(ledger_db):
    """Week = Monday 00:00 to Sunday 24:00 in the hotel's time zone
    (Europe/Istanbul, UTC+3): 00:01 Monday local is 21:01 Sunday UTC."""
    await ledger_db.tenant_settings.insert_one({'tenant_id': 'A', 'timezone': 'Europe/Istanbul'})
    await task(ledger_db, created_at='2026-10-18T21:01:00+00:00')                # Mon 19 Oct 00:01 local
    await task(ledger_db, id='end', created_at='2026-10-25T20:59:00+00:00')      # Sun 25 Oct 23:59 local
    await task(ledger_db, id='next', created_at='2026-10-25T23:59:00+00:00')     # Mon 26 Oct 02:59 local: next week
    await task(ledger_db, id='prev', created_at='2026-10-18T20:59:00+00:00')     # Sun 18 Oct 23:59 local: last week
    report = await maintenance.get_weekly_maintenance_report(0, None)
    assert report['summary']['total_tasks'] == 2
    assert report['period'] == {'start': '2026-10-19', 'end': '2026-10-25', 'week_number': 43, 'timezone': 'Europe/Istanbul'}


async def test_maintenance_month_includes_last_day_afternoon(ledger_db):
    await task(ledger_db, created_at='2026-10-31T12:00:00+00:00')
    assert (await maintenance.get_monthly_maintenance_report('2026-10', None))['summary']['total_tasks'] == 1


async def test_maintenance_month_honors_bson_dates(ledger_db):
    await task(ledger_db, created_at=datetime(2026, 10, 19, 14, tzinfo=UTC))
    assert (await maintenance.get_monthly_maintenance_report('2026-10', None))['summary']['total_tasks'] == 1


async def test_maintenance_costs_do_not_add_euros_to_dollars(ledger_db):
    await task(ledger_db)
    await task(ledger_db, id='usd', currency='USD')
    costs = (await maintenance.get_monthly_maintenance_report('2026-10', None))['costs']
    assert costs.get('total_by_currency') == {'EUR': 100, 'USD': 100}, costs


async def test_maintenance_zero_response_time_is_a_valid_measurement(ledger_db):
    await task(ledger_db, response_time_minutes=0)
    await task(ledger_db, id='slow', response_time_minutes=10)
    assert (await maintenance.get_weekly_maintenance_report(0, None))['summary']['avg_response_time'] == 5


async def test_maintenance_invalid_month_is_a_client_error():
    try:
        await maintenance.get_monthly_maintenance_report('bad', None)
    except HTTPException as exc:
        assert 400 <= exc.status_code < 500
    else:
        pytest.fail('Malformed month accepted')


async def test_spa_summary_preserves_native_currencies(ledger_db):
    await ledger_db.spa_appointments.insert_many([{'tenant_id': 'A', 'id': code, 'starts_at': '2026-10-19T10:00:00Z', 'status': 'completed', 'price': 100, 'currency': code} for code in ['EUR', 'USD']])
    await ledger_db.folio_charges.insert_many([{'tenant_id': 'A', 'source_spa_appointment_id': code, 'total': 100, 'currency': code} for code in ['EUR', 'USD']])
    result = await spa.daily_summary('2026-10-19', USER)
    assert result.get('revenue_by_currency') == {'EUR': 100, 'USD': 100}, result


async def test_spa_summary_honors_bson_start_times(ledger_db):
    await ledger_db.spa_appointments.insert_one({'tenant_id': 'A', 'id': 'bson', 'starts_at': datetime(2026, 10, 19, 10, tzinfo=UTC), 'status': 'completed', 'price': 100, 'currency': 'EUR'})
    assert (await spa.daily_summary('2026-10-19', USER))['total'] == 1


async def test_spa_day_compares_instants_not_offset_text(ledger_db):
    """Review of #1371: '2026-10-19T22:00:00+03:00' sorted after the UTC
    upper bound as text and was dropped; the 18 Oct one was let in."""
    await ledger_db.tenant_settings.insert_one({'tenant_id': 'A', 'timezone': 'Europe/Istanbul'})
    rows = [('in-late', '2026-10-19T22:00:00+03:00'), ('in-early', '2026-10-19T00:00:00+03:00'), ('in-utc', '2026-10-19T20:59:59.999999+00:00'),
            ('in-naive-utc', '2026-10-18T21:00:00'), ('in-far-offset', '2026-10-20T09:00:00+14:00'),
            ('out-prev', '2026-10-18T22:00:00+03:00'), ('out-next', '2026-10-20T00:00:00+03:00'), ('out-garbage', 'not a date')]
    await ledger_db.spa_appointments.insert_many([{'tenant_id': 'A', 'id': i, 'starts_at': at, 'status': 'completed', 'price': 1, 'currency': 'EUR'} for i, at in rows])
    await ledger_db.folio_charges.insert_many([{'tenant_id': 'A', 'source_spa_appointment_id': i, 'total': 1, 'currency': 'EUR'} for i, _ in rows])
    result = await spa.daily_summary('2026-10-19', USER)
    assert result['total'] == 5 and result['revenue_by_currency'] == {'EUR': 5}, result


async def test_spa_invalid_date_is_a_client_error():
    try:
        await spa.daily_summary('bad', USER)
    except HTTPException as exc:
        assert 400 <= exc.status_code < 500
    else:
        pytest.fail('Malformed date accepted')


async def test_mice_summary_uses_the_same_period_and_status_as_list(ledger_db):
    await ledger_db.mice_events.insert_many([
        {'tenant_id': 'A', 'id': 'inside', 'start_date': '2026-10-19', 'end_date': '2026-10-19', 'status': 'confirmed', 'currency': 'EUR', 'totals': {'grand_total': 100}},
        {'tenant_id': 'A', 'id': 'outside', 'start_date': '2026-01-01', 'end_date': '2026-01-01', 'status': 'confirmed', 'currency': 'EUR', 'totals': {'grand_total': 999}},
        {'tenant_id': 'A', 'id': 'cancelled', 'start_date': '2026-10-19', 'end_date': '2026-10-19', 'status': 'cancelled', 'currency': 'EUR', 'totals': {'grand_total': 888}},
    ])
    result = await mice.list_events.__wrapped__('confirmed', '2026-10-01', '2026-10-31', USER)
    assert len(result['events']) == 1
    assert result['summary']['confirmed']['total_value_by_currency'] == {'EUR': 100}, result['summary']
    assert 'cancelled' not in result['summary']


async def test_hr_attendance_reads_all_70_staff_times_30_days(ledger_db, monkeypatch):
    await ledger_db.staff_members.insert_many([{'tenant_id': 'A', 'id': f's{i}', 'name': f'Staff {i}', 'active': True} for i in range(70)])
    await ledger_db.attendance_records.insert_many([{'tenant_id': 'A', 'staff_id': f's{i}', 'date': f'2026-10-{d:02}', 'total_hours': 8} for i in range(70) for d in range(1, 31)])
    report = await hr.get_attendance_summary('2026-10-01', '2026-10-30', USER)
    assert report['metrics']['total_hours'] == 16800, report['metrics']


async def test_contact_report_end_date_includes_whole_end_day(ledger_db):
    await ledger_db.contact_center_calls.insert_one({'tenant_id': 'A', 'id': 'end', 'started_at': datetime(2026, 10, 31, 12, tzinfo=UTC), 'status': 'missed'})
    report = await contact.get_performance_reports('2026-10-01', '2026-10-31', None, None, USER)
    assert report['summary']['total_calls'] == 1, report


async def test_contact_report_does_not_truncate_5001_calls(ledger_db):
    await ledger_db.contact_center_calls.insert_many([{'tenant_id': 'A', 'id': f'call-{i}', 'started_at': datetime(2026, 10, 19, tzinfo=UTC), 'status': 'missed'} for i in range(5001)])
    report = await contact.get_performance_reports(None, None, None, None, USER)
    assert report['summary']['total_calls'] == 5001, report


async def test_contact_callback_period_respects_end_and_queue(ledger_db):
    await ledger_db.contact_center_callbacks.insert_many([
        {'tenant_id': 'A', 'id': 'inside', 'queue_id': 'q1', 'abandoned_at': datetime(2026, 10, 19, tzinfo=UTC), 'status': 'completed'},
        {'tenant_id': 'A', 'id': 'future', 'queue_id': 'q1', 'abandoned_at': datetime(2026, 12, 1, tzinfo=UTC), 'status': 'pending'},
        {'tenant_id': 'A', 'id': 'other-queue', 'queue_id': 'q2', 'abandoned_at': datetime(2026, 10, 19, tzinfo=UTC), 'status': 'pending'},
    ])
    report = await contact.get_performance_reports('2026-10-01', '2026-10-31', 'q1', None, USER)
    assert report['summary']['callback_success_rate'] == 100, report




async def test_departments_exclude_other_tenant_records(ledger_db):
    await task(ledger_db, tenant_id='B')
    await ledger_db.spa_appointments.insert_one({'tenant_id': 'B', 'starts_at': '2026-10-19T10:00:00Z', 'status': 'completed', 'price': 999, 'currency': 'EUR'})
    await ledger_db.contact_center_calls.insert_one({'tenant_id': 'B', 'id': 'foreign', 'status': 'missed'})
    assert (await maintenance.get_weekly_maintenance_report(0, None))['summary']['total_tasks'] == 0
    assert (await spa.daily_summary('2026-10-19', USER))['total'] == 0
    assert (await contact.get_performance_reports(None, None, None, None, USER))['summary']['total_calls'] == 0


async def test_mice_native_currency_groups_are_kept_separate(ledger_db):
    await ledger_db.mice_events.insert_many([{'tenant_id': 'A', 'id': code, 'start_date': '2026-10-19', 'end_date': '2026-10-19', 'status': 'confirmed', 'currency': code, 'totals': {'grand_total': 100}} for code in ['EUR', 'USD']])
    result = await mice.list_events.__wrapped__(None, None, None, USER)
    assert result['summary']['confirmed']['total_value_by_currency'] == {'EUR': 100, 'USD': 100}


async def test_supplier_report_does_not_add_unconverted_po_currencies(ledger_db):
    await ledger_db.proc_suppliers.insert_one({'tenant_id': 'A', 'id': 'supplier', 'name': 'Artificial', 'active': True, 'credit_limit': 1000})
    await ledger_db.proc_purchase_orders.insert_many([{'tenant_id': 'A', 'supplier_id': 'supplier', 'status': 'sent', 'grand_total': 100, 'currency': code} for code in ['EUR', 'USD']])
    result = await procurement.credit_utilisation_report(False, USER)
    row = result['items'][0]
    assert row.get('open_total') != 200 or row.get('open_total_by_currency') == {'EUR': 100, 'USD': 100}, row


async def test_supplier_list_does_not_compare_a_lone_foreign_currency_to_the_limit(ledger_db):
    """Review of #1371: TRY 100 limit, only an EUR 100 open order -> the list
    sent open_commitment=100 and the screen showed 100 % used."""
    await ledger_db.proc_suppliers.insert_many([
        {'tenant_id': 'A', 'id': 'eur-only', 'name': 'EUR only', 'active': True, 'credit_limit': 100, 'currency': 'TRY'},
        {'tenant_id': 'A', 'id': 'try-only', 'name': 'TRY only', 'active': True, 'credit_limit': 100, 'currency': 'TRY'}])
    await ledger_db.proc_purchase_orders.insert_many([
        {'tenant_id': 'A', 'supplier_id': 'eur-only', 'status': 'sent', 'grand_total': 100, 'currency': 'EUR'},
        {'tenant_id': 'A', 'supplier_id': 'try-only', 'status': 'sent', 'grand_total': 40, 'currency': 'TRY'}])
    list_suppliers = getattr(procurement.list_suppliers, '__wrapped__', procurement.list_suppliers)
    rows = {row['id']: row for row in (await list_suppliers(True, None, True, USER))['items']}
    assert rows['eur-only']['open_commitment'] is None
    assert rows['eur-only']['limit_currency'] == 'TRY' and rows['eur-only']['open_commitment_unconverted'] == {'EUR': 100}
    assert rows['try-only']['open_commitment'] == 40 and rows['try-only']['open_commitment_unconverted'] == {}


async def test_hr_payroll_reads_every_attendance_record(ledger_db):
    """200 staff x 30 days = 6000 records: payroll must not stop at 5000."""
    await ledger_db.staff_members.insert_many([{'tenant_id': 'A', 'id': f's{i}', 'name': f'Staff {i}', 'active': True, 'base_salary': 30000}
                                               for i in range(200)])
    await ledger_db.attendance_records.insert_many([{'tenant_id': 'A', 'staff_id': f's{i}', 'date': f'2026-10-{d:02}', 'total_hours': 8}
                                                    for i in range(200) for d in range(1, 31)])
    found = await ledger_db.attendance_records.count_documents({'tenant_id': 'A'})
    assert found == 6000
    monkeypatch_rows = await hr._build_payroll('2026-10', 'A')
    period, payroll = monkeypatch_rows
    rows = payroll if isinstance(payroll, list) else payroll.get('items') or payroll.get('rows') or []
    assert period == '2026-10' and len(rows) == 200
    assert sum(float(row.get('total_hours') or 0) for row in rows) == 48000


async def test_maintenance_summary_today_is_the_hotel_day(ledger_db):
    """12:00 UTC on 19 Oct; 00:30 local (21:30 UTC the day before) is today,
    in text or BSON; 23:00 local on 18 Oct is not."""
    await task(ledger_db, id='early', created_at='2026-10-18T21:30:00+00:00', status='pending')
    await task(ledger_db, id='bson', created_at=datetime(2026, 10, 19, 9, tzinfo=UTC), status='pending')
    await task(ledger_db, id='yesterday', created_at='2026-10-18T20:00:00+00:00', status='pending')
    summary = await maintenance.get_maintenance_summary(None)
    assert summary['today_tasks'] == 2


async def test_maintenance_calendar_invalid_month_is_a_client_error():
    with pytest.raises(HTTPException) as exc:
        await maintenance.get_maintenance_calendar('2026-13', None)
    assert exc.value.status_code == 422
