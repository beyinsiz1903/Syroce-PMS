import { currencyBreakdownEntries, formatCurrencyBreakdown } from '@/lib/reportCurrency';

/** Exact amounts stay readable without joining or converting unrelated currencies. */
export default function CurrencySummary({ breakdown, fallbackAmount = 0, fallbackCurrency = 'TRY', className = '', ...props }) {
  const entries = currencyBreakdownEntries(breakdown);
  return entries.length ? (
    <dl {...props} className={`mt-2 min-w-0 space-y-1 text-sm tabular-nums ${className}`}>
      {entries.map(({ currency, formatted }) => (
        <div key={currency} className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5">
          <dt className="text-xs font-medium text-slate-500">{currency}</dt>
          <dd className="min-w-0 break-words font-semibold">{formatted}</dd>
        </div>
      ))}
    </dl>
  ) : <div {...props} className={`mt-2 break-words text-sm font-semibold tabular-nums ${className}`}>
    {formatCurrencyBreakdown(breakdown, fallbackAmount, fallbackCurrency)}
  </div>;
}
