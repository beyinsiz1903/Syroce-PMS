import ProductState from "@/components/shared/ProductState";
import { useTranslation } from "react-i18next";

const SETUP_STATUSES = new Set([402]);

const MODULE_LABEL_KEYS = {
  revenue_management: "navKeys.gelir_yonetimi",
  pos_fnb: "navKeys.pos_dashboard",
  channel_manager: "navKeys.channel_manager",
  night_audit: "navKeys.night_audit",
  advanced_analytics: "navGroups.advanced",
  basic_reporting: "navKeys.reports_basic",
  booking_engine: "navKeys.wbe_settings",
};

export function friendlyModuleName(moduleName, t) {
  if (!moduleName) return t("moduleAvailability.defaultName", "Bu modül");
  const translationKey = MODULE_LABEL_KEYS[moduleName] || `navKeys.${moduleName}`;
  const translated = t(translationKey, { defaultValue: translationKey });
  if (translated !== translationKey) return translated;
  if (!/^[a-z0-9_.-]+$/.test(moduleName)) return moduleName;
  return moduleName
    .replace(/[_.-]+/g, " ")
    .replace(/^./, (letter) => letter.toUpperCase());
}

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
  const { t } = useTranslation();
  const state = reason === "disabled" || reason === "setup" ? "setup" : reason === "temporary" ? "error" : reason;
  const displayName = friendlyModuleName(moduleName, t);
  return <div data-testid="module-availability-state" data-state={reason}><ProductState moduleName={displayName} state={state} onRetry={onRetry} compact={compact} /></div>;
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
