import { AlertTriangle, CheckCircle2, ChevronDown, Clock3, X } from 'lucide-react';
import { placementDescription } from './exelyPlacements';

const fields = { rate: 'Fiyat', availability: 'Müsaitlik', min_stay: 'Minimum konaklama', max_stay: 'Maksimum konaklama', min_los_arrival: 'Varış bazlı minimum', stop_sell: 'Satış durumu', cta: 'Varış kısıtı', ctd: 'Çıkış kısıtı' };
const dateLabel = value => {
  const date = new Date(`${value}T12:00:00Z`);
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Europe/Istanbul' }).format(date);
};

export const RateDeliveryCard = ({ receipt, feedback, onDismiss }) => {
  const data = receipt.data;
  const confirmed = data.provider_verified === true;
  const unchanged = data.provider_delivery_state === 'UNCHANGED';
  const settled = confirmed || unchanged;
  const unknown = data.provider_delivery_state === 'UNKNOWN' || data.outcome_unknown === true;
  const pending = ['QUEUED', 'PENDING', 'SENDING'].includes(data.provider_delivery_state);
  const state = confirmed ? 'Teslim edildi' : unchanged ? 'Fiyatlar güncel' : unknown ? 'Sonuç doğrulanamadı' : pending ? 'İletim bekleniyor' : data.provider_delivery_state === 'PARTIAL' ? 'Kısmen teslim edildi' : 'İletim tamamlanmadı';
  const Icon = settled ? CheckCircle2 : pending ? Clock3 : AlertTriangle;
  const savedLabel = typeof data.saved === 'number' && Number.isFinite(data.saved)
    ? `${data.saved.toLocaleString('tr-TR')} güncellendi` : unknown ? 'Sonuç belirsiz' : 'Kayıt bilgisi yok';
  const rooms = Object.keys(data.price_guest_prices || {}).length ? Object.keys(data.price_guest_prices) : Object.keys(data.price_occupancies || {});
  return <section role="status" aria-label="Son güncelleme" data-testid="rate-delivery-receipt" className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-5">
      <div className="flex min-w-0 items-center gap-3">
        <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${settled ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'}`}><Icon className="h-5 w-5" aria-hidden="true" /></span>
        <div><h3 className="text-sm font-semibold text-slate-900">Son güncelleme</h3><p className="mt-0.5 text-xs text-slate-500">{(receipt.fields || []).map(field => fields[field] || 'Diğer alan').join(' · ') || 'Kanal güncellemesi'}</p></div>
      </div>
      <div className="flex items-center gap-2"><span className={`rounded-full px-2.5 py-1 text-xs font-medium ${settled ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-800'}`}>{state}</span>
        {onDismiss && <button type="button" onClick={onDismiss} aria-label="Son güncelleme kartını gizle" className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"><X className="h-4 w-4" /></button>}
      </div>
    </div>
    <div className="grid gap-3 border-t border-slate-100 bg-slate-50/60 px-4 py-3 text-sm sm:grid-cols-[minmax(0,2fr)_1fr_1fr] sm:px-5">
      <div><p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">Tarih aralığı</p><p className="mt-1 font-medium text-slate-800">{dateLabel(receipt.dateFrom)} – {dateLabel(receipt.dateTo)}</p></div>
      <div><p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">Kapsam</p><p className="mt-1 font-medium text-slate-800">{receipt.roomCount} oda tipi</p></div>
      <div><p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">Yerel kayıt</p><p className="mt-1 font-medium text-slate-800">{savedLabel}</p></div>
    </div>
    {!settled && <p className="border-t border-amber-100 bg-amber-50/50 px-4 py-3 text-xs leading-5 text-amber-900 sm:px-5">{feedback.message}</p>}
    <details className="group border-t border-slate-100">
      <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-2.5 text-xs font-medium text-slate-600 hover:bg-slate-50 sm:px-5">Gönderim ayrıntıları<ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" aria-hidden="true" /></summary>
      <div className="space-y-3 px-4 pb-4 text-xs leading-5 text-slate-600 sm:px-5">
        <p>{feedback.message}</p>
        {rooms.length > 0 && <p>Seçilen fiyatlar aşağıda. Exely’ye yalnız değişen fiyatlar iletilir.</p>}
        {rooms.map((room, index) => <div key={room} className="rounded-lg border border-slate-100 p-3"><p className="mb-1 font-semibold text-slate-800">{receipt.roomNames?.[room] || `Oda tipi ${index + 1}`}</p>
          {data.price_guest_prices?.[room]?.map((price, i) => <p key={i}>{placementDescription(price)} {receipt.currency || ''}</p>) || <p>{data.price_occupancies[room]} yetişkin · ana yatak · oda/gece toplam fiyatı</p>}
        </div>)}
        {data.availability_input_mode === 'remaining' && <p>Gönderilen müsaitlik, manuel satış kontenjanı veya otomatik net kalan oda sayısıdır. Mevcut rezervasyonlar tekrar düşülmez. Boş alan otomatik hesaptır; elle girilen kontenjan fiziksel kapasiteyi aşabilir.</p>}
        <p className="text-slate-500">Teslim onayı kanal sağlayıcısının yanıtıdır; alıcıdaki fiyat ve yerleşim eşleşmesi ayrıca kontrol edilebilir.</p>
      </div>
    </details>
  </section>;
};
