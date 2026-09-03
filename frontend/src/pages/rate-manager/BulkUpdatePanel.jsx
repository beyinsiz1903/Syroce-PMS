import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Save, Loader2, RotateCcw, Home, Moon, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, AlertTriangle, CopyCheck, Plus, Trash2 } from 'lucide-react';
import { DAYS, UPDATE_FIELDS } from './constants';
import { ChannelList } from './ChannelList';
import { useTranslation } from 'react-i18next';
import { normalizeOccupancyRule } from '@/utils/occupancyPricing';

export const BulkUpdatePanel = ({
  roomTypeTree, roomTypes, ratePlans, enabledFields, toggleField,
  dateFrom, setDateFrom, dateTo, setDateTo,
  allDays, selectedDays, toggleDay, toggleAllDays,
  selections, toggleRoomType, toggleAllRoomTypes, toggleRatePlan,
  isRoomTypeSelected, isRoomTypeFullySelected, isRatePlanSelected,
  roomValues, updateRoomValue, getDefaultValues, applyToAllSelected,
  expandedRoomTypes, toggleExpanded,
  pricingSettings, occupancyPricingRules, saveOccupancyPricingRule, getPricingLabel, togglePricingType, currencySymbol, currency,
  totalSelectedRoomTypes, totalSelectedPlans,
  saving, handleBulkUpdate, handleReset, loading,
  activeChannels, activeChannelsStale, channelProvider,
  mobileStep = 1, setMobileStep,
}) => {
  const { t } = useTranslation();
  const canContinueFromFields = enabledFields.size > 0 && Boolean(dateFrom) && Boolean(dateTo);
  const canContinueFromRooms = totalSelectedRoomTypes > 0;
  const goToStep = (step) => setMobileStep?.(Math.max(1, Math.min(3, step)));

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

    <div className="flex flex-col lg:flex-row gap-4" data-testid="bulk-update-layout">
      {/* LEFT PANEL: Filters */}
      <div className={`${mobileStep === 1 ? 'block' : 'hidden'} w-full flex-shrink-0 space-y-4 lg:block lg:w-[240px]`} data-testid="bulk-left-panel">
        {/* Update Fields Selection */}
        <Card>
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-semibold text-gray-700">
              Neleri guncellemek istiyorsunuz?
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-2">
            {UPDATE_FIELDS.map(f => (
              <label key={f.key} className="flex items-center gap-2 cursor-pointer text-sm" data-testid={`field-${f.key}`}>
                <Checkbox
                  checked={enabledFields.has(f.key)}
                  onCheckedChange={() => toggleField(f.key)}
                />
                <span className={enabledFields.has(f.key) ? 'text-gray-900 font-medium' : 'text-gray-600'}>
                  {f.label}
                </span>
              </label>
            ))}
          </CardContent>
        </Card>

        {/* Date Range */}
        <Card>
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_ratemanager_BulkUpdatePanel.tarih_araligi')}</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-2">
            <div>
              <Label className="text-xs text-gray-500">Baslangic</Label>
              <Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="mt-1 h-8 text-sm" data-testid="bulk-date-from" />
            </div>
            <div>
              <Label className="text-xs text-gray-500">Bitis</Label>
              <Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="mt-1 h-8 text-sm" data-testid="bulk-date-to" />
            </div>
          </CardContent>
        </Card>

        {/* Day Selection */}
        <Card>
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-semibold text-gray-700">Gun</CardTitle>
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
          <Button className="flex-1 bg-amber-600 hover:bg-amber-700 text-white" onClick={handleBulkUpdate} disabled={saving} data-testid="bulk-update-btn">
            {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <Save className="w-4 h-4 mr-1.5" />}
            Guncelle
          </Button>
          <Button variant="outline" onClick={handleReset} data-testid="bulk-reset-btn">
            <RotateCcw className="w-4 h-4 mr-1" />
            Sifirla
          </Button>
        </div>
      </div>

      {/* CENTER PANEL: Room Types Table */}
      <div className={`${mobileStep === 2 ? 'block' : 'hidden'} min-w-0 flex-1 lg:block`} data-testid="bulk-center-panel">
        <Card className="h-full">
          <CardHeader className="pb-2 pt-4 px-4">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_ratemanager_BulkUpdatePanel.oda_adi')}</CardTitle>
              <button onClick={toggleAllRoomTypes} className="text-xs text-blue-600 hover:underline" data-testid="select-all-rooms">
                {roomTypes.length > 0 && roomTypes.every(rt => isRoomTypeFullySelected(rt.code)) ? 'Tumunu kaldir' : 'Tumunu sec'}
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
                totalSelectedRoomTypes={Object.keys(selections).length}
              />
            )}
          </CardContent>
        </Card>
      </div>

      {/* RIGHT PANEL: Channels */}
      <div className={`${mobileStep === 3 ? 'block' : 'hidden'} w-full flex-shrink-0 lg:block lg:w-[200px]`} data-testid="bulk-right-panel">
        <Card className="h-full">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-semibold text-gray-700">Kanallar</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <ChannelList channels={activeChannels} stale={activeChannelsStale} provider={channelProvider} />
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
            <Badge variant="outline" className="bg-white">{dateFrom} → {dateTo}</Badge>
            {!allDays && <Badge variant="outline" className="bg-white">{selectedDays.size} gun</Badge>}
          </div>
        </CardContent>
      </Card>
    )}

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
            <Button className="flex-[2] bg-amber-600 text-white hover:bg-amber-700" onClick={handleBulkUpdate} disabled={saving || !canContinueFromFields || !canContinueFromRooms} data-testid="rate-mobile-update">
              {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}
              Güncelle
            </Button>
          </>
        )}
      </div>
    </div>
  </div>
  );
};

const gridColTemplate = (enabledFields) =>
  `minmax(220px, 1fr)${enabledFields.has('rate') ? ' 150px' : ''}${enabledFields.has('availability') ? ' 130px' : ''}${enabledFields.has('min_stay') ? ' 150px' : ''}${enabledFields.has('max_stay') ? ' 150px' : ''}${enabledFields.has('stop_sell') ? ' 100px' : ''}${enabledFields.has('cta') ? ' 80px' : ''}${enabledFields.has('ctd') ? ' 80px' : ''}`;

const ApplyAllButton = ({ field, value, applyToAllSelected, totalSelectedRoomTypes }) => {
  const { t } = useTranslation();
  if (totalSelectedRoomTypes < 2 || !value) return null;
  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); applyToAllSelected(field, value); }}
      className="text-amber-500 hover:text-amber-700 p-0.5 transition-colors flex-shrink-0"
      title="Tumune uygula"
      data-testid={`apply-all-${field}`}
    >
      <CopyCheck className="w-3.5 h-3.5" />
    </button>
  );
};

const RoomTypeList = ({
  roomTypeTree, enabledFields, selections, roomValues, updateRoomValue, getDefaultValues, applyToAllSelected,
  expandedRoomTypes, toggleExpanded, isRoomTypeSelected, isRoomTypeFullySelected, isRatePlanSelected,
  toggleRoomType, toggleRatePlan, pricingSettings, occupancyPricingRules, saveOccupancyPricingRule, getPricingLabel, togglePricingType, currencySymbol, currency,
  totalSelectedRoomTypes, channelProvider,
}) => {
  const { t } = useTranslation();
  const [editingRule, setEditingRule] = useState(null);
  return (
  <div className="overflow-x-auto" data-testid="room-type-list">
    {/* Table Header */}
    <div className="grid items-center border-b bg-gray-50 px-4 py-2 text-xs font-medium text-gray-500 gap-3"
      style={{ gridTemplateColumns: 'minmax(220px, 1fr) repeat(auto-fit, minmax(130px, 1fr))' }}>
      <div className="grid items-center gap-3" style={{ gridTemplateColumns: gridColTemplate(enabledFields) }}>
        <span>{t('cm.pages_ratemanager_BulkUpdatePanel.oda_adi_8e806')}</span>
        {enabledFields.has('rate') && <span className="flex items-center gap-1">{currencySymbol} Fiyat</span>}
        {enabledFields.has('availability') && <span className="flex items-center gap-1"><Home className="w-3 h-3" /> Musaitlik</span>}
        {enabledFields.has('min_stay') && <span className="flex items-center gap-1"><Moon className="w-3 h-3" /> Min. konaklama</span>}
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
        const isExpanded = expandedRoomTypes.has(rt.code);
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
                {rt.plans.length > 0 && (
                  <button onClick={() => toggleExpanded(rt.code)} className="text-gray-400 hover:text-gray-600 p-0.5" data-testid={`expand-toggle-${rt.code}`}>
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
                  <Input type="number" min="0" placeholder="Musaitlik" value={rv.availability} onChange={e => updateRoomValue(rt.code, 'availability', e.target.value)} className="h-8 text-sm" data-testid={`avail-input-${rt.code}`} />
                  <ApplyAllButton field="availability" value={rv.availability} applyToAllSelected={applyToAllSelected} totalSelectedRoomTypes={totalSelectedRoomTypes} />
                </div>
              )}
              {enabledFields.has('min_stay') && (
                <div className="flex items-center gap-1">
                  <Moon className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                  <Input type="number" min="1" placeholder="Min. konaklama" value={rv.min_stay} onChange={e => updateRoomValue(rt.code, 'min_stay', e.target.value)} className="h-8 text-sm" data-testid={`min-stay-input-${rt.code}`} />
                  <ApplyAllButton field="min_stay" value={rv.min_stay} applyToAllSelected={applyToAllSelected} totalSelectedRoomTypes={totalSelectedRoomTypes} />
                </div>
              )}
              {enabledFields.has('max_stay') && (
                <div className="flex items-center gap-1">
                  <Moon className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                  <Input type="number" min="1" placeholder="Max. konaklama" value={rv.max_stay} onChange={e => updateRoomValue(rt.code, 'max_stay', e.target.value)} className="h-8 text-sm" data-testid={`max-stay-input-${rt.code}`} />
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

            {(pricingSettings[rt.code] || 'per_person') === 'per_person' && (
              <OccupancyPricingEditor
                roomType={rt}
                open={editingRule === rt.code}
                onToggle={() => setEditingRule(editingRule === rt.code ? null : rt.code)}
                rule={occupancyPricingRules?.[rt.code]}
                onSave={async rule => {
                  await saveOccupancyPricingRule(rt.code, rule);
                  setEditingRule(null);
                }}
                currentBaseRate={rv.rate}
                currencySymbol={currencySymbol}
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
                  <Checkbox checked={isRatePlanSelected(rt.code, rp.code)} onCheckedChange={() => toggleRatePlan(rt.code, rp.code)} />
                  <div className="min-w-0">
                    <div className="text-sm text-gray-700">{rt.name} - {rp.name}</div>
                    <div className={`text-xs italic ${(pricingSettings[rt.code] || 'per_person') === 'per_room' ? 'text-blue-400' : 'text-gray-400'}`}>
                      {getPricingLabel(rt.code)}
                    </div>
                  </div>
                </label>
                {enabledFields.has('rate') && <div className="text-xs text-gray-400 italic">{rv.rate ? `Ana Fiyat: ${rv.rate} ${currency}` : '\u2014'}</div>}
                {enabledFields.has('availability') && <div className="text-xs text-gray-400 italic">{rv.availability ? rv.availability : '\u2014'}</div>}
                {enabledFields.has('min_stay') && <div className="text-xs text-gray-400 italic">{rv.min_stay ? rv.min_stay : '\u2014'}</div>}
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

export const OccupancyPricingEditor = ({ roomType, open, onToggle, rule, onSave, currentBaseRate, currencySymbol, channelProvider }) => {
  const normalizedRule = normalizeOccupancyRule(rule);
  const initial = {
    base_occupancy: normalizedRule.base_occupancy,
    extra_adult_rate: normalizedRule.extra_adult_rate,
    extra_adult_rate_type: normalizedRule.extra_adult_rate_type,
    child_age_bands: normalizedRule.child_age_bands,
    max_occupancy: normalizedRule.max_occupancy ?? '',
    provider_pricing_verified: Boolean(rule?.provider_pricing_verified),
    provider_pricing_note: rule?.provider_pricing_note || '',
  };
  const [draft, setDraft] = useState(initial);
  const [submitting, setSubmitting] = useState(false);
  const update = (field, value) => setDraft(prev => ({
    ...prev,
    [field]: value,
    ...(field !== 'provider_pricing_verified' && field !== 'provider_pricing_note'
      ? { provider_pricing_verified: false }
      : {}),
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
    child_age_bands: [...prev.child_age_bands, { min_age: 0, max_age: 17, pricing_mode: 'fixed', value: 0 }],
  }));
  const applyCommonBands = () => update('child_age_bands', [
    { min_age: 0, max_age: 6, pricing_mode: 'free', value: 0 },
    { min_age: 7, max_age: 11, pricing_mode: 'adult_percentage', value: 50 },
    { min_age: 12, max_age: 17, pricing_mode: 'adult_rate', value: 0 },
  ]);
  const sortedBands = [...draft.child_age_bands].sort((left, right) => left.min_age - right.min_age);
  let expectedAge = 0;
  const bandsValid = sortedBands.length > 0 && sortedBands.every(band => {
    const valid = Number.isInteger(Number(band.min_age))
      && Number.isInteger(Number(band.max_age))
      && Number(band.min_age) === expectedAge
      && Number(band.max_age) >= Number(band.min_age)
      && Number(band.max_age) <= 17
      && ['free', 'fixed', 'adult_percentage', 'adult_rate'].includes(band.pricing_mode)
      && Number(band.value || 0) >= 0
      && (band.pricing_mode !== 'adult_percentage' || Number(band.value || 0) <= 100);
    expectedAge = Number(band.max_age) + 1;
    return valid;
  }) && expectedAge === 18;
  const base = Number(currentBaseRate || 0);
  const exampleGuests = Number(draft.base_occupancy) + 1;
  const exampleNightly = base + (draft.extra_adult_rate_type === 'percentage' ? (base * Number(draft.extra_adult_rate || 0) / 100) : Number(draft.extra_adult_rate || 0));

  return (
    <div className="border-t border-amber-100 bg-amber-50/40 px-4 py-2" data-testid={`occupancy-pricing-${roomType.code}`}>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <span className="text-gray-600">
          {draft.base_occupancy} yetişkin dahil · Ek yetişkin {draft.extra_adult_rate_type === 'percentage' ? `%${draft.extra_adult_rate}` : `${currencySymbol}${Number(draft.extra_adult_rate || 0).toLocaleString('tr-TR')}`}/gece
        </span>
        <button type="button" onClick={onToggle} className="font-medium text-amber-700 hover:underline">
          {open ? 'Kuralı kapat' : 'Kuralı düzenle'}
        </button>
      </div>
      {open && (
        <div className="mt-3 rounded-lg border border-amber-200 bg-white p-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <RuleNumber label="Fiyata dahil yetişkin" value={draft.base_occupancy} min={1} max={20} onChange={v => update('base_occupancy', v)} />
            <div>
              <Label className="text-[11px] text-gray-600">Ek yetişkin / gece</Label>
              <div className="flex mt-1">
                <select
                  value={draft.extra_adult_rate_type}
                  onChange={e => update('extra_adult_rate_type', e.target.value)}
                  className="h-8 rounded-l-md border border-r-0 border-slate-300 bg-white px-2 text-sm focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
                >
                  <option value="fixed">{currencySymbol}</option>
                  <option value="percentage">%</option>
                </select>
                <Input
                  type="number"
                  value={draft.extra_adult_rate}
                  min={0}
                  step="0.01"
                  onChange={e => update('extra_adult_rate', e.target.value)}
                  className="h-8 rounded-l-none text-sm focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
                />
              </div>
            </div>
            <RuleNumber label="Maksimum kişi" value={draft.max_occupancy} min={draft.base_occupancy} max={50} optional onChange={v => update('max_occupancy', v)} />
          </div>
          <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3" data-testid={`child-age-bands-${roomType.code}`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-xs font-semibold text-slate-800">Çocuk yaş kademeleri</div>
                <div className="text-[11px] text-slate-500">0–17 yaş aralığının tamamı, boşluk ve çakışma olmadan tanımlanmalıdır.</div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={applyCommonBands}>
                  0–6 ücretsiz · 7–11 %50 · 12+ yetişkin
                </Button>
                <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={addBand}>
                  <Plus className="mr-1 h-3.5 w-3.5" /> Kademe ekle
                </Button>
              </div>
            </div>
            <div className="mt-3 space-y-2">
              {draft.child_age_bands.map((band, index) => {
                const needsValue = ['fixed', 'adult_percentage'].includes(band.pricing_mode);
                return (
                  <div key={`child-band-${index}`} className="grid items-end gap-2 rounded-md border bg-white p-2 sm:grid-cols-[80px_80px_minmax(180px,1fr)_140px_36px]">
                    <RuleNumber label="Başlangıç yaşı" value={band.min_age} min={0} max={17} onChange={value => updateBand(index, 'min_age', Number(value))} />
                    <RuleNumber label="Bitiş yaşı" value={band.max_age} min={0} max={17} onChange={value => updateBand(index, 'max_age', Number(value))} />
                    <div>
                      <Label className="text-[11px] text-gray-600">Ücret yöntemi</Label>
                      <select
                        className="mt-1 h-8 w-full rounded-md border border-input bg-white px-2 text-sm"
                        value={band.pricing_mode}
                        onChange={event => updateBand(index, 'pricing_mode', event.target.value)}
                      >
                        <option value="free">Ücretsiz</option>
                        <option value="adult_percentage">Yetişkin ek ücretinin yüzdesi</option>
                        <option value="adult_rate">Yetişkin sayılır</option>
                        <option value="fixed">Sabit ücret / gece</option>
                      </select>
                    </div>
                    {needsValue
                      ? <RuleNumber
                          label={band.pricing_mode === 'adult_percentage' ? 'Yüzde' : 'Tutar / gece'}
                          value={band.value}
                          min={0}
                          max={band.pricing_mode === 'adult_percentage' ? 100 : undefined}
                          step="0.01"
                          onChange={value => updateBand(index, 'value', Number(value))}
                        />
                      : <div className="pb-2 text-xs text-slate-500">Otomatik</div>}
                    <Button type="button" size="icon" variant="ghost" className="h-8 w-8 text-red-600" aria-label={`${index + 1}. çocuk yaş kademesini sil`} onClick={() => removeBand(index)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                );
              })}
            </div>
            {!bandsValid && <div className="mt-2 text-xs font-medium text-red-600" role="alert">Yaş kademeleri 0–17 aralığını kesintisiz kapsamalıdır.</div>}
          </div>
          {base > 0 && (
            <div className="mt-3 rounded-md bg-blue-50 px-3 py-2 text-xs text-blue-800" data-testid={`occupancy-preview-${roomType.code}`}>
              Örnek: {draft.base_occupancy} kişi {currencySymbol}{base.toLocaleString('tr-TR')}; {exampleGuests}. yetişkin ile gecelik {currencySymbol}{exampleNightly.toLocaleString('tr-TR')}.
            </div>
          )}
          <p className="mt-2 text-[11px] leading-4 text-gray-500">
            Bu kural Syroce'de oluşturulan manuel/doğrudan rezervasyonların toplamını hesaplar. HotelRunner'a taban fiyat gönderilir; HotelRunner kişi farkı ayarı da aynı olmalıdır.
          </p>
          {channelProvider === 'hotelrunner' && (
            <div className={`mt-3 rounded-lg border p-3 ${draft.provider_pricing_verified ? 'border-emerald-200 bg-emerald-50' : 'border-red-200 bg-red-50'}`}>
              <label className="flex cursor-pointer items-start gap-2 text-xs font-medium text-slate-800">
                <Checkbox
                  checked={draft.provider_pricing_verified}
                  onCheckedChange={value => update('provider_pricing_verified', Boolean(value))}
                  data-testid={`hotelrunner-pricing-attestation-${roomType.code}`}
                />
                <span>
                  HotelRunner panelindeki dahil yetişkin, ek yetişkin ve tüm çocuk yaş kademeleri bu değerlerle eşleşiyor.
                  <span className="mt-1 block font-normal text-slate-600">Bu onay olmadan HotelRunner'a taban fiyat gönderimi güvenlik amacıyla durdurulur.</span>
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
          <div className="mt-3 flex justify-end">
            <Button
              type="button"
              size="sm"
              disabled={submitting || !bandsValid}
              onClick={async () => {
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
                  toast.error(err?.response?.data?.detail || 'Kural kaydedilirken bir hata oluştu');
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
  <div>
    <Label className="text-[11px] text-gray-600">{label}</Label>
    <Input
      type="number"
      value={value}
      placeholder={optional ? 'Opsiyonel' : undefined}
      onChange={event => onChange(event.target.value)}
      className="mt-1 h-8 text-sm"
      {...inputProps}
    />
  </div>
);
