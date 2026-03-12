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
