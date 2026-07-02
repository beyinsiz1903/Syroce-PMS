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

export default function SettingsPlanTab({ currentPlan, subscription, fmtPlanPrice, CheckCircle2, upgradeTiers, PLANS, openPlanModal, downgradeTiers, currentTier }) {
    const { t } = useTranslation();
    const PlanIcon = currentPlan.icon;
    return (
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
                    {subscription?.status && <div className="mt-1">
                        <StatusBadge intent={subscription.status === 'active' ? 'success' : 'danger'} icon={CheckCircle2}>
                          {subscription.status === 'active' ? 'Aktif' : subscription.status}
                        </StatusBadge>
                      </div>}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Upgrade options */}
            {upgradeTiers.length > 0 && <>
                <h2 className="text-lg font-semibold flex items-center gap-2"><Sparkles className="w-5 h-5 text-amber-500" /> Yükselt</h2>
                <div className="grid md:grid-cols-2 gap-4">
                  {upgradeTiers.map(tierKey => {
        const plan = PLANS[tierKey];
        const Icon = plan.icon;
        return <Card key={tierKey} className={`border-2 hover:shadow-lg transition-all cursor-pointer group ${plan.borderColor}`} onClick={() => openPlanModal(tierKey, 'upgrade')}>
                        <CardContent className="p-5">
                          <div className="flex items-start justify-between mb-3">
                            <div className={`p-2.5 rounded-xl ${plan.iconBg} ${plan.iconText}`}><Icon className="w-6 h-6" /></div>
                            <div className="text-right"><p className="text-2xl font-bold text-slate-900">{fmtPlanPrice(plan.priceEUR)}</p><p className="text-[10px] text-slate-500">/ay</p></div>
                          </div>
                          <h3 className="text-lg font-bold text-slate-900">{plan.label}</h3>
                          <p className="text-xs text-slate-500 mb-3">{plan.description}</p>
                          <ul className="space-y-1">
                            {plan.features.slice(0, 5).map((f, i) => <li key={f.id || i} className="flex items-center gap-1.5 text-xs text-slate-600"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />{f}</li>)}
                            {plan.features.length > 5 && <li className="text-xs text-slate-400 pl-5">+{plan.features.length - 5} daha</li>}
                          </ul>
                          <Button type="button" className="mt-4 w-full" onClick={e => {
              e.stopPropagation();
              openPlanModal(tierKey, 'upgrade');
            }}>
                            Yükselt <ArrowRight className="w-4 h-4 ml-1" />
                          </Button>
                        </CardContent>
                      </Card>;
      })}
                </div>
              </>}

            {/* Downgrade options */}
            {downgradeTiers.length > 0 && <>
                <h2 className="text-sm font-medium text-slate-500 flex items-center gap-2 mt-6"><ArrowDown className="w-4 h-4" /> Plan Düşür</h2>
                <div className="grid md:grid-cols-2 gap-3">
                  {downgradeTiers.map(tierKey => {
        const plan = PLANS[tierKey];
        const Icon = plan.icon;
        return <Card key={tierKey} className="border border-slate-200 hover:border-slate-300 transition cursor-pointer" onClick={() => openPlanModal(tierKey, 'downgrade')}>
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
                      </Card>;
      })}
                </div>
              </>}

            {/* Current features */}
            <Card>
              <CardHeader><CardTitle className="text-sm">{t('settings.planFeatures')}</CardTitle></CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                  {currentPlan.features.map((f, i) => <div key={f.id || i} className="flex items-center gap-2 text-sm text-slate-700"><CheckCircle2 className="w-4 h-4 text-emerald-500 flex-shrink-0" />{f}</div>)}
                </div>
              </CardContent>
            </Card>

            {currentTier === 'enterprise' && <div className="p-4 rounded-xl bg-indigo-50 border border-indigo-200 text-center">
                <Crown className="w-8 h-8 text-indigo-600 mx-auto mb-2" />
                <p className="text-sm font-bold text-indigo-800">En üst plandasınız!</p>
                <p className="text-xs text-indigo-700">Tüm modüller ve özellikler aktif.</p>
              </div>}
          </TabsContent>
    );
}
