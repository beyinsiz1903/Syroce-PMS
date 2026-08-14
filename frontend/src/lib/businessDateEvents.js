export const BUSINESS_DATE_CHANGED_EVENT = "pms:business-date-changed";

export function emitBusinessDateChanged(businessDate) {
  if (!businessDate || typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(BUSINESS_DATE_CHANGED_EVENT, {
    detail: { businessDate },
  }));
}
