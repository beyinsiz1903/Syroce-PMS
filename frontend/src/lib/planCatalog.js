import { useEffect, useSyncExternalStore } from 'react';
import axios from 'axios';

// Which modules each plan includes comes from the server only
// (GET /subscription/plan-modules → defaults_by_tier, the map the server
// enforces). Until it has loaded nothing is "included": screens that need it
// wait instead of guessing from a second, local definition.

let catalog = null;
let pending = null;
let failed = false;
const listeners = new Set();

const notify = () => listeners.forEach((listener) => listener());

const TIER_ALIASES = { pro: 'professional', ultra: 'enterprise' };
export const normalizeTier = (tier) => {
  const value = String(tier || 'basic').toLowerCase();
  return TIER_ALIASES[value] || value;
};

export function loadPlanCatalog(api = axios) {
  if (catalog) return Promise.resolve(catalog);
  if (!pending) {
    failed = false;
    pending = api.get('/subscription/plan-modules')
      .then(({ data }) => {
        catalog = data?.defaults_by_tier || null;
        failed = !catalog;
        return catalog;
      })
      .catch(() => {
        failed = true;
        return null;
      })
      .finally(() => {
        pending = null;
        notify();
      });
  }
  return pending;
}

export const planCatalogSnapshot = () => catalog;

export function planIncludes(tier, key) {
  return catalog?.[normalizeTier(tier)]?.[key] === true;
}

const subscribe = (listener) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export function usePlanCatalog() {
  const current = useSyncExternalStore(subscribe, () => catalog);
  const error = useSyncExternalStore(subscribe, () => failed);
  useEffect(() => {
    if (!catalog) loadPlanCatalog();
  }, []);
  return { catalog: current, ready: Boolean(current), error, retry: () => loadPlanCatalog() };
}

// Tests and stories only.
export function setPlanCatalogForTests(value) {
  catalog = value;
  failed = false;
  notify();
}
