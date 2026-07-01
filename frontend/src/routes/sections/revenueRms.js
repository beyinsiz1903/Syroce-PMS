import {
  DisplacementAnalysis, GelirYonetimiPage, AIZekaPage, AnalitikRaporlarPage,
  RevenueEngineDashboard, DataIntelligenceDashboard, MessagingDashboard,
  MLSchedulerDashboard, RevenueAutopilotDashboard, AnalyticsExportDashboard,
  RMSModule,
} from "./lazyPages";

export function revenueRmsRoutes({ p }) {
  return [
    // ── Revenue & Analytics (Consolidated) ───────────
    { path: "/displacement-analysis", type: "redirect", to: "/app/rms" },
    { path: "/app/displacement-analysis", type: "redirect", to: "/app/rms" },
    { path: "/app/gelir-yonetimi", type: "redirect", to: "/app/rms" },
    { path: "/app/ai-zeka", type: "redirect", to: "/ai-chatbot" },
    { path: "/app/analitik", type: "redirect", to: "/app/raporlar" },

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
