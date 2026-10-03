import ProductState from "@/components/shared/ProductState";

const SETUP_STATUSES = new Set([402]);

export function moduleLoadState(error) {
  const status = error?.response?.status;
  if (SETUP_STATUSES.has(status)) return "setup";
  if (status === 401 || status === 403) return "forbidden";
  if (status === 429) return "throttled";
  return "error";
}

export function ModuleAvailabilityState({
  moduleName = "Bu modül",
  reason = "disabled",
  onRetry,
  compact = false,
}) {
  const state = reason === "disabled" || reason === "setup" ? "setup" : reason === "temporary" ? "error" : reason;
  return <div data-testid="module-availability-state" data-state={reason}><ProductState moduleName={moduleName} state={state} onRetry={onRetry} compact={compact} /></div>;
}

export function ModuleLoadError({ moduleName, error, onRetry, compact = false }) {
  return (
    <ModuleAvailabilityState
      moduleName={moduleName}
      reason={moduleLoadState(error)}
      onRetry={onRetry}
      compact={compact}
    />
  );
}
