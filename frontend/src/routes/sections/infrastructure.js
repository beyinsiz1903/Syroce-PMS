import {
  DataPipelineDashboard, EventBusDashboard, SystemHealthDashboard,
  ObservabilityDashboard, SecurityHub, RuntimeInfrastructureDashboard,
  InfraHardeningDashboard, ProductionGoLiveDashboard, PlatformScalingDashboard,
  PIIStrictModeDashboard, IntegrationObservabilityDashboard, CredentialVaultDashboard,
} from "./lazyPages";

export function infrastructureRoutes({ p }) {
  return [
    { path: "/data-pipeline", ...p(DataPipelineDashboard) },
    { path: "/event-bus", ...p(EventBusDashboard) },
    { path: "/system-health", ...p(SystemHealthDashboard), wrapLayout: true, layoutModule: "system_health" },
    { path: "/observability", ...p(ObservabilityDashboard) },
    { path: "/integration-observability", ...p(IntegrationObservabilityDashboard), wrapLayout: true },
    { path: "/integration-credentials", ...p(CredentialVaultDashboard), wrapLayout: true },
    { path: "/security-hardening", type: "redirect", to: "/security?tab=hardening" },
    { path: "/security", ...p(SecurityHub), wrapLayout: true, layoutModule: "security" },
    { path: "/app/security", ...p(SecurityHub), wrapLayout: true, layoutModule: "security" },
    { path: "/runtime-infrastructure", ...p(RuntimeInfrastructureDashboard) },
    { path: "/infra-hardening", ...p(InfraHardeningDashboard), wrapLayout: true },
    { path: "/production-golive", ...p(ProductionGoLiveDashboard), wrapLayout: true },
    { path: "/platform-scaling", ...p(PlatformScalingDashboard), wrapLayout: true },
    { path: "/enterprise-live", type: "redirect", to: "/executive" },
    { path: "/pii-strict-mode", ...p(PIIStrictModeDashboard) },
  ];
}
