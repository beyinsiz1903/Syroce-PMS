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
import {
  Settings as SettingsIcon, Users, CreditCard, Shield, Plus, Trash2,
  Building2, Zap, Crown, ArrowRight, CheckCircle2, Lock, AlertTriangle,
  ArrowDown, Sparkles, Clock, Receipt, Save, Pencil, X, FileText, Upload, Image,
  DoorOpen, RefreshCw, Infinity as InfinityIcon, UserCheck, MessageSquare,
  KeyRound, Copy, Plug
} from 'lucide-react';
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

// ─── Plan Config (Sprint A: gradient/blue/green/orange/pink yok) ──────
// Plan ücretleri base EUR cinsinden tutulur (subscription tarafı EUR);
// gösterimde useCurrency.format ile aktif tenant para birimine çevrilir.
const PLAN_CONFIG = {
  basic: {
    key: 'basic', priceEUR: 79, priceYearlyEUR: 790,
    maxRooms: 15, maxUsers: 3,
    icon: Building2,
    iconBg: 'bg-emerald-100', iconText: 'text-emerald-700',
    lightBg: 'bg-emerald-50', borderColor: 'border-emerald-200',
    pillIntent: 'success',
  },
  professional: {
    key: 'professional', priceEUR: 299, priceYearlyEUR: 2990,
    maxRooms: 80, maxUsers: 15,
    icon: Zap,
    iconBg: 'bg-sky-100', iconText: 'text-sky-700',
    lightBg: 'bg-sky-50', borderColor: 'border-sky-200',
    pillIntent: 'info',
  },
  enterprise: {
    key: 'enterprise', priceEUR: 799, priceYearlyEUR: 7990,
    maxRooms: null, maxUsers: null,
    icon: Crown,
    iconBg: 'bg-indigo-100', iconText: 'text-indigo-700',
    lightBg: 'bg-indigo-50', borderColor: 'border-indigo-200',
    pillIntent: 'neutral',
  },
};

// Sprint A intent paleti (indigo/sky/emerald/amber/rose/slate). Pink/violet/teal/cyan/yellow yok.
const ROLE_COLORS = {
  admin:         'bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200',
  super_admin:   'bg-indigo-100 text-indigo-800 ring-1 ring-indigo-300',
  manager:       'bg-sky-50 text-sky-700 ring-1 ring-sky-200',
  supervisor:    'bg-sky-50 text-sky-700 ring-1 ring-sky-200',
  front_desk:    'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
  housekeeping:  'bg-amber-50 text-amber-800 ring-1 ring-amber-200',
  finance:       'bg-slate-100 text-slate-700 ring-1 ring-slate-300',
  procurement:   'bg-amber-50 text-amber-800 ring-1 ring-amber-200',
  sales:         'bg-rose-50 text-rose-700 ring-1 ring-rose-200',
  revenue:       'bg-slate-100 text-slate-700 ring-1 ring-slate-300',
  maintenance:   'bg-slate-100 text-slate-700 ring-1 ring-slate-300',
  fnb:           'bg-rose-50 text-rose-700 ring-1 ring-rose-200',
  spa:           'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
  concierge:     'bg-sky-50 text-sky-700 ring-1 ring-sky-200',
  night_auditor: 'bg-slate-100 text-slate-700 ring-1 ring-slate-300',
  staff:         'bg-slate-100 text-slate-700 ring-1 ring-slate-300',
};

// Para birimi i18n etiketleri için yardımcı (UI tarafında gösterilen ad).
const CURRENCY_OPTIONS = [
  { code: 'TRY', label: 'currencyName.TRY', fallback: 'Türk Lirası', sym: '₺' },
  { code: 'EUR', label: 'currencyName.EUR', fallback: 'Euro',         sym: '€' },
  { code: 'USD', label: 'currencyName.USD', fallback: 'ABD Doları',   sym: '$' },
  { code: 'GBP', label: 'currencyName.GBP', fallback: 'İngiliz Sterlini', sym: '£' },
];

const Settings = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const { code: currencyCode, format: formatCurrencyTenant, refresh: refreshCurrency } = useCurrency();

  const getRoleLabel = useCallback((role) => ({
    label: t(`settings.roles.${role}`) || role,
    color: ROLE_COLORS[role] || 'bg-slate-100 text-slate-700 ring-1 ring-slate-300',
  }), [t]);

  const PLANS = useMemo(() => ({
    basic: {
      ...PLAN_CONFIG.basic,
      label: t('settings.basic'),
      features: ['PMS Core', t('calendar.title'), 'Dashboard', t('guest.title'), t('housekeeping.title'), t('reports.title'), t('mobile.title'), t('invoice.title')],
      description: t('settings.basic') + ' - ' + (PLAN_CONFIG.basic.maxRooms ? `1-${PLAN_CONFIG.basic.maxRooms} ${t('common.rooms')}` : ''),
    },
    professional: {
      ...PLAN_CONFIG.professional,
      label: t('settings.professional'),
      features: [t('settings.basic') + ' +', 'Channel Manager', t('folio.title'), t('nightAudit.title'), t('finance.title'), t('dashboard.costManagement'), t('reports.title'), 'Rate Management', 'Booking Engine'],
      description: t('settings.professional') + ' - ' + (PLAN_CONFIG.professional.maxRooms ? `15-${PLAN_CONFIG.professional.maxRooms} ${t('common.rooms')}` : ''),
    },
    enterprise: {
      ...PLAN_CONFIG.enterprise,
      label: t('settings.enterprise'),
      features: [t('settings.professional') + ' +', 'Revenue Management (RMS)', t('aiModule.title'), t('dashboard.multiProperty'), t('dashboard.groupSales'), t('dashboard.salesCRM'), t('loyalty.title'), 'GM Dashboard', 'API', 'White Label', 'Audit Trail'],
      description: t('settings.enterprise') + ' - 80+ ' + t('common.rooms'),
    },
  }), [t]);

  // Plan değişimi sonrası activeTab'ı koru (window.location.reload state kaybını önler).
  const [activeTab, setActiveTab] = useState(() => {
    try {
      const saved = sessionStorage.getItem('settings:activeTab');
      if (saved) sessionStorage.removeItem('settings:activeTab');
      return saved || 'team';
    } catch { return 'team'; }
  });

  // B2B Connect (Seçenek B — acente oto-saglama)
  const [b2bInfo, setB2bInfo] = useState(null);
  const [b2bRequests, setB2bRequests] = useState([]);
  const [b2bLoading, setB2bLoading] = useState(false);
  const [b2bCodeOnce, setB2bCodeOnce] = useState('');   // ham kod yalniz 1 kez
  const [b2bBusy, setB2bBusy] = useState(false);

  // Team
  const [team, setTeam] = useState([]);
  const [teamLoading, setTeamLoading] = useState(true);
  const [teamMeta, setTeamMeta] = useState({ tier: 'basic', allowed_roles: ['admin'], max_users: 3, can_add: true });
  const [showAddModal, setShowAddModal] = useState(false);
  const [newMember, setNewMember] = useState({ email: '', name: '', phone: '', role: 'admin', password: '' });
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
  const isSuperAdmin = user?.role === 'super_admin' || (Array.isArray(user?.roles) && user.roles.includes('super_admin'));
  // Misafir Talepleri görünürlük ayarı: admin + super_admin yapılandırabilir.
  const isAdmin = isSuperAdmin || user?.role === 'admin' || (Array.isArray(user?.roles) && user.roles.includes('admin'));
  const [roomsList, setRoomsList] = useState([]);
  const [roomsLoading, setRoomsLoading] = useState(false);
  const [showBulkRoomsDialog, setShowBulkRoomsDialog] = useState(false);
  const [showAddRoomDialog, setShowAddRoomDialog] = useState(false);
  const [newRoom, setNewRoom] = useState({ room_number: '', room_type: 'standard', floor: 1, capacity: 2, base_price: 100 });
  const [roomSaving, setRoomSaving] = useState(false);

  // Misafir Talepleri görünürlüğü (admin)
  const [grSettings, setGrSettings] = useState({ visible_roles: [], available_roles: [], always_allowed: [] });
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
  const fmtPlanPrice = useCallback((eurAmount) => {
    if (!Number.isFinite(eurAmount)) return '—';
    if (currencyCode === 'EUR') return formatCurrency(eurAmount, 'EUR', { decimals: 0 });
    // Plan ücretleri sözleşme gereği EUR; tenant TRY ise tenant biriminde
    // göstermek yerine "EUR" işaretiyle dönmek daha doğru (FX dönüşüm yok).
    try {
      return formatCurrencyTenant
        ? `${formatCurrency(eurAmount, 'EUR', { decimals: 0 })}`
        : `${eurAmount}€`;
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
        can_add: res.data?.can_add !== false,
      });
    } catch (err) {
      console.error('Team load failed', err);
      toast.error(err?.response?.data?.detail || 'Ekip listesi alınamadı');
    } finally { setTeamLoading(false); }
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
    } finally { setBillingLoading(false); }
  }, []);

  const loadInvoiceSettings = useCallback(async () => {
    setInvoiceLoading(true);
    try {
      const res = await axios.get('/pms/hotel-settings');
      setInvoiceSettings(res.data || {});
    } catch (err) {
      console.error('Invoice settings load failed', err);
      toast.error(err?.response?.data?.detail || 'Fatura ayarları alınamadı');
    } finally { setInvoiceLoading(false); }
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
    } finally { setRoomsLoading(false); }
  }, [isSuperAdmin]);

  const loadB2B = useCallback(async () => {
    if (!isAdmin) return;
    setB2bLoading(true);
    try {
      const [infoRes, reqRes] = await Promise.all([
        axios.get('/b2b/connect-info'),
        axios.get('/b2b/connect-requests'),
      ]);
      setB2bInfo(infoRes.data || null);
      setB2bRequests(reqRes.data?.items || []);
    } catch (err) {
      console.error('B2B load failed', err);
      toast.error(err?.response?.data?.detail || 'B2B bilgileri alınamadı');
    } finally { setB2bLoading(false); }
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
    if (b2bInfo?.has_active_code && !await confirmDialog({
      message: 'Yeni bağlantı kodu üretilsin mi? Eski kod geçersiz olur; bağlı acentelerin yeni kodla güncellenmesi gerekir.',
      variant: 'danger',
    })) return;
    setB2bBusy(true);
    try {
      const res = await axios.post('/b2b/connect-codes/regenerate');
      setB2bCodeOnce(res.data?.connect_code || '');
      toast.success('Bağlantı kodu üretildi. Yalnızca bir kez gösterilir.');
      await loadB2B();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Kod üretilemedi');
    } finally { setB2bBusy(false); }
  }, [b2bInfo, loadB2B]);

  const handleApproveRequest = useCallback(async (req) => {
    if (!await confirmDialog({
      message: `"${req.agency_name}" bağlantısı onaylansın mı? Onayda bu acenteye API key üretilecek.`,
    })) return;
    setB2bBusy(true);
    try {
      const res = await axios.post(`/b2b/connect-requests/${req.id}/approve`);
      toast.success(res.data?.message || 'İstek onaylandı');
      await loadB2B();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Onaylanamadı');
    } finally { setB2bBusy(false); }
  }, [loadB2B]);

  const handleRejectRequest = useCallback(async (req) => {
    if (!await confirmDialog({
      message: `"${req.agency_name}" bağlantı isteği reddedilsin mi?`,
      variant: 'danger',
    })) return;
    setB2bBusy(true);
    try {
      await axios.post(`/b2b/connect-requests/${req.id}/reject`, { reason: '' });
      toast.success('İstek reddedildi');
      await loadB2B();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Reddedilemedi');
    } finally { setB2bBusy(false); }
  }, [loadB2B]);

  const loadGuestRequestSettings = useCallback(async () => {
    if (!isAdmin) return;
    setGrLoading(true);
    try {
      const res = await axios.get('/messaging/guest-requests/settings');
      setGrSettings({
        visible_roles: res.data?.visible_roles || [],
        available_roles: res.data?.available_roles || [],
        always_allowed: res.data?.always_allowed || [],
      });
    } catch (err) {
      console.error('Guest request settings load failed', err);
      toast.error(err?.response?.data?.detail || 'Misafir talep ayarları alınamadı');
    } finally { setGrLoading(false); }
  }, [isAdmin]);

  const toggleGuestRequestRole = useCallback((role, checked) => {
    setGrSettings((prev) => {
      const set = new Set(prev.visible_roles);
      if (checked) set.add(role); else set.delete(role);
      return { ...prev, visible_roles: Array.from(set) };
    });
  }, []);

  const saveGuestRequestSettings = useCallback(async () => {
    setGrSaving(true);
    try {
      const res = await axios.put('/messaging/guest-requests/settings', {
        visible_roles: grSettings.visible_roles,
      });
      setGrSettings((prev) => ({ ...prev, visible_roles: res.data?.visible_roles || prev.visible_roles }));
      toast.success('Misafir talep görünürlüğü kaydedildi');
    } catch (err) {
      console.error('Guest request settings save failed', err);
      toast.error(err?.response?.data?.detail || 'Ayar kaydedilemedi');
    } finally { setGrSaving(false); }
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
        total_rooms: tenant.total_rooms || 0,
      });
    }
  }, [tenant]);

  // ─── Self check (id veya _id eşleşmesi) ───────
  const isSameUser = useCallback((member) => {
    if (!user) return false;
    const ids = [user.id, user._id].filter(Boolean);
    return ids.includes(member.id) || ids.includes(member._id);
  }, [user]);

  // ─── Team Handlers ─────────────────────────────
  const handleAddMember = async () => {
    if (!newMember.email || !newMember.name || !newMember.password) {
      toast.error('Email, isim ve şifre zorunludur'); return;
    }
    if (newMember.password.length < 6) {
      toast.error('Şifre en az 6 karakter olmalıdır'); return;
    }
    setSaving(true);
    try {
      const res = await axios.post('/hotel/team', newMember);
      toast.success(res.data?.message || 'Ekip üyesi eklendi');
      setShowAddModal(false);
      setNewMember({ email: '', name: '', phone: '', role: teamMeta.allowed_roles[0] || 'admin', password: '' });
      await loadTeam();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Ekip üyesi eklenemedi');
    } finally { setSaving(false); }
  };

  const handleUpdateRole = async (userId, newRole) => {
    try {
      await axios.patch(`/hotel/team/${userId}/role`, { role: newRole });
      toast.success('Rol güncellendi');
      await loadTeam();
    } catch (err) { toast.error(err.response?.data?.detail || 'Rol güncellenemedi'); }
  };

  const handleRemoveMember = async (userId, name) => {
    if (!await confirmDialog({ message: `${name} adlı kullanıcıyı silmek istediğinize emin misiniz?`, variant: 'danger' })) return;
    try {
      await axios.delete(`/hotel/team/${userId}`);
      toast.success('Ekip üyesi silindi');
      await loadTeam();
    } catch (err) { toast.error(err.response?.data?.detail || 'Silinemedi'); }
  };

  // ─── Plan Change Handler ───────────────────────
  const handleChangePlan = async () => {
    if (!selectedPlan) return;
    setSaving(true);
    try {
      const res = await axios.post('/subscription/change-plan', {
        new_tier: selectedPlan,
        billing_cycle: billingCycle,
      });
      toast.success(res.data?.message || 'Plan güncellendi');
      setShowPlanModal(false);
      // Modüller App.jsx mount'unda yükleniyor; aktif tab'ı koruyup soft reload.
      try { sessionStorage.setItem('settings:activeTab', activeTab); } catch { /* ignore */ }
      await Promise.all([loadSubscription(), loadBillingHistory(), loadTeam()]);
      setTimeout(() => window.location.reload(), 600);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Plan değiştirilemedi');
    } finally { setSaving(false); }
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
          const merged = { ...stored, ...updatedTenant };
          localStorage.setItem('tenant', JSON.stringify(merged));
        } catch { /* ignore */ }
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Güncellenemedi');
    } finally { setHotelSaving(false); }
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
        currency_symbol: symLookup?.sym || codeUpper,
      };
      const res = await axios.put('/pms/hotel-settings', payload);
      toast.success('Fatura ayarları kaydedildi');
      setInvoiceSettings(res.data?.settings || payload);
      try { await refreshCurrency(); } catch { /* ignore */ }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Kaydedilemedi');
    } finally { setInvoiceSaving(false); }
  };

  const handleLogoUpload = (e) => {
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
    reader.onload = (event) => {
      // Boyut/dimension doğrulama: çok büyük çözünürlüklerde uyar.
      const dataUrl = event.target.result;
      const probe = new window.Image();
      probe.onload = () => {
        if (probe.width > 2000 || probe.height > 2000) {
          toast.error('Logo en fazla 2000×2000 piksel olabilir.');
          return;
        }
        setInvoiceSettings(prev => ({ ...prev, logo_data: dataUrl }));
      };
      probe.onerror = () => toast.error('Logo görseli okunamadı.');
      probe.src = dataUrl;
    };
    reader.onerror = () => toast.error('Dosya okunamadı.');
    reader.readAsDataURL(file);
  };

  // Room CRUD (super_admin)
  const handleCreateRoom = async (e) => {
    e.preventDefault();
    if (!newRoom.room_number?.toString().trim()) {
      toast.error('Oda numarası zorunludur'); return;
    }
    if (!Number.isFinite(newRoom.floor) || newRoom.floor < 0) {
      toast.error('Kat negatif olamaz'); return;
    }
    if (!Number.isFinite(newRoom.capacity) || newRoom.capacity < 1) {
      toast.error('Kapasite en az 1 olmalıdır'); return;
    }
    if (!Number.isFinite(newRoom.base_price) || newRoom.base_price < 0) {
      toast.error('Taban fiyat negatif olamaz'); return;
    }
    setRoomSaving(true);
    try {
      await axios.post('/pms/rooms', newRoom);
      toast.success('Oda oluşturuldu');
      setShowAddRoomDialog(false);
      setNewRoom({ room_number: '', room_type: 'standard', floor: 1, capacity: 2, base_price: 100 });
      loadRooms();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Oda oluşturulamadı');
    } finally { setRoomSaving(false); }
  };

  const handleDeleteRoom = async (roomId, roomNumber) => {
    if (!await confirmDialog({ message: `${roomNumber} numaralı odayı silmek istediğinize emin misiniz?`, variant: 'danger' })) return;
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
    if (activeTab === 'team') loadTeam();
    else if (activeTab === 'plan') loadSubscription();
    else if (activeTab === 'billing') loadBillingHistory();
    else if (activeTab === 'hotel') loadSubscription();
    else if (activeTab === 'invoice') loadInvoiceSettings();
    else if (activeTab === 'rooms') loadRooms();
    else if (activeTab === 'b2b') loadB2B();
  }, [activeTab, loadTeam, loadSubscription, loadBillingHistory, loadInvoiceSettings, loadRooms, loadB2B]);

  const tabBusy = (
    (activeTab === 'team' && teamLoading)
    || (activeTab === 'billing' && billingLoading)
    || (activeTab === 'invoice' && invoiceLoading)
    || (activeTab === 'rooms' && roomsLoading)
  );

  return (
    <>
      <div className="p-4 md:p-6 space-y-4 max-w-6xl mx-auto">
        <PageHeader
          icon={SettingsIcon}
          iconClassName="text-slate-700"
          title="Ayarlar"
          subtitle={t('settings.subtitle')}
          actions={
            <>
              <StatusBadge intent={currentPlan.pillIntent || 'neutral'} icon={PlanIcon}>
                {currentPlan.label}
              </StatusBadge>
              <Button variant="outline" size="sm" onClick={refreshActiveTab} disabled={tabBusy}>
                <RefreshCw className={`w-4 h-4 mr-1.5 ${tabBusy ? 'animate-spin' : ''}`} />
                Yenile
              </Button>
            </>
          }
        />

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
            {isSuperAdmin && (
              <TabsTrigger value="rooms" className="flex items-center gap-1.5 text-xs sm:text-sm" data-testid="rooms-settings-tab">
                <DoorOpen className="w-4 h-4" /> Oda Yönetimi
              </TabsTrigger>
            )}
            {isAdmin && (
              <TabsTrigger value="b2b" className="flex items-center gap-1.5 text-xs sm:text-sm" data-testid="b2b-settings-tab">
                <Plug className="w-4 h-4" /> B2B Entegrasyon
              </TabsTrigger>
            )}
          </TabsList>

          {/* ═══════════ TEAM TAB ═══════════ */}
          <TabsContent value="team" className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <KpiCard icon={Users} label="Toplam Üye" value={team.length} intent="default" />
              <KpiCard
                icon={UserCheck}
                label="Max Kullanıcı"
                value={teamMeta.max_users === 999 ? '∞' : teamMeta.max_users}
                intent="info"
              />
              <KpiCard icon={Shield} label="Kullanılabilir Rol" value={teamMeta.allowed_roles.length} intent="success" />
              <KpiCard icon={Crown} label="Plan" value={<span className="capitalize">{teamMeta.tier}</span>} intent="neutral" />
            </div>

            {teamMeta.tier === 'basic' && (
              <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-amber-800">Basic planda sadece "Yönetici" rolü kullanılabilir</p>
                  <p className="text-xs text-amber-700 mt-0.5">Departman rolleri için Professional plana yükseltin.</p>
                  <button onClick={() => setActiveTab('plan')} className="text-xs font-bold text-amber-800 mt-1 hover:underline flex items-center gap-1">Planı yükselt <ArrowRight className="w-3 h-3" /></button>
                </div>
              </div>
            )}

            <div className="flex justify-between items-center">
              <h2 className="text-lg font-semibold">{t('settings.teamMembers')}</h2>
              <Button size="sm" onClick={() => { setNewMember({ email: '', name: '', phone: '', role: teamMeta.allowed_roles[0] || 'admin', password: '' }); setShowAddModal(true); }} disabled={!teamMeta.can_add}>
                <Plus className="w-4 h-4 mr-1" /> Üye Ekle {!teamMeta.can_add && <Lock className="w-3 h-3 ml-1" />}
              </Button>
            </div>

            {!teamMeta.can_add && (
              <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-sm text-rose-700">
                Kullanıcı limitine ulaşıldı ({teamMeta.max_users}). Planınızı yükseltin.
              </div>
            )}

            <Card>
              <CardContent className="p-0">
                {teamLoading ? (
                  <div className="p-8 text-center text-slate-400">{t("common.loading")}</div>
                ) : team.length === 0 ? (
                  <div className="p-8 text-center text-slate-400">Henüz ekip üyesi yok</div>
                ) : (
                  <div className="divide-y">
                    {team.map((member) => {
                      const roleInfo = getRoleLabel(member.role);
                      const isMe = isSameUser(member);
                      const editDisabled = isMe || member.role === 'super_admin';
                      const allowedForSelect = teamMeta.allowed_roles.includes(member.role)
                        ? teamMeta.allowed_roles
                        : [...teamMeta.allowed_roles, member.role];
                      return (
                        <div key={member.id} className="flex items-center justify-between px-4 py-3 hover:bg-slate-50">
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="w-9 h-9 rounded-full bg-slate-200 flex items-center justify-center text-sm font-bold text-slate-600">
                              {(member.name || '?')[0].toUpperCase()}
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-medium text-slate-900 truncate">{member.name}</span>
                                {isMe && <StatusBadge intent="info">Siz</StatusBadge>}
                              </div>
                              <span className="text-xs text-slate-500">{member.email}</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            {member.role === 'super_admin' ? (
                              <StatusBadge intent="neutral" icon={Crown}>Super Admin</StatusBadge>
                            ) : (
                              <Select
                                value={member.role}
                                onValueChange={(v) => handleUpdateRole(member.id, v)}
                                disabled={editDisabled}
                              >
                                <SelectTrigger
                                  className={`h-8 w-[160px] text-xs font-medium ${roleInfo.color} disabled:opacity-60 disabled:cursor-not-allowed`}
                                >
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  {allowedForSelect.map((r) => (
                                    <SelectItem key={r} value={r}>{getRoleLabel(r).label}</SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            )}
                            {!isMe && member.role !== 'super_admin' && (
                              <Button variant="ghost" size="sm" className="text-rose-500 hover:text-rose-700 hover:bg-rose-50 p-1" onClick={() => handleRemoveMember(member.id, member.name)}>
                                <Trash2 className="w-4 h-4" />
                              </Button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><Shield className="w-4 h-4" /> Kullanılabilir Roller ({teamMeta.tier})</CardTitle></CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {teamMeta.allowed_roles.map((r) => {
                    const info = getRoleLabel(r);
                    return <span key={r} className={`text-xs px-2.5 py-1 rounded-full ${info.color} font-medium`}>{info.label}</span>;
                  })}
                </div>
                {teamMeta.tier !== 'enterprise' && <p className="text-[11px] text-slate-500 mt-2">Daha fazla rol için {teamMeta.tier === 'basic' ? 'Professional' : 'Enterprise'} plana yükseltin</p>}
              </CardContent>
            </Card>

            {isAdmin && (
              <Card data-testid="guest-request-visibility-card">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <MessageSquare className="w-4 h-4" /> Misafir Talepleri Görünürlüğü
                  </CardTitle>
                  <CardDescription>
                    Oda QR taleplerini personel sohbetinde hangi rollerin göreceğini seçin. Yönetici rolleri her zaman görür.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {grLoading ? (
                    <div className="text-sm text-slate-400">{t('common.loading')}</div>
                  ) : grSettings.available_roles.length === 0 ? (
                    <div className="text-sm text-slate-400">Seçilebilir rol bulunamadı</div>
                  ) : (
                    <>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {grSettings.available_roles.map((r) => {
                          const always = grSettings.always_allowed.includes(r.value);
                          const checked = always || grSettings.visible_roles.includes(r.value);
                          return (
                            <label
                              key={r.value}
                              className={`flex items-center gap-2.5 p-2.5 rounded-lg border ${checked ? 'border-slate-300 bg-slate-50' : 'border-slate-200'} ${always ? 'opacity-70 cursor-not-allowed' : 'cursor-pointer hover:bg-slate-50'}`}
                            >
                              <Checkbox
                                checked={checked}
                                disabled={always}
                                onCheckedChange={(v) => toggleGuestRequestRole(r.value, v === true)}
                                data-testid={`gr-role-${r.value}`}
                              />
                              <span className="text-sm font-medium text-slate-800">{r.label}</span>
                              {always && <span className="text-[11px] text-slate-500 ml-auto">Her zaman</span>}
                            </label>
                          );
                        })}
                      </div>
                      <div className="flex justify-end">
                        <Button size="sm" onClick={saveGuestRequestSettings} disabled={grSaving} data-testid="button-save-gr-visibility">
                          {grSaving ? <RefreshCw className="w-4 h-4 mr-1.5 animate-spin" /> : <Save className="w-4 h-4 mr-1.5" />}
                          Kaydet
                        </Button>
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* ═══════════ PLAN TAB ═══════════ */}
          <TabsContent value="plan" className="space-y-4">
            {/* Current plan */}
            <Card className={`border-2 ${currentPlan.borderColor}`}>
              <CardContent className="p-6">
                <div className="flex items-center justify-between flex-wrap gap-4">
                  <div className="flex items-center gap-4">
                    <div className={`p-3 rounded-2xl ${currentPlan.iconBg} ${currentPlan.iconText}`}><PlanIcon className="w-8 h-8" /></div>
                    <div>
                      <h3 className="text-xl font-bold text-slate-900">{currentPlan.label} Plan</h3>
                      <p className="text-sm text-slate-500">{currentPlan.description}</p>
                      <div className="flex items-center gap-4 mt-2 text-sm">
                        <span className="text-slate-600"><strong>{subscription?.rooms_count || 0}</strong> / {currentPlan.maxRooms || '∞'} oda</span>
                        <span className="text-slate-600"><strong>{subscription?.users_count || 0}</strong> / {currentPlan.maxUsers || '∞'} kullanıcı</span>
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-3xl font-bold text-slate-900">{fmtPlanPrice(currentPlan.priceEUR)}</p>
                    <p className="text-xs text-slate-500">/ ay</p>
                    {subscription?.status && (
                      <div className="mt-1">
                        <StatusBadge
                          intent={subscription.status === 'active' ? 'success' : 'danger'}
                          icon={CheckCircle2}
                        >
                          {subscription.status === 'active' ? 'Aktif' : subscription.status}
                        </StatusBadge>
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Upgrade options */}
            {upgradeTiers.length > 0 && (
              <>
                <h2 className="text-lg font-semibold flex items-center gap-2"><Sparkles className="w-5 h-5 text-amber-500" /> Yükselt</h2>
                <div className="grid md:grid-cols-2 gap-4">
                  {upgradeTiers.map((tierKey) => {
                    const plan = PLANS[tierKey]; const Icon = plan.icon;
                    return (
                      <Card key={tierKey} className={`border-2 hover:shadow-lg transition-all cursor-pointer group ${plan.borderColor}`}
                        onClick={() => openPlanModal(tierKey, 'upgrade')}>
                        <CardContent className="p-5">
                          <div className="flex items-start justify-between mb-3">
                            <div className={`p-2.5 rounded-xl ${plan.iconBg} ${plan.iconText}`}><Icon className="w-6 h-6" /></div>
                            <div className="text-right"><p className="text-2xl font-bold text-slate-900">{fmtPlanPrice(plan.priceEUR)}</p><p className="text-[10px] text-slate-500">/ay</p></div>
                          </div>
                          <h3 className="text-lg font-bold text-slate-900">{plan.label}</h3>
                          <p className="text-xs text-slate-500 mb-3">{plan.description}</p>
                          <ul className="space-y-1">
                            {plan.features.slice(0, 5).map((f, i) => (<li key={i} className="flex items-center gap-1.5 text-xs text-slate-600"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />{f}</li>))}
                            {plan.features.length > 5 && <li className="text-xs text-slate-400 pl-5">+{plan.features.length - 5} daha</li>}
                          </ul>
                          <Button
                            type="button"
                            className="mt-4 w-full"
                            onClick={(e) => { e.stopPropagation(); openPlanModal(tierKey, 'upgrade'); }}
                          >
                            Yükselt <ArrowRight className="w-4 h-4 ml-1" />
                          </Button>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              </>
            )}

            {/* Downgrade options */}
            {downgradeTiers.length > 0 && (
              <>
                <h2 className="text-sm font-medium text-slate-500 flex items-center gap-2 mt-6"><ArrowDown className="w-4 h-4" /> Plan Düşür</h2>
                <div className="grid md:grid-cols-2 gap-3">
                  {downgradeTiers.map((tierKey) => {
                    const plan = PLANS[tierKey]; const Icon = plan.icon;
                    return (
                      <Card key={tierKey} className="border border-slate-200 hover:border-slate-300 transition cursor-pointer"
                        onClick={() => openPlanModal(tierKey, 'downgrade')}>
                        <CardContent className="p-4 flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <div className={`p-2 rounded-lg ${plan.iconBg}`}><Icon className={`w-5 h-5 ${plan.iconText}`} /></div>
                            <div>
                              <h4 className="text-sm font-semibold text-slate-700">{plan.label}</h4>
                              <p className="text-[11px] text-slate-500">{fmtPlanPrice(plan.priceEUR)}/ay • {plan.description}</p>
                            </div>
                          </div>
                          <Button variant="outline" size="sm" className="text-xs text-slate-600">
                            <ArrowDown className="w-3 h-3 mr-1" /> Düşür
                          </Button>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              </>
            )}

            {/* Current features */}
            <Card>
              <CardHeader><CardTitle className="text-sm">{t('settings.planFeatures')}</CardTitle></CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                  {currentPlan.features.map((f, i) => (<div key={i} className="flex items-center gap-2 text-sm text-slate-700"><CheckCircle2 className="w-4 h-4 text-emerald-500 flex-shrink-0" />{f}</div>))}
                </div>
              </CardContent>
            </Card>

            {currentTier === 'enterprise' && (
              <div className="p-4 rounded-xl bg-indigo-50 border border-indigo-200 text-center">
                <Crown className="w-8 h-8 text-indigo-600 mx-auto mb-2" />
                <p className="text-sm font-bold text-indigo-800">En üst plandasınız!</p>
                <p className="text-xs text-indigo-700">Tüm modüller ve özellikler aktif.</p>
              </div>
            )}
          </TabsContent>

          {/* ═══════════ BILLING HISTORY TAB ═══════════ */}
          <TabsContent value="billing" className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold flex items-center gap-2"><Receipt className="w-5 h-5" /> Fatura & Plan Geçmişi</h2>
              <Button variant="outline" size="sm" onClick={loadBillingHistory} disabled={billingLoading}>
                <RefreshCw className={`w-4 h-4 mr-1.5 ${billingLoading ? 'animate-spin' : ''}`} />
                Yenile
              </Button>
            </div>

            {billingLoading ? (
              <div className="text-center py-12 text-slate-400">{t("common.loading")}</div>
            ) : billingHistory.length === 0 ? (
              <Card>
                <CardContent className="p-12 text-center">
                  <Receipt className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                  <h3 className="text-lg font-semibold text-slate-500">Henüz işlem geçmişi yok</h3>
                  <p className="text-sm text-slate-400 mt-1 mb-4">Plan değişiklikleriniz burada listelenecek</p>
                  <Button variant="outline" size="sm" onClick={() => setActiveTab('plan')}>
                    <CreditCard className="w-4 h-4 mr-1.5" />
                    Plan değiştir
                  </Button>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-3">
                {billingHistory.map((record) => {
                  const isUpgrade = record.action === 'upgrade';
                  const fromPlan = PLANS[record.from_tier];
                  const toPlan = PLANS[record.to_tier];
                  return (
                    <Card key={record.id} className="hover:shadow-sm transition">
                      <CardContent className="p-4">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <div className={`p-2 rounded-lg ${isUpgrade ? 'bg-emerald-100' : 'bg-amber-100'}`}>
                              {isUpgrade ? <ArrowRight className="w-5 h-5 text-emerald-600" /> : <ArrowDown className="w-5 h-5 text-amber-600" />}
                            </div>
                            <div>
                              <div className="flex items-center gap-2 flex-wrap">
                                <StatusBadge intent={isUpgrade ? 'success' : 'warning'}>
                                  {isUpgrade ? 'Yükseltme' : 'Düşürme'}
                                </StatusBadge>
                                <span className="text-sm font-semibold text-slate-900">
                                  {fromPlan?.label || record.from_tier} → {toPlan?.label || record.to_tier}
                                </span>
                              </div>
                              <div className="flex items-center gap-3 mt-1 text-xs text-slate-500 flex-wrap">
                                <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{new Date(record.created_at).toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                                <span>{record.billing_cycle === 'yearly' ? 'Yıllık' : 'Aylık'}</span>
                                {record.user_name && <span>İşlem: {record.user_name}</span>}
                              </div>
                            </div>
                          </div>
                          <div className="text-right">
                            <p className="text-lg font-bold text-slate-900">{formatCurrency(Number(record.amount) || 0, record.currency || 'EUR', { decimals: 0 })}</p>
                            <p className="text-[10px] text-slate-500">{record.billing_cycle === 'yearly' ? 'yıl' : 'ay'}</p>
                            <div className="mt-1">
                              <StatusBadge intent={record.status === 'completed' ? 'success' : 'neutral'}>
                                {record.status === 'completed' ? 'Tamamlandı' : record.status}
                              </StatusBadge>
                            </div>
                          </div>
                        </div>
                        {record.valid_until && (
                          <div className="mt-2 pt-2 border-t text-xs text-slate-500">
                            Geçerlilik: {new Date(record.valid_until).toLocaleDateString('tr-TR')} tarihine kadar
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </TabsContent>

          {/* ═══════════ HOTEL INFO TAB ═══════════ */}
          <TabsContent value="hotel" className="space-y-4">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>{t('settings.hotelInfo')}</CardTitle>
                    <CardDescription>İsim, adres ve iletişim bilgileri</CardDescription>
                  </div>
                  {!editMode ? (
                    <Button variant="outline" size="sm" onClick={() => setEditMode(true)}>
                      <Pencil className="w-4 h-4 mr-1" /> Düzenle
                    </Button>
                  ) : (
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" onClick={() => { setEditMode(false); setHotelForm({ property_name: tenant?.property_name || '', phone: tenant?.phone || tenant?.contact_phone || '', email: tenant?.email || tenant?.contact_email || '', address: tenant?.address || '', location: tenant?.location || '', description: tenant?.description || '', total_rooms: tenant?.total_rooms || 0 }); }}>
                        <X className="w-4 h-4 mr-1" /> İptal
                      </Button>
                      <Button size="sm" onClick={handleSaveHotelInfo} disabled={hotelSaving || overRoomLimit}>
                        <Save className="w-4 h-4 mr-1" /> {hotelSaving ? 'Kaydediyor...' : 'Kaydet'}
                      </Button>
                    </div>
                  )}
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label>Otel Adı</Label>
                  <Input value={hotelForm.property_name || ''} readOnly={!editMode} className={!editMode ? 'bg-slate-50' : ''} onChange={(e) => setHotelForm({ ...hotelForm, property_name: e.target.value })} />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label>Telefon</Label>
                    <Input value={hotelForm.phone || ''} readOnly={!editMode} className={!editMode ? 'bg-slate-50' : ''} onChange={(e) => setHotelForm({ ...hotelForm, phone: e.target.value })} placeholder="+905551234567" />
                  </div>
                  <div>
                    <Label>E-posta</Label>
                    <Input type="email" value={hotelForm.email || ''} readOnly={!editMode} className={!editMode ? 'bg-slate-50' : ''} onChange={(e) => setHotelForm({ ...hotelForm, email: e.target.value })} />
                  </div>
                </div>
                <div>
                  <Label>Adres</Label>
                  <Input value={hotelForm.address || ''} readOnly={!editMode} className={!editMode ? 'bg-slate-50' : ''} onChange={(e) => setHotelForm({ ...hotelForm, address: e.target.value })} />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label>Lokasyon / Şehir</Label>
                    <Input value={hotelForm.location || ''} readOnly={!editMode} className={!editMode ? 'bg-slate-50' : ''} onChange={(e) => setHotelForm({ ...hotelForm, location: e.target.value })} />
                  </div>
                  <div>
                    <Label>Toplam Oda Sayısı</Label>
                    <Input
                      type="number"
                      min={0}
                      value={hotelForm.total_rooms ?? ''}
                      readOnly={!editMode}
                      className={`${!editMode ? 'bg-slate-50' : ''} ${overRoomLimit ? 'border-rose-400 focus-visible:ring-rose-400' : ''}`}
                      onChange={(e) => setHotelForm({ ...hotelForm, total_rooms: parseInt(e.target.value) || 0 })}
                    />
                    {editMode && currentPlan.maxRooms && (
                      <p className={`text-[11px] mt-1 ${overRoomLimit ? 'text-rose-600 font-medium' : 'text-slate-500'}`}>
                        Plan limiti: max {currentPlan.maxRooms} oda
                        {overRoomLimit && ' — Kaydetmek için planı yükseltin.'}
                      </p>
                    )}
                  </div>
                </div>
                <div>
                  <Label>Açıklama</Label>
                  <textarea value={hotelForm.description || ''} readOnly={!editMode} className={`w-full border rounded-md px-3 py-2 text-sm min-h-[80px] ${!editMode ? 'bg-slate-50' : ''} focus:outline-none focus:ring-2 focus:ring-indigo-500`} onChange={(e) => setHotelForm({ ...hotelForm, description: e.target.value })} placeholder="Otel hakkında kısa açıklama..." />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-sm">{t('settings.subscription')}</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-slate-500">Plan</span><span className="font-semibold">{currentPlan.label}</span></div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Durum</span>
                  <StatusBadge intent={subscription?.status === 'active' ? 'success' : 'neutral'}>
                    {subscription?.status === 'active' ? 'Aktif' : (subscription?.status || '—')}
                  </StatusBadge>
                </div>
                <div className="flex justify-between"><span className="text-slate-500">Oda</span><span className="font-semibold">{subscription?.rooms_count || 0} / {currentPlan.maxRooms || '∞'}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Kullanıcı</span><span className="font-semibold">{subscription?.users_count || 0} / {currentPlan.maxUsers || '∞'}</span></div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* ═══════════ INVOICE SETTINGS TAB ═══════════ */}
          <TabsContent value="invoice" className="space-y-4" data-testid="invoice-settings-content">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm flex items-center justify-between">
                  <span className="flex items-center gap-2"><FileText className="w-4 h-4" /> Fatura & Logo Ayarları</span>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={loadInvoiceSettings} disabled={invoiceLoading}>
                      <RefreshCw className={`w-4 h-4 mr-1.5 ${invoiceLoading ? 'animate-spin' : ''}`} /> Yenile
                    </Button>
                    <Button size="sm" onClick={handleSaveInvoiceSettings} disabled={invoiceSaving} data-testid="save-invoice-settings-btn">
                      <Save className="w-4 h-4 mr-1" /> {invoiceSaving ? 'Kaydediliyor...' : 'Kaydet'}
                    </Button>
                  </div>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {invoiceLoading ? (
                  <div className="text-center py-8 text-slate-400">Yükleniyor...</div>
                ) : (
                  <>
                    {/* Logo Upload */}
                    <div>
                      <Label>Otel Logosu</Label>
                      <div className="flex items-center gap-4 mt-2">
                        {invoiceSettings.logo_data ? (
                          <div className="relative">
                            <img src={invoiceSettings.logo_data} alt="Logo" className="h-16 max-w-[200px] object-contain border rounded-lg p-2" />
                            <button
                              type="button"
                              onClick={() => setInvoiceSettings(prev => ({ ...prev, logo_data: null }))}
                              className="absolute -top-2 -right-2 w-5 h-5 bg-rose-500 text-white rounded-full flex items-center justify-center text-xs hover:bg-rose-600"
                              aria-label="Logoyu kaldır"
                            >
                              <X className="w-3 h-3" />
                            </button>
                          </div>
                        ) : (
                          <div className="h-16 w-32 border-2 border-dashed rounded-lg flex items-center justify-center text-slate-400">
                            <Image className="w-6 h-6" />
                          </div>
                        )}
                        <div className="flex flex-col gap-1">
                          <Button asChild variant="outline" size="sm" className="w-fit">
                            <label className="cursor-pointer">
                              <Upload className="w-4 h-4 mr-1.5" /> Logo Yükle
                              <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={handleLogoUpload} data-testid="logo-upload-input" />
                            </label>
                          </Button>
                          <p className="text-[10px] text-slate-500">PNG, JPG, WebP — max 2MB / 2000×2000 px</p>
                        </div>
                      </div>
                    </div>

                    {/* Hotel Info for Invoice */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <Label>Otel Adı (Fatura)</Label>
                        <Input value={invoiceSettings.hotel_name || ''} onChange={e => setInvoiceSettings(prev => ({ ...prev, hotel_name: e.target.value }))} placeholder="Otel adı" />
                      </div>
                      <div>
                        <Label>E-posta</Label>
                        <Input value={invoiceSettings.hotel_email || ''} onChange={e => setInvoiceSettings(prev => ({ ...prev, hotel_email: e.target.value }))} placeholder="info@otel.com" />
                      </div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <Label>Telefon</Label>
                        <Input value={invoiceSettings.hotel_phone || ''} onChange={e => setInvoiceSettings(prev => ({ ...prev, hotel_phone: e.target.value }))} />
                      </div>
                      <div>
                        <Label>Adres</Label>
                        <Input value={invoiceSettings.hotel_address || ''} onChange={e => setInvoiceSettings(prev => ({ ...prev, hotel_address: e.target.value }))} />
                      </div>
                    </div>

                    {/* Tax Info */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <Label>Vergi Numarası</Label>
                        <Input value={invoiceSettings.tax_id || ''} onChange={e => setInvoiceSettings(prev => ({ ...prev, tax_id: e.target.value }))} placeholder="1234567890" data-testid="tax-id-input" />
                      </div>
                      <div>
                        <Label>Vergi Dairesi</Label>
                        <Input value={invoiceSettings.tax_office || ''} onChange={e => setInvoiceSettings(prev => ({ ...prev, tax_office: e.target.value }))} placeholder="Beyoğlu" data-testid="tax-office-input" />
                      </div>
                    </div>

                    {/* Currency — sistem geneli etki taşıdığı için warning kasıtlı amber */}
                    <div className="rounded-md border border-amber-200 bg-amber-50 p-4">
                      <Label className="text-amber-900 font-semibold">Para Birimi (Tüm Sistem)</Label>
                      <p className="text-xs text-amber-800 mt-1 mb-3">
                        Bu seçim panel, faturalar, channel manager ve raporlar dahil tüm tutarları etkiler.
                      </p>
                      <Select
                        value={invoiceSettings.currency || 'TRY'}
                        onValueChange={(code) => setInvoiceSettings(prev => ({ ...prev, currency: code }))}
                      >
                        <SelectTrigger data-testid="currency-select" className="w-full bg-white">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {CURRENCY_OPTIONS.map(opt => (
                            <SelectItem key={opt.code} value={opt.code}>
                              {(t(opt.label) === opt.label ? opt.fallback : t(opt.label))} ({opt.sym})
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    {/* Invoice Header/Footer */}
                    <div>
                      <Label>Fatura Üst Bilgi</Label>
                      <textarea value={invoiceSettings.invoice_header || ''} onChange={e => setInvoiceSettings(prev => ({ ...prev, invoice_header: e.target.value }))} className="w-full border rounded-md px-3 py-2 text-sm min-h-[60px] focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="Fatura başlığı..." />
                    </div>
                    <div>
                      <Label>Fatura Alt Bilgi</Label>
                      <textarea value={invoiceSettings.invoice_footer || ''} onChange={e => setInvoiceSettings(prev => ({ ...prev, invoice_footer: e.target.value }))} className="w-full border rounded-md px-3 py-2 text-sm min-h-[60px] focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="Fatura alt notu..." />
                    </div>
                    <div>
                      <Label>Ek Notlar</Label>
                      <textarea value={invoiceSettings.invoice_notes || ''} onChange={e => setInvoiceSettings(prev => ({ ...prev, invoice_notes: e.target.value }))} className="w-full border rounded-md px-3 py-2 text-sm min-h-[60px] focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="Ek bilgiler..." />
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* ═══════════ ROOMS MANAGEMENT TAB (super_admin only) ═══════════ */}
          {isSuperAdmin && (
            <TabsContent value="rooms" className="space-y-4" data-testid="rooms-settings-content">
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="flex items-center gap-2">
                        <DoorOpen className="w-5 h-5" /> Oda Yönetimi
                      </CardTitle>
                      <CardDescription>Otel odalarını ekleyin, düzenleyin veya silin</CardDescription>
                    </div>
                    <div className="flex gap-2 flex-wrap">
                      <Button variant="outline" size="sm" onClick={loadRooms} disabled={roomsLoading}>
                        <RefreshCw className={`w-4 h-4 mr-1.5 ${roomsLoading ? 'animate-spin' : ''}`} /> Yenile
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => setShowBulkRoomsDialog(true)} data-testid="bulk-add-rooms-btn" disabled={!isSuperAdmin} title={!isSuperAdmin ? 'Yalnızca süper-admin' : undefined}>
                        <Plus className="w-4 h-4 mr-1" /> Toplu Oda Ekle
                      </Button>
                      <Button size="sm" onClick={() => setShowAddRoomDialog(true)} data-testid="add-room-btn" disabled={!isSuperAdmin} title={!isSuperAdmin ? 'Yalnızca süper-admin' : undefined}>
                        <Plus className="w-4 h-4 mr-1" /> Tek Oda Ekle
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  {roomsLoading ? (
                    <div className="text-center py-8 text-slate-400">Yükleniyor...</div>
                  ) : roomsList.length === 0 ? (
                    <div className="text-center py-12 text-slate-400">
                      <DoorOpen className="w-12 h-12 mx-auto mb-3 opacity-30" />
                      <p className="text-lg font-medium">Henüz oda eklenmemiş</p>
                      <p className="text-sm mt-1">Yukarıdaki butonlarla oda ekleyebilirsiniz</p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <div className="text-sm text-slate-500 mb-3">Toplam {roomsList.length} oda</div>
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                        {roomsList.map(room => (
                          <div
                            key={room.id}
                            className="flex items-center justify-between p-3 border rounded-lg hover:bg-slate-50 transition-colors"
                            data-testid={`settings-room-${room.room_number}`}
                          >
                            <div className="flex items-center gap-3">
                              <div className="w-10 h-10 bg-indigo-100 rounded-lg flex items-center justify-center">
                                <span className="text-sm font-bold text-indigo-700">{room.room_number}</span>
                              </div>
                              <div>
                                <p className="text-sm font-medium">{room.room_type}</p>
                                <p className="text-xs text-slate-500">Kat {room.floor} - {room.capacity} kişi</p>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              <Badge variant="outline" className="text-xs">{room.status}</Badge>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-rose-500 hover:text-rose-700 hover:bg-rose-50"
                                onClick={() => handleDeleteRoom(room.id, room.room_number)}
                                data-testid={`delete-room-${room.room_number}`}
                              >
                                <Trash2 className="w-4 h-4" />
                              </Button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          )}

          {/* ═══════════ B2B ENTEGRASYON TAB ═══════════ */}
          {isAdmin && (
            <TabsContent value="b2b" className="space-y-4" data-testid="b2b-settings-content">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <KeyRound className="w-5 h-5" /> Bağlantı Bilgileri
                  </CardTitle>
                  <CardDescription>
                    Acente otomasyonunuzu otele bağlamak için Otel ID ve Bağlantı Kodu'nu acente uygulamasına girin.
                    Bağlantı Kodu yalnızca bağlantı isteği oluşturabilir; API key yalnızca sizin onayınızla üretilir.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label>Otel ID</Label>
                      <div className="flex items-center gap-2">
                        <Input value={b2bInfo?.hotel_id ?? ''} readOnly className="bg-slate-50 font-mono" />
                        <Button variant="outline" size="sm" onClick={() => copyToClipboard(String(b2bInfo?.hotel_id ?? ''), 'Otel ID')} disabled={!b2bInfo?.hotel_id}>
                          <Copy className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>
                    <div>
                      <Label>Tenant ID</Label>
                      <div className="flex items-center gap-2">
                        <Input value={b2bInfo?.tenant_id ?? ''} readOnly className="bg-slate-50 font-mono text-xs" />
                        <Button variant="outline" size="sm" onClick={() => copyToClipboard(String(b2bInfo?.tenant_id ?? ''), 'Tenant ID')} disabled={!b2bInfo?.tenant_id}>
                          <Copy className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>
                  </div>

                  <div className="border-t pt-4">
                    <Label>Bağlantı Kodu</Label>
                    {b2bCodeOnce ? (
                      <div className="mt-1 rounded-md border border-amber-300 bg-amber-50 p-3 space-y-2">
                        <div className="flex items-center gap-2 text-sm font-medium text-amber-800">
                          <AlertTriangle className="w-4 h-4" /> Bu kod yalnızca bir kez gösterilir. Güvenli saklayın.
                        </div>
                        <div className="flex items-center gap-2">
                          <Input value={b2bCodeOnce} readOnly className="bg-white font-mono text-xs" data-testid="b2b-connect-code-once" />
                          <Button variant="outline" size="sm" onClick={() => copyToClipboard(b2bCodeOnce, 'Bağlantı Kodu')}>
                            <Copy className="w-4 h-4" />
                          </Button>
                        </div>
                        <button onClick={() => setB2bCodeOnce('')} className="text-xs text-slate-500 hover:underline">Gizle</button>
                      </div>
                    ) : (
                      <div className="mt-1 flex items-center gap-2 text-sm text-slate-600">
                        {b2bInfo?.has_active_code ? (
                          <span className="font-mono">{b2bInfo.code_prefix}</span>
                        ) : (
                          <span>Henüz bağlantı kodu üretilmedi.</span>
                        )}
                      </div>
                    )}
                    <div className="mt-3">
                      <Button onClick={handleRegenerateCode} disabled={b2bBusy} data-testid="b2b-regenerate-code" className="bg-black text-white hover:bg-black/90">
                        <RefreshCw className="w-4 h-4 mr-1" />
                        {b2bInfo?.has_active_code ? 'Yeni Kod Üret' : 'Bağlantı Kodu Üret'}
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle>Bağlantı İstekleri</CardTitle>
                      <CardDescription>Acentelerden gelen bağlantı isteklerini onaylayın veya reddedin.</CardDescription>
                    </div>
                    <Button variant="outline" size="sm" onClick={loadB2B} disabled={b2bLoading}>
                      <RefreshCw className="w-4 h-4 mr-1" /> Yenile
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {b2bLoading ? (
                    <div className="py-8 text-center text-sm text-slate-500">Yükleniyor...</div>
                  ) : b2bRequests.length === 0 ? (
                    <div className="py-8 text-center text-sm text-slate-500">Henüz bağlantı isteği yok.</div>
                  ) : (
                    <div className="space-y-2" data-testid="b2b-requests-list">
                      {b2bRequests.map((req) => (
                        <div key={req.id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-md border p-3">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-medium truncate">{req.agency_name}</span>
                              <span className={`text-xs px-2 py-0.5 rounded-full ${
                                req.status === 'pending' ? 'bg-amber-100 text-amber-800'
                                : req.status === 'approved' ? 'bg-emerald-100 text-emerald-800'
                                : 'bg-red-100 text-red-800'
                              }`}>
                                {req.status === 'pending' ? 'Bekliyor' : req.status === 'approved' ? 'Onaylandı' : 'Reddedildi'}
                              </span>
                            </div>
                            <div className="text-xs text-slate-500 mt-0.5 space-x-2">
                              {req.contact_email ? <span>{req.contact_email}</span> : null}
                              {req.created_at ? <span>{new Date(req.created_at).toLocaleString('tr-TR')}</span> : null}
                              {req.key_prefix ? <span className="font-mono">{req.key_prefix}</span> : null}
                            </div>
                          </div>
                          {req.status === 'pending' ? (
                            <div className="flex items-center gap-2 shrink-0">
                              <Button size="sm" onClick={() => handleApproveRequest(req)} disabled={b2bBusy} className="bg-black text-white hover:bg-black/90" data-testid="b2b-approve">
                                <CheckCircle2 className="w-4 h-4 mr-1" /> Onayla
                              </Button>
                              <Button size="sm" variant="outline" onClick={() => handleRejectRequest(req)} disabled={b2bBusy} data-testid="b2b-reject">
                                <X className="w-4 h-4 mr-1" /> Reddet
                              </Button>
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          )}
        </Tabs>
      </div>

      {/* ─── Add Member Modal ─────────────────────── */}
      <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><Plus className="w-5 h-5" /> Ekip Üyesi Ekle</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>İsim *</Label><Input value={newMember.name} onChange={(e) => setNewMember({ ...newMember, name: e.target.value })} placeholder="Ahmet Yılmaz" /></div>
            <div><Label>{t('common.email')} *</Label><Input type="email" value={newMember.email} onChange={(e) => setNewMember({ ...newMember, email: e.target.value })} placeholder={t('auth.emailPlaceholder')} /></div>
            <div><Label>Telefon</Label><Input value={newMember.phone} onChange={(e) => setNewMember({ ...newMember, phone: e.target.value })} placeholder="+905551234567" /></div>
            <div>
              <Label>Şifre *</Label>
              <Input type="password" value={newMember.password} onChange={(e) => setNewMember({ ...newMember, password: e.target.value })} placeholder="Min 6 karakter" />
              {newMember.password && newMember.password.length < 6 && (
                <p className="text-[11px] text-rose-600 mt-1">Şifre en az 6 karakter olmalıdır</p>
              )}
            </div>
            <div>
              <Label>Rol</Label>
              <Select value={newMember.role} onValueChange={(v) => setNewMember({ ...newMember, role: v })}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {teamMeta.allowed_roles.map((r) => (
                    <SelectItem key={r} value={r}>{getRoleLabel(r).label}</SelectItem>
                  ))}
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
            const plan = PLANS[selectedPlan]; const Icon = plan.icon;
            const priceEUR = billingCycle === 'yearly' ? plan.priceYearlyEUR : plan.priceEUR;
            const period = billingCycle === 'yearly' ? '/yıl' : '/ay';
            const isDowngrade = planAction === 'downgrade';
            return (
              <div className="space-y-4">
                <div className={`p-4 rounded-xl ${plan.lightBg} border ${plan.borderColor}`}>
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-xl ${plan.iconBg} ${plan.iconText}`}><Icon className="w-6 h-6" /></div>
                    <div><h3 className="font-bold text-lg">{plan.label}</h3><p className="text-xs text-slate-500">{plan.description}</p></div>
                  </div>
                </div>

                {isDowngrade && (
                  <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 flex items-start gap-2">
                    <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-amber-800">Plan düşürme uyarısı</p>
                      <p className="text-xs text-amber-700 mt-0.5">
                        Mevcut planınıza ait modüller devre dışı kalacaktır. Oda ve kullanıcı sayınız yeni plan limitlerini aşıyorsa düşürme yapılamaz.
                      </p>
                    </div>
                  </div>
                )}

                <div className="flex items-center justify-center gap-3 p-3 bg-slate-50 rounded-lg">
                  <button type="button" className={`px-4 py-2 rounded-lg text-sm font-medium transition ${billingCycle === 'monthly' ? 'bg-white shadow text-slate-900' : 'text-slate-500'}`} onClick={() => setBillingCycle('monthly')}>Aylık</button>
                  <button type="button" className={`px-4 py-2 rounded-lg text-sm font-medium transition ${billingCycle === 'yearly' ? 'bg-white shadow text-slate-900' : 'text-slate-500'}`} onClick={() => setBillingCycle('yearly')}>
                    Yıllık <span className="ml-1 text-[10px] text-emerald-600 font-bold">2 AY ÜCRETSİZ</span>
                  </button>
                </div>

                <div className="text-center py-2"><p className="text-4xl font-bold text-slate-900">{fmtPlanPrice(priceEUR)}</p><p className="text-sm text-slate-500">{period}</p></div>

                <ul className="space-y-1.5 max-h-40 overflow-y-auto">
                  {plan.features.map((f, i) => (<li key={i} className="flex items-center gap-2 text-sm text-slate-700"><CheckCircle2 className="w-4 h-4 text-emerald-500 flex-shrink-0" />{f}</li>))}
                </ul>

                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="outline" onClick={() => setShowPlanModal(false)}>{t("common.cancel")}</Button>
                  <Button onClick={handleChangePlan} disabled={saving}>
                    {saving ? 'İşleniyor...' : isDowngrade ? `${plan.label} Plana Düşür` : `${plan.label} Plana Yükselt`}
                  </Button>
                </div>
              </div>
            );
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
              <Input value={newRoom.room_number} onChange={(e) => setNewRoom({ ...newRoom, room_number: e.target.value })} placeholder="101" required data-testid="new-room-number" />
            </div>
            <div>
              <Label>Oda Tipi</Label>
              <Select value={newRoom.room_type} onValueChange={(v) => setNewRoom({ ...newRoom, room_type: v })}>
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
                <Input type="number" min={0} value={newRoom.floor} onChange={(e) => setNewRoom({ ...newRoom, floor: parseInt(e.target.value) || 0 })} required />
              </div>
              <div>
                <Label>Kapasite</Label>
                <Input type="number" min={1} value={newRoom.capacity} onChange={(e) => setNewRoom({ ...newRoom, capacity: parseInt(e.target.value) || 1 })} required />
              </div>
            </div>
            <div>
              <Label>Taban Fiyat</Label>
              <Input type="number" min={0} step="0.01" value={newRoom.base_price} onChange={(e) => setNewRoom({ ...newRoom, base_price: parseFloat(e.target.value) || 0 })} required />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={() => setShowAddRoomDialog(false)}>İptal</Button>
              <Button type="submit" disabled={roomSaving} data-testid="create-room-submit">{roomSaving ? 'Oluşturuluyor...' : 'Oda Oluştur'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* ─── Bulk Rooms Dialog (super_admin) ─── */}
      <BulkRoomsDialog
        open={showBulkRoomsDialog}
        onClose={() => setShowBulkRoomsDialog(false)}
        onRoomsCreated={loadRooms}
        user={user}
      />
    </>
  );
};

export default Settings;
