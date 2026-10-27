"""Read-only enrichment of legacy refunds; never rewrite accounting history."""
from datetime import UTC, datetime


def is_refund(row):
    return row.get('payment_type') == 'refund' or row.get('status') == 'refunded'


def category_amounts(row):
    if 'category_amounts' in row:
        return row['category_amounts'] or {}
    result = {}
    for line in row.get('order_items') or row.get('items') or []:
        category = line.get('category') or 'other'
        amount = line.get('total', line.get('total_price'))
        if amount is None:
            amount = float(line.get('unit_price', line.get('price', 0)) or 0) * float(line.get('quantity', 1) or 1)
        result[category] = result.get(category, 0) + float(amount or 0)
    return result


def _time(row):
    value = row.get('created_at') or row.get('transaction_date') or ''
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.astimezone(UTC).isoformat()
    return str(value)


async def enrich_refunds(database, tenant_id, rows, session=None):
    kwargs = {"session": session} if session is not None else {}
    refunds = [row for row in rows if is_refund(row)]
    if not refunds:
        return rows, []
    ids = [r['original_transaction_id'] for r in refunds if r.get('original_transaction_id')]
    orders = [r['order_id'] for r in refunds if r.get('order_id')]
    source_filter = {'tenant_id': tenant_id, 'status': 'completed', '$or': [{'id': {'$in': ids}}, {'order_id': {'$in': orders}}]}
    sources = await database.pos_transactions.find(source_filter, {'_id': 0}, **kwargs).to_list(None)
    sources = [row for row in sources if not is_refund(row) and row.get('status') == 'completed']
    by_id = {row.get('id'): row for row in sources}
    by_order = {row.get('order_id'): row for row in sources if row.get('order_id')}
    history = await database.pos_transactions.find({
        'tenant_id': tenant_id, '$or': [{'original_transaction_id': {'$in': list(by_id)}}, {'order_id': {'$in': orders}}],
        '$and': [{'$or': [{'payment_type': 'refund'}, {'status': 'refunded'}]}],
    }, {'_id': 0}, **kwargs).to_list(None)
    known = {row.get('id'): row for row in history if is_refund(row)}
    known.update({row['id']: row for row in refunds if row.get('id')})
    consumed = {}
    enriched = {}
    warnings = []
    for row in sorted(known.values(), key=lambda r: (_time(r), str(r.get('id')))):
        # An explicit source ID cannot silently fall back to another sale.
        source = (by_id.get(row['original_transaction_id']) if row.get('original_transaction_id')
                  else by_order.get(row.get('order_id')))
        if source and row.get('order_id') and source.get('order_id') != row['order_id']:
            source = None
        paid = float((source or {}).get('total_amount') or 0)
        if not source or paid <= 0:
            if any(field not in row for field in ('tax_amount', 'category_amounts')):
                warnings.append('Bazı eski iadelerin kaynak satışı doğrulanamadı; KDV/kategori ayrıntıları eksik olabilir.')
            continue
        previous = consumed.get(source['id'], 0)
        current = min(paid, round(previous + abs(float(row.get('total_amount') or row.get('amount') or 0)), 2))
        consumed[source['id']] = current
        copy = dict(row)
        copy['source_sale'] = source
        source_currency = str(source.get('currency') or '').strip().upper()
        refund_currency = str(row.get('currency') or '').strip().upper()
        if source_currency and refund_currency and source_currency != refund_currency:
            warnings.append('İade para birimi kaynak satışla uyuşmuyor; kapanış öncesinde kaynakları inceleyin.')
        elif not refund_currency and source_currency:
            # Immutable source sale, not today's property or tender currency.
            # The stored legacy refund remains untouched.
            copy['currency'] = source_currency
        for field in ('tax_amount', 'tip_amount', 'discount_amount', 'service_charge_amount'):
            if field not in copy:
                original = float(source.get(field) or 0)
                copy[field] = -round(round(original * current / paid, 2) - round(original * previous / paid, 2), 2)
        if 'category_amounts' not in copy:
            copy['category_amounts'] = {key: -round(round(value * current / paid, 2) - round(value * previous / paid, 2), 2)
                                        for key, value in category_amounts(source).items()}
        enriched[row['id']] = copy
    return [enriched.get(row.get('id'), row) for row in rows], list(dict.fromkeys(warnings))
