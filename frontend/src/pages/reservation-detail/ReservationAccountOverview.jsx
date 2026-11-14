import { ChevronDown, Receipt } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { exelyReservationDetails } from '@/utils/exelyReservation';
import ExelyPrepaymentSummary from './ExelyPrepaymentSummary';
import { fmtCurrency, InfoLine } from './helpers';
import { reservationPaymentSummary } from './paymentSummary';
import { UnpostedRoomBreakdown } from './UnpostedRoomBreakdown';

export default function ReservationAccountOverview({ booking, summary, onSwitchTab }) {
  const source = exelyReservationDetails(booking);
  if (!source) return null;
  const currency = booking.currency || 'TL';
  const local = reservationPaymentSummary(summary, booking);
  const hasHotelActivity = [summary?.additional_charge_total ?? summary?.total_extra,
    summary?.cash_collection_total ?? summary?.total_payments,
    summary?.city_ledger_transfer_total, summary?.total_discounts]
    .some(value => Number.isFinite(Number(value)) && Math.abs(Number(value)) > 0.01);
  const services = Array.isArray(booking.provider_services) ? booking.provider_services : [];
  return <section className="min-w-0 space-y-4" data-testid="reservation-account-overview">
    <div>
      <h3 className="text-lg font-bold text-slate-900">Hesap ve ödeme</h3>
      <p className="mt-1 text-sm text-slate-600">Rezervasyon bedeli, alınan ön ödeme ve kalan tutar tek yerde.</p>
    </div>
    {local.kind === 'reconciliation' && <div role="alert" className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">Fiyat ve hesap kayıtları uyuşmuyor. Tahsilat öncesi folyo kayıtlarını kontrol edin.</div>}
    <ExelyPrepaymentSummary booking={booking} />
    <p className="text-xs text-slate-500">Bu özet, Exely rezervasyonunun tüm odalarını ve hizmetlerini kapsar. Otelde eklenen harcama ve ödemeler ayrıca izlenir.</p>
    {hasHotelActivity && <div role="status" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Otelde eklenen harcama, ödeme veya hesap işlemi var. Tahsilat öncesi aşağıdaki hesap ayrıntılarını kontrol edin.</div>}
    <div className="grid min-w-0 gap-4 lg:grid-cols-2">
      <section className="min-w-0 rounded-xl border border-slate-200 bg-white p-4" data-testid="account-charge-breakdown">
        <h4 className="mb-2 font-semibold text-slate-900">Ücret dökümü</h4>
        <InfoLine label="Bu odanın konaklaması" value={booking.total_amount == null ? 'Doğrulanmadı' : fmtCurrency(booking.total_amount, currency)} />
        {services.map(service => <div key={service.reference || `${service.name}-${service.start_date}`}>
          <InfoLine label={service.name === 'Breakfast' ? 'Kahvaltı' : service.name} value={service.inclusive && Number(service.amount) === 0 ? 'Ücrete dahil' : fmtCurrency(service.amount, service.currency)} />
          {service.scope === 'reservation' && <p className="text-xs text-slate-500">Rezervasyon genelinde</p>}
        </div>)}
        <p className="mt-3 text-xs text-slate-500">Birden fazla oda varsa üstteki toplam tüm odalar içindir. Oda ve hizmet tutarları bu toplama dahildir.</p>
      </section>
      <section className="min-w-0 rounded-xl border border-slate-200 bg-white p-4" data-testid="account-invoice-info">
        <h4 className="mb-2 flex items-center gap-2 font-semibold text-slate-900"><Receipt className="h-4 w-4" />Fatura bilgileri</h4>
        <InfoLine label="Kime kesilecek?" value="Fatura ekranında belirlenir" />
        <p className="my-3 text-sm text-slate-600">Exely rezervasyon kaynağıdır. Fatura alıcısı ayrıca seçilir.</p>
        {onSwitchTab && <Button type="button" variant="outline" size="sm" onClick={() => onSwitchTab('invoice')} className="border-blue-200 text-blue-700">Fatura bilgilerini aç</Button>}
      </section>
    </div>
    <details className="group rounded-xl border border-slate-200 bg-white" data-testid="account-ledger-details">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 p-4 text-sm font-semibold text-slate-800 [&::-webkit-details-marker]:hidden"><ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" />Hesap ayrıntıları<span className="font-normal text-slate-500">PMS hareketleri ve mutabakat</span></summary>
      <div className="space-y-2 border-t border-slate-100 p-4 text-sm" data-testid="local-payment-scope">
        <p className="text-xs text-slate-500">Exely ön ödemesi aşağıdaki PMS tahsilatına dahil değildir. Bu iki bakiyeyi toplayarak tahsilat yapmayın.</p>
        <InfoLine label={local.label} value={local.displayAmount == null ? 'Doğrulanmadı' : fmtCurrency(local.displayAmount, currency)} />
        <InfoLine label="Otelde eklenen harcamalar" value={summary ? fmtCurrency(summary.additional_charge_total ?? summary.total_extra ?? 0, currency) : 'Doğrulanmadı'} />
        <InfoLine label="PMS tahsilatı" value={summary ? fmtCurrency(summary.cash_collection_total ?? summary.total_payments ?? 0, currency) : 'Doğrulanmadı'} />
        {Number(summary?.city_ledger_transfer_total) > 0 && <InfoLine label="Cariye aktarılan (tahsilat değil)" value={fmtCurrency(summary.city_ledger_transfer_total, currency)} />}
        {Number(summary?.total_discounts) > 0 && <InfoLine label="İkram / indirim" value={fmtCurrency(summary.total_discounts, currency)} />}
        {Number(summary?.total_deposits) > 0 && <InfoLine label="Depozito" value={fmtCurrency(summary.total_deposits, currency)} />}
        <UnpostedRoomBreakdown payment={local} currency={currency} />
        <InfoLine label="Exely rezervasyon no" value={source.reservationId || 'Belirtilmemiş'} />
        <InfoLine label="Exely ödeme yöntemi" value={source.paymentMethod || 'Belirtilmemiş'} />
        <p className="text-xs text-slate-500">Ödeme yöntemi tek başına tahsilat yapıldığını göstermez.</p>
        {onSwitchTab && <Button type="button" variant="outline" size="sm" onClick={() => onSwitchTab('folios')}>Folyo hareketlerini aç</Button>}
      </div>
    </details>
  </section>;
}
