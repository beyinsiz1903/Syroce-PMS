import {
  DisplacementAnalysis, GelirYonetimiPage, AIZekaPage, AnalitikRaporlarPage,
  RevenueEngineDashboard, DataIntelligenceDashboard, MessagingDashboard,
  MLSchedulerDashboard, RevenueAutopilotDashboard, AnalyticsExportDashboard,
  RMSModule,
} from "./lazyPages";

export function revenueRmsRoutes({ p }) {
  return [
    // ── Revenue & Analytics (Consolidated) ───────────
    { path: "/displacement-analysis", ...p(DisplacementAnalysis) },
    { path: "/app/displacement-analysis", ...p(DisplacementAnalysis) },
    { path: "/app/gelir-yonetimi", ...p(GelirYonetimiPage) },
    { path: "/app/ai-zeka", ...p(AIZekaPage), wrapLayout: true, layoutModule: "ai" },
    { path: "/app/analitik", ...p(AnalitikRaporlarPage), wrapLayout: true, layoutModule: "rms" },

    // ── Revenue & Analytics (Legacy routes — backward compat) ──
    { path: "/revenue-engine", ...p(RevenueEngineDashboard), wrapLayout: true, layoutModule: "rms" },
    { path: "/data-intelligence", ...p(DataIntelligenceDashboard) },
    { path: "/messaging-dashboard", ...p(MessagingDashboard), wrapLayout: true, layoutModule: "messaging" },
    { path: "/ml-scheduler", ...p(MLSchedulerDashboard) },
    { path: "/revenue-autopilot-v2", ...p(RevenueAutopilotDashboard) },
    { path: "/analytics-export", ...p(AnalyticsExportDashboard) },

    // ── RMS (feature-gated) ────────────────────────────
    { path: "/rms", type: "feature", featureKey: "hidden_rms", ...p(RMSModule) },
    { path: "/app/rms", type: "feature", featureKey: "hidden_rms", ...p(RMSModule) },
  ];
}
