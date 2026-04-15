import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Save, Loader2, RotateCcw, Home, Moon, ChevronDown, ChevronUp, AlertTriangle, CopyCheck } from 'lucide-react';
import { DAYS, UPDATE_FIELDS } from './constants';
import { ChannelList } from './ChannelList';

export const BulkUpdatePanel = ({
  roomTypeTree, roomTypes, ratePlans, enabledFields, toggleField,
  dateFrom, setDateFrom, dateTo, setDateTo,
  allDays, selectedDays, toggleDay, toggleAllDays,
  selections, toggleRoomType, toggleAllRoomTypes, toggleRatePlan,
  isRoomTypeSelected, isRoomTypeFullySelected, isRatePlanSelected,
  roomValues, updateRoomValue, getDefaultValues, applyToAllSelected,
  expandedRoomTypes, toggleExpanded,
  pricingSettings, getPricingLabel, togglePricingType, currencySymbol, currency,
  totalSelectedRoomTypes, totalSelectedPlans,
  saving, handleBulkUpdate, handleReset, loading,
}) => (
  <div>
    <div className="flex flex-col lg:flex-row gap-4" data-testid="bulk-update-layout">
      {/* LEFT PANEL: Filters */}
      <div className="w-full lg:w-[240px] flex-shrink-0 space-y-4" data-testid="bulk-left-panel">
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
            <CardTitle className="text-sm font-semibold text-gray-700">Tarih Araligi</CardTitle>
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
        <div className="flex gap-2">
          <Button className="flex-1 bg-orange-600 hover:bg-orange-700 text-white" onClick={handleBulkUpdate} disabled={saving} data-testid="bulk-update-btn">
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
      <div className="flex-1 min-w-0" data-testid="bulk-center-panel">
        <Card className="h-full">
          <CardHeader className="pb-2 pt-4 px-4">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold text-gray-700">Oda adi</CardTitle>
              <button onClick={toggleAllRoomTypes} className="text-xs text-blue-600 hover:underline" data-testid="select-all-rooms">
                {roomTypes.length > 0 && roomTypes.every(rt => isRoomTypeFullySelected(rt.code)) ? 'Tumunu kaldir' : 'Tumunu sec'}
              </button>
            </div>
          </CardHeader>
          <CardContent className="px-0 pb-4">
            {loading && roomTypes.length === 0 ? (
              <div className="flex items-center justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
            ) : roomTypes.length === 0 ? (
              <div className="text-center py-12 text-gray-400 text-sm px-4">Exely bağlantısı bulunamadı veya oda tipi tanımlı değil</div>
            ) : (
              <RoomTypeList
                roomTypeTree={roomTypeTree} enabledFields={enabledFields} selections={selections}
                roomValues={roomValues} updateRoomValue={updateRoomValue} getDefaultValues={getDefaultValues} applyToAllSelected={applyToAllSelected}
                expandedRoomTypes={expandedRoomTypes} toggleExpanded={toggleExpanded}
                isRoomTypeSelected={isRoomTypeSelected} isRoomTypeFullySelected={isRoomTypeFullySelected}
                isRatePlanSelected={isRatePlanSelected}
                toggleRoomType={toggleRoomType} toggleRatePlan={toggleRatePlan}
                pricingSettings={pricingSettings} getPricingLabel={getPricingLabel} togglePricingType={togglePricingType}
                currencySymbol={currencySymbol} currency={currency}
                totalSelectedRoomTypes={Object.keys(selections).length}
              />
            )}
          </CardContent>
        </Card>
      </div>

      {/* RIGHT PANEL: Channels */}
      <div className="w-full lg:w-[200px] flex-shrink-0" data-testid="bulk-right-panel">
        <Card className="h-full">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-semibold text-gray-700">Kanallar</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <ChannelList />
          </CardContent>
        </Card>
      </div>
    </div>

    {/* Summary Bar */}
    {(totalSelectedRoomTypes > 0 || enabledFields.size > 0) && (
      <Card className="border-orange-200 bg-orange-50/50 mt-4" data-testid="bulk-summary">
        <CardContent className="py-3 px-4">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="font-medium text-gray-700">Ozet:</span>
            <Badge variant="outline" className="bg-white">{totalSelectedRoomTypes} oda tipi</Badge>
            <Badge variant="outline" className="bg-white">{totalSelectedPlans} plan</Badge>
            <Badge variant="outline" className="bg-white">{enabledFields.size} alan</Badge>
            <Badge variant="outline" className="bg-white">{dateFrom} → {dateTo}</Badge>
            {!allDays && <Badge variant="outline" className="bg-white">{selectedDays.size} gun</Badge>}
          </div>
        </CardContent>
      </Card>
    )}
  </div>
);

const gridColTemplate = (enabledFields) =>
  `minmax(220px, 1fr)${enabledFields.has('rate') ? ' 150px' : ''}${enabledFields.has('availability') ? ' 130px' : ''}${enabledFields.has('min_stay') ? ' 150px' : ''}${enabledFields.has('max_stay') ? ' 150px' : ''}${enabledFields.has('stop_sell') ? ' 100px' : ''}${enabledFields.has('cta') ? ' 80px' : ''}${enabledFields.has('ctd') ? ' 80px' : ''}`;

const ApplyAllButton = ({ field, value, applyToAllSelected, totalSelectedRoomTypes }) => {
  if (totalSelectedRoomTypes < 2 || !value) return null;
  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); applyToAllSelected(field, value); }}
      className="text-orange-500 hover:text-orange-700 p-0.5 transition-colors flex-shrink-0"
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
  toggleRoomType, toggleRatePlan, pricingSettings, getPricingLabel, togglePricingType, currencySymbol, currency,
  totalSelectedRoomTypes,
}) => (
  <div className="overflow-x-auto" data-testid="room-type-list">
    {/* Table Header */}
    <div className="grid items-center border-b bg-gray-50 px-4 py-2 text-xs font-medium text-gray-500 gap-3"
      style={{ gridTemplateColumns: 'minmax(220px, 1fr) repeat(auto-fit, minmax(130px, 1fr))' }}>
      <div className="grid items-center gap-3" style={{ gridTemplateColumns: gridColTemplate(enabledFields) }}>
        <span>Oda adi</span>
        {enabledFields.has('rate') && <span className="flex items-center gap-1">{currencySymbol} Fiyat</span>}
        {enabledFields.has('availability') && <span className="flex items-center gap-1"><Home className="w-3 h-3" /> Musaitlik</span>}
        {enabledFields.has('min_stay') && <span className="flex items-center gap-1"><Moon className="w-3 h-3" /> Min. konaklama</span>}
        {enabledFields.has('max_stay') && <span className="flex items-center gap-1"><Moon className="w-3 h-3" /> Max. konaklama</span>}
        {enabledFields.has('stop_sell') && <span>Satis durdur</span>}
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
            <div className={`grid items-center px-4 py-3 gap-3 transition-colors ${isSelected ? 'bg-orange-50/60' : 'hover:bg-gray-50'}`}
              style={{ gridTemplateColumns: colTemplate }}>
              <div className="flex items-center gap-2">
                <Checkbox checked={isRoomTypeFullySelected(rt.code)} onCheckedChange={() => toggleRoomType(rt.code)} data-testid={`room-type-check-${rt.code}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-sm text-gray-900">{rt.name}</span>
                    {rt.availability_update === false && (
                      <span className="inline-flex items-center gap-0.5 text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded font-medium" title="HotelRunner bu oda tipi için musaitlik guncellemeye izin vermiyor">
                        <AlertTriangle className="w-2.5 h-2.5" /> Musaitlik kapali
                      </span>
                    )}
                    {rt.price_update === false && (
                      <span className="inline-flex items-center gap-0.5 text-[10px] bg-red-100 text-red-700 px-1.5 py-0.5 rounded font-medium" title="HotelRunner bu oda tipi için fiyat guncellemeye izin vermiyor">
                        <AlertTriangle className="w-2.5 h-2.5" /> Fiyat kapali
                      </span>
                    )}
                  </div>
                  <button onClick={(e) => togglePricingType(rt.code, e)}
                    className={`text-xs italic cursor-pointer hover:underline transition-colors ${(pricingSettings[rt.code] || 'per_person') === 'per_room' ? 'text-blue-600' : 'text-orange-600'}`}
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
