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
  const C = _map.get(path);
  if (C && typeof C.preload === "function") {
    try { C.preload(); } catch { /* ignore */ }
  }
}
