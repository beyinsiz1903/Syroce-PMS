import { fmtCurrency } from './helpers';

export function UnpostedRoomBreakdown({ payment, currency, testIdPrefix = '' }) {
  if (!(payment.pendingRoomAmount > 0.01) || payment.kind === 'reconciliation') return null;
  const folioCredit = payment.folioBalance < -0.01;
  return (
    <div className="space-y-2 border-t border-slate-200 pt-2 text-xs" data-testid={`${testIdPrefix}payment-balance-breakdown`}>
      <div className="flex items-start justify-between gap-3" data-testid={`${testIdPrefix}posted-folio-balance`}>
        <span className="min-w-0 text-slate-500">{folioCredit ? 'Folyodaki ön ödeme / alacak' : 'Folyodaki borç'}</span>
        <span className="shrink-0 whitespace-nowrap font-semibold text-slate-700">{payment.folioBalance == null ? '—' : fmtCurrency(Math.abs(payment.folioBalance), currency)}</span>
      </div>
      <div className="flex items-start justify-between gap-3" data-testid={`${testIdPrefix}unposted-room-amount`}>
        <span className="min-w-0 text-slate-500">Henüz işlenmemiş oda bedeli</span>
        <span className="shrink-0 whitespace-nowrap font-semibold text-slate-700">{fmtCurrency(payment.pendingRoomAmount, currency)}</span>
      </div>
      <p className="text-[11px] leading-4 text-slate-500">İşlenmemiş oda bedeli toplam kalan ödemede dikkate alınır; ayrıca eklenmez.</p>
      {payment.hasAllocatedPrepayment && <p className="text-[11px] leading-4 text-emerald-700">Ön ödeme henüz işlenmemiş oda bedelini karşılıyor. Bu tutar yeniden tahsil edilmez.</p>}
    </div>
  );
}
