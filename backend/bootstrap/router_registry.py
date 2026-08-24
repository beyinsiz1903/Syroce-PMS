"""
Bootstrap: Router Registry
Centralised router mounting. Each router is imported and mounted
with proper error isolation so one broken module cannot crash the app.
"""

import asyncio
import importlib
import logging
import os
import traceback
from typing import Callable

from fastapi import Depends, FastAPI

from modules.pms_core.module_scope_service import require_module_scope

logger = logging.getLogger(__name__)


# Dedicated human/UI routers that are safe to protect as a whole. Mixed
# routers that expose public/provider/webhook/service-key endpoints are
# intentionally absent and are scoped at endpoint/sub-router level instead.
ROUTER_MODULE_SCOPES: dict[str, str] = {
    "routers.housekeeping": "housekeeping",
    "routers.walkin": "frontdesk",
    "routers.room_map": "frontdesk",
    "routers.report_builder": "reports",
    "routers.procurement": "procurement",
    "routers.report_scheduler": "reports",
    "domains.sales.router": "sales",
    "domains.sales.crm_router": "sales",
    "domains.hr.router": "hr",
    "domains.pms.frontdesk_router": "frontdesk",
    "domains.pms.frontdesk_router_v2": "frontdesk",
    "domains.pms.housekeeping_router": "housekeeping",
    "domains.pms.maintenance_router": "maintenance",
    "domains.pms.pos_router": "pos",
    "domains.pms.pos_fnb_router": "pos",
    "domains.pms.pos_fnb_router_v2": "pos",
    "domains.pms.pos_extensions.pos_currency": "pos",
    "domains.pms.pos_extensions.pos_happy_hour": "pos",
    "domains.pms.pos_extensions.pos_coupons": "pos",
    "domains.pms.pos_extensions.pos_loyalty_pos": "pos",
    "domains.pms.pos_extensions.pos_shift_close": "pos",
    "domains.pms.pos_extensions.pos_barcode": "pos",
    "domains.pms.pos_extensions.pos_print_spool": "pos",
    "domains.pms.pos_extensions.pos_fiscal": "pos",
    "domains.pms.cashier_router": "cashier",
    "domains.pms.calendar_router": "frontdesk",
    "domains.accounting.router": "finance",
    "domains.accounting.gl_router": "finance",
    "domains.accounting.ap_router": "finance",
    "domains.accounting.budget_router": "finance",
    "domains.accounting.fixed_asset_router": "finance",
    "domains.accounting.payroll_gl_router": "finance",
    "domains.channel_manager.operations_router": "channel_manager",
    "domains.channel_manager.rate_manager_router": "channel_manager",
    "domains.channel_manager.hr_rate_manager_router": "channel_manager",
    "domains.channel_manager.unified_rate_manager_router": "channel_manager",
    "domains.channel_manager.channel_connections_router": "channel_manager",
    "domains.channel_manager.auto_map_router": "channel_manager",
}


def _safe_import(module_path: str, attr: str):
    """Import a router attribute from a module, returning None on failure."""
    try:
        mod = importlib.import_module(module_path)
        router = getattr(mod, attr)
        return router
    except Exception as e:
        logger.info(f"⚠️  Router import failed [{module_path}.{attr}]: {e}")
        traceback.print_exc()
        return None


def _router_dependencies(module_path: str, declared: list | None) -> list:
    dependencies = list(declared or [])
    scope = ROUTER_MODULE_SCOPES.get(module_path)
    if scope:
        dependencies.append(Depends(require_module_scope(scope)))
    return dependencies


# ── Router manifest ─────────────────────────────────────────────────
# (module_path, attribute_name, tags, prefix_override, dependencies)
_EXTRACTED_ROUTERS: list[tuple[str, str, list[str], str | None, list | None]] = [
    # Core extracted routers
    ("routers.auth", "router", ["auth"], None, None),
    ("routers.db_admin", "router", ["admin-db"], None, None),
    ("routers.housekeeping", "router", ["housekeeping"], None, None),
    ("routers.departments", "router", ["departments"], None, None),
    ("routers.pms", "router", ["pms"], None, None),
    ("routers.pms_rooms", "router", ["pms"], None, None),
    ("routers.pms_guests", "router", ["pms"], None, None),
    ("routers.shift_handover", "router", ["pms"], None, None),
    ("routers.early_late_pricing", "router", ["pms"], None, None),
    ("routers.eod_report", "router", ["pms"], None, None),
    ("routers.no_show_risk", "router", ["pms"], None, None),
    ("routers.walkin", "router", ["pms"], None, None),
    ("routers.room_map", "router", ["pms"], None, None),
    ("routers.pms_bookings", "router", ["pms"], None, None),
    ("routers.pms_dashboard", "router", ["pms"], None, None),
    ("routers.pms_analytics", "router", ["pms-analytics"], None, None),
    ("routers.pms_services", "router", ["pms-services"], None, None),
    ("routers.pms_room_queue", "router", ["pms-room-queue"], None, None),
    ("routers.pms_room_details", "router", ["pms-room-details"], None, None),
    ("routers.pms_reservations", "router", ["pms-reservations"], None, None),
    ("routers.pms_availability", "router", ["pms-availability"], None, None),
    ("routers.reservation_detail", "router", ["reservation-detail"], None, None),
    ("routers.vcc_router", "router", ["vcc"], None, None),
    ("routers.payments_router", "router", ["payments"], None, None),
    ("routers.hotel_services", "router", ["hotel-services"], None, None),
    ("routers.finance", "router", ["finance"], None, None),
    ("routers.finance.folio_einvoice_public", "router", ["e-Fatura"], None, None),
    ("routers.finance.einvoice", "router", ["e-Fatura"], None, None),
    ("api.routes.invoice_integrations", "router", ["Integrations", "Reconciliation"], None, None),
    ("api.routes.incoming_invoice_integrations", "router", ["Integrations", "Reconciliation"], None, None),
    ("routers.reports", "router", ["reports"], None, None),
    ("routers.pms_hardening", "router", ["pms-core"], None, None),
    ("routers.revenue_management", "router", ["revenue-engine"], None, None),
    ("routers.displacement_analysis", "router", ["displacement-analysis"], None, None),
    ("routers.travel_agent_arap", "router", ["travel-agent-arap"], None, None),
    ("routers.event_system", "router", ["event-system"], None, None),
    ("routers.guest_journey", "router", ["guest-journey"], None, None),
    ("routers.platform_scaling", "router", ["platform-scaling"], None, None),
    ("routers.enterprise_live", "router", ["enterprise-live"], None, None),
    ("routers.data_intelligence", "router", ["data-intelligence"], None, None),
    ("routers.messaging", "router", ["messaging"], None, None),
    ("routers.ml_scheduler", "router", ["ml-scheduler"], None, None),
    ("routers.revenue_autopilot_v2", "router", ["revenue-autopilot-v2"], None, None),
    ("routers.websocket_health", "router", ["websocket-health"], None, None),
    ("routers.analytics_export", "router", ["analytics-export"], None, None),
    ("routers.data_pipeline", "router", ["data-pipeline"], None, None),
    ("routers.event_bus", "router", ["event-bus"], None, None),
    ("routers.observability", "router", ["observability"], None, None),
    ("routers.security_hardening", "router", ["security-hardening"], None, None),
    ("routers.runtime_infrastructure", "router", ["runtime-infrastructure"], None, None),
    ("routers.infra_hardening", "router", ["infrastructure-hardening"], None, None),
    ("routers.production_golive", "router", ["production-golive"], None, None),
    ("routers.report_builder", "router", ["report-builder"], None, None),
    ("routers.guest_messaging", "router", ["guest-messaging"], None, None),
    ("routers.mailing", "router", ["mailing"], None, None),
    ("routers.marketplace", "router", ["marketplace"], None, None),
    ("routers.integrations_afsadakat", "router", ["af-sadakat"], None, None),
    ("routers.pms_outbound", "router", ["pms-outbound"], None, None),
    ("routers.onboarding", "router", ["onboarding"], None, None),
    ("routers.security_2fa", "router", ["2fa"], None, None),
    ("routers.pci_compliance", "router", ["compliance"], None, None),
    ("routers.xchange", "router", ["xchange"], None, None),
    ("domains.spa.router", "router", ["spa"], None, None),
    ("domains.golf.router", "router", ["golf"], None, None),
    ("routers.sustainability", "router", ["sustainability"], None, None),
    ("routers.wbe_public", "router", ["wbe-public"], None, None),
    ("routers.mice", "router", ["mice"], None, None),
    ("routers.sales_catering", "router", ["sales-catering"], None, None),
    ("routers.banquet_competitor", "router", ["banquet-competitor"], None, None),
    ("routers.cross_property", "router", ["cross-property"], None, None),
    ("routers.procurement", "router", ["procurement"], None, None),
    ("routers.integration_rollout", "router", ["integration-rollout"], None, None),
    ("routers.uploads", "router", ["uploads"], None, None),
    # Domain routers (Phase B extraction)
    ("domains.channel_manager.router", "router", ["channel-manager-domain"], None, None),
    ("domains.guest.router", "router", ["guest-profile-domain"], None, None),
    ("domains.guest.checkin_router", "router", ["checkin-domain"], None, None),
    ("domains.sales.router", "router", ["sales-crm-domain"], None, None),
    ("domains.pms.pos_router", "router", ["pos-fnb-domain"], None, None),
    ("domains.pms.mobile_router", "router", ["mobile-domain"], None, None),
    ("domains.revenue.analytics_router", "router", ["analytics-domain"], None, None),
    ("domains.pms.enterprise_router", "router", ["enterprise-features"], None, None),
    ("domains.pms.marketplace_router", "router", ["pos-marketplace"], None, None),
    ("domains.revenue.rms_router", "router", ["rms-revenue"], None, None),
    ("domains.guest.experience_router", "router", ["guest-experience"], None, None),
    ("domains.hr.router", "router", ["hr-operations"], None, None),
    # Phase B - Wave 2 domain routers
    ("domains.ai.router", "router", ["AI / ML"], None, None),
    ("domains.pms.night_audit_router", "router", ["PMS / Night Audit"], None, None),
    ("domains.guest.messaging.router", "router", ["Guest / Messaging"], None, None),
    ("domains.guest.messaging.guest_requests_router", "router", ["Guest Requests"], None, None),
    ("domains.revenue.pricing_router", "router", ["Revenue / Pricing"], None, None),
    ("domains.revenue.central_pricing_router", "router", ["Revenue / Central Pricing"], None, None),
    ("domains.compliance.gdpr_router", "router", ["Compliance / GDPR"], None, None),
    ("domains.admin.router", "router", ["Admin / Operations"], None, None),
    ("domains.pms.notification_router", "router", ["PMS / Notifications"], None, None),
    ("domains.pms.dashboard_router", "router", ["PMS / Dashboard"], None, None),
    ("domains.pms.frontdesk_router", "router", ["PMS / Front Desk"], None, None),
    ("domains.pms.pos_fnb_router", "router", ["PMS / POS & F&B"], None, None),
    ("domains.pms.housekeeping_router", "router", ["PMS / Housekeeping"], None, None),
    ("domains.pms.maintenance_router", "router", ["PMS / Maintenance"], None, None),
    ("domains.guest.operations_router", "router", ["Guest / Operations"], None, None),
    ("domains.guest.qr_badge", "router", ["Guest / QR Badge"], None, None),
    ("domains.pms.groups_router", "router", ["PMS / Groups"], None, None),
    ("routers.reservation_waitlist", "router", ["PMS / Reservation Waitlist"], None, None),
    ("domains.channel_manager.operations_router", "router", ["Channel Manager / Operations"], None, None),
    ("domains.sales.crm_router", "router", ["Sales / CRM"], None, None),
    ("domains.pms.calendar_router", "router", ["PMS / Calendar"], None, None),
    ("domains.pms.approvals_router", "router", ["PMS / Approvals"], None, None),
    ("domains.pms.misc_router", "router", ["PMS / Operations"], None, None),
    # Accounting (migrated from _legacy)
    ("domains.accounting.router", "router", ["Accounting"], None, None),
    ("domains.accounting.gl_router", "router", ["Accounting / GL"], None, None),
    ("domains.accounting.ap_router", "router", ["Accounting / AP"], None, None),
    ("domains.accounting.budget_router", "router", ["Accounting / Budget"], None, None),
    ("domains.accounting.fixed_asset_router", "router", ["Accounting / Fixed Assets"], None, None),
    ("domains.accounting.payroll_gl_router", "router", ["Accounting / Payroll GL"], None, None),
    # Phase C/D/E — Hardening routers
    ("domains.channel_manager.hardening_router", "router", ["Channel Manager / Hardening"], None, None),
    ("workers.hardening_router", "router", ["Workers / Hardening"], None, None),
    ("security.hardening_router", "router", ["Security / Hardening"], None, None),
    ("modules.observability.hardening_router", "router", ["Observability / Runtime"], None, None),
    ("domains.pms.night_audit.router", "router", ["Night Audit Core"], None, None),
    ("routers.audit_timeline", "router", ["Audit Timeline"], None, None),
    ("routers.operational_metrics", "router", ["Operational Metrics"], None, None),
    ("routers.system_health_dashboard", "router", ["System Health"], None, None),
    ("routers.system_health_normalized", "router", ["System Health Normalized"], None, None),
    ("routers.system_health_live", "router", ["System Health Live"], None, None),
    ("domains.pms.frontdesk_router_v2", "router", ["Front Desk v2"], None, None),
    ("domains.pms.pos_fnb_router_v2", "router", ["POS & F&B v2"], None, None),
    ("domains.pms.pos_extensions.pos_currency", "router", ["POS Ext / Multi-Currency"], None, None),
    ("domains.pms.pos_extensions.pos_happy_hour", "router", ["POS Ext / Happy Hour"], None, None),
    ("domains.pms.pos_extensions.pos_coupons", "router", ["POS Ext / Coupons"], None, None),
    ("domains.pms.pos_extensions.pos_loyalty_pos", "router", ["POS Ext / Loyalty"], None, None),
    ("domains.pms.pos_extensions.pos_shift_close", "router", ["POS Ext / Shift Close"], None, None),
    ("domains.pms.pos_extensions.pos_barcode", "router", ["POS Ext / Barcode"], None, None),
    ("domains.pms.pos_extensions.pos_print_spool", "router", ["POS Ext / Print Spool"], None, None),
    ("domains.pms.pos_extensions.pos_fiscal", "router", ["POS Ext / Fiscal (ÖKC)"], None, None),
    ("modules.stays.router", "router", ["Semantic Stays"], None, None),
    ("modules.inventory.router", "router", ["Semantic Inventory"], None, None),
    ("routers.integration_credentials", "router", ["Integration Credentials"], None, None),
    ("routers.capx_integration", "router", ["CapX Integration"], None, None),
    ("routers.capx_webhook", "router", ["CapX Webhook"], None, None),
    ("modules.observability.alert_router", "router", ["Alert Enrichment"], None, None),
    ("modules.incident.incident_router", "router", ["Incident Response"], None, None),
    ("domains.channel_manager.validation_router", "router", ["CM Provider Validation"], None, None),
    ("domains.channel_manager.providers.hotelrunner_router", "router", ["HotelRunner Integration"], None, None),
    ("domains.channel_manager.providers.hotelrunner_webhook", "router", ["HotelRunner Webhooks"], None, None),
    ("domains.channel_manager.providers.hotelrunner_sync", "sync_router", ["HotelRunner Sync"], None, None),
    ("domains.channel_manager.providers.exely.exely_router", "router", ["Exely Integration"], None, None),
    ("domains.channel_manager.providers.exely.exely_webhook_router", "router", ["Exely Webhooks"], None, None),
    ("domains.channel_manager.ari.router", "router", ["ARI Push Engine"], None, None),
    ("domains.channel_manager.rate_manager_router", "router", ["Rate Manager"], None, None),
    ("domains.channel_manager.hr_rate_manager_router", "router", ["HR Rate Manager"], None, None),
    ("domains.channel_manager.unified_rate_manager_router", "router", ["Unified Rate Manager"], None, None),
    ("domains.channel_manager.channel_connections_router", "router", ["Channel Connections"], None, None),
    ("domains.channel_manager.auto_map_router", "router", ["Auto-Map"], None, None),
    ("domains.channel_manager.wire_failure_router", "router", ["Wire Failure Tracking"], None, None),
    ("security.pii_strict_mode_router", "router", ["Security — PII Strict Mode"], None, None),
    ("domains.channel_manager.model_router", "router", ["Channel Manager — Data Model"], None, None),
    ("domains.channel_manager.ingest.ingest_router", "router", ["Reservation Ingest"], None, None),
    ("domains.channel_manager.reconciliation_engine.reconciliation_router", "router", ["Cross-Provider Reconciliation"], None, None),
    ("domains.channel_manager.monitoring.monitoring_router", "router", ["Operational Monitoring"], None, None),
    ("domains.channel_manager.provider_config_router", "router", ["Provider Config & Validation"], None, None),
    ("security.tenant_isolation_router", "router", ["Tenant Isolation v2"], None, None),
    ("ops.pilot_router", "router", ["Pilot Readiness"], None, None),
    ("ops.validation_router", "router", ["Runtime Validation & Go-Live"], None, None),
    ("ops.production_rollout_router", "router", ["Production Rollout"], None, None),
    ("domains.channel_manager.lockdown_router", "router", ["Core Lockdown"], None, None),
    ("domains.channel_manager.incident_router", "router", ["Incident Panel"], None, None),
    ("domains.channel_manager.runtime_enforcement_router", "router", ["Runtime Enforcement"], None, None),
    ("domains.channel_manager.notification_events_router", "router", ["Notification Events"], None, None),
    ("controlplane.ops_router", "router", ["Control Plane"], None, None),
    ("controlplane.timeline_router", "router", ["Event Timeline"], None, None),
    ("controlplane.dashboard_router", "router", ["Control Plane Dashboard"], None, None),
    ("controlplane.dashboard_router", "deploy_router", ["Deploy Events"], None, None),
    ("routers.folio_ledger", "router", ["Folio Ledger"], None, None),
    ("controlplane.learning_loop_router", "router", ["Learning Loop"], None, None),
    ("controlplane.security_ops_router", "router", ["Security Operations"], None, None),
    ("controlplane.sandbox_dashboard_router", "router", ["Sandbox Dashboard"], None, None),
    ("controlplane.cicd_pipeline_router", "router", ["CI/CD Pipeline"], None, None),
    ("routers.room_blocks", "router", ["Room Blocks"], None, None),
    ("routers.booking_holds", "router", ["Booking Holds"], None, None),
    ("routers.inventory", "router", ["Room-Type Inventory"], None, None),
    ("routers.hotelrunner_compat", "router", ["HotelRunner External Integration"], None, None),
    ("channel_manager.connectors.hotelrunner_v2.router", "router", ["HotelRunner v2 Connector"], None, None),
    ("routers.agency_portal", "router", ["Agency Portal"], None, None),
    ("routers.agency_content", "router", ["Agency Content"], None, None),
    ("routers.b2b_api", "router", ["B2B API - Syroce"], None, None),
    ("routers.agency_v1", "router", ["Agency v1 - PMS Entegrasyon"], None, None),
    ("routers.b2b_analytics", "router", ["B2B Analytics"], None, None),
    ("routers.marketplace_b2b", "router", ["Marketplace v1"], None, None),
    ("routers.agency_contracts", "agency_router", ["Marketplace v1 / Contracts"], None, None),
    ("routers.agency_contracts", "hotel_router", ["Marketplace v1 / Incoming"], None, None),
    ("routers.agency_contracts", "admin_router", ["Marketplace v1 / Admin"], None, None),
    ("routers.kbs", "router", ["KBS"], None, None),
    ("routers.help", "router", ["help"], None, None),
    ("routers.academy", "router", ["academy"], None, None),
    ("routers.academy_public", "router", ["academy-public"], None, None),
    ("domains.contact_center.router", "router", ["contact-center"], None, None),
    ("domains.contact_center.voice_router", "router", ["contact-center-voice"], None, None),
    ("domains.contact_center.voice_router", "public_router", ["contact-center-voice-webhook"], None, None),
    ("routers.regulatory", "router", ["regulatory"], None, None),
    ("routers.report_scheduler", "router", ["Report Scheduler"], None, None),
    ("domains.pms.minibar_router", "router", ["PMS / Minibar"], None, None),
    ("domains.pms.cashier_router", "router", ["PMS / Cashier"], None, None),
    ("domains.pms.laundry_router", "router", ["PMS / Laundry"], None, None),
    ("domains.pms.transfer_parking_router", "router", ["PMS / Transfer & Parking"], None, None),
    ("domains.pms.concierge_router", "router", ["PMS / Concierge"], None, None),
    ("domains.pms.fnb_cost_router", "router", ["PMS / F&B Cost"], None, None),
    ("domains.pms.turndown_router", "router", ["PMS / Turndown"], None, None),
    ("domains.pms.folio_routing_router", "router", ["PMS / Folio Routing"], None, None),
    ("domains.pms.folio_window_router", "router", ["PMS / Folio Windows"], None, None),
    ("domains.pms.long_stay_router", "router", ["PMS / Long Stay"], None, None),
    ("domains.pms.block_management_router", "router", ["PMS / Block Management"], None, None),
    ("domains.pms.activity_scheduler_router", "router", ["Activity Scheduler"], None, None),
    ("domains.pms.function_space_router", "router", ["Function Space"], None, None),
    ("domains.guest.loyalty_router", "router", ["Loyalty Program"], None, None),
    ("domains.guest.profile_udf_router", "router", ["Profile UDF"], None, None),
    ("domains.pms.catering_router", "router", ["Catering Menu"], None, None),
    ("domains.pms.suite_connecting_router", "router", ["Suite & Connecting"], None, None),
    ("domains.revenue.hurdle_router", "router", ["Hurdle Rates"], None, None),
    ("domains.revenue.forecast_router", "router", ["Revenue / Forecast"], None, None),
    ("domains.pms.operations_router", "router", ["PMS / Operations"], None, None),
    ("routers.ops_events_router", "router", ["Ops Events & Telemetry"], None, None),
    ("routers.ops_timeline_router", "router", ["Ops Timeline & Incidents"], None, None),
    ("routers.early_warning_router", "router", ["Early Warning & Predictive"], None, None),
    ("routers.outbox_admin", "outbox_admin_router", ["Outbox Admin"], "/api", None),
    ("routers.import_admin", "import_admin_router", ["Import Admin"], "/api", None),
    ("routers.room_qr_requests", "router", ["Room QR Requests"], None, None),
    ("routers.door_reader", "router", ["Door Reader"], None, None),
    ("domains.pms.lock_bridge.connector_router", "router", ["Lock Bridge"], None, None),
    ("routers.physical_security", "router", ["PMS / Physical Security"], None, None),
    ("routers.spa_dining_packages", "router", ["SPA & Dining Scheduler"], None, None),
    ("routers.procurement_b2b", "router", ["B2B Procurement Automation"], None, None),
    ("routers.guest_relations", "router", ["Guest Relations Smart Engine"], None, None),
    ("routers.cm_conflict_queue", "router", ["channel-manager"], None, None),
    ("domains.iot.access_control_router", "router", ["IoT Access Control"], None, None),
]

_OPTIONAL_ROUTERS: list[tuple[str, str, list[str], str | None, str | None]] = [
    ("channel_manager.interfaces.router_registry", "router", ["Channel Manager v2"], None, None),
]

_EXELY_COMPATIBILITY_WEBHOOK_MODULE = "domains.channel_manager.providers.exely.exely_webhook_router"


def _should_mount_router(module_path: str) -> bool:
    """The legacy Exely inbound webhook has no PMSConnect inbound contract."""
    if module_path != _EXELY_COMPATIBILITY_WEBHOOK_MODULE:
        return True
    return not any(os.getenv(key, "").strip().lower() in {"production", "prod", "live"} for key in ("APP_ENV", "ENVIRONMENT", "NODE_ENV"))


def _iter_register(app: FastAPI, api_router, require_super_admin_dep: Callable = None):
    """Generator core for router mounting with cooperative yield points."""
    for mod_path, attr, tags, prefix_override, deps in _EXTRACTED_ROUTERS:
        if not _should_mount_router(mod_path):
            logger.info("  Exely compatibility webhook disabled in production")
            yield
            continue
        router = _safe_import(mod_path, attr)
        if router is not None:
            try:
                kwargs = {"tags": tags}
                if prefix_override:
                    kwargs["prefix"] = prefix_override
                dependencies = _router_dependencies(mod_path, deps)
                if dependencies:
                    kwargs["dependencies"] = dependencies
                app.include_router(router, **kwargs)
                logger.info(f"  ✅ {mod_path}")
            except Exception as e:
                logger.info(f"  ❌ {mod_path}: {e}")
        yield

    for mod_path, attr, tags, prefix, guard in _OPTIONAL_ROUTERS:
        router = _safe_import(mod_path, attr)
        if router is not None:
            kwargs = {"tags": tags}
            if prefix:
                kwargs["prefix"] = prefix
            if guard == "super_admin" and require_super_admin_dep:
                kwargs["dependencies"] = [Depends(require_super_admin_dep())]
            try:
                app.include_router(router, **kwargs)
                logger.info(f"  ✅ {mod_path} (optional)")
            except Exception as e:
                logger.info(f"  ❌ {mod_path}: {e}")
        yield


def register_routers(app: FastAPI, api_router, require_super_admin_dep: Callable = None) -> None:
    """Mount all extracted and optional routers onto the app (synchronous)."""
    for _ in _iter_register(app, api_router, require_super_admin_dep):
        pass


async def register_routers_async(
    app: FastAPI,
    api_router,
    require_super_admin_dep: Callable = None,
    *,
    yield_every: int = 1,
) -> None:
    """Async variant that releases the event loop every ``yield_every`` routers.

    register_routers() imports ~189 router modules synchronously (~17-34s). On
    the single-worker combined deployment that one call blocks the event loop
    for the whole window, so uvicorn cannot serve even the cheap ``/`` health
    probe or the SPA shell while it runs — the platform health check times out.

    Driving the same work as a generator and awaiting ``asyncio.sleep(0)``
    between routers lets the loop service pending requests between imports.
    """
    count = 0
    for _ in _iter_register(app, api_router, require_super_admin_dep):
        count += 1
        if yield_every <= 1 or count % yield_every == 0:
            await asyncio.sleep(0)
