import { formatCurrencyBreakdown } from '@/lib/reportCurrency';

export default function ReportConversionNotice({ payments }) {
  if (!(payments?.conversion_issue_count > 0)) return null;
  const received = payments.received_totals_by_currency;
  return <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
    <p>{payments.conversion_issue_count} işlemde tarihsel TL karşılığı eksik. Bu işlemler TL toplamına dahil edilmedi; gösterilen TL toplamı tüm tahsilatları kapsamaz.</p>
    {received && Object.keys(received).length > 0 && <p className="mt-1">Alınan tutarlar (para birimi bazında): {formatCurrencyBreakdown(received)}</p>}
  </div>;
}
