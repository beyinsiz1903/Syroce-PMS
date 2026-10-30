"""One reporting taxonomy. Sales techniques (upsell/extra) are not departments."""

LABELS = {
    "room": "Konaklama", "food": "Yiyecek", "beverage": "İçecek",
    "alcohol": "Alkollü içecek", "fnb": "Yiyecek–içecek (kırılımı yok)",
    "restaurant": "Restoran", "cafe": "Kafe", "room_service": "Oda servisi",
    "minibar": "Minibar", "spa": "SPA", "laundry": "Çamaşırhane",
    "concierge": "Concierge", "transfer": "Transfer", "mice": "Toplantı ve etkinlik (MICE)",
    "activity": "Aktiviteler", "function_space": "Salon kiralama",
    "phone": "Telefon", "internet": "İnternet", "parking": "Otopark",
    "city_tax": "Ayrı vergi hareketi", "service_charge": "Servis bedeli",
    "other": "Diğer", "unclassified": "Sınıflandırılmamış hizmet",
}
ALIASES = {
    **dict.fromkeys(("rooms", "room_charge", "accommodation", "lodging", "konaklama"), "room"),
    **dict.fromkeys(("fb", "f&b", "food_beverage", "food_and_beverage", "yeme_icecek"), "fnb"),
    **dict.fromkeys(("drink", "drinks", "beverages"), "beverage"),
    **dict.fromkeys(("alcoholic_beverage", "bar"), "alcohol"),
    **dict.fromkeys(("appetizer", "dessert"), "food"),
    "mini_bar": "minibar", "accommodation_tax": "city_tax",
    "banquet": "mice", "transfer_vehicle": "transfer", "parking_spot": "parking",
    "extra": "unclassified", "upsell": "unclassified",
}
FNB_CATEGORIES = frozenset({"food", "beverage", "alcohol", "fnb", "restaurant", "cafe", "room_service"})
NON_REVENUE_CATEGORIES = frozenset({"split_adjustment", "opening_balance"})


def is_revenue_charge(row):
    """Debt allocation and migration opening debt are not a new sale."""
    raw = str(row.get("charge_category") or row.get("category") or row.get("charge_type") or "").strip().lower()
    return raw not in NON_REVENUE_CATEGORIES


def charge_category(row, *, preserve_unknown=False):
    """Normalize known aliases; detail ledgers may retain custom source keys."""
    raw = str(row.get("charge_category") or row.get("category") or row.get("charge_type") or "other").strip().lower()
    # Generic sales labels may carry an explicit service category. Never guess
    # that an upsell is room rental: it can just as easily be breakfast or SPA.
    if raw in {"upsell", "extra"}:
        service = row.get("service_category") or row.get("revenue_category")
        raw = str(service).strip().lower() if service else raw
    return ALIASES.get(raw, raw if preserve_unknown or raw in LABELS else "unclassified")


def revenue_department(category):
    if category in FNB_CATEGORIES:
        return "fnb"
    if category in {"room", "minibar", "city_tax", "unclassified"}:
        return category
    return "other"
