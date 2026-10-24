"""PII-free operational forecast. Commitments, not statistical predictions.

Booked nights and unpicked definite group allotments are disjoint. Closed
physical rooms are not group allotments. No FX conversion, payments or fiscal
revenue is inferred from reservation prices.
"""
from decimal import Decimal

from modules.pms_core.occupancy_calendar import occupancy_calendar
from modules.pms_core.report_money import add_amount, currency_code, money, rounded, rounded_totals
from modules.pms_core.stay_night_metrics import OCCUPYING_STATUSES, allocated_revenue_for_night, as_date, booking_occupies_night, is_physical_room


def _count(value):
    try:
        number = int(value)
        return number if not isinstance(value, bool) and number >= 0 and number == float(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _night(booking, day, business_day):
    return booking_occupies_night(booking, day, actual_only=day < business_day or booking.get("status") == "checked_out")


def _kind(booking, active, by_number):
    rid = str(booking.get("room_id") or by_number.get(str(booking.get("room_number")), ""))
    return active[rid].get("room_type") if rid in active else booking.get("room_type")


def _group_units(block, room_type):
    total = _count(block.get("total_rooms", block.get("rooms_blocked")))
    if total is None:
        return None
    if not room_type:
        return total
    breakdown = block.get("room_breakdown") or {}
    if breakdown:
        if not isinstance(breakdown, dict) or any(_count(value) is None for value in breakdown.values()):
            return None
        if sum(int(value) for value in breakdown.values()) != total:
            return None
        return int(breakdown.get(room_type, 0))
    return total if block.get("room_type") == room_type else 0 if block.get("room_type") else None


def frontdesk_forecast(rooms, bookings, closed_blocks, groups, daily_rates, first, last, business_day, *, room_type=None, fallback_currency="TRY"):
    bookings = list({str(row["id"]): {**row, "check_in": row.get("check_in") or row.get("check_in_date"),
        "check_out": row.get("check_out") or row.get("check_out_date")} for row in bookings if row.get("id")}.values())
    active = {str(row["id"]): row for row in rooms if row.get("id") and is_physical_room(row)}
    by_number = {str(row["room_number"]): rid for rid, row in active.items() if row.get("room_number")}
    types = {str(row["room_type"]) for row in active.values() if row.get("room_type")}
    nights = [row for row in bookings if row.get("booking_type") != "day_use"]
    groups = list({str(row.get('id') or row.get('_id') or index): row for index, row in enumerate(groups)}.values())
    calendar = occupancy_calendar(rooms, nights, closed_blocks, first, last, business_day, room_type)
    selected = [row for row in bookings if not room_type or _kind(row, active, by_number) == room_type]
    rates = {}
    for rate in daily_rates:
        key = (str(rate.get("booking_id")), str(rate.get("date"))[:10])
        rates.setdefault(key, []).append(rate)
    rows, warnings = [], set()
    for item in calendar["rows"]:
        day = as_date(item["date"])
        actual = day < business_day
        def inventory_known(row):
            rid = str(row.get("room_id") or by_number.get(str(row.get("room_number")), ""))
            return rid in active or (not actual and not rid and row.get("room_type") in types)

        nightly = [row for row in selected if row.get("booking_type") != "day_use" and _night(row, day, business_day)
                   and inventory_known(row)]
        commitments = item["actual_rooms"] if actual else item["expected_rooms"]
        picked_by_group = {}
        for booking in nightly:
            linked = {str(booking.get(key)) for key in ("group_block_id", "group_id", "group_booking_id") if booking.get(key)}
            if booking.get("block_id"):
                linked.add(f"block:{booking['block_id']}")
            for gid in linked:
                picked_by_group[gid] = picked_by_group.get(gid, 0) + 1
        unpicked = tentative = unallocated_groups = 0
        for group in groups:
            ci, co = as_date(group.get("check_in")), as_date(group.get("check_out"))
            if not ci or not co or not ci <= day < co or actual:
                continue
            status = str(group.get("status") or "").strip().lower()
            if status not in {"definite", "confirmed", "active", "tentative"}:
                continue
            units = _group_units(group, room_type)
            if units is None:
                unallocated_groups += 1
                warnings.add("Oda tipi / miktarı doğrulanamayan grup blokları var; belirsiz bloklar tahminle dağıtılmadı.")
                continue
            gid = str(group.get("id") or group.get("_id") or "")
            if not gid:
                unallocated_groups += 1
                warnings.add("Kimliği doğrulanamayan grup bloğunun pickup hesabı yapılamadı; miktar tahmin edilmedi.")
                continue
            # Recompute pickup on each NIGHT. A stored lifetime pickup counter
            # cannot establish how many rooms were picked on this particular day.
            picked = picked_by_group.get(gid, 0)
            remaining = max(0, units - picked)
            if picked > units:
                warnings.add("Bazı gruplarda gece bazlı pickup blok miktarını aşıyor; fazla taahhüt gizlenmedi.")
            if status == "tentative":
                tentative += remaining
            else:
                unpicked += remaining
        revenue, paid_counts, missing_prices, price_sources = {}, {}, 0, set()
        comp = house = 0
        adults = children = babies = unknown_ages = 0
        missing_people = 0
        for booking in nightly:
            choices = rates.get((str(booking["id"]), day.isoformat()), [])
            night_comp = bool(booking.get("is_complimentary")) or (len(choices) == 1 and bool(choices[0].get("is_complimentary")))
            comp += int(night_comp)
            house += int(bool(booking.get("is_house_use")) or booking.get("booking_type") == "house_use")
            adult_count, child_count = _count(booking.get("adults")), _count(booking.get("children"))
            if adult_count is None or child_count is None:
                missing_people += 1
            adults += adult_count or 0
            child_count = child_count or 0
            ages = booking.get("children_ages") or []
            if not isinstance(ages, (list, tuple)):
                ages = []
            ages = [age for age in ages if isinstance(age, int) and not isinstance(age, bool) and 0 <= age <= 17]
            if len(ages) > child_count:
                warnings.add("Çocuk sayısı ve yaş listesi uyuşmayan rezervasyon var; yaş kırılımı eksik gösterildi.")
                ages = []
            infant_count = sum(age <= 2 for age in ages)
            babies += infant_count
            children += child_count - infant_count
            unknown_ages += max(0, child_count - len(ages))
            code = currency_code(booking.get("currency"), fallback_currency)
            try:
                if len(code) != 3 or not code.isascii() or not code.isalpha():
                    raise ValueError("Unknown reservation currency")
                if len(choices) > 1:
                    raise ValueError("Ambiguous daily price")
                if choices:
                    rate = choices[0]
                    if rate.get("currency") and currency_code(rate["currency"]) != code:
                        raise ValueError("Daily price currency mismatch")
                    amount = Decimal(0) if night_comp else money(rate["rate"])
                    price_sources.add("daily_rate")
                else:
                    if booking.get("total_amount") is None:
                        raise ValueError("Missing stay price")
                    money(booking["total_amount"])
                    amount = allocated_revenue_for_night(booking, day)
                    price_sources.add("stay_total_allocation")
                if amount < 0:
                    raise ValueError("Negative room price")
                add_amount(revenue, code, amount)
                if amount > 0:
                    paid_counts[code] = paid_counts.get(code, 0) + 1
            except (ValueError, ArithmeticError, TypeError, KeyError):
                missing_prices += 1
        if missing_prices:
            warnings.add("Eksik / çakışan günlük fiyat var. Gelir ve ADR eksik toplamla gösterilmedi.")
        if unknown_ages or missing_people:
            warnings.add("Kişi sayısı / çocuk yaşı eksik kayıtlar var; bebek yaşı 0–2 olarak ayrılır, bilinmeyen bebek sayısı sıfır varsayılmaz.")
        sold = commitments + unpicked
        physical, sellable = item["physical_rooms"], item["available_rooms"]
        remaining = sellable - sold
        inventory_incomplete = bool(unallocated_groups or item["unknown_room_references"])
        revenue_incomplete = bool(missing_prices or item["unknown_room_references"])
        valid_movements = [row for row in selected if inventory_known(row) and str(row.get("status") or "").lower() in OCCUPYING_STATUSES
                           and row.get("booking_type") != "day_use"]
        arrivals = sum(as_date(row.get("check_in")) == day and _night(row, day, business_day) for row in valid_movements)
        departures = 0
        for booking in valid_movements:
            departure = None
            if booking.get("status") == "checked_out":
                departure = as_date(booking.get("checked_out_business_date"))
                wall_day = as_date(booking.get("checked_out_at"))
                ci, co = as_date(booking.get("check_in")), as_date(booking.get("check_out"))
                if not departure and wall_day and ci and co and ci <= wall_day <= co:
                    departure = wall_day
                elif not departure and wall_day:
                    warnings.add("İş günü kaydı olmayan eski çıkışlarda, konaklama dışındaki işlem saati yerine planlı çıkış tarihi kullanıldı.")
            departure = departure or as_date(booking.get("check_out"))
            if departure == day and (not actual or booking.get("status") in {"checked_in", "in_house", "checked_out"}):
                departures += 1
        day_use = sum(as_date(row.get("check_in")) == day and row.get("booking_type") == "day_use"
                      and inventory_known(row)
                      and str(row.get("status") or "").lower() in OCCUPYING_STATUSES
                      and (not actual or row.get("status") in {"checked_in", "in_house", "checked_out"}) for row in selected)
        if any(item.get(key) for key in ("assignment_conflicts", "unknown_room_references", "occupied_blocked_rooms")):
            warnings.add("Oda atama / kapalı oda çakışması var. Gerçekleşen odalar fiziksel tekil, rezervasyon taahhütleri ayrı sayılır; tutarsızlıklar düzeltilmelidir.")
        rows.append({**item, "basis": "actual" if actual else "on_the_books", "booked_rooms": commitments,
            "block_rooms": unpicked, "tentative_block_rooms": tentative, "total_occupied_rooms": None if inventory_incomplete else sold,
            "known_occupied_rooms": sold, "inventory_incomplete": inventory_incomplete,
            "remaining_rooms": None if inventory_incomplete else remaining, "vacant_rooms": None if inventory_incomplete else max(0, remaining), "overbooked_rooms": max(0, -remaining),
            "occupancy_pct": rounded(money(sold) * 100 / physical) if physical and not inventory_incomplete else None,
            "sellable_occupancy_pct": rounded(money(sold) * 100 / sellable) if sellable and not inventory_incomplete else None,
            "arrivals": arrivals, "departures": departures, "stayovers": max(0, len(nightly) - arrivals),
            "adults": None if missing_people else adults, "children": None if missing_people else children,
            "infants": None if missing_people or unknown_ages else babies, "unknown_child_ages": unknown_ages,
            "comp_rooms": comp, "house_use_rooms": house, "day_use_rooms": day_use,
            "group_rooms": sum(any(row.get(key) for key in ("group_block_id", "group_id", "group_booking_id", "block_id")) for row in nightly),
            "room_revenue_by_currency": None if revenue_incomplete else rounded_totals(revenue),
            "adr_by_currency": None if revenue_incomplete else {code: rounded(money(amount) / paid_counts[code]) if paid_counts.get(code) else 0 for code, amount in revenue.items()},
            "revenue_incomplete": revenue_incomplete,
            "paid_rooms_by_currency": paid_counts, "price_sources": sorted(price_sources), "missing_prices": missing_prices,
            "unallocated_group_blocks": unallocated_groups})
    physical = sum(row["physical_rooms"] for row in rows)
    sellable = sum(row["available_rooms"] for row in rows)
    sold = sum(row["known_occupied_rooms"] for row in rows)
    inventory_incomplete = any(row["inventory_incomplete"] for row in rows)
    revenues, denominators = {}, {}
    for row in rows:
        for code, amount in (row["room_revenue_by_currency"] or {}).items():
            add_amount(revenues, code, amount)
        for code, count in row["paid_rooms_by_currency"].items():
            denominators[code] = denominators.get(code, 0) + count
    missing = any(row["revenue_incomplete"] for row in rows)
    totals = {"occupied_room_nights": None if inventory_incomplete else sold, "known_occupied_room_nights": sold,
        "inventory_incomplete": inventory_incomplete, "booked_room_nights": sum(row["booked_rooms"] for row in rows),
        "block_room_nights": sum(row["block_rooms"] for row in rows), "physical_room_nights": physical, "sellable_room_nights": sellable,
        "occupancy_pct": rounded(money(sold) * 100 / physical) if physical and not inventory_incomplete else None,
        "sellable_occupancy_pct": rounded(money(sold) * 100 / sellable) if sellable and not inventory_incomplete else None,
        "room_revenue_by_currency": None if missing else rounded_totals(revenues),
        "adr_by_currency": None if missing else {code: rounded(money(amount) / denominators[code]) if denominators.get(code) else 0 for code, amount in revenues.items()}}
    return {"start_date": first.isoformat(), "end_date": last.isoformat(), "business_date": business_day.isoformat(),
        "room_type": room_type, "room_types": sorted(types), "rows": rows, "totals": totals, "currency": fallback_currency,
        "warnings": sorted(warnings), "definitions": {
            "occupancy": "Dolu rezervasyon + henüz pickup yapılmamış kesin grup bloğu / fiziksel oda kapasitesi. Kapalı odalar paydada kalır.",
            "availability": "Satılabilir kapasite − dolu rezervasyon − kalan kesin grup bloğu. Negatif kalan fazla satıştır. Opsiyon blokları kapasite tüketmez.",
            "revenue": "Rezervasyon oda bedeli: günlük fiyat varsa o fiyat, yoksa konaklama toplamının kuruş korumalı gece dağılımı. Tahsilat veya kesinleşmiş muhasebe geliri değildir. Kalan grup bloklarına gelir uydurulmaz.",
            "people": "Çocuk sayısından yaşı bilinen 0–2 bebekler ayrılır; yaşı eksik çocuklar Çocuk sütununda kalır, Bebek değeri bilinmiyor gösterilir.",
            "inventory": "Kapasite güncel aktif fiziksel oda envanteridir; tarihsel envanter fotoğrafı değildir. Day-use gece doluluğuna eklenmez. Comp/House-use rezervasyon işaretlerinden okunur; finansal ikram mahsupları konaklama statüsüne çevrilmez."}}
