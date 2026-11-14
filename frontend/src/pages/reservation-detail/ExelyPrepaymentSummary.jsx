import { exelyReservationDetails } from '@/utils/exelyReservation';
import { fmtCurrency, InfoLine } from './helpers';

// Reservation-wide provider evidence. Never add these amounts to local cash,
// card or folio receipts, or multiply them by the number of room bookings.
export default function ExelyPrepaymentSummary({ booking, compact = false }) {
  if (!exelyReservationDetails(booking)) return null;
  const snapshot = booking.provider_prepayment;
  if (!snapshot || snapshot.schema_version !== 1) return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600" data-testid="exely-prepayment-unknown">
      Bu kayıtta Exely ön ödeme tutarı bulunmuyor. Ödeme yöntemi bilgisi, ödeme alındığını göstermez.
    </div>
  );
  return (
    <section className={`rounded-xl border border-emerald-200 bg-emerald-50/50 ${compact ? 'p-2 space-y-2' : 'p-4 space-y-3'}`} data-testid={compact ? 'exely-prepayment-sidebar' : 'exely-prepayment-summary'}>
      <h4 className="text-sm font-semibold text-slate-800">Exely ön ödemesi</h4>
      <div className="rounded-lg bg-white px-3 py-1">
        <InfoLine label={compact ? 'Rezervasyon bedeli' : 'Exely rezervasyon bedeli'} value={<span className="whitespace-nowrap">{fmtCurrency(snapshot.booking_total, snapshot.booking_currency)}</span>} />
        {snapshot.totals.map(row => <div key={row.currency}>
          <InfoLine label="Alınan ön ödeme" value={<span className="whitespace-nowrap">{fmtCurrency(row.received_amount, row.currency)}</span>} />
          {row.expected_amount > 0 && <InfoLine label="Beklenen ön ödeme (henüz alınmamış)" value={fmtCurrency(row.expected_amount, row.currency)} />}
          {row.loyalty_amount > 0 && <InfoLine label="Kullanılan sadakat bakiyesi" value={fmtCurrency(row.loyalty_amount, row.currency)} />}
        </div>)}
        {snapshot.totals.length === 0 && <p className="py-2 text-sm text-slate-600">Exely alınmış ön ödeme bildirmedi.</p>}
        {!compact && <InfoLine label="Exely’de kalan tutar" value={snapshot.remaining_amount == null
          ? 'Para birimleri farklı; tutar karşılaştırılamıyor'
          : fmtCurrency(snapshot.remaining_amount, snapshot.booking_currency)} />}
        {snapshot.overpayment_amount > 0 && <InfoLine label="Rezervasyon bedelini aşan ödeme" value={fmtCurrency(snapshot.overpayment_amount, snapshot.booking_currency)} />}
      </div>
      {!compact && <p className="text-xs text-slate-600">Hizmetler dahil Exely rezervasyonunun tamamını kapsar. Birden fazla oda varsa bu tutar oda başına tekrar sayılmaz. PMS kasa ve folyo tahsilatları ayrıca izlenir.</p>}
    </section>
  );
}
