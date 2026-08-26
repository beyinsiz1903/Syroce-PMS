import {
  OnlineCheckin, FlashReport, GroupSales, SalesCRM, ServiceRecovery,
  SpaWellness, SpaDiningPackages, MultiProperty, StaffManagement, StaffProfile, ShiftPlannerPage,
  HRHub, FnBComplete, FnbBeoGenerator, KitchenDisplay,
  AIChatbot, DynamicPricing, AIWhatsAppConcierge, PredictiveAnalytics,
  SocialMediaRadar, RevenueAutopilot, RevenueAutopilotMonitor,
} from "./lazyPages";

export function hotelFeaturesAiRoutes({ p, pm }) {
  return [
    // ── 5-Star Hotel Features ──────────────────────────
    { path: "/online-checkin", ...p(OnlineCheckin) },
    { path: "/flash-report", ...p(FlashReport) },
    { path: "/group-sales", ...p(GroupSales), wrapLayout: true, layoutModule: "group-sales" },
    { path: "/sales-crm", ...p(SalesCRM), wrapLayout: true, layoutModule: "sales-crm" },
    { path: "/service-recovery", ...p(ServiceRecovery), wrapLayout: true },
    { path: "/spa-wellness", ...pm(SpaWellness, "spa", undefined, { strict: true }), wrapLayout: true, layoutModule: "spa" },
    { path: "/spa-dining-packages", ...pm(SpaDiningPackages, "spa", undefined, { strict: false }), wrapLayout: true, layoutModule: "spa" },
    { path: "/app/multi-property", ...p(MultiProperty) },
    { path: "/multi-property", type: "redirect", to: "/app/multi-property" },
    { path: "/staff-management", ...pm(StaffManagement, "hr", undefined, { strict: true }), wrapLayout: true, layoutModule: "hr" },
    { path: "/staff/:id", ...pm(StaffProfile, "hr", undefined, { strict: true }), wrapLayout: true, layoutModule: "hr" },
    { path: "/hr/shifts", ...pm(ShiftPlannerPage, "hr", undefined, { strict: true }), wrapLayout: true, layoutModule: "hr" },
    { path: "/hr-complete", type: "redirect", to: "/hr?tab=suite" },
    { path: "/hr", ...pm(HRHub, "hr", undefined, { strict: true }), wrapLayout: true, layoutModule: "hr" },
    { path: "/app/hr", ...pm(HRHub, "hr", undefined, { strict: true }), wrapLayout: true, layoutModule: "hr" },
    { path: "/fnb-complete", ...p(FnBComplete), wrapLayout: true, layoutModule: "fnb" },
    { path: "/fnb/beo-generator", ...p(FnbBeoGenerator), wrapLayout: true, layoutModule: "fnb" },
    { path: "/kitchen-display", ...p(KitchenDisplay) },

    // ── AI Module-gated ────────────────────────────────
    { path: "/ai-chatbot", type: "redirect", to: "/app/ai?module=ai-chatbot" },
    { path: "/dynamic-pricing", ...pm(DynamicPricing, "ai_pricing") },
    { path: "/ai-whatsapp-concierge", ...pm(AIWhatsAppConcierge, "ai_whatsapp") },
    { path: "/predictive-analytics", ...pm(PredictiveAnalytics, "ai_predictive") },
    { path: "/social-media-radar", ...pm(SocialMediaRadar, "ai_social_radar") },
    { path: "/revenue-autopilot", ...pm(RevenueAutopilot, "ai_revenue_autopilot") },
    { path: "/revenue-autopilot/monitor", ...pm(RevenueAutopilotMonitor, "ai_revenue_autopilot") },
  ];
}
