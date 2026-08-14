export const NIGHT_AUDIT_RUN_TIMEOUT_MS = 120_000;

export function isNightAuditTimeout(error) {
  return error?.code === "ECONNABORTED" || error?.code === "ETIMEDOUT";
}

export function nextIsoDate(isoDate) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(isoDate || "")) return null;
  const [year, month, day] = isoDate.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
}

export function confirmsNightAuditAdvance(requestedDate, currentDate) {
  return Boolean(currentDate && currentDate === nextIsoDate(requestedDate));
}
