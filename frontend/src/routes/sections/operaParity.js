import {
  FolioRoutingPage, LoyaltyAdminPage, ActivitySchedulerPage, BlockManagementPage,
  ForecastReportsPage, FunctionSpacePage, TrialBalancePage, ProfileUdfPage,
  CateringMenuPage, SuiteConnectingPage, HurdleRatesPage,
} from "./lazyPages";

// Opera-parity additions (Folio Routing, Block Mgmt, Activity Scheduler,
// Loyalty, Forecast, Function Space, Trial Balance, Profile UDF, Catering,
// Suite Connecting, Hurdle Rates).
export function operaParityRoutes({ p, pm }) {
  return [
    {
      path: "/folio-routing",
      ...pm(FolioRoutingPage, "pms", undefined, { strict: true }),
      wrapLayout: true,
      layoutModule: "pms",
    },
    { path: "/loyalty-admin", ...p(LoyaltyAdminPage) },
    { path: "/activities", ...p(ActivitySchedulerPage) },
    {
      path: "/block-management",
      ...pm(BlockManagementPage, "pms", undefined, { strict: true }),
      wrapLayout: true,
      layoutModule: "block_management",
    },
    {
      path: "/forecast-reports",
      ...pm(ForecastReportsPage, "basic_reporting", undefined, { strict: true }),
      wrapLayout: true,
      layoutModule: "reports_basic",
    },
    {
      path: "/function-space",
      ...pm(FunctionSpacePage, "mice", undefined, { strict: true }),
      wrapLayout: true,
      layoutModule: "mice",
    },
    {
      path: "/trial-balance",
      ...pm(TrialBalancePage, "reports", undefined, { strict: true }),
      wrapLayout: true,
      layoutModule: "reports_basic",
    },
    {
      path: "/profile-udf",
      ...pm(ProfileUdfPage, "pms", undefined, { strict: true }),
      wrapLayout: true,
      layoutModule: "pms",
    },
    {
      path: "/catering",
      ...pm(CateringMenuPage, "mice", undefined, { strict: true }),
      wrapLayout: true,
      layoutModule: "mice",
    },
    {
      path: "/suite-connecting",
      ...pm(SuiteConnectingPage, "pms", undefined, { strict: true }),
      wrapLayout: true,
      layoutModule: "settings",
    },
    { path: "/hurdle-rates", ...p(HurdleRatesPage) },
  ];
}
