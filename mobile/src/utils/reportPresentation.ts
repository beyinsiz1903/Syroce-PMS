import { reservationAmountLabel, reservationCurrency } from './reservationPresentation';

/** Omitted executive metrics and failed reads must not look like real zero. */
export function reportCountLabel(value: unknown): string {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? String(value) : '—';
}

export function reportAmountLabel(amount: unknown, currency: unknown): string {
  const code = reservationCurrency(currency);
  return typeof amount === 'number' && Number.isFinite(amount) && code
    ? reservationAmountLabel(amount, code)
    : '—';
}

export type ReportCurrencyBucket = { currency?: string; total?: number };
export type ReportCurrencyBuckets =
  | { kind: 'unavailable'; buckets: [] }
  | { kind: 'empty'; buckets: [] }
  | { kind: 'data'; buckets: ReportCurrencyBucket[] };

/** The legacy aggregate can contain mixed currencies. Only the API's explicit
 * bucket keys identify their currency; a missing breakdown is not empty AR. */
export function reportCurrencyBuckets(value: unknown): ReportCurrencyBuckets {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return { kind: 'unavailable', buckets: [] };
  const entries = Object.entries(value);
  if (!entries.length) return { kind: 'empty', buckets: [] };
  return {
    kind: 'data',
    buckets: entries.map(([currency, raw]) => {
      const total = raw && typeof raw === 'object' ? (raw as { total?: unknown }).total : undefined;
      return {
        currency: reservationCurrency(currency),
        total: typeof total === 'number' && Number.isFinite(total) ? total : undefined,
      };
    }),
  };
}
