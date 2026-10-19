"""Read-only no-show reporting contracts shared by legacy and risk screens.

Booked reference value is NOT a penalty, collection or realised loss. Arrival
cohorts and event-day cohorts are deliberately labelled, not silently mixed.
"""

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from common.legacy_data_normalization import normalize_dimension_label, parse_utc_datetime
from modules.pms_core.report_money import add_amount, currency_code, rounded_totals, single_amount
from modules.pms_core.reporting_dates import date_period_match
from modules.pms_core.reservation_reporting import reservation_value
from modules.pms_core.stay_night_metrics import OCCUPYING_STATUSES, as_date

NO_SHOW_STATUSES = frozenset({"no_show", "noshow"})
COHORT_STATUSES = OCCUPYING_STATUSES | NO_SHOW_STATUSES
REFERENCE_BASIS = "gross_booking_value_not_realized_loss_or_penalty_or_collection"


def booking_channel(booking):
    return normalize_dimension_label(booking.get("ota_channel") or booking.get("source_channel") or booking.get("channel") or booking.get("source"))


def is_no_show(booking):
    return str(booking.get("status") or "").strip().lower() in NO_SHOW_STATUSES


async def arrival_cohort(database, tenant_id, first, last):
    rows = await database.bookings.find({"tenant_id": tenant_id, **date_period_match("check_in", first, last),
        "status": {"$in": sorted(COHORT_STATUSES)}}, {"_id": 0}).to_list(None)
    valid = [row for row in rows if (day := as_date(row.get("check_in"))) and first <= day <= last]
    return valid, len(rows) - len(valid)


def reference_values(rows, fallback_currency):
    totals, invalid = {}, 0
    counts = Counter()
    for row in rows:
        value = reservation_value(row)
        if value is None:
            invalid += 1
            continue
        code = currency_code(row.get("currency"), fallback_currency)
        add_amount(totals, code, value)
        counts[code] += 1
    scalar = None if invalid and not totals else single_amount(totals)
    averages = {code: amount / counts[code] for code, amount in totals.items()}
    return {"total_loss": scalar, "loss_by_currency": rounded_totals(totals), "invalid_amounts": invalid,
        "avg_loss": None if invalid and not totals else single_amount(averages), "avg_loss_by_currency": rounded_totals(averages)}


def quality(rows, *, invalid_amounts=0, invalid_dates=0, minimum=5):
    data_days = len({as_date(row.get("check_in")) for row in rows if as_date(row.get("check_in"))})
    confidence = "low" if len(rows) < minimum else "medium" if data_days < 7 else "high"
    return {"confidence": confidence, "confidence_basis": "sample_coverage_not_calibrated_accuracy",
        "note": f"{len(rows)} kayıt / {data_days} olaylı giriş günü; bu bir tahmin doğruluğu veya olasılık ölçümü değildir.",
        "data_points": len(rows), "data_days": data_days, "invalid_amounts": invalid_amounts, "invalid_dates": invalid_dates}


def build_channel_report(bookings, first, last, currency, *, invalid_dates=0):
    no_shows = [row for row in bookings if is_no_show(row)]
    all_counts = Counter(booking_channel(row) for row in bookings)
    by_channel = defaultdict(list)
    for row in no_shows:
        by_channel[booking_channel(row)].append(row)
    channels = []
    for channel, total in sorted(all_counts.items()):
        rows = by_channel[channel]
        channels.append({"channel": channel, "no_show_count": len(rows), "total_bookings": total,
            "no_show_rate": round(len(rows) / total * 100, 1) if total else 0, **reference_values(rows, currency)})
    channels.sort(key=lambda row: (-row["no_show_rate"], -row["no_show_count"], row["channel"]))
    trend = []
    event_counts = Counter((as_date(row.get("check_in")), booking_channel(row)) for row in no_shows)
    trend_channels = sorted(by_channel)
    for offset in range((last - first).days + 1):
        day = first + timedelta(days=offset)
        counts = {channel: event_counts[(day, channel)] for channel in trend_channels}
        # Keep legacy flat keys, except a channel named "date" cannot overwrite
        # the time axis. The nested contract is unambiguous for every label.
        trend.append({**{channel: count for channel, count in counts.items() if channel != "date"},
            "date": day.isoformat(), "counts_by_channel": counts})
    values = reference_values(no_shows, currency)
    return {"channels": channels, "top3_worst": [row for row in channels if row["no_show_count"] > 0][:3],
        "trend": trend, "trend_channels": trend_channels, "total_no_shows": len(no_shows),
        "total_loss": values["total_loss"], "loss_by_currency": values["loss_by_currency"], "currency": currency,
        "start_date": first.isoformat(), "end_date": last.isoformat(), "period_days": (last - first).days + 1,
        "basis": "arrival_cohort_" + REFERENCE_BASIS, "data_quality": quality(no_shows, invalid_amounts=values["invalid_amounts"], invalid_dates=invalid_dates)}


def build_heatmap_report(bookings, first, last, currency, *, invalid_dates=0):
    no_shows = [row for row in bookings if is_no_show(row)]
    overbookings = [row for row in no_shows if row.get("no_show_reason") == "overbooking"]
    by_day, ob_by_day = defaultdict(list), defaultdict(list)
    for row in no_shows:
        by_day[as_date(row.get("check_in"))].append(row)
    for row in overbookings:
        ob_by_day[as_date(row.get("check_in"))].append(row)
    heatmap = []
    weekdays = [{"overbooking": 0, "noshow": 0, "days": 0} for _ in range(7)]
    for offset in range((last - first).days + 1):
        day = first + timedelta(days=offset)
        rows, obs = by_day[day], ob_by_day[day]
        values = reference_values(obs, currency)
        heatmap.append({"date": day.isoformat(), "overbooking_count": len(obs), "total_noshow": len(rows),
            "loss": values["total_loss"], "loss_by_currency": values["loss_by_currency"],
            "noshow_value_by_currency": reference_values(rows, currency)["loss_by_currency"],
            "invalid_amounts": values["invalid_amounts"], "channel_breakdown": dict(Counter(booking_channel(row) for row in obs))})
        weekday = weekdays[day.weekday()]
        weekday["days"] += 1
        weekday["overbooking"] += len(obs)
        weekday["noshow"] += len(rows)
    names = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    weekly = [{"day_index": day, "day_name": names[day], "overbooking_total": row["overbooking"], "noshow_total": row["noshow"],
        "avg_overbooking": round(row["overbooking"] / row["days"], 2) if row["days"] else 0,
        "avg_noshow": round(row["noshow"] / row["days"], 2) if row["days"] else 0, "is_weekend": day >= 5} for day, row in enumerate(weekdays)]
    values = reference_values(overbookings, currency)
    all_values = reference_values(no_shows, currency)
    return {"heatmap": heatmap, "peak_days": sorted([row for row in heatmap if row["overbooking_count"] > 0], key=lambda row: (-row["overbooking_count"], row["date"]))[:5],
        "weekly_pattern": weekly, "channel_overlay": [{"channel": channel, "count": count} for channel, count in Counter(booking_channel(row) for row in overbookings).most_common()],
        "total_overbookings": len(overbookings), "total_no_shows": len(no_shows), "total_loss": values["total_loss"], "loss_by_currency": values["loss_by_currency"],
        "noshow_value_by_currency": all_values["loss_by_currency"], "currency": currency,
        "start_date": first.isoformat(), "end_date": last.isoformat(), "period_days": (last - first).days + 1,
        "basis": "arrival_cohort_overbooking_" + REFERENCE_BASIS,
        "data_quality": quality(overbookings, invalid_amounts=all_values["invalid_amounts"], invalid_dates=invalid_dates, minimum=3)}


def build_event_report(bookings, first, last, currency, reason_labels):
    from core.guest_name_utils import display_guest_name

    daily, reasons = Counter(), Counter()
    rooms, channels = defaultdict(list), defaultdict(list)
    for row in bookings:
        day = as_date(row.get("no_show_at"))
        if day:
            daily[day.isoformat()] += 1
        rooms[normalize_dimension_label(row.get("room_type"), default="Bilinmiyor")].append(row)
        channels[booking_channel(row)].append(row)
        reasons[normalize_dimension_label(row.get("no_show_reason"), default="belirtilmemis")] += 1
    def breakdown(groups, key):
        result = []
        for name, rows in groups.items():
            values = reference_values(rows, currency)
            result.append({key: name, "count": len(rows), "revenue_loss": values["total_loss"], "loss_by_currency": values["loss_by_currency"], "invalid_amounts": values["invalid_amounts"]})
        return sorted(result, key=lambda row: (-row["count"], row[key]))
    recent = sorted(bookings, key=lambda row: parse_utc_datetime(row.get("no_show_at")) or datetime.combine(as_date(row.get("no_show_at")), datetime.min.time(), UTC), reverse=True)[:10]
    details = [{"id": row.get("id"), "guest_name": display_guest_name(row.get("guest_name"), row.get("guest_id")),
        "room_type": normalize_dimension_label(row.get("room_type"), default="-"), "channel": booking_channel(row),
        "reason": normalize_dimension_label(row.get("no_show_reason"), default="belirtilmemis"),
        "reason_label": reason_labels.get(row.get("no_show_reason"), "Belirtilmemiş") if isinstance(row.get("no_show_reason"), str) else "Belirtilmemiş",
        "amount": float(reservation_value(row)) if reservation_value(row) is not None else None,
        "currency": currency_code(row.get("currency"), currency), "date": as_date(row.get("no_show_at")).isoformat()} for row in recent]
    values = reference_values(bookings, currency)
    return {"total_no_shows": len(bookings), "total_revenue_loss": values["total_loss"], "loss_by_currency": values["loss_by_currency"],
        "currency": currency, "period_days": (last - first).days + 1, "start_date": first.isoformat(), "end_date": last.isoformat(),
        "basis": "no_show_event_day_" + REFERENCE_BASIS, "daily": [{"date": day, "count": count} for day, count in sorted(daily.items())],
        "by_room_type": breakdown(rooms, "room_type"), "by_channel": breakdown(channels, "channel"),
        "by_reason": [{"reason": reason, "label": reason_labels.get(reason, reason), "count": count} for reason, count in reasons.most_common()],
        "recent": details, "data_quality": {"invalid_amounts": values["invalid_amounts"]}}
