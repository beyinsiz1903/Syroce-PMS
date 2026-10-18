"""Is a module set up, and is it used? — from the hotel's own data.

Every catalogue module has a declarative entry:

* ``setup``: what must exist before the module can work (rooms, a channel
  connection, an outlet...). A missing item is reported with its label and,
  where useful, the screen that adds it.
* ``usage``: evidence of real work in the last ``days`` (bookings created,
  audits run, deliveries sent...). Without it a set-up module is "idle".
* ``view``: screens that need no data of their own (dashboards, settings,
  the module store); they are ready as soon as the module is on.

Statuses: ``off`` (module not enabled), ``incomplete`` (a setup item is
missing), ``idle`` (set up, no recent use), ``active`` (set up and used),
``ready`` (set up; no usage signal defined, or a view).
``unknown`` means a check could not be completed (or a rule is not defined).
Per-check ``ok=None`` is unavailable evidence, never a missing setup item.

Read-only. Every query is tenant-scoped and stops counting at the threshold.
Dates are stored as ISO strings in most collections and as datetimes in a
few; the recent-use filter matches both and excludes future records. Shared
checks are deduplicated within one request, not cached across hotels/requests.
Mailing's shared platform transport is checked only for configuration presence;
no secret is returned and no provider connection is tested by this read model.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)
CHECK_TIMEOUT_SECONDS = 3
MAX_CONCURRENT_CHECKS = 8


def check(key, label, collections=(), *, filter=None, min_count=1, days=None, date_field="created_at", path=None, platform=None, not_past=None):
    return {"key": key, "label": label, "collections": [collections] if isinstance(collections, str) else list(collections),
            "filter": filter or {}, "min_count": min_count, "days": days, "date_field": date_field, "path": path, "platform": platform, "not_past": not_past}


ACTIVE_CONNECTION = {"$or": [{"is_active": True}, {"status": "active"}]}
NOT_DELETED = {"status": {"$nin": ["deleted", "archived", "inactive"]}, "is_active": {"$ne": False}, "active": {"$ne": False}}
ROOMS = check("rooms", "Odalar tanımlı", "rooms", filter={**NOT_DELETED, "is_virtual": {"$ne": True}}, path="/app/onboarding")
ROOM_TYPES = check("room_types", "Oda tipleri tanımlı", ["room_types", "rooms"],
                   filter={**NOT_DELETED, "$or": [{"name": {"$type": "string", "$ne": ""}},
                                                  {"room_type": {"$type": "string", "$ne": ""}},
                                                  {"room_type_id": {"$type": "string", "$ne": ""}}]}, path="/app/onboarding")
# Inventory is only a room count; daily_rates belongs to existing bookings,
# not the hotel's sellable price configuration. Legacy rooms use base_price.
RATES = check("rates", "Fiyatlar girilmiş", ["rate_calendar", "room_types", "rooms"],
              filter={**NOT_DELETED, "$or": [{"rate": {"$gt": 0}}, {"base_price": {"$gt": 0}}, {"base_rate": {"$gt": 0}}]},
              path="/unified-rate-manager")
BOOKINGS_30 = check("bookings_30d", "Son 30 günde rezervasyon", "bookings", days=30)
CM_CONNECTION = check("cm_connection", "Kanal yöneticisi bağlantısı", ["exely_connections", "hotelrunner_connections", "provider_connections"],
                      filter=ACTIVE_CONNECTION, path="/channel-connections")
CM_MAPPING = check("cm_mapping", "Oda eşlemesi yapılmış", ["exely_room_mappings", "hotelrunner_room_mappings", "room_mappings", "cm_mappings"],
                   filter={**NOT_DELETED, "$or": [{"entity_type": "room_type"}, {"entity_type": {"$exists": False}}]}, path="/room-mapping-wizard")
CM_PUSH_2 = check("cm_push_2d", "Son 2 günde kanala gönderim", ["exely_ari_deliveries", "hotelrunner_ari_deliveries"], days=2)
NIGHT_AUDIT_2 = check("night_audit_2d", "Son 2 günde gece kapanışı", "night_audit_runs", days=2, date_field="completed_at",
                      filter={"status": "completed", "dry_run": {"$ne": True}})
# Nilvera's provider config is distinct from GL account mappings and global
# platform credentials. Only test for presence, never decrypt or return secrets.
EINVOICE = check("einvoice_provider", "E-fatura sağlayıcısı ayarlı", "tenant_settings",
                 filter={"nilvera.enabled": True, "nilvera.api_key_enc": {"$type": "string", "$ne": ""}}, path="/app/invoices")
INVOICES_30 = check("invoices_30d", "Son 30 günde fatura", ["invoices", "accounting_invoices"], days=30)
POS_SETUP = [check("pos_outlet", "Satış noktası tanımlı", "pos_outlets", filter=NOT_DELETED, path="/pos"),
             check("pos_menu", "Menü ürünleri tanımlı", "pos_menu_items", filter={**NOT_DELETED, "available": {"$ne": False}}, path="/pos")]
POS_30 = check("pos_30d", "Son 30 günde satış", "pos_transactions", days=30)
STAFF = check("staff", "Personel kayıtlı", "staff_members", filter={**NOT_DELETED, "employment_status": {"$ne": "terminated"}}, path="/app/hr")

MODULE_CHECKS: dict[str, dict] = {
    # ── Core PMS ──
    "pms": {"setup": [ROOMS, ROOM_TYPES, RATES], "usage": [BOOKINGS_30]},
    "reservation_calendar": {"setup": [ROOMS], "usage": [BOOKINGS_30]},
    "dashboard": {"view": True},
    "guests": {"usage": [check("guests_30d", "Son 30 günde misafir kaydı", "guests", days=30)]},
    "guest_advanced": {"usage": [check("guest_profiles", "Misafir profili / tercih", ["guest_profiles", "guest_preferences"])]},
    "housekeeping": {"setup": [ROOMS], "usage": [check("hk_30d", "Son 30 günde HK görevi", "housekeeping_tasks", days=30)]},
    "housekeeping_advanced": {"setup": [ROOMS], "usage": [check("hk_log_30d", "Son 30 günde HK kaydı", "housekeeping_log", days=30)]},
    "mobile_housekeeping": {"setup": [ROOMS], "usage": [check("hk_30d", "Son 30 günde HK görevi", "housekeeping_tasks", days=30)]},
    "settings": {"view": True},
    "pms_mobile": {"view": True},
    "folio_basic": {"usage": [check("folios_30d", "Son 30 günde folyo", "folios", days=30)]},
    "folio_management": {"usage": [check("folios_30d", "Son 30 günde folyo", "folios", days=30)]},
    "night_audit_basic": {"setup": [ROOMS], "usage": [NIGHT_AUDIT_2]},
    "night_audit": {"setup": [ROOMS], "usage": [NIGHT_AUDIT_2]},
    "kbs_notify": {"usage": [check("kbs_7d", "Son 7 günde KBS bildirimi", ["kbs_reports", "kbs_notifications"], days=7,
                                   date_field="created_at")]},
    "basic_reporting": {"view": True},
    "reports": {"view": True},
    "gm_dashboards": {"view": True},
    "audit_trail": {"view": True},
    "advanced_analytics": {"usage": [check("analytics_exports", "Analitik dışa aktarım", "analytics_export_jobs", days=30)]},
    "cost_management": {"usage": [check("expenses_30d", "Son 30 günde gider kaydı", "expenses", days=30)]},
    "multi_property": {"view": True},
    "white_label": {"view": True},
    # ── Invoicing & payments ──
    "invoices_basic": {"usage": [INVOICES_30]},
    "invoices": {"setup": [EINVOICE], "usage": [INVOICES_30]},
    "payments_link": {"usage": [check("payments", "Ödeme kaydı", "payments")]},
    # ── Distribution ──
    "channel_manager_lite": {"setup": [CM_CONNECTION, CM_MAPPING], "usage": [CM_PUSH_2]},
    "channel_manager": {"setup": [CM_CONNECTION, CM_MAPPING], "usage": [CM_PUSH_2]},
    "rate_management": {"setup": [RATES], "usage": [check("rates_30d", "Son 30 günde fiyat takvimi güncellemesi", "rate_calendar", days=30, date_field="updated_at")]},
    "agency_extranet": {
        "setup": [
            check("listing", "Tesis vitrini yayında", "marketplace_listings", filter={"is_listed": True}, path="/agency-content"),
            check("contract", "Süresi dolmamış onaylı acente sözleşmesi", "agency_contracts", filter={"status": "approved"}, not_past="valid_to", path="/app/incoming-agency-contracts"),
            check("agency_rates", "Acentelere fiyat paylaşılmış", "agency_rate_calendar", filter={"rate": {"$gt": 0}}, not_past="date", path="/unified-rate-manager"),
        ],
        "usage": [check("agency_bookings_30d", "Son 30 günde acente rezervasyonu", "marketplace_bookings", days=30)],
    },
    "agency_requests": {"view": True},
    "booking_engine": {"setup": [ROOMS, RATES], "usage": [check("wbe_bookings_30d", "Son 30 günde web rezervasyonu", "bookings", days=30,
                                                              filter={"$or": [{"source_channel": "web_booking_engine"}, {"origin": "wbe"}]})]},
    # ── Revenue ──
    "revenue_management": {"setup": [check("rms_rules", "Fiyat kuralı / eşik", ["pricing_settings", "yield_rules", "hurdle_rates"], path="/app/rms")],
                           "usage": [check("rms_reco_30d", "Son 30 günde fiyat önerisi", "rms_pricing_recommendations", days=30, date_field="generated_at")]},
    "mobile_revenue": {"view": True},
    # ── Sales ──
    "group_sales": {"usage": [check("groups_30d", "Son 30 günde grup", ["group_reservations", "group_blocks"], days=30)]},
    "sales_crm": {"setup": [check("companies", "Firma kartı", "companies", path="/crm")],
                  "usage": [check("crm_30d", "Son 30 günde CRM notu", "crm_notes", days=30)]},
    "loyalty_program": {"usage": [check("members", "Sadakat üyesi", "loyalty_members")]},
    "mailing": {"setup": [check("mail_provider", "Merkezi e-posta altyapısı ayarlı", platform="email", path="/app/mailing")],
                "usage": [check("mail_30d", "Son 30 günde kampanya gönderimi", "mailing_campaigns", filter={"sent_count": {"$gt": 0}, "is_test": {"$ne": True}}, days=30)]},
    "api_access": {"setup": [check("api_credentials", "Otele bağlı etkin API anahtarı", "agency_api_keys", filter={"is_active": True}, path="/app/integration-hub")]},
    # ── Operations ──
    "maintenance": {"setup": [check("assets", "Varlık / ekipman kaydı", "maintenance_assets", filter={"status": {"$ne": "retired"}}, path="/maintenance/assets")],
                    "usage": [check("work_orders_30d", "Son 30 günde iş emri", "maintenance_work_orders", days=30)]},
    # QR codes work without a per-hotel salt (it only exists after a rotation).
    "room_qr_requests": {"setup": [ROOMS],
                         "usage": [check("qr_30d", "Son 30 günde QR talebi", "room_qr_requests", days=30)]},
    "quick_id": {"view": True},
    "af_sadakat": {"setup": [check("afsadakat", "Afsadakat bağlantısı", "integration_afsadakat_tenants", filter={"status": "active"}, path="/app/afsadakat")]},
    "marketplace": {"view": True},
    # ── Optional workspaces / add-ons ──
    "hr": {"setup": [STAFF, check("departments", "Departman tanımlı", "hr_departments", filter=NOT_DELETED, path="/app/hr")],
           "usage": [check("attendance_30d", "Son 30 günde puantaj / vardiya", ["attendance_records", "shift_schedules"], days=30)]},
    "pos_fnb": {"setup": POS_SETUP, "usage": [POS_30]},
    "pos_basic": {"setup": POS_SETUP, "usage": [POS_30]},
    "parking": {"setup": [check("transport_resources", "Araç / kaynak tanımlı", "transport_resources", path="/transfer-parking")],
                "usage": [check("parking_30d", "Son 30 günde transfer / vale", ["transport_bookings", "parking_valet_tickets"], days=30)]},
    "spa": {"setup": [check("spa_services", "SPA hizmeti", "spa_services", filter={"active": {"$ne": False}}, path="/spa-wellness"),
                      check("spa_rooms", "SPA odası", "spa_rooms", filter={"active": True}, path="/spa-wellness"),
                      check("spa_therapists", "Terapist", "spa_therapists", filter={"active": True}, path="/spa-wellness")],
            "usage": [check("spa_30d", "Son 30 günde randevu", "spa_appointments", days=30)]},
    "mice": {"setup": [check("mice_spaces", "Toplantı / etkinlik alanı", "mice_spaces", path="/app/mice")],
             "usage": [check("mice_30d", "Son 30 günde etkinlik / fırsat", ["mice_events", "mice_opportunities"], days=30)]},
    "academy": {"usage": [check("academy_assignments", "Eğitim ataması", "academy_assignments")]},
    "contact_center": {"setup": [check("voice_number", "Santral numarası", "contact_center_voice_numbers", path="/app/call-center")],
                       "usage": [check("calls_30d", "Son 30 günde çağrı", "contact_center_calls", days=30, date_field="started_at")]},
    # ── AI ──
    "ai": {"view": True},
    "ai_chatbot": {"usage": [check("guest_messages_30d", "Son 30 günde misafir mesajı", "guest_messages", days=30)]},
    "ai_pricing": {"usage": [check("pricing_reco_30d", "Son 30 günde fiyat önerisi", "pricing_recommendations", days=30)]},
    "ai_predictive": {"usage": [check("forecasts", "Talep tahmini", "demand_forecasts")]},
    "ai_whatsapp": {"setup": [check("wa_provider", "WhatsApp sağlayıcısı ayarlı ve etkin", "messaging_provider_configs",
                                    filter={"enabled": True, "provider_type": "whatsapp",
                                            "credentials_encrypted.access_token": {"$type": "string", "$ne": ""},
                                            "credentials_encrypted.phone_number_id": {"$type": "string", "$ne": ""}}, path="/ai-whatsapp-concierge")]},
    "ai_reputation": {"usage": [check("reviews", "Misafir yorumu", "guest_reviews")]},
    "ai_revenue_autopilot": {"setup": [check("autopilot_policy", "Otopilot politikası", "revenue_autopilot_policies", path="/revenue-autopilot")],
                             "usage": [check("autopilot_runs", "Otopilot çalıştı", "revenue_autopilot_runs")]},
    "ai_social_radar": {"view": True},
}


async def _met(db, tenant_id: str, item: dict, *, now: datetime | None = None) -> bool:
    """True once ``min_count`` matching documents exist in any collection."""
    if item.get("platform") == "email":
        from core.email import DEFAULT_FROM, _is_valid_sender, _provider

        # Mailing uses the platform's Resend/SES transport, not the hotel's
        # operational SMTP/WhatsApp settings. No provider request is made.
        return bool(_is_valid_sender(DEFAULT_FROM) and (_provider() == "ses" or os.environ.get("RESEND_API_KEY", "").strip()))
    query = {"$and": [{"tenant_id": tenant_id}, item["filter"]]}
    now = now or datetime.now(UTC)
    if item.get("not_past"):
        query["$and"].append({item["not_past"]: {"$gte": now.date().isoformat()}})
    if item["days"]:
        moment = now - timedelta(days=item["days"])
        recent = {"$or": [{item["date_field"]: {"$gte": moment.isoformat(), "$lte": now.isoformat()}},
                          {item["date_field"]: {"$gte": moment, "$lte": now}}]}
        query = {"$and": [query, recent]}
    found = 0
    for name in item["collections"]:
        found += await db[name].count_documents(query, limit=item["min_count"] - found, maxTimeMS=1000)
        if found >= item["min_count"]:
            return True
    return False


async def module_readiness(db, tenant_id: str, module_key: str, enabled: bool, *, read_check=None) -> dict:
    spec = MODULE_CHECKS.get(module_key)
    if spec is None:
        return {"module": module_key, "status": "unknown", "setup": [], "usage": []}
    if not enabled:
        return {"module": module_key, "status": "off", "setup": [], "usage": []}
    if spec.get("view"):
        return {"module": module_key, "status": "ready", "view": True, "setup": [], "usage": []}

    async def evaluate(items):
        async def one(item):
            try:
                return await (read_check(item) if read_check else asyncio.wait_for(_met(db, tenant_id, item), CHECK_TIMEOUT_SECONDS))
            except Exception as exc:
                logger.warning("Module readiness check unavailable: %s (%s)", item["key"], type(exc).__name__)
                return None

        results = await asyncio.gather(*(one(item) for item in items))
        return [{"key": item["key"], "label": item["label"], "ok": ok, "path": item["path"]} for item, ok in zip(items, results)]

    setup, usage = await asyncio.gather(evaluate(spec.get("setup", [])), evaluate(spec.get("usage", [])))
    if any(row["ok"] is None for row in [*setup, *usage]):
        status = "unknown"
    elif not all(row["ok"] for row in setup):
        status = "incomplete"
    elif not usage:
        status = "ready"
    else:
        status = "active" if any(row["ok"] for row in usage) else "idle"
    return {"module": module_key, "status": status, "setup": setup, "usage": usage}


async def tenant_readiness(db, tenant_id: str, modules: dict[str, bool], keys: list[str] | None = None) -> dict:
    """Readiness for every catalogue module (or ``keys``) of one hotel."""
    keys = keys or list(MODULE_CHECKS)
    cache = {}
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)
    now = datetime.now(UTC)

    async def bounded(item):
        async with semaphore:
            return await asyncio.wait_for(_met(db, tenant_id, item, now=now), CHECK_TIMEOUT_SECONDS)

    async def read_check(item):
        signature = json.dumps(item, sort_keys=True)
        if signature not in cache:
            cache[signature] = asyncio.create_task(bounded(item))
        return await cache[signature]

    rows = await asyncio.gather(*(module_readiness(db, tenant_id, key, bool(modules.get(key)), read_check=read_check) for key in keys))
    return {row["module"]: row for row in rows}
