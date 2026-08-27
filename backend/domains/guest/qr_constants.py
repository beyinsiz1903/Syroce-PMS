# Kategori → Departman eşlemesi (DepartmentType enum değerleriyle uyumlu)
CATEGORY_CATALOG = [
    {"id": "cleaning", "department": "rooms", "icon": "sparkles", "default_priority": "normal"},
    {"id": "towels", "department": "rooms", "icon": "shirt", "default_priority": "normal"},
    {"id": "amenities", "department": "rooms", "icon": "package", "default_priority": "low"},
    {"id": "maintenance", "department": "technical", "icon": "wrench", "default_priority": "normal"},
    {"id": "wifi", "department": "technical", "icon": "wifi", "default_priority": "normal"},
    {"id": "tv", "department": "technical", "icon": "tv", "default_priority": "low"},
    {"id": "ac_heating", "department": "technical", "icon": "thermometer", "default_priority": "normal"},
    {"id": "food_order", "department": "fnb", "icon": "utensils", "default_priority": "normal"},
    {"id": "drinks", "department": "fnb", "icon": "wine", "default_priority": "normal"},
    {"id": "minibar", "department": "minibar", "icon": "beer", "default_priority": "low"},
    {"id": "laundry", "department": "laundry", "icon": "shirt", "default_priority": "normal"},
    {"id": "transport", "department": "transportation", "icon": "car", "default_priority": "normal"},
    {"id": "reception", "department": "other", "icon": "bell", "default_priority": "normal"},
    {"id": "spa", "department": "spa", "icon": "heart", "default_priority": "low"},
    {"id": "complaint", "department": "other", "icon": "alert", "default_priority": "high"},
    {"id": "other", "department": "other", "icon": "message", "default_priority": "normal"},
]

CATEGORY_MAP = {c["id"]: c for c in CATEGORY_CATALOG}
VALID_PRIORITIES = {"low", "normal", "high", "urgent"}

# Çoklu dil etiketleri (10 dil için başlangıç seti — eklenebilir)
CATEGORY_LABELS = {
    "cleaning": {"tr": "Oda Temizliği", "en": "Room Cleaning", "de": "Zimmerreinigung", "ru": "Уборка номера", "ar": "تنظيف الغرفة"},
    "towels": {"tr": "Havlu / Çarşaf", "en": "Towels / Linens", "de": "Handtücher", "ru": "Полотенца", "ar": "مناشف"},
    "amenities": {"tr": "Amenity (Sabun vb.)", "en": "Amenities", "de": "Pflegeprodukte", "ru": "Косметика", "ar": "مستلزمات"},
    "maintenance": {"tr": "Arıza / Tamir", "en": "Maintenance", "de": "Wartung", "ru": "Ремонт", "ar": "صيانة"},
    "wifi": {"tr": "İnternet / Wi-Fi", "en": "Internet / Wi-Fi", "de": "WLAN", "ru": "Wi-Fi", "ar": "واي فاي"},
    "tv": {"tr": "Televizyon", "en": "Television", "de": "Fernseher", "ru": "Телевизор", "ar": "تلفاز"},
    "ac_heating": {"tr": "Klima / Isıtma", "en": "AC / Heating", "de": "Klima / Heizung", "ru": "Кондиционер", "ar": "تكييف/تدفئة"},
    "food_order": {"tr": "Oda Servisi (Yemek)", "en": "Room Service (Food)", "de": "Zimmerservice", "ru": "Обслуживание", "ar": "خدمة الغرف"},
    "drinks": {"tr": "İçecek", "en": "Drinks", "de": "Getränke", "ru": "Напитки", "ar": "مشروبات"},
    "minibar": {"tr": "Minibar", "en": "Minibar", "de": "Minibar", "ru": "Минибар", "ar": "ميني بار"},
    "laundry": {"tr": "Çamaşır / Kuru Tem.", "en": "Laundry", "de": "Wäscherei", "ru": "Прачечная", "ar": "غسيل"},
    "transport": {"tr": "Transfer / Ulaşım", "en": "Transport", "de": "Transport", "ru": "Транспорт", "ar": "نقل"},
    "reception": {"tr": "Resepsiyon", "en": "Reception", "de": "Rezeption", "ru": "Стойка", "ar": "استقبال"},
    "spa": {"tr": "SPA / Wellness", "en": "SPA / Wellness", "de": "SPA", "ru": "СПА", "ar": "سبا"},
    "complaint": {"tr": "Şikayet / Geri Bildirim", "en": "Complaint / Feedback", "de": "Beschwerde", "ru": "Жалоба", "ar": "شكوى"},
    "other": {"tr": "Diğer", "en": "Other", "de": "Andere", "ru": "Другое", "ar": "أخرى"},
}

# Default mappings for known service codes
DEFAULT_SERVICE_MAPPINGS = {
    "housekeeping.room_cleaning": "cleaning",
    "housekeeping.no_cleaning_today": "cleaning",
    "housekeeping.extra_bath_towel": "towels",
    "housekeeping.extra_toilet_paper": "amenities",
    "housekeeping.extra_slippers": "amenities",
    "technical.ac_not_working": "ac_heating",
    "technical.no_hot_water": "maintenance",
    "technical.light_not_working": "maintenance",
    "technical.television_not_working": "tv",
    "technical.wifi_problem": "wifi",
    "technical.other_problem": "maintenance",
    "reception.late_checkout": "reception",
    "reception.wake_up_call": "reception",
    "reception.luggage_assistance": "reception",
    "reception.contact_reception": "reception",
    # Older configured catalogue identifiers remain supported.
    "housekeeping room cleaning": "cleaning",
    "housekeeping towels/linen": "towels",
    "housekeeping amenities/toiletries": "amenities",
    "technical generic issue/no hot water": "maintenance",
    "technical AC": "ac_heating",
    "technical Wi-Fi": "wifi",
    "technical TV": "tv",
}

CATALOGUE_DEPARTMENT_MAPPINGS = {
    "housekeeping": "cleaning",
    "rooms": "cleaning",
    "technical": "maintenance",
    "reception": "reception",
    "fnb": "food_order",
    "minibar": "minibar",
    "laundry": "laundry",
    "transportation": "transport",
    "spa": "spa",
    "other": "other",
}

def map_legacy_routing(service_code: str, department_code: str) -> tuple[str, str]:
    if service_code in DEFAULT_SERVICE_MAPPINGS:
        mapped_cat = DEFAULT_SERVICE_MAPPINGS[service_code]
        if mapped_cat in CATEGORY_MAP:
            return mapped_cat, CATEGORY_MAP[mapped_cat]["department"]

    if service_code in CATEGORY_MAP:
        return service_code, CATEGORY_MAP[service_code]["department"]

    # Configured catalogue items still need a meaningful staff-facing category
    # even when their custom service code is not known in advance.
    mapped_cat = CATALOGUE_DEPARTMENT_MAPPINGS.get(department_code)
    if mapped_cat in CATEGORY_MAP:
        return mapped_cat, CATEGORY_MAP[mapped_cat]["department"]

    return "other", "other"
