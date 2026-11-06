import { useId, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Loader2, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { calculateOccupancyPrice, normalizeOccupancyRule } from '@/utils/occupancyPricing';
import { exelyPriceOccupancy } from './updateReview';
import { ExelyPlacementEditor } from './ExelyPlacementEditor';
import { exelyDraftError, formatGuestAmount, nextChildAgeBand, validateGuestPricingDraft } from './guestPricingEditor';

export const OccupancyPricingEditor = ({ roomType, open, onToggle, rule, onSave, currentBaseRate, currencySymbol, currency, channelProvider }) => {
  const [section, setSection] = useState(channelProvider === 'exely' ? 'exely' : 'pms');
  const sectionId = useId();
  const providerName = channelProvider === 'exely' ? 'Exely' : 'HotelRunner';
  const normalizedRule = normalizeOccupancyRule(rule);
  const initial = {
    base_occupancy: normalizedRule.base_occupancy,
    extra_adult_rate: normalizedRule.extra_adult_rate,
    extra_adult_rate_type: normalizedRule.extra_adult_rate_type,
    child_age_bands: normalizedRule.child_age_bands,
    max_occupancy: normalizedRule.max_occupancy ?? '',
    provider_pricing_verified: Boolean(rule?.provider_pricing_verified),
    provider_pricing_note: rule?.provider_pricing_note || '',
    exely_price_placements: rule?.exely_price_placements || [],
    exely_placements_reviewed: rule?.exely_placements_reviewed === true && rule?.currency === currency,
  };
  const [draft, setDraft] = useState(initial);
  const [submitting, setSubmitting] = useState(false);
  const update = (field, value) => setDraft(prev => ({
    ...prev,
    [field]: value,
    ...(field !== 'provider_pricing_verified' && field !== 'provider_pricing_note'
      ? { provider_pricing_verified: false }
      : {}),
    ...(field === 'base_occupancy' ? { exely_placements_reviewed: false } : {}),
  }));
  const updateBand = (index, field, value) => setDraft(prev => ({
    ...prev,
    provider_pricing_verified: false,
    child_age_bands: prev.child_age_bands.map((band, bandIndex) => bandIndex === index
      ? { ...band, [field]: value }
      : band),
  }));
  const removeBand = index => setDraft(prev => ({
    ...prev,
    provider_pricing_verified: false,
    child_age_bands: prev.child_age_bands.filter((_, bandIndex) => bandIndex !== index),
  }));
  const addBand = () => setDraft(prev => ({
    ...prev,
    provider_pricing_verified: false,
    child_age_bands: [...prev.child_age_bands, { ...nextChildAgeBand(prev.child_age_bands), pricing_mode: 'fixed', value: '' }],
  }));
  const applyCommonBands = () => update('child_age_bands', [
    { min_age: 0, max_age: 6, pricing_mode: 'free', value: 0 },
    { min_age: 7, max_age: 11, pricing_mode: 'adult_percentage', value: 50 },
    { min_age: 12, max_age: 17, pricing_mode: 'adult_rate', value: 0 },
  ]);
  const sortedBands = [...draft.child_age_bands].sort((left, right) => left.min_age - right.min_age);
  const draftErrors = validateGuestPricingDraft(draft);
  const placementError = channelProvider === 'exely' ? exelyDraftError(draft, currency) : '';
  const saveErrors = [...draftErrors, ...(placementError ? [placementError] : [])];
  const pmsPreviewReady = draftErrors.length === 0;
  const nextBand = nextChildAgeBand(draft.child_age_bands);
  const base = Number(currentBaseRate || 0);
  const exampleGuests = Number(draft.base_occupancy) + 1;
  const extraRate = draft.extra_adult_rate_type === 'percentage' ? base * Number(draft.extra_adult_rate || 0) / 100 : Number(draft.extra_adult_rate || 0);
  const previewRule = { ...draft, pricing_type: 'per_person', child_age_bands: sortedBands };
  const extraAdultExample = calculateOccupancyPrice({ baseNightlyRate: base, nights: 1, adults: exampleGuests, rule: previewRule });
  const childPreviews = sortedBands.map(band => {
    const sampleAge = Math.floor((Number(band.min_age) + Number(band.max_age)) / 2);
    const result = calculateOccupancyPrice({
      baseNightlyRate: base,
      nights: 1,
      adults: Number(draft.base_occupancy),
      childrenAges: [sampleAge],
      rule: previewRule,
    });
    return { band, supplement: result?.childSupplement, total: result?.nightlyTotal };
  });

  return (
    <div className="border-t border-amber-100 bg-amber-50/40 px-4 py-2" data-testid={`occupancy-pricing-${roomType.code}`}>
      {rule?.policy_invalid && <p className="mb-2 text-xs text-destructive" role="alert">Kayıtlı kişi/çocuk fiyat kuralı geçersiz; otomatik fiyat önerisi uygulanmaz. Yaş kademelerini kontrol edip yeniden kaydedin.</p>}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <span className="text-gray-600">
          {channelProvider === 'exely'
            ? open ? 'Kişi ve çocuk fiyatlandırma kuralları' : exelyPriceOccupancy(rule) ? `Kayıtlı fiyat yerleşimi: ${exelyPriceOccupancy(rule)} yetişkin · ana yatak` : 'Fiyat yerleşimi henüz kaydedilmedi'
            : <>{draft.base_occupancy} yetişkin dahil · Ek yetişkin {draft.extra_adult_rate_type === 'percentage' ? `%${draft.extra_adult_rate}` : `${currencySymbol}${Number(draft.extra_adult_rate || 0).toLocaleString('tr-TR')}`}/gece</>}
        </span>
        <button type="button" onClick={onToggle} className="font-medium text-amber-700 hover:underline">
          {open ? 'Kuralı kapat' : 'Kuralı düzenle'}
        </button>
      </div>
      {rule?.currency && currency && rule.currency !== currency && rule.pricing_type === 'per_person' && ((rule.extra_adult_rate_type !== 'percentage' && Number(rule.extra_adult_rate) > 0) || (rule.child_age_bands || []).some(band => band.pricing_mode === 'fixed' && Number(band.value) > 0) || (rule.exely_price_placements || []).some(row => row.price_mode === 'fixed')) && (
        <p className="mt-1 text-[11px] text-red-700" data-testid={`occupancy-currency-warning-${roomType.code}`}>
          Bu kuraldaki sabit tutarlar {rule.currency} girilmiş; ekran {currency} gösteriyor. Acente satışında farklı para birimindeki sabit ek ücret uygulanmaz, oda satışa kapanır. Tutarları {currency} olarak kontrol edip kaydedin.
        </p>
      )}
      {open && (
        <div className="mt-3 min-w-0 rounded-xl border border-slate-200 bg-white p-3 sm:p-4">
          <div className="mb-4">
            <h3 className="text-sm font-semibold text-slate-900">{roomType.name} · Kişi ve çocuk fiyatları</h3>
            <p className="mt-1 text-xs leading-5 text-slate-600">Önce taban fiyatın kaç yetişkin için olduğunu belirtin. Diğer kişi ve çocuk ücretlerini ilgili bölümden düzenleyin.</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <RuleNumber label="Fiyata dahil yetişkin" value={draft.base_occupancy} min={1} max={20} onChange={v => update('base_occupancy', v === '' ? '' : Number(v))} />
            <RuleNumber label="Maksimum kişi" value={draft.max_occupancy} min={draft.base_occupancy} max={50} optional onChange={v => update('max_occupancy', v)} />
          </div>
          <p className="mt-2 text-[11px] leading-5 text-slate-500">Maksimum kişi, PMS rezervasyon kapasitesidir; Exely’deki yatak kapasitesini değiştirmez.</p>
          {channelProvider === 'exely' && <div className="my-4 grid grid-cols-2 gap-1 rounded-lg bg-slate-100 p-1" role="tablist" aria-label="Fiyat kuralı kapsamı">
            {[['exely', 'Exely tarifeleri'], ['pms', 'PMS ek ücretleri']].map(([key, label]) => <button key={key} type="button" role="tab" id={`${sectionId}-${key}-tab`} aria-controls={`${sectionId}-${key}-panel`} aria-selected={section === key} tabIndex={section === key ? 0 : -1}
              onClick={() => setSection(key)}
              onKeyDown={event => { if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) { event.preventDefault(); const target = event.key === 'Home' ? 'exely' : event.key === 'End' ? 'pms' : section === 'exely' ? 'pms' : 'exely'; setSection(target); document.getElementById(`${sectionId}-${target}-tab`)?.focus(); } }}
              className={`min-w-0 rounded-md px-2 py-2.5 text-xs font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600 ${section === key ? 'bg-white text-blue-900 shadow-sm' : 'text-slate-600'}`}>{label}</button>)}
          </div>}
          {channelProvider === 'exely' && <div role="tabpanel" id={`${sectionId}-exely-panel`} aria-labelledby={`${sectionId}-exely-tab`} hidden={section !== 'exely'} className="mt-4">
            <ExelyPlacementEditor draft={draft} update={update} base={base} currency={currency} pricingType={rule?.pricing_type || 'per_room'} />
          </div>}
          <div role={channelProvider === 'exely' ? 'tabpanel' : undefined} id={`${sectionId}-pms-panel`} aria-labelledby={channelProvider === 'exely' ? `${sectionId}-pms-tab` : undefined} hidden={channelProvider === 'exely' && section !== 'pms'} className="mt-4 space-y-4">
          <div><h4 className="text-sm font-semibold text-slate-900">PMS rezervasyonlarında ek ücretler</h4><p className="mt-1 text-xs leading-5 text-slate-600">Manuel ve doğrudan rezervasyonların hesabında kullanılır. {channelProvider === 'exely' ? 'Bu ücretler Exely’ye otomatik kopyalanmaz; kanal tarifelerini diğer sekmede düzenleyin.' : 'Kanal yöneticisindeki kişi ve çocuk ayarlarını ayrıca kontrol edin.'}</p></div>
          {rule?.pricing_type === 'per_room' && <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-950">Oda bazlı modda bu ek ücretler hesaba katılmaz. Aşağıdaki kurallar ve örnekler, kişi bazlı fiyatlandırma seçildiğinde kullanılır.</p>}
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <label className="text-xs font-medium text-slate-700">Ek yetişkin / gece
              <div className="flex mt-1">
                <select
                  aria-label="PMS ek yetişkin fiyat yöntemi"
                  value={draft.extra_adult_rate_type}
                  onChange={e => update('extra_adult_rate_type', e.target.value)}
                  className="h-10 rounded-l-md border border-r-0 border-slate-300 bg-white px-2 text-sm focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
                >
                  <option value="fixed">{currencySymbol}</option>
                  <option value="percentage">%</option>
                </select>
                <Input
                  aria-label="PMS ek yetişkin ücreti"
                  type="number"
                  value={draft.extra_adult_rate}
                  min={0}
                  step="0.01"
                  onChange={e => update('extra_adult_rate', e.target.value)}
                  className="h-10 min-w-0 rounded-l-none text-sm focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
                />
              </div></label>
              <p className="mt-2 text-xs leading-5 text-slate-600">Dahil yetişkin sayısı aşıldığında, her ek yetişkin için gecelik ücret. {draft.extra_adult_rate_type === 'percentage' ? 'Yüzde, taban oda fiyatından hesaplanır.' : 'Sabit tutar seçili para birimindedir.'}</p>
              {pmsPreviewReady && base > 0 && <p className="mt-1 text-xs font-medium text-slate-900">Ek yetişkin başına: {formatGuestAmount(extraRate, currency)} / gece</p>}
            </div>

          <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3" data-testid={`child-age-bands-${roomType.code}`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-xs font-semibold text-slate-800">Çocuk yaş kademeleri</div>
                <div className="text-[11px] text-slate-500">İlk ve son yaş dahil, giriş tarihindeki yaş esas alınır. 0–17 yaş aralığında boşluk veya çakışma bırakmayın.</div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={applyCommonBands}>
                  0–6 ücretsiz · 7–11 %50 · 12+ yetişkin
                </Button>
                <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={addBand} disabled={!nextBand}>
                  <Plus className="mr-1 h-3.5 w-3.5" /> Kademe ekle
                </Button>
              </div>
            </div>
            <div className="mt-3 space-y-2">
              {draft.child_age_bands.map((band, index) => {
                const needsValue = ['fixed', 'adult_percentage'].includes(band.pricing_mode);
                return (
                  <div key={`child-band-${index}`} data-testid={`pms-child-band-${index}`} className="grid grid-cols-2 items-end gap-3 rounded-lg border bg-white p-3">
                    <RuleNumber label="Başlangıç yaşı" value={band.min_age} min={0} max={17} onChange={value => updateBand(index, 'min_age', value === '' ? '' : Number(value))} />
                    <RuleNumber label="Bitiş yaşı" value={band.max_age} min={0} max={17} onChange={value => updateBand(index, 'max_age', value === '' ? '' : Number(value))} />
                    <label className="col-span-2 text-xs text-slate-700">Ücret yöntemi
                      <select
                        aria-label={`${index + 1}. PMS çocuk ücret yöntemi`}
                        className="mt-1 h-10 w-full rounded-md border border-input bg-white px-2 text-sm"
                        value={band.pricing_mode}
                        onChange={event => updateBand(index, 'pricing_mode', event.target.value)}
                      >
                        <option value="free">Ücretsiz</option>
                        <option value="adult_percentage">Yetişkin ek ücretinin yüzdesi</option>
                        <option value="adult_rate">Yetişkin kontenjanından hesapla</option>
                        <option value="fixed">Sabit ücret / gece</option>
                      </select>
                    </label>
                    {needsValue
                      ? <RuleNumber
                          label={band.pricing_mode === 'adult_percentage' ? 'Ek yetişkin ücretinin %’si' : `Çocuk başı / gece (${currency || currencySymbol})`}
                          value={band.value}
                          min={0}
                          max={band.pricing_mode === 'adult_percentage' ? 100 : undefined}
                          step="0.01"
                          onChange={value => updateBand(index, 'value', value === '' ? '' : Number(value))}
                        />
                      : <p className="text-xs leading-5 text-slate-500">{band.pricing_mode === 'free' ? 'Her çocuk için 0 ek ücret.' : 'Dahil yetişkin kontenjanında yer varsa ek ücret alınmaz; aşılırsa ek yetişkin ücreti uygulanır.'}</p>}
                    <Button type="button" size="icon" variant="ghost" className="h-10 w-10 justify-self-end text-slate-500 hover:text-destructive" aria-label={`${index + 1}. çocuk yaş kademesini sil`} onClick={() => removeBand(index)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                    {band.pricing_mode === 'adult_percentage' && pmsPreviewReady && base > 0 && <p className="col-span-2 text-xs text-slate-600">Ek yetişkin {formatGuestAmount(extraRate, currency)} × %{band.value} = {formatGuestAmount(extraRate * Number(band.value) / 100, currency)} / çocuk / gece. Taban oda fiyatının yüzdesi değildir.</p>}
                  </div>
                );
              })}
            </div>

          </div>

          {pmsPreviewReady && base > 0 && (
            <div className="mt-3 overflow-hidden rounded-lg border border-blue-200 bg-blue-50" data-testid={`occupancy-preview-${roomType.code}`}>
              <div className="border-b border-blue-200 px-3 py-2 text-xs font-semibold text-blue-950">PMS hesap örnekleri · 1 gece</div>
              <div className="grid gap-px bg-blue-100 sm:grid-cols-2 lg:grid-cols-4">
                <div className="bg-white p-3">
                  <div className="text-[11px] text-slate-500">{draft.base_occupancy} yetişkin</div>
                  <div className="mt-1 font-bold text-slate-900">{formatGuestAmount(base, currency)}</div>
                  <div className="text-[10px] text-slate-500">Taban gecelik fiyat</div>
                </div>
                <div className="bg-white p-3">
                  <div className="text-[11px] text-slate-500">{exampleGuests} yetişkin</div>
                  <div className="mt-1 font-bold text-slate-900">{extraAdultExample ? formatGuestAmount(extraAdultExample.nightlyTotal, currency) : 'Kapasite aşılıyor'}</div>
                  <div className="text-[10px] text-slate-500">{extraAdultExample ? `+${formatGuestAmount(extraAdultExample.adultSupplement, currency)} kişi farkı` : 'Maksimum kişi sayısını kontrol edin'}</div>
                </div>
                {childPreviews.map(({ band, supplement, total }) => (
                  <div key={`${band.min_age}-${band.max_age}`} className="bg-white p-3">
                    <div className="text-[11px] text-slate-500">{draft.base_occupancy} yetişkin + {band.min_age}–{band.max_age} yaş 1 çocuk</div>
                    <div className="mt-1 font-bold text-slate-900">{total === undefined ? 'Hesaplanamıyor' : formatGuestAmount(total, currency)}</div>
                    <div className="text-[10px] text-slate-500">{total === undefined ? 'Yaşları ve oda kapasitesini kontrol edin' : supplement > 0 ? `+${formatGuestAmount(supplement, currency)} çocuk farkı` : 'Ücretsiz / dahil'}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
          <p className="text-xs leading-5 text-slate-500">{channelProvider === 'hotelrunner' ? "HotelRunner'a taban fiyat gönderilir; kişi farkı ayarı da aynı olmalıdır. Çocuk yaş kademeleri bu işlemle kanal yöneticisine gönderilmez." : 'Hesap örnekleri yalnız PMS ek ücretlerini gösterir; Exely’ye gidecek fiyatları Exely tarifeleri sekmesinden kontrol edin.'}</p>
          </div>
          {(channelProvider === 'hotelrunner' || channelProvider === 'exely' && rule?.pricing_type === 'per_person' && draft.exely_price_placements.length === 0) && (
            <div className={`mt-3 rounded-lg border p-3 ${draft.provider_pricing_verified ? 'border-emerald-200 bg-emerald-50' : 'border-red-200 bg-red-50'}`}>
              <label className="flex cursor-pointer items-start gap-2 text-xs font-medium text-slate-800">
                <Checkbox
                  checked={draft.provider_pricing_verified}
                  onCheckedChange={value => update('provider_pricing_verified', Boolean(value))}
                  data-testid={`${channelProvider}-pricing-attestation-${roomType.code}`}
                />
                <span>
                  {providerName} panelindeki dahil yetişkin, ek yetişkin ve tüm çocuk yaş kademeleri bu değerlerle eşleşiyor.
                  <span className="mt-1 block font-normal text-slate-600">{channelProvider === 'hotelrunner' ? "Bu onay olmadan HotelRunner'a taban fiyat gönderimi güvenlik amacıyla durdurulur." : 'Bu onay olmadan tanımlı kişi bazlı kural için birleşik fiyat ekranından Exely taban fiyat gönderimi durdurulur. Onay, Exely ayarlarını değiştirmez veya otomatik sertifikasyon sağlamaz.'}</span>
                </span>
              </label>
              <Input
                className="mt-2 h-8 bg-white text-xs"
                value={draft.provider_pricing_note}
                onChange={event => update('provider_pricing_note', event.target.value)}
                placeholder="İsteğe bağlı kontrol notu"
                maxLength={500}
              />
            </div>
          )}
          {saveErrors.length > 0 && <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800" role="alert" data-testid="guest-pricing-save-errors"><p className="font-semibold">Kaydetmeden önce kontrol edin</p><ul className="mt-1 list-disc space-y-1 pl-4">{saveErrors.map(error => <li key={error}>{error}</li>)}</ul></div>}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
            <p className="max-w-sm text-xs leading-5 text-slate-500">Yalnız bu odanın kuralları kaydedilir. Tarih bazlı fiyatlar değişmez, kanala fiyat gönderilmez.</p>
            <Button
              type="button"
              size="sm"
              disabled={submitting || saveErrors.length > 0}
              onClick={async () => {
                if (saveErrors.length) return;
                setSubmitting(true);
                try {
                  const freeBand = sortedBands[0]?.pricing_mode === 'free' && sortedBands[0]?.min_age === 0 ? sortedBands[0] : null;
                  const fixedBand = sortedBands.find(band => band.pricing_mode === 'fixed');
                  await onSave({
                    ...draft,
                    base_occupancy: Number(draft.base_occupancy),
                    extra_adult_rate: Number(draft.extra_adult_rate),
                    extra_adult_rate_type: draft.extra_adult_rate_type,
                    extra_child_rate: Number(fixedBand?.value || 0),
                    child_free_age_max: Number(freeBand?.max_age || 0),
                    child_age_bands: sortedBands.map(band => ({
                      min_age: Number(band.min_age),
                      max_age: Number(band.max_age),
                      pricing_mode: band.pricing_mode,
                      value: Number(band.value || 0),
                    })),
                    max_occupancy: draft.max_occupancy === '' ? null : Number(draft.max_occupancy),
                  });
                  toast.success('Kural başarıyla kaydedildi');
                  onToggle();
                } catch (err) {
                  toast.error(err?.response?.data?.detail || err?.message || 'Kural kaydedilirken bir hata oluştu');
                } finally {
                  setSubmitting(false);
                }
              }}
              data-testid={`save-occupancy-rule-${roomType.code}`}
            >
              {submitting && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
              Kuralı kaydet
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

const RuleNumber = ({ label, value, onChange, optional = false, ...inputProps }) => (
  <label className="block min-w-0 text-xs text-slate-700">
    {label}
    <Input type="number" value={value} aria-label={label} placeholder={optional ? 'Sınır yok' : undefined}
      onChange={event => onChange(event.target.value)} className="mt-1 h-10 text-sm" {...inputProps} />
  </label>
);
