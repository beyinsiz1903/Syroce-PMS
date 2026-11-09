"""Explicit PMSConnect 1.17.1 placements (pp. 35-43, 48-49).

Adult main-bed amounts are room totals, child/extra-bed amounts are per guest.
PMS inclusive child ages are converted to Exely's exclusive upper boundary.
Never infer a main-bed/extra-bed tariff from the PMS child surcharge policy.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

KINDS = {"adult_main", "child_main", "adult_extra", "child_extra", "child_without_bed"}


def money(value):
    if isinstance(value, bool) or value is None or value == "":
        raise ValueError("Yerleşim fiyatı geçersiz")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Yerleşim fiyatı geçersiz") from exc
    if not result.is_finite() or not 0 <= result <= Decimal("1e12"):
        raise ValueError("Yerleşim fiyatı negatif, sonsuz veya çok büyük olamaz")
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def normalize_placements(rows, base_guests):
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError("En fazla 100 Exely yerleşim tarifesi tanımlanabilir")
    result, seen, bands = [], set(), {}
    for row in rows:
        if not isinstance(row, dict) or row.get("kind") not in KINDS:
            raise ValueError("Exely yerleşim türü geçersiz")
        kind = row["kind"]
        mode = row.get("price_mode")
        if mode not in {"fixed", "percentage"}:
            raise ValueError("Yerleşim fiyat yöntemi geçersiz")
        amount = money(row.get("value"))
        item = {"kind": kind, "price_mode": mode, "value": float(amount)}
        key = (kind,)
        if kind == "adult_main":
            count = row.get("number_of_guests")
            if type(count) is not int or not 1 <= count <= 20 or count == base_guests or amount == 0:
                raise ValueError("Ana yatak yetişkin sayısı 1–20 olmalı; taban yerleşimi tekrar eklenemez ve yetişkin fiyatı sıfır olamaz")
            item["number_of_guests"] = count
            key += (count,)
        elif kind.startswith("child_"):
            low, high = row.get("min_age"), row.get("max_age")
            if type(low) is not int or type(high) is not int or not 0 <= low <= high <= 17:
                raise ValueError("Çocuk yaş aralığı 0–17 olmalıdır (iki sınır da dahil)")
            if any(low <= old_high and high >= old_low for old_low, old_high in bands.get(kind, [])):
                raise ValueError("Aynı yerleşim türünde çocuk yaş aralıkları çakışamaz")
            bands.setdefault(kind, []).append((low, high))
            item.update(min_age=low, max_age=high)
            key += (low, high)
        if key in seen:
            raise ValueError("Aynı Exely yerleşim tarifesi tekrar eklenemez")
        seen.add(key)
        result.append(item)
    return sorted(result, key=lambda item: (item["kind"], item.get("number_of_guests", 0), item.get("min_age", -1)))


def compile_guest_prices(rule, base_rate, currency):
    count = rule["base_occupancy"]
    base = money(base_rate)
    if base <= 0:
        raise ValueError("Taban oda fiyatı sıfırdan büyük olmalıdır")
    result = [{"kind": "adult_main", "number_of_guests": count, "amount": float(base)}]
    if rule.get("pricing_type") != "per_person":
        return result
    rows = normalize_placements(rule.get("exely_price_placements", []), count)
    if not rows:
        return result  # Legacy attested base-only clients remain compatible.
    if rule.get("exely_placements_reviewed") is not True:
        raise ValueError("Exely ana/ek yatak kapasitesi ve çocuk yaş aralıklarını kontrol edip yerleşim tarifelerini kaydedin")
    if any(row["price_mode"] == "fixed" for row in rows) and rule.get("currency") != currency:
        raise ValueError("Exely yerleşim tarifelerinin para birimi bağlantı para birimiyle eşleşmiyor; tarifeleri yeniden kaydedin")
    for row in rows:
        amount = money(row["value"]) if row["price_mode"] == "fixed" else money(base * Decimal(str(row["value"])) / 100)
        if row["kind"] == "adult_main" and amount <= 0:
            raise ValueError("Yetişkin ana yatak fiyatı sıfır olamaz")
        price = {"kind": row["kind"], "amount": float(amount)}
        if row["kind"] == "adult_main":
            price["number_of_guests"] = row["number_of_guests"]
        elif row["kind"].startswith("child_"):
            price.update(min_age=row["min_age"], max_age=row["max_age"] + 1)
        result.append(price)
    return sorted(result, key=lambda item: (item["kind"], item.get("number_of_guests", 0), item.get("min_age", -1)))


def validate_guest_prices(prices, *, require_adult=True):
    """Strict wire payload validation, also used before acquiring/send of ARI."""
    if not isinstance(prices, list) or not 1 <= len(prices) <= 101:
        raise ValueError("Exely yerleşim fiyat listesi geçersiz")
    seen, bands = set(), {}
    adult_main = False
    for price in prices:
        if not isinstance(price, dict) or price.get("kind") not in KINDS:
            raise ValueError("Exely yerleşim türü geçersiz")
        kind = price["kind"]
        amount = money(price.get("amount"))
        allowed = {"kind", "amount"}
        key = (kind,)
        if kind == "adult_main":
            count = price.get("number_of_guests")
            if type(count) is not int or not 1 <= count <= 20 or amount <= 0:
                raise ValueError("Exely yetişkin yerleşimi geçersiz")
            allowed.add("number_of_guests")
            key += (count,)
            adult_main = True
        elif kind.startswith("child_"):
            low, high = price.get("min_age"), price.get("max_age")
            if type(low) is not int or type(high) is not int or not 0 <= low < high <= 18:
                raise ValueError("Exely çocuk yaş sınırları geçersiz")
            if any(low < old_high and high > old_low for old_low, old_high in bands.get(kind, [])):
                raise ValueError("Exely çocuk yaşları çakışıyor")
            bands.setdefault(kind, []).append((low, high))
            allowed.update({"min_age", "max_age"})
            key += (low, high)
        if set(price) != allowed or key in seen:
            raise ValueError("Exely yerleşim fiyatında beklenmeyen veya yinelenen alan")
        seen.add(key)
    if require_adult and not adult_main:
        raise ValueError("Exely yetişkin ana yatak fiyatı gerekli")


def validate_placement_inventory(prices, connection, *room_codes):
    """Known discovery constraints win over a stale/manual attestation."""
    inventories = [room for room in connection.get("room_types", []) if str(room.get("code")) in set(room_codes)]
    for inventory in inventories:
        for price in prices:
            if price["kind"] == "adult_main" and "main_occupancy_max" in inventory:
                if not inventory.get("main_occupancy_min", 1) <= price["number_of_guests"] <= inventory["main_occupancy_max"]:
                    raise ValueError("Yetişkin ana yatak yerleşimi Exely oda kapasitesiyle eşleşmiyor")
            if price["kind"].startswith("child_") and inventory.get("child_age_ranges"):
                if {"min_age": price["min_age"], "max_age": price["max_age"]} not in inventory["child_age_ranges"]:
                    raise ValueError("Çocuk yaş aralığı Exely envanterindeki yaş sınırlarıyla eşleşmiyor")
