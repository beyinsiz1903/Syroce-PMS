import { lazy } from "react";

const _cache = new WeakMap();

// Sentinel chunk-error message for a dynamic import that RESOLVED but handed
// back an unusable module (no default export). KEEP THIS STRING IN SYNC with the
// CHUNK_ERR lists in `frontend/index.html` (stale-chunk self-heal matcher) and
// `frontend/src/index.jsx` (Sentry beforeSend), so this case is healed/dropped
// exactly like a fetch-level chunk error.
export const INVALID_CHUNK_MODULE_MSG = "Dynamically imported module is invalid";

// A dynamic import can RESOLVE (no network / vite:preloadError) yet return an
// invalid module — e.g. a stale deploy served the chunk as index.html, or a
// Safari cache quirk returned an empty module. React.lazy then throws an opaque
// "undefined is not an object (evaluating '..._result.default')" that the
// stale-chunk self-heal does NOT recognize, so the tab is stuck and the error
// pages Sentry. Normalize that case into a recognized chunk-error class so the
// existing one-shot reload heals it; a recurrence AFTER the reload still
// surfaces (the self-heal latch is spent and the Sentry heal-flag is false), so
// a genuinely broken deploy is never masked.
function guardModule(mod) {
  if (!mod || mod.default == null) {
    throw new Error(INVALID_CHUNK_MODULE_MSG + " (chunk load)");
  }
  return mod;
}

export function lazyWithPreload(factory) {
  const guardedFactory = () => factory().then(guardModule);
  const Component = lazy(guardedFactory);
  Component.preload = () => {
    if (_cache.has(factory)) return _cache.get(factory);
    const promise = guardedFactory().catch((err) => {
      _cache.delete(factory);
      throw err;
    });
    _cache.set(factory, promise);
    return promise;
  };
  return Component;
}
