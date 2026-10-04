// Keep money input as text while the user is typing. Native number inputs are
// locale-dependent and can turn a Turkish decimal comma into an unexpected
// value (or expose increment controls) before the payment is submitted.
const EDITING_MONEY_PATTERN = /^\d*(?:[.,]\d{0,2})?$/;

export function isMoneyInput(value) {
  return EDITING_MONEY_PATTERN.test(String(value ?? '').trim());
}

/**
 * Normalizes an operator-entered monetary amount without relying on the
 * browser's locale-dependent number input. Turkish operators commonly enter
 * `150,74`; `parseFloat` silently turns that into `150`.
 */
export function parseMoneyInput(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : Number.NaN;

  const raw = String(value ?? '').trim().replace(/\s/g, '');
  if (!raw) return Number.NaN;

  const lastComma = raw.lastIndexOf(',');
  const lastDot = raw.lastIndexOf('.');
  const decimalIndex = Math.max(lastComma, lastDot);
  const integerPart = decimalIndex >= 0 ? raw.slice(0, decimalIndex) : raw;
  const fractionPart = decimalIndex >= 0 ? raw.slice(decimalIndex + 1) : '';

  // A separator may be repeated only as the *other* thousands separator:
  // 1.500,74 and 1,500.74 are valid; 150,74,2 is not.
  const decimalSeparator = decimalIndex >= 0 ? raw[decimalIndex] : null;
  const thousandsSeparator = decimalSeparator === ',' ? '.' : ',';
  const containsRepeatedDecimal = decimalSeparator && integerPart.includes(decimalSeparator);
  const groupedInteger = integerPart.includes(thousandsSeparator);
  const validInteger = groupedInteger
    ? new RegExp(`^\\d{1,3}(?:\\${thousandsSeparator}\\d{3})*$`).test(integerPart)
    : /^\d+$/.test(integerPart);
  const normalizedInteger = integerPart.replace(/[.,]/g, '');
  if (containsRepeatedDecimal || !validInteger || !/^\d+$/.test(normalizedInteger) || (decimalIndex >= 0 && !/^\d+$/.test(fractionPart))) {
    return Number.NaN;
  }

  return Number(`${normalizedInteger}${decimalIndex >= 0 ? `.${fractionPart}` : ''}`);
}

export function isValidMoneyInput(value, { min = 0, max = Number.POSITIVE_INFINITY } = {}) {
  const amount = parseMoneyInput(value);
  return Number.isFinite(amount) && amount >= min && amount <= max;
}

export const moneyInputProps = {
  type: 'text',
  inputMode: 'decimal',
  autoComplete: 'off',
};
