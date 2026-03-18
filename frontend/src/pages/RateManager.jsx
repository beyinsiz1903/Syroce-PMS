import { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  DollarSign, Calendar, Save, Loader2, ChevronLeft, ChevronRight,
  BedDouble, Lock, Unlock, ArrowUpRight, RefreshCw, Eye, RotateCcw,
  CalendarDays, Grid3X3, Settings2
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

/* ─── Day names (Turkish) ─── */
const DAYS = [
  { value: 0, label: 'Pazar' },
  { value: 1, label: 'Pazartesi' },
  { value: 2, label: 'Salı' },
  { value: 3, label: 'Çarşamba' },
  { value: 4, label: 'Perşembe' },
  { value: 5, label: 'Cuma' },
  { value: 6, label: 'Cumartesi' },
];

/* ─── Update field options ─── */
const UPDATE_FIELDS = [
  { key: 'availability', label: 'Müsaitlik' },
  { key: 'rate', label: 'Fiyat' },
  { key: 'min_stay', label: 'Minimum konaklama' },
  { key: 'max_stay', label: 'Maksimum konaklama' },
  { key: 'cta', label: 'CTA (Varışa Kapalı)' },
  { key: 'ctd', label: 'CTD (Çıkışa Kapalı)' },
  { key: 'stop_sell', label: 'Satışı durdur' },
];

const RateManager = ({ user, tenant, onLogout }) => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeView, setActiveView] = useState('bulk');

  // Data from API
  const [roomTypes, setRoomTypes] = useState([]);
  const [ratePlans, setRatePlans] = useState([]);
  const [grid, setGrid] = useState([]);
  const [pricingSettings, setPricingSettings] = useState({});

  // ─── BULK UPDATE STATE ───
  const [selectedRoomTypes, setSelectedRoomTypes] = useState(new Set());
  const [selectedRatePlans, setSelectedRatePlans] = useState(new Set());
  const [enabledFields, setEnabledFields] = useState(new Set());
  const [allDays, setAllDays] = useState(true);
  const [selectedDays, setSelectedDays] = useState(new Set([0, 1, 2, 3, 4, 5, 6]));

  // Date range
  const today = new Date().toISOString().slice(0, 10);
  const nextWeek = new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10);
  const [dateFrom, setDateFrom] = useState(today);
  const [dateTo, setDateTo] = useState(nextWeek);

  // Values to apply
  const [bulkRate, setBulkRate] = useState('');
  const [bulkAvailability, setBulkAvailability] = useState('');
  const [bulkMinStay, setBulkMinStay] = useState('');
  const [bulkMaxStay, setBulkMaxStay] = useState('');
  const [bulkStopSell, setBulkStopSell] = useState(false);
  const [bulkCTA, setBulkCTA] = useState(false);
  const [bulkCTD, setBulkCTD] = useState(false);

  // Grid view state
  const [gridRoomType, setGridRoomType] = useState('all');
  const [gridRatePlan, setGridRatePlan] = useState('all');
  const [startDate, setStartDate] = useState(today);
  const [endDate, setEndDate] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() + 13);
    return d.toISOString().slice(0, 10);
  });

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  // ─── FETCH DATA ───
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
    } catch {
      toast.error('Veriler yüklenemedi');
    }
    setLoading(false);
  }, [startDate, endDate]);

  useEffect(() => { fetchGrid(); }, [fetchGrid]);

  // ─── ROOM TYPE TREE: group rate plans under room types ───
  const roomTypeTree = useMemo(() => {
    const map = new Map();
    for (const rt of roomTypes) {
      map.set(rt.code, { ...rt, plans: [] });
    }
    for (const rp of ratePlans) {
      // Each rate plan applies to all room types
      for (const [, rtObj] of map) {
        rtObj.plans.push(rp);
      }
    }
    return Array.from(map.values());
  }, [roomTypes, ratePlans]);

  // ─── SELECTION HELPERS ───
  const toggleRoomType = (code) => {
    setSelectedRoomTypes(prev => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code); else next.add(code);
      return next;
    });
  };

  const toggleAllRoomTypes = () => {
    if (selectedRoomTypes.size === roomTypes.length) {
      setSelectedRoomTypes(new Set());
    } else {
      setSelectedRoomTypes(new Set(roomTypes.map(rt => rt.code)));
    }
  };

  const toggleRatePlan = (code) => {
    setSelectedRatePlans(prev => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code); else next.add(code);
      return next;
    });
  };

  const toggleAllRatePlans = () => {
    if (selectedRatePlans.size === ratePlans.length) {
      setSelectedRatePlans(new Set());
    } else {
      setSelectedRatePlans(new Set(ratePlans.map(rp => rp.code)));
    }
  };

  const toggleField = (key) => {
    setEnabledFields(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  const toggleDay = (day) => {
    setAllDays(false);
    setSelectedDays(prev => {
      const next = new Set(prev);
      if (next.has(day)) next.delete(day); else next.add(day);
      return next;
    });
  };

  const toggleAllDays = () => {
    if (allDays) {
      setAllDays(false);
      setSelectedDays(new Set());
    } else {
      setAllDays(true);
      setSelectedDays(new Set([0, 1, 2, 3, 4, 5, 6]));
    }
  };

  // ─── PRICING TYPE TOGGLE ───
  const getPricingLabel = (roomTypeCode) => {
    const type = pricingSettings[roomTypeCode] || 'per_person';
    return type === 'per_room' ? 'Oda bazlı fiyatlandırma' : 'Kişi bazlı fiyatlandırma';
  };

  const togglePricingType = async (roomTypeCode, e) => {
    e.preventDefault();
    e.stopPropagation();
    const current = pricingSettings[roomTypeCode] || 'per_person';
    const newType = current === 'per_person' ? 'per_room' : 'per_person';
    
    // Optimistic update
    setPricingSettings(prev => ({ ...prev, [roomTypeCode]: newType }));
    
    try {
      await axios.put(
        `${API}/api/channel-manager/rate-manager/pricing-settings`,
        { settings: [{ room_type_code: roomTypeCode, pricing_type: newType }] },
        { headers }
      );
      toast.success(`${newType === 'per_room' ? 'Oda bazlı' : 'Kişi bazlı'} fiyatlandırma ayarlandı`);
    } catch {
      // Revert on error
      setPricingSettings(prev => ({ ...prev, [roomTypeCode]: current }));
      toast.error('Fiyatlandırma ayarı güncellenemedi');
    }
  };

  // ─── RESET ───
  const handleReset = () => {
    setSelectedRoomTypes(new Set());
    setSelectedRatePlans(new Set());
    setEnabledFields(new Set());
    setAllDays(true);
    setSelectedDays(new Set([0, 1, 2, 3, 4, 5, 6]));
    setBulkRate('');
    setBulkAvailability('');
    setBulkMinStay('');
    setBulkMaxStay('');
    setBulkStopSell(false);
    setBulkCTA(false);
    setBulkCTD(false);
    setDateFrom(today);
    setDateTo(nextWeek);
  };

  // ─── BULK UPDATE ───
  const handleBulkUpdate = async () => {
    if (selectedRoomTypes.size === 0) {
      toast.error('Lütfen en az bir oda tipi seçin');
      return;
    }
    if (selectedRatePlans.size === 0) {
      toast.error('Lütfen en az bir fiyat planı seçin');
      return;
    }
    if (enabledFields.size === 0) {
      toast.error('Lütfen güncellenecek en az bir alan seçin');
      return;
    }
    if (!dateFrom || !dateTo) {
      toast.error('Lütfen tarih aralığı seçin');
      return;
    }

    setSaving(true);
    try {
      const payload = {
        room_type_codes: Array.from(selectedRoomTypes),
        rate_plan_codes: Array.from(selectedRatePlans),
        start_date: dateFrom,
        end_date: dateTo,
        selected_days: allDays ? null : Array.from(selectedDays),
        update_fields: Array.from(enabledFields),
        rate: enabledFields.has('rate') && bulkRate ? parseFloat(bulkRate) : null,
        availability: enabledFields.has('availability') && bulkAvailability ? parseInt(bulkAvailability) : null,
        min_stay: enabledFields.has('min_stay') && bulkMinStay ? parseInt(bulkMinStay) : null,
        max_stay: enabledFields.has('max_stay') && bulkMaxStay ? parseInt(bulkMaxStay) : null,
        stop_sell: enabledFields.has('stop_sell') ? bulkStopSell : null,
        cta: enabledFields.has('cta') ? bulkCTA : null,
        ctd: enabledFields.has('ctd') ? bulkCTD : null,
      };

      const { data } = await axios.post(
        `${API}/api/channel-manager/rate-manager/bulk-grid-update`,
        payload,
        { headers }
      );

      if (data.all_pushed) {
        toast.success(`${data.saved} kayıt güncellendi ve Exely'ye gönderildi`);
      } else {
        toast.success(`${data.saved} kayıt güncellendi`);
        const failed = data.push_results?.filter(r => !r.success) || [];
        if (failed.length > 0) {
          toast.warning(`${failed.length} Exely push hatası oluştu`);
        }
      }
      fetchGrid();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Güncelleme hatası');
    }
    setSaving(false);
  };

  // ─── GRID HELPERS ───
  const filteredGrid = grid.filter(row => {
    if (gridRoomType !== 'all' && row.room_type_code !== gridRoomType) return false;
    if (gridRatePlan !== 'all' && row.rate_plan_code !== gridRatePlan) return false;
    return true;
  });

  const shiftDates = (days) => {
    const s = new Date(startDate);
    const e = new Date(endDate);
    s.setDate(s.getDate() + days);
    e.setDate(e.getDate() + days);
    setStartDate(s.toISOString().slice(0, 10));
    setEndDate(e.toISOString().slice(0, 10));
  };

  const dates = [];
  if (filteredGrid.length > 0 && filteredGrid[0].dates) {
    filteredGrid[0].dates.forEach(d => dates.push(d.date));
  }

  const formatDate = (ds) => {
    const d = new Date(ds + 'T00:00:00');
    const dayNames = ['Paz', 'Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt'];
    return {
      day: d.getDate(),
      month: d.toLocaleDateString('tr-TR', { month: 'short' }),
      weekday: dayNames[d.getDay()],
      isWeekend: d.getDay() === 0 || d.getDay() === 6,
    };
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="rate_manager">
      <div className="p-4 md:p-6 space-y-4" data-testid="rate-manager-page">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold" style={{ fontFamily: 'Space Grotesk' }}>
              Toplu Güncellemeler
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Tüm oda tiplerini aynı anda görüntüleyin ve tek seferde güncelleyin
            </p>
          </div>
          <Badge className="bg-green-600 text-white" data-testid="exely-push-badge">
            <ArrowUpRight className="w-3 h-3 mr-1" />
            Exely Push Aktif
          </Badge>
        </div>

        {/* View Tabs */}
        <Tabs value={activeView} onValueChange={setActiveView}>
          <TabsList className="grid w-full grid-cols-2 max-w-xs">
            <TabsTrigger value="bulk" data-testid="bulk-tab">
              <Grid3X3 className="w-4 h-4 mr-1.5" />
              Toplu Güncelle
            </TabsTrigger>
            <TabsTrigger value="grid" data-testid="grid-tab">
              <CalendarDays className="w-4 h-4 mr-1.5" />
              Takvim Görünümü
            </TabsTrigger>
          </TabsList>

          {/* ═══════════════ BULK UPDATE VIEW ═══════════════ */}
          <TabsContent value="bulk" className="mt-4">
            <div className="flex flex-col lg:flex-row gap-4" data-testid="bulk-update-layout">
              {/* ─── LEFT PANEL: Filters & Values ─── */}
              <div className="w-full lg:w-[280px] flex-shrink-0 space-y-4" data-testid="bulk-left-panel">
                {/* Update Fields Selection */}
                <Card>
                  <CardHeader className="pb-2 pt-4 px-4">
                    <CardTitle className="text-sm font-semibold text-gray-700">
                      Neleri güncellemek istiyorsunuz?
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

                {/* Values to apply */}
                {enabledFields.size > 0 && (
                  <Card>
                    <CardHeader className="pb-2 pt-4 px-4">
                      <CardTitle className="text-sm font-semibold text-gray-700">
                        Değerler
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="px-4 pb-4 space-y-3">
                      {enabledFields.has('rate') && (
                        <div>
                          <Label className="text-xs text-gray-500">Fiyat (TRY)</Label>
                          <Input
                            type="number" step="0.01" placeholder="0.00"
                            value={bulkRate} onChange={e => setBulkRate(e.target.value)}
                            className="mt-1 h-8 text-sm"
                            data-testid="bulk-rate-input"
                          />
                        </div>
                      )}
                      {enabledFields.has('availability') && (
                        <div>
                          <Label className="text-xs text-gray-500">Müsait Oda</Label>
                          <Input
                            type="number" min="0" placeholder="0"
                            value={bulkAvailability} onChange={e => setBulkAvailability(e.target.value)}
                            className="mt-1 h-8 text-sm"
                            data-testid="bulk-availability-input"
                          />
                        </div>
                      )}
                      {enabledFields.has('min_stay') && (
                        <div>
                          <Label className="text-xs text-gray-500">Min. Konaklama (gece)</Label>
                          <Input
                            type="number" min="1" placeholder="1"
                            value={bulkMinStay} onChange={e => setBulkMinStay(e.target.value)}
                            className="mt-1 h-8 text-sm"
                            data-testid="bulk-min-stay-input"
                          />
                        </div>
                      )}
                      {enabledFields.has('max_stay') && (
                        <div>
                          <Label className="text-xs text-gray-500">Max. Konaklama (gece)</Label>
                          <Input
                            type="number" min="1" placeholder="30"
                            value={bulkMaxStay} onChange={e => setBulkMaxStay(e.target.value)}
                            className="mt-1 h-8 text-sm"
                            data-testid="bulk-max-stay-input"
                          />
                        </div>
                      )}
                      {enabledFields.has('stop_sell') && (
                        <label className="flex items-center gap-2 text-sm cursor-pointer" data-testid="bulk-stop-sell">
                          <Checkbox checked={bulkStopSell} onCheckedChange={setBulkStopSell} />
                          <span>Satışı Durdur</span>
                        </label>
                      )}
                      {enabledFields.has('cta') && (
                        <label className="flex items-center gap-2 text-sm cursor-pointer" data-testid="bulk-cta">
                          <Checkbox checked={bulkCTA} onCheckedChange={setBulkCTA} />
                          <span>Varışa Kapalı (CTA)</span>
                        </label>
                      )}
                      {enabledFields.has('ctd') && (
                        <label className="flex items-center gap-2 text-sm cursor-pointer" data-testid="bulk-ctd">
                          <Checkbox checked={bulkCTD} onCheckedChange={setBulkCTD} />
                          <span>Çıkışa Kapalı (CTD)</span>
                        </label>
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* Date Range */}
                <Card>
                  <CardHeader className="pb-2 pt-4 px-4">
                    <CardTitle className="text-sm font-semibold text-gray-700">Tarih Aralığı</CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-4 space-y-2">
                    <div>
                      <Label className="text-xs text-gray-500">Başlangıç</Label>
                      <Input
                        type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
                        className="mt-1 h-8 text-sm" data-testid="bulk-date-from"
                      />
                    </div>
                    <div>
                      <Label className="text-xs text-gray-500">Bitiş</Label>
                      <Input
                        type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
                        className="mt-1 h-8 text-sm" data-testid="bulk-date-to"
                      />
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
                        <Checkbox
                          checked={selectedDays.has(d.value)}
                          onCheckedChange={() => toggleDay(d.value)}
                        />
                        <span className={selectedDays.has(d.value) ? 'text-gray-900' : 'text-gray-500'}>
                          {d.label}
                        </span>
                      </label>
                    ))}
                  </CardContent>
                </Card>

                {/* Action Buttons */}
                <div className="flex gap-2">
                  <Button
                    className="flex-1 bg-orange-600 hover:bg-orange-700 text-white"
                    onClick={handleBulkUpdate}
                    disabled={saving}
                    data-testid="bulk-update-btn"
                  >
                    {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <Save className="w-4 h-4 mr-1.5" />}
                    Güncelle
                  </Button>
                  <Button variant="outline" onClick={handleReset} data-testid="bulk-reset-btn">
                    <RotateCcw className="w-4 h-4 mr-1" />
                    Sıfırla
                  </Button>
                </div>
              </div>

              {/* ─── CENTER PANEL: Room Types ─── */}
              <div className="flex-1 min-w-0" data-testid="bulk-center-panel">
                <Card className="h-full">
                  <CardHeader className="pb-2 pt-4 px-4">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm font-semibold text-gray-700">Oda adı</CardTitle>
                      <button
                        onClick={toggleAllRoomTypes}
                        className="text-xs text-blue-600 hover:underline"
                        data-testid="select-all-rooms"
                      >
                        {selectedRoomTypes.size === roomTypes.length ? 'Tümünü kaldır' : 'Tümünü seç'}
                      </button>
                    </div>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    {loading && roomTypes.length === 0 ? (
                      <div className="flex items-center justify-center py-12">
                        <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
                      </div>
                    ) : roomTypes.length === 0 ? (
                      <div className="text-center py-12 text-gray-400 text-sm">
                        Exely bağlantısı bulunamadı veya oda tipi tanımlı değil
                      </div>
                    ) : (
                      <div className="space-y-1" data-testid="room-type-list">
                        {roomTypeTree.map(rt => (
                          <div key={rt.code} className="border rounded-lg overflow-hidden">
                            {/* Room Type Header */}
                            <label
                              className={`flex items-center gap-3 px-3 py-2.5 cursor-pointer transition-colors ${
                                selectedRoomTypes.has(rt.code)
                                  ? 'bg-orange-50 border-l-4 border-l-orange-500'
                                  : 'hover:bg-gray-50 border-l-4 border-l-transparent'
                              }`}
                              data-testid={`room-type-${rt.code}`}
                            >
                              <Checkbox
                                checked={selectedRoomTypes.has(rt.code)}
                                onCheckedChange={() => toggleRoomType(rt.code)}
                              />
                              <div className="flex-1 min-w-0">
                                <div className="font-semibold text-sm text-gray-900">{rt.name}</div>
                                <button
                                  onClick={(e) => togglePricingType(rt.code, e)}
                                  className={`text-xs italic cursor-pointer hover:underline transition-colors ${
                                    (pricingSettings[rt.code] || 'per_person') === 'per_room'
                                      ? 'text-blue-600'
                                      : 'text-orange-600'
                                  }`}
                                  data-testid={`pricing-type-toggle-${rt.code}`}
                                >
                                  {getPricingLabel(rt.code)}
                                </button>
                              </div>
                            </label>

                            {/* Rate Plans under this room type */}
                            {rt.plans.map(rp => (
                              <label
                                key={`${rt.code}-${rp.code}`}
                                className={`flex items-center gap-3 px-3 py-2 pl-8 border-t border-gray-100 cursor-pointer transition-colors ${
                                  selectedRatePlans.has(rp.code) && selectedRoomTypes.has(rt.code)
                                    ? 'bg-blue-50'
                                    : 'hover:bg-gray-50'
                                }`}
                                data-testid={`rate-plan-${rt.code}-${rp.code}`}
                              >
                                <Checkbox
                                  checked={selectedRatePlans.has(rp.code)}
                                  onCheckedChange={() => toggleRatePlan(rp.code)}
                                />
                                <div className="flex-1 min-w-0">
                                  <div className="text-sm text-gray-700">
                                    {rt.name} - {rp.name}
                                  </div>
                                  <div className={`text-xs italic ${
                                    (pricingSettings[rt.code] || 'per_person') === 'per_room'
                                      ? 'text-blue-400'
                                      : 'text-gray-400'
                                  }`}>
                                    {getPricingLabel(rt.code)}
                                  </div>
                                </div>
                              </label>
                            ))}
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>

              {/* ─── RIGHT PANEL: Channels ─── */}
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
            {(selectedRoomTypes.size > 0 || enabledFields.size > 0) && (
              <Card className="border-orange-200 bg-orange-50/50" data-testid="bulk-summary">
                <CardContent className="py-3 px-4">
                  <div className="flex flex-wrap items-center gap-3 text-sm">
                    <span className="font-medium text-gray-700">Özet:</span>
                    <Badge variant="outline" className="bg-white">
                      {selectedRoomTypes.size} oda tipi
                    </Badge>
                    <Badge variant="outline" className="bg-white">
                      {selectedRatePlans.size} plan
                    </Badge>
                    <Badge variant="outline" className="bg-white">
                      {enabledFields.size} alan
                    </Badge>
                    <Badge variant="outline" className="bg-white">
                      {dateFrom} → {dateTo}
                    </Badge>
                    {!allDays && (
                      <Badge variant="outline" className="bg-white">
                        {selectedDays.size} gün
                      </Badge>
                    )}
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* ═══════════════ CALENDAR GRID VIEW ═══════════════ */}
          <TabsContent value="grid" className="mt-4">
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-base">Mevcut Fiyat Takvimi</CardTitle>
                    <CardDescription className="text-xs">
                      Tarih bazında mevcut fiyat, müsaitlik ve kısıtlamaları görüntüleyin
                    </CardDescription>
                  </div>
                  <Button variant="outline" size="sm" onClick={fetchGrid} disabled={loading}>
                    <RefreshCw className="w-4 h-4 mr-1.5" /> Yenile
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {/* Grid Filters & Date Navigation */}
                <div className="flex items-center gap-3 flex-wrap mb-4">
                  <Select value={gridRoomType} onValueChange={setGridRoomType}>
                    <SelectTrigger data-testid="grid-room-type-filter" className="w-[180px] h-8 text-xs">
                      <SelectValue placeholder="Oda Tipi" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Tüm Oda Tipleri</SelectItem>
                      {roomTypes.map(rt => (
                        <SelectItem key={rt.code} value={rt.code}>{rt.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <Select value={gridRatePlan} onValueChange={setGridRatePlan}>
                    <SelectTrigger data-testid="grid-rate-plan-filter" className="w-[200px] h-8 text-xs">
                      <SelectValue placeholder="Fiyat Planı" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Tüm Fiyat Planları</SelectItem>
                      {ratePlans.map(rp => (
                        <SelectItem key={rp.code} value={rp.code}>{rp.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <div className="flex items-center gap-1 ml-auto">
                    <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => shiftDates(-7)} data-testid="prev-week-btn">
                      <ChevronLeft className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="outline" size="sm" className="h-8 text-xs"
                      onClick={() => {
                        const t = new Date().toISOString().slice(0, 10);
                        const e = new Date(); e.setDate(e.getDate() + 13);
                        setStartDate(t); setEndDate(e.toISOString().slice(0, 10));
                      }}
                      data-testid="today-btn"
                    >
                      <Calendar className="w-3 h-3 mr-1" />
                      Bugün
                    </Button>
                    <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => shiftDates(7)} data-testid="next-week-btn">
                      <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                </div>

                {/* Grid Table */}
                {loading ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
                  </div>
                ) : (
                  <div className="overflow-x-auto border rounded-lg">
                    <table className="w-full text-sm" data-testid="rate-grid-table">
                      <thead>
                        <tr className="border-b bg-gray-50">
                          <th className="sticky left-0 z-10 bg-gray-50 px-3 py-2 text-left text-xs text-gray-500 font-medium min-w-[200px]">
                            Oda / Plan
                          </th>
                          {dates.map(d => {
                            const f = formatDate(d);
                            return (
                              <th
                                key={d}
                                className={`px-2 py-2 text-center text-xs font-medium min-w-[80px] ${
                                  f.isWeekend ? 'bg-amber-50 text-amber-700' : 'text-gray-500'
                                }`}
                              >
                                <div>{f.weekday}</div>
                                <div className="text-base font-bold text-gray-800">{f.day}</div>
                                <div className="text-[10px] opacity-70">{f.month}</div>
                              </th>
                            );
                          })}
                        </tr>
                      </thead>
                      <tbody>
                        {filteredGrid.map((row) => (
                          <tr
                            key={`${row.room_type_code}-${row.rate_plan_code}`}
                            className="border-b hover:bg-gray-50/50"
                          >
                            <td className="sticky left-0 z-10 bg-white px-3 py-2 border-r">
                              <div className="flex items-center gap-2">
                                <BedDouble className="w-4 h-4 text-gray-400 flex-shrink-0" />
                                <div>
                                  <div className="font-medium text-gray-800 text-xs">{row.room_type_name}</div>
                                  <div className="text-[10px] text-gray-400 truncate max-w-[150px]">{row.rate_plan_name}</div>
                                </div>
                              </div>
                            </td>
                            {row.dates.map((cell) => {
                              const f = formatDate(cell.date);
                              return (
                                <td
                                  key={cell.date}
                                  className={`px-1 py-1 text-center ${
                                    f.isWeekend ? 'bg-amber-50/40' : ''
                                  } ${cell.stop_sell ? 'bg-red-50' : ''}`}
                                  data-testid={`cell-${row.room_type_code}-${row.rate_plan_code}-${cell.date}`}
                                >
                                  <div className="space-y-0.5">
                                    {cell.rate != null ? (
                                      <div className="text-xs font-semibold text-blue-700">{cell.rate} TRY</div>
                                    ) : (
                                      <div className="text-xs text-gray-300">-</div>
                                    )}
                                    <div className="text-[10px] text-gray-400">
                                      {cell.availability != null ? (
                                        <span className={cell.availability === 0 ? 'text-red-500 font-semibold' : cell.availability <= 2 ? 'text-amber-500 font-medium' : ''}>
                                          {cell.availability} oda
                                        </span>
                                      ) : ''}
                                      {cell.sold > 0 && (
                                        <span className="text-blue-500 ml-0.5">({cell.sold} satıldı)</span>
                                      )}
                                    </div>
                                    {cell.min_stay > 1 && (
                                      <div className="text-[10px] text-amber-600">min {cell.min_stay}g</div>
                                    )}
                                    {cell.stop_sell && (
                                      <Lock className="w-3 h-3 text-red-400 mx-auto" />
                                    )}
                                  </div>
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                        {filteredGrid.length === 0 && (
                          <tr>
                            <td colSpan={dates.length + 1} className="py-12 text-center text-gray-400">
                              Veri bulunamadı
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
};

/* ─── Channel List Component ─── */
const ChannelList = () => {
  const CHANNELS = [
    { key: 'online', label: 'Online', active: true },
    { key: 'booking_com', label: 'Booking.com', active: true },
    { key: 'expedia', label: 'Expedia', active: true },
    { key: 'hotelbeds', label: 'Hotelbeds', active: true },
    { key: 'tatilsepeti', label: 'Tatilsepeti.com', active: true },
    { key: 'jolly_tours', label: 'Jolly Tours', active: true },
    { key: 'airbnb', label: 'Airbnb - iCal', active: true },
    { key: 'etg', label: 'Emerging Travel Group', active: true },
    { key: 'agoda', label: 'Agoda', active: true },
    { key: 'etstur', label: 'Etstur', active: true },
    { key: 'tatilbudur', label: 'Tatilbudur.com', active: true },
    { key: 'setur', label: 'Setur', active: true },
    { key: 'otelz', label: 'Otelz.com V2', active: true },
    { key: 'namila', label: 'Namila Tour', active: true },
    { key: 'inhores', label: 'Inhores V2', active: true },
    { key: 'trip', label: 'Trip.com V2', active: true },
  ];

  const [allChannels, setAllChannels] = useState(true);
  const [selected, setSelected] = useState(new Set(CHANNELS.map(c => c.key)));

  const toggleAll = () => {
    if (allChannels) {
      setAllChannels(false);
      setSelected(new Set());
    } else {
      setAllChannels(true);
      setSelected(new Set(CHANNELS.map(c => c.key)));
    }
  };

  const toggleChannel = (key) => {
    setAllChannels(false);
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  return (
    <div className="space-y-1.5">
      <label className="flex items-center gap-2 cursor-pointer text-sm font-medium" data-testid="channel-all">
        <Checkbox checked={allChannels} onCheckedChange={toggleAll} />
        <span>Hepsi</span>
      </label>
      <div className="border-t pt-1.5 space-y-1">
        {CHANNELS.map(ch => (
          <label key={ch.key} className="flex items-center gap-2 cursor-pointer text-xs" data-testid={`channel-${ch.key}`}>
            <Checkbox
              checked={selected.has(ch.key)}
              onCheckedChange={() => toggleChannel(ch.key)}
              className="h-3.5 w-3.5"
            />
            <span className={selected.has(ch.key) ? 'text-gray-800' : 'text-gray-400'}>
              {ch.label}
            </span>
          </label>
        ))}
      </div>
    </div>
  );
};

export default RateManager;
