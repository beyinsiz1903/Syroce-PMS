const SYMBOLS = {
  TRY: '\u20ba',
  USD: '$',
  EUR: '\u20ac',
  GBP: '\u00a3',
  JPY: '\u00a5',
  CHF: 'CHF',
  AED: 'AED',
  SAR: 'SAR',
};

const LOCALE_BY_CURRENCY = {
  TRY: 'tr-TR',
  USD: 'en-US',
  EUR: 'de-DE',
  GBP: 'en-GB',
  JPY: 'ja-JP',
  CHF: 'de-CH',
};

export function currencySymbol(code) {
  if (!code) return SYMBOLS.TRY;
  const c = String(code).toUpperCase();
  return SYMBOLS[c] || c;
}

export function localeForCurrency(code) {
  if (!code) return 'tr-TR';
  return LOCALE_BY_CURRENCY[String(code).toUpperCase()] || 'tr-TR';
}

export function formatCurrency(amount, currency = 'TRY', opts = {}) {
  const value = Number(amount);
  const safeValue = Number.isFinite(value) ? value : 0;
  const code = (currency || 'TRY').toUpperCase();
  const locale = opts.locale || localeForCurrency(code);
  const decimals = opts.decimals !== undefined
    ? opts.decimals
    : (Math.abs(safeValue) >= 1000 && opts.compactDecimals !== false ? 0 : 2);
  try {
    return new Intl.NumberFormat(locale, {
      style: 'currency',
      currency: code,
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(safeValue);
  } catch {
    const sym = currencySymbol(code);
    return `${sym}${safeValue.toLocaleString(locale, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })}`;
  }
}

export function formatAmount(amount, currency = 'TRY', opts = {}) {
  const value = Number(amount);
  const safeValue = Number.isFinite(value) ? value : 0;
  const code = (currency || 'TRY').toUpperCase();
  const locale = opts.locale || localeForCurrency(code);
  const decimals = opts.decimals !== undefined ? opts.decimals : 2;
  return safeValue.toLocaleString(locale, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}
