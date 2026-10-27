"""Outlet revenue must retain direct, room-charge and refund provenance."""
from domains.pms.pos_fnb.report_adapters import report
from tests.test_pos_final_consistency_replica import db  # noqa: F401
from tests.test_pos_presentation_replica import DAY, sale, seed_reports


async def test_outlets_sum_to_total_and_manual_unknown_is_not_assigned_arbitrarily(db):
    await seed_reports(db)  # bar cash 110 - refund 110 + room charge 220
    await db.pos_transactions.insert_one({**sale('cafe', 55), 'outlet_id': 'cafe'})
    await db.folio_charges.insert_many([
        {'tenant_id': 't', 'id': 'manual', 'charge_category': 'beverage', 'currency': 'EUR', 'business_date': DAY, 'amount': 10, 'total': 10},
        {'tenant_id': 't', 'id': 'legacy-room', 'source_pos_order_id': 'legacy', 'charge_category': 'beverage', 'currency': 'EUR', 'business_date': DAY, 'amount': 20, 'total': 20},
    ])
    await db.pos_orders.insert_many([
        {'tenant_id': 't', 'id': 'legacy', 'outlet_id': 'terrace'},
        {'tenant_id': 'foreign', 'id': 'legacy', 'outlet_id': 'WRONG'},
    ])
    result = await report(db, 't', 'mobile', DAY, DAY)
    grouped = result['orders']['by_outlet']
    assert grouped == {'bar': {'count': 2, 'revenue': 220}, 'cafe': {'count': 1, 'revenue': 55},
        'unassigned': {'count': 0, 'revenue': 10}, 'terrace': {'count': 0, 'revenue': 20}}
    assert sum(value['revenue'] for value in grouped.values()) == result['orders']['total_revenue'] == 305
