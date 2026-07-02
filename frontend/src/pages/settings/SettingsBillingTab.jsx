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

export default function SettingsBillingTab({ loadBillingHistory, billingLoading, billingHistory, setActiveTab, PLANS, formatCurrency }) {
    const { t } = useTranslation();
    return (
        <TabsContent value="billing" className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold flex items-center gap-2"><Receipt className="w-5 h-5" /> Fatura & Plan Geçmişi</h2>
              <Button variant="outline" size="sm" onClick={loadBillingHistory} disabled={billingLoading}>
                <RefreshCw className={`w-4 h-4 mr-1.5 ${billingLoading ? 'animate-spin' : ''}`} />
                Yenile
              </Button>
            </div>

            {billingLoading ? <div className="text-center py-12 text-slate-400">{t("common.loading")}</div> : billingHistory.length === 0 ? <Card>
                <CardContent className="p-12 text-center">
                  <Receipt className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                  <h3 className="text-lg font-semibold text-slate-500">Henüz işlem geçmişi yok</h3>
                  <p className="text-sm text-slate-400 mt-1 mb-4">Plan değişiklikleriniz burada listelenecek</p>
                  <Button variant="outline" size="sm" onClick={() => setActiveTab('plan')}>
                    <CreditCard className="w-4 h-4 mr-1.5" />
                    Plan değiştir
                  </Button>
                </CardContent>
              </Card> : <div className="space-y-3">
                {billingHistory.map(record => {
      const isUpgrade = record.action === 'upgrade';
      const fromPlan = PLANS[record.from_tier];
      const toPlan = PLANS[record.to_tier];
      return <Card key={record.id} className="hover:shadow-sm transition">
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
                                <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{new Date(record.created_at).toLocaleDateString('tr-TR', {
                      day: 'numeric',
                      month: 'long',
                      year: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}</span>
                                <span>{record.billing_cycle === 'yearly' ? 'Yıllık' : 'Aylık'}</span>
                                {record.user_name && <span>İşlem: {record.user_name}</span>}
                              </div>
                            </div>
                          </div>
                          <div className="text-right">
                            <p className="text-lg font-bold text-slate-900">{formatCurrency(Number(record.amount) || 0, record.currency || 'EUR', {
                  decimals: 0
                })}</p>
                            <p className="text-[10px] text-slate-500">{record.billing_cycle === 'yearly' ? 'yıl' : 'ay'}</p>
                            <div className="mt-1">
                              <StatusBadge intent={record.status === 'completed' ? 'success' : 'neutral'}>
                                {record.status === 'completed' ? 'Tamamlandı' : record.status}
                              </StatusBadge>
                            </div>
                          </div>
                        </div>
                        {record.valid_until && <div className="mt-2 pt-2 border-t text-xs text-slate-500">
                            Geçerlilik: {new Date(record.valid_until).toLocaleDateString('tr-TR')} tarihine kadar
                          </div>}
                      </CardContent>
                    </Card>;
    })}
              </div>}
          </TabsContent>
    );
}
