"""Pure financial and scheduling contracts for banquet operations."""
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal


def money(value) -> Decimal:
    amount = Decimal(str(0 if value is None else value))
    if not amount.is_finite() or amount < 0:
        raise ValueError("Tutar sonlu ve sıfırdan büyük veya eşit olmalıdır")
    return amount


def rounded(value) -> float:
    return float(money(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value


def overlaps(left, right) -> bool:
    a, b = instant(left["starts_at"]), instant(left["ends_at"])
    c, d = instant(right["starts_at"]), instant(right["ends_at"])
    # Naive legacy entries are venue-local wall times. For mixed legacy rows
    # use the explicit offset of the other record, never the server OS zone.
    zone = a.tzinfo or b.tzinfo or c.tzinfo or d.tzinfo
    if zone:
        a, b, c, d = [x.replace(tzinfo=zone) if x.tzinfo is None else x for x in (a, b, c, d)]
    return a < d and c < b


def protect_paid_schedule(previous: list, proposed: list) -> None:
    """General event edits cannot forge, move or rewrite paid milestones."""
    fields = ("due_date", "label", "amount", "paid", "paid_at", "reference")
    def canonical(row, key):
        value = row.get(key)
        if key == "paid_at" and value:
            return instant(value)
        if key == "reference" and not value:
            return None
        return value
    for i, row in enumerate(proposed):
        old = previous[i] if i < len(previous) else {}
        if row.get("paid") and not old.get("paid"):
            raise ValueError("Ödemeyi yalnız yetkili ödeme işlemiyle işaretleyin")
    for i, row in enumerate(previous):
        if row.get("paid"):
            if i >= len(proposed) or any(canonical(row, k) != canonical(proposed[i], k) for k in fields):
                raise ValueError("Ödenmiş taksit silinemez, taşınamaz veya değiştirilemez")


def peak_usage(windows: list, allocations: list) -> float:
    """Peak concurrent inventory, not sum of unrelated bookings in an envelope."""
    all_windows = windows + [w for bookings, _qty in allocations for w in bookings]
    zone = next((instant(w["starts_at"]).tzinfo for w in all_windows if instant(w["starts_at"]).tzinfo), UTC)

    def interval(w):
        values = [instant(w[k]) for k in ("starts_at", "ends_at")]
        return tuple(v.replace(tzinfo=zone) if v.tzinfo is None else v for v in values)

    desired = [interval(w) for w in windows]
    others = [([interval(w) for w in bookings], qty) for bookings, qty in allocations]
    points = {s for s, _e in desired}
    points.update(s for spans, _qty in others for s, _e in spans if any(a <= s < b for a, b in desired))
    return max((sum(qty for spans, qty in others if any(s <= p < e for s, e in spans)) for p in points), default=0)
