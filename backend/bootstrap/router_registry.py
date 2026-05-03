"""
Bootstrap: Router Registry
Centralised router mounting. Each router is imported and mounted
with proper error isolation so one broken module cannot crash the app.
"""
import logging

logger = logging.getLogger(__name__)
import importlib
import traceback
from typing import Callable

from fastapi import Depends, FastAPI


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
    ("routers.hotel_services", "router", ["hotel-services"], None, None),
    ("routers.finance", "router", ["finance"], None, None),
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
    ("routers.mice", "router", ["mice"], None, None),
    ("routers.sales_catering", "router", ["sales-catering"], None, None),
    ("routers.banquet_competitor", "router", ["banquet-competitor"], None, None),
    ("routers.cross_property", "router", ["cross-property"], None, None),
    ("routers.procurement", "router", ["procurement"], None, None),
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
    ("domains.revenue.pricing_router", "router", ["Revenue / Pricing"], None, None),
    ("domains.admin.router", "router", ["Admin / Operations"], None, None),
    ("domains.pms.notification_router", "router", ["PMS / Notifications"], None, None),
    ("domains.pms.dashboard_router", "router", ["PMS / Dashboard"], None, None),
    ("domains.pms.frontdesk_router", "router", ["PMS / Front Desk"], None, None),
    ("domains.pms.pos_fnb_router", "router", ["PMS / POS & F&B"], None, None),
    ("domains.pms.housekeeping_router", "router", ["PMS / Housekeeping"], None, None),
    ("domains.pms.maintenance_router", "router", ["PMS / Maintenance"], None, None),
    ("domains.guest.operations_router", "router", ["Guest / Operations"], None, None),
    ("domains.pms.groups_router", "router", ["PMS / Groups"], None, None),
    ("domains.channel_manager.operations_router", "router", ["Channel Manager / Operations"], None, None),
    ("domains.sales.crm_router", "router", ["Sales / CRM"], None, None),
    ("domains.pms.calendar_router", "router", ["PMS / Calendar"], None, None),
    ("domains.pms.approvals_router", "router", ["PMS / Approvals"], None, None),
    ("domains.pms.misc_router", "router", ["PMS / Operations"], None, None),
    # Accounting (migrated from _legacy)
    ("domains.accounting.router", "router", ["Accounting"], None, None),
    # Phase C/D/E — Hardening routers
    ("domains.channel_manager.hardening_router", "router", ["Channel Manager / Hardening"], None, None),
    ("workers.hardening_router", "router", ["Workers / Hardening"], None, None),
    ("security.hardening_router", "router", ["Security / Hardening"], None, None),
    ("modules.observability.hardening_router", "router", ["Observability / Runtime"], None, None),
    # Night Audit Core (production-grade)
    ("domains.pms.night_audit.router", "router", ["Night Audit Core"], None, None),
    # Audit Timeline API
    ("routers.audit_timeline", "router", ["Audit Timeline"], None, None),
    # Operational Metrics
    ("routers.operational_metrics", "router", ["Operational Metrics"], None, None),
    # System Health Dashboard — role-based
    ("routers.system_health_dashboard", "router", ["System Health"], None, None),
    ("routers.system_health_normalized", "router", ["System Health Normalized"], None, None),
    ("routers.system_health_live", "router", ["System Health Live"], None, None),
    # Phase 5 — Production Hardening
    ("domains.pms.frontdesk_router_v2", "router", ["Front Desk v2"], None, None),
    ("domains.pms.pos_fnb_router_v2", "router", ["POS & F&B v2"], None, None),
    # Semantic Layer (ADR read models for BI/SDK/partner consumers)
    ("modules.stays.router", "router", ["Semantic Stays"], None, None),
    ("modules.inventory.router", "router", ["Semantic Inventory"], None, None),
    # 3rd-party integration credentials (super-admin)
    ("routers.integration_credentials", "router", ["Integration Credentials"], None, None),
    ("modules.observability.alert_router", "router", ["Alert Enrichment"], None, None),
    ("modules.incident.incident_router", "router", ["Incident Response"], None, None),
    ("domains.channel_manager.validation_router", "router", ["CM Provider Validation"], None, None),
    ("domains.channel_manager.providers.hotelrunner_router", "router", ["HotelRunner Integration"], None, None),
    ("domains.channel_manager.providers.hotelrunner_webhook", "router", ["HotelRunner Webhooks"], None, None),
    ("domains.channel_manager.providers.hotelrunner_sync", "sync_router", ["HotelRunner Sync"], None, None),
    ("domains.channel_manager.providers.exely.exely_router", "router", ["Exely Integration"], None, None),
    ("domains.channel_manager.providers.exely.exely_webhook_router", "router", ["Exely Webhooks"], None, None),
    # ARI Push Engine
    ("domains.channel_manager.ari.router", "router", ["ARI Push Engine"], None, None),
    # Rate Manager — Fiyat/Müsaitlik/Kısıtlama Yönetimi
    ("domains.channel_manager.rate_manager_router", "router", ["Rate Manager"], None, None),
    # HR Rate Manager — HotelRunner Fiyat/Müsaitlik Yönetimi
    ("domains.channel_manager.hr_rate_manager_router", "router", ["HR Rate Manager"], None, None),
    # Unified Rate Manager — Birlesik Fiyat/Musaitlik Yonetimi
    ("domains.channel_manager.unified_rate_manager_router", "router", ["Unified Rate Manager"], None, None),
    # Channel Connections Overview — Kanal Bağlantıları Genel Bakış
    ("domains.channel_manager.channel_connections_router", "router", ["Channel Connections"], None, None),
    # Auto-Map — Otomatik Oda Esleme
    ("domains.channel_manager.auto_map_router", "router", ["Auto-Map"], None, None),
    # Wire Failure Tracking — Hata Takip
    ("domains.channel_manager.wire_failure_router", "router", ["Wire Failure Tracking"], None, None),
    # PII Strict Mode — Zorunlu PII Maskeleme
    ("security.pii_strict_mode_router", "router", ["Security — PII Strict Mode"], None, None),
    # Channel Manager — Unified Data Model
    ("domains.channel_manager.model_router", "router", ["Channel Manager — Data Model"], None, None),
    # Reservation Ingest Pipeline
    ("domains.channel_manager.ingest.ingest_router", "router", ["Reservation Ingest"], None, None),
    # Cross-Provider Reconciliation Engine
    ("domains.channel_manager.reconciliation_engine.reconciliation_router", "router", ["Cross-Provider Reconciliation"], None, None),
    # Operational Monitoring & Alerting
    ("domains.channel_manager.monitoring.monitoring_router", "router", ["Operational Monitoring"], None, None),
    # Provider Configuration & Validation
    ("domains.channel_manager.provider_config_router", "router", ["Provider Config & Validation"], None, None),
    ("security.tenant_isolation_router", "router", ["Tenant Isolation v2"], None, None),
    ("ops.pilot_router", "router", ["Pilot Readiness"], None, None),
    # Phase 6 — Runtime Validation & Go-Live
    ("ops.validation_router", "router", ["Runtime Validation & Go-Live"], None, None),
    # Phase 7 — Production Rollout & Pilot Readiness
    ("ops.production_rollout_router", "router", ["Production Rollout"], None, None),
    # Core Lockdown — Observability & Health
    ("domains.channel_manager.lockdown_router", "router", ["Core Lockdown"], None, None),
    # Operator Incident Panel
    ("domains.channel_manager.incident_router", "router", ["Incident Panel"], None, None),
    # Runtime Enforcement (Hard Fail, Auto-Heal, Push Loop)
    ("domains.channel_manager.runtime_enforcement_router", "router", ["Runtime Enforcement"], None, None),
    # Notification Events (High-Signal Dashboard Notifications)
    ("domains.channel_manager.notification_events_router", "router", ["Notification Events"], None, None),
    # Control Plane — Operational Visibility & Reliability
    ("controlplane.ops_router", "router", ["Control Plane"], None, None),
    # Event Timeline — Trace any reservation in seconds
    ("controlplane.timeline_router", "router", ["Event Timeline"], None, None),
    # Dashboard — Single pane of glass health view
    ("controlplane.dashboard_router", "router", ["Control Plane Dashboard"], None, None),
    # Deploy Events — CI/CD → Control Plane bridge
    ("controlplane.dashboard_router", "deploy_router", ["Deploy Events"], None, None),
    # Folio Ledger — Immutable append-only ledger
    ("routers.folio_ledger", "router", ["Folio Ledger"], None, None),
    # Learning Loop — Incident classification, RCA, never-again rules
    ("controlplane.learning_loop_router", "router", ["Learning Loop"], None, None),
    # Security Operations — SEC-001 Secrets + SEC-002 Crypto rollout APIs
    ("controlplane.security_ops_router", "router", ["Security Operations"], None, None),
    # Sandbox Dashboard — Visualization of simulation results on ops dashboard
    ("controlplane.sandbox_dashboard_router", "router", ["Sandbox Dashboard"], None, None),
    # CI/CD Pipeline — 3-tier deploy validation (PR Gate, Staging Gate, Nightly)
    ("controlplane.cicd_pipeline_router", "router", ["CI/CD Pipeline"], None, None),
    # Room Blocks — OOO/OOS/Maintenance (INV-5: same availability truth)
    ("routers.room_blocks", "router", ["Room Blocks"], None, None),
    # Booking Holds — TTL/Hold mechanism for pending bookings
    ("routers.booking_holds", "router", ["Booking Holds"], None, None),
    # Room-Type Inventory — Phase C.1 read-only materialized view (ADR-003)
    ("routers.inventory", "router", ["Room-Type Inventory"], None, None),
    # HotelRunner External Integration — Compatibility endpoints for HR panel
    ("routers.hotelrunner_compat", "router", ["HotelRunner External Integration"], None, None),
    # HotelRunner v2 Connector — Production-grade adapter
    ("channel_manager.connectors.hotelrunner_v2.router", "router", ["HotelRunner v2 Connector"], None, None),
    # Agency Portal — Bolgesel Acente Yonetimi ve Portali
    ("routers.agency_portal", "router", ["Agency Portal"], None, None),
    ("routers.agency_content", "router", ["Agency Content"], None, None),
    # Syroce B2B API — Acente Otomasyon Sistemi Entegrasyonu
    ("routers.b2b_api", "router", ["B2B API - Syroce"], None, None),
    # B2B Analytics Dashboard — Acente & API Kullanım Analitikleri
    ("routers.b2b_analytics", "router", ["B2B Analytics"], None, None),
    # Marketplace v1 — Cross-tenant B2B köprüsü (Syroce Agent entegrasyonu)
    ("routers.marketplace_b2b", "router", ["Marketplace v1"], None, None),
    # Marketplace v1 — Sözleşme yönetimi (agency-side / hotel-side / admin)
    ("routers.agency_contracts", "agency_router", ["Marketplace v1 / Contracts"], None, None),
    ("routers.agency_contracts", "hotel_router", ["Marketplace v1 / Incoming"], None, None),
    ("routers.agency_contracts", "admin_router", ["Marketplace v1 / Admin"], None, None),
    # KBS — Konaklama Bildirim Sistemi (PMS kullanıcı oturumuyla, key gerekmez)
    ("routers.kbs", "router", ["KBS"], None, None),
    ("routers.help", "router", ["help"], None, None),
    ("routers.regulatory", "router", ["regulatory"], None, None),
    ("routers.report_scheduler", "router", ["Report Scheduler"], None, None),
    # PMS Cashier, Laundry, Meeting Rooms
    ("domains.pms.cashier_router", "router", ["PMS / Cashier"], None, None),
    # Opera-parity: Folio Routing, Block Mgmt, Activity Scheduler, Loyalty, Forecast
    ("domains.pms.folio_routing_router", "router", ["PMS / Folio Routing"], None, None),
    ("domains.pms.folio_window_router", "router", ["PMS / Folio Windows"], None, None),
    ("domains.pms.block_management_router", "router", ["PMS / Block Management"], None, None),
    ("domains.pms.activity_scheduler_router", "router", ["Activity Scheduler"], None, None),
    ("domains.pms.function_space_router", "router", ["Function Space"], None, None),
    ("domains.guest.loyalty_router", "router", ["Loyalty Program"], None, None),
    ("domains.guest.profile_udf_router", "router", ["Profile UDF"], None, None),
    ("domains.pms.catering_router", "router", ["Catering Menu"], None, None),
    ("domains.pms.suite_connecting_router", "router", ["Suite & Connecting"], None, None),
    ("domains.revenue.hurdle_router", "router", ["Hurdle Rates"], None, None),
    ("domains.revenue.forecast_router", "router", ["Revenue / Forecast"], None, None),
    # PMS Operations — Concierge, Banquet, KBS, KVKK, Guest Prefs, Room Features
    ("domains.pms.operations_router", "router", ["PMS / Operations"], None, None),
    # Ops Telemetry — Operational events, webhook DLQ, channel health
    ("routers.ops_events_router", "router", ["Ops Events & Telemetry"], None, None),
    ("routers.ops_timeline_router", "router", ["Ops Timeline & Incidents"], None, None),
    ("routers.early_warning_router", "router", ["Early Warning & Predictive"], None, None),
    # Outbox / Import admin
    ("routers.outbox_admin", "outbox_admin_router", ["Outbox Admin"], "/api", None),
    ("routers.import_admin", "import_admin_router", ["Import Admin"], "/api", None),
    # Room QR Requests — Per-room QR codes for guest service requests
    # NOTE: route paths inside the router already start with /api, so no extra prefix
    ("routers.room_qr_requests", "router", ["Room QR Requests"], None, None),
]

# Optional routers with special import paths
# Legacy routers (moved to _legacy/) removed — active modules live in domains/ and routers/
_OPTIONAL_ROUTERS: list[tuple[str, str, list[str], str | None, str | None]] = [
    ("channel_manager.interfaces.router_registry", "router", ["Channel Manager v2"], None, None),
]


def register_routers(app: FastAPI, api_router, require_super_admin_dep: Callable = None) -> None:
    """Mount all extracted and optional routers onto the app."""

    # Mount extracted routers onto the api_router (these all use /api prefix already)
    for mod_path, attr, tags, prefix_override, deps in _EXTRACTED_ROUTERS:
        router = _safe_import(mod_path, attr)
        if router is not None:
            try:
                kwargs = {"tags": tags}
                if prefix_override:
                    kwargs["prefix"] = prefix_override
                app.include_router(router, **kwargs)
                logger.info(f"  ✅ {mod_path}")
            except Exception as e:
                logger.info(f"  ❌ {mod_path}: {e}")

    # Mount optional routers directly on app
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
