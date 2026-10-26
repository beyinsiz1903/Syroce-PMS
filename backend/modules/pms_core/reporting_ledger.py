"""Shared, read-only accounting ledger selection for reports and workers."""

import asyncio
from datetime import UTC, date, datetime, time, timedelta

from core.business_date_service import accounting_period_match
from modules.pms_core.report_money import money, resolve_ledger_currencies, rounded
from modules.pms_core.revenue_categories import (
    charge_category,  # noqa: F401 — public shared API
    is_revenue_charge,
)


def charge_amount(row: dict, *, round_to_cents: bool = True) -> float:
    """Report cents by default; validators can request unrounded evidence."""
    for field in ("total", "charge_amount", "amount"):
        if row.get(field) is not None:
            amount = money(row[field] or 0)
            if field == "charge_amount" and row.get("report_source") == "extra":
                amount *= money(row.get("quantity") if row.get("quantity") is not None else 1)
            return rounded(amount) if round_to_cents else float(amount)
    return 0.0


async def posted_revenue_rows(tenant_id: str, start: date, end: date, *, database, fallback_currency: str | None = None) -> list[dict]:
    """Return posted folio, manual-extra and untransferred POS revenue once."""
    start_text = start.isoformat()
    next_day = (end + timedelta(days=1)).isoformat()
    period = {"$gte": start_text, "$lt": next_day}
    bson_period = {"$gte": datetime.combine(start, time.min, UTC), "$lt": datetime.combine(end + timedelta(days=1), time.min, UTC)}

    def legacy_period(field, *missing):
        return {**{key: {"$in": [None, ""]} for key in missing},
            "$or": [{field: period}, {field: bson_period}]}

    def report_period_match(*legacy_clauses):
        query = accounting_period_match(start_text, end.isoformat(), *legacy_clauses)
        query["$or"][0] = {"business_date": period}
        query["$or"].append({"business_date": bson_period})
        return query

    charge_query = {
        "tenant_id": tenant_id,
        "voided": {"$ne": True},
        **report_period_match(
            legacy_period("date"), legacy_period("charge_date", "date"), legacy_period("posted_at", "date", "charge_date"), legacy_period("created_at", "date", "charge_date", "posted_at")),
    }
    projection = {
        "_id": 0,
        "id": 1,
        "charge_category": 1,
        "category": 1,
        "charge_type": 1,
        "total": 1,
        "charge_amount": 1,
        "amount": 1,
        "currency": 1,
        "source_pos_order_id": 1,
        "booking_id": 1,
        "folio_id": 1,
        'outlet_id': 1,
        "business_date": 1,
        "date": 1,
        "charge_date": 1,
        "posted_at": 1,
        "created_at": 1,
        "service_category": 1,
        "revenue_category": 1,
        "subtotal": 1,
        "discount_amount": 1,
        "quantity": 1,
        "unit_price": 1,
        "vat_amount": 1,
        "tax_amount": 1,
        "tax_breakdown": 1,
        "tax_inclusive": 1,
        "posted_by": 1,
        "demo_reconstruction": 1,
        'pos_financial_version': 1,
    }
    folio_rows, extra_rows, pos_rows = await asyncio.gather(
        # Financial reports may cover high-volume F&B and chain properties.
        # A hard cap silently underreports revenue, so preserve every matching
        # ledger row instead of treating 10,000 as a reporting limit.
        database.folio_charges.find(charge_query, projection).to_list(None),
        database.extra_charges.find(charge_query, projection).to_list(None),
        database.pos_orders.find(
            {
                "tenant_id": tenant_id,
                "status": {"$in": ["closed", "completed", "paid"]},
                **report_period_match(
                    legacy_period("closed_at"), legacy_period("created_at", "closed_at")),
            },
            {"_id": 0, "id": 1, "total_amount": 1, "grand_total": 1, "currency": 1, "business_date": 1, "closed_at": 1, "created_at": 1, "tax_amount": 1, "vat_amount": 1, "tax_breakdown": 1, "discount_amount": 1},
        ).to_list(None),
    )
    # Finalized POS ledger is authoritative; orders are only a legacy fallback.
    # In particular, refunds belong to their own accounting day, never as a
    # cumulative subtraction from the original order's historical sales day.
    transaction_query = {"tenant_id": tenant_id,
        "status": {"$in": ["completed", "closed", "paid", "refunded", "refund"]},
        **report_period_match(
            legacy_period("transaction_date"), legacy_period("created_at", "transaction_date"))}
    transaction_sources = await asyncio.gather(
        database.pos_transactions.find(transaction_query, {"_id": 0}).to_list(None),
        database.pos_menu_transactions.find(transaction_query, {"_id": 0}).to_list(None),
        database.transactions.find({**transaction_query, "$and": [{"$or": [{"category": "pos"}, {"_closure_source": "pos_menu_transactions"}]}]}, {"_id": 0}).to_list(None),
    )
    # The POS report enriches older refunds from their source sale. Share that
    # read-only reconstruction so net revenue excludes the refunded tip too.
    from domains.pms.pos_fnb.reporting import enrich_refunds

    transaction_sources[0], _ = await enrich_refunds(database, tenant_id, transaction_sources[0])
    represented_pos_ids = {str(row["source_pos_order_id"]) for row in [*folio_rows, *extra_rows] if row.get("source_pos_order_id")}
    settled_ids, seen_transaction_ids, order_source = set(), set(), {}
    transaction_rows = []
    order_currencies = {str(row.get("id")): row.get("currency") for row in pos_rows}
    for transactions in transaction_sources:
        for row in transactions:
            if row.get("order_id") and row.get("currency"):
                order_currencies[str(row["order_id"])] = row["currency"]
    unresolved = {str(row["order_id"]) for transactions in transaction_sources for row in transactions
        if row.get("order_id") and not row.get("currency") and not order_currencies.get(str(row["order_id"]))}
    if unresolved:
        # A refund may be inside this report while its original sale is not.
        # Recover currency from the tenant-scoped source order, not from today
        # or a different currency's sales on the selected day.
        source_orders = await database.pos_orders.find({"tenant_id": tenant_id, "id": {"$in": sorted(unresolved)}}, {"_id": 0, "id": 1, "currency": 1}).to_list(None)
        order_currencies.update({str(row["id"]): row.get("currency") for row in source_orders})
    for source_index, transactions in enumerate(transaction_sources):
        for row in transactions:
            transaction_id = str(row.get("id") or row.get("transaction_id") or "")
            order_id = str(row.get("order_id") or "")
            if order_id:
                settled_ids.add(order_id)
                if order_source.setdefault(order_id, source_index) != source_index:
                    continue
            if transaction_id and transaction_id in seen_transaction_ids:
                continue
            if transaction_id:
                seen_transaction_ids.add(transaction_id)
            # Room transfers are already revenue in the folio ledger. Do not
            # reintroduce an asynchronously reversed/voided charge as cash POS.
            if order_id in represented_pos_ids or row.get("payment_method") == "room_charge":
                continue
            value = row.get("total_amount") if row.get("total_amount") is not None else row.get("amount", 0)
            gross = float(value or 0)
            tip = float(row.get("tip_amount") or 0)
            value = gross - tip
            if row.get("payment_type") == "refund" or row.get("status") in {"refunded", "refund"}:
                value = -(abs(gross) - abs(tip))
            transaction_rows.append({"id": transaction_id, "category": "fnb", "total": value,
                # A POS tax_amount is aggregate tax, unlike legacy folio's
                # accommodation-only field. Keep provenance explicit.
                "report_tax_kind": "aggregate", "tax_amount": row.get("tax_amount"),
                "vat_amount": row.get("vat_amount"), "tax_breakdown": row.get("tax_breakdown"),
                "discount_amount": row.get("discount_amount"),
                "report_refund": value < 0, "source_pos_order_id": order_id,
                '_pos_transaction': row,
                "currency": row.get("currency") or order_currencies.get(order_id),
                "business_date": row.get("business_date") or row.get("transaction_date"), "date": row.get("created_at")})
    direct_pos_rows = [
        {
            "id": row.get("id"),
            "category": "fnb",
            "total": row.get("grand_total") if row.get("grand_total") is not None else row.get("total_amount", 0),
            "currency": row.get("currency"),
            "business_date": row.get("business_date"),
            "date": row.get("closed_at") or row.get("created_at"),
            "report_tax_kind": "aggregate", "tax_amount": row.get("tax_amount"),
            "vat_amount": row.get("vat_amount"), "tax_breakdown": row.get("tax_breakdown"),
            "discount_amount": row.get("discount_amount"),
        }
        for row in pos_rows
        if str(row.get("id") or "") not in represented_pos_ids | settled_ids
    ]
    result = await resolve_ledger_currencies([
        *({**row, "report_source": "folio"} for row in folio_rows if is_revenue_charge(row)),
        *({**row, "report_source": "extra"} for row in extra_rows if is_revenue_charge(row)),
        *({**row, "report_source": "pos"} for row in [*transaction_rows, *direct_pos_rows]),
    ], tenant_id, database=database, fallback_currency=fallback_currency)
    # Repair the VIEW, never the historical ledger. An old single aggregate
    # folio row can be split only when its exact sale snapshot proves both
    # gross and tax. Conflicting/unknown evidence remains visibly unreconciled.
    from domains.pms.pos_fnb.folio_lines import checkout_lines
    from domains.pms.pos_fnb.reporting import is_refund

    ids = [row['source_pos_order_id'] for row in result if row.get('report_source') == 'folio'
           and row.get('source_pos_order_id') and row.get('pos_financial_version') != 2]
    originals = await database.pos_transactions.find({'tenant_id': tenant_id, 'order_id': {'$in': ids},
        'status': 'completed', 'payment_method': 'room_charge'}, {'_id': 0}).to_list(None) if ids else []
    by_order = {row['order_id']: row for row in originals}
    counts = {}
    for row in result:
        if row.get('report_source') == 'folio' and row.get('source_pos_order_id'):
            key = row['source_pos_order_id']
            counts[key] = counts.get(key, 0) + 1
    normalized = []
    for row in result:
        txn = row.pop('_pos_transaction', None)
        ratio = 1
        if row.get('report_source') == 'folio' and row.get('pos_financial_version') != 2:
            txn = by_order.get(row.get('source_pos_order_id'))
            if txn and (counts[row['source_pos_order_id']] != 1 or money(txn.get('amount')) != money(row.get('total'))
                    or money(txn.get('tax_amount')) != money(row.get('tax_amount'))
                    or txn.get('currency') != row.get('currency')):
                txn = None
        elif txn and is_refund(txn):
            original = txn.get('source_sale')
            if original and money(original.get('total_amount')):
                ratio = -abs(money(txn.get('total_amount'))) / money(original['total_amount'])
                txn = original
            else:
                txn = None
        if not txn or txn.get('tax_amount') is None or not (txn.get('order_items') or txn.get('items')):
            normalized.append(row)
            continue
        try:
            lines = checkout_lines(txn)
        except Exception:
            # A malformed snapshot is not permission to guess a tax/category.
            normalized.append(row)
            continue
        # Round cumulatively so a virtual partial refund conserves its exact
        # posted cents. Never create an off-by-cent report-only financial row.
        from domains.pms.pos_fnb.folio_lines import allocate
        totals = allocate(abs(money(row['total'])), [line['total'] for line in lines])
        taxes = allocate(abs(money(row.get('tax_amount'))), [line['vat_amount'] for line in lines])
        for index, (line, total, tax) in enumerate(zip(lines, totals, taxes)):
            sign = -1 if ratio < 0 else 1
            vat = sign * tax
            discount = rounded(money(line['discount_amount']) * ratio)
            value = sign * total
            net = rounded(money(value) - money(vat))
            normalized.append({**row, 'id': f"{row.get('id')}:pos-line:{index}",
                'charge_category': line['charge_category'], 'category': line['charge_category'],
                'amount': net, 'subtotal': rounded(money(net) + money(discount)), 'discount_amount': discount,
                'vat_amount': vat, 'tax_amount': 0, 'tax_breakdown': {'vat': vat}, 'total': value,
                'report_normalized_from': row.get('id'), 'report_normalization': 'verified_pos_snapshot'})
    return normalized
