import {
  DataPipelineDashboard, EventBusDashboard, SystemHealthDashboard,
  ObservabilityDashboard, SecurityHub, RuntimeInfrastructureDashboard,
  InfraHardeningDashboard, ProductionGoLiveDashboard, PlatformScalingDashboard,
  PIIStrictModeDashboard, IntegrationObservabilityDashboard,
} from "./lazyPages";

export function infrastructureRoutes({ p, pa }) {
  const adminRoute = pa || p;
  return [
    { path: "/data-pipeline", ...p(DataPipelineDashboard) },
    { path: "/event-bus", ...p(EventBusDashboard) },
    { path: "/system-health", ...p(SystemHealthDashboard), wrapLayout: true, layoutModule: "system_health" },
    { path: "/observability", ...adminRoute(ObservabilityDashboard), wrapLayout: true, layoutModule: "observability" },
    { path: "/integration-observability", ...adminRoute(IntegrationObservabilityDashboard), wrapLayout: true },
    // Compatibility alias: the catalog-based, super-admin-protected screen is
    // the single canonical place for platform integration keys. Preserve a
    // credential hash so existing deep links still focus the same key.
    { path: "/integration-credentials", type: "redirect", to: "/admin/integration-credentials", preserveLocation: true },
    { path: "/security-hardening", type: "redirect", to: "/security?tab=hardening" },
    { path: "/security", ...p(SecurityHub), wrapLayout: true, layoutModule: "security" },
    { path: "/app/security", ...p(SecurityHub), wrapLayout: true, layoutModule: "security" },
    { path: "/runtime-infrastructure", ...p(RuntimeInfrastructureDashboard) },
    { path: "/infra-hardening", ...adminRoute(InfraHardeningDashboard), wrapLayout: true },
    { path: "/production-golive", ...adminRoute(ProductionGoLiveDashboard), wrapLayout: true },
    { path: "/platform-scaling", ...p(PlatformScalingDashboard), wrapLayout: true },
    { path: "/enterprise-live", type: "redirect", to: "/executive" },
    { path: "/pii-strict-mode", ...p(PIIStrictModeDashboard) },
  ];
}
