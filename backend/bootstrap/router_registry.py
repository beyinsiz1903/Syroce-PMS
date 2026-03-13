"""
Bootstrap: Router Registry
Centralised router mounting. Each router is imported and mounted
with proper error isolation so one broken module cannot crash the app.
"""
from fastapi import FastAPI, Depends
import importlib
import traceback
from typing import List, Tuple, Optional, Callable


def _safe_import(module_path: str, attr: str):
    """Import a router attribute from a module, returning None on failure."""
    try:
        mod = importlib.import_module(module_path)
        router = getattr(mod, attr)
        return router
    except Exception as e:
        print(f"⚠️  Router import failed [{module_path}.{attr}]: {e}")
        traceback.print_exc()
        return None


# ── Router manifest ─────────────────────────────────────────────────
# (module_path, attribute_name, tags, prefix_override, dependencies)
_EXTRACTED_ROUTERS: List[Tuple[str, str, List[str], Optional[str], Optional[list]]] = [
    # Core extracted routers
    ("routers.auth", "router", ["auth"], None, None),
    ("routers.housekeeping", "router", ["housekeeping"], None, None),
    ("routers.departments", "router", ["departments"], None, None),
    ("routers.pms", "router", ["pms"], None, None),
    ("routers.finance", "router", ["finance"], None, None),
    ("routers.reports", "router", ["reports"], None, None),
    ("routers.pms_hardening", "router", ["pms-core"], None, None),
    ("routers.revenue_management", "router", ["revenue-engine"], None, None),
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
    ("modules.observability.alert_router", "router", ["Alert Enrichment"], None, None),
    ("modules.incident.incident_router", "router", ["Incident Response"], None, None),
    ("domains.channel_manager.validation_router", "router", ["CM Provider Validation"], None, None),
    ("domains.channel_manager.providers.hotelrunner_router", "router", ["HotelRunner Integration"], None, None),
    ("domains.channel_manager.providers.hotelrunner_webhook", "router", ["HotelRunner Webhooks & Sync"], None, None),
    ("security.tenant_isolation_router", "router", ["Tenant Isolation v2"], None, None),
    ("ops.pilot_router", "router", ["Pilot Readiness"], None, None),
    # Phase 6 — Runtime Validation & Go-Live
    ("ops.validation_router", "router", ["Runtime Validation & Go-Live"], None, None),
    # Phase 7 — Production Rollout & Pilot Readiness
    ("ops.production_rollout_router", "router", ["Production Rollout"], None, None),
]

# Optional routers with special import paths
_OPTIONAL_ROUTERS: List[Tuple[str, str, List[str], Optional[str], Optional[str]]] = [
    ("desktop_enhancements_endpoints", "desktop_router", ["desktop-enhancements"], "/api", None),
    ("world_class_features", "world_class_router", ["world-class-features"], None, "super_admin"),
    ("advanced_features_endpoints", "advanced_router", ["advanced-features"], "/api", "super_admin"),
    ("comprehensive_modules_endpoints", "router", ["comprehensive-modules"], "/api", "super_admin"),
    ("finance_endpoints", "finance_router", ["finance"], "/api", None),
    ("notification_endpoints", "notification_router", ["notifications"], "/api", None),
    ("media_endpoints", "media_router", ["media"], "/api", None),
    ("faz2_endpoints", "faz2_router", ["faz2"], "/api", None),
    ("agency_endpoints", "agency_router", ["agency-booking"], None, None),
    ("security_2fa", "twofa_router", ["2FA Security"], None, None),
    ("ip_access_control", "ip_router", ["IP Access Control"], None, None),
    ("gdpr_compliance", "gdpr_router", ["GDPR/KVKK Compliance"], None, None),
    ("central_office_endpoints", "co_router", ["Central Office Dashboard"], None, None),
    ("central_pricing_endpoints", "cp_router", ["Central Pricing"], None, None),
    ("cross_property_guests", "cpg_router", ["Cross-Property Guests"], None, None),
    ("ml_real_models", "ml_router", ["ML/AI Models"], None, None),
    ("tenant_isolation", "ti_router", ["Tenant Isolation"], None, None),
    ("pci_dss_compliance", "pci_router", ["PCI DSS Compliance"], None, None),
    ("channel_manager.interfaces.router_registry", "router", ["Channel Manager v2"], None, None),
]


def register_routers(app: FastAPI, api_router, require_super_admin_dep: Callable = None) -> None:
    """Mount all extracted and optional routers onto the app."""
    
    # Mount extracted routers onto the api_router (these all use /api prefix already)
    for mod_path, attr, tags, prefix_override, deps in _EXTRACTED_ROUTERS:
        router = _safe_import(mod_path, attr)
        if router is not None:
            try:
                app.include_router(router, tags=tags)
                print(f"  ✅ {mod_path}")
            except Exception as e:
                print(f"  ❌ {mod_path}: {e}")

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
                print(f"  ✅ {mod_path} (optional)")
            except Exception as e:
                print(f"  ❌ {mod_path}: {e}")
