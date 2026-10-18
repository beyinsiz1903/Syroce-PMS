import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  Building2, Home, TreePalm, Bed, Car, Building, Gem, Tent, MountainSnow,
  Briefcase, Sun, Snowflake, Droplets, Star, Crown, ChevronRight,
  ChevronLeft, Check, Users, DoorOpen, Sparkles, ArrowRight,
  RotateCcw, CalendarDays, UserRound, Plug, WalletCards,
  SlidersHorizontal, Search, ChevronDown, Info,
} from 'lucide-react';
import { MODULE_GROUPS, PLANS, isModuleIncludedInPlan } from './tenantConstants';
import { usePlanCatalog } from '@/lib/planCatalog';
import { NEEDS, TIER_ORDER, applyNeeds, needModules, recommendTier } from '@/lib/setupNeeds';
import { fromMinorUnits, parseFinancialDecimal, toMinorUnits } from '@/lib/financialInput';
import { useTranslation } from 'react-i18next';

const ICON_MAP = {
  Home, TreePalm, Bed, Car, Building, Gem, Tent, Building2,
  Briefcase, Sun, Snowflake, Droplets, Star, Crown, MountainSnow,
};

const TIER_LABELS = {
  mini: { label: 'Mini', color: 'bg-teal-50 text-teal-700 border-teal-200' },
  basic: { label: 'Basic', color: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  professional: { label: 'Professional', color: 'bg-sky-50 text-sky-700 border-sky-200' },
  enterprise: { label: 'Enterprise', color: 'bg-indigo-50 text-indigo-700 border-indigo-200' },
};

// The creation wizard should expose commercial choices, not every internal
// feature flag. Core plan modules, navigation sub-tabs, report entries and
// platform/security switches are derived from the selected plan and remain
// manageable from the tenant detail screen after creation.
const OPTIONAL_MODULE_GROUP_IDS = new Set([
  'optional_workspaces',
  'enterprise',
  'ai',
  'mobile',
  'operations',
  // These are independently licensed/enabled inside their parent hubs. They
  // must be selectable during onboarding as well as in the later edit screen.
  'pms_submodules',
  'rms_submodules',
  'channels_submodules',
  'reports_submodules',
  'reports_items',
  'addons',
]);

const PLAN_HIGHLIGHTS = [
  {
    id: 'front-office',
    title: 'Ön Büro & Rezervasyon',
    description: 'Takvim, oda blokajı ve konaklama akışı',
    icon: CalendarDays,
    keys: ['pms', 'reservation_calendar'],
  },
  {
    id: 'guest-operations',
    title: 'Misafir & Operasyon',
    description: 'Misafir profili ve kat hizmetleri',
    icon: UserRound,
    keys: ['guests', 'housekeeping'],
  },
  {
    id: 'channels',
    title: 'Satış & Kanallar',
    description: 'Kanal yöneticisi ve doğrudan satış',
    icon: Plug,
    keys: ['channel_manager_lite', 'channel_manager', 'booking_engine'],
  },
  {
    id: 'finance',
    title: 'Finans & Raporlama',
    description: 'Folyo, fatura, gün sonu ve raporlar',
    icon: WalletCards,
    keys: ['folio_basic', 'folio_management', 'invoices_basic', 'invoices', 'basic_reporting', 'reports'],
  },
];


const PROPERTY_CATEGORIES = [
  {
    label: 'Hazır Kurulumlar',
    label_detail: 'Sade ve otomatik çalışma alanları',
    types: ['sapanca_kartepe_basic'],
  },
  {
    label: 'Küçük Tesisler',
    label_detail: '1-15 oda',
    types: ['pension', 'villa', 'hostel', 'motel', 'camping'],
  },
  {
    label: 'Orta Ölçek',
    label_detail: '15-100 oda',
    types: ['apart_hotel', 'boutique_hotel', 'hotel_3star', 'city_hotel'],
  },
  {
    label: 'Büyük Tesisler',
    label_detail: '100+ oda',
    types: ['business_hotel', 'hotel_4star', 'hotel_5star'],
  },
  {
    label: 'Resortlar',
    label_detail: 'Tatil tesisleri',
    types: ['resort_summer', 'resort_winter', 'resort_thermal'],
  },
];

// Build the default module map for a given property profile + tier.
// - Top-level keys come from profile.modules (if any) merged with tier defaults.
// - PMS sub-tab keys (`pms.<tab>`) default to true unless explicitly hidden by
//   profile.hidden_nav_items (only relevant for PMS sub-tabs we ship).
const PMS_SUBKEYS = MODULE_GROUPS.find(g => g.id === 'pms_submodules')?.items.map(i => i.key) || [];
const NEGOTIATED_MODULES = MODULE_GROUPS.flatMap((group) => group.items).filter((item) => item.quoteRequired);
const hasPrice = (value) => parseFinancialDecimal(value) !== null;

const buildDefaultModules = (profile, tier) => {
  const result = {};
  // Top-level: collect everything in profile.modules, fall back to tier-included
  // for anything else operator might toggle.
  const profileModules = profile?.modules || {};
  Object.entries(profileModules).forEach(([k, v]) => { result[k] = !!v; });

  // For every checklist item, if not present in profile, derive from tier.
  // PMS sub-tabs use the same tier check as top-level modules so a `mini`
  // tenant doesn't accidentally get `professional`-only sub-tabs (POS,
  // Allotment, etc.) turned on by default. Operator can still toggle them
  // on explicitly in step 3 if they want.
  MODULE_GROUPS.forEach((group) => {
    group.items.forEach((item) => {
      if (item.key in result) return;
      if (item.addon || item.tier === 'addon') {
        result[item.key] = false;
      } else {
        result[item.key] = isModuleIncludedInPlan(item, tier);
      }
    });
  });
  return result;
};

const CreateTenantModal = ({ open, onOpenChange, onSuccess }) => {
  const { t } = useTranslation();
  // Plan scope comes from the server; defaults and prices wait for it.
  const { catalog: planCatalog, ready: planReady, error: planError, retry: retryPlanCatalog } = usePlanCatalog();
  // What the hotel does (sales channels, outlets, operations): drives the
  // recommended plan and the modules switched on. The operator can still
  // pick another plan or customise modules in step 3.
  const [needs, setNeeds] = useState([]);
  const [tierTouched, setTierTouched] = useState(false);
  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [propertyTypes, setPropertyTypes] = useState([]);
  const [selectedType, setSelectedType] = useState(null);
  const [moduleOverrides, setModuleOverrides] = useState({});
  const [advancedModulesOpen, setAdvancedModulesOpen] = useState(false);
  const [moduleSearch, setModuleSearch] = useState('');
  const [showSelectedModulesOnly, setShowSelectedModulesOnly] = useState(false);
  const [expandedModuleGroups, setExpandedModuleGroups] = useState([]);
  const [finalMonthly, setFinalMonthly] = useState(null);
  const [finalSetup, setFinalSetup] = useState(null);
  const [overrideReason, setOverrideReason] = useState('');
  const [negotiatedPrices, setNegotiatedPrices] = useState({});
  // Kanal yoneticisi altyapisi secimi (super_admin). '' = otomatik tespit.
  const [channelProvider, setChannelProvider] = useState('');
  const [chains, setChains] = useState([]);
  const [chainMode, setChainMode] = useState('standalone');
  const [chainId, setChainId] = useState('');
  const [chainName, setChainName] = useState('');
  const [form, setForm] = useState({
    property_name: '',
    property_type: '',
    email: '',
    password: '',
    name: '',
    phone: '',
    address: '',
    location: '',
    total_rooms: '',
    description: '',
    subscription_tier: 'basic',
    subscription_days: 30,
  });

  useEffect(() => {
    if (open) {
      axios.get('/admin/property-types').then(r => {
        setPropertyTypes(r.data.property_types || []);
      }).catch((e) => {
        console.warn('[CreateTenantModal] property-types fetch failed:', e?.response?.status ?? e?.message);
      });
      axios.get('/admin/chains').then(r => setChains(r.data?.chains || [])).catch(() => setChains([]));
    }
  }, [open]);

  const handleChange = (field, value) => setForm((p) => ({ ...p, [field]: value }));
  const modulesTouched = Object.keys(moduleOverrides).length > 0;
  // Preserve only deliberate per-key overrides. A change to an unrelated
  // module must not freeze future needs or plan defaults for the whole form.
  const modulesMap = useMemo(() => {
    if (!selectedType || !planReady) return {};
    return { ...applyNeeds(buildDefaultModules(selectedType, form.subscription_tier), needs), ...moduleOverrides };
  }, [selectedType, planReady, form.subscription_tier, needs, moduleOverrides]);

  const selectPropertyType = (typeKey) => {
    const pt = propertyTypes.find(p => p.key === typeKey);
    if (!pt) return;
    setSelectedType(pt);
    const tier = pt.recommended_tier || 'basic';
    setForm(prev => ({
      ...prev,
      property_type: typeKey,
      subscription_tier: tier,
      total_rooms: prev.total_rooms || pt.room_range?.min || '',
    }));
    setModuleOverrides({});
    setTierTouched(false);
    setAdvancedModulesOpen(false);
    setModuleSearch('');
    setShowSelectedModulesOnly(false);
    setExpandedModuleGroups([]);
  };

  // Lowest plan covering the needs (never below the property type's).
  const recommendation = useMemo(
    () => recommendTier(needs, planCatalog, selectedType?.recommended_tier || 'mini'),
    [needs, planCatalog, selectedType],
  );
  useEffect(() => {
    if (!planReady || tierTouched || !selectedType) return;
    setForm((prev) => (prev.subscription_tier === recommendation.tier ? prev : { ...prev, subscription_tier: recommendation.tier }));
  }, [recommendation.tier, planReady, tierTouched, selectedType]);
  const toggleNeed = (id) => {
    // The latest explicit need choice supersedes an older override for that
    // need only; all unrelated custom choices remain intact.
    setModuleOverrides((current) => Object.fromEntries(Object.entries(current).filter(([key]) => !needModules([id]).includes(key))));
    setNeeds((current) => (current.includes(id) ? current.filter((x) => x !== id) : [...current, id]));
  };
  const tierBelowNeeds = TIER_ORDER.indexOf(form.subscription_tier) < TIER_ORDER.indexOf(recommendation.tier);

  const toggleModule = (key) => {
    setModuleOverrides((prev) => {
      const next = { ...prev, [key]: !modulesMap[key] };
      if (key.startsWith('ai_') && !modulesMap[key]) next.ai = true;
      return next;
    });
  };

  const setGroupAll = (group, value) => {
    setModuleOverrides((prev) => {
      const next = { ...prev };
      group.items.forEach((item) => { next[item.key] = value; });
      return next;
    });
  };

  const resetModulesToDefaults = () => {
    if (!selectedType) return;
    setModuleOverrides({});
  };

  const goToStep2 = () => {
    if (!selectedType) {
      setError('Lütfen bir tesis tipi seçin');
      return;
    }
    setError(null);
    setStep(2);
  };

  const goToStep3 = () => {
    if (!form.property_name || !form.email || !form.password || !form.name || !form.phone || !form.address) {
      setError('Lütfen zorunlu alanları doldurun');
      return;
    }
    if (chainMode === 'new_chain' && chainName.trim().length < 2) {
      setError('Lütfen zincir adını girin');
      return;
    }
    if (chainMode === 'existing_chain' && !chainId) {
      setError('Lütfen eklenecek zinciri seçin');
      return;
    }
    setError(null);
    setStep(3);
  };

  const handleSubmit = async () => {
    if (quote.pendingPricing.length > 0) {
      setError('Seçilen İK / otopark modülleri için aylık tutar, kurulum tutarı ve fiyat gerekçesi girin');
      return;
    }
    if (quote.finalMonthly < 0 || quote.finalSetup < 0 || !Number.isFinite(quote.finalMonthly) || !Number.isFinite(quote.finalSetup)) {
      setError('Nihai fiyatlar sıfır veya daha büyük geçerli sayılar olmalıdır');
      return;
    }
    if (quote.isOverridden && !overrideReason.trim()) {
      setError('Liste fiyatı değiştirildiğinde fiyat değişikliği nedeni zorunludur');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = { ...form };
      if (payload.total_rooms) payload.total_rooms = parseInt(payload.total_rooms);
      else delete payload.total_rooms;
      // Always send the explicit module map so backend uses operator's choices.
      payload.modules = modulesMap;
      payload.commercial_quote = {
        pricing_version: '2026-08-23',
        currency: 'EUR',
        plan_key: form.subscription_tier,
        plan_label: PLANS[form.subscription_tier]?.label || form.subscription_tier,
        base_monthly: quote.baseMonthly,
        addon_monthly: quote.addonMonthly,
        list_monthly_total: quote.listMonthly,
        list_setup_total: quote.listSetup,
        final_monthly_total: quote.finalMonthly,
        final_setup_total: quote.finalSetup,
        override_reason: overrideReason.trim() || null,
        line_items: quote.lineItems,
        negotiated_addon_prices: quote.negotiatedPrices,
      };
      payload.channel_manager_provider = channelProvider || null;
      payload.chain_mode = chainMode;
      if (chainMode === 'existing_chain') payload.chain_id = chainId;
      if (chainMode === 'new_chain') payload.chain_name = chainName.trim();
      const response = await axios.post('/admin/tenants', payload);
      onSuccess?.({ ...response.data, property_name: form.property_name });
      onOpenChange(false);
      resetForm();
    } catch (err) {
      setError(err.response?.data?.detail || 'Tesis oluşturulurken hata oluştu');
    } finally {
      setSaving(false);
    }
  };

  const resetForm = () => {
    setStep(1);
    setSelectedType(null);
    setChannelProvider('');
    setChainMode('standalone');
    setChainId('');
    setChainName('');
    setError(null);
    setModuleOverrides({});
    setNeeds([]);
    setTierTouched(false);
    setAdvancedModulesOpen(false);
    setModuleSearch('');
    setShowSelectedModulesOnly(false);
    setExpandedModuleGroups([]);
    setFinalMonthly(null);
    setFinalSetup(null);
    setOverrideReason('');
    setNegotiatedPrices({});
    setForm({
      property_name: '', property_type: '', email: '', password: '', name: '', phone: '',
      address: '', location: '', total_rooms: '', description: '', subscription_tier: 'basic', subscription_days: 30,
    });
  };

  const getTypesByCategory = (categoryTypes) => {
    return propertyTypes.filter(pt => categoryTypes.includes(pt.key));
  };

  const optionalModuleGroups = useMemo(() => {
    const search = moduleSearch.trim().toLocaleLowerCase('tr-TR');
    return MODULE_GROUPS
      .filter((group) => OPTIONAL_MODULE_GROUP_IDS.has(group.id))
      .map((group) => ({
        ...group,
        items: group.items.filter((item) => {
          if (showSelectedModulesOnly && !modulesMap[item.key]) return false;
          if (!search) return true;
          return `${item.label} ${item.hint || ''}`.toLocaleLowerCase('tr-TR').includes(search);
        }),
      }))
      .filter((group) => group.items.length > 0);
  }, [moduleSearch, modulesMap, showSelectedModulesOnly]);

  const optionalEnabledCount = useMemo(() => {
    return MODULE_GROUPS
      .filter((group) => OPTIONAL_MODULE_GROUP_IDS.has(group.id))
      .flatMap((group) => group.items)
      .filter((item) => modulesMap[item.key])
      .length;
  }, [modulesMap]);

  const quote = useMemo(() => {
    const baseMonthly = PLANS[form.subscription_tier]?.monthlyPrice || 0;
    const manualItems = NEGOTIATED_MODULES.filter((item) => modulesMap[item.key]);
    const pendingPricing = manualItems.filter((item) => {
      const price = negotiatedPrices[item.key];
      return !hasPrice(price?.monthly) || !hasPrice(price?.setup) || !price?.reason?.trim();
    });
    const resolvedPrices = Object.fromEntries(manualItems
      .filter((item) => !pendingPricing.includes(item))
      .map((item) => [item.key, {
        monthly: parseFinancialDecimal(negotiatedPrices[item.key].monthly),
        setup: parseFinancialDecimal(negotiatedPrices[item.key].setup),
        reason: negotiatedPrices[item.key].reason.trim(),
      }]));
    const pricedItems = MODULE_GROUPS.flatMap((group) => group.items)
      .filter((item) => (modulesMap[item.key] || (item.key === 'multi_property' && chainMode !== 'standalone')) && (item.monthly != null || resolvedPrices[item.key]))
      .map((item) => {
        const included = isModuleIncludedInPlan(item, form.subscription_tier);
        const negotiated = resolvedPrices[item.key];
        return {
          module_key: item.key,
          label: item.label,
          monthly: included ? 0 : (negotiated?.monthly ?? item.monthly),
          setup: included ? 0 : (negotiated?.setup ?? item.setup ?? 0),
          included,
          usage_note: item.usageNote || null,
        };
      });
    const addonMonthly = fromMinorUnits(pricedItems.reduce((sum, item) => sum + toMinorUnits(item.monthly), 0));
    const listMonthly = fromMinorUnits(toMinorUnits(baseMonthly) + toMinorUnits(addonMonthly));
    const listSetup = fromMinorUnits(pricedItems.reduce((sum, item) => sum + toMinorUnits(item.setup), 0));
    const resolvedMonthly = finalMonthly === null ? listMonthly : Number(finalMonthly);
    const resolvedSetup = finalSetup === null ? listSetup : Number(finalSetup);
    return {
      baseMonthly, addonMonthly, listMonthly, listSetup,
      finalMonthly: resolvedMonthly,
      finalSetup: resolvedSetup,
      isOverridden: resolvedMonthly !== listMonthly || resolvedSetup !== listSetup,
      lineItems: pricedItems,
      manualItems, pendingPricing, negotiatedPrices: resolvedPrices,
      usageNotes: pricedItems.filter((item) => item.usage_note).map((item) => item.usage_note),
    };
  // planReady: isModuleIncludedInPlan reads the server catalogue loaded behind it.
  }, [chainMode, finalMonthly, finalSetup, form.subscription_tier, modulesMap, negotiatedPrices, planReady]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleExpandedModuleGroup = (groupId) => {
    setExpandedModuleGroups((current) => (
      current.includes(groupId)
        ? current.filter((id) => id !== groupId)
        : [...current, groupId]
    ));
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) resetForm(); }}>
      <DialogContent className={`${step === 1 || step === 3 ? 'max-w-3xl' : 'max-w-lg'} max-h-[90vh] overflow-y-auto p-0`}>
        <div className="sticky top-0 z-10 bg-white border-b px-6 py-4">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Building2 className="w-5 h-5 text-indigo-600" />
              {t('cm.pages_admin_CreateTenantModal.yeni_tesis_ekle')}
              {step >= 2 && selectedType && (
                <span className="ml-2 text-sm font-normal text-slate-500">
                  — {selectedType.name_tr}
                </span>
              )}
            </DialogTitle>
          </DialogHeader>
          <div className="flex items-center gap-3 mt-3">
            {[
              { n: 1, label: 'Tesis Tipi' },
              { n: 2, label: 'Tesis Bilgileri' },
              { n: 3, label: 'Kurulum Özeti' },
            ].map((s, i, arr) => (
              <React.Fragment key={s.n}>
                <div className={`flex items-center gap-1.5 text-xs font-medium ${step === s.n ? 'text-indigo-600' : (step > s.n ? 'text-slate-600' : 'text-slate-400')}`}>
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                    step === s.n ? 'bg-indigo-600 text-white' :
                    step > s.n ? 'bg-emerald-100 text-emerald-700' :
                    'bg-slate-200 text-slate-500'
                  }`}>
                    {step > s.n ? <Check size={12} /> : s.n}
                  </div>
                  {s.label}
                </div>
                {i < arr.length - 1 && <ChevronRight size={14} className="text-slate-300" />}
              </React.Fragment>
            ))}
          </div>
        </div>

        <div className="px-6 pb-6 pt-4">
          {step === 1 && (
            <div className="space-y-5">
              <p className="text-sm text-slate-500">
                {t('cm.pages_admin_CreateTenantModal.tesisinizin_tipini_secin_sectiginiz_tipe')}
              </p>

              {PROPERTY_CATEGORIES.map((cat, ci) => (
                <div key={ci}>
                  <div className="flex items-center gap-2 mb-2">
                    <h3 className="text-sm font-semibold text-slate-700">{cat.label}</h3>
                    <span className="text-xs text-slate-400">{cat.label_detail}</span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {getTypesByCategory(cat.types).map(pt => {
                      const IconComp = ICON_MAP[pt.icon] || Building2;
                      const isSelected = selectedType?.key === pt.key;
                      const tierInfo = TIER_LABELS[pt.recommended_tier] || TIER_LABELS.basic;
                      return (
                        <button
                          key={pt.key}
                          onClick={() => selectPropertyType(pt.key)}
                          className={`relative text-left p-3 rounded-xl border-2 transition-all duration-150 hover:shadow-md ${
                            isSelected
                              ? 'border-indigo-500 bg-indigo-50 shadow-md ring-2 ring-indigo-200'
                              : 'border-slate-200 bg-white hover:border-slate-300'
                          }`}
                        >
                          {isSelected && (
                            <div className="absolute top-2 right-2 w-5 h-5 rounded-full bg-indigo-600 flex items-center justify-center">
                              <Check size={12} className="text-white" />
                            </div>
                          )}
                          <IconComp size={20} className={isSelected ? 'text-indigo-600' : 'text-slate-400'} />
                          <div className="mt-1.5">
                            <div className="text-sm font-medium text-slate-800 leading-tight">{pt.name_tr}</div>
                            <div className="text-[11px] text-slate-400 mt-0.5 flex items-center gap-1.5">
                              <span className="flex items-center gap-0.5"><DoorOpen size={10} />{pt.room_range.min}-{pt.room_range.max}</span>
                              <span className="flex items-center gap-0.5"><Users size={10} />{pt.typical_staff}</span>
                            </div>
                          </div>
                          <div className="mt-1.5">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${tierInfo.color}`}>
                              {tierInfo.label}
                            </span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}

              {selectedType && (
                <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 mt-4">
                  <div className="flex items-start gap-3">
                    <Sparkles size={18} className="text-indigo-600 mt-0.5 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <h4 className="text-sm font-semibold text-indigo-900">{selectedType.name_tr}</h4>
                      <p className="text-xs text-indigo-700 mt-0.5">{selectedType.description_tr}</p>
                      <div className="flex flex-wrap gap-3 mt-2 text-xs text-indigo-600">
                        <span className="flex items-center gap-1"><DoorOpen size={12} /> {selectedType.room_range.min}–{selectedType.room_range.max} oda</span>
                        <span className="flex items-center gap-1"><Users size={12} /> ~{selectedType.typical_staff} personel</span>
                        <span className="flex items-center gap-1">
                          Dashboard: <span className="font-medium capitalize">{selectedType.dashboard_layout}</span>
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {error && <div className="p-2 rounded bg-red-50 text-red-700 text-sm">{error}</div>}
              {planError && (
                <div className="flex items-center justify-between gap-2 rounded bg-amber-50 p-2 text-sm text-amber-800" data-testid="plan-catalog-error">
                  Paket kapsamı sunucudan alınamadı; modül varsayılanları hesaplanamıyor.
                  <Button size="sm" variant="outline" onClick={retryPlanCatalog}>Tekrar dene</Button>
                </div>
              )}

              <div className="flex justify-end pt-2">
                <Button onClick={goToStep2} disabled={!selectedType || !planReady} className="gap-1.5">
                  Devam <ArrowRight size={15} />
                </Button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <Label>{t('cm.pages_admin_CreateTenantModal.tesis_adi')}</Label>
                  <input data-testid="create-tenant-property-name" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.property_name} onChange={(e) => handleChange('property_name', e.target.value)} placeholder={selectedType?.name_tr === 'Pansiyon' ? 'Deniz Pansiyonu' : 'Grand Hotel'} />
                </div>
                <div>
                  <Label>{t('cm.pages_admin_CreateTenantModal.yonetici_adi')}</Label>
                  <input data-testid="create-tenant-admin-name" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.name} onChange={(e) => handleChange('name', e.target.value)} placeholder={t('cm.pages_admin_CreateTenantModal.ahmet_yilmaz')} />
                </div>
                <div>
                  <Label>E-posta *</Label>
                  <input data-testid="create-tenant-email" type="email" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.email} onChange={(e) => handleChange('email', e.target.value)} placeholder="admin@hotel.com" />
                </div>
                <div>
                  <Label>{t('cm.pages_admin_CreateTenantModal.sifre')}</Label>
                  <input data-testid="create-tenant-password" type="password" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.password} onChange={(e) => handleChange('password', e.target.value)} placeholder="En az 6 karakter" />
                </div>
                <div>
                  <Label>Telefon *</Label>
                  <input data-testid="create-tenant-phone" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.phone} onChange={(e) => handleChange('phone', e.target.value)} placeholder="+90 555 123 4567" />
                </div>
                <div className="col-span-2">
                  <Label>Adres *</Label>
                  <input data-testid="create-tenant-address" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.address} onChange={(e) => handleChange('address', e.target.value)} placeholder={t('cm.pages_admin_CreateTenantModal.caddesi_no_1_ilce')} />
                </div>
                <div>
                  <Label>Konum</Label>
                  <input className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.location} onChange={(e) => handleChange('location', e.target.value)} placeholder={t('cm.pages_admin_CreateTenantModal.istanbul')} />
                </div>
                <div>
                  <Label>{t('cm.pages_admin_CreateTenantModal.oda_sayisi')}</Label>
                  <input type="number" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.total_rooms} onChange={(e) => handleChange('total_rooms', e.target.value)} placeholder={selectedType ? `${selectedType.room_range.min}` : '50'} min="1" max="2000" />
                </div>
                <div>
                  <Label>{t('cm.pages_admin_CreateTenantModal.aciklama')}</Label>
                  <input className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.description} onChange={(e) => handleChange('description', e.target.value)} placeholder={selectedType?.name_tr || 'Tesis açıklaması'} />
                </div>
                <div className="col-span-2 rounded-lg border border-indigo-200 bg-indigo-50 p-3 space-y-2" data-testid="create-tenant-needs">
                  <div>
                    <Label>Tesisin ihtiyaçları</Label>
                    <p className="text-[11px] text-slate-500 mt-0.5">İşaretledikleriniz modülleri açar ve uygun planı önerir. Ücretli ekler planı yükseltmez, teklife eklenir. İK ve otopark için son adımda ayrıca fiyat ve gerekçe girilmelidir.</p>
                  </div>
                  {['Satış', 'Tesiste', 'İşletme'].map((group) => (
                    <div key={group} className="flex flex-wrap items-center gap-1.5">
                      <span className="w-16 text-[11px] font-semibold text-slate-500">{group}</span>
                      {NEEDS.filter((need) => need.group === group).map((need) => {
                        const on = needs.includes(need.id);
                        return (
                          <button type="button" key={need.id} data-testid={`need-${need.id}`} aria-pressed={on} onClick={() => toggleNeed(need.id)}
                            className={`rounded-full border px-2.5 py-1 text-xs ${on ? 'border-indigo-500 bg-indigo-600 text-white' : 'border-slate-200 bg-white text-slate-700'}`}>
                            {need.label}{NEGOTIATED_MODULES.some((item) => need.modules.includes(item.key)) ? ' · fiyat gerekli' : need.paid ? ' · ek' : ''}
                          </button>
                        );
                      })}
                    </div>
                  ))}
                  {planReady && (
                    <p className="text-xs text-slate-700" data-testid="create-tenant-recommendation">
                      Önerilen plan: <span className="font-semibold">{TIER_LABELS[recommendation.tier]?.label || recommendation.tier}</span>
                      {recommendation.reasons.length > 0 && <span className="text-slate-500"> — {recommendation.reasons.map((r) => `${r.need} → ${TIER_LABELS[r.tier]?.label || r.tier}`).join(', ')}</span>}
                    </p>
                  )}
                  {recommendation.uncovered.length > 0 && (
                    <p className="text-[11px] text-amber-700">Hiçbir planda bulunmayan: {recommendation.uncovered.join(', ')}; 3. adımda ayrıca açın.</p>
                  )}
                </div>
                <div>
                  <Label>Plan</Label>
                  <select data-testid="create-tenant-tier" className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.subscription_tier} onChange={(e) => { setTierTouched(true); handleChange('subscription_tier', e.target.value); }}>
                    <option value="mini">Mini</option>
                    <option value="basic">Basic</option>
                    <option value="professional">Professional</option>
                    <option value="enterprise">Enterprise</option>
                  </select>
                  {tierBelowNeeds && (
                    <p className="text-[11px] text-red-600 mt-1" data-testid="create-tenant-tier-below-needs">
                      Bu plan işaretlenen ihtiyaçları karşılamıyor; önerilen: {TIER_LABELS[recommendation.tier]?.label}
                    </p>
                  )}
                  {selectedType && form.subscription_tier !== selectedType.recommended_tier && (
                    <p className="text-[11px] text-amber-600 mt-1">
                      {t('cm.pages_admin_CreateTenantModal.bu_tesis_tipi_icin_onerilen_plan')} <span className="font-semibold">{TIER_LABELS[selectedType.recommended_tier]?.label}</span>
                    </p>
                  )}
                </div>
                <div>
                  <Label>{t('cm.pages_admin_CreateTenantModal.uyelik_suresi')}</Label>
                  <select className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={form.subscription_days || ''} onChange={(e) => handleChange('subscription_days', e.target.value ? parseInt(e.target.value) : null)}>
                    <option value="30">{t('cm.pages_admin_CreateTenantModal.30_gun')}</option>
                    <option value="90">{t('cm.pages_admin_CreateTenantModal.90_gun')}</option>
                    <option value="365">{t('cm.pages_admin_CreateTenantModal.1_yil')}</option>
                    <option value="">{t('cm.pages_admin_CreateTenantModal.sinirsiz')}</option>
                  </select>
                </div>
                <div className="col-span-2 rounded-lg border border-slate-200 p-3 space-y-3">
                  <div>
                    <Label>Zincir otel yapısı</Label>
                    <p className="text-[11px] text-slate-500 mt-0.5">Her otel ayrı veri alanında kalır; zincir müdürü konsolide ekran üzerinden takip eder.</p>
                  </div>
                  <div className="grid sm:grid-cols-3 gap-2">
                    {[
                      ['standalone', 'Bağımsız otel'],
                      ['new_chain', 'Yeni zincir merkezi'],
                      ['existing_chain', 'Mevcut zincire ekle'],
                    ].map(([value, label]) => (
                      <button
                        type="button"
                        key={value}
                        onClick={() => setChainMode(value)}
                        className={`rounded-lg border px-3 py-2 text-xs font-medium ${chainMode === value ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-200 text-slate-600'}`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  {chainMode === 'new_chain' && (
                    <div><Label>Yeni zincir adı *</Label><input className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={chainName} onChange={(e) => setChainName(e.target.value)} placeholder="Syroce Hotels" /></div>
                  )}
                  {chainMode === 'existing_chain' && (
                    <div>
                      <Label>Zincir seçin *</Label>
                      <select className="w-full border rounded-lg px-3 py-2 text-sm mt-1" value={chainId} onChange={(e) => setChainId(e.target.value)}>
                        <option value="">Seçiniz</option>
                        {chains.map((chain) => <option key={chain.id} value={chain.id}>{chain.name} ({chain.property_count || 0} otel)</option>)}
                      </select>
                    </div>
                  )}
                </div>
              </div>

              {error && <div className="p-2 rounded bg-red-50 text-red-700 text-sm">{error}</div>}

              <div className="flex justify-between pt-2">
                <Button variant="outline" onClick={() => { setStep(1); setError(null); }} className="gap-1.5">
                  <ChevronLeft size={15} /> Geri
                </Button>
                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>{t('cm.pages_admin_CreateTenantModal.iptal')}</Button>
                  <Button data-testid="create-tenant-next-modules" onClick={goToStep3} className="gap-1.5">
                    Devam <ArrowRight size={15} />
                  </Button>
                </div>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4">
              <div data-testid="tenant-module-summary" className="rounded-xl border border-indigo-200 bg-gradient-to-br from-indigo-50 to-white p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3 min-w-0">
                    <div className="rounded-lg bg-indigo-600 p-2 text-white shrink-0">
                      <Sparkles size={18} />
                    </div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-semibold text-slate-900">Önerilen kurulum hazır</h3>
                        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${TIER_LABELS[form.subscription_tier]?.color || TIER_LABELS.basic.color}`}>
                          {TIER_LABELS[form.subscription_tier]?.label || 'Basic'} plan
                        </span>
                        {modulesTouched && (
                          <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
                            Özelleştirildi
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-xs text-slate-600">
                        {selectedType?.name_tr} için gerekli çekirdek özellikler, menüler ve raporlar planınıza göre otomatik yapılandırılacak.
                      </p>
                    </div>
                  </div>
                  {modulesTouched && (
                    <Button variant="outline" size="sm" onClick={resetModulesToDefaults} className="shrink-0 gap-1 bg-white">
                      <RotateCcw size={12} /> Önerilene dön
                    </Button>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-4">
                  {PLAN_HIGHLIGHTS.map((highlight) => {
                    const HighlightIcon = highlight.icon;
                    const active = highlight.keys.some((key) => modulesMap[key]);
                    return (
                      <div key={highlight.id} className={`flex items-start gap-2 rounded-lg border p-2.5 ${active ? 'border-emerald-200 bg-white' : 'border-slate-200 bg-slate-50'}`}>
                        <div className={`rounded-md p-1.5 ${active ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-400'}`}>
                          <HighlightIcon size={14} />
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-800">
                            {highlight.title}
                            {active && <Check size={12} className="text-emerald-600" />}
                          </div>
                          <p className="mt-0.5 text-[10px] text-slate-500">{highlight.description}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {(modulesMap.channel_manager || modulesMap.channel_manager_lite) && (
                <div className="border border-slate-200 rounded-lg p-3">
                  <h4 className="text-sm font-semibold text-slate-800">Kanal yöneticisi altyapısı</h4>
                  <p className="text-[11px] text-slate-500 mt-0.5 mb-2">
                    Bu otelin fiyat/müsaitlik ekranı hangi altyapı üzerinden çalışsın? Operatör bu adı görmez.
                  </p>
                  <select
                    data-testid="create-tenant-cm-provider"
                    value={channelProvider}
                    onChange={(e) => setChannelProvider(e.target.value)}
                    className="w-full border rounded-lg px-3 py-2 text-sm"
                  >
                    <option value="">Otomatik tespit</option>
                    <option value="exely">Exely</option>
                    <option value="hotelrunner">HotelRunner</option>
                  </select>
                </div>
              )}

              <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
                <button
                  type="button"
                  data-testid="tenant-module-customize-toggle"
                  aria-expanded={advancedModulesOpen}
                  onClick={() => setAdvancedModulesOpen((value) => !value)}
                  className="flex w-full items-center justify-between gap-3 p-4 text-left hover:bg-slate-50"
                >
                  <div className="flex items-start gap-3 min-w-0">
                    <div className="rounded-lg bg-slate-100 p-2 text-slate-600 shrink-0">
                      <SlidersHorizontal size={16} />
                    </div>
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-slate-900">İsteğe bağlı özellikler</div>
                      <div className="mt-0.5 text-[11px] text-slate-500">
                        Kurumsal, yapay zekâ, mobil, entegrasyon ve ek ücretli ürünleri özelleştirin.
                        {optionalEnabledCount > 0 && ` ${optionalEnabledCount} özellik seçili.`}
                      </div>
                    </div>
                  </div>
                  <ChevronDown size={18} className={`shrink-0 text-slate-400 transition-transform ${advancedModulesOpen ? 'rotate-180' : ''}`} />
                </button>

                {advancedModulesOpen && (
                  <div data-testid="tenant-module-customization" className="border-t border-slate-200 p-4 space-y-3">
                    <div className="flex items-start gap-2 rounded-lg border border-sky-100 bg-sky-50 p-3 text-[11px] text-sky-800">
                      <Info size={14} className="mt-0.5 shrink-0" />
                      <p>
                        Paket kapsamındaki çekirdek modüller, alt menüler, rapor listeleri ve platform güvenlik ayarları otomatik yönetilir. Tüm ayrıntıları tesisi oluşturduktan sonra <span className="font-semibold">Otel & Modül Yönetimi</span> ekranından değiştirebilirsiniz.
                      </p>
                    </div>

                    <div className="flex flex-col sm:flex-row gap-2">
                      <label className="relative flex-1">
                        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                        <input
                          value={moduleSearch}
                          onChange={(event) => setModuleSearch(event.target.value)}
                          placeholder="İsteğe bağlı özellik ara..."
                          className="w-full rounded-lg border border-slate-200 py-2 pl-9 pr-3 text-xs focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                        />
                      </label>
                      <button
                        type="button"
                        aria-pressed={showSelectedModulesOnly}
                        onClick={() => setShowSelectedModulesOnly((value) => !value)}
                        className={`rounded-lg border px-3 py-2 text-xs font-medium ${showSelectedModulesOnly ? 'border-indigo-300 bg-indigo-50 text-indigo-700' : 'border-slate-200 text-slate-600 hover:bg-slate-50'}`}
                      >
                        Yalnızca seçilenler
                      </button>
                    </div>

                    <div className="space-y-2">
                      {optionalModuleGroups.map((group) => {
                        const sourceGroup = MODULE_GROUPS.find((candidate) => candidate.id === group.id) || group;
                        const selectedCount = sourceGroup.items.filter((item) => modulesMap[item.key]).length;
                        const allOn = sourceGroup.items.every((item) => modulesMap[item.key]);
                        const allOff = sourceGroup.items.every((item) => !modulesMap[item.key]);
                        const expanded = moduleSearch.trim().length > 0 || expandedModuleGroups.includes(group.id);
                        return (
                          <div key={group.id} className="overflow-hidden rounded-lg border border-slate-200">
                            <button
                              type="button"
                              onClick={() => toggleExpandedModuleGroup(group.id)}
                              className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left hover:bg-slate-50"
                            >
                              <div className="min-w-0">
                                <div className="text-xs font-semibold text-slate-800">{group.title}</div>
                                <div className="mt-0.5 text-[10px] text-slate-500">{selectedCount} / {sourceGroup.items.length} seçili</div>
                              </div>
                              <ChevronDown size={15} className={`shrink-0 text-slate-400 transition-transform ${expanded ? 'rotate-180' : ''}`} />
                            </button>

                            {expanded && (
                              <div className="border-t border-slate-200 bg-slate-50/50 p-3">
                                <div className="mb-2 flex items-start justify-between gap-2">
                                  {group.description ? <p className="text-[10px] text-slate-500">{group.description}</p> : <span />}
                                  <div className="flex shrink-0 gap-1">
                                    <button
                                      type="button"
                                      onClick={() => setGroupAll(sourceGroup, true)}
                                      disabled={allOn}
                                      className="rounded border border-slate-200 bg-white px-2 py-1 text-[10px] text-slate-600 disabled:cursor-not-allowed disabled:opacity-40"
                                    >
                                      Hepsi
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => setGroupAll(sourceGroup, false)}
                                      disabled={allOff}
                                      className="rounded border border-slate-200 bg-white px-2 py-1 text-[10px] text-slate-600 disabled:cursor-not-allowed disabled:opacity-40"
                                    >
                                      Hiçbiri
                                    </button>
                                  </div>
                                </div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                                  {group.items.map((item) => {
                                    const checked = !!modulesMap[item.key];
                                    return (
                                      <label
                                        key={item.key}
                                        className={`flex cursor-pointer items-start gap-2 rounded border p-2 transition-colors ${checked ? 'border-indigo-300 bg-indigo-50/60' : 'border-slate-200 bg-white hover:bg-slate-50'}`}
                                      >
                                        <input
                                          type="checkbox"
                                          checked={checked}
                                          onChange={() => toggleModule(item.key)}
                                          className="mt-0.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                                        />
                                        <div className="min-w-0 flex-1">
                                          <div className="flex flex-wrap items-center gap-1 text-xs font-medium leading-tight text-slate-800">
                                            <span>{item.label}</span>
                                            {isModuleIncludedInPlan(item, form.subscription_tier) ? (
                                              <span className="rounded-full bg-emerald-100 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-700">Pakete dahil</span>
                                            ) : item.monthly != null ? (
                                              <span className="rounded-full bg-indigo-100 px-1.5 py-0.5 text-[9px] font-semibold text-indigo-700">€{item.monthly}/ay</span>
                                            ) : item.quoteRequired ? (
                                              <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-700">Ayrı fiyat gerekli</span>
                                            ) : null}
                                            {!isModuleIncludedInPlan(item, form.subscription_tier) && item.setup > 0 && (
                                              <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-700">Kurulum €{item.setup}</span>
                                            )}
                                          </div>
                                          {item.hint && <div className="mt-0.5 text-[10px] text-slate-500">{item.hint}</div>}
                                          {item.usageNote && <div className="mt-1 text-[9px] font-medium text-amber-700">{item.usageNote}</div>}
                                        </div>
                                      </label>
                                    );
                                  })}
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                      {optionalModuleGroups.length === 0 && (
                        <div className="rounded-lg border border-dashed border-slate-200 p-6 text-center text-xs text-slate-500">
                          Aramanızla eşleşen isteğe bağlı özellik bulunamadı.
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>

              <div data-testid="commercial-quote-summary" className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">Ticari teklif özeti</h3>
                  <p className="mt-0.5 text-[11px] text-slate-500">Bu kayıt yalnızca teklif niteliğindedir; ödeme veya tahsilat başlatmaz.</p>
                </div>
                {quote.manualItems.map((item) => (
                  <fieldset key={item.key} className="rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-2" data-testid={`negotiated-quote-${item.key}`}>
                    <legend className="px-1 text-xs font-semibold text-slate-800">{item.label} — ayrı teklif</legend>
                    <p className="text-[11px] text-slate-600">Bu ürünün sabit EUR fiyatı yok. Anlaşılan EUR tutarını ve gerekçesini girin; TRY mağaza fiyatı otomatik çevrilmez. Ücretsiz verilecekse 0 girip gerekçesini belirtin.</p>
                    <div className="grid grid-cols-2 gap-3">
                      {['monthly', 'setup'].map((field) => (
                        <label key={field} className="text-xs text-slate-700">
                          {field === 'monthly' ? 'Aylık (€) *' : 'Kurulum (€) *'}
                          <input data-testid={`negotiated-${item.key}-${field}`} type="text" inputMode="decimal" autoComplete="off" placeholder="0,00" className="mt-1 w-full rounded-lg border bg-white px-3 py-2 text-sm"
                            value={negotiatedPrices[item.key]?.[field] ?? ''}
                            onChange={(event) => setNegotiatedPrices((current) => ({ ...current, [item.key]: { ...current[item.key], [field]: event.target.value } }))} />
                        </label>
                      ))}
                    </div>
                    <label className="block text-xs text-slate-700">Fiyat gerekçesi / anlaşma notu *
                      <textarea data-testid={`negotiated-${item.key}-reason`} maxLength={1000} className="mt-1 w-full rounded-lg border bg-white px-3 py-2 text-sm"
                        value={negotiatedPrices[item.key]?.reason ?? ''}
                        onChange={(event) => setNegotiatedPrices((current) => ({ ...current, [item.key]: { ...current[item.key], reason: event.target.value } }))} />
                    </label>
                  </fieldset>
                ))}
                {quote.pendingPricing.length > 0 && (
                  <p data-testid="quote-pricing-incomplete" className="rounded-lg bg-amber-50 p-2 text-xs text-amber-800">Teklif tamamlanmadı: {quote.pendingPricing.map((item) => item.label).join(', ')} için tutar ve gerekçe gereklidir. Aşağıdaki ara toplam bu ürünleri içermez; oluşturma kapalıdır.</p>
                )}
                <div className="space-y-1.5 text-xs">
                  <div className="flex justify-between"><span>{PLANS[form.subscription_tier]?.label} paket bedeli</span><strong>€{quote.baseMonthly}/ay</strong></div>
                  {quote.lineItems.filter((item) => !item.included && (item.monthly || item.setup || negotiatedPrices[item.module_key])).map((item) => (
                    <div key={item.module_key} className="flex justify-between gap-3 text-slate-600">
                      <span>{item.label}</span><span>€{item.monthly}/ay{item.setup ? ` + €${item.setup} kurulum` : ''}</span>
                    </div>
                  ))}
                  <div className="flex justify-between border-t pt-2"><span>{quote.pendingPricing.length ? 'Bilinen aylık ara toplam' : 'Liste aylık toplamı'}</span><strong>€{quote.listMonthly}/ay</strong></div>
                  <div className="flex justify-between"><span>Liste kurulum toplamı</span><strong>€{quote.listSetup}</strong></div>
                </div>
                {quote.usageNotes.length > 0 && (
                  <div className="rounded-lg bg-amber-50 p-2 text-[10px] text-amber-800">
                    <strong>Kullanıma bağlı giderler:</strong> {[...new Set(quote.usageNotes)].join(' ')}
                  </div>
                )}
                <div className="grid grid-cols-2 gap-3">
                  <div><Label>Nihai aylık (€)</Label><input data-testid="final-monthly-total" disabled={quote.pendingPricing.length > 0} type="number" min="0" step="0.01" className="mt-1 w-full rounded-lg border px-3 py-2 text-sm" value={finalMonthly === null ? quote.listMonthly : finalMonthly} onChange={(event) => setFinalMonthly(event.target.value)} /></div>
                  <div><Label>Nihai kurulum (€)</Label><input data-testid="final-setup-total" disabled={quote.pendingPricing.length > 0} type="number" min="0" step="0.01" className="mt-1 w-full rounded-lg border px-3 py-2 text-sm" value={finalSetup === null ? quote.listSetup : finalSetup} onChange={(event) => setFinalSetup(event.target.value)} /></div>
                </div>
                {quote.isOverridden && (
                  <div><Label>Fiyat değişikliği nedeni *</Label><textarea data-testid="quote-override-reason" className="mt-1 min-h-20 w-full rounded-lg border px-3 py-2 text-sm" value={overrideReason} onChange={(event) => setOverrideReason(event.target.value)} placeholder="İndirim/onay gerekçesini yazın" /></div>
                )}
              </div>

              {error && <div className="p-2 rounded bg-red-50 text-red-700 text-sm">{error}</div>}

              <div className="flex justify-between pt-2 sticky bottom-0 bg-white border-t -mx-6 px-6 py-3">
                <Button variant="outline" onClick={() => { setStep(2); setError(null); }} className="gap-1.5">
                  <ChevronLeft size={15} /> Geri
                </Button>
                <div className="flex items-center gap-3">
                  <div className="hidden text-right text-xs sm:block">{quote.pendingPricing.length ? <span>Ek ürün fiyatı bekleniyor</span> : <><div className="font-semibold text-slate-900">€{quote.finalMonthly}/ay</div><div className="text-slate-500">Kurulum €{quote.finalSetup}</div></>}</div>
                  <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>{t('cm.pages_admin_CreateTenantModal.iptal_25174')}</Button>
                  <Button data-testid="create-tenant-submit" onClick={handleSubmit} disabled={saving || !planReady || quote.pendingPricing.length > 0}>
                    {saving ? 'Oluşturuluyor...' : 'Tesis Oluştur'}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default CreateTenantModal;
