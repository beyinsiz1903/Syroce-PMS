// Keep money input as text while the user is typing. Native number inputs are
// locale-dependent and can turn a Turkish decimal comma into an unexpected
// value (or expose increment controls) before the payment is submitted.
const EDITING_MONEY_PATTERN = /^\d*(?:[.,]\d{0,2})?$/;
const COMPLETE_MONEY_PATTERN = /^\d+(?:[.,]\d{1,2})?$/;

export function isMoneyInput(value) {
  return EDITING_MONEY_PATTERN.test(String(value ?? '').trim());
}

export function parseMoneyInput(value) {
  const text = String(value ?? '').trim();
  if (!COMPLETE_MONEY_PATTERN.test(text)) return null;

  const amount = Number(text.replace(',', '.'));
  return Number.isFinite(amount) ? amount : null;
}
