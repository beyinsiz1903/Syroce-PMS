import { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ArrowUpRight, CalendarDays, Grid3X3, Ban } from 'lucide-react';

import { BulkUpdatePanel } from './rate-manager/BulkUpdatePanel';
import { CalendarGridView } from './rate-manager/CalendarGridView';
import { StopSalePanel } from './rate-manager/StopSalePanel';

const API = process.env.REACT_APP_BACKEND_URL;

const RateManager = ({ user, tenant, onLogout }) => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeView, setActiveView] = useState('bulk');

  const [roomTypes, setRoomTypes] = useState([]);
  const [ratePlans, setRatePlans] = useState([]);
  const [grid, setGrid] = useState([]);
  const [pricingSettings, setPricingSettings] = useState({});
  const [currency, setCurrency] = useState('TRY');

  const CURRENCY_SYMBOLS = { TRY: '\u20BA', USD: '$', EUR: '\u20AC', GBP: '\u00A3', RUB: '\u20BD' };
  const currencySymbol = CURRENCY_SYMBOLS[currency] || currency;

  const [selections, setSelections] = useState({});
  const [enabledFields, setEnabledFields] = useState(new Set());
  const [allDays, setAllDays] = useState(true);
  const [selectedDays, setSelectedDays] = useState(new Set([0, 1, 2, 3, 4, 5, 6]));

  const today = new Date().toISOString().slice(0, 10);
  const nextWeek = new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10);
  const [dateFrom, setDateFrom] = useState(today);
  const [dateTo, setDateTo] = useState(nextWeek);

  const [roomValues, setRoomValues] = useState({});
  const [expandedRoomTypes, setExpandedRoomTypes] = useState(new Set());

  const [gridRoomType, setGridRoomType] = useState('all');
  const [gridRatePlan, setGridRatePlan] = useState('all');
  const [startDate, setStartDate] = useState(today);
  const [endDate, setEndDate] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() + 13);
    return d.toISOString().slice(0, 10);
  });

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const fetchGrid = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(
        `${API}/api/channel-manager/rate-manager/grid?start_date=${startDate}&end_date=${endDate}`,
        { headers }
      );
      setGrid(data.grid || []);
      setRoomTypes(data.room_types || []);
      setRatePlans(data.rate_plans || []);
      if (data.pricing_settings) setPricingSettings(data.pricing_settings);
      if (data.currency) setCurrency(data.currency);
    } catch {
      toast.error('Veriler yuklenemedi');
    }
    setLoading(false);
  }, [startDate, endDate]);

  useEffect(() => { fetchGrid(); }, [fetchGrid]);

  const roomTypeTree = useMemo(() => {
    const map = new Map();
    for (const rt of roomTypes) { map.set(rt.code, { ...rt, plans: [] }); }
    for (const rp of ratePlans) { for (const [, rtObj] of map) { rtObj.plans.push(rp); } }
    return Array.from(map.values());
  }, [roomTypes, ratePlans]);

  // Selection helpers
  const getDefaultValues = () => ({ rate: '', availability: '', min_stay: '', max_stay: '', stop_sell: false, cta: false, ctd: false });

  const updateRoomValue = (roomTypeCode, field, value) => {
    setRoomValues(prev => ({ ...prev, [roomTypeCode]: { ...(prev[roomTypeCode] || getDefaultValues()), [field]: value } }));
  };

  const toggleExpanded = (code) => {
    setExpandedRoomTypes(prev => { const next = new Set(prev); if (next.has(code)) next.delete(code); else next.add(code); return next; });
  };

  const toggleRoomType = (code) => {
    setSelections(prev => {
      const next = { ...prev };
      const allPlans = ratePlans.map(rp => rp.code);
      if (next[code] && next[code].size === allPlans.length) { delete next[code]; } else { next[code] = new Set(allPlans); }
      return next;
    });
    setRoomValues(prev => prev[code] ? prev : { ...prev, [code]: getDefaultValues() });
  };

  const toggleAllRoomTypes = () => {
    const allPlans = ratePlans.map(rp => rp.code);
    const allSelected = roomTypes.length > 0 && roomTypes.every(rt => selections[rt.code] && selections[rt.code].size === allPlans.length);
    if (allSelected) { setSelections({}); } else {
      const next = {}; const rv = { ...roomValues };
      roomTypes.forEach(rt => { next[rt.code] = new Set(allPlans); if (!rv[rt.code]) rv[rt.code] = getDefaultValues(); });
      setSelections(next); setRoomValues(rv);
    }
  };

  const toggleRatePlan = (roomTypeCode, ratePlanCode) => {
    setSelections(prev => {
      const next = { ...prev };
      const current = next[roomTypeCode] ? new Set(next[roomTypeCode]) : new Set();
      if (current.has(ratePlanCode)) { current.delete(ratePlanCode); } else { current.add(ratePlanCode); }
      if (current.size === 0) { delete next[roomTypeCode]; } else { next[roomTypeCode] = current; }
      return next;
    });
  };

  const isRoomTypeSelected = (code) => selections[code] && selections[code].size > 0;
  const isRoomTypeFullySelected = (code) => selections[code] && selections[code].size === ratePlans.length;
  const isRatePlanSelected = (roomTypeCode, ratePlanCode) => selections[roomTypeCode] && selections[roomTypeCode].has(ratePlanCode);

  const totalSelectedRoomTypes = Object.keys(selections).length;
  const totalSelectedPlans = Object.values(selections).reduce((sum, s) => sum + s.size, 0);

  const toggleField = (key) => { setEnabledFields(prev => { const next = new Set(prev); if (next.has(key)) next.delete(key); else next.add(key); return next; }); };

  const toggleDay = (day) => {
    setAllDays(false);
    setSelectedDays(prev => { const next = new Set(prev); if (next.has(day)) next.delete(day); else next.add(day); return next; });
  };

  const toggleAllDays = () => {
    if (allDays) { setAllDays(false); setSelectedDays(new Set()); }
    else { setAllDays(true); setSelectedDays(new Set([0, 1, 2, 3, 4, 5, 6])); }
  };

  const getPricingLabel = (roomTypeCode) => {
    const type = pricingSettings[roomTypeCode] || 'per_person';
    return type === 'per_room' ? 'Oda bazli fiyatlandirma' : 'Kisi bazli fiyatlandirma';
  };

  const togglePricingType = async (roomTypeCode, e) => {
    e.preventDefault(); e.stopPropagation();
    const current = pricingSettings[roomTypeCode] || 'per_person';
    const newType = current === 'per_person' ? 'per_room' : 'per_person';
    setPricingSettings(prev => ({ ...prev, [roomTypeCode]: newType }));
    try {
      await axios.put(`${API}/api/channel-manager/rate-manager/pricing-settings`, { settings: [{ room_type_code: roomTypeCode, pricing_type: newType }] }, { headers });
      toast.success(`${newType === 'per_room' ? 'Oda bazli' : 'Kisi bazli'} fiyatlandirma ayarlandi`);
    } catch {
      setPricingSettings(prev => ({ ...prev, [roomTypeCode]: current }));
      toast.error('Fiyatlandirma ayari guncellenemedi');
    }
  };

  const handleReset = () => {
    setSelections({}); setEnabledFields(new Set()); setAllDays(true);
    setSelectedDays(new Set([0, 1, 2, 3, 4, 5, 6])); setRoomValues({});
    setExpandedRoomTypes(new Set()); setDateFrom(today); setDateTo(nextWeek);
  };

  const handleBulkUpdate = async () => {
    if (totalSelectedRoomTypes === 0) { toast.error('Lutfen en az bir oda tipi secin'); return; }
    if (totalSelectedPlans === 0) { toast.error('Lutfen en az bir fiyat plani secin'); return; }
    if (enabledFields.size === 0) { toast.error('Lutfen guncellenecek en az bir alan secin'); return; }
    if (!dateFrom || !dateTo) { toast.error('Lutfen tarih araligi secin'); return; }

    const selectedRoomCodes = Object.keys(selections);
    const hasAnyValue = selectedRoomCodes.some(rtCode => {
      const rv = roomValues[rtCode];
      if (!rv) return false;
      return (enabledFields.has('rate') && rv.rate) || (enabledFields.has('availability') && rv.availability) ||
        (enabledFields.has('min_stay') && rv.min_stay) || (enabledFields.has('max_stay') && rv.max_stay) ||
        (enabledFields.has('stop_sell') && rv.stop_sell) || (enabledFields.has('cta') && rv.cta) || (enabledFields.has('ctd') && rv.ctd);
    });
    if (!hasAnyValue) { toast.error('Lutfen en az bir oda tipi icin deger girin'); return; }

    setSaving(true);
    try {
      const perRoomValues = selectedRoomCodes.map(rtCode => {
        const rv = roomValues[rtCode] || getDefaultValues();
        return {
          room_type_code: rtCode, rate_plan_codes: Array.from(selections[rtCode]),
          rate: enabledFields.has('rate') && rv.rate ? parseFloat(rv.rate) : null,
          availability: enabledFields.has('availability') && rv.availability ? parseInt(rv.availability) : null,
          min_stay: enabledFields.has('min_stay') && rv.min_stay ? parseInt(rv.min_stay) : null,
          max_stay: enabledFields.has('max_stay') && rv.max_stay ? parseInt(rv.max_stay) : null,
          stop_sell: enabledFields.has('stop_sell') ? rv.stop_sell : null,
          cta: enabledFields.has('cta') ? rv.cta : null,
          ctd: enabledFields.has('ctd') ? rv.ctd : null,
        };
      });

      const { data } = await axios.post(`${API}/api/channel-manager/rate-manager/bulk-grid-update`,
        { per_room_values: perRoomValues, start_date: dateFrom, end_date: dateTo, selected_days: allDays ? null : Array.from(selectedDays), update_fields: Array.from(enabledFields) },
        { headers }
      );

      if (data.all_pushed) { toast.success(`${data.saved} kayit guncellendi ve Exely'ye gonderildi`); }
      else {
        toast.success(`${data.saved} kayit guncellendi`);
        const failed = data.push_results?.filter(r => !r.success) || [];
        if (failed.length > 0) { toast.warning(`${failed.length} Exely push hatasi olustu`); }
      }
      fetchGrid();
    } catch (e) { toast.error(e.response?.data?.detail || 'Guncelleme hatasi'); }
    setSaving(false);
  };

  // Grid helpers
  const filteredGrid = grid.filter(row => {
    if (gridRoomType !== 'all' && row.room_type_code !== gridRoomType) return false;
    if (gridRatePlan !== 'all' && row.rate_plan_code !== gridRatePlan) return false;
    return true;
  });

  const shiftDates = (days) => {
    const s = new Date(startDate); const e = new Date(endDate);
    s.setDate(s.getDate() + days); e.setDate(e.getDate() + days);
    setStartDate(s.toISOString().slice(0, 10)); setEndDate(e.toISOString().slice(0, 10));
  };

  const dates = [];
  if (filteredGrid.length > 0 && filteredGrid[0].dates) {
    filteredGrid[0].dates.forEach(d => dates.push(d.date));
  }

  const formatDate = (ds) => {
    const d = new Date(ds + 'T00:00:00');
    const dayNames = ['Paz', 'Pzt', 'Sal', 'Car', 'Per', 'Cum', 'Cmt'];
    return { day: d.getDate(), month: d.toLocaleDateString('tr-TR', { month: 'short' }), weekday: dayNames[d.getDay()], isWeekend: d.getDay() === 0 || d.getDay() === 6 };
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="rate_manager">
      <div className="p-4 md:p-6 space-y-4" data-testid="rate-manager-page">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold" style={{ fontFamily: 'Space Grotesk' }}>
              Toplu Guncellemeler
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Tum oda tiplerini ayni anda goruntuleyin ve tek seferde guncelleyin
            </p>
          </div>
          <Badge className="bg-green-600 text-white" data-testid="exely-push-badge">
            <ArrowUpRight className="w-3 h-3 mr-1" />
            Exely Push Aktif
          </Badge>
        </div>

        <Tabs value={activeView} onValueChange={setActiveView}>
          <TabsList className="grid w-full grid-cols-3 max-w-md">
            <TabsTrigger value="bulk" data-testid="bulk-tab">
              <Grid3X3 className="w-4 h-4 mr-1.5" /> Toplu Guncelle
            </TabsTrigger>
            <TabsTrigger value="grid" data-testid="grid-tab">
              <CalendarDays className="w-4 h-4 mr-1.5" /> Takvim Gorunumu
            </TabsTrigger>
            <TabsTrigger value="stop-sale" data-testid="stop-sale-tab">
              <Ban className="w-4 h-4 mr-1.5" /> Stop Sale
            </TabsTrigger>
          </TabsList>

          <TabsContent value="bulk" className="mt-4">
            <BulkUpdatePanel
              roomTypeTree={roomTypeTree} roomTypes={roomTypes} ratePlans={ratePlans}
              enabledFields={enabledFields} toggleField={toggleField}
              dateFrom={dateFrom} setDateFrom={setDateFrom} dateTo={dateTo} setDateTo={setDateTo}
              allDays={allDays} selectedDays={selectedDays} toggleDay={toggleDay} toggleAllDays={toggleAllDays}
              selections={selections} toggleRoomType={toggleRoomType} toggleAllRoomTypes={toggleAllRoomTypes} toggleRatePlan={toggleRatePlan}
              isRoomTypeSelected={isRoomTypeSelected} isRoomTypeFullySelected={isRoomTypeFullySelected} isRatePlanSelected={isRatePlanSelected}
              roomValues={roomValues} updateRoomValue={updateRoomValue} getDefaultValues={getDefaultValues}
              expandedRoomTypes={expandedRoomTypes} toggleExpanded={toggleExpanded}
              pricingSettings={pricingSettings} getPricingLabel={getPricingLabel} togglePricingType={togglePricingType}
              currencySymbol={currencySymbol} currency={currency}
              totalSelectedRoomTypes={totalSelectedRoomTypes} totalSelectedPlans={totalSelectedPlans}
              saving={saving} handleBulkUpdate={handleBulkUpdate} handleReset={handleReset} loading={loading}
            />
          </TabsContent>

          <TabsContent value="grid" className="mt-4">
            <CalendarGridView
              filteredGrid={filteredGrid} dates={dates} roomTypes={roomTypes} ratePlans={ratePlans}
              gridRoomType={gridRoomType} setGridRoomType={setGridRoomType}
              gridRatePlan={gridRatePlan} setGridRatePlan={setGridRatePlan}
              startDate={startDate} setStartDate={setStartDate} endDate={endDate} setEndDate={setEndDate}
              shiftDates={shiftDates} fetchGrid={fetchGrid} loading={loading} formatDate={formatDate} currency={currency}
            />
          </TabsContent>

          <TabsContent value="stop-sale" className="mt-4">
            <StopSalePanel
              roomTypes={roomTypes}
              ratePlans={ratePlans}
              fetchGrid={fetchGrid}
              loading={loading}
            />
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
};

export default RateManager;
