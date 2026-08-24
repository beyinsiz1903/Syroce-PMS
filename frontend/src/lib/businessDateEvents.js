export const BUSINESS_DATE_CHANGED_EVENT = "pms:business-date-changed";

export function emitBusinessDateChanged(businessDate, metadata = null) {
  if (!businessDate || typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(BUSINESS_DATE_CHANGED_EVENT, {
    detail: { businessDate, metadata },
  }));
}
