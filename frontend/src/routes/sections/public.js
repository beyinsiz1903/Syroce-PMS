import {
  LandingPage, RoomRequestPage, PublicReviewPage, PrivacyPolicy,
  PmsLiteLanding, AgencyPortalDashboard, B2BApiDocs, SimpleAdminPanel,
  ResetPasswordPage, PreCheckinPage,
} from "./lazyPages";

export function publicRoutes({ pa }) {
  return [
    { path: "/landing", type: "public", component: LandingPage },
    { path: "/g/room/:tenantId/:roomId", type: "public", component: RoomRequestPage },
    { path: "/review/:token", type: "public", component: PublicReviewPage },
    { path: "/privacy-policy", type: "public", component: PrivacyPolicy },
    { path: "/gizlilik", type: "public", component: PrivacyPolicy },
    { path: "/pms-lite", type: "public", component: PmsLiteLanding },
    { path: "/agency-portal", type: "public", component: AgencyPortalDashboard },
    { path: "/b2b/docs", ...pa(B2BApiDocs) },
    { path: "/system-status", type: "public", component: SimpleAdminPanel },
    { path: "/auth/reset-password", type: "public", component: ResetPasswordPage },
    { path: "/precheckin/:token", type: "public", component: PreCheckinPage },
  ];
}
