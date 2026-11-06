import { useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Save, Loader2, RotateCcw, Home, Moon, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, AlertTriangle, CopyCheck, Eye, Sparkles } from 'lucide-react';
import { DAYS, UPDATE_FIELDS, UPDATE_FIELD_PRESETS, usesExpandedAriLayout } from './constants';
import { ChannelList } from './ChannelList';
import { buildRateUpdateReview, exelyPriceOccupancy, isExelyPricePlanWritable } from './updateReview';
import { useTranslation } from 'react-i18next';
import { OccupancyPricingEditor } from './OccupancyPricingEditor';
import { RatePublishReview } from './RatePublishReview';

export { OccupancyPricingEditor } from './OccupancyPricingEditor';

export const BulkUpdatePanel = ({
  roomTypeTree, roomTypes, ratePlans, enabledFields, toggleField, applyFieldPreset,
  dateFrom, setDateFrom, dateTo, setDateTo,
  allDays, selectedDays, toggleDay, toggleAllDays,
  selections, toggleRoomType, toggleAllRoomTypes, toggleRatePlan,
  isRoomTypeSelected, isRoomTypeFullySelected, isRatePlanSelected,
  roomValues, updateRoomValue, getDefaultValues, applyToAllSelected,
  expandedRoomTypes, toggleExpanded,
  pricingSettings, occupancyPricingRules, saveOccupancyPricingRule, getPricingLabel, togglePricingType, currencySymbol, currency,
  totalSelectedRoomTypes, totalSelectedPlans,
  saving, handleBulkUpdate, handleReset, loading,
  activeChannels, activeChannelsStale, selectedChannelCodes, toggleChannel, toggleAllChannels, channelProvider,
  agenciesOnly = false,
  exelyPlacementsSupported = true,
  mobileStep = 1, setMobileStep,
}) => {
  const { t } = useTranslation();
  const [reviewOpen, setReviewOpen] = useState(false);
  const review = useMemo(() => buildRateUpdateReview({
    dateFrom, dateTo, allDays, selectedDays, selections, enabledFields, roomValues,
    selectedChannelCodes, activeChannelsStale, channelProvider, agenciesOnly,
    ratePlans, roomTypes, occupancyPricingRules, currency, exelyPlacementsSupported,
  }), [dateFrom, dateTo, allDays, selectedDays, selections, enabledFields, roomValues, selectedChannelCodes, activeChannelsStale, channelProvider, agenciesOnly, ratePlans, roomTypes, occupancyPricingRules, currency, exelyPlacementsSupported]);
  const canContinueFromFields = enabledFields.size > 0 && Boolean(dateFrom) && Boolean(dateTo);
  const canContinueFromRooms = totalSelectedRoomTypes > 0;
  const goToStep = (step) => setMobileStep?.(Math.max(1, Math.min(3, step)));
  // Four or more simultaneous ARI fields no longer fit comfortably between
  // both sidebars. On wide screens stack the channel selector under the
  // filters and give the editor the remaining page width instead of creating
  // a narrow, internally scrolling table.
  const wideFieldLayout = usesExpandedAriLayout(enabledFields.size);
  const remainingAvailability = channelProvider === 'exely' && !agenciesOnly;

  return (
  <div>
    <div className="mb-4 lg:hidden" data-testid="rate-mobile-wizard">
      <div className="grid grid-cols-3 gap-1 rounded-xl border border-slate-200 bg-slate-50 p-1">
        {[
          [1, 'Alan ve tarih'],
          [2, 'Oda ve fiyat'],
          [3, 'Kanal ve onay'],
        ].map(([step, label]) => (
          <button
            key={step}
            type="button"
            onClick={() => goToStep(step)}
            disabled={(step === 2 && !canContinueFromFields) || (step === 3 && (!canContinueFromFields || !canContinueFromRooms))}
            className={`rounded-lg px-1.5 py-2 text-center text-[11px] font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${mobileStep === step ? 'bg-white text-amber-700 shadow-sm' : 'text-slate-500'}`}
            aria-current={mobileStep === step ? 'step' : undefined}
            data-testid={`rate-mobile-step-${step}`}
          >
            <span className={`mx-auto mb-1 flex h-5 w-5 items-center justify-center rounded-full text-[10px] ${mobileStep === step ? 'bg-amber-600 text-white' : 'bg-slate-200 text-slate-600'}`}>{step}</span>
            {label}
          </button>
        ))}
      </div>
    </div>

    <div
      className={wideFieldLayout
        ? 'flex flex-col gap-4 lg:grid lg:grid-cols-[240px_minmax(0,1fr)] lg:items-start'
        : 'flex flex-col gap-4 lg:flex-row'}
      data-layout={wideFieldLayout ? 'expanded' : 'standard'}
      data-testid="bulk-update-layout"
    >
      {/* LEFT PANEL: Filters */}
      <div className={`${mobileStep === 1 ? 'block' : 'hidden'} w-full flex-shrink-0 space-y-4 lg:block lg:w-[240px]`} data-testid="bulk-left-panel">
        {/* Update Fields Selection */}
        <Card>
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-semibold text-gray-700">
              Neleri güncellemek istiyorsunuz?
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-2">
            <div className="mb-3 flex flex-wrap gap-1.5" aria-label="Hızlı güncelleme şablonları">
              {UPDATE_FIELD_PRESETS.map(preset => (
                <Button
                  key={preset.key}
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-7 px-2 text-[11px]"
                  onClick={() => applyFieldPreset?.(preset.fields)}
                  data-testid={`rate-preset-${preset.key}`}
                >
                  <Sparkles className="mr-1 h-3 w-3" /> {preset.label}
                </Button>
              ))}
            </div>
            {UPDATE_FIELDS.filter(f => !f.providers || f.providers.includes(channelProvider)).map(f => (
              <label key={f.key} className="flex items-center gap-2 cursor-pointer text-sm" data-testid={`field-${f.key}`}>
                <Checkbox
                  checked={enabledFields.has(f.key)}
                  onCheckedChange={() => toggleField(f.key)}
                />
                <span className={enabledFields.has(f.key) ? 'text-gray-900 font-medium' : 'text-gray-600'}>
                  {f.key === 'availability' && remainingAvailability ? 'Müsait oda (net)' : f.label}
                </span>
              </label>
            ))}
            {remainingAvailability && enabledFields.has('availability') && <p className="rounded border border-sky-200 bg-sky-50 p-2 text-xs text-sky-900" data-testid="remaining-availability-help">
              Sayı girerseniz doluluktan bağımsız manuel satış kontenjanı gönderilir; fiziksel kapasite aşılabilir (overbooking). Sonraki yeni rezervasyonlarla azalır. Boş bırakarak yayımlarsanız seçili günler rezervasyon ve blokajlara göre otomatik hesaplanır. 0, sıfır satış kontenjanıdır.
            </p>}
          </CardContent>
        </Card>

        {/* Date Range */}
        <Card>
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_ratemanager_BulkUpdatePanel.tarih_araligi')}</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-2">
            <div>
              <Label className="text-xs text-gray-500">Başlangıç</Label>
              <Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="mt-1 h-8 text-sm" data-testid="bulk-date-from" />
            </div>
            <div>
              <Label className="text-xs text-gray-500">Bitiş</Label>
              <Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="mt-1 h-8 text-sm" data-testid="bulk-date-to" />
            </div>
          </CardContent>
        </Card>

        {/* Day Selection */}
        <Card>
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-semibold text-gray-700">Gün</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-1.5">
            <label className="flex items-center gap-2 cursor-pointer text-sm font-medium" data-testid="day-all">
              <Checkbox checked={allDays} onCheckedChange={toggleAllDays} />
              <span>Hepsi</span>
            </label>
            {DAYS.map(d => (
              <label key={d.value} className="flex items-center gap-2 cursor-pointer text-sm" data-testid={`day-${d.value}`}>
                <Checkbox checked={selectedDays.has(d.value)} onCheckedChange={() => toggleDay(d.value)} />
                <span className={selectedDays.has(d.value) ? 'text-gray-900' : 'text-gray-500'}>{d.label}</span>
              </label>
            ))}
          </CardContent>
        </Card>

        {/* Action Buttons */}
        <div className="hidden gap-2 lg:flex">
          <Button className="flex-1 bg-amber-600 hover:bg-amber-700 text-white" onClick={() => setReviewOpen(true)} disabled={saving} data-testid="bulk-update-btn">
            <Eye className="w-4 h-4 mr-1.5" />
            Önizle
          </Button>
          <Button variant="outline" onClick={handleReset} data-testid="bulk-reset-btn">
            <RotateCcw className="w-4 h-4 mr-1" />
            Sıfırla
          </Button>
        </div>
      </div>

      {/* CENTER PANEL: Room Types Table */}
      <div className={`${mobileStep === 2 ? 'block' : 'hidden'} min-w-0 flex-1 lg:block ${wideFieldLayout ? 'lg:col-start-2 lg:row-span-2 lg:row-start-1' : ''}`} data-testid="bulk-center-panel">
        <Card className="h-full">
          <CardHeader className="pb-2 pt-4 px-4">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_ratemanager_BulkUpdatePanel.oda_adi')}</CardTitle>
              <button onClick={toggleAllRoomTypes} className="text-xs text-blue-600 hover:underline" data-testid="select-all-rooms">
                {roomTypes.length > 0 && roomTypes.every(rt => isRoomTypeFullySelected(rt.code)) ? 'Tümünü kaldır' : 'Tümünü seç'}
              </button>
            </div>
          </CardHeader>
          <CardContent className="px-0 pb-4">
            {loading && roomTypes.length === 0 ? (
              <div className="flex items-center justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
            ) : roomTypes.length === 0 ? (
              <div className="text-center py-12 text-gray-400 text-sm px-4">{t('cm.pages_ratemanager_BulkUpdatePanel.exely_baglantisi_bulunamadi_veya_oda_tip')}</div>
            ) : (
              <RoomTypeList
                roomTypeTree={roomTypeTree} enabledFields={enabledFields} selections={selections}
                roomValues={roomValues} updateRoomValue={updateRoomValue} getDefaultValues={getDefaultValues} applyToAllSelected={applyToAllSelected}
                expandedRoomTypes={expandedRoomTypes} toggleExpanded={toggleExpanded}
                isRoomTypeSelected={isRoomTypeSelected} isRoomTypeFullySelected={isRoomTypeFullySelected}
                isRatePlanSelected={isRatePlanSelected}
                toggleRoomType={toggleRoomType} toggleRatePlan={toggleRatePlan}
                pricingSettings={pricingSettings} occupancyPricingRules={occupancyPricingRules} saveOccupancyPricingRule={saveOccupancyPricingRule} getPricingLabel={getPricingLabel} togglePricingType={togglePricingType}
                currencySymbol={currencySymbol} currency={currency}
                channelProvider={channelProvider}
                canRemoveLos={channelProvider === 'exely' && !agenciesOnly}
                remainingAvailability={remainingAvailability}
                exelyPriceSelection={channelProvider === 'exely' && !agenciesOnly && enabledFields.has('rate')}
                totalSelectedRoomTypes={Object.keys(selections).length}
                wideFieldLayout={wideFieldLayout}
              />
            )}
          </CardContent>
        </Card>
      </div>

      {/* RIGHT PANEL: Channels */}
      <div className={`${mobileStep === 3 ? 'block' : 'hidden'} w-full flex-shrink-0 lg:block ${wideFieldLayout ? 'lg:col-start-1 lg:row-start-2 lg:w-auto' : 'lg:w-[200px]'}`} data-testid="bulk-right-panel">
        <Card className="h-full">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-semibold text-gray-700">Kanallar</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <ChannelList channels={activeChannels} stale={activeChannelsStale} selectedChannelCodes={selectedChannelCodes} onToggle={toggleChannel} onToggleAll={toggleAllChannels} provider={channelProvider} />
          </CardContent>
        </Card>
      </div>
    </div>

    {/* Summary Bar */}
    {(totalSelectedRoomTypes > 0 || enabledFields.size > 0) && (
      <Card className={`${mobileStep === 3 ? 'block' : 'hidden'} border-amber-200 bg-amber-50/50 mt-4 lg:block`} data-testid="bulk-summary">
        <CardContent className="py-3 px-4">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="font-medium text-gray-700">{t('cm.pages_ratemanager_BulkUpdatePanel.ozet')}</span>
            <Badge variant="outline" className="bg-white">{totalSelectedRoomTypes} oda tipi</Badge>
            <Badge variant="outline" className="bg-white">{totalSelectedPlans} plan</Badge>
            <Badge variant="outline" className="bg-white">{enabledFields.size} alan</Badge>
            <Badge variant="outline" className="bg-white">{review.dateCount} hedef gece</Badge>
            <Badge variant="outline" className="bg-white">{review.cellCount.toLocaleString('tr-TR')} fiyat-plan hücresi</Badge>
            <Badge variant="outline" className="bg-white">{review.channelCount} OTA kanalı</Badge>
            <Badge variant="outline" className="bg-white">{dateFrom} → {dateTo}</Badge>
            {!allDays && <Badge variant="outline" className="bg-white">{selectedDays.size} gün</Badge>}
          </div>
        </CardContent>
      </Card>
    )}

    {reviewOpen && <RatePublishReview review={review} saving={saving} onClose={() => setReviewOpen(false)} onPublish={handleBulkUpdate} />}

    <div className="sticky bottom-0 z-20 -mx-4 mt-4 border-t border-slate-200 bg-white/95 px-4 pt-3 safe-bottom-padding backdrop-blur lg:hidden" data-testid="rate-mobile-wizard-actions">
      <div className="flex items-center gap-2">
        {mobileStep > 1 && (
          <Button type="button" variant="outline" onClick={() => goToStep(mobileStep - 1)} className="flex-1" data-testid="rate-mobile-previous">
            <ChevronLeft className="mr-1 h-4 w-4" /> Geri
          </Button>
        )}
        {mobileStep < 3 ? (
          <Button
            type="button"
            onClick={() => goToStep(mobileStep + 1)}
            disabled={mobileStep === 1 ? !canContinueFromFields : !canContinueFromRooms}
            className="flex-1 bg-amber-600 text-white hover:bg-amber-700"
            data-testid="rate-mobile-next"
          >
            Devam <ChevronRight className="ml-1 h-4 w-4" />
          </Button>
        ) : (
          <>
            <Button type="button" variant="outline" size="icon" onClick={() => { handleReset(); goToStep(1); }} data-testid="rate-mobile-reset" aria-label="Sıfırla">
              <RotateCcw className="h-4 w-4" />
            </Button>
            <Button className="flex-[2] bg-amber-600 text-white hover:bg-amber-700" onClick={() => setReviewOpen(true)} disabled={saving || !canContinueFromFields || !canContinueFromRooms} data-testid="rate-mobile-update">
              <Eye className="mr-1.5 h-4 w-4" />
              Önizle ve yayınla
            </Button>
          </>
        )}
      </div>
    </div>
  </div>
  );
};

const gridColTemplate = (enabledFields) =>
  `minmax(220px, 1fr)${enabledFields.has('rate') ? ' 150px' : ''}${enabledFields.has('availability') ? ' 130px' : ''}${enabledFields.has('min_stay') ? ' 150px' : ''}${enabledFields.has('min_los_arrival') ? ' 180px' : ''}${enabledFields.has('max_stay') ? ' 150px' : ''}${enabledFields.has('stop_sell') ? ' 100px' : ''}${enabledFields.has('cta') ? ' 80px' : ''}${enabledFields.has('ctd') ? ' 80px' : ''}`;

const ApplyAllButton = ({ field, value, applyToAllSelected, totalSelectedRoomTypes }) => {
  const { t } = useTranslation();
  if (totalSelectedRoomTypes < 2 || value === null || value === undefined || value === '') return null;
  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); applyToAllSelected(field, value); }}
      className="text-amber-500 hover:text-amber-700 p-0.5 transition-colors flex-shrink-0"
      title="Tümüne uygula"
      data-testid={`apply-all-${field}`}
    >
      <CopyCheck className="w-3.5 h-3.5" />
    </button>
  );
};

const LosInput = ({ value, onChange, label, testId, canRemove }) => (
  <div className="min-w-0 flex-1">
    <Input type="number" min={canRemove ? '0' : '1'} placeholder={label} aria-label={label} value={value} onChange={e => onChange(e.target.value)} className="h-8 text-sm" data-testid={testId} />
    {canRemove && <button type="button" className="text-[11px] text-amber-700 underline" aria-label={`${label} kısıtını kaldır`} onClick={() => onChange('0')}>
      {String(value) === '0' ? 'Kısıt kaldırılacak' : 'Kısıtı kaldır'}
    </button>}
  </div>
);

const RoomTypeList = ({
  roomTypeTree, enabledFields, selections, roomValues, updateRoomValue, getDefaultValues, applyToAllSelected,
  expandedRoomTypes, toggleExpanded, isRoomTypeSelected, isRoomTypeFullySelected, isRatePlanSelected,
  toggleRoomType, toggleRatePlan, pricingSettings, occupancyPricingRules, saveOccupancyPricingRule, getPricingLabel, togglePricingType, currencySymbol, currency,
  totalSelectedRoomTypes, channelProvider, wideFieldLayout, canRemoveLos, remainingAvailability, exelyPriceSelection,
}) => {
  const { t } = useTranslation();
  const [editingRule, setEditingRule] = useState(null);
  return (
  <div className={wideFieldLayout ? 'overflow-x-auto xl:overflow-x-visible' : 'overflow-x-auto'} data-testid="room-type-list">
    {/* Table Header */}
    <div className="grid items-center border-b bg-gray-50 px-4 py-2 text-xs font-medium text-gray-500 gap-3"
      style={{ gridTemplateColumns: 'minmax(220px, 1fr) repeat(auto-fit, minmax(130px, 1fr))' }}>
      <div className="grid items-center gap-3" style={{ gridTemplateColumns: gridColTemplate(enabledFields) }}>
        <span>{t('cm.pages_ratemanager_BulkUpdatePanel.oda_adi_8e806')}</span>
        {enabledFields.has('rate') && <span className="flex items-center gap-1">{currencySymbol} Fiyat</span>}
        {enabledFields.has('availability') && <span className="flex items-center gap-1"><Home className="w-3 h-3" /> {remainingAvailability ? 'Net kalan oda' : 'Müsaitlik'}</span>}
        {enabledFields.has('min_stay') && <span className="flex items-center gap-1"><Moon className="w-3 h-3" /> Min. konaklama</span>}
        {enabledFields.has('min_los_arrival') && <span className="flex items-center gap-1"><Moon className="w-3 h-3" /> Varış bazlı min.</span>}
        {enabledFields.has('max_stay') && <span className="flex items-center gap-1"><Moon className="w-3 h-3" /> Max. konaklama</span>}
        {enabledFields.has('stop_sell') && <span>{t('cm.pages_ratemanager_BulkUpdatePanel.satis_durdur')}</span>}
        {enabledFields.has('cta') && <span>CTA</span>}
        {enabledFields.has('ctd') && <span>CTD</span>}
      </div>
    </div>

    {/* Room Type Rows */}
    <div className="divide-y">
      {roomTypeTree.map(rt => {
        const rv = roomValues[rt.code] || getDefaultValues();
        const isSelected = isRoomTypeSelected(rt.code);
        const isExpanded = expandedRoomTypes.has(rt.code) || exelyPriceSelection && isSelected;
        const colTemplate = gridColTemplate(enabledFields);

        return (
          <div key={rt.code} data-testid={`room-type-row-${rt.code}`}>
            <div className={`grid items-center px-4 py-3 gap-3 transition-colors ${isSelected ? 'bg-amber-50/60' : 'hover:bg-gray-50'}`}
              style={{ gridTemplateColumns: colTemplate }}>
              <div className="flex items-center gap-2">
                <Checkbox checked={isRoomTypeFullySelected(rt.code)} onCheckedChange={() => toggleRoomType(rt.code)} data-testid={`room-type-check-${rt.code}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-sm text-gray-900">{rt.name}</span>
                    {rt.availability_update === false && (
                      <span className="inline-flex items-center gap-0.5 text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded font-medium" title={t('cm.pages_ratemanager_BulkUpdatePanel.hotelrunner_bu_oda_tipi_icin_musaitlik_g')}>
                        <AlertTriangle className="w-2.5 h-2.5" /> {t('cm.pages_ratemanager_BulkUpdatePanel.musaitlik_kapali')}
                      </span>
                    )}
                    {rt.price_update === false && (
                      <span className="inline-flex items-center gap-0.5 text-[10px] bg-red-100 text-red-700 px-1.5 py-0.5 rounded font-medium" title={t('cm.pages_ratemanager_BulkUpdatePanel.hotelrunner_bu_oda_tipi_icin_fiyat_gunce')}>
                        <AlertTriangle className="w-2.5 h-2.5" /> {t('cm.pages_ratemanager_BulkUpdatePanel.fiyat_kapali')}
                      </span>
                    )}
                  </div>
                  <button onClick={(e) => togglePricingType(rt.code, e)}
                    className={`text-xs italic cursor-pointer hover:underline transition-colors ${(pricingSettings[rt.code] || 'per_person') === 'per_room' ? 'text-blue-600' : 'text-amber-600'}`}
                    data-testid={`pricing-type-toggle-${rt.code}`}>
                    {getPricingLabel(rt.code)}
                  </button>
                </div>
                {rt.plans.length > 0 && !(exelyPriceSelection && isSelected) && (
                  <button aria-label={`${rt.name} fiyat planlarını göster veya gizle`} onClick={() => toggleExpanded(rt.code)} className="text-gray-400 hover:text-gray-600 p-0.5" data-testid={`expand-toggle-${rt.code}`}>
                    {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>
                )}
              </div>

              {enabledFields.has('rate') && (
                <div className="flex items-center gap-1">
                  <span className="text-xs text-gray-400">{currencySymbol}</span>
                  <Input type="number" step="0.01" placeholder="Fiyat" value={rv.rate} onChange={e => updateRoomValue(rt.code, 'rate', e.target.value)} className="h-8 text-sm" data-testid={`rate-input-${rt.code}`} />
                  <ApplyAllButton field="rate" value={rv.rate} applyToAllSelected={applyToAllSelected} totalSelectedRoomTypes={totalSelectedRoomTypes} />
                </div>
              )}
              {enabledFields.has('availability') && (
                <div className="flex items-center gap-1">
                  <Home className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                  <Input type="number" min="0" step="1" max={remainingAvailability ? '999' : undefined} placeholder={remainingAvailability ? 'Boş: otomatik' : 'Müsaitlik'} aria-label={remainingAvailability ? `Net müsait oda — ${rt.name}` : `Müsaitlik — ${rt.name}`} value={rv.availability} onChange={e => updateRoomValue(rt.code, 'availability', e.target.value)} className="h-8 text-sm" data-testid={`avail-input-${rt.code}`} />
                  <ApplyAllButton field="availability" value={rv.availability} applyToAllSelected={applyToAllSelected} totalSelectedRoomTypes={totalSelectedRoomTypes} />
                </div>
              )}
              {enabledFields.has('min_stay') && (
                <div className="flex items-center gap-1">
                  <Moon className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                  <LosInput label="Min. konaklama" value={rv.min_stay} onChange={value => updateRoomValue(rt.code, 'min_stay', value)} canRemove={canRemoveLos} testId={`min-stay-input-${rt.code}`} />
                  <ApplyAllButton field="min_stay" value={rv.min_stay} applyToAllSelected={applyToAllSelected} totalSelectedRoomTypes={totalSelectedRoomTypes} />
                </div>
              )}
              {enabledFields.has('min_los_arrival') && (
                <div className="flex items-center gap-1">
                  <Moon className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                  <LosInput label="Varış bazlı min." value={rv.min_los_arrival} onChange={value => updateRoomValue(rt.code, 'min_los_arrival', value)} canRemove={canRemoveLos} testId={`min-los-arrival-input-${rt.code}`} />
                  <ApplyAllButton field="min_los_arrival" value={rv.min_los_arrival} applyToAllSelected={applyToAllSelected} totalSelectedRoomTypes={totalSelectedRoomTypes} />
                </div>
              )}
              {enabledFields.has('max_stay') && (
                <div className="flex items-center gap-1">
                  <Moon className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                  <LosInput label="Max. konaklama" value={rv.max_stay} onChange={value => updateRoomValue(rt.code, 'max_stay', value)} canRemove={canRemoveLos} testId={`max-stay-input-${rt.code}`} />
                  <ApplyAllButton field="max_stay" value={rv.max_stay} applyToAllSelected={applyToAllSelected} totalSelectedRoomTypes={totalSelectedRoomTypes} />
                </div>
              )}
              {enabledFields.has('stop_sell') && (
                <div className="flex items-center justify-center gap-1">
                  <Checkbox checked={!!rv.stop_sell} onCheckedChange={v => updateRoomValue(rt.code, 'stop_sell', v)} data-testid={`stop-sell-${rt.code}`} />
                  <ApplyAllButton field="stop_sell" value={rv.stop_sell} applyToAllSelected={applyToAllSelected} totalSelectedRoomTypes={totalSelectedRoomTypes} />
                </div>
              )}
              {enabledFields.has('cta') && (
                <div className="flex items-center justify-center gap-1">
                  <Checkbox checked={!!rv.cta} onCheckedChange={v => updateRoomValue(rt.code, 'cta', v)} data-testid={`cta-${rt.code}`} />
                  <ApplyAllButton field="cta" value={rv.cta} applyToAllSelected={applyToAllSelected} totalSelectedRoomTypes={totalSelectedRoomTypes} />
                </div>
              )}
              {enabledFields.has('ctd') && (
                <div className="flex items-center justify-center gap-1">
                  <Checkbox checked={!!rv.ctd} onCheckedChange={v => updateRoomValue(rt.code, 'ctd', v)} data-testid={`ctd-${rt.code}`} />
                  <ApplyAllButton field="ctd" value={rv.ctd} applyToAllSelected={applyToAllSelected} totalSelectedRoomTypes={totalSelectedRoomTypes} />
                </div>
              )}
            </div>

            {exelyPriceSelection && <p className="border-t bg-blue-50 px-4 py-2 text-xs text-blue-950" data-testid={`exely-price-occupancy-${rt.code}`}>
              {exelyPriceOccupancy(occupancyPricingRules?.[rt.code])
                ? `Kanal fiyatı: ${exelyPriceOccupancy(occupancyPricingRules[rt.code])} yetişkin için oda/gece toplamı (ana yatak). ${(pricingSettings[rt.code] || 'per_person') === 'per_person' && occupancyPricingRules[rt.code]?.exely_price_placements?.length ? 'Kayıtlı kişi, çocuk ve ek yatak fiyatları da gönderilir.' : 'Yalnız taban yerleşimi gönderilir.'}`
                : 'Kişi sayısı henüz kaydedilmedi. Kuralı düzenleyip fiyata dahil ana yatak yetişkin sayısını kaydedin; gönderim kişi sayısı olmadan başlatılmaz.'}
            </p>}
            {((pricingSettings[rt.code] || 'per_person') === 'per_person' || exelyPriceSelection) && (
              <OccupancyPricingEditor
                roomType={rt}
                open={editingRule === rt.code}
                onToggle={() => setEditingRule(editingRule === rt.code ? null : rt.code)}
                rule={occupancyPricingRules?.[rt.code]}
                onSave={async rule => {
                  await saveOccupancyPricingRule(rt.code, { ...rule, pricing_type: pricingSettings[rt.code] || 'per_person' });
                  setEditingRule(null);
                }}
                currentBaseRate={rv.rate}
                currencySymbol={currencySymbol}
                currency={currency}
                channelProvider={channelProvider}
              />
            )}

            {/* Expanded Rate Plans */}
            {isExpanded && rt.plans.map(rp => (
              <div key={`${rt.code}-${rp.code}`}
                className={`grid items-center px-4 py-2 pl-10 gap-3 border-t border-gray-100 transition-colors ${isRatePlanSelected(rt.code, rp.code) ? 'bg-blue-50/40' : 'hover:bg-gray-50'}`}
                style={{ gridTemplateColumns: colTemplate }}
                data-testid={`rate-plan-row-${rt.code}-${rp.code}`}>
                <label className="flex items-center gap-2 cursor-pointer">
                  <Checkbox checked={isRatePlanSelected(rt.code, rp.code)} onCheckedChange={() => toggleRatePlan(rt.code, rp.code)}
                    disabled={exelyPriceSelection && !isExelyPricePlanWritable(rp, rt.code) && !isRatePlanSelected(rt.code, rp.code)}
                    aria-label={`${rt.name} — ${rp.name} fiyat planı`} data-testid={`rate-plan-check-${rt.code}-${rp.code}`} />
                  <div className="min-w-0">
                    <div className="text-sm text-gray-700">{rt.name} - {rp.name}</div>
                    {exelyPriceSelection && !isExelyPricePlanWritable(rp, rt.code) && <div className="text-xs text-amber-800">Exely doğrudan fiyat yüklemesi kapalı</div>}
                    <div className={`text-xs italic ${(pricingSettings[rt.code] || 'per_person') === 'per_room' ? 'text-blue-400' : 'text-gray-400'}`}>
                      {getPricingLabel(rt.code)}
                    </div>
                  </div>
                </label>
                {enabledFields.has('rate') && <div className="text-xs text-gray-400 italic">{rv.rate ? `Ana Fiyat: ${rv.rate} ${currency}` : '\u2014'}</div>}
                {enabledFields.has('availability') && <div className="text-xs text-gray-400 italic">{rv.availability !== '' && rv.availability != null ? rv.availability : remainingAvailability ? 'Otomatik' : '\u2014'}</div>}
                {enabledFields.has('min_stay') && <div className="text-xs text-gray-400 italic">{rv.min_stay ? rv.min_stay : '\u2014'}</div>}
                {enabledFields.has('min_los_arrival') && <div className="text-xs text-gray-400 italic">{rv.min_los_arrival ? rv.min_los_arrival : '\u2014'}</div>}
                {enabledFields.has('max_stay') && <div className="text-xs text-gray-400 italic">{rv.max_stay ? rv.max_stay : '\u2014'}</div>}
                {enabledFields.has('stop_sell') && <div />}
                {enabledFields.has('cta') && <div />}
                {enabledFields.has('ctd') && <div />}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  </div>
  );
};
