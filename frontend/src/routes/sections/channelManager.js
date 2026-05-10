import {
  GoLiveReadinessCockpit, ChannelManagerModule, ChannelHub, RevenueHub, AdminHub,
  MappingManager, RoomMappingWizard, HotelRunnerIntegration, ExelyIntegration,
  ARIPushDashboard, UnifiedRateManager, WireFailureDashboard, DataModelDashboard,
  LockdownDashboard, OperatorIncidentPanel, RuntimeCockpitPage, ControlPlane,
} from "./lazyPages";

export function channelManagerRoutes({ p, pa }) {
  return [
    { path: "/channel-connections", type: "redirect", to: "/channels?tab=connections" },
    { path: "/cm-dashboard", type: "redirect", to: "/channels?tab=dashboard" },
    { path: "/go-live-readiness", ...p(GoLiveReadinessCockpit), wrapLayout: true },
    { path: "/channel-manager", ...p(ChannelManagerModule), wrapLayout: true, layoutModule: "channel-manager" },
    { path: "/app/channel-manager", ...p(ChannelManagerModule), wrapLayout: true, layoutModule: "channel-manager" },
    { path: "/channel-ops", type: "redirect", to: "/channels?tab=ops" },
    { path: "/channels", ...p(ChannelHub), wrapLayout: true, layoutModule: "channels" },
    { path: "/app/channels", ...p(ChannelHub), wrapLayout: true, layoutModule: "channels" },
    { path: "/app/revenue-hub", ...p(RevenueHub), wrapLayout: true, layoutModule: "revenue" },
    { path: "/app/admin-hub", ...pa(AdminHub), wrapLayout: true, layoutModule: "admin" },
    { path: "/mapping-manager", ...p(MappingManager), wrapLayout: true, layoutModule: "channel-manager" },
    { path: "/room-mapping-wizard", ...p(RoomMappingWizard), wrapLayout: true },
    { path: "/hotelrunner", ...pa(HotelRunnerIntegration), wrapLayout: true },
    { path: "/hrv2-ops", type: "redirect", to: "/hr?tab=ops" },
    { path: "/exely", ...pa(ExelyIntegration), wrapLayout: true },
    { path: "/ari-push", ...pa(ARIPushDashboard), wrapLayout: true },
    { path: "/rate-manager", ...pa(UnifiedRateManager) },
    { path: "/hr-rate-manager", ...pa(UnifiedRateManager) },
    { path: "/unified-rate-manager", ...p(UnifiedRateManager), wrapLayout: true, layoutModule: "unified_rate_manager" },
    { path: "/wire-failures", ...pa(WireFailureDashboard), wrapLayout: true, layoutModule: "channel-manager" },
    { path: "/data-model", ...pa(DataModelDashboard), wrapLayout: true },
    { path: "/lockdown", ...pa(LockdownDashboard), wrapLayout: true },
    { path: "/incidents", ...pa(OperatorIncidentPanel), wrapLayout: true },
    { path: "/runtime-cockpit", ...pa(RuntimeCockpitPage), wrapLayout: true },
    { path: "/control-plane", ...pa(ControlPlane), wrapLayout: true },
  ];
}
