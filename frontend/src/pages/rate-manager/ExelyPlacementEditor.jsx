import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { compileExelyGuestPrices, PLACEMENT_LABELS, placementDescription } from './exelyPlacements';

// Embedded in the existing rule editor; saving a rule never sends prices.
export const ExelyPlacementEditor = ({ draft, update, base, currency }) => {
  const rows = draft.exely_price_placements || [];
  const replace = next => {
    update('exely_price_placements', next);
    update('exely_placements_reviewed', false);
  };
  const change = (index, field, value) => replace(rows.map((row, i) => i === index ? { ...row, [field]: value } : row));
  let preview = [], error = '';
  try { preview = compileExelyGuestPrices({ ...draft, pricing_type: 'per_person', exely_placements_reviewed: true, currency }, base, currency); }
  catch (failure) { error = failure.message; }
  return <section className="mt-4 space-y-3 rounded-lg border border-blue-200 bg-blue-50 p-3" data-testid="exely-placement-editor">
    <h4 className="text-sm font-semibold">Exely yerleşim tarifeleri</h4>
    <p className="text-xs text-slate-700">Oda bazlı mod yalnız kayıtlı taban yetişkin yerleşimini gönderir. Kişi bazlı mod taban fiyatla birlikte aşağıdaki tarifeleri aynı XML içinde gönderir. Ana yatak yetişkin fiyatı oda/gece toplamıdır; çocuk ve ek yatak tutarı kişi/gecedir. Boş veya eklenmemiş tarife ücretsiz sayılmaz ve gönderilmez.</p>
    <p className="text-xs text-slate-700">Bu tablo kanalın yerleşim fiyatlarıdır; aşağıdaki PMS çocuk ek ücreti kuralları buraya kendiliğinden kopyalanmaz. Örneğin 1 yetişkin %90, 3 yetişkin %120 olarak tanımlanabilir. Yüzdeler girilen taban oda fiyatına uygulanır.</p>
    <p className="text-xs font-medium">Taban: {draft.base_occupancy} yetişkin · {base || '—'} {currency} / oda / gece (otomatik dahil)</p>
    {rows.map((row, index) => <div key={index} className="space-y-2 rounded border bg-white p-2" data-testid={`exely-placement-row-${index}`}>
      <label className="block text-xs">Yerleşim türü
        <select aria-label={`${index + 1}. Exely yerleşim türü`} className="mt-1 h-8 w-full rounded border px-2" value={row.kind} onChange={e => replace(rows.map((old, i) => i === index ? { kind: e.target.value, price_mode: 'fixed', value: '', ...(e.target.value === 'adult_main' ? { number_of_guests: 1 } : e.target.value.startsWith('child_') ? { min_age: 0, max_age: 2 } : {}) } : old))}>
          {Object.entries(PLACEMENT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <div className="flex flex-wrap items-end gap-2">
        {row.kind === 'adult_main' && <label className="text-xs">Yetişkin sayısı<Input aria-label={`${index + 1}. yetişkin sayısı`} className="mt-1 h-8 w-28" type="number" min="1" max="20" value={row.number_of_guests} onChange={e => change(index, 'number_of_guests', e.target.value === '' ? '' : Number(e.target.value))} /></label>}
        {row.kind.startsWith('child_') && <>
          <label className="text-xs">İlk yaş (dahil)<Input aria-label={`${index + 1}. ilk yaş`} className="mt-1 h-8 w-28" type="number" min="0" max="17" value={row.min_age} onChange={e => change(index, 'min_age', e.target.value === '' ? '' : Number(e.target.value))} /></label>
          <label className="text-xs">Son yaş (dahil)<Input aria-label={`${index + 1}. son yaş`} className="mt-1 h-8 w-28" type="number" min="0" max="17" value={row.max_age} onChange={e => change(index, 'max_age', e.target.value === '' ? '' : Number(e.target.value))} /></label>
        </>}
        <label className="text-xs">Fiyat yöntemi<select aria-label={`${index + 1}. fiyat yöntemi`} className="mt-1 block h-8 rounded border px-2" value={row.price_mode} onChange={e => change(index, 'price_mode', e.target.value)}><option value="fixed">Sabit {currency}</option><option value="percentage">Taban fiyatın yüzdesi</option></select></label>
        <label className="text-xs">{row.price_mode === 'fixed' ? 'Tutar / gece' : 'Yüzde'}<Input aria-label={`${index + 1}. yerleşim fiyatı`} className="mt-1 h-8 w-32" type="number" min="0" step="0.01" value={row.value} onChange={e => change(index, 'value', e.target.value === '' ? '' : Number(e.target.value))} /></label>
        <Button type="button" size="sm" variant="outline" onClick={() => replace(rows.filter((_, i) => i !== index))} aria-label={`${index + 1}. Exely tarifesini kaldır`}>Kaldır</Button>
      </div>
    </div>)}
    <Button type="button" size="sm" variant="outline" disabled={rows.length >= 100} onClick={() => replace([...rows, { kind: 'adult_main', number_of_guests: 1, price_mode: 'percentage', value: '' }])}>Yerleşim tarifesi ekle</Button>
    {error ? <p role="alert" className="text-xs text-red-700">{error}</p> : <ul className="space-y-1 text-xs" data-testid="exely-placement-preview">{preview.map((price, i) => <li key={i}>{placementDescription(price)} {currency}</li>)}</ul>}
    <label className="flex items-start gap-2 text-xs"><Checkbox checked={draft.exely_placements_reviewed === true} disabled={!!error || !rows.length} onCheckedChange={value => update('exely_placements_reviewed', value === true)} data-testid="exely-placements-reviewed" /><span>Exely oda tipindeki ana/ek yatak kapasitesini, çocuk yaş aralıklarını ve yukarıdaki tarifelerin birimlerini kontrol ettim. Kaydetmek fiyat göndermez; yayın önizlemesinde yeniden gösterilir. Yataksız konaklama yalnız çocuklar içindir.</span></label>
    <p className="text-xs text-slate-600">Satırı kaldırmak Exely’deki eski fiyatı silmez. Yalnız açıkça tanımlanan yerleşimler güncellenir; “oda içinde yatak satışı” için çoklu ek yatak toplamı bu tabloda desteklenmez.</p>
  </section>;
};
