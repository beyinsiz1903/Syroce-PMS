import React, { useState, useEffect, useMemo, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Settings as SettingsIcon, Users, CreditCard, Shield, Plus, Trash2, Building2, Zap, Crown, ArrowRight, CheckCircle2, Lock, AlertTriangle, ArrowDown, Sparkles, Clock, Receipt, Save, Pencil, X, FileText, Upload, Image, DoorOpen, RefreshCw, Infinity as InfinityIcon, UserCheck, MessageSquare, KeyRound, Copy, Plug } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import BulkRoomsDialog from '@/components/pms/BulkRoomsDialog';
import { useCurrency } from '@/context/CurrencyContext';
import { formatCurrency } from '@/lib/currency';
import { confirmDialog } from '@/lib/dialogs';
import SettingsTeamTab from './SettingsTeamTab';
import SettingsPlanTab from './SettingsPlanTab';
import SettingsBillingTab from './SettingsBillingTab';
import SettingsHotelTab from './SettingsHotelTab';
import SettingsInvoiceTab from './SettingsInvoiceTab';
import SettingsRoomsTab from './SettingsRoomsTab';
import SettingsB2bTab from './SettingsB2bTab';

// ─── Plan Config (Sprint A: gradient/blue/green/orange/pink yok) ──────
// Plan ücretleri base EUR cinsinden tutulur (subscription tarafı EUR);
// gösterimde useCurrency.format ile aktif tenant para birimine çevrilir.
const PLAN_CONFIG = {
  basic: {
    key: 'basic',
    priceEUR: 79,
    priceYearlyEUR: 790,
    maxRooms: 15,
    maxUsers: 3,
    icon: Building2,
    iconBg: 'bg-emerald-100',
    iconText: 'text-emerald-700',
    lightBg: 'bg-emerald-50',
    borderColor: 'border-emerald-200',
    pillIntent: 'success'
  },
  professional: {
    key: 'professional',
    priceEUR: 299,
    priceYearlyEUR: 2990,
    maxRooms: 80,
    maxUsers: 15,
    icon: Zap,
    iconBg: 'bg-sky-100',
    iconText: 'text-sky-700',
    lightBg: 'bg-sky-50',
    borderColor: 'border-sky-200',
    pillIntent: 'info'
  },
  enterprise: {
    key: 'enterprise',
    priceEUR: 799,
    priceYearlyEUR: 7990,
    maxRooms: null,
    maxUsers: null,
    icon: Crown,
    iconBg: 'bg-indigo-100',
    iconText: 'text-indigo-700',
    lightBg: 'bg-indigo-50',
    borderColor: 'border-indigo-200',
    pillIntent: 'neutral'
  }
};

// Sprint A intent paleti (indigo/sky/emerald/amber/rose/slate). Pink/violet/teal/cyan/yellow yok.
const ROLE_COLORS = {
  admin: 'bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200',
  super_admin: 'bg-indigo-100 text-indigo-800 ring-1 ring-indigo-300',
  manager: 'bg-sky-50 text-sky-700 ring-1 ring-sky-200',
  supervisor: 'bg-sky-50 text-sky-700 ring-1 ring-sky-200',
  front_desk: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
  housekeeping: 'bg-amber-50 text-amber-800 ring-1 ring-amber-200',
  finance: 'bg-slate-100 text-slate-700 ring-1 ring-slate-300',
  procurement: 'bg-amber-50 text-amber-800 ring-1 ring-amber-200',
  sales: 'bg-rose-50 text-rose-700 ring-1 ring-rose-200',
  revenue: 'bg-slate-100 text-slate-700 ring-1 ring-slate-300',
  maintenance: 'bg-slate-100 text-slate-700 ring-1 ring-slate-300',
  fnb: 'bg-rose-50 text-rose-700 ring-1 ring-rose-200',
  spa: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
  concierge: 'bg-sky-50 text-sky-700 ring-1 ring-sky-200',
  night_auditor: 'bg-slate-100 text-slate-700 ring-1 ring-slate-300',
  staff: 'bg-slate-100 text-slate-700 ring-1 ring-slate-300'
};

// Para birimi i18n etiketleri için yardımcı (UI tarafında gösterilen ad).
const CURRENCY_OPTIONS = [{
  code: 'TRY',
  label: 'currencyName.TRY',
  fallback: 'Türk Lirası',
  sym: '₺'
}, {
  code: 'EUR',
  label: 'currencyName.EUR',
  fallback: 'Euro',
  sym: '€'
}, {
  code: 'USD',
  label: 'currencyName.USD',
  fallback: 'ABD Doları',
  sym: '$'
}, {
  code: 'GBP',
  label: 'currencyName.GBP',
  fallback: 'İngiliz Sterlini',
  sym: '£'
}];
const Settings = ({
  user,
  tenant,
  onLogout
}) => {
  const {
    t
  } = useTranslation();
  const {
    code: currencyCode,
    format: formatCurrencyTenant,
    refresh: refreshCurrency
  } = useCurrency();
  const getRoleLabel = useCallback(role => ({
    label: t(`settings.roles.${role}`) || role,
    color: ROLE_COLORS[role] || 'bg-slate-100 text-slate-700 ring-1 ring-slate-300'
  }), [t]);
  const PLANS = useMemo(() => ({
    basic: {
      ...PLAN_CONFIG.basic,
      label: t('settings.basic'),
      features: ['PMS Core', t('calendar.title'), 'Dashboard', t('guest.title'), t('housekeeping.title'), t('reports.title'), t('mobile.title'), t('invoice.title')],
      description: t('settings.basic') + ' - ' + (PLAN_CONFIG.basic.maxRooms ? `1-${PLAN_CONFIG.basic.maxRooms} ${t('common.rooms')}` : '')
    },
    professional: {
      ...PLAN_CONFIG.professional,
      label: t('settings.professional'),
      features: [t('settings.basic') + ' +', 'Channel Manager', t('folio.title'), t('nightAudit.title'), t('finance.title'), t('dashboard.costManagement'), t('reports.title'), 'Rate Management', 'Booking Engine'],
      description: t('settings.professional') + ' - ' + (PLAN_CONFIG.professional.maxRooms ? `15-${PLAN_CONFIG.professional.maxRooms} ${t('common.rooms')}` : '')
    },
    enterprise: {
      ...PLAN_CONFIG.enterprise,
      label: t('settings.enterprise'),
      features: [t('settings.professional') + ' +', 'Revenue Management (RMS)', t('aiModule.title'), t('dashboard.multiProperty'), t('dashboard.groupSales'), t('dashboard.salesCRM'), t('loyalty.title'), 'GM Dashboard', 'API', 'White Label', 'Audit Trail'],
      description: t('settings.enterprise') + ' - 80+ ' + t('common.rooms')
    }
  }), [t]);

  // Plan değişimi sonrası activeTab'ı koru (window.location.reload state kaybını önler).
  const [activeTab, setActiveTab] = useState(() => {
    try {
      const saved = sessionStorage.getItem('settings:activeTab');
      if (saved) sessionStorage.removeItem('settings:activeTab');
      return saved || 'team';
    } catch {
      return 'team';
    }
  });

  // B2B Connect (Seçenek B — acente oto-saglama)
  const [b2bInfo, setB2bInfo] = useState(null);
  const [b2bRequests, setB2bRequests] = useState([]);
  const [b2bLoading, setB2bLoading] = useState(false);
  const [b2bCodeOnce, setB2bCodeOnce] = useState(''); // ham kod yalniz 1 kez
  const [b2bBusy, setB2bBusy] = useState(false);

  // Team
  const [team, setTeam] = useState([]);
  const [teamLoading, setTeamLoading] = useState(true);
  const [teamMeta, setTeamMeta] = useState({
    tier: 'basic',
    allowed_roles: ['admin'],
    max_users: 3,
    can_add: true
  });
  const [showAddModal, setShowAddModal] = useState(false);
  const [newMember, setNewMember] = useState({
    email: '',
    name: '',
    phone: '',
    role: 'admin',
    password: ''
  });
  const [saving, setSaving] = useState(false);

  // Subscription
  const [subscription, setSubscription] = useState(null);
  const [billingCycle, setBillingCycle] = useState('monthly');
  const [showPlanModal, setShowPlanModal] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [planAction, setPlanAction] = useState('upgrade');

  // Billing history
  const [billingHistory, setBillingHistory] = useState([]);
  const [billingLoading, setBillingLoading] = useState(false);

  // Hotel info editing
  const [editMode, setEditMode] = useState(false);
  const [hotelForm, setHotelForm] = useState({});
  const [hotelSaving, setHotelSaving] = useState(false);

  // Invoice settings
  const [invoiceSettings, setInvoiceSettings] = useState({});
  const [invoiceLoading, setInvoiceLoading] = useState(false);
  const [invoiceSaving, setInvoiceSaving] = useState(false);

  // Room management (super_admin only)
  const isSuperAdmin = user?.role === 'super_admin' || Array.isArray(user?.roles) && user.roles.includes('super_admin');
  // Misafir Talepleri görünürlük ayarı: admin + super_admin yapılandırabilir.
  const isAdmin = isSuperAdmin || user?.role === 'admin' || Array.isArray(user?.roles) && user.roles.includes('admin');
  const [roomsList, setRoomsList] = useState([]);
  const [roomsLoading, setRoomsLoading] = useState(false);
  const [showBulkRoomsDialog, setShowBulkRoomsDialog] = useState(false);
  const [showAddRoomDialog, setShowAddRoomDialog] = useState(false);
  const [newRoom, setNewRoom] = useState({
    room_number: '',
    room_type: 'standard',
    floor: 1,
    capacity: 2,
    base_price: 100
  });
  const [roomSaving, setRoomSaving] = useState(false);

  // Misafir Talepleri görünürlüğü (admin)
  const [grSettings, setGrSettings] = useState({
    visible_roles: [],
    available_roles: [],
    always_allowed: []
  });
  const [grLoading, setGrLoading] = useState(false);
  const [grSaving, setGrSaving] = useState(false);
  const currentTier = useMemo(() => {
    const t = tenant?.subscription_tier || 'basic';
    if (t === 'pro') return 'professional';
    if (t === 'ultra') return 'enterprise';
    return t;
  }, [tenant]);
  const currentPlan = PLANS[currentTier] || PLANS.basic;
  const PlanIcon = currentPlan.icon;

  // Plan ücretini aktif tenant para biriminde formatla.
  const fmtPlanPrice = useCallback(eurAmount => {
    if (!Number.isFinite(eurAmount)) return '—';
    if (currencyCode === 'EUR') return formatCurrency(eurAmount, 'EUR', {
      decimals: 0
    });
    // Plan ücretleri sözleşme gereği EUR; tenant TRY ise tenant biriminde
    // göstermek yerine "EUR" işaretiyle dönmek daha doğru (FX dönüşüm yok).
    try {
      return formatCurrencyTenant ? `${formatCurrency(eurAmount, 'EUR', {
        decimals: 0
      })}` : `${eurAmount}€`;
    } catch {
      return `${eurAmount}€`;
    }
  }, [currencyCode, formatCurrencyTenant]);

  // ─── Loaders ───────────────────────────────────
  const loadTeam = useCallback(async () => {
    setTeamLoading(true);
    try {
      const res = await axios.get('/hotel/team');
      setTeam(res.data?.users || []);
      setTeamMeta({
        tier: res.data?.tier || 'basic',
        allowed_roles: res.data?.allowed_roles || ['admin'],
        max_users: res.data?.max_users || 3,
        can_add: res.data?.can_add !== false
      });
    } catch (err) {
      console.error('Team load failed', err);
      toast.error(err?.response?.data?.detail || 'Ekip listesi alınamadı');
    } finally {
      setTeamLoading(false);
    }
  }, []);
  const loadSubscription = useCallback(async () => {
    try {
      const res = await axios.get('/subscription/current');
      setSubscription(res.data);
    } catch (err) {
      console.error('Sub load failed', err);
      toast.error(err?.response?.data?.detail || 'Abonelik bilgisi alınamadı');
    }
  }, []);
  const loadBillingHistory = useCallback(async () => {
    setBillingLoading(true);
    try {
      const res = await axios.get('/billing/history');
      setBillingHistory(res.data?.records || []);
    } catch (err) {
      console.error('Billing load failed', err);
      toast.error(err?.response?.data?.detail || 'Fatura geçmişi alınamadı');
    } finally {
      setBillingLoading(false);
    }
  }, []);
  const loadInvoiceSettings = useCallback(async () => {
    setInvoiceLoading(true);
    try {
      const res = await axios.get('/pms/hotel-settings');
      setInvoiceSettings(res.data || {});
    } catch (err) {
      console.error('Invoice settings load failed', err);
      toast.error(err?.response?.data?.detail || 'Fatura ayarları alınamadı');
    } finally {
      setInvoiceLoading(false);
    }
  }, []);
  const loadRooms = useCallback(async () => {
    if (!isSuperAdmin) return;
    setRoomsLoading(true);
    try {
      const res = await axios.get('/pms/rooms?limit=500');
      setRoomsList(res.data || []);
    } catch (err) {
      console.error('Rooms load failed', err);
      toast.error(err?.response?.data?.detail || 'Oda listesi alınamadı');
    } finally {
      setRoomsLoading(false);
    }
  }, [isSuperAdmin]);
  const loadB2B = useCallback(async () => {
    if (!isAdmin) return;
    setB2bLoading(true);
    try {
      const [infoRes, reqRes] = await Promise.all([axios.get('/b2b/connect-info'), axios.get('/b2b/connect-requests')]);
      setB2bInfo(infoRes.data || null);
      setB2bRequests(reqRes.data?.items || []);
    } catch (err) {
      console.error('B2B load failed', err);
      toast.error(err?.response?.data?.detail || 'B2B bilgileri alınamadı');
    } finally {
      setB2bLoading(false);
    }
  }, [isAdmin]);
  const copyToClipboard = useCallback(async (text, label) => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      toast.success(`${label} kopyalandı`);
    } catch {
      toast.error('Kopyalanamadı');
    }
  }, []);
  const handleRegenerateCode = useCallback(async () => {
    if (b2bInfo?.has_active_code && !(await confirmDialog({
      message: 'Yeni bağlantı kodu üretilsin mi? Eski kod geçersiz olur; bağlı acentelerin yeni kodla güncellenmesi gerekir.',
      variant: 'danger'
    }))) return;
    setB2bBusy(true);
    try {
      const res = await axios.post('/b2b/connect-codes/regenerate');
      setB2bCodeOnce(res.data?.connect_code || '');
      toast.success('Bağlantı kodu üretildi. Yalnızca bir kez gösterilir.');
      await loadB2B();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Kod üretilemedi');
    } finally {
      setB2bBusy(false);
    }
  }, [b2bInfo, loadB2B]);
  const handleApproveRequest = useCallback(async req => {
    if (!(await confirmDialog({
      message: `"${req.agency_name}" bağlantısı onaylansın mı? Onayda bu acenteye API key üretilecek.`
    }))) return;
    setB2bBusy(true);
    try {
      const res = await axios.post(`/b2b/connect-requests/${req.id}/approve`);
      toast.success(res.data?.message || 'İstek onaylandı');
      await loadB2B();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Onaylanamadı');
    } finally {
      setB2bBusy(false);
    }
  }, [loadB2B]);
  const handleRejectRequest = useCallback(async req => {
    if (!(await confirmDialog({
      message: `"${req.agency_name}" bağlantı isteği reddedilsin mi?`,
      variant: 'danger'
    }))) return;
    setB2bBusy(true);
    try {
      await axios.post(`/b2b/connect-requests/${req.id}/reject`, {
        reason: ''
      });
      toast.success('İstek reddedildi');
      await loadB2B();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Reddedilemedi');
    } finally {
      setB2bBusy(false);
    }
  }, [loadB2B]);
  const loadGuestRequestSettings = useCallback(async () => {
    if (!isAdmin) return;
    setGrLoading(true);
    try {
      const res = await axios.get('/messaging/guest-requests/settings');
      setGrSettings({
        visible_roles: res.data?.visible_roles || [],
        available_roles: res.data?.available_roles || [],
        always_allowed: res.data?.always_allowed || []
      });
    } catch (err) {
      console.error('Guest request settings load failed', err);
      toast.error(err?.response?.data?.detail || 'Misafir talep ayarları alınamadı');
    } finally {
      setGrLoading(false);
    }
  }, [isAdmin]);
  const toggleGuestRequestRole = useCallback((role, checked) => {
    setGrSettings(prev => {
      const set = new Set(prev.visible_roles);
      if (checked) set.add(role);else set.delete(role);
      return {
        ...prev,
        visible_roles: Array.from(set)
      };
    });
  }, []);
  const saveGuestRequestSettings = useCallback(async () => {
    setGrSaving(true);
    try {
      const res = await axios.put('/messaging/guest-requests/settings', {
        visible_roles: grSettings.visible_roles
      });
      setGrSettings(prev => ({
        ...prev,
        visible_roles: res.data?.visible_roles || prev.visible_roles
      }));
      toast.success('Misafir talep görünürlüğü kaydedildi');
    } catch (err) {
      console.error('Guest request settings save failed', err);
      toast.error(err?.response?.data?.detail || 'Ayar kaydedilemedi');
    } finally {
      setGrSaving(false);
    }
  }, [grSettings.visible_roles]);
  useEffect(() => {
    // Only load what is needed for the active tab (Lazy fan-out reduction)
    if (activeTab === 'hotel' || activeTab === 'plan') {
      if (!subscription) loadSubscription();
    }
    if (activeTab === 'team') {
      if (team.length === 0) loadTeam();
    }
    if (activeTab === 'billing') {
      if (billingHistory.length === 0) loadBillingHistory();
    }
    if (activeTab === 'invoice') {
      if (Object.keys(invoiceSettings).length === 0) loadInvoiceSettings();
    }
    if (activeTab === 'rooms') {
      if (roomsList.length === 0) loadRooms();
    }
    if (activeTab === 'guest-requests') {
      if (grSettings.visible_roles.length === 0) loadGuestRequestSettings();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  // Init hotel form from tenant
  useEffect(() => {
    if (tenant) {
      setHotelForm({
        property_name: tenant.property_name || '',
        phone: tenant.phone || tenant.contact_phone || '',
        email: tenant.email || tenant.contact_email || '',
        address: tenant.address || '',
        location: tenant.location || '',
        description: tenant.description || '',
        total_rooms: tenant.total_rooms || 0
      });
    }
  }, [tenant]);

  // ─── Self check (id veya _id eşleşmesi) ───────
  const isSameUser = useCallback(member => {
    if (!user) return false;
    const ids = [user.id, user._id].filter(Boolean);
    return ids.includes(member.id) || ids.includes(member._id);
  }, [user]);

  // ─── Team Handlers ─────────────────────────────
  const handleAddMember = async () => {
    if (!newMember.email || !newMember.name || !newMember.password) {
      toast.error('Email, isim ve şifre zorunludur');
      return;
    }
    if (newMember.password.length < 6) {
      toast.error('Şifre en az 6 karakter olmalıdır');
      return;
    }
    setSaving(true);
    try {
      const res = await axios.post('/hotel/team', newMember);
      toast.success(res.data?.message || 'Ekip üyesi eklendi');
      setShowAddModal(false);
      setNewMember({
        email: '',
        name: '',
        phone: '',
        role: teamMeta.allowed_roles[0] || 'admin',
        password: ''
      });
      await loadTeam();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Ekip üyesi eklenemedi');
    } finally {
      setSaving(false);
    }
  };
  const handleUpdateRole = async (userId, newRole) => {
    try {
      await axios.patch(`/hotel/team/${userId}/role`, {
        role: newRole
      });
      toast.success('Rol güncellendi');
      await loadTeam();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Rol güncellenemedi');
    }
  };
  const handleRemoveMember = async (userId, name) => {
    if (!(await confirmDialog({
      message: `${name} adlı kullanıcıyı silmek istediğinize emin misiniz?`,
      variant: 'danger'
    }))) return;
    try {
      await axios.delete(`/hotel/team/${userId}`);
      toast.success('Ekip üyesi silindi');
      await loadTeam();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Silinemedi');
    }
  };

  // ─── Plan Change Handler ───────────────────────
  const handleChangePlan = async () => {
    if (!selectedPlan) return;
    setSaving(true);
    try {
      const res = await axios.post('/subscription/change-plan', {
        new_tier: selectedPlan,
        billing_cycle: billingCycle
      });
      toast.success(res.data?.message || 'Plan güncellendi');
      setShowPlanModal(false);
      // Modüller App.jsx mount'unda yükleniyor; aktif tab'ı koruyup soft reload.
      try {
        sessionStorage.setItem('settings:activeTab', activeTab);
      } catch {/* ignore */}
      await Promise.all([loadSubscription(), loadBillingHistory(), loadTeam()]);
      setTimeout(() => window.location.reload(), 600);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Plan değiştirilemedi');
    } finally {
      setSaving(false);
    }
  };

  // ─── Hotel Info Handler ────────────────────────
  const overRoomLimit = useMemo(() => {
    const limit = currentPlan.maxRooms;
    if (!limit) return false;
    return Number(hotelForm.total_rooms) > Number(limit);
  }, [currentPlan.maxRooms, hotelForm.total_rooms]);
  const handleSaveHotelInfo = async () => {
    if (overRoomLimit) {
      toast.error(`Mevcut planınızda en fazla ${currentPlan.maxRooms} oda tanımlanabilir. Önce planınızı yükseltin.`);
      return;
    }
    setHotelSaving(true);
    try {
      const res = await axios.patch('/hotel/info', hotelForm);
      toast.success(res.data?.message || 'Otel bilgileri güncellendi');
      setEditMode(false);
      // localStorage'daki tenant'ı senkron tutmak: App.jsx mount'unda
      // okunduğu için bu yazım sıradaki sayfa açılışına etki eder.
      // (Auth context'inde refreshTenant fonksiyonu yok — invasive değişiklik
      // bilinçli olarak yapılmadı.)
      const updatedTenant = res.data?.tenant;
      if (updatedTenant) {
        try {
          const stored = JSON.parse(localStorage.getItem('tenant') || '{}');
          const merged = {
            ...stored,
            ...updatedTenant
          };
          localStorage.setItem('tenant', JSON.stringify(merged));
        } catch {/* ignore */}
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Güncellenemedi');
    } finally {
      setHotelSaving(false);
    }
  };
  const handleSaveInvoiceSettings = async () => {
    setInvoiceSaving(true);
    try {
      // currency_symbol UI'da tutulmuyor; her zaman currency'den derive ederiz.
      const codeUpper = String(invoiceSettings.currency || 'TRY').toUpperCase();
      const symLookup = CURRENCY_OPTIONS.find(c => c.code === codeUpper);
      const payload = {
        ...invoiceSettings,
        currency: codeUpper,
        currency_symbol: symLookup?.sym || codeUpper
      };
      const res = await axios.put('/pms/hotel-settings', payload);
      toast.success('Fatura ayarları kaydedildi');
      setInvoiceSettings(res.data?.settings || payload);
      try {
        await refreshCurrency();
      } catch {/* ignore */}
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Kaydedilemedi');
    } finally {
      setInvoiceSaving(false);
    }
  };
  const handleLogoUpload = e => {
    const file = e.target.files?.[0];
    // Input'u sıfırla ki aynı dosya tekrar seçilebilsin.
    if (e.target) e.target.value = '';
    if (!file) return;
    // MIME whitelist (KVKK/güvenlik): yalnızca image/png, image/jpeg, image/webp.
    const ALLOWED_MIME = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp'];
    if (!ALLOWED_MIME.includes(file.type)) {
      toast.error('Yalnızca PNG, JPG veya WebP yüklenebilir.');
      return;
    }
    if (file.size > 2 * 1024 * 1024) {
      toast.error("Logo dosyası 2MB'dan küçük olmalıdır");
      return;
    }
    const reader = new FileReader();
    reader.onload = event => {
      // Boyut/dimension doğrulama: çok büyük çözünürlüklerde uyar.
      const dataUrl = event.target.result;
      const probe = new window.Image();
      probe.onload = () => {
        if (probe.width > 2000 || probe.height > 2000) {
          toast.error('Logo en fazla 2000×2000 piksel olabilir.');
          return;
        }
        setInvoiceSettings(prev => ({
          ...prev,
          logo_data: dataUrl
        }));
      };
      probe.onerror = () => toast.error('Logo görseli okunamadı.');
      probe.src = dataUrl;
    };
    reader.onerror = () => toast.error('Dosya okunamadı.');
    reader.readAsDataURL(file);
  };

  // Room CRUD (super_admin)
  const handleCreateRoom = async e => {
    e.preventDefault();
    if (!newRoom.room_number?.toString().trim()) {
      toast.error('Oda numarası zorunludur');
      return;
    }
    if (!Number.isFinite(newRoom.floor) || newRoom.floor < 0) {
      toast.error('Kat negatif olamaz');
      return;
    }
    if (!Number.isFinite(newRoom.capacity) || newRoom.capacity < 1) {
      toast.error('Kapasite en az 1 olmalıdır');
      return;
    }
    if (!Number.isFinite(newRoom.base_price) || newRoom.base_price < 0) {
      toast.error('Taban fiyat negatif olamaz');
      return;
    }
    setRoomSaving(true);
    try {
      await axios.post('/pms/rooms', newRoom);
      toast.success('Oda oluşturuldu');
      setShowAddRoomDialog(false);
      setNewRoom({
        room_number: '',
        room_type: 'standard',
        floor: 1,
        capacity: 2,
        base_price: 100
      });
      loadRooms();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Oda oluşturulamadı');
    } finally {
      setRoomSaving(false);
    }
  };
  const handleDeleteRoom = async (roomId, roomNumber) => {
    if (!(await confirmDialog({
      message: `${roomNumber} numaralı odayı silmek istediğinize emin misiniz?`,
      variant: 'danger'
    }))) return;
    try {
      await axios.post('/pms/rooms/bulk/delete', {
        ids: [roomId],
        confirm_text: 'DELETE'
      });
      toast.success(`Oda ${roomNumber} silindi`);
      loadRooms();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Oda silinemedi');
    }
  };

  // Plan tiers for upgrade/downgrade
  const tierOrder = ['basic', 'professional', 'enterprise'];
  const currentIdx = tierOrder.indexOf(currentTier);
  const upgradeTiers = tierOrder.filter((_, i) => i > currentIdx);
  const downgradeTiers = tierOrder.filter((_, i) => i < currentIdx);
  const openPlanModal = (tierKey, action) => {
    setSelectedPlan(tierKey);
    setPlanAction(action);
    setBillingCycle('monthly');
    setShowPlanModal(true);
  };

  // ─── Yenile butonu (her tab için) ───────────
  const refreshActiveTab = useCallback(() => {
    if (activeTab === 'team') loadTeam();else if (activeTab === 'plan') loadSubscription();else if (activeTab === 'billing') loadBillingHistory();else if (activeTab === 'hotel') loadSubscription();else if (activeTab === 'invoice') loadInvoiceSettings();else if (activeTab === 'rooms') loadRooms();else if (activeTab === 'b2b') loadB2B();
  }, [activeTab, loadTeam, loadSubscription, loadBillingHistory, loadInvoiceSettings, loadRooms, loadB2B]);
  const tabBusy = activeTab === 'team' && teamLoading || activeTab === 'billing' && billingLoading || activeTab === 'invoice' && invoiceLoading || activeTab === 'rooms' && roomsLoading;
  return <>
      <div className="p-4 md:p-6 space-y-4 max-w-6xl mx-auto">
        <PageHeader icon={SettingsIcon} iconClassName="text-slate-700" title="Ayarlar" subtitle={t('settings.subtitle')} actions={<>
              <StatusBadge intent={currentPlan.pillIntent || 'neutral'} icon={PlanIcon}>
                {currentPlan.label}
              </StatusBadge>
              <Button variant="outline" size="sm" onClick={refreshActiveTab} disabled={tabBusy}>
                <RefreshCw className={`w-4 h-4 mr-1.5 ${tabBusy ? 'animate-spin' : ''}`} />
                Yenile
              </Button>
            </>} />

        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
          <TabsList className={`grid w-full ${isSuperAdmin ? 'grid-cols-7' : isAdmin ? 'grid-cols-6' : 'grid-cols-5'}`}>
            <TabsTrigger value="team" className="flex items-center gap-1.5 text-xs sm:text-sm">
              <Users className="w-4 h-4" /> Ekip
            </TabsTrigger>
            <TabsTrigger value="plan" className="flex items-center gap-1.5 text-xs sm:text-sm">
              <CreditCard className="w-4 h-4" /> Plan
            </TabsTrigger>
            <TabsTrigger value="billing" className="flex items-center gap-1.5 text-xs sm:text-sm">
              <Receipt className="w-4 h-4" /> Fatura Geçmişi
            </TabsTrigger>
            <TabsTrigger value="hotel" className="flex items-center gap-1.5 text-xs sm:text-sm">
              <Building2 className="w-4 h-4" /> Otel
            </TabsTrigger>
            <TabsTrigger value="invoice" className="flex items-center gap-1.5 text-xs sm:text-sm" data-testid="invoice-settings-tab">
              <FileText className="w-4 h-4" /> Fatura & Para Birimi
            </TabsTrigger>
            {isSuperAdmin && <TabsTrigger value="rooms" className="flex items-center gap-1.5 text-xs sm:text-sm" data-testid="rooms-settings-tab">
                <DoorOpen className="w-4 h-4" /> Oda Yönetimi
              </TabsTrigger>}
            {isAdmin && <TabsTrigger value="b2b" className="flex items-center gap-1.5 text-xs sm:text-sm" data-testid="b2b-settings-tab">
                <Plug className="w-4 h-4" /> B2B Entegrasyon
              </TabsTrigger>}
          </TabsList>

          {/* ═══════════ TEAM TAB ═══════════ */}
          <SettingsTeamTab Users={Users} team={team} UserCheck={UserCheck} teamMeta={teamMeta} Shield={Shield} Crown={Crown} setActiveTab={setActiveTab} setNewMember={setNewMember} setShowAddModal={setShowAddModal} teamLoading={teamLoading} getRoleLabel={getRoleLabel} isSameUser={isSameUser} handleUpdateRole={handleUpdateRole} handleRemoveMember={handleRemoveMember} isAdmin={isAdmin} grLoading={grLoading} grSettings={grSettings} toggleGuestRequestRole={toggleGuestRequestRole} saveGuestRequestSettings={saveGuestRequestSettings} grSaving={grSaving} />

          {/* ═══════════ PLAN TAB ═══════════ */}
          <SettingsPlanTab currentPlan={currentPlan} subscription={subscription} fmtPlanPrice={fmtPlanPrice} CheckCircle2={CheckCircle2} upgradeTiers={upgradeTiers} PLANS={PLANS} openPlanModal={openPlanModal} downgradeTiers={downgradeTiers} currentTier={currentTier} />

          {/* ═══════════ BILLING HISTORY TAB ═══════════ */}
          <SettingsBillingTab loadBillingHistory={loadBillingHistory} billingLoading={billingLoading} billingHistory={billingHistory} setActiveTab={setActiveTab} PLANS={PLANS} formatCurrency={formatCurrency} />

          {/* ═══════════ HOTEL INFO TAB ═══════════ */}
          <SettingsHotelTab editMode={editMode} setEditMode={setEditMode} setHotelForm={setHotelForm} tenant={tenant} handleSaveHotelInfo={handleSaveHotelInfo} hotelSaving={hotelSaving} overRoomLimit={overRoomLimit} hotelForm={hotelForm} parseInt={parseInt} currentPlan={currentPlan} subscription={subscription} />

          {/* ═══════════ INVOICE SETTINGS TAB ═══════════ */}
          <SettingsInvoiceTab loadInvoiceSettings={loadInvoiceSettings} invoiceLoading={invoiceLoading} handleSaveInvoiceSettings={handleSaveInvoiceSettings} invoiceSaving={invoiceSaving} invoiceSettings={invoiceSettings} setInvoiceSettings={setInvoiceSettings} handleLogoUpload={handleLogoUpload} CURRENCY_OPTIONS={CURRENCY_OPTIONS} />

          {/* ═══════════ ROOMS MANAGEMENT TAB (super_admin only) ═══════════ */}
          {isSuperAdmin && <SettingsRoomsTab loadRooms={loadRooms} roomsLoading={roomsLoading} setShowBulkRoomsDialog={setShowBulkRoomsDialog} isSuperAdmin={isSuperAdmin} setShowAddRoomDialog={setShowAddRoomDialog} roomsList={roomsList} handleDeleteRoom={handleDeleteRoom} />}

          {/* ═══════════ B2B ENTEGRASYON TAB ═══════════ */}
          {isAdmin && <SettingsB2bTab b2bInfo={b2bInfo} copyToClipboard={copyToClipboard} b2bCodeOnce={b2bCodeOnce} setB2bCodeOnce={setB2bCodeOnce} handleRegenerateCode={handleRegenerateCode} b2bBusy={b2bBusy} loadB2B={loadB2B} b2bLoading={b2bLoading} b2bRequests={b2bRequests} handleApproveRequest={handleApproveRequest} handleRejectRequest={handleRejectRequest} />}
        </Tabs>
      </div>

      {/* ─── Add Member Modal ─────────────────────── */}
      <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><Plus className="w-5 h-5" /> Ekip Üyesi Ekle</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>İsim *</Label><Input value={newMember.name} onChange={e => setNewMember({
              ...newMember,
              name: e.target.value
            })} placeholder="Ahmet Yılmaz" /></div>
            <div><Label>{t('common.email')} *</Label><Input type="email" value={newMember.email} onChange={e => setNewMember({
              ...newMember,
              email: e.target.value
            })} placeholder={t('auth.emailPlaceholder')} /></div>
            <div><Label>Telefon</Label><Input value={newMember.phone} onChange={e => setNewMember({
              ...newMember,
              phone: e.target.value
            })} placeholder="+905551234567" /></div>
            <div>
              <Label>Şifre *</Label>
              <Input type="password" value={newMember.password} onChange={e => setNewMember({
              ...newMember,
              password: e.target.value
            })} placeholder="Min 6 karakter" />
              {newMember.password && newMember.password.length < 6 && <p className="text-[11px] text-rose-600 mt-1">Şifre en az 6 karakter olmalıdır</p>}
            </div>
            <div>
              <Label>Rol</Label>
              <Select value={newMember.role} onValueChange={v => setNewMember({
              ...newMember,
              role: v
            })}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {teamMeta.allowed_roles.map(r => <SelectItem key={r} value={r}>{getRoleLabel(r).label}</SelectItem>)}
                </SelectContent>
              </Select>
              {teamMeta.tier === 'basic' && <p className="text-[11px] text-amber-700 mt-1">Basic planda sadece Yönetici rolü kullanılabilir</p>}
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowAddModal(false)}>{t("common.cancel")}</Button>
              <Button onClick={handleAddMember} disabled={saving}>{saving ? 'Ekleniyor...' : 'Ekle'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* ─── Plan Change Modal (Upgrade / Downgrade) ─── */}
      <Dialog open={showPlanModal} onOpenChange={setShowPlanModal}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {planAction === 'upgrade' ? <Sparkles className="w-5 h-5 text-amber-500" /> : <ArrowDown className="w-5 h-5 text-amber-500" />}
              {planAction === 'upgrade' ? 'Plan Yükselt' : 'Plan Düşür'}
            </DialogTitle>
          </DialogHeader>
          {selectedPlan && PLANS[selectedPlan] && (() => {
          const plan = PLANS[selectedPlan];
          const Icon = plan.icon;
          const priceEUR = billingCycle === 'yearly' ? plan.priceYearlyEUR : plan.priceEUR;
          const period = billingCycle === 'yearly' ? '/yıl' : '/ay';
          const isDowngrade = planAction === 'downgrade';
          return <div className="space-y-4">
                <div className={`p-4 rounded-xl ${plan.lightBg} border ${plan.borderColor}`}>
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-xl ${plan.iconBg} ${plan.iconText}`}><Icon className="w-6 h-6" /></div>
                    <div><h3 className="font-bold text-lg">{plan.label}</h3><p className="text-xs text-slate-500">{plan.description}</p></div>
                  </div>
                </div>

                {isDowngrade && <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 flex items-start gap-2">
                    <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-amber-800">Plan düşürme uyarısı</p>
                      <p className="text-xs text-amber-700 mt-0.5">
                        Mevcut planınıza ait modüller devre dışı kalacaktır. Oda ve kullanıcı sayınız yeni plan limitlerini aşıyorsa düşürme yapılamaz.
                      </p>
                    </div>
                  </div>}

                <div className="flex items-center justify-center gap-3 p-3 bg-slate-50 rounded-lg">
                  <button type="button" className={`px-4 py-2 rounded-lg text-sm font-medium transition ${billingCycle === 'monthly' ? 'bg-white shadow text-slate-900' : 'text-slate-500'}`} onClick={() => setBillingCycle('monthly')}>Aylık</button>
                  <button type="button" className={`px-4 py-2 rounded-lg text-sm font-medium transition ${billingCycle === 'yearly' ? 'bg-white shadow text-slate-900' : 'text-slate-500'}`} onClick={() => setBillingCycle('yearly')}>
                    Yıllık <span className="ml-1 text-[10px] text-emerald-600 font-bold">2 AY ÜCRETSİZ</span>
                  </button>
                </div>

                <div className="text-center py-2"><p className="text-4xl font-bold text-slate-900">{fmtPlanPrice(priceEUR)}</p><p className="text-sm text-slate-500">{period}</p></div>

                <ul className="space-y-1.5 max-h-40 overflow-y-auto">
                  {plan.features.map((f, i) => <li key={f.id || i} className="flex items-center gap-2 text-sm text-slate-700"><CheckCircle2 className="w-4 h-4 text-emerald-500 flex-shrink-0" />{f}</li>)}
                </ul>

                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="outline" onClick={() => setShowPlanModal(false)}>{t("common.cancel")}</Button>
                  <Button onClick={handleChangePlan} disabled={saving}>
                    {saving ? 'İşleniyor...' : isDowngrade ? `${plan.label} Plana Düşür` : `${plan.label} Plana Yükselt`}
                  </Button>
                </div>
              </div>;
        })()}
        </DialogContent>
      </Dialog>

      {/* ─── Add Single Room Modal (super_admin) ─── */}
      <Dialog open={showAddRoomDialog} onOpenChange={setShowAddRoomDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><DoorOpen className="w-5 h-5" /> Yeni Oda Ekle</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateRoom} className="space-y-3">
            <div>
              <Label>Oda Numarası *</Label>
              <Input value={newRoom.room_number} onChange={e => setNewRoom({
              ...newRoom,
              room_number: e.target.value
            })} placeholder="101" required data-testid="new-room-number" />
            </div>
            <div>
              <Label>Oda Tipi</Label>
              <Select value={newRoom.room_type} onValueChange={v => setNewRoom({
              ...newRoom,
              room_type: v
            })}>
                <SelectTrigger data-testid="new-room-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="standard">Standard</SelectItem>
                  <SelectItem value="deluxe">Deluxe</SelectItem>
                  <SelectItem value="suite">Suite</SelectItem>
                  <SelectItem value="presidential">Presidential</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Kat</Label>
                <Input type="number" min={0} value={newRoom.floor} onChange={e => setNewRoom({
                ...newRoom,
                floor: parseInt(e.target.value) || 0
              })} required />
              </div>
              <div>
                <Label>Kapasite</Label>
                <Input type="number" min={1} value={newRoom.capacity} onChange={e => setNewRoom({
                ...newRoom,
                capacity: parseInt(e.target.value) || 1
              })} required />
              </div>
            </div>
            <div>
              <Label>Taban Fiyat</Label>
              <Input type="number" min={0} step="0.01" value={newRoom.base_price} onChange={e => setNewRoom({
              ...newRoom,
              base_price: parseFloat(e.target.value) || 0
            })} required />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={() => setShowAddRoomDialog(false)}>İptal</Button>
              <Button type="submit" disabled={roomSaving} data-testid="create-room-submit">{roomSaving ? 'Oluşturuluyor...' : 'Oda Oluştur'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* ─── Bulk Rooms Dialog (super_admin) ─── */}
      <BulkRoomsDialog open={showBulkRoomsDialog} onClose={() => setShowBulkRoomsDialog(false)} onRoomsCreated={loadRooms} user={user} />
    </>;
};
export default Settings;