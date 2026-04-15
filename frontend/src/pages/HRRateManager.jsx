import { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Grid3X3, CalendarDays, Ban, Eye, CheckCircle2, AlertTriangle, RefreshCw, Clock, Loader2, Timer, Trash2, X } from 'lucide-react';

import { BulkUpdatePanel } from './rate-manager/BulkUpdatePanel';
import { CalendarGridView } from './rate-manager/CalendarGridView';
import { StopSalePanel } from './rate-manager/StopSalePanel';
import { ProviderToggle } from './rate-manager/ProviderToggle';

const API = "";
const HR_API_PREFIX = '/api/channel-manager/hr-rate-manager';

const HRRateManager = ({ user, tenant, onLogout }) => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeView, setActiveView] = useState('bulk');

  const [roomTypes, setRoomTypes] = useState([]);
  const [ratePlans, setRatePlans] = useState([]);
  const [grid, setGrid] = useState([]);
  const [pricingSettings, setPricingSettings] = useState({});
  const [currency, setCurrency] = useState('TRY');
  const [queueStatus, setQueueStatus] = useState(null);
  const [cancellingQueue, setCancellingQueue] = useState(false);

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
  const [pushProviders, setPushProviders] = useState([]);

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
        `${API}${HR_API_PREFIX}/grid?start_date=${startDate}&end_date=${endDate}`,
        { headers }
      );
      setGrid(data.grid || []);
      setRoomTypes(data.room_types || []);
      setRatePlans(data.rate_plans || []);
      if (data.pricing_settings) setPricingSettings(data.pricing_settings);
      if (data.currency) setCurrency(data.currency);
    } catch {
      toast.error('HotelRunner verileri yüklenemedi');
    }
    setLoading(false);
  }, [startDate, endDate]);

  useEffect(() => { fetchGrid(); }, [fetchGrid]);

  useEffect(() => {
    axios.get(`${API}${HR_API_PREFIX}/push-providers`, { headers })
      .then(res => setPushProviders(res.data?.providers || []))
      .catch(() => {});
  }, []);

  const fetchQueueStatus = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}${HR_API_PREFIX}/queue-status`, { headers });
      setQueueStatus(data);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { fetchQueueStatus(); }, [fetchQueueStatus]);

  // Auto-poll queue status when batch push is active or items exist
  useEffect(() => {
    if (!queueStatus?.total_in_queue) return;
    const interval = setInterval(() => { fetchQueueStatus(); }, 10000);
    return () => clearInterval(interval);
  }, [queueStatus?.total_in_queue, fetchQueueStatus]);

  const handleCancelAllQueue = async () => {
    if (!confirm('Kuyruktaki tum bekleyen push işlemleri iptal edilsin mi?')) return;
    setCancellingQueue(true);
    try {
      const { data } = await axios.delete(`${API}${HR_API_PREFIX}/queue-cancel-all`, { headers });
      toast.success(`${data.deleted} bekleyen push iptal edildi`);
      fetchQueueStatus();
    } catch {
      toast.error('Kuyruk iptal edilemedi');
    }
    setCancellingQueue(false);
  };

  const roomTypeTree = useMemo(() => {
    const map = new Map();
    for (const rt of roomTypes) { map.set(rt.code, { ...rt, plans: [] }); }
    for (const rp of ratePlans) { for (const [, rtObj] of map) { rtObj.plans.push(rp); } }
    return Array.from(map.values());
  }, [roomTypes, ratePlans]);

  const getDefaultValues = () => ({ rate: '', availability: '', min_stay: '', max_stay: '', stop_sell: false, cta: false, ctd: false });

  const updateRoomValue = (roomTypeCode, field, value) => {
    setRoomValues(prev => ({ ...prev, [roomTypeCode]: { ...(prev[roomTypeCode] || getDefaultValues()), [field]: value } }));
  };

  const applyToAllSelected = (field, value) => {
    setRoomValues(prev => {
      const next = { ...prev };
      Object.keys(selections).forEach(rtCode => {
        next[rtCode] = { ...(next[rtCode] || getDefaultValues()), [field]: value };
      });
      return next;
    });
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
      await axios.put(`${API}${HR_API_PREFIX}/pricing-settings`, { settings: [{ room_type_code: roomTypeCode, pricing_type: newType }] }, { headers });
      toast.success(`${newType === 'per_room' ? 'Oda bazli' : 'Kisi bazli'} fiyatlandirma ayarlandi`);
    } catch {
      setPricingSettings(prev => ({ ...prev, [roomTypeCode]: current }));
      toast.error('Fiyatlandırma ayarı güncellenemedi');
    }
  };

  const handleReset = () => {
    setSelections({}); setEnabledFields(new Set()); setAllDays(true);
    setSelectedDays(new Set([0, 1, 2, 3, 4, 5, 6])); setRoomValues({});
    setExpandedRoomTypes(new Set()); setDateFrom(today); setDateTo(nextWeek);
  };

  const handleBulkUpdate = async () => {
    if (totalSelectedRoomTypes === 0) { toast.error('Lutfen en az bir oda tipi seçin'); return; }
    if (totalSelectedPlans === 0) { toast.error('Lutfen en az bir fiyat plani seçin'); return; }
    if (enabledFields.size === 0) { toast.error('Lütfen güncellenecek en az bir alan seçin'); return; }
    if (!dateFrom || !dateTo) { toast.error('Lutfen tarih araligi seçin'); return; }

    const selectedRoomCodes = Object.keys(selections);
    const hasAnyValue = selectedRoomCodes.some(rtCode => {
      const rv = roomValues[rtCode];
      if (!rv) return false;
      return (enabledFields.has('rate') && rv.rate) || (enabledFields.has('availability') && rv.availability) ||
        (enabledFields.has('min_stay') && rv.min_stay) || (enabledFields.has('max_stay') && rv.max_stay) ||
        (enabledFields.has('stop_sell') && rv.stop_sell) || (enabledFields.has('cta') && rv.cta) || (enabledFields.has('ctd') && rv.ctd);
    });
    if (!hasAnyValue) { toast.error('Lutfen en az bir oda tipi için deger girin'); return; }

    // Check permission warnings before push
    if (enabledFields.has('availability')) {
      const noAvailPerms = selectedRoomCodes.filter(code => {
        const rt = roomTypes.find(r => r.code === code);
        return rt && rt.availability_update === false;
      });
      if (noAvailPerms.length > 0) {
        const names = noAvailPerms.map(code => roomTypes.find(r => r.code === code)?.name || code).join(', ');
        toast.warning(`Dikkat: ${names} için HotelRunner musaitlik guncelleme izni yok. Fiyat gidecek ama musaitlik HotelRunner tarafindan reddedilecek.`, { duration: 8000 });
      }
    }

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

      const { data } = await axios.post(`${API}${HR_API_PREFIX}/bulk-grid-update`,
        { per_room_values: perRoomValues, start_date: dateFrom, end_date: dateTo, selected_days: allDays ? null : Array.from(selectedDays), update_fields: Array.from(enabledFields) },
        { headers }
      );

      toast.success(`${data.saved} kayıt güncellendi`);
      if (data.background_push) {
        toast.success(`${data.total_room_types} oda tipi HotelRunner'a arka planda gonderiliyor`);
      }
      if (data.provider_warning) {
        toast.error(data.provider_warning, { duration: 8000 });
      }
      if (data.permission_warnings && data.permission_warnings.length > 0) {
        data.permission_warnings.forEach(w => toast.warning(w, { duration: 10000 }));
      }
      fetchGrid();
    } catch (e) { toast.error(e.response?.data?.detail || 'Guncelleme hatasi'); }
    setSaving(false);
  };

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
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="hr_rate_manager">
      <div className="p-4 md:p-6 space-y-4" data-testid="hr-rate-manager-page">
        <ProviderToggle active="hotelrunner" />
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold" style={{ fontFamily: 'Space Grotesk' }}>
              HotelRunner - Fiyat ve Musaitlik
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              HotelRunner oda tiplerini goruntuleyin ve tek seferde guncelleyin
            </p>
          </div>
          <div className="flex items-center gap-2" data-testid="hr-push-provider-badges">
            {pushProviders.length > 0 ? pushProviders.map(p => {
              const modeConfig = {
                live: { className: 'bg-green-600 text-white', icon: <CheckCircle2 className="w-3 h-3 mr-1" />, label: 'Push Aktif' },
                shadow: { className: 'bg-amber-500 text-white', icon: <Eye className="w-3 h-3 mr-1" />, label: 'Shadow Mode' },
                inactive: { className: 'bg-gray-400 text-white', icon: null, label: 'Inaktif' },
                read_only: { className: 'bg-blue-500 text-white', icon: <Eye className="w-3 h-3 mr-1" />, label: 'Salt Okunur' },
              };
              const cfg = modeConfig[p.mode] || modeConfig.inactive;
              return (
                <Badge key={p.slug} className={cfg.className} data-testid={`hr-push-badge-${p.slug}`}>
                  {cfg.icon}
                  {p.name}: {cfg.label}
                </Badge>
              );
            }) : (
              <Badge className="bg-amber-500 text-white" data-testid="hr-push-badge-default">
                <Eye className="w-3 h-3 mr-1" />
                HotelRunner: Shadow Mode
              </Badge>
            )}
          </div>
        </div>

        {/* Push Queue Status Banner */}
        {queueStatus && queueStatus.total_in_queue > 0 && (
          <div className="flex items-center justify-between rounded-lg px-4 py-3 bg-amber-50 border border-amber-200" data-testid="hr-queue-banner">
            <div className="flex items-center gap-3">
              {queueStatus.batch_push_active ? (
                <Loader2 className="w-5 h-5 text-amber-600 flex-shrink-0 animate-spin" />
              ) : (
                <Clock className="w-5 h-5 text-amber-600 flex-shrink-0" />
              )}
              <div>
                <p className="text-sm font-medium text-amber-800">
                  {queueStatus.total_in_queue} push kuyrukta
                  {queueStatus.batch_push_active && ' — otomatik gonderiliyor'}
                </p>
                <p className="text-xs text-amber-600">
                  {queueStatus.batch_push_active
                    ? 'Arka planda sirayla isleniyor'
                    : 'Arka plan worker tarafindan otomatik islenecek'
                  }
                  {queueStatus.completed > 0 && ` | ${queueStatus.completed} tamamlandi`}
                  {queueStatus.failed > 0 && ` | ${queueStatus.failed} başarısız`}
                </p>
              </div>
            </div>
            <button
              onClick={handleCancelAllQueue}
              disabled={cancellingQueue}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-colors text-red-700 bg-red-100 hover:bg-red-200 disabled:opacity-50 disabled:cursor-not-allowed"
              data-testid="hr-queue-cancel-all-btn"
            >
              {cancellingQueue ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
              {cancellingQueue ? 'İptal ediliyor...' : 'Tumunu İptal Et'}
            </button>
          </div>
        )}

        <Tabs value={activeView} onValueChange={setActiveView}>
          <TabsList className="grid w-full grid-cols-3 max-w-md">
            <TabsTrigger value="bulk" data-testid="hr-bulk-tab">
              <Grid3X3 className="w-4 h-4 mr-1.5" /> Toplu Guncelle
            </TabsTrigger>
            <TabsTrigger value="grid" data-testid="hr-grid-tab">
              <CalendarDays className="w-4 h-4 mr-1.5" /> Takvim Gorunumu
            </TabsTrigger>
            <TabsTrigger value="stop-sale" data-testid="hr-stop-sale-tab">
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
              roomValues={roomValues} updateRoomValue={updateRoomValue} getDefaultValues={getDefaultValues} applyToAllSelected={applyToAllSelected}
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
              apiPrefix={HR_API_PREFIX}
            />
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
};

export default HRRateManager;
