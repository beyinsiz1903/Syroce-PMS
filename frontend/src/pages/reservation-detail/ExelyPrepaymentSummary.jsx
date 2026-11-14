import { BedDouble, CreditCard, Wallet } from 'lucide-react';
import { exelyReservationDetails } from '@/utils/exelyReservation';
import { fmtCurrency, InfoLine } from './helpers';

const validAmount = value => ['number', 'string'].includes(typeof value)
  && String(value).trim() !== '' && Number.isFinite(Number(value)) && Number(value) >= 0;
const money = (value, currency) => validAmount(value) && currency ? fmtCurrency(value, currency) : 'Doğrulanmadı';

// Read persisted provider totals without combining them with hotel receipts.
export default function ExelyPrepaymentSummary({ booking }) {
  if (!exelyReservationDetails(booking)) return null;
  const snapshot = booking.provider_prepayment;
  if (!snapshot || snapshot.schema_version !== 1) return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900" data-testid="exely-prepayment-unknown">
      Ön ödeme bilgisi doğrulanmadı. Ödeme almadan önce Exely kaydını kontrol edin.
    </div>
  );
  const totals = Array.isArray(snapshot.totals) ? snapshot.totals : [];
  const cards = [
    { label: 'Toplam bedel', icon: BedDouble, tone: 'bg-slate-50 text-slate-900', value: money(snapshot.booking_total, snapshot.booking_currency), hint: 'Konaklama ve hizmetler dahil' },
    { label: 'Alınan ön ödeme', icon: CreditCard, tone: 'bg-emerald-50 text-emerald-900', value: totals.length ? totals.map(row => money(row.received_amount, row.currency)).join(' · ') : 'Bildirilmedi', hint: 'Exely tarafından bildirildi' },
    { label: 'Kalan tutar', icon: Wallet, tone: 'bg-blue-50 text-blue-900', value: money(snapshot.remaining_amount, snapshot.booking_currency), hint: 'Ön ödeme düşüldükten sonra' },
  ];
  return <section className="space-y-3" aria-label="Rezervasyon hesap özeti" data-testid="exely-prepayment-summary">
    <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-3">
      {cards.map(({ label, icon: Icon, tone, value, hint }) => <div key={label} className={`min-w-0 rounded-xl p-4 ${tone}`}>
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold"><Icon className="h-4 w-4 shrink-0" />{label}</div>
        <p className="break-words text-2xl font-bold tabular-nums lg:text-3xl">{value}</p>
        <p className="mt-2 text-xs opacity-80">{hint}</p>
      </div>)}
    </div>
    {snapshot.remaining_amount == null && <p className="text-sm text-amber-800">Kalan tutar doğrulanamadı. Para birimleri farklıysa ödemeleri ayrı kontrol edin.</p>}
    {totals.length === 0 && <p className="text-sm text-slate-600">Exely alınmış ön ödeme bildirmedi.</p>}
    {totals.map(row => <div key={row.currency} className="text-sm text-slate-600">
      {row.expected_amount > 0 && <InfoLine label="Beklenen ön ödeme (henüz alınmamış)" value={money(row.expected_amount, row.currency)} />}
      {row.loyalty_amount > 0 && <InfoLine label="Kullanılan sadakat bakiyesi" value={money(row.loyalty_amount, row.currency)} />}
    </div>)}
    {snapshot.overpayment_amount > 0 && <div className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900"><InfoLine label="Rezervasyon bedelini aşan ödeme" value={money(snapshot.overpayment_amount, snapshot.booking_currency)} /></div>}
  </section>;
}
