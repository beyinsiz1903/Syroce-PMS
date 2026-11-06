import { Baby, BedDouble, Users, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { compileExelyGuestPrices, PLACEMENT_LABELS } from './exelyPlacements';
import { exelyDraftError, formatGuestAmount, nextAdultPlacement, nextChildAgeBand } from './guestPricingEditor';

const units = kind => kind === 'adult_main' ? 'oda / gece toplamı' : kind.startsWith('child_') ? 'çocuk başı / gece' : 'kişi başı / gece';
const guestLabel = price => price.kind === 'adult_main' ? `${price.number_of_guests} yetişkin`
  : `${price.kind === 'adult_extra' ? 'Yetişkin' : `${price.min_age}–${price.max_age - 1} yaş çocuk`} · ${price.kind.endsWith('_extra') ? 'ek yatak' : price.kind === 'child_without_bed' ? 'yataksız' : 'ana yatak'}`;
const rowHelp = kind => kind === 'adult_main' ? 'Bu kişi sayısının oda toplamını girin; kişi sayısıyla tekrar çarpılmaz.'
  : kind === 'child_without_bed' ? 'Ayrı yatak kullanmayan her çocuk için gecelik tutar.'
    : kind.endsWith('_extra') ? 'Ek yatak kullanan her misafir için gecelik tutar.' : 'Ana yatak kullanan her çocuk için gecelik tutar.';

// The channel table is explicit: never infer a bed type from a PMS surcharge.
export const ExelyPlacementEditor = ({ draft, update, base, currency, pricingType = 'per_person' }) => {
  const rows = draft.exely_price_placements || [];
  const replace = next => {
    update('exely_price_placements', next);
    update('exely_placements_reviewed', false);
  };
  const change = (index, field, value) => replace(rows.map((row, i) => i === index ? { ...row, [field]: value } : row));
  const nextAdult = nextAdultPlacement(rows, draft.base_occupancy);
  const childBand = nextChildAgeBand(rows, 'child_main');
  const error = exelyDraftError(draft, currency);
  let preview = [], previewError = '';
  if (!error && base > 0) {
    try { preview = compileExelyGuestPrices({ ...draft, pricing_type: 'per_person', exely_placements_reviewed: true, currency }, base, currency); }
    catch (failure) { previewError = failure.message; }
  }
  const makeRow = kind => ({ kind, price_mode: 'fixed', value: '', ...(kind === 'adult_main'
    ? { number_of_guests: nextAdult ?? 1 } : kind.startsWith('child_') ? nextChildAgeBand(rows, kind) ?? { min_age: '', max_age: '' } : {}) });
  const add = kind => replace([...rows, makeRow(kind)]);
  return <section className="space-y-4" data-testid="exely-placement-editor" aria-label="Exely yerleşim tarifeleri">
    <div>
      <h4 className="text-sm font-semibold text-slate-900">Exely’ye gönderilecek fiyatlar</h4>
      <p className="mt-1 text-xs leading-5 text-slate-600">Aynı oda için farklı yetişkin sayıları, çocuk yaşları ve yatak seçeneklerini ayrı ayrı fiyatlandırın.</p>
    </div>
    {pricingType === 'per_room' && <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-950" role="status">Oda bazlı fiyatlandırma açık: yalnız aşağıdaki taban oda fiyatı gönderilir. Ek tarifeleri göndermek için oda satırından “Kişi bazlı fiyatlandırma”yı seçin. Kayıtlı ek tarifeler silinmez.</p>}
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3">
      <div><div className="text-xs font-semibold text-blue-950">Taban oda fiyatı · {draft.base_occupancy || '—'} yetişkin</div><p className="mt-1 text-xs text-blue-900">Ekranda girdiğiniz fiyat otomatik dahil edilir.</p></div>
      <div className="text-right"><div className="text-sm font-semibold text-blue-950">{base > 0 ? formatGuestAmount(base, currency) : 'Henüz fiyat girilmedi'}</div><div className="text-[11px] text-blue-900">oda / gece toplamı</div></div>
    </div>
    <div className="flex flex-wrap gap-2" aria-label="Tarife ekle">
      <Button type="button" size="sm" variant="outline" disabled={rows.length >= 100 || !nextAdult} onClick={() => add('adult_main')}><Users className="mr-1.5 h-4 w-4" />Yetişkin fiyatı ekle</Button>
      <Button type="button" size="sm" variant="outline" disabled={rows.length >= 100 || !childBand} onClick={() => add('child_main')}><Baby className="mr-1.5 h-4 w-4" />Çocuk fiyatı ekle</Button>
      <Button type="button" size="sm" variant="outline" disabled={rows.length >= 100 || rows.some(row => row.kind === 'adult_extra')} onClick={() => add('adult_extra')}><BedDouble className="mr-1.5 h-4 w-4" />Ek yatak fiyatı ekle</Button>
    </div>
    {!rows.length && <p className="rounded-lg border border-dashed border-slate-300 p-4 text-xs leading-5 text-slate-600">Henüz ek tarife yok. Örneğin tek yetişkin fiyatını veya çocuk için yatak türüne göre bir ücret ekleyebilirsiniz. Eklenmeyen tarife ücretsiz sayılmaz.</p>}
    <div className="space-y-3">{rows.map((row, index) => {
      const free = row.kind !== 'adult_main' && row.price_mode === 'fixed' && row.value === 0;
      const amount = row.value === '' ? null : row.price_mode === 'fixed' ? Number(row.value) : base > 0 ? Math.round((base * Number(row.value) / 100 + Number.EPSILON) * 100) / 100 : null;
      return <div key={index} className="min-w-0 rounded-xl border border-slate-200 bg-white p-3" data-testid={`exely-placement-row-${index}`}>
        <div className="flex items-start gap-2">
          <label className="min-w-0 flex-1 text-xs font-medium text-slate-700">Misafir ve yatak seçeneği
            <select aria-label={`${index + 1}. Exely yerleşim türü`} className="mt-1 h-10 w-full min-w-0 rounded-md border border-input bg-background px-2 text-sm" value={row.kind} onChange={e => replace(rows.map((old, i) => i === index ? makeRow(e.target.value) : old))}>
              {Object.entries(PLACEMENT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <Button type="button" size="icon" variant="ghost" className="mt-5 shrink-0 text-slate-500 hover:text-destructive" onClick={() => replace(rows.filter((_, i) => i !== index))} aria-label={`${index + 1}. Exely tarifesini kaldır`}><Trash2 className="h-4 w-4" /></Button>
        </div>
        <p className="mt-2 text-xs leading-5 text-slate-500">{rowHelp(row.kind)}</p>
        <div className="mt-3 grid grid-cols-2 items-end gap-3">
          {row.kind === 'adult_main' && <label className="text-xs text-slate-700">Yetişkin sayısı<Input aria-label={`${index + 1}. yetişkin sayısı`} className="mt-1 h-10" type="number" min="1" max="20" value={row.number_of_guests} onChange={e => change(index, 'number_of_guests', e.target.value === '' ? '' : Number(e.target.value))} /></label>}
          {row.kind.startsWith('child_') && <>
            <label className="text-xs text-slate-700">İlk yaş (dahil)<Input aria-label={`${index + 1}. ilk yaş`} className="mt-1 h-10" type="number" min="0" max="17" value={row.min_age} onChange={e => change(index, 'min_age', e.target.value === '' ? '' : Number(e.target.value))} /></label>
            <label className="text-xs text-slate-700">Son yaş (dahil)<Input aria-label={`${index + 1}. son yaş`} className="mt-1 h-10" type="number" min="0" max="17" value={row.max_age} onChange={e => change(index, 'max_age', e.target.value === '' ? '' : Number(e.target.value))} /></label>
          </>}
          <label className="min-w-0 text-xs text-slate-700">Fiyat yöntemi<select aria-label={`${index + 1}. fiyat yöntemi`} className="mt-1 block h-10 w-full min-w-0 rounded-md border border-input bg-background px-2 text-sm" value={free ? 'free' : row.price_mode} onChange={e => replace(rows.map((old, i) => i === index ? { ...old, price_mode: e.target.value === 'free' ? 'fixed' : e.target.value, value: e.target.value === 'free' ? 0 : '' } : old))}>
            <option value="fixed">Sabit tutar ({currency})</option><option value="percentage">Taban oda fiyatının %’si</option>{row.kind !== 'adult_main' && <option value="free">Ücretsiz</option>}
          </select></label>
          {!free && <label className="text-xs text-slate-700">{row.price_mode === 'fixed' ? `Tutar (${currency})` : 'Yüzde (%)'}<Input aria-label={`${index + 1}. yerleşim fiyatı`} className="mt-1 h-10" type="number" min="0" step="0.01" value={row.value} onChange={e => change(index, 'value', e.target.value === '' ? '' : Number(e.target.value))} /></label>}
        </div>
        {row.kind.startsWith('child_') && <p className="mt-2 text-[11px] text-slate-500">Her iki yaş dahil; yaş, giriş tarihine göre değerlendirilir. Örnek: 3–6 yaş, 7. doğum gününe kadar.</p>}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-1 rounded-lg bg-slate-50 px-3 py-2 text-xs" data-testid={`exely-placement-amount-${index}`}>
          <span className="text-slate-600">{row.price_mode === 'percentage' ? `Taban oda fiyatı × %${row.value === '' ? '…' : row.value}` : free ? 'Ücretsiz konaklama' : 'Gönderilecek tutar'}</span>
          <span className="font-semibold text-slate-900">{amount !== null && Number.isFinite(amount) && amount >= 0 ? formatGuestAmount(amount, currency) : 'Tutarı tamamlayın'} <span className="font-normal text-slate-500">/ {units(row.kind)}</span></span>
        </div>
      </div>;
    })}</div>
    {(error || previewError) && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800">{error || previewError}</p>}
    {!error && !previewError && <div className="rounded-lg border border-slate-200 p-3">
      <h5 className="text-xs font-semibold text-slate-900">{pricingType === 'per_room' ? 'Kayıtlı tarifelerin örnek hesabı' : 'Gönderilecek fiyatların önizlemesi'}</h5>
      {base > 0 ? <ul className="mt-3 space-y-2 text-xs" data-testid="exely-placement-preview">{preview.map((price, i) => <li key={i} className="flex flex-wrap justify-between gap-1"><span className="text-slate-600">{guestLabel(price)}: <strong className="font-semibold text-slate-900">{formatGuestAmount(price.amount, currency)}</strong></span><span className="text-slate-500">{units(price.kind)}</span></li>)}</ul>
        : <p className="mt-2 text-xs text-slate-500">Oda fiyatını girdiğinizde yüzdeli tarifelerin tutarını burada görebilirsiniz. Şu anda yalnız kuralları kaydediyorsunuz.</p>}
    </div>}
    {rows.length > 0 && <label className="flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs leading-5 text-blue-950"><Checkbox className="mt-0.5 shrink-0" checked={draft.exely_placements_reviewed === true} disabled={!!error || !!previewError} onCheckedChange={value => update('exely_placements_reviewed', value === true)} data-testid="exely-placements-reviewed" /><span>Bu tarifelerdeki kişi sayılarını, çocuk yaşlarını ve yatak seçeneklerini Exely panelindeki oda ayarlarıyla karşılaştırdım.<span className="mt-1 block font-normal text-blue-900">Bu onay yalnız sizin kontrolünüzü kaydeder; Exely’nin kabul veya sertifikasyon onayı değildir.</span></span></label>}
    <details className="text-xs text-slate-600"><summary className="cursor-pointer font-medium text-slate-700">Kapsam ve önemli bilgiler</summary><div className="mt-2 space-y-2 leading-5">
      <p>Kaydetmek fiyat göndermez. Tarihleri ve fiyat planlarını seçip gönderim özetini onayladığınızda fiyatlar iletilir.</p>
      <p>PMS çocuk ek ücretleri otomatik kopyalanmaz: Exely’de yatak türü ve yaş sınırları ayrıca eşleşmelidir. Ana yatak yetişkin tutarı oda toplamıdır; çocuk ve ek yatak tutarları kişi başıdır.</p>
      <p>Tarife kaldırmak Exely’deki eski fiyatı silmez. Tanımlanmayan yaşlar ve yatak seçenekleri güncellenmez; ücretsiz fiyat için açıkça “Ücretsiz” seçin.</p>
      <p>Yataksız seçenek yalnız çocuklar içindir. Oda içinde ayrı ayrı yatak satışı için toplu ek yatak fiyatlandırması desteklenmez.</p>
    </div></details>
  </section>;
};
