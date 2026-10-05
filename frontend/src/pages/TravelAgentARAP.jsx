import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Link } from 'react-router-dom';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  Building2, DollarSign, TrendingUp, TrendingDown, AlertTriangle,
  Search, CreditCard, FileText, Clock, CheckCircle2, XCircle,
  ChevronDown, ChevronRight, Loader2, Plus, Calendar, Info, ArrowRight,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';
import { paymentMethodLabel } from '@/lib/accountingLabels';
import { moneyInputProps, parseMoneyInput } from '@/lib/moneyInput';

const CURRENCIES = ['TRY', 'EUR', 'USD', 'GBP'];

const TravelAgentARAP = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const tenantCurrency = cachedTenantCurrency();
  const [activeTab, setActiveTab] = useState('overview');

  const [summary, setSummary] = useState(null);
  const [aging, setAging] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  const [selectedAgency, setSelectedAgency] = useState(null);
  const [agencyTxns, setAgencyTxns] = useState(null);
  const [txnLoading, setTxnLoading] = useState(false);

  const [statement, setStatement] = useState(null);
  const [stmtLoading, setStmtLoading] = useState(false);

  const [paymentPlans, setPaymentPlans] = useState([]);
  const [plansLoading, setPlansLoading] = useState(false);

  const [paymentDialog, setPaymentDialog] = useState(false);
  const [paymentForm, setPaymentForm] = useState({ agency_id: '', amount: '', currency: tenantCurrency, payment_method: 'bank_transfer', reference: '', notes: '' });
  const [paymentSaving, setPaymentSaving] = useState(false);

  const [planDialog, setPlanDialog] = useState(false);
  const [planForm, setPlanForm] = useState({ agency_id: '', total_amount: '', currency: tenantCurrency, installments: 3, start_date: '', notes: '' });
  const [planSaving, setPlanSaving] = useState(false);

  const [stmtDialog, setStmtDialog] = useState(false);

  const loadSummary = useCallback(async () => {
    setLoading(true);
    try {
      const [sumRes, agingRes] = await Promise.all([
        axios.get('/agent-arap/summary'),
        axios.get('/agent-arap/aging'),
      ]);
      setSummary(sumRes.data);
      setAging(agingRes.data);
    } catch {
      toast.error(t('agentArap.loadError'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  const loadTransactions = async (agencyId) => {
    setTxnLoading(true);
    try {
      const { data } = await axios.get(`/agent-arap/transactions/${agencyId}`);
      setAgencyTxns(data);
    } catch {
      toast.error(t('agentArap.loadError'));
    } finally {
      setTxnLoading(false);
    }
  };

  const loadStatement = async (agencyId) => {
    setStmtLoading(true);
    try {
      const { data } = await axios.get(`/agent-arap/statement/${agencyId}`);
      setStatement(data);
      setStmtDialog(true);
    } catch {
      toast.error(t('agentArap.loadError'));
    } finally {
      setStmtLoading(false);
    }
  };

  const loadPlans = useCallback(async () => {
    setPlansLoading(true);
    try {
      const { data } = await axios.get('/agent-arap/payment-plans');
      setPaymentPlans(data);
    } catch {
      toast.error(t('agentArap.loadError'));
    } finally {
      setPlansLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  useEffect(() => {
    if (activeTab === 'plans') loadPlans();
  }, [activeTab, loadPlans]);

  const handleRecordPayment = async () => {
    const amount = parseMoneyInput(paymentForm.amount);
    if (!amount || amount <= 0) {
      toast.error(t('agentArap.invalidAmount'));
      return;
    }
    setPaymentSaving(true);
    try {
      await axios.post('/agent-arap/payment', {
        agency_id: paymentForm.agency_id,
        amount,
        currency: paymentForm.currency,
        payment_method: paymentForm.payment_method,
        reference: paymentForm.reference,
        notes: paymentForm.notes,
      });
      toast.success(t('agentArap.paymentRecorded'));
      setPaymentDialog(false);
      loadSummary();
      if (selectedAgency) loadTransactions(selectedAgency);
    } catch {
      toast.error(t('agentArap.paymentError'));
    } finally {
      setPaymentSaving(false);
    }
  };

  const handleCreatePlan = async () => {
    const total = parseMoneyInput(planForm.total_amount);
    if (!total || total <= 0) {
      toast.error(t('agentArap.invalidAmount'));
      return;
    }
    if (!planForm.start_date) {
      toast.error(t('agentArap.selectDate'));
      return;
    }
    setPlanSaving(true);
    try {
      await axios.post('/agent-arap/payment-plans', {
        agency_id: planForm.agency_id,
        total_amount: total,
        currency: planForm.currency,
        installments: planForm.installments,
        start_date: planForm.start_date,
        notes: planForm.notes,
      });
      toast.success(t('agentArap.planCreated'));
      setPlanDialog(false);
      loadPlans();
    } catch {
      toast.error(t('agentArap.planError'));
    } finally {
      setPlanSaving(false);
    }
  };

  const handleMarkInstallmentPaid = async (planId, idx) => {
    try {
      await axios.put('/agent-arap/payment-plans/installment', {
        plan_id: planId,
        installment_index: idx,
        paid: true,
      });
      toast.success(t('agentArap.installmentPaid'));
      loadPlans();
      loadSummary();
    } catch {
      toast.error(t('agentArap.paymentError'));
    }
  };

  const preferredCurrency = (breakdown = {}) => {
    const currencies = Object.entries(breakdown).filter(([, value]) => Math.abs(Number(value || 0)) > 0).map(([currency]) => currency);
    return currencies.length === 1 ? currencies[0] : summary?.currency || tenantCurrency;
  };

  const money = (value, currency = summary?.currency || tenantCurrency) => formatCurrency(value || 0, currency, { decimals: 2 });
  const moneyBreakdown = (breakdown, fallback = 0, currency = summary?.currency || tenantCurrency) => {
    const rows = Object.entries(breakdown || {}).filter(([, value]) => Math.abs(Number(value || 0)) > 0);
    return rows.length
      ? rows.sort(([left], [right]) => left.localeCompare(right)).map(([code, value]) => money(value, code)).join(' · ')
      : money(fallback, currency);
  };

  const openPaymentDialog = (agency) => {
    setPaymentForm({ agency_id: agency.agency_id, amount: '', currency: preferredCurrency(agency.balance_by_currency), payment_method: 'bank_transfer', reference: '', notes: '' });
    setPaymentDialog(true);
  };

  const openPlanDialog = (agency) => {
    const currency = preferredCurrency(agency.balance_by_currency);
    const balance = Number(agency.balance_by_currency?.[currency] ?? agency.balance ?? 0);
    setPlanForm({ agency_id: agency.agency_id, total_amount: balance > 0 ? String(balance) : '', currency, installments: 3, start_date: new Date().toISOString().split('T')[0], notes: '' });
    setPlanDialog(true);
  };

  const filteredAgencies = (summary?.agencies || []).filter(a => {
    const term = searchTerm.toLowerCase();
    return !term || a.agency_name.toLowerCase().includes(term) || (a.contact_name || '').toLowerCase().includes(term);
  });

  const agingBuckets = aging ? [
    { key: 'current', label: t('agentArap.current'), color: 'bg-green-100 text-green-800', data: aging.current },
    { key: '30_days', label: t('agentArap.days30'), color: 'bg-yellow-100 text-yellow-800', data: aging['30_days'] },
    { key: '60_days', label: t('agentArap.days60'), color: 'bg-amber-100 text-amber-800', data: aging['60_days'] },
    { key: '90_days', label: t('agentArap.days90'), color: 'bg-red-100 text-red-800', data: aging['90_days'] },
    { key: 'over_90', label: t('agentArap.over90'), color: 'bg-red-200 text-red-900', data: aging.over_90 },
  ] : [];

  if (loading && !summary) {
    return (
      <>
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
        </div>
      </>
    );
  }

  return (
    <>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold">{t('agentArap.title')}</h1>
          <p className="text-muted-foreground">{t('agentArap.subtitle')}</p>
        </div>

        <div className="rounded-xl border border-blue-200 bg-blue-50/70 p-4 dark:border-blue-800 dark:bg-blue-950/30">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 rounded-lg bg-white p-2 text-blue-700 shadow-sm dark:bg-slate-900 dark:text-blue-300">
                <Info className="h-4 w-4" />
              </div>
              <div className="space-y-1">
                <p className="font-semibold text-slate-900 dark:text-slate-100">Operasyon ve finans ekranı</p>
                <p className="max-w-4xl text-sm leading-6 text-slate-600 dark:text-slate-300">
                  Bu ekran, Acente Yönetimi'nde tanımlanan B2B acentelere bağlı rezervasyonların komisyonunu, yapılan ödemeleri, taksit planlarını ve vade yaşlandırmasını yönetir. HotelRunner üzerinden gelen Expedia, Agoda gibi OTA rezervasyonları burada otomatik cari hesap oluşturmaz.
                </p>
              </div>
            </div>
            <Button asChild variant="outline" className="shrink-0 bg-white dark:bg-slate-900">
              <Link to="/agency-management">
                Acente Yönetimi <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
          </div>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="overview">{t('agentArap.tabOverview')}</TabsTrigger>
            <TabsTrigger value="ledger">{t('agentArap.tabLedger')}</TabsTrigger>
            <TabsTrigger value="plans">{t('agentArap.tabPlans')}</TabsTrigger>
            <TabsTrigger value="aging">{t('agentArap.tabAging')}</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-6">
            {summary && (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <Card>
                    <CardContent className="pt-4">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Building2 className="w-4 h-4" />
                        {t('agentArap.totalAgencies')}
                      </div>
                      <div className="text-2xl font-bold mt-1">{summary.total_agencies}</div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-4">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <TrendingUp className="w-4 h-4 text-red-500" />
                        {t('agentArap.totalReceivable')}
                      </div>
                      <div className="text-2xl font-bold mt-1 text-red-600">{moneyBreakdown(summary.total_receivable_by_currency, summary.total_receivable)}</div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-4">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <DollarSign className="w-4 h-4 text-green-500" />
                        {t('agentArap.totalPaid')}
                      </div>
                      <div className="text-2xl font-bold mt-1 text-green-600">{moneyBreakdown(summary.total_paid_by_currency, summary.total_paid)}</div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-4">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <TrendingDown className="w-4 h-4 text-blue-500" />
                        {t('agentArap.collectionRate')}
                      </div>
                      <div className="text-2xl font-bold mt-1">{summary.collection_rate}%</div>
                    </CardContent>
                  </Card>
                </div>

                <div className="grid md:grid-cols-3 gap-4">
                  <Card>
                    <CardContent className="pt-4">
                      <div className="text-sm text-muted-foreground">{t('agentArap.totalBookingsRevenue')}</div>
                      <div className="text-xl font-bold">{moneyBreakdown(summary.total_bookings_revenue_by_currency, summary.total_bookings_revenue)}</div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-4">
                      <div className="text-sm text-muted-foreground">{t('agentArap.totalCommission')}</div>
                      <div className="text-xl font-bold">{moneyBreakdown(summary.total_commission_earned_by_currency, summary.total_commission_earned)}</div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-4">
                      <div className="text-sm text-muted-foreground">{t('agentArap.overdueAccounts')}</div>
                      <div className="flex gap-4 mt-1">
                        <span className="text-sm">30d: <strong className="text-yellow-600">{summary.overdue_30_count}</strong></span>
                        <span className="text-sm">60d: <strong className="text-amber-600">{summary.overdue_60_count}</strong></span>
                        <span className="text-sm">90d: <strong className="text-red-600">{summary.overdue_90_count}</strong></span>
                      </div>
                    </CardContent>
                  </Card>
                </div>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">{t('agentArap.agencySummary')}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b text-left">
                            <th className="py-2 px-3">{t('agentArap.agency')}</th>
                            <th className="py-2 px-3 text-right">{t('agentArap.bookings')}</th>
                            <th className="py-2 px-3 text-right">{t('agentArap.revenue')}</th>
                            <th className="py-2 px-3 text-right">{t('agentArap.commission')}</th>
                            <th className="py-2 px-3 text-right">{t('agentArap.paid')}</th>
                            <th className="py-2 px-3 text-right">{t('agentArap.balance')}</th>
                            <th className="py-2 px-3">{t('agentArap.status')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(summary.agencies || []).map(a => (
                            <tr key={a.agency_id} className="border-b hover:bg-muted/50">
                              <td className="py-2 px-3 font-medium">{a.agency_name}</td>
                              <td className="py-2 px-3 text-right">{a.total_bookings}</td>
                              <td className="py-2 px-3 text-right">{moneyBreakdown(a.total_bookings_revenue_by_currency, a.total_bookings_revenue, a.currency)}</td>
                              <td className="py-2 px-3 text-right">{moneyBreakdown(a.total_commission_owed_by_currency, a.total_commission_owed, a.currency)}</td>
                              <td className="py-2 px-3 text-right text-green-600">{moneyBreakdown(a.total_paid_by_currency, a.total_paid, a.currency)}</td>
                              <td className="py-2 px-3 text-right font-bold text-red-600">{moneyBreakdown(a.balance_by_currency, a.balance, a.currency)}</td>
                              <td className="py-2 px-3">
                                {a.days_outstanding > 90 ? (
                                  <Badge variant="destructive">{t('agentArap.overdue')}</Badge>
                                ) : a.days_outstanding > 30 ? (
                                  <Badge className="bg-yellow-100 text-yellow-800">{t('agentArap.pending')}</Badge>
                                ) : (
                                  <Badge className="bg-green-100 text-green-800">{t('agentArap.current')}</Badge>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              </>
            )}
          </TabsContent>

          <TabsContent value="ledger" className="space-y-4">
            <div className="flex items-center gap-3">
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder={t('agentArap.searchAgency')}
                  value={searchTerm}
                  onChange={e => setSearchTerm(e.target.value)}
                  className="pl-9"
                />
              </div>
            </div>

            <div className="space-y-3">
              {filteredAgencies.map(a => (
                <Card key={a.agency_id} className="overflow-hidden">
                  <div
                    className="flex items-center justify-between p-4 cursor-pointer hover:bg-muted/50"
                    onClick={() => {
                      if (selectedAgency === a.agency_id) {
                        setSelectedAgency(null);
                      } else {
                        setSelectedAgency(a.agency_id);
                        loadTransactions(a.agency_id);
                      }
                    }}
                  >
                    <div className="flex items-center gap-3">
                      {selectedAgency === a.agency_id ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                      <Building2 className="w-5 h-5 text-blue-500" />
                      <div>
                        <div className="font-medium">{a.agency_name}</div>
                        <div className="text-xs text-muted-foreground">
                          {a.contact_name} • {a.contact_email} • {t('agentArap.commissionRate')}: {a.commission_rate}%
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <div className="text-sm text-muted-foreground">{t('agentArap.balance')}</div>
                        <div className={`font-bold ${Object.values(a.balance_by_currency || {}).some(value => Number(value) > 0) || a.balance > 0 ? 'text-red-600' : 'text-green-600'}`}>{moneyBreakdown(a.balance_by_currency, a.balance, a.currency)}</div>
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" onClick={e => { e.stopPropagation(); openPaymentDialog(a); }}>
                          <CreditCard className="w-3 h-3 mr-1" />{t('agentArap.recordPayment')}
                        </Button>
                        <Button size="sm" variant="outline" onClick={e => { e.stopPropagation(); loadStatement(a.agency_id); }}>
                          <FileText className="w-3 h-3 mr-1" />{t('agentArap.statement')}
                        </Button>
                        {(Object.values(a.balance_by_currency || {}).some(value => Number(value) > 0) || a.balance > 0) && (
                          <Button size="sm" variant="outline" onClick={e => { e.stopPropagation(); openPlanDialog(a); }}>
                            <Calendar className="w-3 h-3 mr-1" />{t('agentArap.createPlan')}
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>

                  {selectedAgency === a.agency_id && (
                    <div className="border-t p-4 bg-muted/30">
                      {txnLoading ? (
                        <div className="flex justify-center py-4"><Loader2 className="w-5 h-5 animate-spin" /></div>
                      ) : agencyTxns ? (
                        <div className="space-y-4">
                          <div>
                            <h4 className="font-medium mb-2">{t('agentArap.commissionEntries')}</h4>
                            <div className="overflow-x-auto">
                              <table className="w-full text-sm">
                                <thead>
                                  <tr className="border-b text-left">
                                    <th className="py-1 px-2">{t('agentArap.guest')}</th>
                                    <th className="py-1 px-2">{t('agentArap.dates')}</th>
                                    <th className="py-1 px-2 text-right">{t('agentArap.bookingAmount')}</th>
                                    <th className="py-1 px-2 text-right">{t('agentArap.commissionAmount')}</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {(agencyTxns.commission_entries || []).slice(0, 10).map(ce => (
                                    <tr key={ce.id} className="border-b">
                                      <td className="py-1 px-2">{ce.guest_name}</td>
                                      <td className="py-1 px-2 text-xs">{ce.check_in} → {ce.check_out}</td>
                                      <td className="py-1 px-2 text-right">{money(ce.booking_amount, ce.currency)}</td>
                                      <td className="py-1 px-2 text-right text-red-600">{money(ce.amount, ce.currency)}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>

                          {(agencyTxns.transactions || []).length > 0 && (
                            <div>
                              <h4 className="font-medium mb-2">{t('agentArap.paymentHistory')}</h4>
                              <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                  <thead>
                                    <tr className="border-b text-left">
                                      <th className="py-1 px-2">{t('agentArap.date')}</th>
                                      <th className="py-1 px-2">{t('agentArap.type')}</th>
                                      <th className="py-1 px-2 text-right">{t('agentArap.amount')}</th>
                                      <th className="py-1 px-2">{t('agentArap.method')}</th>
                                      <th className="py-1 px-2">{t('agentArap.reference')}</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {agencyTxns.transactions.map(tx => (
                                      <tr key={tx.id} className="border-b">
                                        <td className="py-1 px-2 text-xs">{(tx.created_at || '').slice(0, 10)}</td>
                                        <td className="py-1 px-2">
                                          <Badge variant={tx.type === 'payment' ? 'default' : 'secondary'}>
                                            {tx.type === 'payment' ? t('agentArap.payment') : t('agentArap.adjustment')}
                                          </Badge>
                                        </td>
                                        <td className="py-1 px-2 text-right text-green-600">{money(tx.amount, tx.currency)}</td>
                                        <td className="py-1 px-2 text-xs">{paymentMethodLabel(t, tx.payment_method)}</td>
                                        <td className="py-1 px-2 text-xs">{tx.reference}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          )}
                        </div>
                      ) : null}
                    </div>
                  )}
                </Card>
              ))}
              {filteredAgencies.length === 0 && (
                <div className="text-center py-8 text-muted-foreground">{t('agentArap.noAgencies')}</div>
              )}
            </div>
          </TabsContent>

          <TabsContent value="plans" className="space-y-4">
            {plansLoading ? (
              <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin" /></div>
            ) : paymentPlans.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">{t('agentArap.noPlans')}</div>
            ) : (
              paymentPlans.map(plan => (
                <Card key={plan.id}>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base">{plan.agency_name}</CardTitle>
                      <Badge variant={plan.status === 'completed' ? 'default' : plan.status === 'active' ? 'secondary' : 'destructive'}>
                        {plan.status === 'completed' ? t('agentArap.completed') : plan.status === 'active' ? t('agentArap.active') : plan.status}
                      </Badge>
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {t('agentArap.totalAmount')}: {money(plan.total_amount, plan.currency)} • {plan.installment_count} {t('agentArap.installments')}
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {(plan.installments || []).map((inst, idx) => (
                        <div key={idx} className="flex items-center justify-between py-2 px-3 rounded border bg-muted/20">
                          <div className="flex items-center gap-3">
                            {inst.paid ? (
                              <CheckCircle2 className="w-4 h-4 text-green-500" />
                            ) : (
                              <Clock className="w-4 h-4 text-muted-foreground" />
                            )}
                            <div>
                              <div className="text-sm font-medium">
                                {t('agentArap.installment')} #{idx + 1}
                              </div>
                              <div className="text-xs text-muted-foreground">
                                {t('agentArap.dueDate')}: {inst.due_date}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-3">
                            <span className={`font-medium ${inst.paid ? 'text-green-600' : ''}`}>
                              {money(inst.amount, plan.currency)}
                            </span>
                            {!inst.paid && plan.status === 'active' && (
                              <Button size="sm" variant="outline" onClick={() => handleMarkInstallmentPaid(plan.id, idx)}>
                                <CheckCircle2 className="w-3 h-3 mr-1" />{t('agentArap.markPaid')}
                              </Button>
                            )}
                            {inst.paid && (
                              <span className="text-xs text-green-600">{inst.paid_date}</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </TabsContent>

          <TabsContent value="aging" className="space-y-4">
            {aging && (
              <>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                  {agingBuckets.map(b => (
                    <Card key={b.key}>
                      <CardContent className="pt-4 text-center">
                        <Badge className={b.color}>{b.label}</Badge>
                        <div className="text-2xl font-bold mt-2">{moneyBreakdown(b.data?.totals_by_currency, b.data?.total || 0, aging.currency)}</div>
                        <div className="text-xs text-muted-foreground">{b.data?.count || 0} {t('agentArap.agencies')}</div>
                      </CardContent>
                    </Card>
                  ))}
                </div>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">{t('agentArap.agingDetail')}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      {agingBuckets.map(b => (
                        (b.data?.agencies || []).length > 0 && (
                          <div key={b.key}>
                            <h4 className="font-medium mb-2 flex items-center gap-2">
                              <Badge className={b.color}>{b.label}</Badge>
                            </h4>
                            <div className="overflow-x-auto">
                              <table className="w-full text-sm">
                                <thead>
                                  <tr className="border-b text-left">
                                    <th className="py-1 px-2">{t('agentArap.agency')}</th>
                                    <th className="py-1 px-2 text-right">{t('agentArap.balance')}</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {b.data.agencies.map(ag => (
                                    <tr key={ag.agency_id} className="border-b">
                                      <td className="py-1 px-2">{ag.agency_name}</td>
                                      <td className="py-1 px-2 text-right font-medium text-red-600">{moneyBreakdown(ag.balance_by_currency, ag.balance, aging.currency)}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </>
            )}
          </TabsContent>
        </Tabs>
      </div>

      <Dialog open={paymentDialog} onOpenChange={setPaymentDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('agentArap.recordPayment')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-[1fr_120px] gap-3">
              <div>
                <Label>{t('agentArap.amount')}</Label>
              <Input {...moneyInputProps} placeholder="Örn. 150,74" value={paymentForm.amount} onChange={e => setPaymentForm(p => ({ ...p, amount: e.target.value }))} />
              </div>
              <div>
                <Label>Para Birimi</Label>
                <select className="w-full border rounded-md px-3 py-2 text-sm" value={paymentForm.currency} onChange={e => setPaymentForm(p => ({ ...p, currency: e.target.value }))}>
                  {CURRENCIES.map(currency => <option key={currency} value={currency}>{currency}</option>)}
                </select>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">Tahsilat yalnızca seçtiğiniz para birimindeki cari bakiyeyi azaltır; dövizler birbirine çevrilmez.</p>
            <div>
              <Label>{t('agentArap.method')}</Label>
              <select
                className="w-full border rounded-md px-3 py-2 text-sm"
                value={paymentForm.payment_method}
                onChange={e => setPaymentForm(p => ({ ...p, payment_method: e.target.value }))}
              >
                <option value="bank_transfer">{t('agentArap.bankTransfer')}</option>
                <option value="check">{t('agentArap.check')}</option>
                <option value="credit_card">{t('agentArap.creditCard')}</option>
                <option value="wire_transfer">{t('agentArap.wireTransfer')}</option>
                <option value="cash">{t('agentArap.cash')}</option>
              </select>
            </div>
            <div>
              <Label>{t('agentArap.reference')}</Label>
              <Input value={paymentForm.reference} onChange={e => setPaymentForm(p => ({ ...p, reference: e.target.value }))} />
            </div>
            <div>
              <Label>{t('agentArap.notes')}</Label>
              <Input value={paymentForm.notes} onChange={e => setPaymentForm(p => ({ ...p, notes: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPaymentDialog(false)}>{t('agentArap.cancel')}</Button>
            <Button onClick={handleRecordPayment} disabled={paymentSaving}>
              {paymentSaving && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
              {t('agentArap.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={planDialog} onOpenChange={setPlanDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('agentArap.createPaymentPlan')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-[1fr_120px] gap-3">
              <div>
                <Label>{t('agentArap.totalAmount')}</Label>
              <Input {...moneyInputProps} placeholder="Örn. 150,74" value={planForm.total_amount} onChange={e => setPlanForm(p => ({ ...p, total_amount: e.target.value }))} />
              </div>
              <div>
                <Label>Para Birimi</Label>
                <select className="w-full border rounded-md px-3 py-2 text-sm" value={planForm.currency} onChange={e => setPlanForm(p => ({ ...p, currency: e.target.value }))}>
                  {CURRENCIES.map(currency => <option key={currency} value={currency}>{currency}</option>)}
                </select>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">Taksit planı seçilen para biriminde izlenir; farklı döviz bakiyeleri ayrı kalır.</p>
            <div>
              <Label>{t('agentArap.installmentCount')}</Label>
              <select
                className="w-full border rounded-md px-3 py-2 text-sm"
                value={planForm.installments}
                onChange={e => setPlanForm(p => ({ ...p, installments: parseInt(e.target.value) }))}
              >
                {[2, 3, 4, 6, 8, 10, 12].map(n => (
                  <option key={n} value={n}>{n} {t('agentArap.installments')}</option>
                ))}
              </select>
            </div>
            <div>
              <Label>{t('agentArap.startDate')}</Label>
              <Input type="date" value={planForm.start_date} onChange={e => setPlanForm(p => ({ ...p, start_date: e.target.value }))} />
            </div>
            <div>
              <Label>{t('agentArap.notes')}</Label>
              <Input value={planForm.notes} onChange={e => setPlanForm(p => ({ ...p, notes: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPlanDialog(false)}>{t('agentArap.cancel')}</Button>
            <Button onClick={handleCreatePlan} disabled={planSaving}>
              {planSaving && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
              {t('agentArap.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={stmtDialog} onOpenChange={setStmtDialog}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('agentArap.accountStatement')} — {statement?.agency_name}</DialogTitle>
          </DialogHeader>
          {stmtLoading ? (
            <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 animate-spin" /></div>
          ) : statement ? (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">{t('agentArap.totalCommission')}</span>
                  <div className="font-bold">{moneyBreakdown(statement.total_commission_owed_by_currency, statement.total_commission_owed, statement.currency)}</div>
                </div>
                <div>
                  <span className="text-muted-foreground">{t('agentArap.totalPaid')}</span>
                  <div className="font-bold text-green-600">{moneyBreakdown(statement.total_paid_by_currency, statement.total_paid, statement.currency)}</div>
                </div>
                <div>
                  <span className="text-muted-foreground">{t('agentArap.balance')}</span>
                  <div className="font-bold text-red-600">{moneyBreakdown(statement.balance_by_currency, statement.balance, statement.currency)}</div>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left">
                      <th className="py-1 px-2">{t('agentArap.date')}</th>
                      <th className="py-1 px-2">{t('agentArap.description')}</th>
                      <th className="py-1 px-2 text-right">{t('agentArap.debit')}</th>
                      <th className="py-1 px-2 text-right">{t('agentArap.credit')}</th>
                      <th className="py-1 px-2 text-right">{t('agentArap.runningBalance')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(statement.statement || []).map((line, idx) => (
                      <tr key={idx} className="border-b">
                        <td className="py-1 px-2 text-xs">{line.date}</td>
                        <td className="py-1 px-2 text-xs">{line.description}</td>
                        <td className="py-1 px-2 text-right text-red-600">{line.debit > 0 ? money(line.debit, line.currency) : ''}</td>
                        <td className="py-1 px-2 text-right text-green-600">{line.credit > 0 ? money(line.credit, line.currency) : ''}</td>
                        <td className="py-1 px-2 text-right font-medium">{money(line.balance, line.currency)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
};

export default TravelAgentARAP;
