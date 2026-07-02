import { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import MaybeLayout from '@/components/MaybeLayout';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Grid3X3, CalendarDays, Ban, CheckCircle2, Eye, Loader2, Building2, ChevronDown, ChevronUp, Settings2, Percent, DollarSign, X, AlertTriangle, ShieldAlert, ShieldCheck } from 'lucide-react';
import { BulkUpdatePanel } from './rate-manager/BulkUpdatePanel';
import { CalendarGridView } from './rate-manager/CalendarGridView';
import { StopSalePanel } from './rate-manager/StopSalePanel';
import { useTranslation } from 'react-i18next';
const UNIFIED_PREFIX = '/channel-manager/unified-rate-manager';
const UnifiedRateManager = ({
  user,
  tenant,
  onLogout,
  embedded = false
}) => {
  const {
    t
  } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeView, setActiveView] = useState('bulk');

  // Provider detection
  const [provider, setProvider] = useState(null);
  const [detecting, setDetecting] = useState(true);

  // Grid data
  const [roomTypes, setRoomTypes] = useState([]);
  const [ratePlans, setRatePlans] = useState([]);
  const [grid, setGrid] = useState([]);
  const [pricingSettings, setPricingSettings] = useState({});
  const [currency, setCurrency] = useState('TRY');
  const [pushProviders, setPushProviders] = useState([]);

  // Agencies
  const [agencies, setAgencies] = useState([]);
  const [selectedAgencies, setSelectedAgencies] = useState(new Set());
  const [agencyPanelOpen, setAgencyPanelOpen] = useState(true);
  const [agencyOverrides, setAgencyOverrides] = useState({});
  const [editingOverride, setEditingOverride] = useState(null);
  const CURRENCY_SYMBOLS = {
    TRY: '\u20BA',
    USD: '$',
    EUR: '\u20AC',
    GBP: '\u00A3',
    RUB: '\u20BD'
  };
  const currencySymbol = CURRENCY_SYMBOLS[currency] || currency;

  // Bulk update state
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

  // Circuit breaker statuses (per provider)
  const [breakers, setBreakers] = useState([]);

  // Calendar grid state
  const [gridRoomType, setGridRoomType] = useState('all');
  const [gridRatePlan, setGridRatePlan] = useState('all');
  const [startDate, setStartDate] = useState(today);
  const [endDate, setEndDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 13);
    return d.toISOString().slice(0, 10);
  });
  const headers = {};

  // Fetch circuit breaker status (CM-Hardening Stop-Sale Circuit Breaker, May 2026)
  const fetchBreakers = useCallback(async () => {
    try {
      const {
        data
      } = await axios.get(`${UNIFIED_PREFIX}/circuit-breakers`, {
        headers
      });
      setBreakers(Array.isArray(data?.breakers) ? data.breakers : []);
    } catch (e) {
      // silent — admin-level endpoint, not all roles can read
      console.warn('[UnifiedRateManager] fetchBreakers skipped (likely insufficient role):', e?.response?.status);
    }
  }, []);
  useEffect(() => {
    fetchBreakers();
    const id = setInterval(fetchBreakers, 30000);
    return () => clearInterval(id);
  }, [fetchBreakers]);

  // Lookup helper: current provider's breaker state ('closed' | 'half_open' | 'open')
  const activeBreaker = useMemo(() => breakers.find(b => b.provider === provider) || null, [breakers, provider]);

  // Detect active provider — operatore saglayici ADI gosterilmez; yalnizca
  // hangi altyapinin aktif oldugunu icsel olarak (grid/push yonlendirmesi
  // icin) biliriz. Otel icin secili altyapi backend'de fail-closed uygulanir.
  useEffect(() => {
    const detect = async () => {
      try {
        const {
          data
        } = await axios.get(`${UNIFIED_PREFIX}/detect-provider`, {
          headers
        });
        setProvider(data.provider || null);
      } catch {
        toast.error('Kanal saglayici tespit edilemedi');
      }
      setDetecting(false);
    };
    detect();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only detection
  }, []);

  // Fetch grid
  const fetchGrid = useCallback(async () => {
    if (!provider) return;
    setLoading(true);
    try {
      const {
        data
      } = await axios.get(`${UNIFIED_PREFIX}/grid?start_date=${startDate}&end_date=${endDate}&provider=${provider}`, {
        headers
      });
      setGrid(data.grid || []);
      setRoomTypes(data.room_types || []);
      setRatePlans(data.rate_plans || []);
      if (data.pricing_settings) setPricingSettings(data.pricing_settings);
      if (data.currency) setCurrency(data.currency);
    } catch {
      toast.error('Veriler yüklenemedi');
    }
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [startDate, endDate, provider]);
  useEffect(() => {
    if (provider) fetchGrid();
  }, [fetchGrid, provider]);

  // Fetch push providers
  useEffect(() => {
    if (!provider) return;
    axios.get(`${UNIFIED_PREFIX}/push-providers`, {
      headers
    }).then(res => setPushProviders(res.data?.providers || [])).catch(e => {
      console.warn('[UnifiedRateManager] fetchPushProviders failed (non-critical):', e?.response?.status ?? e?.message); toast.error('Bildirim saglayicilar yuklenemedi');
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [provider]);

  // Fetch agencies
  useEffect(() => {
    axios.get(`${UNIFIED_PREFIX}/agencies`, {
      headers
    }).then(res => setAgencies(res.data?.agencies || [])).catch(e => {
      console.warn('[UnifiedRateManager] fetchAgencies failed (non-critical):', e?.response?.status ?? e?.message); toast.error('Acenteler yuklenemedi');
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  // Room type tree
  const roomTypeTree = useMemo(() => {
    const map = new Map();
    for (const rt of roomTypes) {
      map.set(rt.code, {
        ...rt,
        plans: []
      });
    }
    for (const rp of ratePlans) {
      for (const [, rtObj] of map) {
        rtObj.plans.push(rp);
      }
    }
    return Array.from(map.values());
  }, [roomTypes, ratePlans]);

  // Selection helpers (same pattern as individual managers)
  const getDefaultValues = () => ({
    rate: '',
    availability: '',
    min_stay: '',
    max_stay: '',
    stop_sell: false,
    cta: false,
    ctd: false
  });
  const updateRoomValue = (roomTypeCode, field, value) => {
    setRoomValues(prev => ({
      ...prev,
      [roomTypeCode]: {
        ...(prev[roomTypeCode] || getDefaultValues()),
        [field]: value
      }
    }));
  };
  const applyToAllSelected = (field, value) => {
    setRoomValues(prev => {
      const next = {
        ...prev
      };
      Object.keys(selections).forEach(rtCode => {
        next[rtCode] = {
          ...(next[rtCode] || getDefaultValues()),
          [field]: value
        };
      });
      return next;
    });
  };
  const toggleExpanded = code => {
    setExpandedRoomTypes(prev => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);else next.add(code);
      return next;
    });
  };
  const toggleRoomType = code => {
    setSelections(prev => {
      const next = {
        ...prev
      };
      const allPlans = ratePlans.map(rp => rp.code);
      if (next[code] && next[code].size === allPlans.length) {
        delete next[code];
      } else {
        next[code] = new Set(allPlans);
      }
      return next;
    });
    setRoomValues(prev => prev[code] ? prev : {
      ...prev,
      [code]: getDefaultValues()
    });
  };
  const toggleAllRoomTypes = () => {
    const allPlans = ratePlans.map(rp => rp.code);
    const allSelected = roomTypes.length > 0 && roomTypes.every(rt => selections[rt.code] && selections[rt.code].size === allPlans.length);
    if (allSelected) {
      setSelections({});
    } else {
      const next = {};
      const rv = {
        ...roomValues
      };
      roomTypes.forEach(rt => {
        next[rt.code] = new Set(allPlans);
        if (!rv[rt.code]) rv[rt.code] = getDefaultValues();
      });
      setSelections(next);
      setRoomValues(rv);
    }
  };
  const toggleRatePlan = (roomTypeCode, ratePlanCode) => {
    setSelections(prev => {
      const next = {
        ...prev
      };
      const current = next[roomTypeCode] ? new Set(next[roomTypeCode]) : new Set();
      if (current.has(ratePlanCode)) {
        current.delete(ratePlanCode);
      } else {
        current.add(ratePlanCode);
      }
      if (current.size === 0) {
        delete next[roomTypeCode];
      } else {
        next[roomTypeCode] = current;
      }
      return next;
    });
  };
  const isRoomTypeSelected = code => selections[code] && selections[code].size > 0;
  const isRoomTypeFullySelected = code => selections[code] && selections[code].size === ratePlans.length;
  const isRatePlanSelected = (roomTypeCode, ratePlanCode) => selections[roomTypeCode] && selections[roomTypeCode].has(ratePlanCode);
  const totalSelectedRoomTypes = Object.keys(selections).length;
  const totalSelectedPlans = Object.values(selections).reduce((sum, s) => sum + s.size, 0);
  const toggleField = key => {
    setEnabledFields(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);else next.add(key);
      return next;
    });
  };
  const toggleDay = day => {
    setAllDays(false);
    setSelectedDays(prev => {
      const next = new Set(prev);
      if (next.has(day)) next.delete(day);else next.add(day);
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
  const getPricingLabel = roomTypeCode => {
    const type = pricingSettings[roomTypeCode] || 'per_person';
    return type === 'per_room' ? 'Oda bazli fiyatlandirma' : 'Kisi bazli fiyatlandirma';
  };
  const togglePricingType = async (roomTypeCode, e) => {
    e.preventDefault();
    e.stopPropagation();
    const current = pricingSettings[roomTypeCode] || 'per_person';
    const newType = current === 'per_person' ? 'per_room' : 'per_person';
    setPricingSettings(prev => ({
      ...prev,
      [roomTypeCode]: newType
    }));
    try {
      await axios.put(`${UNIFIED_PREFIX}/pricing-settings`, {
        settings: [{
          room_type_code: roomTypeCode,
          pricing_type: newType
        }]
      }, {
        headers
      });
      toast.success(`${newType === 'per_room' ? 'Oda bazli' : 'Kisi bazli'} fiyatlandirma ayarlandi`);
    } catch {
      setPricingSettings(prev => ({
        ...prev,
        [roomTypeCode]: current
      }));
      toast.error('Fiyatlandırma ayarı güncellenemedi');
    }
  };
  const handleReset = () => {
    setSelections({});
    setEnabledFields(new Set());
    setAllDays(true);
    setSelectedDays(new Set([0, 1, 2, 3, 4, 5, 6]));
    setRoomValues({});
    setExpandedRoomTypes(new Set());
    setDateFrom(today);
    setDateTo(nextWeek);
  };

  // Toggle agency selection
  const toggleAgency = agencyId => {
    setSelectedAgencies(prev => {
      const next = new Set(prev);
      if (next.has(agencyId)) next.delete(agencyId);else next.add(agencyId);
      return next;
    });
  };
  const toggleAllAgencies = () => {
    if (selectedAgencies.size === agencies.length) {
      setSelectedAgencies(new Set());
    } else {
      setSelectedAgencies(new Set(agencies.map(a => a.id)));
    }
  };

  // Save agency override
  const saveAgencyOverride = async (agencyId, roomTypeCode, overrideType, value) => {
    try {
      const override = {
        agency_id: agencyId,
        room_type_code: roomTypeCode
      };
      if (overrideType === 'multiplier') {
        override.rate_multiplier = parseFloat(value);
      } else {
        override.fixed_rate = parseFloat(value);
      }
      await axios.post(`${UNIFIED_PREFIX}/agency-rates`, {
        overrides: [override]
      }, {
        headers
      });
      toast.success('Acente fiyat tanimi kaydedildi');
      setEditingOverride(null);
      // Refresh agencies
      const {
        data
      } = await axios.get(`${UNIFIED_PREFIX}/agencies`, {
        headers
      });
      setAgencies(data?.agencies || []);
    } catch {
      toast.error('Fiyat tanimi kaydedilemedi');
    }
  };

  // Delete agency override
  const deleteAgencyOverride = async agencyId => {
    try {
      await axios.delete(`${UNIFIED_PREFIX}/agency-rates/${agencyId}`, {
        headers
      });
      toast.success('Acente özel fiyati silindi');
      const {
        data
      } = await axios.get(`${UNIFIED_PREFIX}/agencies`, {
        headers
      });
      setAgencies(data?.agencies || []);
    } catch {
      toast.error('Silinemedi');
    }
  };

  // Unified bulk update
  const handleBulkUpdate = async () => {
    if (totalSelectedRoomTypes === 0) {
      toast.error('Lutfen en az bir oda tipi seçin');
      return;
    }
    if (totalSelectedPlans === 0) {
      toast.error('Lutfen en az bir fiyat plani seçin');
      return;
    }
    if (enabledFields.size === 0) {
      toast.error('Lütfen güncellenecek en az bir alan seçin');
      return;
    }
    if (!dateFrom || !dateTo) {
      toast.error('Lutfen tarih araligi seçin');
      return;
    }
    const selectedRoomCodes = Object.keys(selections);
    const hasAnyValue = selectedRoomCodes.some(rtCode => {
      const rv = roomValues[rtCode];
      if (!rv) return false;
      return enabledFields.has('rate') && rv.rate || enabledFields.has('availability') && rv.availability || enabledFields.has('min_stay') && rv.min_stay || enabledFields.has('max_stay') && rv.max_stay || enabledFields.has('stop_sell') && rv.stop_sell || enabledFields.has('cta') && rv.cta || enabledFields.has('ctd') && rv.ctd;
    });
    if (!hasAnyValue) {
      toast.error('Lutfen en az bir oda tipi için değer girin');
      return;
    }
    setSaving(true);
    try {
      const perRoomValues = selectedRoomCodes.map(rtCode => {
        const rv = roomValues[rtCode] || getDefaultValues();
        return {
          room_type_code: rtCode,
          rate_plan_codes: Array.from(selections[rtCode]),
          rate: enabledFields.has('rate') && rv.rate ? parseFloat(rv.rate) : null,
          availability: enabledFields.has('availability') && rv.availability ? parseInt(rv.availability) : null,
          min_stay: enabledFields.has('min_stay') && rv.min_stay ? parseInt(rv.min_stay) : null,
          max_stay: enabledFields.has('max_stay') && rv.max_stay ? parseInt(rv.max_stay) : null,
          stop_sell: enabledFields.has('stop_sell') ? rv.stop_sell : null,
          cta: enabledFields.has('cta') ? rv.cta : null,
          ctd: enabledFields.has('ctd') ? rv.ctd : null
        };
      });
      const agencyIds = selectedAgencies.size > 0 ? Array.from(selectedAgencies) : null;
      const {
        data
      } = await axios.post(`${UNIFIED_PREFIX}/bulk-grid-update`, {
        provider,
        per_room_values: perRoomValues,
        start_date: dateFrom,
        end_date: dateTo,
        selected_days: allDays ? null : Array.from(selectedDays),
        update_fields: Array.from(enabledFields),
        agency_ids: agencyIds
      }, {
        headers
      });
      const providerLabel = 'Kanal yöneticisi';
      const breakerState = activeBreaker?.state;
      if (data.channel_push_count > 0 && breakerState === 'open') {
        toast.warning(`${data.saved} kayıt veritabanına yazıldı, ancak ${providerLabel} şu an erişilemez (devre OPEN). Push tekrar denenecek.`, {
          duration: 8000
        });
      } else if (data.channel_push_count > 0 && breakerState === 'half_open') {
        toast.warning(`${data.saved} kayıt yazıldı; ${providerLabel} kısmen yanıt veriyor (devre HALF_OPEN). Push gönderildi, sonuç birkaç saniye içinde netleşir.`, {
          duration: 6000
        });
      } else {
        toast.success(data.message || `${data.saved} kayıt güncellendi`);
      }
      if (data.agency_push_count > 0) {
        toast.success(`${data.agency_push_count} acente için kaydedildi (webhook bildirimleri gönderildi)`, {
          duration: 5000
        });
      }
      fetchGrid();
      setTimeout(fetchBreakers, 1500);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Güncelleme hatası');
    }
    setSaving(false);
  };

  // Breaker status pill UI helper
  const renderBreakerPill = b => {
    if (!b) return null;
    const map = {
      closed: {
        Icon: ShieldCheck,
        cls: 'bg-emerald-50 text-emerald-700 border-emerald-200',
        label: 'Sağlıklı'
      },
      half_open: {
        Icon: AlertTriangle,
        cls: 'bg-amber-50 text-amber-800 border-amber-200',
        label: 'Kurtarılıyor'
      },
      open: {
        Icon: ShieldAlert,
        cls: 'bg-rose-50 text-rose-700 border-rose-200',
        label: 'Devre Dışı'
      }
    };
    const meta = map[b.state] || map.closed;
    const {
      Icon
    } = meta;
    const providerLabel = 'Kanal';
    const failBit = b.state !== 'closed' ? ` · ${b.failure_count}/${b.failure_threshold} hata` : '';
    return <div key={b.provider} className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-xs font-medium ${meta.cls}`} title={b.last_failure ? `Son hata: ${new Date(b.last_failure).toLocaleString('tr-TR')}` : 'Henüz hata yok'}>
        <Icon className="w-3.5 h-3.5" />
        <span>{providerLabel}: {meta.label}{failBit}</span>
      </div>;
  };

  // Grid helpers
  const filteredGrid = grid.filter(row => {
    if (gridRoomType !== 'all' && row.room_type_code !== gridRoomType) return false;
    if (gridRatePlan !== 'all' && row.rate_plan_code !== gridRatePlan) return false;
    return true;
  });
  const shiftDates = days => {
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
  const formatDate = ds => {
    const d = new Date(ds + 'T00:00:00');
    const dayNames = ['Paz', 'Pzt', 'Sal', 'Car', 'Per', 'Cum', 'Cmt'];
    return {
      day: d.getDate(),
      month: d.toLocaleDateString('tr-TR', {
        month: 'short'
      }),
      weekday: dayNames[d.getDay()],
      isWeekend: d.getDay() === 0 || d.getDay() === 6
    };
  };

  // Provider badge config
  const modeConfig = {
    live: {
      className: 'bg-emerald-600 text-white',
      icon: <CheckCircle2 className="w-3 h-3 mr-1" />,
      label: 'Push Aktif'
    },
    shadow: {
      className: 'bg-amber-500 text-white',
      icon: <Eye className="w-3 h-3 mr-1" />,
      label: 'Shadow Mode'
    },
    inactive: {
      className: 'bg-slate-400 text-white',
      icon: null,
      label: 'Inaktif'
    },
    read_only: {
      className: 'bg-sky-500 text-white',
      icon: <Eye className="w-3 h-3 mr-1" />,
      label: 'Salt Okunur'
    }
  };
  if (detecting) {
    return <MaybeLayout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout} currentModule="unified_rate_manager">
        <div className="flex items-center justify-center min-h-[400px]" data-testid="unified-rate-loading">
          <Loader2 className="w-8 h-8 animate-spin text-zinc-400" />
          <span className="ml-3 text-zinc-500">Kanal saglayici tespit ediliyor...</span>
        </div>
      </MaybeLayout>;
  }
  if (!provider) {
    return <MaybeLayout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout} currentModule="unified_rate_manager">
        <div className="flex flex-col items-center justify-center min-h-[400px] gap-4" data-testid="unified-rate-no-provider">
          <Building2 className="w-16 h-16 text-zinc-300" />
          <h2 className="text-xl font-semibold text-zinc-600">{t('cm.pages_UnifiedRateManager.aktif_kanal_saglayici_bulunamadi')}</h2>
          <p className="text-sm text-zinc-500 text-center max-w-md">
            {t('cm.pages_UnifiedRateManager.fiyat_ve_musaitlik_yonetimi_icin_once_bi')}
          </p>
        </div>
      </MaybeLayout>;
  }
  return <MaybeLayout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout} currentModule="unified_rate_manager">
      <div className="p-4 md:p-6 space-y-4" data-testid="unified-rate-manager-page">
        {/* Header */}
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold" style={{
            fontFamily: 'Space Grotesk'
          }}>
              {t('cm.pages_UnifiedRateManager.fiyat_musaitlik_yonetimi')}
            </h1>
            <p className="text-sm text-zinc-500 mt-1">
              {t('cm.pages_UnifiedRateManager.tum_kanallara_ve_acentelere_tek_noktadan')}
            </p>
          </div>
          <div className="flex items-center gap-2" data-testid="unified-push-provider-badges">
            {pushProviders.length > 0 ? pushProviders.map(p => {
            const cfg = modeConfig[p.mode] || modeConfig.inactive;
            return <Badge key={p.slug} className={cfg.className} data-testid={`unified-push-badge-${p.slug}`}>
                  {cfg.icon}
                  Kanal: {cfg.label}
                </Badge>;
          }) : <Badge className="bg-zinc-600 text-white" data-testid="unified-push-badge-default">
                Kanal Yöneticisi
              </Badge>}
            {selectedAgencies.size > 0 && <Badge className="bg-slate-600 text-white" data-testid="unified-agency-badge">
                <Building2 className="w-3 h-3 mr-1" />
                {selectedAgencies.size} Acente
              </Badge>}
          </div>
        </div>

        {/* Circuit breaker status pills (CM-Hardening Stop-Sale, May 2026) */}
        {breakers.some(b => b.state !== 'closed') && <div className="flex flex-wrap items-center gap-2" data-testid="circuit-breaker-pills">
            <span className="text-xs text-zinc-500">Kanal sağlığı:</span>
            {breakers.map(renderBreakerPill)}
          </div>}

        {/* Main content with agency panel */}
        <div className="flex gap-4">
          {/* Main tabs area */}
          <div className="flex-1 min-w-0">
            <Tabs value={activeView} onValueChange={setActiveView}>
              <TabsList className="grid w-full grid-cols-3 max-w-md">
                <TabsTrigger value="bulk" data-testid="unified-bulk-tab">
                  <Grid3X3 className="w-4 h-4 mr-1.5" /> Toplu Guncelle
                </TabsTrigger>
                <TabsTrigger value="grid" data-testid="unified-grid-tab">
                  <CalendarDays className="w-4 h-4 mr-1.5" /> Takvim Gorunumu
                </TabsTrigger>
                <TabsTrigger value="stop-sale" data-testid="unified-stop-sale-tab">
                  <Ban className="w-4 h-4 mr-1.5" /> Stop Sale
                </TabsTrigger>
              </TabsList>

              <TabsContent value="bulk" className="mt-4">
                <BulkUpdatePanel roomTypeTree={roomTypeTree} roomTypes={roomTypes} ratePlans={ratePlans} enabledFields={enabledFields} toggleField={toggleField} dateFrom={dateFrom} setDateFrom={setDateFrom} dateTo={dateTo} setDateTo={setDateTo} allDays={allDays} selectedDays={selectedDays} toggleDay={toggleDay} toggleAllDays={toggleAllDays} selections={selections} toggleRoomType={toggleRoomType} toggleAllRoomTypes={toggleAllRoomTypes} toggleRatePlan={toggleRatePlan} isRoomTypeSelected={isRoomTypeSelected} isRoomTypeFullySelected={isRoomTypeFullySelected} isRatePlanSelected={isRatePlanSelected} roomValues={roomValues} updateRoomValue={updateRoomValue} getDefaultValues={getDefaultValues} applyToAllSelected={applyToAllSelected} expandedRoomTypes={expandedRoomTypes} toggleExpanded={toggleExpanded} pricingSettings={pricingSettings} getPricingLabel={getPricingLabel} togglePricingType={togglePricingType} currencySymbol={currencySymbol} currency={currency} totalSelectedRoomTypes={totalSelectedRoomTypes} totalSelectedPlans={totalSelectedPlans} saving={saving} handleBulkUpdate={handleBulkUpdate} handleReset={handleReset} loading={loading} />
              </TabsContent>

              <TabsContent value="grid" className="mt-4">
                <CalendarGridView filteredGrid={filteredGrid} dates={dates} roomTypes={roomTypes} ratePlans={ratePlans} gridRoomType={gridRoomType} setGridRoomType={setGridRoomType} gridRatePlan={gridRatePlan} setGridRatePlan={setGridRatePlan} startDate={startDate} setStartDate={setStartDate} endDate={endDate} setEndDate={setEndDate} shiftDates={shiftDates} fetchGrid={fetchGrid} loading={loading} formatDate={formatDate} currency={currency} />
              </TabsContent>

              <TabsContent value="stop-sale" className="mt-4">
                <StopSalePanel roomTypes={roomTypes} ratePlans={ratePlans} fetchGrid={fetchGrid} loading={loading} apiPrefix={UNIFIED_PREFIX} />
              </TabsContent>
            </Tabs>
          </div>

          {/* Agency Panel (right side) */}
          <div className="w-[260px] flex-shrink-0" data-testid="agency-panel">
            <Card className="sticky top-4">
              <CardHeader className="pb-2 pt-4 px-4">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-semibold text-zinc-700 flex items-center gap-1.5">
                    <Building2 className="w-4 h-4" />
                    Acentelere Ilet
                  </CardTitle>
                  <button onClick={() => setAgencyPanelOpen(p => !p)} className="text-zinc-400 hover:text-zinc-600" data-testid="agency-panel-toggle">
                    {agencyPanelOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>
                </div>
              </CardHeader>

              {agencyPanelOpen && <CardContent className="px-4 pb-4 space-y-3">
                  {agencies.length === 0 ? <p className="text-xs text-zinc-400 text-center py-3">
                      {t('cm.pages_UnifiedRateManager.henuz_aktif_acente_tanimlanmamis')}
                    </p> : <>
                      {/* Select all */}
                      <label className="flex items-center gap-2 cursor-pointer text-xs font-medium text-zinc-600 pb-1 border-b border-zinc-100" data-testid="agency-select-all">
                        <Checkbox checked={selectedAgencies.size === agencies.length && agencies.length > 0} onCheckedChange={toggleAllAgencies} />
                        Tumunu Sec ({agencies.length})
                      </label>

                      {/* Agency list */}
                      <div className="space-y-1.5 max-h-[300px] overflow-y-auto">
                        {agencies.map(agency => <div key={agency.id} className="group" data-testid={`agency-item-${agency.id}`}>
                            <label className="flex items-center gap-2 cursor-pointer text-xs">
                              <Checkbox checked={selectedAgencies.has(agency.id)} onCheckedChange={() => toggleAgency(agency.id)} data-testid={`agency-checkbox-${agency.id}`} />
                              <div className="flex-1 min-w-0">
                                <span className={`block truncate ${selectedAgencies.has(agency.id) ? 'text-zinc-900 font-medium' : 'text-zinc-600'}`}>
                                  {agency.name}
                                </span>
                                {agency.has_custom_rates && <span className="text-[10px] text-sky-600 font-medium">{t('cm.pages_UnifiedRateManager.ozel_fiyat')}</span>}
                              </div>
                              <span className="text-[10px] text-zinc-400">%{agency.commission_rate}</span>
                            </label>

                            {/* Override controls */}
                            {selectedAgencies.has(agency.id) && <div className="ml-6 mt-1 flex gap-1">
                                {editingOverride === agency.id ? <AgencyOverrideEditor agency={agency} roomTypes={roomTypes} onSave={saveAgencyOverride} onCancel={() => setEditingOverride(null)} onDelete={() => deleteAgencyOverride(agency.id)} currencySymbol={currencySymbol} /> : <button onClick={() => setEditingOverride(agency.id)} className="text-[10px] text-sky-600 hover:text-sky-800 flex items-center gap-0.5" data-testid={`agency-override-btn-${agency.id}`}>
                                    <Settings2 className="w-3 h-3" />
                                    {agency.has_custom_rates ? 'Özel fiyat düzenle' : 'Özel fiyat tanimla'}
                                  </button>}
                              </div>}
                          </div>)}
                      </div>

                      {/* Summary */}
                      {selectedAgencies.size > 0 && <div className="text-[10px] text-zinc-500 pt-2 border-t border-zinc-100">
                          {t('cm.pages_UnifiedRateManager.guncelleme_yapildiginda_secili')} {selectedAgencies.size} acenteye
                          afise fiyat iletilecektir.
                          {agencies.some(a => selectedAgencies.has(a.id) && a.has_custom_rates) && <span className="block text-sky-600 mt-0.5">
                              {t('cm.pages_UnifiedRateManager.ozel_fiyat_tanimli_acentelerde_indirimli')}
                            </span>}
                        </div>}
                    </>}
                </CardContent>}
            </Card>
          </div>
        </div>
      </div>
    </MaybeLayout>;
};

// Agency Override Editor (inline mini form)
const AgencyOverrideEditor = ({
  agency,
  roomTypes,
  onSave,
  onCancel,
  onDelete,
  currencySymbol
}) => {
  const {
    t
  } = useTranslation();
  const [overrideType, setOverrideType] = useState('multiplier');
  const [value, setValue] = useState(agency.has_custom_rates ? '' : '0.90');
  const [roomType, setRoomType] = useState('*');
  return <div className="bg-zinc-50 rounded p-2 space-y-1.5 w-full" data-testid={`agency-override-editor-${agency.id}`}>
      <div className="flex items-center gap-1">
        <button onClick={() => setOverrideType('multiplier')} className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors ${overrideType === 'multiplier' ? 'bg-sky-100 text-sky-700' : 'bg-zinc-200 text-zinc-500'}`}>
          <Percent className="w-2.5 h-2.5" /> Carpan
        </button>
        <button onClick={() => setOverrideType('fixed')} className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium transition-colors ${overrideType === 'fixed' ? 'bg-sky-100 text-sky-700' : 'bg-zinc-200 text-zinc-500'}`}>
          <DollarSign className="w-2.5 h-2.5" /> Sabit
        </button>
      </div>

      <select value={roomType} onChange={e => setRoomType(e.target.value)} className="w-full text-[10px] h-6 rounded border border-zinc-200 px-1">
        <option value="*">{t('cm.pages_UnifiedRateManager.tum_oda_tipleri')}</option>
        {roomTypes.map(rt => <option key={rt.code} value={rt.code}>{rt.name}</option>)}
      </select>

      <div className="flex items-center gap-1">
        <Input type="number" step={overrideType === 'multiplier' ? '0.01' : '1'} value={value} onChange={e => setValue(e.target.value)} placeholder={overrideType === 'multiplier' ? '0.90 = %10 indirim' : `${currencySymbol}500`} className="h-6 text-[10px] flex-1" data-testid={`agency-override-value-${agency.id}`} />
      </div>

      <div className="flex justify-between">
        <div className="flex gap-1">
          <Button size="sm" variant="default" className="h-5 text-[10px] px-2" onClick={() => onSave(agency.id, roomType, overrideType, value)} data-testid={`agency-override-save-${agency.id}`}>
            {t('cm.pages_UnifiedRateManager.kaydet')}
          </Button>
          <Button size="sm" variant="ghost" className="h-5 text-[10px] px-2" onClick={onCancel}>
            {t('cm.pages_UnifiedRateManager.iptal')}
          </Button>
        </div>
        {agency.has_custom_rates && <Button size="sm" variant="ghost" className="h-5 text-[10px] px-1.5 text-rose-500 hover:text-rose-700" onClick={() => onDelete(agency.id)} data-testid={`agency-override-delete-${agency.id}`}>
            <X className="w-3 h-3" />
          </Button>}
      </div>

      {overrideType === 'multiplier' && <p className="text-[9px] text-zinc-400">
          Ornek: 0.85 = %15 indirim, 1.10 = %10 zam
        </p>}
    </div>;
};
export default UnifiedRateManager;