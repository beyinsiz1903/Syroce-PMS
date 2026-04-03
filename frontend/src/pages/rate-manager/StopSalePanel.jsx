import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import {
  Ban, CheckCircle, Lock, Unlock, Loader2, AlertTriangle,
  Calendar, RefreshCw, BedDouble, Globe, Clock, Trash2,
  CalendarRange, Palmtree, Star, Snowflake, Sun
} from 'lucide-react';

const API = import.meta.env.VITE_BACKEND_URL;

// Category icons & colors
const CATEGORY_STYLE = {
  turkey: { icon: Star, color: 'text-red-600', bg: 'bg-red-50', border: 'border-red-200', label: 'Turk Tatili' },
  international: { icon: Globe, color: 'text-blue-600', bg: 'bg-blue-50', border: 'border-blue-200', label: 'Uluslararasi' },
  season: { icon: Sun, color: 'text-amber-600', bg: 'bg-amber-50', border: 'border-amber-200', label: 'Sezon' },
};

export const StopSalePanel = ({ roomTypes, ratePlans, fetchGrid, loading: parentLoading, apiPrefix = '/api/channel-manager/rate-manager' }) => {
  const isHotelRunner = apiPrefix.includes('hr-rate-manager');
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const today = new Date().toISOString().slice(0, 10);
  const nextMonth = new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10);

  const [dateFrom, setDateFrom] = useState(today);
  const [dateTo, setDateTo] = useState(nextMonth);
  const [selectedRoomTypes, setSelectedRoomTypes] = useState(new Set());
  const [saving, setSaving] = useState(false);
  const [activeStopSales, setActiveStopSales] = useState([]);
  const [loadingActive, setLoadingActive] = useState(true);

  // Holidays
  const [holidays, setHolidays] = useState([]);
  const [selectedHoliday, setSelectedHoliday] = useState('');
  const [loadingHolidays, setLoadingHolidays] = useState(false);

  // Scheduler
  const [schedules, setSchedules] = useState([]);
  const [loadingSchedules, setLoadingSchedules] = useState(false);
  const [scheduleName, setScheduleName] = useState('');
  const [savingSchedule, setSavingSchedule] = useState(false);

  // Operator-level stop sale
  const [operatorStatus, setOperatorStatus] = useState({});
  const [operatorLoading, setOperatorLoading] = useState({});

  const defaultOperators = [
    { id: 'booking_com', name: 'Booking.com' },
    { id: 'expedia', name: 'Expedia' },
    { id: 'tatilsepeti', name: 'Tatilsepeti' },
    { id: 'hotelbeds', name: 'Hotelbeds' },
    { id: 'agoda', name: 'Agoda' },
  ];

  const loadActiveStopSales = useCallback(async () => {
    setLoadingActive(true);
    try {
      const { data } = await axios.get(
        `${API}${apiPrefix}/stop-sale-summary?start_date=${today}&end_date=${nextMonth}`,
        { headers }
      );
      setActiveStopSales(data.stops || []);
    } catch {
      console.error('Stop sale durumu yuklenemedi');
    }
    setLoadingActive(false);
  }, [today, nextMonth]);

  const loadOperatorStatus = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/api/rates/stop-sale/status`, { headers });
      setOperatorStatus(data.operators || {});
    } catch {
      console.error('Operator stop-sale durumu yuklenemedi');
    }
  }, []);

  const loadHolidays = useCallback(async () => {
    setLoadingHolidays(true);
    try {
      const { data } = await axios.get(`${API}${apiPrefix}/holidays`, { headers });
      setHolidays(data.holidays || []);
    } catch {
      console.error('Tatil verileri yuklenemedi');
    }
    setLoadingHolidays(false);
  }, []);

  const loadSchedules = useCallback(async () => {
    setLoadingSchedules(true);
    try {
      const { data } = await axios.get(`${API}${apiPrefix}/stop-sale-schedules`, { headers });
      setSchedules(data.schedules || []);
    } catch {
      console.error('Zamanlayicilar yuklenemedi');
    }
    setLoadingSchedules(false);
  }, []);

  useEffect(() => {
    loadActiveStopSales();
    loadOperatorStatus();
    loadHolidays();
    loadSchedules();
  }, [loadActiveStopSales, loadOperatorStatus, loadHolidays, loadSchedules]);

  const handleHolidaySelect = (key) => {
    setSelectedHoliday(key);
    if (key === 'manual') {
      return;
    }
    const h = holidays.find(h => h.key === key);
    if (h) {
      setDateFrom(h.start_date);
      setDateTo(h.end_date);
      setScheduleName(h.name);
    }
  };

  const toggleRoomType = (code) => {
    setSelectedRoomTypes(prev => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code); else next.add(code);
      return next;
    });
  };

  const selectAllRoomTypes = () => {
    if (selectedRoomTypes.size === roomTypes.length) {
      setSelectedRoomTypes(new Set());
    } else {
      setSelectedRoomTypes(new Set(roomTypes.map(rt => rt.code)));
    }
  };

  const applyStopSale = async (stopSell) => {
    if (selectedRoomTypes.size === 0) {
      toast.error('Lutfen en az bir oda tipi secin');
      return;
    }
    if (!dateFrom || !dateTo) {
      toast.error('Lutfen tarih araligi secin');
      return;
    }

    setSaving(true);
    try {
      const perRoomValues = Array.from(selectedRoomTypes).map(rtCode => ({
        room_type_code: rtCode,
        rate_plan_codes: ratePlans.map(rp => rp.code),
        stop_sell: stopSell,
      }));

      const { data } = await axios.post(
        `${API}${apiPrefix}/bulk-grid-update`,
        {
          per_room_values: perRoomValues,
          start_date: dateFrom,
          end_date: dateTo,
          selected_days: null,
          update_fields: ['stop_sell'],
        },
        { headers }
      );

      if (stopSell) {
        toast.success(`${data.saved} kayit icin satis durduruldu`);
      } else {
        toast.success(`${data.saved} kayit icin satis acildi`);
      }
      if (data.all_pushed) {
        toast.success(isHotelRunner ? 'HotelRunner push basarili' : 'Exely push basarili');
      } else if (data.background_push) {
        const failed = data.push_results?.filter(r => !r.success) || [];
        const succeeded = data.push_results?.filter(r => r.success) || [];
        if (succeeded.length > 0) {
          toast.success(`${succeeded.length} oda tipi ${isHotelRunner ? 'HotelRunner' : 'Exely'}'a basariyla gonderildi`);
        }
        if (failed.length > 0) {
          failed.forEach(f => {
            const errMsg = f.error?.includes('Rate limit') ? 'Rate limit (cok fazla istek)' : (f.error || 'Bilinmeyen hata');
            toast.error(`${f.room_type_code || 'Oda tipi'}: ${errMsg}`, { duration: 8000 });
          });
        }
      }
      if (data.provider_warning) {
        toast.error(data.provider_warning, { duration: 8000 });
      }

      loadActiveStopSales();
      if (fetchGrid) setTimeout(() => fetchGrid(), 500);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Stop sale isleminde hata olustu');
    }
    setSaving(false);
  };

  const toggleOperatorStopSale = async (operatorId, operatorName) => {
    setOperatorLoading(prev => ({ ...prev, [operatorId]: true }));
    try {
      const currentStatus = operatorStatus[operatorId];
      const newStatus = !currentStatus;

      await axios.post(`${API}/api/rates/stop-sale/toggle`, {
        operator_id: operatorId,
        stop_sale: newStatus,
      }, { headers });

      setOperatorStatus(prev => ({ ...prev, [operatorId]: newStatus }));

      if (newStatus) {
        toast.success(`${operatorName} icin stop-sale aktif edildi`);
      } else {
        toast.success(`${operatorName} icin stop-sale kaldirildi`);
      }
    } catch {
      toast.error('Stop-sale durumu degistirilemedi');
    }
    setOperatorLoading(prev => ({ ...prev, [operatorId]: false }));
  };

  const saveSchedule = async () => {
    if (selectedRoomTypes.size === 0) {
      toast.error('Lutfen en az bir oda tipi secin');
      return;
    }
    if (!dateFrom || !dateTo) {
      toast.error('Lutfen tarih araligi secin');
      return;
    }
    const name = scheduleName.trim() || `Stop Sale ${dateFrom} - ${dateTo}`;

    setSavingSchedule(true);
    try {
      await axios.post(`${API}${apiPrefix}/stop-sale-schedules`, {
        name,
        holiday_key: selectedHoliday !== 'manual' ? selectedHoliday : null,
        start_date: dateFrom,
        end_date: dateTo,
        room_type_codes: Array.from(selectedRoomTypes),
        auto_apply: true,
      }, { headers });
      toast.success('Zamanlayici olusturuldu ve stop sale uygulandi');
      loadSchedules();
      loadActiveStopSales();
      setScheduleName('');
      if (fetchGrid) setTimeout(() => fetchGrid(), 500);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Zamanlayici olusturulamadi');
    }
    setSavingSchedule(false);
  };

  const deleteSchedule = async (scheduleId, removeStopSale) => {
    try {
      await axios.delete(
        `${API}${apiPrefix}/stop-sale-schedules/${scheduleId}?remove_stop_sale=${removeStopSale}`,
        { headers }
      );
      toast.success(removeStopSale ? 'Zamanlayici silindi ve stop sale kaldirildi' : 'Zamanlayici silindi');
      loadSchedules();
      if (removeStopSale) {
        loadActiveStopSales();
        if (fetchGrid) setTimeout(() => fetchGrid(), 500);
      }
    } catch {
      toast.error('Zamanlayici silinemedi');
    }
  };

  // Active stops pre-grouped
  const groupedStops = {};
  for (const s of activeStopSales) {
    groupedStops[s.room_type_code] = { name: s.room_type_name, dates: new Set(s.dates) };
  }

  // Group holidays by category
  const holidaysByCategory = {};
  for (const h of holidays) {
    const cat = h.category || 'other';
    if (!holidaysByCategory[cat]) holidaysByCategory[cat] = [];
    holidaysByCategory[cat].push(h);
  }

  const formatDateRange = (start, end) => {
    const s = new Date(start + 'T00:00:00');
    const e = new Date(end + 'T00:00:00');
    const opts = { day: 'numeric', month: 'short' };
    return `${s.toLocaleDateString('tr-TR', opts)} - ${e.toLocaleDateString('tr-TR', opts)}`;
  };

  return (
    <div className="space-y-6" data-testid="stop-sale-panel">
      {/* Holiday Quick Select + Date Range */}
      <Card className="border-indigo-200 bg-gradient-to-br from-indigo-50/50 to-white">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2" data-testid="holiday-selector-title">
            <Palmtree className="w-4 h-4 text-indigo-600" />
            Tatil Donemi Hizli Secim
          </CardTitle>
          <CardDescription className="text-xs">
            Tatil donemi secin, tarihler otomatik dolsun. Isterseniz tarihleri manuel duzenleyebilirsiniz.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Holiday Grid */}
          {loadingHolidays ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="w-5 h-5 animate-spin text-indigo-400" />
            </div>
          ) : (
            <div className="space-y-3">
              {Object.entries(holidaysByCategory).map(([cat, items]) => {
                const style = CATEGORY_STYLE[cat] || CATEGORY_STYLE.turkey;
                const Icon = style.icon;
                return (
                  <div key={cat}>
                    <div className="flex items-center gap-1.5 mb-1.5">
                      <Icon className={`w-3.5 h-3.5 ${style.color}`} />
                      <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{style.label}</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5" data-testid={`holiday-category-${cat}`}>
                      {items.map(h => {
                        const isSelected = selectedHoliday === h.key;
                        return (
                          <button
                            key={h.key}
                            onClick={() => handleHolidaySelect(h.key)}
                            className={`
                              inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium
                              transition-all duration-200 border cursor-pointer
                              ${isSelected
                                ? `${style.bg} ${style.border} ${style.color} ring-2 ring-offset-1 ring-indigo-300`
                                : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50 hover:border-gray-300'
                              }
                            `}
                            data-testid={`holiday-btn-${h.key}`}
                          >
                            <span>{h.name}</span>
                            <span className="text-[10px] opacity-70">
                              {formatDateRange(h.start_date, h.end_date)}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
              {/* Manual option */}
              <button
                onClick={() => handleHolidaySelect('manual')}
                className={`
                  inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium
                  transition-all duration-200 border cursor-pointer
                  ${selectedHoliday === 'manual'
                    ? 'bg-gray-100 border-gray-400 text-gray-800 ring-2 ring-offset-1 ring-gray-300'
                    : 'bg-white border-gray-200 text-gray-500 hover:bg-gray-50'
                  }
                `}
                data-testid="holiday-btn-manual"
              >
                <CalendarRange className="w-3 h-3" />
                Manuel Tarih Gir
              </button>
            </div>
          )}

          {/* Date Fields (always editable) */}
          <div className="grid grid-cols-2 gap-3 pt-2 border-t border-gray-100">
            <div>
              <Label className="text-xs text-gray-500">Baslangic</Label>
              <Input
                type="date"
                value={dateFrom}
                onChange={e => { setDateFrom(e.target.value); setSelectedHoliday('manual'); }}
                className="mt-1 h-9"
                data-testid="stop-sale-date-from"
              />
            </div>
            <div>
              <Label className="text-xs text-gray-500">Bitis</Label>
              <Input
                type="date"
                value={dateTo}
                onChange={e => { setDateTo(e.target.value); setSelectedHoliday('manual'); }}
                className="mt-1 h-9"
                data-testid="stop-sale-date-to"
              />
            </div>
          </div>

          {selectedHoliday && selectedHoliday !== 'manual' && (
            <div className="flex items-center gap-2 px-3 py-2 bg-indigo-50 border border-indigo-200 rounded-lg text-xs text-indigo-700">
              <Calendar className="w-3.5 h-3.5 flex-shrink-0" />
              <span>
                <strong>{holidays.find(h => h.key === selectedHoliday)?.name}</strong> tarihleri secildi. 
                Tarihleri manuel olarak degistirebilirsiniz.
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Main Controls Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left: Room Type Selection */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <BedDouble className="w-4 h-4" />
              Oda Tipi Sec
            </CardTitle>
            <CardDescription className="text-xs">
              Stop sale uygulanacak oda tiplerini secin
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <button
              onClick={selectAllRoomTypes}
              className="text-xs text-blue-600 hover:underline mb-2"
              data-testid="stop-sale-select-all"
            >
              {selectedRoomTypes.size === roomTypes.length ? 'Tumunu kaldir' : 'Tumunu sec'}
            </button>
            <div className="space-y-1.5 max-h-[280px] overflow-y-auto">
              {roomTypes.map(rt => (
                <label
                  key={rt.code}
                  className="flex items-center gap-2 cursor-pointer text-sm py-1"
                  data-testid={`stop-sale-room-${rt.code}`}
                >
                  <Checkbox
                    checked={selectedRoomTypes.has(rt.code)}
                    onCheckedChange={() => toggleRoomType(rt.code)}
                  />
                  <span className={selectedRoomTypes.has(rt.code) ? 'text-gray-900 font-medium' : 'text-gray-600'}>
                    {rt.name}
                  </span>
                </label>
              ))}
              {roomTypes.length === 0 && (
                <p className="text-xs text-gray-400 py-4 text-center">Oda tipi bulunamadi</p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Center: Actions + Scheduler Save */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Calendar className="w-4 h-4" />
              Islem & Zamanlayici
            </CardTitle>
            <CardDescription className="text-xs">
              Satisi durdur/ac veya zamanlayici olarak kaydet
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Summary */}
            <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-600">
              <span className="font-medium">{selectedRoomTypes.size}</span> oda tipi secili
              {dateFrom && dateTo && (
                <span className="text-gray-400 ml-1">
                  | {formatDateRange(dateFrom, dateTo)}
                </span>
              )}
            </div>

            {/* Action Buttons */}
            <div className="flex gap-3">
              <Button
                className="flex-1 bg-red-600 hover:bg-red-700 text-white"
                onClick={() => applyStopSale(true)}
                disabled={saving || selectedRoomTypes.size === 0}
                data-testid="apply-stop-sale-btn"
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <Lock className="w-4 h-4 mr-1.5" />}
                Satisi Durdur
              </Button>
              <Button
                className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white"
                onClick={() => applyStopSale(false)}
                disabled={saving || selectedRoomTypes.size === 0}
                data-testid="remove-stop-sale-btn"
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <Unlock className="w-4 h-4 mr-1.5" />}
                Satisi Ac
              </Button>
            </div>

            {/* Scheduler Save */}
            <div className="border-t border-gray-100 pt-3 space-y-2">
              <div className="flex items-center gap-2">
                <Clock className="w-3.5 h-3.5 text-indigo-500" />
                <span className="text-xs font-semibold text-gray-700">Zamanlayici Olarak Kaydet</span>
              </div>
              <Input
                placeholder="Zamanlayici adi (opsiyonel)"
                value={scheduleName}
                onChange={e => setScheduleName(e.target.value)}
                className="h-8 text-sm"
                data-testid="schedule-name-input"
              />
              <Button
                className="w-full bg-indigo-600 hover:bg-indigo-700 text-white"
                size="sm"
                onClick={saveSchedule}
                disabled={savingSchedule || selectedRoomTypes.size === 0}
                data-testid="save-schedule-btn"
              >
                {savingSchedule ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <Clock className="w-3.5 h-3.5 mr-1.5" />}
                Zamanlayici Olustur & Uygula
              </Button>
            </div>

            {/* Warning */}
            <div className="flex items-start gap-2 p-2.5 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-700">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>{isHotelRunner
                ? 'Stop sale islemleri HotelRunner uzerinden tum kanallara anlik yansitilir.'
                : 'Stop sale islemleri Exely uzerinden tum kanallara anlik yansitilir.'
              }</span>
            </div>
          </CardContent>
        </Card>

        {/* Right: Operator-Level Stop Sales */}
        <Card className="border-orange-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Globe className="w-4 h-4 text-orange-600" />
              Kanal Bazli Stop Sale
            </CardTitle>
            <CardDescription className="text-xs">
              Belirli kanallar icin satisi tek tikla durdurun
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {defaultOperators.map(op => (
              <div
                key={op.id}
                className={`flex items-center justify-between p-2.5 rounded-lg border transition-colors ${
                  operatorStatus[op.id] ? 'bg-red-50 border-red-200' : 'bg-white border-gray-200 hover:bg-gray-50'
                }`}
                data-testid={`operator-stop-${op.id}`}
              >
                <div className="flex items-center gap-2">
                  {operatorStatus[op.id] ? (
                    <Ban className="w-4 h-4 text-red-500" />
                  ) : (
                    <CheckCircle className="w-4 h-4 text-emerald-500" />
                  )}
                  <span className="text-sm font-medium text-gray-800">{op.name}</span>
                </div>
                <Button
                  size="sm"
                  variant={operatorStatus[op.id] ? 'default' : 'destructive'}
                  className={operatorStatus[op.id] ? 'bg-emerald-600 hover:bg-emerald-700 h-7 text-xs' : 'h-7 text-xs'}
                  onClick={() => toggleOperatorStopSale(op.id, op.name)}
                  disabled={operatorLoading[op.id]}
                  data-testid={`operator-toggle-${op.id}`}
                >
                  {operatorLoading[op.id] ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : operatorStatus[op.id] ? (
                    'Satisi Ac'
                  ) : (
                    'Durdur'
                  )}
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Saved Schedules */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Clock className="w-4 h-4 text-indigo-500" />
                Kayitli Zamanlayicilar
              </CardTitle>
              <CardDescription className="text-xs">
                Olusturulmus stop sale zamanlayicilari
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={loadSchedules}
              disabled={loadingSchedules}
              data-testid="refresh-schedules"
            >
              <RefreshCw className={`w-4 h-4 mr-1.5 ${loadingSchedules ? 'animate-spin' : ''}`} />
              Yenile
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loadingSchedules ? (
            <div className="flex items-center justify-center py-6">
              <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
            </div>
          ) : schedules.length === 0 ? (
            <div className="text-center py-6 text-gray-400">
              <Clock className="w-8 h-8 mx-auto mb-2 text-gray-300" />
              <p className="text-sm">Henuz zamanlayici yok</p>
              <p className="text-xs mt-1">Tatil donemi secip zamanlayici olusturun</p>
            </div>
          ) : (
            <div className="space-y-2" data-testid="schedules-list">
              {schedules.map(s => {
                const isPast = s.end_date < today;
                return (
                  <div
                    key={s.id}
                    className={`flex items-center justify-between p-3 rounded-lg border transition-colors ${
                      isPast ? 'bg-gray-50 border-gray-200 opacity-60' : 'bg-indigo-50/50 border-indigo-200'
                    }`}
                    data-testid={`schedule-item-${s.id}`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-gray-800 truncate">{s.name}</span>
                        {s.applied && (
                          <Badge className="bg-green-100 text-green-700 border-0 text-[10px]">Uygulandi</Badge>
                        )}
                        {isPast && (
                          <Badge variant="outline" className="text-[10px]">Gecmis</Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
                        <span className="flex items-center gap-1">
                          <Calendar className="w-3 h-3" />
                          {formatDateRange(s.start_date, s.end_date)}
                        </span>
                        <span className="flex items-center gap-1">
                          <BedDouble className="w-3 h-3" />
                          {s.room_type_codes?.length || 0} oda tipi
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 ml-3">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2 text-red-500 hover:text-red-700 hover:bg-red-50"
                        onClick={() => deleteSchedule(s.id, true)}
                        title="Sil ve stop sale'i kaldir"
                        data-testid={`schedule-delete-restore-${s.id}`}
                      >
                        <Unlock className="w-3.5 h-3.5 mr-1" />
                        <span className="text-xs">Kaldir</span>
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2 text-gray-400 hover:text-gray-600"
                        onClick={() => deleteSchedule(s.id, false)}
                        title="Sadece zamanlayiciyi sil"
                        data-testid={`schedule-delete-${s.id}`}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Active Stop Sales Overview */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Ban className="w-4 h-4 text-red-500" />
                Aktif Stop Sale Durumu
              </CardTitle>
              <CardDescription className="text-xs">
                Oda bazinda aktif stop sale kayitlari
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={loadActiveStopSales}
              disabled={loadingActive}
              data-testid="refresh-stop-sales"
            >
              <RefreshCw className={`w-4 h-4 mr-1.5 ${loadingActive ? 'animate-spin' : ''}`} />
              Yenile
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loadingActive ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
            </div>
          ) : Object.keys(groupedStops).length === 0 ? (
            <div className="text-center py-8 text-gray-400">
              <CheckCircle className="w-10 h-10 mx-auto mb-2 text-emerald-300" />
              <p className="text-sm font-medium">Aktif stop sale yok</p>
              <p className="text-xs mt-1">Tum odalar satis icin acik</p>
            </div>
          ) : (
            <div className="space-y-3" data-testid="active-stop-sales-list">
              {Object.entries(groupedStops).map(([code, info]) => {
                const dateList = Array.from(info.dates).sort();
                return (
                  <div key={code} className="flex items-start gap-3 p-3 bg-red-50 border border-red-100 rounded-lg">
                    <Lock className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-sm text-gray-800">{info.name}</div>
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {dateList.slice(0, 14).map(d => (
                          <Badge key={d} variant="outline" className="text-[10px] bg-white border-red-200 text-red-600">
                            {new Date(d + 'T00:00:00').toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' })}
                          </Badge>
                        ))}
                        {dateList.length > 14 && (
                          <Badge variant="outline" className="text-[10px] bg-white border-gray-200">
                            +{dateList.length - 14} gun daha
                          </Badge>
                        )}
                      </div>
                    </div>
                    <Badge className="bg-red-100 text-red-700 border-0 text-xs">
                      {dateList.length} gun
                    </Badge>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};
