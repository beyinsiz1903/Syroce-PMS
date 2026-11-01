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

export function reportPercentLabel(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value) ? `%${value.toFixed(1)}` : '—';
}

/** Never use an arbitrary legacy scalar as TRY when its bucket map is absent. */
export function reportTotalsLabel(value: unknown): string {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return '—';
  const entries = Object.entries(value);
  if (!entries.length) return 'Kayıt yok';
  return entries.map(([currency, amount]) => reportAmountLabel(amount, currency)).join(' · ');
}

export function reportArLabel(value: unknown): string {
  const result = reportCurrencyBuckets(value);
  return result.kind === 'unavailable' ? '—' : result.kind === 'empty' ? 'Kayıt yok'
    : result.buckets.map((bucket) => reportAmountLabel(bucket.total, bucket.currency)).join(' · ');
}

export function postedRoomKpis(value: unknown, expectedDate?: string) {
  const missing = { date: undefined, adr: '—', revpar: '—', postingPending: false };
  if (!value || typeof value !== 'object') return missing;
  const data = value as { date?: unknown; revenue?: { basis?: string; adr_by_currency?: unknown; rev_par_by_currency?: unknown; posting_pending?: boolean } };
  if (typeof data.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(data.date)
    || (expectedDate && data.date !== expectedDate)
    || data.revenue?.basis !== 'posted_folio_charges_plus_untransferred_pos') return missing;
  return { date: data.date, adr: reportTotalsLabel(data.revenue.adr_by_currency),
    revpar: reportTotalsLabel(data.revenue.rev_par_by_currency), postingPending: data.revenue.posting_pending === true };
}

/** Raw expense rows cannot be added across currencies, including unknowns. */
export function reportRowTotals(rows: readonly { currency?: string; total_amount?: number; amount?: number }[]): Record<string, number> {
  const totals: Record<string, number> = {};
  for (const row of rows) {
    const code = reservationCurrency(row.currency) || 'UNKNOWN';
    const amount = row.total_amount ?? row.amount;
    if (typeof amount !== 'number' || !Number.isFinite(amount)) { totals[code] = NaN; continue; }
    totals[code] = (totals[code] ?? 0) + amount;
  }
  return totals;
}

type SnapshotForShare = {
  business_date?: string; report_date?: string;
  pending_ar?: { by_currency?: unknown; complete?: boolean };
  mtd_collections?: { amount?: unknown; currency?: unknown; conversion_issue_count?: number };
};
export function financeShareText(snapshot: SnapshotForShare): string {
  return `Syroce finans özeti · PMS iş günü ${snapshot.business_date || snapshot.report_date || 'Bilgi yok'}\n`
    + `Bekleyen alacak: ${reportArLabel(snapshot.pending_ar?.by_currency)}${snapshot.pending_ar?.complete === false ? ' (eksik kaynak)' : ''}\n`
    + `Ay içi tahsilat: ${reportAmountLabel(snapshot.mtd_collections?.amount, snapshot.mtd_collections?.currency)}`
    + (snapshot.mtd_collections?.conversion_issue_count ? '\nKur verisi eksik; tahsilat özeti kısmi.' : '')
    + '\nFinansal veridir; yalnızca yetkili kişilerle paylaşın.';
}

/** Currency-preserving folio summaries; null or a missing read is not zero. */
export function reportMoneyTotalsLabel(value: unknown, amount?: unknown, currency?: unknown): string {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const entries = Object.entries(value);
    if (!entries.length) return reportAmountLabel(0, currency);
    return entries.map(([code, total]) => reportAmountLabel(total, code)).join(' · ');
  }
  return reportAmountLabel(amount, currency);
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
