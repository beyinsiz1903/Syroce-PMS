// Real-user monitoring is deliberately limited to the operational entry
// points people use repeatedly during a hotel shift. It is not a list of all
// implementation routes: detail/redirect routes would turn a route change
// into noisy duplicate samples and would not represent a module entry.
//
// The backend mirrors these paths and thresholds because it owns retention,
// aggregation and alerting. Keep this list grouped by user-facing workspace
// rather than by bundle or source-file ownership.
export const RUM_ROUTE_BUDGETS = Object.freeze({
  '/app/dashboard': { module: 'dashboard', routeMs: 5_000, lcpMs: 4_000, inpMs: 500, apiP95Ms: 2_000 },
  '/app/pms': { module: 'pms', routeMs: 6_000, lcpMs: 4_500, inpMs: 600, apiP95Ms: 2_500 },
  '/app/reservation-calendar': { module: 'calendar', routeMs: 6_500, lcpMs: 4_500, inpMs: 500, apiP95Ms: 2_500 },
  '/arrival-list': { module: 'arrivals', routeMs: 5_000, lcpMs: 4_000, inpMs: 500, apiP95Ms: 2_000 },
  '/departure-list': { module: 'departures', routeMs: 5_000, lcpMs: 4_000, inpMs: 500, apiP95Ms: 2_000 },
  '/night-audit': { module: 'night-audit', routeMs: 6_000, lcpMs: 4_500, inpMs: 600, apiP95Ms: 2_500 },
  '/housekeeping': { module: 'housekeeping', routeMs: 5_500, lcpMs: 4_000, inpMs: 500, apiP95Ms: 2_000 },
  '/pos': { module: 'pos', routeMs: 5_500, lcpMs: 4_000, inpMs: 500, apiP95Ms: 2_000 },
  '/app/cashier': { module: 'cashier', routeMs: 5_500, lcpMs: 4_000, inpMs: 500, apiP95Ms: 2_000 },
  '/app/invoices': { module: 'invoices', routeMs: 6_000, lcpMs: 4_500, inpMs: 600, apiP95Ms: 2_500 },
  '/app/general-ledger': { module: 'general-ledger', routeMs: 6_000, lcpMs: 4_500, inpMs: 600, apiP95Ms: 2_500 },
  '/app/raporlar': { module: 'reports', routeMs: 6_500, lcpMs: 4_500, inpMs: 600, apiP95Ms: 2_500 },
  '/app/rms': { module: 'rms', routeMs: 6_000, lcpMs: 4_500, inpMs: 600, apiP95Ms: 2_500 },
  '/sales': { module: 'sales', routeMs: 5_500, lcpMs: 4_000, inpMs: 500, apiP95Ms: 2_000 },
  '/app/guest-relations': { module: 'guest-relations', routeMs: 5_500, lcpMs: 4_000, inpMs: 500, apiP95Ms: 2_000 },
  '/app/procurement': { module: 'procurement', routeMs: 6_000, lcpMs: 4_500, inpMs: 600, apiP95Ms: 2_500 },
  '/app/mice': { module: 'mice', routeMs: 6_000, lcpMs: 4_500, inpMs: 600, apiP95Ms: 2_500 },
  '/app/channel-manager': { module: 'channel-manager', routeMs: 6_000, lcpMs: 4_500, inpMs: 600, apiP95Ms: 2_500 },
  '/channels': { module: 'channels', routeMs: 5_500, lcpMs: 4_000, inpMs: 500, apiP95Ms: 2_000 },
  '/app/integration-hub': { module: 'integration-hub', routeMs: 6_000, lcpMs: 4_500, inpMs: 600, apiP95Ms: 2_500 },
  '/app/settings': { module: 'settings', routeMs: 5_000, lcpMs: 4_000, inpMs: 500, apiP95Ms: 2_000 },
  '/app/folio-management': { module: 'folio-management', routeMs: 5_500, lcpMs: 4_000, inpMs: 500, apiP95Ms: 2_000 },
  '/app/room-requests': { module: 'room-requests', routeMs: 5_500, lcpMs: 4_000, inpMs: 500, apiP95Ms: 2_000 },
  '/app/tasks': { module: 'tasks', routeMs: 5_000, lcpMs: 4_000, inpMs: 500, apiP95Ms: 2_000 },
  '/hr': { module: 'hr', routeMs: 6_000, lcpMs: 4_500, inpMs: 600, apiP95Ms: 2_500 },
  '/app/xchange': { module: 'xchange', routeMs: 5_500, lcpMs: 4_000, inpMs: 500, apiP95Ms: 2_000 },
  '/app/revenue-hub': { module: 'revenue-hub', routeMs: 6_000, lcpMs: 4_500, inpMs: 600, apiP95Ms: 2_500 },
  '/messaging-center': { module: 'messaging', routeMs: 5_500, lcpMs: 4_000, inpMs: 500, apiP95Ms: 2_000 },
});

export const RUM_ROUTE_PATHS = Object.freeze(Object.keys(RUM_ROUTE_BUDGETS));

export const isRumRoute = (pathname) => Object.hasOwn(RUM_ROUTE_BUDGETS, pathname);
