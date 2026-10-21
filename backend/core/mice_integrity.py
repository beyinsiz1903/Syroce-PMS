"""Pure financial and scheduling contracts for banquet operations."""
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo


def money(value) -> Decimal:
    amount = Decimal(str(0 if value is None else value))
    if not amount.is_finite() or amount < 0:
        raise ValueError("Tutar sonlu ve sıfırdan büyük veya eşit olmalıdır")
    return amount


def rounded(value) -> float:
    return float(money(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def space_leaves(space_id: str, spaces: dict, visited: frozenset | None = None) -> set[str]:
    """A combined hall occupies each physical child; siblings stay independent."""
    visited = visited or frozenset()
    if len(visited) >= 20:
        raise ValueError("Birleşik salon hiyerarşisi en fazla 20 seviye olabilir")
    if space_id in visited:
        raise ValueError("Birleşik salon tanımında döngü var")
    space = spaces.get(space_id)
    if not space or space.get("active") is False:
        raise ValueError("Birleşik salonun alt mekanlarından biri eksik veya pasif")
    children = space.get("component_space_ids") or []
    if len(children) != len(set(children)):
        raise ValueError("Aynı alt mekan birden fazla seçilemez")
    if not children:
        return {space_id}
    leaves = set()
    for child in children:
        part = space_leaves(child, spaces, visited | {space_id})
        if leaves & part:
            raise ValueError("Birleşik salon aynı fiziksel alanı iki kez içeriyor")
        leaves.update(part)
    return leaves


def price_breakdown(subtotal, policy: dict) -> dict:
    """Net catalog prices; discount → service → tax. No inferred legal rate.

    Round each payable component to cents, then add those rounded components
    so the screen, BEO, customer acceptance and accounting reconcile exactly.
    """
    base = money(rounded(subtotal))
    rates = {key: money(policy.get(key, 0)) for key in ("discount_percent", "service_percent", "tax_percent")}
    if any(rate > 100 for rate in rates.values()):
        raise ValueError("Yüzde oranı 0 ile 100 arasında olmalıdır")
    discount = money(rounded(base * rates["discount_percent"] / 100))
    net = base - discount
    service = money(rounded(net * rates["service_percent"] / 100))
    taxable = net + service if policy.get("tax_on_service", True) else net
    tax = money(rounded(taxable * rates["tax_percent"] / 100))
    return {"subtotal": float(base), "discount_total": float(discount), "net_total": float(net),
            "service_total": float(service), "taxable_total": float(taxable), "tax_total": float(tax),
            "grand_total": rounded(net + service + tax)}


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value


def local_instant(value, timezone: str):
    parsed, zone = instant(value), ZoneInfo(timezone)
    if parsed.tzinfo is not None:
        return parsed.astimezone(zone)
    attached = parsed.replace(tzinfo=zone)
    if attached.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != parsed:
        raise ValueError("Yaz/kış saati geçişinde var olmayan yerel saat; geçerli saat seçin")
    if attached.utcoffset() != parsed.replace(tzinfo=zone, fold=1).utcoffset():
        raise ValueError("Yaz/kış saati geçişinde belirsiz saat; açık UTC ofseti gönderin")
    return attached


def occupancy_window(booking: dict) -> dict:
    return {"starts_at": instant(booking["starts_at"]) - timedelta(minutes=booking.get("setup_minutes", 0)),
            "ends_at": instant(booking["ends_at"]) + timedelta(minutes=booking.get("teardown_minutes", 0))}


def overlaps(left, right) -> bool:
    left, right = occupancy_window(left), occupancy_window(right)
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


def peak_usage(windows: list, allocations: list) -> Decimal:
    """Peak concurrent inventory, not sum of unrelated bookings in an envelope."""
    all_windows = windows + [w for bookings, _qty in allocations for w in bookings]
    zone = next((instant(w["starts_at"]).tzinfo for w in all_windows if instant(w["starts_at"]).tzinfo), UTC)

    def interval(w):
        w = occupancy_window(w)
        values = [instant(w[k]) for k in ("starts_at", "ends_at")]
        return tuple(v.replace(tzinfo=zone) if v.tzinfo is None else v for v in values)

    desired = [interval(w) for w in windows]
    others = [([interval(w) for w in bookings], qty) for bookings, qty in allocations]
    points = {s for s, _e in desired}
    points.update(s for spans, _qty in others for s, _e in spans if any(a <= s < b for a, b in desired))
    return max((sum((money(qty) for spans, qty in others if any(s <= p < e for s, e in spans)), Decimal(0)) for p in points), default=Decimal(0))
