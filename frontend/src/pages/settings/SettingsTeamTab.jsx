import { useTranslation } from 'react-i18next';
import React, { useState, useEffect, useMemo, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
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

export default function SettingsTeamTab({ Users, team, UserCheck, teamMeta, Shield, Crown, setActiveTab, setNewMember, setShowAddModal, teamLoading, getRoleLabel, isSameUser, handleUpdateRole, handleRemoveMember, isAdmin, grLoading, grSettings, toggleGuestRequestRole, saveGuestRequestSettings, grSaving }) {
    const { t } = useTranslation();
    return (
        <TabsContent value="team" className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <KpiCard icon={Users} label="Toplam Üye" value={team.length} intent="default" className="shadow-sm rounded-xl border-slate-200" />
              <KpiCard icon={UserCheck} label="Max Kullanıcı" value={teamMeta.max_users === 999 ? '∞' : teamMeta.max_users} intent="info" className="shadow-sm rounded-xl border-slate-200" />
              <KpiCard icon={Shield} label="Kullanılabilir Rol" value={teamMeta.allowed_roles.length} intent="success" className="shadow-sm rounded-xl border-slate-200" />
              <KpiCard icon={Crown} label="Plan" value={<span className="capitalize">{teamMeta.tier}</span>} intent="neutral" className="shadow-sm rounded-xl border-slate-200" />
            </div>

            {teamMeta.tier === 'basic' && <div className="p-4 rounded-xl bg-amber-50/80 border border-amber-200/60 flex items-start gap-3 shadow-sm">
                <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5 drop-shadow-sm" />
                <div>
                  <p className="text-sm font-semibold text-amber-900">Basic planda sadece "Yönetici" rolü kullanılabilir</p>
                  <p className="text-xs text-amber-700/80 mt-1 font-medium">Departman rolleri için Professional plana yükseltin.</p>
                  <button onClick={() => setActiveTab('plan')} className="text-[13px] font-bold text-amber-800 mt-2 hover:text-amber-950 flex items-center gap-1.5 transition-colors">Planı yükselt <ArrowRight className="w-3.5 h-3.5" /></button>
                </div>
              </div>}

            {!teamMeta.can_add && <div className="p-4 rounded-xl bg-rose-50/80 border border-rose-200/60 flex items-start gap-3 shadow-sm text-sm text-rose-800 font-medium">
                <AlertTriangle className="w-5 h-5 text-rose-600 flex-shrink-0 drop-shadow-sm" />
                <div>Kullanıcı limitine ulaşıldı ({teamMeta.max_users}). Lütfen planınızı yükseltin.</div>
              </div>}

            <Card className="rounded-xl shadow-sm border-slate-200 overflow-hidden">
              <CardHeader className="flex flex-row items-center justify-between bg-slate-50/50 border-b border-slate-100 pb-4 pt-5 px-5">
                <div>
                  <CardTitle className="text-lg font-bold text-slate-800 flex items-center gap-2">
                    <Users className="w-5 h-5 text-slate-500" />
                    {t('settings.teamMembers')}
                  </CardTitle>
                  <CardDescription className="text-xs mt-1">Ekip üyelerinizi ve yetkilerini yönetin</CardDescription>
                </div>
                <Button size="sm" className="shadow-sm" onClick={() => {
        setNewMember({
          email: '',
          name: '',
          phone: '',
          role: teamMeta.allowed_roles[0] || 'admin',
          password: ''
        });
        setShowAddModal(true);
      }} disabled={!teamMeta.can_add}>
                  <Plus className="w-4 h-4 mr-1.5" /> Üye Ekle {!teamMeta.can_add && <Lock className="w-3 h-3 ml-1.5 opacity-70" />}
                </Button>
              </CardHeader>
              <CardContent className="p-0">
                {teamLoading ? <div className="p-10 text-center text-slate-400 font-medium">{t("common.loading")}</div> : team.length === 0 ? <div className="p-10 text-center text-slate-400 font-medium">Henüz ekip üyesi yok</div> : <div className="divide-y divide-slate-100">
                    {team.map(member => {
          const roleInfo = getRoleLabel(member.role);
          const isMe = isSameUser(member);
          const editDisabled = isMe || member.role === 'super_admin';
          const allowedForSelect = teamMeta.allowed_roles.includes(member.role) ? teamMeta.allowed_roles : [...teamMeta.allowed_roles, member.role];
          return <div key={member.id} className="flex flex-col sm:flex-row sm:items-center justify-between px-5 py-3.5 hover:bg-slate-50/80 transition-colors gap-3 sm:gap-0">
                          <div className="flex items-center gap-3.5 min-w-0">
                            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-slate-100 to-slate-200 border border-slate-300/50 flex items-center justify-center text-sm font-bold text-slate-600 shadow-sm shrink-0">
                              {(member.name || '?')[0].toUpperCase()}
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2.5">
                                <span className="text-[15px] font-semibold text-slate-800 truncate">{member.name}</span>
                                {isMe && <Badge variant="secondary" className="bg-sky-100 text-sky-700 hover:bg-sky-100 font-semibold px-2 py-0 border-0">Siz</Badge>}
                              </div>
                              <span className="text-[13px] text-slate-500 font-medium truncate block">{member.email}</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-3 sm:pl-4">
                            {member.role === 'super_admin' ? <div className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 rounded-md border border-slate-200">
                                <Crown className="w-3.5 h-3.5 text-slate-500" />
                                <span className="text-xs font-semibold text-slate-700">Super Admin</span>
                              </div> : <Select value={member.role} onValueChange={v => handleUpdateRole(member.id, v)} disabled={editDisabled}>
                                <SelectTrigger className={`h-9 w-[170px] text-[13px] font-semibold ${roleInfo.color} shadow-sm disabled:opacity-60 disabled:cursor-not-allowed transition-all focus:ring-2`}>
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent className="shadow-lg rounded-xl border-slate-200">
                                  {allowedForSelect.map(r => <SelectItem key={r} value={r} className="text-[13px] font-medium focus:bg-slate-50">{getRoleLabel(r).label}</SelectItem>)}
                                </SelectContent>
                              </Select>}
                            {!isMe && member.role !== 'super_admin' && <Button variant="ghost" size="icon" className="text-rose-400 hover:text-rose-600 hover:bg-rose-50 h-9 w-9 rounded-lg transition-colors" onClick={() => handleRemoveMember(member.id, member.name)}>
                                <Trash2 className="w-4 h-4" />
                              </Button>}
                          </div>
                        </div>;
        })}
                  </div>}
              </CardContent>
            </Card>

            <Card className="rounded-xl shadow-sm border-slate-200">
              <CardHeader className="pb-3 pt-5 px-5">
                <CardTitle className="text-[15px] font-bold text-slate-800 flex items-center gap-2">
                  <Shield className="w-4.5 h-4.5 text-slate-500" /> Kullanılabilir Roller ({teamMeta.tier})
                </CardTitle>
                <CardDescription className="text-xs">Sahip olduğunuz plana göre ekibinize atayabileceğiniz yetki rolleri</CardDescription>
              </CardHeader>
              <CardContent className="px-5 pb-5">
                <div className="flex flex-wrap gap-2.5">
                  {teamMeta.allowed_roles.map(r => {
          const info = getRoleLabel(r);
          return <span key={r} className={`text-xs px-3 py-1.5 rounded-full ${info.color} font-bold shadow-sm border`}>{info.label}</span>;
        })}
                </div>
                {teamMeta.tier !== 'enterprise' && <p className="text-xs font-medium text-slate-500 mt-4 bg-slate-50 p-2.5 rounded-lg border border-slate-100">Daha fazla rol ve departman ayrımı için {teamMeta.tier === 'basic' ? 'Professional' : 'Enterprise'} plana yükseltin.</p>}
              </CardContent>
            </Card>

            {isAdmin && <Card data-testid="guest-request-visibility-card" className="rounded-xl shadow-sm border-slate-200">
                <CardHeader className="pb-3 pt-5 px-5">
                  <CardTitle className="text-[15px] font-bold text-slate-800 flex items-center gap-2">
                    <MessageSquare className="w-4.5 h-4.5 text-slate-500" /> Misafir Talepleri Görünürlüğü
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Oda QR taleplerini personel sohbetinde hangi rollerin göreceğini seçin. Yönetici rolleri her zaman görür.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4 px-5 pb-5">
                  {grLoading ? <div className="text-sm font-medium text-slate-400">{t('common.loading')}</div> : grSettings.available_roles.length === 0 ? <div className="text-sm font-medium text-slate-400">Seçilebilir rol bulunamadı</div> : <>
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {grSettings.available_roles.map(r => {
            const always = grSettings.always_allowed.includes(r.value);
            const checked = always || grSettings.visible_roles.includes(r.value);
            return <label key={r.value} className={`flex items-center gap-3 p-3 rounded-xl border transition-all duration-200 ${checked ? 'border-sky-200 bg-sky-50/50 shadow-sm' : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'} ${always ? 'opacity-70 cursor-not-allowed grayscale-[30%]' : 'cursor-pointer'}`}>
                              <Checkbox checked={checked} disabled={always} onCheckedChange={v => toggleGuestRequestRole(r.value, v === true)} data-testid={`gr-role-${r.value}`} className={checked && !always ? 'border-sky-500 bg-sky-500 text-white' : ''} />
                              <span className="text-[13px] font-bold text-slate-800">{r.label}</span>
                              {always && <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 ml-auto bg-slate-100 px-2 py-0.5 rounded-md">Her zaman</span>}
                            </label>;
          })}
                      </div>
                      <div className="flex justify-end pt-2 border-t border-slate-100">
                        <Button size="sm" onClick={saveGuestRequestSettings} disabled={grSaving} data-testid="button-save-gr-visibility" className="shadow-sm">
                          {grSaving ? <RefreshCw className="w-4 h-4 mr-1.5 animate-spin" /> : <Save className="w-4 h-4 mr-1.5" />}
                          Değişiklikleri Kaydet
                        </Button>
                      </div>
                    </>}
                </CardContent>
              </Card>}
          </TabsContent>
    );
}
