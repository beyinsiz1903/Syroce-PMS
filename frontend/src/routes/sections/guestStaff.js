import {
  SelfCheckin, DigitalKey, UpsellStore, StaffMobileApp, StaffRoomServiceOrders,
  OTAMessagingHub, MessagingCenter, SalesModule, TravelAgentARAP,
  AgencyRequests, IncomingAgencyContracts, AgencyManagement,
  AgencyContentDistribution, B2BAnalyticsDashboard, ReportScheduler,
} from "./lazyPages";

export function guestStaffRoutes({ p }) {
  return [
    // ── Guest Features ─────────────────────────────────
    { path: "/guest/checkin/:bookingId", ...p(SelfCheckin) },
    { path: "/guest/digital-key/:bookingId", ...p(DigitalKey) },
    { path: "/guest/upsell/:bookingId", ...p(UpsellStore) },

    // ── Staff & OTA ────────────────────────────────────
    { path: "/staff/mobile", ...p(StaffMobileApp) },
    { path: "/staff/room-service", ...p(StaffRoomServiceOrders), wrapLayout: true, layoutModule: "pos" },
    { path: "/ota-messaging-hub", ...p(OTAMessagingHub) },
    { path: "/messaging-center", ...p(MessagingCenter), wrapLayout: true, layoutModule: "messaging" },
    { path: "/sales", ...p(SalesModule), wrapLayout: true, layoutModule: "sales" },
    { path: "/travel-agent-arap", ...p(TravelAgentARAP), wrapLayout: true },
    { path: "/app/travel-agent-arap", ...p(TravelAgentARAP), wrapLayout: true },
    { path: "/agency-requests", ...p(AgencyRequests) },
    { path: "/app/incoming-agency-contracts", ...p(IncomingAgencyContracts), wrapLayout: true },
    { path: "/agency-management", ...p(AgencyManagement), wrapLayout: true },
    { path: "/agency-content", ...p(AgencyContentDistribution), wrapLayout: true },
    { path: "/b2b-analytics", ...p(B2BAnalyticsDashboard), wrapLayout: true, layoutModule: "b2b-analytics" },
    { path: "/report-scheduler", ...p(ReportScheduler), wrapLayout: true, layoutModule: "report-scheduler" },
  ];
}
