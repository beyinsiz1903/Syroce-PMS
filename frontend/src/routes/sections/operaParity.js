import {
  FolioRoutingPage, LoyaltyAdminPage, ActivitySchedulerPage, BlockManagementPage,
  ForecastReportsPage, FunctionSpacePage, TrialBalancePage, ProfileUdfPage,
  CateringMenuPage, SuiteConnectingPage, HurdleRatesPage,
} from "./lazyPages";

// Opera-parity additions (Folio Routing, Block Mgmt, Activity Scheduler,
// Loyalty, Forecast, Function Space, Trial Balance, Profile UDF, Catering,
// Suite Connecting, Hurdle Rates).
export function operaParityRoutes({ p }) {
  return [
    { path: "/folio-routing", ...p(FolioRoutingPage) },
    { path: "/loyalty-admin", ...p(LoyaltyAdminPage) },
    { path: "/activities", ...p(ActivitySchedulerPage) },
    { path: "/block-management", ...p(BlockManagementPage), wrapLayout: true, layoutModule: "block_management" },
    { path: "/forecast-reports", ...p(ForecastReportsPage) },
    { path: "/function-space", ...p(FunctionSpacePage) },
    { path: "/trial-balance", ...p(TrialBalancePage) },
    { path: "/profile-udf", ...p(ProfileUdfPage) },
    { path: "/catering", ...p(CateringMenuPage) },
    { path: "/suite-connecting", ...p(SuiteConnectingPage) },
    { path: "/hurdle-rates", ...p(HurdleRatesPage) },
  ];
}
