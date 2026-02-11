import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import {
  Settings as SettingsIcon, Users, CreditCard, Shield, Plus, Trash2,
  Building2, Zap, Crown, ArrowRight, CheckCircle2, Lock, AlertTriangle,
  User, Mail, Phone, Key, ChevronRight, Sparkles, Star
} from 'lucide-react';
import { UpgradeBanner } from '@/components/UpgradeBanner';

// ─── Plan Config ──────────────────────────────────
const PLANS = {
  basic: {
    key: 'basic', label: 'Basic', price: 79, priceYearly: 790,
    maxRooms: 15, maxUsers: 3,
    icon: Building2, gradient: 'from-emerald-500 to-green-600',
    lightBg: 'bg-emerald-50', borderColor: 'border-emerald-200',
    features: ['PMS Core', 'Takvim', 'Dashboard', 'Misafir Yönetimi', 'Kat Hizmetleri', 'Temel Raporlar', 'Mobil PMS', 'Basit Fatura'],
    description: 'Küçük oteller için (1-15 oda)',
  },
  professional: {
    key: 'professional', label: 'Professional', price: 299, priceYearly: 2990,
    maxRooms: 80, maxUsers: 15,
    icon: Zap, gradient: 'from-blue-500 to-indigo-600',
    lightBg: 'bg-blue-50', borderColor: 'border-blue-200',
    features: ['Tüm Basic özellikler', 'Channel Manager', 'Folio Yönetimi', 'Gece Denetimi', 'Gelişmiş Fatura & Finans', 'Maliyet Yönetimi', 'Gelişmiş Raporlar', 'Mobil Housekeeping', 'Rate Management', 'Booking Engine'],
    description: 'Orta ölçekli oteller (15-80 oda)',
  },
  enterprise: {
    key: 'enterprise', label: 'Enterprise', price: 799, priceYearly: 7990,
    maxRooms: null, maxUsers: null,
    icon: Crown, gradient: 'from-purple-500 to-pink-600',
    lightBg: 'bg-purple-50', borderColor: 'border-purple-200',
    features: ['Tüm Professional özellikler', 'Revenue Management (RMS)', 'AI Modülleri (7 adet)', 'Multi-Property', 'Grup Satış & MICE', 'Satış CRM', 'Loyalty Programı', 'GM Dashboard', 'API Erişimi', 'White Label', 'Audit Trail'],
    description: 'Büyük oteller ve zincirler (80+ oda)',
  },
};

const ROLE_LABELS = {
  admin: { label: 'Yönetici', color: 'bg-blue-100 text-blue-800' },
  supervisor: { label: 'Süpervizör', color: 'bg-green-100 text-green-800' },
  front_desk: { label: 'Resepsiyon', color: 'bg-yellow-100 text-yellow-800' },
  housekeeping: { label: 'Kat Hizmetleri', color: 'bg-orange-100 text-orange-800' },
  finance: { label: 'Muhasebe', color: 'bg-pink-100 text-pink-800' },
  sales: { label: 'Satış', color: 'bg-indigo-100 text-indigo-800' },
  revenue: { label: 'Revenue', color: 'bg-teal-100 text-teal-800' },
  maintenance: { label: 'Teknik', color: 'bg-gray-100 text-gray-800' },
  fnb: { label: 'F&B', color: 'bg-red-100 text-red-800' },
  spa: { label: 'Spa', color: 'bg-violet-100 text-violet-800' },
  concierge: { label: 'Concierge', color: 'bg-cyan-100 text-cyan-800' },
  night_auditor: { label: 'Gece Denetçisi', color: 'bg-slate-100 text-slate-800' },
  staff: { label: 'Personel', color: 'bg-neutral-100 text-neutral-800' },
  super_admin: { label: 'Super Admin', color: 'bg-purple-100 text-purple-800' },
};

const Settings = ({ user, tenant, onLogout }) => {
  const [activeTab, setActiveTab] = useState('team');

  // Team state
  const [team, setTeam] = useState([]);
  const [teamLoading, setTeamLoading] = useState(true);
  const [teamMeta, setTeamMeta] = useState({ tier: 'basic', allowed_roles: ['admin'], max_users: 3, can_add: true });
  const [showAddModal, setShowAddModal] = useState(false);
  const [newMember, setNewMember] = useState({ email: '', name: '', phone: '', role: 'front_desk', password: '' });
  const [saving, setSaving] = useState(false);

  // Subscription state
  const [subscription, setSubscription] = useState(null);
  const [billingCycle, setBillingCycle] = useState('monthly');
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [selectedUpgradePlan, setSelectedUpgradePlan] = useState(null);

  const currentTier = useMemo(() => {
    const t = tenant?.subscription_tier || 'basic';
    if (t === 'pro') return 'professional';
    if (t === 'ultra') return 'enterprise';
    return t;
  }, [tenant]);

  const currentPlan = PLANS[currentTier] || PLANS.basic;
  const PlanIcon = currentPlan.icon;

  // ─── Load team ─────────────────────────────────
  const loadTeam = async () => {
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
    } finally {
      setTeamLoading(false);
    }
  };

  // ─── Load subscription ─────────────────────────
  const loadSubscription = async () => {
    try {
      const res = await axios.get('/subscription/current');
      setSubscription(res.data);
    } catch (err) {
      console.error('Subscription load failed', err);
    }
  };

  useEffect(() => {
    loadTeam();
    loadSubscription();
  }, []);

  // ─── Add team member ───────────────────────────
  const handleAddMember = async () => {
    if (!newMember.email || !newMember.name || !newMember.password) {
      toast.error('Email, isim ve şifre zorunludur');
      return;
    }
    setSaving(true);
    try {
      const res = await axios.post('/hotel/team', newMember);
      toast.success(res.data?.message || 'Ekip üyesi eklendi');
      setShowAddModal(false);
      setNewMember({ email: '', name: '', phone: '', role: 'front_desk', password: '' });
      await loadTeam();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Ekip üyesi eklenemedi');
    } finally {
      setSaving(false);
    }
  };

  // ─── Update role ───────────────────────────────
  const handleUpdateRole = async (userId, newRole) => {
    try {
      await axios.patch(`/hotel/team/${userId}/role`, { role: newRole });
      toast.success('Rol güncellendi');
      await loadTeam();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Rol güncellenemedi');
    }
  };

  // ─── Remove member ─────────────────────────────
  const handleRemoveMember = async (userId, name) => {
    if (!window.confirm(`${name} adlı kullanıcıyı silmek istediğinize emin misiniz?`)) return;
    try {
      await axios.delete(`/hotel/team/${userId}`);
      toast.success('Ekip üyesi silindi');
      await loadTeam();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Silinemedi');
    }
  };

  // ─── Upgrade ───────────────────────────────────
  const handleUpgrade = async () => {
    if (!selectedUpgradePlan) return;
    setSaving(true);
    try {
      const res = await axios.post(`/subscription/upgrade?new_tier=${selectedUpgradePlan}&billing_cycle=${billingCycle}`);
      toast.success(res.data?.message || 'Plan yükseltildi!');
      setShowUpgradeModal(false);
      // Reload page to get new modules
      window.location.reload();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Yükseltme başarısız');
    } finally {
      setSaving(false);
    }
  };

  // Available upgrade tiers
  const upgradeTiers = useMemo(() => {
    const tierOrder = ['basic', 'professional', 'enterprise'];
    const currentIdx = tierOrder.indexOf(currentTier);
    return tierOrder.filter((_, i) => i > currentIdx);
  }, [currentTier]);

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="settings">
      <div className="p-4 md:p-6 space-y-4 max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <SettingsIcon className="w-6 h-6 text-gray-600" />
              Ayarlar
            </h1>
            <p className="text-sm text-gray-500 mt-1">Ekip yönetimi, plan ve abonelik ayarları</p>
          </div>
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border ${currentPlan.borderColor} ${currentPlan.lightBg}`}>
            <PlanIcon className="w-4 h-4" />
            <span className="text-sm font-semibold">{currentPlan.label}</span>
          </div>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="team" className="flex items-center gap-1.5">
              <Users className="w-4 h-4" /> Ekip
            </TabsTrigger>
            <TabsTrigger value="plan" className="flex items-center gap-1.5">
              <CreditCard className="w-4 h-4" /> Plan & Abonelik
            </TabsTrigger>
            <TabsTrigger value="hotel" className="flex items-center gap-1.5">
              <Building2 className="w-4 h-4" /> Otel Bilgileri
            </TabsTrigger>
          </TabsList>

          {/* ═══════════ TEAM TAB ═══════════ */}
          <TabsContent value="team" className="space-y-4">
            {/* Team stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Card className="p-4">
                <div className="text-2xl font-bold">{team.length}</div>
                <div className="text-xs text-gray-500">Toplam Üye</div>
              </Card>
              <Card className="p-4">
                <div className="text-2xl font-bold">{teamMeta.max_users === 999 ? '∞' : teamMeta.max_users}</div>
                <div className="text-xs text-gray-500">Max Kullanıcı</div>
              </Card>
              <Card className="p-4">
                <div className="text-2xl font-bold">{teamMeta.allowed_roles.length}</div>
                <div className="text-xs text-gray-500">Kullanılabilir Rol</div>
              </Card>
              <Card className="p-4">
                <div className="text-2xl font-bold capitalize">{teamMeta.tier}</div>
                <div className="text-xs text-gray-500">Plan</div>
              </Card>
            </div>

            {/* RBAC info banner */}
            {teamMeta.tier === 'basic' && (
              <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-amber-800">Basic planda sadece "Yönetici" rolü kullanılabilir</p>
                  <p className="text-xs text-amber-600 mt-0.5">Resepsiyon, Kat Hizmetleri, Muhasebe gibi departman rolleri için Professional plana yükseltin.</p>
                  <button onClick={() => { setActiveTab('plan'); }} className="text-xs font-bold text-amber-700 mt-1 hover:underline flex items-center gap-1">
                    Planı yükselt <ArrowRight className="w-3 h-3" />
                  </button>
                </div>
              </div>
            )}

            {/* Add member button */}
            <div className="flex justify-between items-center">
              <h2 className="text-lg font-semibold">Ekip Üyeleri</h2>
              <Button
                size="sm"
                onClick={() => setShowAddModal(true)}
                disabled={!teamMeta.can_add}
              >
                <Plus className="w-4 h-4 mr-1" />
                Üye Ekle
                {!teamMeta.can_add && <Lock className="w-3 h-3 ml-1" />}
              </Button>
            </div>

            {!teamMeta.can_add && (
              <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
                Kullanıcı limitine ulaştınız ({teamMeta.max_users}). Daha fazla üye eklemek için planınızı yükseltin.
              </div>
            )}

            {/* Team list */}
            <Card>
              <CardContent className="p-0">
                {teamLoading ? (
                  <div className="p-8 text-center text-gray-400">Yükleniyor...</div>
                ) : team.length === 0 ? (
                  <div className="p-8 text-center text-gray-400">Henüz ekip üyesi yok</div>
                ) : (
                  <div className="divide-y">
                    {team.map((member) => {
                      const roleInfo = ROLE_LABELS[member.role] || { label: member.role, color: 'bg-gray-100 text-gray-800' };
                      const isCurrentUser = member.id === user?.id;
                      return (
                        <div key={member.id} className="flex items-center justify-between px-4 py-3 hover:bg-gray-50/50">
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-gray-200 to-gray-300 flex items-center justify-center text-sm font-bold text-gray-600">
                              {(member.name || '?')[0].toUpperCase()}
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-medium text-gray-900 truncate">{member.name}</span>
                                {isCurrentUser && <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-600 border border-blue-100">Siz</span>}
                              </div>
                              <span className="text-xs text-gray-400">{member.email}</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            {/* Role selector */}
                            <select
                              value={member.role}
                              onChange={(e) => handleUpdateRole(member.id, e.target.value)}
                              disabled={isCurrentUser || member.role === 'super_admin'}
                              className={`text-xs px-2 py-1 rounded-lg border ${roleInfo.color} font-medium cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed`}
                            >
                              {teamMeta.allowed_roles.map((r) => (
                                <option key={r} value={r}>{ROLE_LABELS[r]?.label || r}</option>
                              ))}
                              {/* Show current role even if not in allowed list */}
                              {!teamMeta.allowed_roles.includes(member.role) && member.role !== 'super_admin' && (
                                <option value={member.role}>{ROLE_LABELS[member.role]?.label || member.role}</option>
                              )}
                              {member.role === 'super_admin' && (
                                <option value="super_admin">Super Admin</option>
                              )}
                            </select>
                            {/* Delete */}
                            {!isCurrentUser && member.role !== 'super_admin' && (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-red-400 hover:text-red-600 hover:bg-red-50 p-1"
                                onClick={() => handleRemoveMember(member.id, member.name)}
                              >
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

            {/* Roles info */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Shield className="w-4 h-4" /> Kullanılabilir Roller ({teamMeta.tier})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {teamMeta.allowed_roles.map((r) => {
                    const info = ROLE_LABELS[r] || { label: r, color: 'bg-gray-100 text-gray-800' };
                    return (
                      <span key={r} className={`text-xs px-2.5 py-1 rounded-full ${info.color} font-medium`}>
                        {info.label}
                      </span>
                    );
                  })}
                </div>
                {teamMeta.tier !== 'enterprise' && (
                  <p className="text-[11px] text-gray-400 mt-2">
                    Daha fazla rol için {teamMeta.tier === 'basic' ? 'Professional' : 'Enterprise'} plana yükseltin
                  </p>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* ═══════════ PLAN & SUBSCRIPTION TAB ═══════════ */}
          <TabsContent value="plan" className="space-y-4">
            {/* Current plan card */}
            <Card className={`border-2 ${currentPlan.borderColor}`}>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className={`p-3 rounded-2xl bg-gradient-to-br ${currentPlan.gradient} text-white shadow-lg`}>
                      <PlanIcon className="w-8 h-8" />
                    </div>
                    <div>
                      <h3 className="text-xl font-bold text-gray-900">{currentPlan.label} Plan</h3>
                      <p className="text-sm text-gray-500">{currentPlan.description}</p>
                      <div className="flex items-center gap-4 mt-2 text-sm">
                        <span className="text-gray-600">
                          <strong>{subscription?.rooms_count || 0}</strong> / {currentPlan.maxRooms || '∞'} oda
                        </span>
                        <span className="text-gray-600">
                          <strong>{subscription?.users_count || 0}</strong> / {currentPlan.maxUsers || '∞'} kullanıcı
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-3xl font-bold text-gray-900">{currentPlan.price}€</p>
                    <p className="text-xs text-gray-400">/ ay</p>
                    {subscription?.status && (
                      <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full mt-1 ${subscription.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                        <CheckCircle2 className="w-3 h-3" />
                        {subscription.status === 'active' ? 'Aktif' : subscription.status}
                      </span>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Plan comparison / upgrade cards */}
            {upgradeTiers.length > 0 && (
              <>
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-amber-500" />
                  Planınızı Yükseltin
                </h2>

                <div className="grid md:grid-cols-2 gap-4">
                  {upgradeTiers.map((tierKey) => {
                    const plan = PLANS[tierKey];
                    const Icon = plan.icon;
                    return (
                      <Card key={tierKey} className={`border-2 hover:shadow-lg transition-all cursor-pointer group ${plan.borderColor}`}
                        onClick={() => { setSelectedUpgradePlan(tierKey); setShowUpgradeModal(true); }}>
                        <CardContent className="p-5">
                          <div className="flex items-start justify-between mb-3">
                            <div className={`p-2.5 rounded-xl bg-gradient-to-br ${plan.gradient} text-white shadow-md`}>
                              <Icon className="w-6 h-6" />
                            </div>
                            <div className="text-right">
                              <p className="text-2xl font-bold text-gray-900">{plan.price}€</p>
                              <p className="text-[10px] text-gray-400">/ay ({plan.priceYearly}€/yıl)</p>
                            </div>
                          </div>
                          <h3 className="text-lg font-bold text-gray-900">{plan.label}</h3>
                          <p className="text-xs text-gray-500 mb-3">{plan.description}</p>
                          <ul className="space-y-1">
                            {plan.features.slice(0, 6).map((f, i) => (
                              <li key={i} className="flex items-center gap-1.5 text-xs text-gray-600">
                                <CheckCircle2 className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />
                                {f}
                              </li>
                            ))}
                            {plan.features.length > 6 && (
                              <li className="text-xs text-gray-400 pl-5">
                                +{plan.features.length - 6} daha fazla özellik
                              </li>
                            )}
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

            {/* Feature comparison */}
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Mevcut Plan Özellikleri</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                  {currentPlan.features.map((f, i) => (
                    <div key={i} className="flex items-center gap-2 text-sm text-gray-700">
                      <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />
                      {f}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {currentTier === 'enterprise' && (
              <div className="p-4 rounded-xl bg-purple-50 border border-purple-200 text-center">
                <Crown className="w-8 h-8 text-purple-600 mx-auto mb-2" />
                <p className="text-sm font-bold text-purple-800">En üst plandasınız!</p>
                <p className="text-xs text-purple-600">Tüm modüller ve özellikler aktif.</p>
              </div>
            )}
          </TabsContent>

          {/* ═══════════ HOTEL INFO TAB ═══════════ */}
          <TabsContent value="hotel" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Otel Bilgileri</CardTitle>
                <CardDescription>Otel adı, adres ve iletişim bilgileri</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <Label>Otel Adı</Label>
                  <Input value={tenant?.property_name || ''} readOnly className="bg-gray-50" />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <Label>Telefon</Label>
                    <Input value={tenant?.phone || tenant?.contact_phone || ''} readOnly className="bg-gray-50" />
                  </div>
                  <div>
                    <Label>E-posta</Label>
                    <Input value={tenant?.email || tenant?.contact_email || ''} readOnly className="bg-gray-50" />
                  </div>
                </div>
                <div>
                  <Label>Adres</Label>
                  <Input value={tenant?.address || ''} readOnly className="bg-gray-50" />
                </div>
                <div>
                  <Label>Lokasyon</Label>
                  <Input value={tenant?.location || ''} readOnly className="bg-gray-50" />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Abonelik Bilgileri</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Plan</span>
                  <span className="font-semibold">{currentPlan.label}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Durum</span>
                  <span className="font-semibold text-green-600">{subscription?.status === 'active' ? 'Aktif' : subscription?.status || '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Oda Sayısı</span>
                  <span className="font-semibold">{subscription?.rooms_count || 0} / {currentPlan.maxRooms || '∞'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Kullanıcı Sayısı</span>
                  <span className="font-semibold">{subscription?.users_count || 0} / {currentPlan.maxUsers || '∞'}</span>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>

      {/* ─── Add Member Modal ────────────────────────── */}
      <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Plus className="w-5 h-5" /> Ekip Üyesi Ekle
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>İsim *</Label>
              <Input value={newMember.name} onChange={(e) => setNewMember({ ...newMember, name: e.target.value })} placeholder="Ahmet Yılmaz" />
            </div>
            <div>
              <Label>Email *</Label>
              <Input type="email" value={newMember.email} onChange={(e) => setNewMember({ ...newMember, email: e.target.value })} placeholder="ahmet@otel.com" />
            </div>
            <div>
              <Label>Telefon</Label>
              <Input value={newMember.phone} onChange={(e) => setNewMember({ ...newMember, phone: e.target.value })} placeholder="+905551234567" />
            </div>
            <div>
              <Label>Şifre *</Label>
              <Input type="password" value={newMember.password} onChange={(e) => setNewMember({ ...newMember, password: e.target.value })} placeholder="Minimum 6 karakter" />
            </div>
            <div>
              <Label>Rol</Label>
              <select
                value={newMember.role}
                onChange={(e) => setNewMember({ ...newMember, role: e.target.value })}
                className="w-full border rounded-md px-3 py-2 text-sm"
              >
                {teamMeta.allowed_roles.map((r) => (
                  <option key={r} value={r}>{ROLE_LABELS[r]?.label || r}</option>
                ))}
              </select>
              {teamMeta.tier === 'basic' && (
                <p className="text-[11px] text-amber-600 mt-1">Basic planda sadece Yönetici rolü kullanılabilir</p>
              )}
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowAddModal(false)}>İptal</Button>
              <Button onClick={handleAddMember} disabled={saving}>
                {saving ? 'Ekleniyor...' : 'Ekle'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* ─── Upgrade Modal ───────────────────────────── */}
      <Dialog open={showUpgradeModal} onOpenChange={setShowUpgradeModal}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-amber-500" /> Plan Yükselt
            </DialogTitle>
          </DialogHeader>
          {selectedUpgradePlan && PLANS[selectedUpgradePlan] && (() => {
            const plan = PLANS[selectedUpgradePlan];
            const Icon = plan.icon;
            const price = billingCycle === 'yearly' ? plan.priceYearly : plan.price;
            const period = billingCycle === 'yearly' ? '/yıl' : '/ay';
            return (
              <div className="space-y-4">
                <div className={`p-4 rounded-xl ${plan.lightBg} border ${plan.borderColor}`}>
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-xl bg-gradient-to-br ${plan.gradient} text-white`}>
                      <Icon className="w-6 h-6" />
                    </div>
                    <div>
                      <h3 className="font-bold text-lg">{plan.label}</h3>
                      <p className="text-xs text-gray-500">{plan.description}</p>
                    </div>
                  </div>
                </div>

                {/* Billing cycle toggle */}
                <div className="flex items-center justify-center gap-3 p-3 bg-gray-50 rounded-lg">
                  <button
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition ${billingCycle === 'monthly' ? 'bg-white shadow text-gray-900' : 'text-gray-500'}`}
                    onClick={() => setBillingCycle('monthly')}
                  >Aylık</button>
                  <button
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition ${billingCycle === 'yearly' ? 'bg-white shadow text-gray-900' : 'text-gray-500'}`}
                    onClick={() => setBillingCycle('yearly')}
                  >
                    Yıllık
                    <span className="ml-1 text-[10px] text-green-600 font-bold">2 AY ÜCRETSİZ</span>
                  </button>
                </div>

                <div className="text-center py-2">
                  <p className="text-4xl font-bold text-gray-900">{price}€</p>
                  <p className="text-sm text-gray-400">{period}</p>
                </div>

                <ul className="space-y-1.5">
                  {plan.features.map((f, i) => (
                    <li key={i} className="flex items-center gap-2 text-sm text-gray-700">
                      <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />
                      {f}
                    </li>
                  ))}
                </ul>

                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="outline" onClick={() => setShowUpgradeModal(false)}>İptal</Button>
                  <Button
                    className={`bg-gradient-to-r ${plan.gradient} text-white hover:opacity-90`}
                    onClick={handleUpgrade}
                    disabled={saving}
                  >
                    {saving ? 'İşleniyor...' : `${plan.label} Plana Yükselt`}
                  </Button>
                </div>
              </div>
            );
          })()}
        </DialogContent>
      </Dialog>
    </Layout>
  );
};

export default Settings;
