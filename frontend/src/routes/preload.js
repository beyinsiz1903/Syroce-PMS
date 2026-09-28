import { prefetchAdminManagementRoute } from '@/lib/adminManagementQueries';

const _map = new Map();

export function registerRoutes(routeConfigs) {
  if (!Array.isArray(routeConfigs)) return;
  _map.clear();
  for (const rc of routeConfigs) {
    if (rc?.path && rc?.component) _map.set(rc.path, rc.component);
  }
}

export function preloadRoute(path) {
  if (!path) return;
  // Super-admin switches between these two datasets frequently. Start the
  // request when the menu opens/receives hover instead of after navigation.
  void prefetchAdminManagementRoute(path)?.catch(() => {});
  const C = _map.get(path);
  if (C && typeof C.preload === "function") {
    try { C.preload(); } catch { /* ignore */ }
  }
}
