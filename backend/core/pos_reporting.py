"""Read-only POS report sources shared by PMS and revenue domains.

Settlements take precedence over order history; tenant and business-day scope
are explicit. Legacy refund enrichment never changes stored source documents.
"""
import asyncio
from datetime import UTC, datetime
from typing import Any


async def query_pos_transactions(
    tenant_id: str,
    *,
    limit: int | None = 50,
    outlet_id: str | None = None,
    booking_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    date: str | None = None,
    database,
    session=None,
    validate_duplicates=None,
) -> list[dict]:
    """Canonical POS transaction query.

    Finalized payments live in ``pos_transactions``. Older integrations wrote
    to ``pos_menu_transactions`` or the shared ``transactions`` collection.
    ``pos_orders`` is an operational order source, not a payment ledger, but is
    retained as a last-resort legacy fallback when no finalized transaction for
    that order exists. Read every source and de-duplicate by transaction and
    order identity so the same check cannot be counted twice.
    """
    common_q: dict[str, Any] = {"tenant_id": tenant_id}
    if outlet_id:
        common_q["outlet_id"] = outlet_id
    if booking_id:
        common_q["booking_id"] = booking_id

    legacy_q = dict(common_q)
    order_q = dict(common_q)
    if date:
        legacy_q["transaction_date"] = date
        order_q["business_date"] = date
    elif start_date or end_date:
        rng: dict[str, Any] = {}
        if start_date:
            rng["$gte"] = start_date
        if end_date:
            rng["$lte"] = end_date
        if rng:
            legacy_q["transaction_date"] = rng
            order_q["business_date"] = dict(rng)

    tx_q = dict(legacy_q)
    tx_q["$or"] = [{"category": "pos"}, {"_closure_source": "pos_menu_transactions"}]

    kwargs = {"session": session} if session is not None else {}
    queries = [(database.pos_transactions, legacy_q), (database.pos_menu_transactions, legacy_q),
               (database.transactions, tx_q), (database.pos_orders, order_q)]
    if session is not None:
        # MongoDB forbids parallel operations within one transaction/session.
        source_rows = [await coll.find(query, {"_id": 0}, **kwargs).sort("created_at", -1).to_list(limit)
                       for coll, query in queries]
    else:
        source_rows = await asyncio.gather(*(coll.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
                                           for coll, query in queries))

    financial_rows = [*source_rows[0], *source_rows[1], *source_rows[2]]
    if validate_duplicates is not None:
        # Normal report reads retain legacy precedence. Financial sealing may
        # instead reject conflicting copies before precedence hides them.
        validate_duplicates(financial_rows)
    settled_order_ids = {
        str(row.get("order_id"))
        for row in financial_rows
        if row.get("order_id")
    }
    merged: list[dict] = []
    seen_ids: set[str] = set()
    financial_order_source: dict[str, int] = {}
    for source_index, rows in enumerate(source_rows):
        is_order_source = source_index == 3
        for row in rows:
            row_id = str(row.get("id") or row.get("transaction_id") or "")
            order_id = str(row.get("order_id") or (row_id if is_order_source else ""))
            if is_order_source and order_id and order_id in settled_order_ids:
                continue
            if not is_order_source and order_id:
                prior_source = financial_order_source.get(order_id)
                if prior_source is not None and prior_source != source_index:
                    continue
                financial_order_source.setdefault(order_id, source_index)
            if row_id and row_id in seen_ids:
                continue
            if row_id:
                seen_ids.add(row_id)
            merged.append(row)
    merged.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return merged if limit is None else merged[:limit]



FINALIZED_STATUSES = frozenset({"completed", "closed", "paid", "settled", "refunded", "refund"})


def is_finalized(row):
    # A merged/served check is operational history, not another settlement.
    return str(row.get("status") or "").strip().lower() in FINALIZED_STATUSES


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
