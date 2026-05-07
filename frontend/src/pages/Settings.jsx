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
  BedDouble, DoorOpen
} from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import BulkRoomsDialog from '@/components/pms/BulkRoomsDialog';
import { useCurrency } from '@/context/CurrencyContext';

import { confirmDialog } from '@/lib/dialogs';
// ─── Plan Config ──────────────────────────────────
const PLAN_CONFIG = {
  basic: {
    key: 'basic', price: 79, priceYearly: 790,
    maxRooms: 15, maxUsers: 3,
    icon: Building2, gradient: 'from-emerald-500 to-green-600',
    lightBg: 'bg-emerald-50', borderColor: 'border-emerald-200',
  },
  professional: {
    key: 'professional', price: 299, priceYearly: 2990,
    maxRooms: 80, maxUsers: 15,
    icon: Zap, gradient: 'from-blue-500 to-indigo-600',
    lightBg: 'bg-blue-50', borderColor: 'border-blue-200',
  },
  enterprise: {
    key: 'enterprise', price: 799, priceYearly: 7990,
    maxRooms: null, maxUsers: null,
    icon: Crown, gradient: 'from-indigo-500 to-pink-600',
    lightBg: 'bg-indigo-50', borderColor: 'border-indigo-200',
  },
};

const ROLE_COLORS = {
  admin: 'bg-blue-100 text-blue-800',
  supervisor: 'bg-green-100 text-green-800',
  front_desk: 'bg-yellow-100 text-yellow-800',
  housekeeping: 'bg-amber-100 text-amber-800',
  finance: 'bg-pink-100 text-pink-800',
  procurement: 'bg-amber-100 text-amber-800',
  sales: 'bg-indigo-100 text-indigo-800',
  revenue: 'bg-teal-100 text-teal-800',
  maintenance: 'bg-gray-100 text-gray-800',
  fnb: 'bg-red-100 text-red-800',
  spa: 'bg-violet-100 text-violet-800',
  concierge: 'bg-cyan-100 text-cyan-800',
  night_auditor: 'bg-slate-100 text-slate-800',
  staff: 'bg-neutral-100 text-neutral-800',
  super_admin: 'bg-indigo-100 text-indigo-800',
};

const Settings = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const { refresh: refreshCurrency } = useCurrency();

  const getRoleLabel = (role) => ({
    label: t(`settings.roles.${role}`) || role,
    color: ROLE_COLORS[role] || 'bg-gray-100 text-gray-800'
  });

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
  const [activeTab, setActiveTab] = useState('team');

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
  const [planAction, setPlanAction] = useState('upgrade'); // upgrade or downgrade

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
  const [roomsList, setRoomsList] = useState([]);
  const [roomsLoading, setRoomsLoading] = useState(false);
  const [showBulkRoomsDialog, setShowBulkRoomsDialog] = useState(false);
  const [showAddRoomDialog, setShowAddRoomDialog] = useState(false);
  const [newRoom, setNewRoom] = useState({ room_number: '', room_type: 'standard', floor: 1, capacity: 2, base_price: 100 });
  const [roomSaving, setRoomSaving] = useState(false);

  const currentTier = useMemo(() => {
    const t = tenant?.subscription_tier || 'basic';
    if (t === 'pro') return 'professional';
    if (t === 'ultra') return 'enterprise';
    return t;
  }, [tenant]);

  const currentPlan = PLANS[currentTier] || PLANS.basic;
  const PlanIcon = currentPlan.icon;

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
    } catch (err) { console.error('Team load failed', err); }
    finally { setTeamLoading(false); }
  }, []);

  const loadSubscription = useCallback(async () => {
    try {
      const res = await axios.get('/subscription/current');
      setSubscription(res.data);
    } catch (err) { console.error('Sub load failed', err); }
  }, []);

  const loadBillingHistory = useCallback(async () => {
    setBillingLoading(true);
    try {
      const res = await axios.get('/billing/history');
      setBillingHistory(res.data?.records || []);
    } catch (err) { console.error('Billing load failed', err); }
    finally { setBillingLoading(false); }
  }, []);

  const loadInvoiceSettings = useCallback(async () => {
    setInvoiceLoading(true);
    try {
      const API = "";
      const res = await axios.get(`/pms/hotel-settings`);
      setInvoiceSettings(res.data || {});
    } catch (err) { console.error('Invoice settings load failed', err); }
    finally { setInvoiceLoading(false); }
  }, []);

  const loadRooms = useCallback(async () => {
    if (!isSuperAdmin) return;
    setRoomsLoading(true);
    try {
      const API = "";
      const res = await axios.get(`/pms/rooms?limit=500`);
      setRoomsList(res.data || []);
    } catch (err) { console.error('Rooms load failed', err); }
    finally { setRoomsLoading(false); }
  }, [isSuperAdmin]);

  useEffect(() => {
    loadTeam();
    loadSubscription();
    loadBillingHistory();
    loadInvoiceSettings();
    loadRooms();
  }, [loadTeam, loadSubscription, loadBillingHistory, loadInvoiceSettings, loadRooms]);

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

  // ─── Team Handlers ─────────────────────────────
  const handleAddMember = async () => {
    if (!newMember.email || !newMember.name || !newMember.password) {
      toast.error('Email, isim ve şifre zorunludur'); return;
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
      await loadBillingHistory();
      // Reload to apply new modules
      setTimeout(() => window.location.reload(), 800);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Plan değiştirilemedi');
    } finally { setSaving(false); }
  };

  // ─── Hotel Info Handler ────────────────────────
  const handleSaveHotelInfo = async () => {
    setHotelSaving(true);
    try {
      const res = await axios.patch('/hotel/info', hotelForm);
      toast.success(res.data?.message || 'Otel bilgileri güncellendi');
      setEditMode(false);
      // Update tenant in localStorage for immediate effect
      const updatedTenant = res.data?.tenant;
      if (updatedTenant) {
        const stored = JSON.parse(localStorage.getItem('tenant') || '{}');
        const merged = { ...stored, ...updatedTenant };
        localStorage.setItem('tenant', JSON.stringify(merged));
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Güncellenemedi');
    } finally { setHotelSaving(false); }
  };

  const handleSaveInvoiceSettings = async () => {
    setInvoiceSaving(true);
    try {
      const API = "";
      const res = await axios.put(`/pms/hotel-settings`, invoiceSettings);
      toast.success('Fatura ayarları kaydedildi');
      setInvoiceSettings(res.data?.settings || invoiceSettings);
      try { await refreshCurrency(); } catch { /* ignore */ }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Kaydedilemedi');
    } finally { setInvoiceSaving(false); }
  };

  const handleLogoUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      toast.error('Logo dosyası 2MB\'dan küçük olmalıdır');
      return;
    }
    const reader = new FileReader();
    reader.onload = (event) => {
      setInvoiceSettings(prev => ({ ...prev, logo_data: event.target.result }));
    };
    reader.readAsDataURL(file);
  };

  // Room CRUD (super_admin)
  const handleCreateRoom = async (e) => {
    e.preventDefault();
    setRoomSaving(true);
    try {
      const API = "";
      await axios.post(`/pms/rooms`, newRoom);
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
      const API = "";
      await axios.post(`/pms/rooms/bulk/delete`, {
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

  return (
    <>
      <div className="p-4 md:p-6 space-y-4 max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <SettingsIcon className="w-6 h-6 text-gray-600" />
              Ayarlar
            </h1>
            <p className="text-sm text-gray-500 mt-1">{t('settings.subtitle')}</p>
          </div>
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border ${currentPlan.borderColor} ${currentPlan.lightBg}`}>
            <PlanIcon className="w-4 h-4" />
            <span className="text-sm font-semibold">{currentPlan.label}</span>
          </div>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
          <TabsList className={`grid w-full ${isSuperAdmin ? 'grid-cols-6' : 'grid-cols-5'}`}>
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
          </TabsList>

          {/* ═══════════ TEAM TAB ═══════════ */}
          <TabsContent value="team" className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Card className="p-4"><div className="text-2xl font-bold">{team.length}</div><div className="text-xs text-gray-500">Toplam Üye</div></Card>
              <Card className="p-4"><div className="text-2xl font-bold">{teamMeta.max_users === 999 ? '∞' : teamMeta.max_users}</div><div className="text-xs text-gray-500">Max Kullanıcı</div></Card>
              <Card className="p-4"><div className="text-2xl font-bold">{teamMeta.allowed_roles.length}</div><div className="text-xs text-gray-500">Kullanılabilir Rol</div></Card>
              <Card className="p-4"><div className="text-2xl font-bold capitalize">{teamMeta.tier}</div><div className="text-xs text-gray-500">Plan</div></Card>
            </div>

            {teamMeta.tier === 'basic' && (
              <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-amber-800">Basic planda sadece "Yönetici" rolü kullanılabilir</p>
                  <p className="text-xs text-amber-600 mt-0.5">Departman rolleri için Professional plana yükseltin.</p>
                  <button onClick={() => setActiveTab('plan')} className="text-xs font-bold text-amber-700 mt-1 hover:underline flex items-center gap-1">Planı yükselt <ArrowRight className="w-3 h-3" /></button>
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
              <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
                Kullanıcı limitine ulaşıldı ({teamMeta.max_users}). Planınızı yükseltin.
              </div>
            )}

            <Card>
              <CardContent className="p-0">
                {teamLoading ? (
                  <div className="p-8 text-center text-gray-400">{t("common.loading")}</div>
                ) : team.length === 0 ? (
                  <div className="p-8 text-center text-gray-400">Henüz ekip üyesi yok</div>
                ) : (
                  <div className="divide-y">
                    {team.map((member) => {
                      const roleInfo = getRoleLabel(member.role);
                      const isMe = member.id === user?.id;
                      return (
                        <div key={member.id} className="flex items-center justify-between px-4 py-3 hover:bg-gray-50/50">
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-gray-200 to-gray-300 flex items-center justify-center text-sm font-bold text-gray-600">
                              {(member.name || '?')[0].toUpperCase()}
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-medium text-gray-900 truncate">{member.name}</span>
                                {isMe && <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-600 border border-blue-100">Siz</span>}
                              </div>
                              <span className="text-xs text-gray-400">{member.email}</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <select value={member.role} onChange={(e) => handleUpdateRole(member.id, e.target.value)} disabled={isMe || member.role === 'super_admin'}
                              className={`text-xs px-2 py-1 rounded-lg border ${roleInfo.color} font-medium cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed`}>
                              {teamMeta.allowed_roles.map((r) => (<option key={r} value={r}>{getRoleLabel(r).label}</option>))}
                              {!teamMeta.allowed_roles.includes(member.role) && member.role !== 'super_admin' && (<option value={member.role}>{getRoleLabel(member.role).label}</option>)}
                              {member.role === 'super_admin' && (<option value="super_admin">Super Admin</option>)}
                            </select>
                            {!isMe && member.role !== 'super_admin' && (
                              <Button variant="ghost" size="sm" className="text-red-400 hover:text-red-600 hover:bg-red-50 p-1" onClick={() => handleRemoveMember(member.id, member.name)}>
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
                {teamMeta.tier !== 'enterprise' && <p className="text-[11px] text-gray-400 mt-2">Daha fazla rol için {teamMeta.tier === 'basic' ? 'Professional' : 'Enterprise'} plana yükseltin</p>}
              </CardContent>
            </Card>
          </TabsContent>

          {/* ═══════════ PLAN TAB ═══════════ */}
          <TabsContent value="plan" className="space-y-4">
            {/* Current plan */}
            <Card className={`border-2 ${currentPlan.borderColor}`}>
              <CardContent className="p-6">
                <div className="flex items-center justify-between flex-wrap gap-4">
                  <div className="flex items-center gap-4">
                    <div className={`p-3 rounded-2xl bg-gradient-to-br ${currentPlan.gradient} text-white shadow-lg`}><PlanIcon className="w-8 h-8" /></div>
                    <div>
                      <h3 className="text-xl font-bold text-gray-900">{currentPlan.label} Plan</h3>
                      <p className="text-sm text-gray-500">{currentPlan.description}</p>
                      <div className="flex items-center gap-4 mt-2 text-sm">
                        <span className="text-gray-600"><strong>{subscription?.rooms_count || 0}</strong> / {currentPlan.maxRooms || '∞'} oda</span>
                        <span className="text-gray-600"><strong>{subscription?.users_count || 0}</strong> / {currentPlan.maxUsers || '∞'} kullanıcı</span>
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-3xl font-bold text-gray-900">{currentPlan.price}€</p>
                    <p className="text-xs text-gray-400">/ ay</p>
                    {subscription?.status && (
                      <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full mt-1 ${subscription.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                        <CheckCircle2 className="w-3 h-3" /> {subscription.status === 'active' ? 'Aktif' : subscription.status}
                      </span>
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
                            <div className={`p-2.5 rounded-xl bg-gradient-to-br ${plan.gradient} text-white shadow-md`}><Icon className="w-6 h-6" /></div>
                            <div className="text-right"><p className="text-2xl font-bold text-gray-900">{plan.price}€</p><p className="text-[10px] text-gray-400">/ay</p></div>
                          </div>
                          <h3 className="text-lg font-bold text-gray-900">{plan.label}</h3>
                          <p className="text-xs text-gray-500 mb-3">{plan.description}</p>
                          <ul className="space-y-1">
                            {plan.features.slice(0, 5).map((f, i) => (<li key={i} className="flex items-center gap-1.5 text-xs text-gray-600"><CheckCircle2 className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />{f}</li>))}
                            {plan.features.length > 5 && <li className="text-xs text-gray-400 pl-5">+{plan.features.length - 5} daha</li>}
                          </ul>
                          <div className={`mt-4 w-full py-2 rounded-lg bg-gradient-to-r ${plan.gradient} text-white text-center text-sm font-bold flex items-center justify-center gap-1 group-hover:shadow-md transition`}>
                            Yükselt <ArrowRight className="w-4 h-4" />
                          </div>
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
                <h2 className="text-sm font-medium text-gray-400 flex items-center gap-2 mt-6"><ArrowDown className="w-4 h-4" /> Plan Düşür</h2>
                <div className="grid md:grid-cols-2 gap-3">
                  {downgradeTiers.map((tierKey) => {
                    const plan = PLANS[tierKey]; const Icon = plan.icon;
                    return (
                      <Card key={tierKey} className="border border-gray-200 hover:border-gray-300 transition cursor-pointer"
                        onClick={() => openPlanModal(tierKey, 'downgrade')}>
                        <CardContent className="p-4 flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <div className={`p-2 rounded-lg ${plan.lightBg}`}><Icon className="w-5 h-5 text-gray-500" /></div>
                            <div>
                              <h4 className="text-sm font-semibold text-gray-700">{plan.label}</h4>
                              <p className="text-[11px] text-gray-400">{plan.price}€/ay • {plan.description}</p>
                            </div>
                          </div>
                          <Button variant="outline" size="sm" className="text-xs text-gray-500">
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
                  {currentPlan.features.map((f, i) => (<div key={i} className="flex items-center gap-2 text-sm text-gray-700"><CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />{f}</div>))}
                </div>
              </CardContent>
            </Card>

            {currentTier === 'enterprise' && (
              <div className="p-4 rounded-xl bg-indigo-50 border border-indigo-200 text-center">
                <Crown className="w-8 h-8 text-indigo-600 mx-auto mb-2" />
                <p className="text-sm font-bold text-indigo-800">En üst plandasınız!</p>
                <p className="text-xs text-indigo-600">Tüm modüller ve özellikler aktif.</p>
              </div>
            )}
          </TabsContent>

          {/* ═══════════ BILLING HISTORY TAB ═══════════ */}
          <TabsContent value="billing" className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold flex items-center gap-2"><Receipt className="w-5 h-5" /> Fatura & Plan Geçmişi</h2>
              <Button variant="outline" size="sm" onClick={loadBillingHistory} disabled={billingLoading}>
                {billingLoading ? t('common.loading') : 'Yenile'}
              </Button>
            </div>

            {billingLoading ? (
              <div className="text-center py-12 text-gray-400">{t("common.loading")}</div>
            ) : billingHistory.length === 0 ? (
              <Card>
                <CardContent className="p-12 text-center">
                  <Receipt className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                  <h3 className="text-lg font-semibold text-gray-400">Henüz işlem geçmişi yok</h3>
                  <p className="text-sm text-gray-300 mt-1">Plan değişiklikleriniz burada listelenecek</p>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-3">
                {billingHistory.map((record) => {
                  const isUpgrade = record.action === 'upgrade';
                  const fromPlan = PLANS[record.from_tier];
                  const toPlan = PLANS[record.to_tier];
                  const ToIcon = toPlan?.icon || Building2;
                  return (
                    <Card key={record.id} className="hover:shadow-sm transition">
                      <CardContent className="p-4">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <div className={`p-2 rounded-lg ${isUpgrade ? 'bg-green-100' : 'bg-amber-100'}`}>
                              {isUpgrade ? <ArrowRight className="w-5 h-5 text-green-600" /> : <ArrowDown className="w-5 h-5 text-amber-600" />}
                            </div>
                            <div>
                              <div className="flex items-center gap-2">
                                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${isUpgrade ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>
                                  {isUpgrade ? 'Yükseltme' : 'Düşürme'}
                                </span>
                                <span className="text-sm font-semibold text-gray-900">
                                  {fromPlan?.label || record.from_tier} → {toPlan?.label || record.to_tier}
                                </span>
                              </div>
                              <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
                                <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{new Date(record.created_at).toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                                <span>{record.billing_cycle === 'yearly' ? 'Yıllık' : 'Aylık'}</span>
                                {record.user_name && <span>İşlem: {record.user_name}</span>}
                              </div>
                            </div>
                          </div>
                          <div className="text-right">
                            <p className="text-lg font-bold text-gray-900">{record.amount}€</p>
                            <p className="text-[10px] text-gray-400">{record.currency} / {record.billing_cycle === 'yearly' ? 'yıl' : 'ay'}</p>
                            <span className={`inline-flex text-[10px] px-1.5 py-0.5 rounded mt-1 ${record.status === 'completed' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
                              {record.status === 'completed' ? 'Tamamlandı' : record.status}
                            </span>
                          </div>
                        </div>
                        {record.valid_until && (
                          <div className="mt-2 pt-2 border-t text-xs text-gray-400">
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
                      <Button size="sm" onClick={handleSaveHotelInfo} disabled={hotelSaving}>
                        <Save className="w-4 h-4 mr-1" /> {hotelSaving ? 'Kaydediyor...' : 'Kaydet'}
                      </Button>
                    </div>
                  )}
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label>Otel Adı</Label>
                  <Input value={hotelForm.property_name || ''} readOnly={!editMode} className={!editMode ? 'bg-gray-50' : ''} onChange={(e) => setHotelForm({ ...hotelForm, property_name: e.target.value })} />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label>Telefon</Label>
                    <Input value={hotelForm.phone || ''} readOnly={!editMode} className={!editMode ? 'bg-gray-50' : ''} onChange={(e) => setHotelForm({ ...hotelForm, phone: e.target.value })} placeholder="+905551234567" />
                  </div>
                  <div>
                    <Label>E-posta</Label>
                    <Input type="email" value={hotelForm.email || ''} readOnly={!editMode} className={!editMode ? 'bg-gray-50' : ''} onChange={(e) => setHotelForm({ ...hotelForm, email: e.target.value })} />
                  </div>
                </div>
                <div>
                  <Label>Adres</Label>
                  <Input value={hotelForm.address || ''} readOnly={!editMode} className={!editMode ? 'bg-gray-50' : ''} onChange={(e) => setHotelForm({ ...hotelForm, address: e.target.value })} />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label>Lokasyon / Şehir</Label>
                    <Input value={hotelForm.location || ''} readOnly={!editMode} className={!editMode ? 'bg-gray-50' : ''} onChange={(e) => setHotelForm({ ...hotelForm, location: e.target.value })} />
                  </div>
                  <div>
                    <Label>Toplam Oda Sayısı</Label>
                    <Input type="number" value={hotelForm.total_rooms || ''} readOnly={!editMode} className={!editMode ? 'bg-gray-50' : ''} onChange={(e) => setHotelForm({ ...hotelForm, total_rooms: parseInt(e.target.value) || 0 })} />
                    {editMode && currentPlan.maxRooms && <p className="text-[11px] text-gray-400 mt-1">Plan limiti: max {currentPlan.maxRooms} oda</p>}
                  </div>
                </div>
                <div>
                  <Label>Açıklama</Label>
                  <textarea value={hotelForm.description || ''} readOnly={!editMode} className={`w-full border rounded-md px-3 py-2 text-sm min-h-[80px] ${!editMode ? 'bg-gray-50' : ''} focus:outline-none focus:ring-2 focus:ring-blue-500`} onChange={(e) => setHotelForm({ ...hotelForm, description: e.target.value })} placeholder="Otel hakkında kısa açıklama..." />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-sm">{t('settings.subscription')}</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-gray-500">Plan</span><span className="font-semibold">{currentPlan.label}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Durum</span><span className="font-semibold text-green-600">{subscription?.status === 'active' ? 'Aktif' : subscription?.status || '—'}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Oda</span><span className="font-semibold">{subscription?.rooms_count || 0} / {currentPlan.maxRooms || '∞'}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Kullanıcı</span><span className="font-semibold">{subscription?.users_count || 0} / {currentPlan.maxUsers || '∞'}</span></div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* ═══════════ INVOICE SETTINGS TAB ═══════════ */}
          <TabsContent value="invoice" className="space-y-4" data-testid="invoice-settings-content">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm flex items-center justify-between">
                  <span className="flex items-center gap-2"><FileText className="w-4 h-4" /> Fatura & Logo Ayarları</span>
                  <Button size="sm" onClick={handleSaveInvoiceSettings} disabled={invoiceSaving} data-testid="save-invoice-settings-btn">
                    <Save className="w-4 h-4 mr-1" /> {invoiceSaving ? 'Kaydediliyor...' : 'Kaydet'}
                  </Button>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {invoiceLoading ? (
                  <div className="text-center py-8 text-gray-400">Yükleniyor...</div>
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
                              onClick={() => setInvoiceSettings(prev => ({ ...prev, logo_data: null }))}
                              className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 text-white rounded-full flex items-center justify-center text-xs hover:bg-red-600"
                            >
                              <X className="w-3 h-3" />
                            </button>
                          </div>
                        ) : (
                          <div className="h-16 w-32 border-2 border-dashed rounded-lg flex items-center justify-center text-gray-400">
                            <Image className="w-6 h-6" />
                          </div>
                        )}
                        <label className="cursor-pointer">
                          <div className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700">
                            <Upload className="w-4 h-4" /> Logo Yükle
                          </div>
                          <input type="file" accept="image/*" className="hidden" onChange={handleLogoUpload} data-testid="logo-upload-input" />
                          <p className="text-[10px] text-gray-400 mt-1">PNG, JPG (max 2MB)</p>
                        </label>
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

                    {/* Currency */}
                    <div className="rounded-md border border-amber-200 bg-amber-50 p-4">
                      <Label className="text-amber-900 font-semibold">Para Birimi (Tüm Sistem)</Label>
                      <p className="text-xs text-amber-700 mt-1 mb-3">
                        Bu seçim panel, faturalar, channel manager ve raporlar dahil tüm tutarları etkiler.
                      </p>
                      <select
                        value={invoiceSettings.currency || 'TRY'}
                        onChange={e => {
                          const code = e.target.value;
                          const sym = { TRY: '₺', EUR: '€', USD: '$', GBP: '£' }[code] || code;
                          setInvoiceSettings(prev => ({ ...prev, currency: code, currency_symbol: sym }));
                        }}
                        className="w-full border rounded-md px-3 py-2 text-sm bg-white"
                        data-testid="currency-select"
                      >
                        <option value="TRY">Türk Lirası (₺)</option>
                        <option value="EUR">Euro (€)</option>
                        <option value="USD">Amerikan Doları ($)</option>
                        <option value="GBP">İngiliz Sterlini (£)</option>
                      </select>
                    </div>

                    {/* Invoice Header/Footer */}
                    <div>
                      <Label>Fatura Üst Bilgi</Label>
                      <textarea value={invoiceSettings.invoice_header || ''} onChange={e => setInvoiceSettings(prev => ({ ...prev, invoice_header: e.target.value }))} className="w-full border rounded-md px-3 py-2 text-sm min-h-[60px] focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="Fatura başlığı..." />
                    </div>
                    <div>
                      <Label>Fatura Alt Bilgi</Label>
                      <textarea value={invoiceSettings.invoice_footer || ''} onChange={e => setInvoiceSettings(prev => ({ ...prev, invoice_footer: e.target.value }))} className="w-full border rounded-md px-3 py-2 text-sm min-h-[60px] focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="Fatura alt notu..." />
                    </div>
                    <div>
                      <Label>Ek Notlar</Label>
                      <textarea value={invoiceSettings.invoice_notes || ''} onChange={e => setInvoiceSettings(prev => ({ ...prev, invoice_notes: e.target.value }))} className="w-full border rounded-md px-3 py-2 text-sm min-h-[60px] focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="Ek bilgiler..." />
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
                    <div className="flex gap-2">
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
                    <div className="text-center py-8 text-gray-400">Yükleniyor...</div>
                  ) : roomsList.length === 0 ? (
                    <div className="text-center py-12 text-gray-400">
                      <DoorOpen className="w-12 h-12 mx-auto mb-3 opacity-30" />
                      <p className="text-lg font-medium">Henüz oda eklenmemiş</p>
                      <p className="text-sm mt-1">Yukarıdaki butonlarla oda ekleyebilirsiniz</p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <div className="text-sm text-gray-500 mb-3">Toplam {roomsList.length} oda</div>
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                        {roomsList.map(room => (
                          <div
                            key={room.id}
                            className="flex items-center justify-between p-3 border rounded-lg hover:bg-gray-50 transition-colors"
                            data-testid={`settings-room-${room.room_number}`}
                          >
                            <div className="flex items-center gap-3">
                              <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                                <span className="text-sm font-bold text-blue-700">{room.room_number}</span>
                              </div>
                              <div>
                                <p className="text-sm font-medium">{room.room_type}</p>
                                <p className="text-xs text-gray-400">Kat {room.floor} - {room.capacity} kişi</p>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              <Badge variant="outline" className="text-xs">{room.status}</Badge>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-red-500 hover:text-red-700 hover:bg-red-50"
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
            <div><Label>Şifre *</Label><Input type="password" value={newMember.password} onChange={(e) => setNewMember({ ...newMember, password: e.target.value })} placeholder="Min 6 karakter" /></div>
            <div>
              <Label>Rol</Label>
              <select value={newMember.role} onChange={(e) => setNewMember({ ...newMember, role: e.target.value })} className="w-full border rounded-md px-3 py-2 text-sm">
                {teamMeta.allowed_roles.map((r) => (<option key={r} value={r}>{getRoleLabel(r).label}</option>))}
              </select>
              {teamMeta.tier === 'basic' && <p className="text-[11px] text-amber-600 mt-1">Basic planda sadece Yönetici rolü kullanılabilir</p>}
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
            const price = billingCycle === 'yearly' ? plan.priceYearly : plan.price;
            const period = billingCycle === 'yearly' ? '/yıl' : '/ay';
            const isDowngrade = planAction === 'downgrade';
            return (
              <div className="space-y-4">
                <div className={`p-4 rounded-xl ${plan.lightBg} border ${plan.borderColor}`}>
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-xl bg-gradient-to-br ${plan.gradient} text-white`}><Icon className="w-6 h-6" /></div>
                    <div><h3 className="font-bold text-lg">{plan.label}</h3><p className="text-xs text-gray-500">{plan.description}</p></div>
                  </div>
                </div>

                {isDowngrade && (
                  <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 flex items-start gap-2">
                    <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-amber-800">Plan düşürme uyarısı</p>
                      <p className="text-xs text-amber-600 mt-0.5">
                        Mevcut planınıza ait modüller devre dışı kalacaktır. Oda ve kullanıcı sayınız yeni plan limitlerini aşıyorsa düşürme yapılamaz.
                      </p>
                    </div>
                  </div>
                )}

                <div className="flex items-center justify-center gap-3 p-3 bg-gray-50 rounded-lg">
                  <button className={`px-4 py-2 rounded-lg text-sm font-medium transition ${billingCycle === 'monthly' ? 'bg-white shadow text-gray-900' : 'text-gray-500'}`} onClick={() => setBillingCycle('monthly')}>Aylık</button>
                  <button className={`px-4 py-2 rounded-lg text-sm font-medium transition ${billingCycle === 'yearly' ? 'bg-white shadow text-gray-900' : 'text-gray-500'}`} onClick={() => setBillingCycle('yearly')}>
                    Yıllık <span className="ml-1 text-[10px] text-green-600 font-bold">2 AY ÜCRETSİZ</span>
                  </button>
                </div>

                <div className="text-center py-2"><p className="text-4xl font-bold text-gray-900">{price}€</p><p className="text-sm text-gray-400">{period}</p></div>

                <ul className="space-y-1.5 max-h-40 overflow-y-auto">
                  {plan.features.map((f, i) => (<li key={i} className="flex items-center gap-2 text-sm text-gray-700"><CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />{f}</li>))}
                </ul>

                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="outline" onClick={() => setShowPlanModal(false)}>{t("common.cancel")}</Button>
                  <Button
                    className={isDowngrade ? 'bg-amber-500 hover:bg-amber-600 text-white' : `bg-gradient-to-r ${plan.gradient} text-white hover:opacity-90`}
                    onClick={handleChangePlan} disabled={saving}>
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
                <Input type="number" value={newRoom.floor} onChange={(e) => setNewRoom({ ...newRoom, floor: parseInt(e.target.value) || 1 })} required />
              </div>
              <div>
                <Label>Kapasite</Label>
                <Input type="number" value={newRoom.capacity} onChange={(e) => setNewRoom({ ...newRoom, capacity: parseInt(e.target.value) || 2 })} required />
              </div>
            </div>
            <div>
              <Label>Taban Fiyat</Label>
              <Input type="number" step="0.01" value={newRoom.base_price} onChange={(e) => setNewRoom({ ...newRoom, base_price: parseFloat(e.target.value) || 0 })} required />
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
