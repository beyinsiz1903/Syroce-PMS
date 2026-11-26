"""Batch read-only reservation balances for operational lists."""


async def reservation_balances(database, tenant_id, bookings):
    from routers.reservation_detail import _build_financial_summary

    by_id = {row['id']: row for row in bookings if row.get('id')}
    if not by_id:
        return {}
    scope = {'tenant_id': tenant_id, 'booking_id': {'$in': list(by_id)}}
    folio_owner = {row['id']: row['booking_id'] async for row in database.folios.find(
        scope, {'_id': 0, 'id': 1, 'booking_id': 1}) if row.get('id')}
    financial_scope = {'tenant_id': tenant_id, '$or': [
        {'booking_id': {'$in': list(by_id)}}, {'folio_id': {'$in': list(folio_owner)}}]}
    grouped = {name: {key: [] for key in by_id} for name in ('charges', 'payments', 'extras', 'deposits')}
    for name, collection, query in (
        ('charges', database.folio_charges, financial_scope),
        ('payments', database.payments, financial_scope),
        ('extras', database.extra_charges, scope),
        ('deposits', database.deposits, scope),
    ):
        async for row in collection.find(query, {'_id': 0}):
            owners = {row.get('booking_id')}
            if name in ('charges', 'payments'):
                owners.add(folio_owner.get(row.get('folio_id')))
            for owner in owners.intersection(by_id):
                grouped[name][owner].append(row)
    return {key: _build_financial_summary(booking, grouped['charges'][key], grouped['payments'][key],
        grouped['extras'][key], grouped['deposits'][key])['reservation_total_due'] for key, booking in by_id.items()}
