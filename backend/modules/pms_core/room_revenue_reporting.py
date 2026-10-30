"""Operational room KPIs: preserve posted zeroes and accrue only missing day/currency buckets."""

from modules.pms_core.report_money import add_amount, currency_code, money, rounded, rounded_totals, single_amount


def room_adr_by_currency(revenue, metric_rows):
    """Posted and accrued reports share the same currency-specific denominator.

    Older report fixtures/consumers without a currency partition retain their
    declared sold-room denominator; canonical metrics always carry partitions.
    """
    counts = {code: sum(int(row["sold_rooms_by_currency"].get(code, 0))
        if row.get("sold_rooms_by_currency") is not None else int(row.get("sold_rooms", row.get("occupied_rooms")) or 0)
        for row in metric_rows) for code in revenue}
    return {code: rounded(money(amount) / counts[code]) if counts[code] else 0 for code, amount in revenue.items()}


def reconcile_room_revenue(posted, accrued, occupied):
    """Presence, not a nonzero sum, proves a room posting exists."""
    totals, sources = {}, {}
    for code in posted.keys() | accrued.keys():
        use_accrual = code not in posted and occupied > 0 and money(accrued.get(code, 0)) != 0
        totals[code] = money(accrued.get(code, 0) if use_accrual else posted.get(code, 0))
        sources[code] = "accrued" if use_accrual else "posted"
    return totals, sources


def room_period_performance(metric_rows, posted_by_day_currency, *, fallback_currency="TRY"):
    occupied = sum(int(row.get("occupied_rooms") or 0) for row in metric_rows)
    sold = sum(int(row.get("sold_rooms", row.get("occupied_rooms")) or 0) for row in metric_rows)
    capacity = sum(int(row.get("total_rooms") or 0) for row in metric_rows)
    rooms, posted_total, accrued_total, sources_by_day, gaps, sold_by_currency = {}, {}, {}, {}, [], {}
    for row in metric_rows:
        day = str(row.get("date"))
        posted = posted_by_day_currency.get(day, {})
        accrued = row.get("revenue_by_currency")
        if accrued is None:
            accrued = {currency_code(row.get("currency"), fallback_currency): row.get("revenue") or 0}
        selected, sources = reconcile_room_revenue(posted, accrued, int(row.get("occupied_rooms") or 0))
        currency_counts = row.get("sold_rooms_by_currency")
        for code in selected:
            count = currency_counts.get(code, 0) if currency_counts is not None else int(row.get("sold_rooms", row.get("occupied_rooms")) or 0)
            sold_by_currency[code] = sold_by_currency.get(code, 0) + count
        sources_by_day[day] = sources
        if "accrued" in sources.values():
            gaps.append(day)
        for target, amounts in ((rooms, selected), (posted_total, posted), (accrued_total, accrued)):
            for code, amount in amounts.items():
                add_amount(target, code, amount)
    kinds = {kind for sources in sources_by_day.values() for kind in sources.values()}
    for totals in (rooms, posted_total, accrued_total):
        if not totals:
            totals[currency_code(fallback_currency)] = 0
    result = {
        "start_date": str(metric_rows[0].get("date")) if metric_rows else None,
        "end_date": str(metric_rows[-1].get("date")) if metric_rows else None,
        "occupied_room_nights": occupied,
        "sold_room_nights": sold,
        "sold_room_nights_by_currency": sold_by_currency,
        "available_room_nights": capacity,
        "occupancy_percentage": rounded(money(occupied) / capacity * 100) if capacity else 0,
        "revenue_source": "mixed" if len(kinds) > 1 else next(iter(kinds), "posted"),
        "revenue_source_by_day_currency": sources_by_day,
        "posting_gap_days": gaps,
    }
    for key, totals in {
        "room_revenue": rooms,
        "posted_room_revenue": posted_total,
        "accrued_room_revenue": accrued_total,
        "adr": {code: rounded(money(value) / sold_by_currency[code]) if sold_by_currency.get(code) else 0 for code, value in rooms.items()},
        "revpar": {code: rounded(money(value) / capacity) if capacity else 0 for code, value in rooms.items()},
    }.items():
        result[key] = single_amount(totals)
        result[key + "_by_currency"] = rounded_totals(totals)
    return result
