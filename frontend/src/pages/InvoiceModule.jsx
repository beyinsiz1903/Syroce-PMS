import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

import { useCurrency } from '@/context/CurrencyContext';
import { formatAmount } from '@/lib/currency';
import { ExpenseDialog, SupplierDialog, BankAccountDialog, InventoryDialog } from '@/components/invoice/AccountingDialogs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  FileText, Plus, Building2, Info,
  Wallet, Package, AlertCircle, Receipt, BarChart3,
} from 'lucide-react';

const InvoiceModule = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const { amount: fmtMoney } = useCurrency();
  const [fatal, setFatal] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [expenses, setExpenses] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [bankAccounts, setBankAccounts] = useState([]);
  const [inventory, setInventory] = useState([]);
  const [cashFlow, setCashFlow] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [reports, setReports] = useState({ profitLoss: null, vat: null, balanceSheet: null });
  const [loading, setLoading] = useState(true);
  const [openDialog, setOpenDialog] = useState(null);

  const loadedRef = useRef({ expenses: false, suppliers: false, banks: false, inventory: false });
  const inFlightRef = useRef({});

  const loadInitial = useCallback(async () => {
    try {
      const [invoicesRes, dashRes] = await Promise.all([
        axios.get('/accounting/invoices'),
        axios.get('/accounting/dashboard'),
      ]);
      setInvoices(invoicesRes.data || []);
      setDashboard(dashRes.data || null);
    } catch (error) {
      console.error('InvoiceModule loadInitial error:', error);
      setFatal(error?.message || 'Failed to load accounting data');
      toast.error(t('common.loadFailed') || 'Veri yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, [t]);

  const refreshDashboard = useCallback(async () => {
    try {
      const r = await axios.get('/accounting/dashboard');
      setDashboard(r.data || null);
    } catch { /* non-fatal */ }
  }, []);

  const fetchOnce = useCallback(async (key, url, apply) => {
    if (loadedRef.current[key]) return;
    if (inFlightRef.current[key]) return inFlightRef.current[key];
    const p = (async () => {
      try {
        const r = await axios.get(url);
        apply(r);
        loadedRef.current[key] = true;
      } catch {
        toast.error(t('common.loadFailed') || 'Yüklenemedi');
      } finally {
        delete inFlightRef.current[key];
      }
    })();
    inFlightRef.current[key] = p;
    return p;
  }, [t]);

  const refetch = useCallback(async (key, url, apply) => {
    if (inFlightRef.current[key]) return inFlightRef.current[key];
    const p = (async () => {
      try {
        const r = await axios.get(url);
        apply(r);
        loadedRef.current[key] = true;
      } catch {
        toast.error(t('common.loadFailed') || 'Yüklenemedi');
      } finally {
        delete inFlightRef.current[key];
      }
    })();
    inFlightRef.current[key] = p;
    return p;
  }, [t]);

  const loadExpenses = useCallback((force = false) => {
    const apply = (r) => setExpenses(r.data || []);
    return force
      ? refetch('expenses', '/accounting/expenses', apply)
      : fetchOnce('expenses', '/accounting/expenses', apply);
  }, [fetchOnce, refetch]);

  const loadSuppliers = useCallback((force = false) => {
    const apply = (r) => setSuppliers(r.data || []);
    return force
      ? refetch('suppliers', '/accounting/suppliers', apply)
      : fetchOnce('suppliers', '/accounting/suppliers', apply);
  }, [fetchOnce, refetch]);

  const loadBanks = useCallback((force = false) => {
    const apply = (r) => setBankAccounts(r.data || []);
    return force
      ? refetch('banks', '/accounting/bank-accounts', apply)
      : fetchOnce('banks', '/accounting/bank-accounts', apply);
  }, [fetchOnce, refetch]);

  const loadInventory = useCallback((force = false) => {
    const apply = (r) => setInventory(r.data?.items || []);
    return force
      ? refetch('inventory', '/accounting/inventory', apply)
      : fetchOnce('inventory', '/accounting/inventory', apply);
  }, [fetchOnce, refetch]);

  useEffect(() => {
    let mounted = true;
    (async () => {
      await loadInitial();
      if (!mounted) return;
    })();
    return () => { mounted = false; };
  }, [loadInitial]);

  const loadCashFlow = async () => {
    try {
      const response = await axios.get('/accounting/cash-flow');
      setCashFlow(response.data);
    } catch (error) {
      toast.error(t('common.loadFailed') || 'Yüklenemedi');
    }
  };

  const loadReports = async () => {
    try {
      const today = new Date();
      const monthStart = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().split('T')[0];
      const monthEnd = new Date(today.getFullYear(), today.getMonth() + 1, 0).toISOString().split('T')[0];
      const [plRes, vatRes, bsRes] = await Promise.all([
        axios.get(`/accounting/reports/profit-loss?start_date=${monthStart}&end_date=${monthEnd}`),
        axios.get(`/accounting/reports/vat-report?start_date=${monthStart}&end_date=${monthEnd}`),
        axios.get('/accounting/reports/balance-sheet'),
      ]);
      setReports({ profitLoss: plRes.data, vat: vatRes.data, balanceSheet: bsRes.data });
    } catch (error) {
      toast.error(t('common.loadFailed') || 'Yüklenemedi');
    }
  };

  const updateInvoiceStatus = async (invoiceId, newStatus) => {
    const previous = invoices;
    setInvoices(prev => prev.map(inv => (inv.id === invoiceId ? { ...inv, status: newStatus } : inv)));
    try {
      await axios.put(`/accounting/invoices/${invoiceId}`, { status: newStatus });
      toast.success(t('messages.success.saved') || 'Kaydedildi');
      try {
        const dashRes = await axios.get('/accounting/dashboard');
        setDashboard(dashRes.data || null);
      } catch { /* non-fatal */ }
    } catch (error) {
      setInvoices(previous);
      toast.error(t('messages.error.saveFailed') || 'Güncellenemedi');
    }
  };

  const downloadEfaturaXml = async (invoiceId) => {
    try {
      const response = await axios.get(`/accounting/invoices/${invoiceId}/efatura-xml`, { responseType: 'blob' });
      const disposition = response.headers['content-disposition'] || '';
      const match = /filename="?([^"]+)"?/.exec(disposition);
      const filename = match ? match[1] : `efatura-${invoiceId}.xml`;
      const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/xml' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      toast.error(t('invoice.efatura.downloadFailed') || 'XML indirilemedi');
    }
  };

  const reportEfaturaExternal = async (invoiceId) => {
    const previous = invoices;
    setInvoices(prev => prev.map(inv => (inv.id === invoiceId ? { ...inv, efatura_status: 'reported_externally' } : inv)));
    try {
      await axios.post(`/accounting/invoices/${invoiceId}/report-efatura-external`);
      toast.success(t('invoice.efatura.reportedSuccess') || 'E-Fatura harici olarak bildirildi');
    } catch (error) {
      setInvoices(previous);
      toast.error(t('invoice.efatura.reportFailed') || 'İşaretlenemedi');
    }
  };

  if (!user || !tenant) {
    return (
      <>
        <div className="p-6 text-sm text-slate-600">{t('common.loading')}</div>
      </>
    );
  }

  const _userRoles = Array.isArray(user?.roles) ? user.roles : [];
  const _isAllowed = ['super_admin', 'admin'].includes(user?.role) || _userRoles.includes('super_admin') || _userRoles.includes('admin');
  if (!_isAllowed) {
    return (
      <>
        <div className="p-6 text-sm text-slate-600">{t('common.noAccess') || 'Bu modüle erişim izniniz yok.'}</div>
      </>
    );
  }

  if (loading) {
    return (
      <>
        <div className="p-6 text-center">{t('common.loading')}</div>
      </>
    );
  }

  if (fatal) {
    return (
      <>
        <div className="p-6 space-y-2">
          <div className="text-sm font-medium text-red-600">{t('common.error') || 'Hata'}</div>
          <pre className="text-xs bg-slate-950/80 text-slate-200 p-3 rounded-md overflow-auto">{String(fatal)}</pre>
        </div>
      </>
    );
  }

  const money = (v) => fmtMoney(v || 0, { decimals: 2 });

  return (
    <>
      <div className="p-6 space-y-6">
        <div>
          <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Space Grotesk' }}>{t('invoice.title')}</h1>
          <p className="text-gray-600">{t('invoice.subtitle')}</p>
        </div>

        {dashboard && (
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm text-gray-600">{t('invoice.kpi.collected')}</CardTitle></CardHeader>
              <CardContent><div className="text-2xl font-bold text-green-600">{money(dashboard.collected_income ?? dashboard.monthly_income)}</div></CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm text-gray-600">{t('invoice.kpi.accrued')}</CardTitle></CardHeader>
              <CardContent><div className="text-2xl font-bold text-blue-600">{money(dashboard.accrued_revenue ?? 0)}</div></CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm text-gray-600">{t('invoice.kpi.pendingAmount')}</CardTitle></CardHeader>
              <CardContent><div className="text-2xl font-bold text-yellow-600">{money(dashboard.pending_amount ?? 0)}</div></CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm text-gray-600">{t('dashboard.monthlyExpenses')}</CardTitle></CardHeader>
              <CardContent><div className="text-2xl font-bold text-red-600">{money(dashboard.monthly_expenses)}</div></CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm text-gray-600">{t('dashboard.bankBalance')}</CardTitle></CardHeader>
              <CardContent><div className="text-2xl font-bold">{money(dashboard.total_bank_balance)}</div></CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm text-gray-600">{t('dashboard.overdue')}</CardTitle></CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-red-600">{dashboard.overdue_invoices ?? 0}</div>
                {(dashboard.overdue_amount ?? 0) > 0 && (
                  <div className="text-xs text-gray-500 mt-1">{money(dashboard.overdue_amount)}</div>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        <Tabs defaultValue="invoices" onValueChange={(v) => {
          if (v === 'expenses') { loadExpenses(); loadSuppliers(); }
          if (v === 'suppliers') loadSuppliers();
          if (v === 'banks') loadBanks();
          if (v === 'inventory') loadInventory();
          if (v === 'cashflow') loadCashFlow();
          if (v === 'reports') loadReports();
        }}>
          <TabsList className="grid w-full grid-cols-6">
            <TabsTrigger value="invoices" data-testid="tab-invoices"><FileText className="w-4 h-4 mr-2" />{t('invoice.tabs.invoices')}</TabsTrigger>
            <TabsTrigger value="expenses" data-testid="tab-expenses"><Receipt className="w-4 h-4 mr-2" />{t('invoice.tabs.expenses')}</TabsTrigger>
            <TabsTrigger value="suppliers" data-testid="tab-suppliers"><Building2 className="w-4 h-4 mr-2" />{t('invoice.tabs.suppliers')}</TabsTrigger>
            <TabsTrigger value="banks" data-testid="tab-banks"><Wallet className="w-4 h-4 mr-2" />{t('invoice.tabs.banks')}</TabsTrigger>
            <TabsTrigger value="inventory" data-testid="tab-inventory"><Package className="w-4 h-4 mr-2" />{t('invoice.tabs.inventory')}</TabsTrigger>
            <TabsTrigger value="reports" data-testid="tab-reports"><BarChart3 className="w-4 h-4 mr-2" />{t('invoice.tabs.reports')}</TabsTrigger>
          </TabsList>

          <TabsContent value="invoices" className="space-y-4">
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-start gap-3">
              <Info className="w-5 h-5 text-blue-600 shrink-0 mt-0.5" />
              <div className="text-sm">
                <div className="font-medium text-blue-900">{t('invoice.info.noEInvoiceTitle')}</div>
                <div className="text-blue-800 mt-1">{t('invoice.info.noEInvoiceBody')}</div>
              </div>
            </div>

            <h2 className="text-2xl font-semibold">{t('invoice.headers.invoices', { count: invoices.length })}</h2>

            <div className="space-y-4">
              {invoices.map((invoice) => (
                <Card key={invoice.id} data-testid={`invoice-card-${invoice.invoice_number}`}>
                  <CardContent className="pt-6">
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="font-bold text-lg">{invoice.invoice_number}</div>
                        <div className="text-sm text-gray-600">
                          {(invoice.customer_name || '').trim()
                            ? invoice.customer_name
                            : <span className="italic text-gray-400">(İsimsiz Müşteri)</span>}
                        </div>
                        {invoice.customer_tax_number && (
                          <div className="text-xs text-gray-500">{t('invoice.labels.taxNo')}: {invoice.customer_tax_number}</div>
                        )}
                        <div className="text-sm text-gray-500 mt-1">
                          {t('invoice.labels.issue')}: {new Date(invoice.issue_date).toLocaleDateString()} | {t('invoice.labels.due')}: {new Date(invoice.due_date).toLocaleDateString()}
                        </div>
                        <div className="text-xs text-gray-400 mt-1 capitalize">{t('invoice.labels.type')}: {invoice.invoice_type}</div>
                        {invoice.efatura_status && (() => {
                          const cfg = {
                            pending: { cls: 'bg-yellow-100 text-yellow-700', label: t('invoice.efatura.pending') || 'E-Fatura: Kuyrukta' },
                            xml_ready: { cls: 'bg-blue-100 text-blue-700', label: t('invoice.efatura.xmlReady') || 'E-Fatura: XML Hazır' },
                            reported_externally: { cls: 'bg-green-100 text-green-700', label: t('invoice.efatura.reportedExternally') || 'E-Fatura: Harici Bildirildi' },
                            error: { cls: 'bg-red-100 text-red-700', label: t('invoice.efatura.error') || 'E-Fatura: Hata' },
                          }[invoice.efatura_status] || { cls: 'bg-gray-100 text-gray-600', label: `E-Fatura: ${invoice.efatura_status}` };
                          return (
                            <div className="mt-2">
                              <span className={`inline-block px-2 py-1 rounded text-xs font-medium ${cfg.cls}`}>{cfg.label}</span>
                              {invoice.efatura_status === 'error' && invoice.efatura_last_error && (
                                <div className="text-xs text-red-600 mt-1 break-all">{invoice.efatura_last_error}</div>
                              )}
                              {invoice.efatura_status === 'xml_ready' && (
                                <div className="mt-2 flex flex-wrap gap-2">
                                  <Button size="sm" variant="outline" onClick={() => downloadEfaturaXml(invoice.id)} data-testid={`efatura-download-${invoice.id}`}>
                                    {t('invoice.efatura.downloadXml') || 'UBL XML İndir'}
                                  </Button>
                                  <Button size="sm" onClick={() => reportEfaturaExternal(invoice.id)} data-testid={`efatura-report-${invoice.id}`}>
                                    {t('invoice.efatura.reportExternal') || 'Harici Bildirildi İşaretle'}
                                  </Button>
                                </div>
                              )}
                              {invoice.efatura_status === 'reported_externally' && (
                                <div className="mt-2">
                                  <Button size="sm" variant="outline" onClick={() => downloadEfaturaXml(invoice.id)} data-testid={`efatura-download-${invoice.id}`}>
                                    {t('invoice.efatura.downloadXml') || 'UBL XML İndir'}
                                  </Button>
                                </div>
                              )}
                            </div>
                          );
                        })()}
                      </div>
                      <div className="text-right">
                        <div className="text-2xl font-bold text-blue-600">{money(invoice.total)}</div>
                        <div className="text-xs text-gray-500">{t('invoice.labels.vat')}: {money(invoice.total_vat)}</div>
                        <div className="mt-2">
                          <Select value={invoice.status} onValueChange={(v) => updateInvoiceStatus(invoice.id, v)}>
                            <SelectTrigger className="w-32 h-8"><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="pending">{t('invoice.pending')}</SelectItem>
                              <SelectItem value="paid">{t('invoice.paid')}</SelectItem>
                              <SelectItem value="partial">{t('invoice.partial')}</SelectItem>
                              <SelectItem value="overdue">{t('invoice.overdue')}</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          <TabsContent value="expenses" className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-semibold">{t('invoice.headers.expenses', { count: expenses.length })}</h2>
              <Button onClick={() => setOpenDialog('expense')} data-testid="create-expense-btn">
                <Plus className="w-4 h-4 mr-2" />{t('invoice.actions.addExpense')}
              </Button>
            </div>
            <div className="space-y-4">
              {expenses.map((expense) => (
                <Card key={expense.id}>
                  <CardContent className="pt-6">
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="font-bold">{expense.expense_number}</div>
                        <div className="text-sm text-gray-600 capitalize">{expense.category} - {expense.description}</div>
                        <div className="text-sm text-gray-500">{t('invoice.labels.date')}: {new Date(expense.date).toLocaleDateString()}</div>
                        {expense.payment_method && <div className="text-xs text-gray-400 capitalize mt-1">{t('invoice.labels.payment')}: {expense.payment_method}</div>}
                      </div>
                      <div className="text-right">
                        <div className="text-xl font-bold text-red-600">{money(expense.total_amount)}</div>
                        <div className="text-xs text-gray-500">{t('invoice.labels.vat')}: {money(expense.vat_amount)}</div>
                        <span className={`mt-2 inline-block px-2 py-1 rounded text-xs ${expense.payment_status === 'paid' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'}`}>
                          {expense.payment_status === 'paid' ? t('invoice.paid') : t('invoice.pending')}
                        </span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          <TabsContent value="suppliers" className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-semibold">{t('invoice.headers.suppliers', { count: suppliers.length })}</h2>
              <Button onClick={() => setOpenDialog('supplier')}><Plus className="w-4 h-4 mr-2" />{t('invoice.actions.addSupplier')}</Button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {suppliers.map((supplier) => (
                <Card key={supplier.id}>
                  <CardHeader><CardTitle className="text-lg">{supplier.name}</CardTitle></CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    {supplier.tax_number && <div className="flex justify-between"><span className="text-gray-600">{t('invoice.labels.taxNo')}:</span><span className="font-medium">{supplier.tax_number}</span></div>}
                    {supplier.email && <div className="flex justify-between"><span className="text-gray-600">{t('invoice.labels.email')}:</span><span className="font-medium">{supplier.email}</span></div>}
                    {supplier.phone && <div className="flex justify-between"><span className="text-gray-600">{t('invoice.labels.phone')}:</span><span className="font-medium">{supplier.phone}</span></div>}
                    <div className="flex justify-between pt-2 border-t"><span className="text-gray-600">{t('invoice.labels.balance')}:</span><span className="font-bold text-red-600">{money(supplier.account_balance)}</span></div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          <TabsContent value="banks" className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-semibold">{t('invoice.headers.banks', { count: bankAccounts.length })}</h2>
              <Button onClick={() => setOpenDialog('bank')}><Plus className="w-4 h-4 mr-2" />{t('invoice.actions.addAccount')}</Button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {bankAccounts.map((account) => {
                const code = (account.currency || 'TRY').toUpperCase();
                return (
                  <Card key={account.id}>
                    <CardHeader>
                      <CardTitle className="text-lg">{account.name}</CardTitle>
                      <div className="text-sm text-gray-600">{account.bank_name}</div>
                    </CardHeader>
                    <CardContent className="space-y-2 text-sm">
                      <div className="flex justify-between"><span className="text-gray-600">{t('invoice.labels.accountNo')}:</span><span className="font-medium">{account.account_number}</span></div>
                      {account.iban && <div className="flex justify-between"><span className="text-gray-600">{t('invoice.labels.iban')}:</span><span className="font-medium text-xs">{account.iban}</span></div>}
                      <div className="flex justify-between pt-2 border-t">
                        <span className="text-gray-600">{t('invoice.labels.balance')}:</span>
                        <span className="text-xl font-bold text-green-600">{formatAmount(account.balance || 0, code, { decimals: 2 })}</span>
                      </div>
                      <div className="text-xs text-gray-500">{code}</div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </TabsContent>

          <TabsContent value="inventory" className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-semibold">{t('invoice.headers.inventory', { count: inventory.length })}</h2>
              <Button onClick={() => setOpenDialog('inventory')}><Plus className="w-4 h-4 mr-2" />{t('invoice.actions.addItem')}</Button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {inventory.map((item) => (
                <Card key={item.id}>
                  <CardHeader>
                    <div className="flex justify-between items-start">
                      <div>
                        <CardTitle className="text-lg">{item.name}</CardTitle>
                        <div className="text-sm text-gray-600 capitalize">{item.category}</div>
                      </div>
                      {item.quantity <= item.reorder_level && <AlertCircle className="w-5 h-5 text-amber-500" />}
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    {item.sku && <div className="flex justify-between"><span className="text-gray-600">{t('invoice.labels.sku')}:</span><span className="font-medium">{item.sku}</span></div>}
                    <div className="flex justify-between"><span className="text-gray-600">{t('invoice.labels.qty')}:</span><span className="font-bold">{item.quantity} {item.unit}</span></div>
                    <div className="flex justify-between"><span className="text-gray-600">{t('invoice.labels.unitPrice')}:</span><span className="font-medium">{money(item.unit_cost)}</span></div>
                    <div className="flex justify-between pt-2 border-t"><span className="text-gray-600">{t('invoice.labels.totalValue')}:</span><span className="font-bold text-blue-600">{money((item.quantity || 0) * (item.unit_cost || 0))}</span></div>
                    {item.quantity <= item.reorder_level && <div className="text-xs text-amber-600 font-medium">{t('invoice.labels.lowStock')}</div>}
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          <TabsContent value="reports" className="space-y-6">
            <h2 className="text-2xl font-bold">{t('invoice.reports.title')}</h2>

            {reports.profitLoss && (
              <Card>
                <CardHeader>
                  <CardTitle>{t('invoice.reports.profitLoss')}</CardTitle>
                  <div className="text-sm text-gray-500">{t('invoice.reports.thisMonth')}</div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div className="grid grid-cols-3 gap-4">
                      <div><div className="text-sm text-gray-600">{t('invoice.reports.totalRevenue')}</div><div className="text-3xl font-bold text-green-600">{money(reports.profitLoss.total_revenue)}</div></div>
                      <div><div className="text-sm text-gray-600">{t('invoice.reports.totalExpenses')}</div><div className="text-3xl font-bold text-red-600">{money(reports.profitLoss.total_expenses)}</div></div>
                      <div><div className="text-sm text-gray-600">{t('invoice.reports.grossProfit')}</div><div className="text-3xl font-bold text-blue-600">{money(reports.profitLoss.gross_profit)}</div></div>
                    </div>
                    <div className="pt-4 border-t">
                      <div className="text-sm font-medium mb-2">{t('invoice.reports.profitMargin')}</div>
                      <div className="text-2xl font-bold">{reports.profitLoss.profit_margin}%</div>
                    </div>
                    {reports.profitLoss.expense_breakdown && Object.keys(reports.profitLoss.expense_breakdown).length > 0 && (
                      <div className="pt-4 border-t">
                        <div className="text-sm font-medium mb-3">{t('invoice.reports.expenseBreakdown')}</div>
                        <div className="space-y-2">
                          {Object.entries(reports.profitLoss.expense_breakdown).map(([cat, amt]) => (
                            <div key={cat} className="flex justify-between text-sm">
                              <span className="capitalize text-gray-600">{cat.replace('_', ' ')}:</span>
                              <span className="font-medium">{money(amt)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            )}

            {reports.vat && (
              <Card>
                <CardHeader>
                  <CardTitle>{t('invoice.reports.vat')}</CardTitle>
                  <div className="text-sm text-gray-500">{t('invoice.reports.thisMonth')}</div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-3 gap-4">
                    <div><div className="text-sm text-gray-600">{t('invoice.reports.vatCollected')}</div><div className="text-2xl font-bold text-green-600">{money(reports.vat.sales_vat)}</div></div>
                    <div><div className="text-sm text-gray-600">{t('invoice.reports.vatPaid')}</div><div className="text-2xl font-bold text-blue-600">{money(reports.vat.purchase_vat)}</div></div>
                    <div><div className="text-sm text-gray-600">{t('invoice.reports.vatPayable')}</div><div className="text-2xl font-bold text-red-600">{money(reports.vat.vat_payable)}</div></div>
                  </div>
                </CardContent>
              </Card>
            )}

            {reports.balanceSheet && (
              <Card>
                <CardHeader><CardTitle>{t('invoice.reports.balanceSheet')}</CardTitle></CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div>
                      <div className="font-semibold mb-3">{t('invoice.reports.assets')}</div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between"><span className="text-gray-600">{t('invoice.reports.cash')}:</span><span className="font-medium">{money(reports.balanceSheet.assets.cash)}</span></div>
                        <div className="flex justify-between"><span className="text-gray-600">{t('invoice.reports.inventory')}:</span><span className="font-medium">{money(reports.balanceSheet.assets.inventory)}</span></div>
                        <div className="flex justify-between"><span className="text-gray-600">{t('invoice.reports.receivables')}:</span><span className="font-medium">{money(reports.balanceSheet.assets.receivables)}</span></div>
                        <div className="flex justify-between pt-2 border-t font-bold"><span>{t('invoice.reports.totalAssets')}:</span><span className="text-blue-600">{money(reports.balanceSheet.assets.total)}</span></div>
                      </div>
                    </div>
                    <div>
                      <div className="font-semibold mb-3">{t('invoice.reports.liabilities')}</div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between"><span className="text-gray-600">{t('invoice.reports.payables')}:</span><span className="font-medium">{money(reports.balanceSheet.liabilities.payables)}</span></div>
                        <div className="flex justify-between pt-2 border-t font-bold"><span>{t('invoice.reports.totalLiabilities')}:</span><span className="text-red-600">{money(reports.balanceSheet.liabilities.total)}</span></div>
                      </div>
                    </div>
                    <div>
                      <div className="font-semibold mb-3">{t('invoice.reports.equity')}</div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between pt-2 border-t font-bold"><span>{t('invoice.reports.totalEquity')}:</span><span className="text-green-600">{money(reports.balanceSheet.equity.total)}</span></div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>
        </Tabs>

        <ExpenseDialog open={openDialog === 'expense'} onClose={() => { setOpenDialog(null); loadExpenses(true); refreshDashboard(); }} suppliers={suppliers} />
        <SupplierDialog open={openDialog === 'supplier'} onClose={() => { setOpenDialog(null); loadSuppliers(true); }} />
        <BankAccountDialog open={openDialog === 'bank'} onClose={() => { setOpenDialog(null); loadBanks(true); refreshDashboard(); }} />
        <InventoryDialog open={openDialog === 'inventory'} onClose={() => { setOpenDialog(null); loadInventory(true); }} />
      </div>
    </>
  );
};

export default InvoiceModule;
