import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import Layout from '@/components/Layout';
import InvoiceFormDialog from '@/components/invoice/InvoiceFormDialog';
import { ExpenseDialog, SupplierDialog, BankAccountDialog, InventoryDialog } from '@/components/invoice/AccountingDialogs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { 
  FileText, Plus, Building2, 
  Wallet, Package, AlertCircle, Receipt, BarChart3 
} from 'lucide-react';

const InvoiceModule = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
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

  useEffect(() => {
    let mounted = true;
    const loadData = async () => {
      try {
        const [invoicesRes, expensesRes, suppliersRes, bankRes, inventoryRes, dashRes] = await Promise.all([
          axios.get('/accounting/invoices'),
          axios.get('/accounting/expenses'),
          axios.get('/accounting/suppliers'),
          axios.get('/accounting/bank-accounts'),
          axios.get('/accounting/inventory'),
          axios.get('/accounting/dashboard')
        ]);
        if (!mounted) return;
        setInvoices(invoicesRes.data || []);
        setExpenses(expensesRes.data || []);
        setSuppliers(suppliersRes.data || []);
        setBankAccounts(bankRes.data || []);
        setInventory(inventoryRes.data?.items || []);
        setDashboard(dashRes.data || null);
      } catch (error) {
        if (!mounted) return;
        console.error('InvoiceModule loadData error:', error);
        setFatal(error?.message || 'Failed to load accounting data');
        toast.error('Failed to load accounting data');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    loadData();
    return () => { mounted = false; };
  }, []);

  const loadCashFlow = async () => {
    try {
      const response = await axios.get('/accounting/cash-flow');
      setCashFlow(response.data);
    } catch (error) {
      toast.error('Failed to load cash flow');
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
        axios.get('/accounting/reports/balance-sheet')
      ]);
      setReports({ profitLoss: plRes.data, vat: vatRes.data, balanceSheet: bsRes.data });
    } catch (error) {
      toast.error('Failed to load reports');
    }
  };

  const updateInvoiceStatus = async (invoiceId, newStatus) => {
    try {
      await axios.put(`/accounting/invoices/${invoiceId}`, { status: newStatus });
      toast.success('Invoice status updated');
    } catch (error) {
      toast.error('Update failed');
    }
  };

  if (!user || !tenant) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="invoices">
        <div className="p-6 text-sm text-slate-600">{t("common.loading")}</div>
      </Layout>
    );
  }

  const _userRoles = Array.isArray(user?.roles) ? user.roles : [];
  const _isAllowed = ['super_admin', 'admin'].includes(user?.role) || _userRoles.includes('super_admin') || _userRoles.includes('admin');
  if (!_isAllowed) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="invoices">
        <div className="p-6 text-sm text-slate-600">You do not have access to this module.</div>
      </Layout>
    );
  }

  if (loading) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="invoices">
        <div className="p-6 text-center">{t("common.loading")}</div>
      </Layout>
    );
  }

  if (fatal) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="invoices">
        <div className="p-6 space-y-2">
          <div className="text-sm font-medium text-red-600">Error loading invoice module</div>
          <pre className="text-xs bg-slate-950/80 text-slate-200 p-3 rounded-md overflow-auto">{String(fatal)}</pre>
        </div>
      </Layout>
    );
  }

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="invoices">
      <div className="p-6 space-y-6">
        <div>
          <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Space Grotesk' }}>{t('invoice.title')}</h1>
          <p className="text-gray-600">{t('invoice.subtitle')}</p>
        </div>

        {dashboard && (
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm text-gray-600">{t('dashboard.monthlyIncome')}</CardTitle></CardHeader>
              <CardContent><div className="text-2xl font-bold text-green-600">${dashboard.monthly_income}</div></CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm text-gray-600">{t('dashboard.monthlyExpenses')}</CardTitle></CardHeader>
              <CardContent><div className="text-2xl font-bold text-red-600">${dashboard.monthly_expenses}</div></CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm text-gray-600">{t('dashboard.netIncome')}</CardTitle></CardHeader>
              <CardContent><div className="text-2xl font-bold text-blue-600">${dashboard.net_income}</div></CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm text-gray-600">{t('dashboard.bankBalance')}</CardTitle></CardHeader>
              <CardContent><div className="text-2xl font-bold">${dashboard.total_bank_balance}</div></CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm text-gray-600">{t('invoice.pending')}</CardTitle></CardHeader>
              <CardContent><div className="text-2xl font-bold text-yellow-600">{dashboard.pending_invoices}</div></CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm text-gray-600">{t('dashboard.overdue')}</CardTitle></CardHeader>
              <CardContent><div className="text-2xl font-bold text-red-600">{dashboard.overdue_invoices}</div></CardContent>
            </Card>
          </div>
        )}

        <Tabs defaultValue="invoices" onValueChange={(v) => {
          if (v === 'cashflow') loadCashFlow();
          if (v === 'reports') loadReports();
        }}>
          <TabsList className="grid w-full grid-cols-6">
            <TabsTrigger value="invoices" data-testid="tab-invoices"><FileText className="w-4 h-4 mr-2" />Invoices</TabsTrigger>
            <TabsTrigger value="expenses" data-testid="tab-expenses"><Receipt className="w-4 h-4 mr-2" />Expenses</TabsTrigger>
            <TabsTrigger value="suppliers" data-testid="tab-suppliers"><Building2 className="w-4 h-4 mr-2" />Suppliers</TabsTrigger>
            <TabsTrigger value="banks" data-testid="tab-banks"><Wallet className="w-4 h-4 mr-2" />Banks</TabsTrigger>
            <TabsTrigger value="inventory" data-testid="tab-inventory"><Package className="w-4 h-4 mr-2" />Inventory</TabsTrigger>
            <TabsTrigger value="reports" data-testid="tab-reports"><BarChart3 className="w-4 h-4 mr-2" />Reports</TabsTrigger>
          </TabsList>

          <TabsContent value="invoices" className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-semibold">Invoices ({invoices.length})</h2>
              <Button onClick={() => setOpenDialog('invoice')} data-testid="create-invoice-btn">
                <Plus className="w-4 h-4 mr-2" />New Invoice
              </Button>
            </div>
            <div className="space-y-4">
              {invoices.map((invoice) => (
                <Card key={invoice.id} data-testid={`invoice-card-${invoice.invoice_number}`}>
                  <CardContent className="pt-6">
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="font-bold text-lg">{invoice.invoice_number}</div>
                        <div className="text-sm text-gray-600">{invoice.customer_name}</div>
                        {invoice.customer_tax_number && <div className="text-xs text-gray-500">Tax No: {invoice.customer_tax_number}</div>}
                        <div className="text-sm text-gray-500 mt-1">
                          Issue: {new Date(invoice.issue_date).toLocaleDateString()} | Due: {new Date(invoice.due_date).toLocaleDateString()}
                        </div>
                        <div className="text-xs text-gray-400 mt-1 capitalize">Type: {invoice.invoice_type}</div>
                      </div>
                      <div className="text-right">
                        <div className="text-2xl font-bold text-blue-600">${invoice.total.toFixed(2)}</div>
                        <div className="text-xs text-gray-500">VAT: ${invoice.total_vat.toFixed(2)}</div>
                        <div className="mt-2">
                          <Select value={invoice.status} onValueChange={(v) => updateInvoiceStatus(invoice.id, v)}>
                            <SelectTrigger className="w-32 h-8"><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="pending">Pending</SelectItem>
                              <SelectItem value="paid">Paid</SelectItem>
                              <SelectItem value="partial">Partial</SelectItem>
                              <SelectItem value="overdue">Overdue</SelectItem>
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
              <h2 className="text-2xl font-semibold">Expenses ({expenses.length})</h2>
              <Button onClick={() => setOpenDialog('expense')} data-testid="create-expense-btn">
                <Plus className="w-4 h-4 mr-2" />Add Expense
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
                        <div className="text-sm text-gray-500">Date: {new Date(expense.date).toLocaleDateString()}</div>
                        {expense.payment_method && <div className="text-xs text-gray-400 capitalize mt-1">Payment: {expense.payment_method}</div>}
                      </div>
                      <div className="text-right">
                        <div className="text-xl font-bold text-red-600">${expense.total_amount.toFixed(2)}</div>
                        <div className="text-xs text-gray-500">VAT: ${expense.vat_amount.toFixed(2)}</div>
                        <span className={`mt-2 inline-block px-2 py-1 rounded text-xs ${expense.payment_status === 'paid' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'}`}>
                          {expense.payment_status}
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
              <h2 className="text-2xl font-semibold">Suppliers ({suppliers.length})</h2>
              <Button onClick={() => setOpenDialog('supplier')}><Plus className="w-4 h-4 mr-2" />Add Supplier</Button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {suppliers.map((supplier) => (
                <Card key={supplier.id}>
                  <CardHeader><CardTitle className="text-lg">{supplier.name}</CardTitle></CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    {supplier.tax_number && <div className="flex justify-between"><span className="text-gray-600">Tax No:</span><span className="font-medium">{supplier.tax_number}</span></div>}
                    {supplier.email && <div className="flex justify-between"><span className="text-gray-600">Email:</span><span className="font-medium">{supplier.email}</span></div>}
                    {supplier.phone && <div className="flex justify-between"><span className="text-gray-600">Phone:</span><span className="font-medium">{supplier.phone}</span></div>}
                    <div className="flex justify-between pt-2 border-t"><span className="text-gray-600">Balance:</span><span className="font-bold text-red-600">${supplier.account_balance.toFixed(2)}</span></div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          <TabsContent value="banks" className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-semibold">Bank Accounts ({bankAccounts.length})</h2>
              <Button onClick={() => setOpenDialog('bank')}><Plus className="w-4 h-4 mr-2" />Add Account</Button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {bankAccounts.map((account) => (
                <Card key={account.id}>
                  <CardHeader>
                    <CardTitle className="text-lg">{account.name}</CardTitle>
                    <div className="text-sm text-gray-600">{account.bank_name}</div>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    <div className="flex justify-between"><span className="text-gray-600">Account No:</span><span className="font-medium">{account.account_number}</span></div>
                    {account.iban && <div className="flex justify-between"><span className="text-gray-600">IBAN:</span><span className="font-medium text-xs">{account.iban}</span></div>}
                    <div className="flex justify-between pt-2 border-t"><span className="text-gray-600">Balance:</span><span className="text-xl font-bold text-green-600">${account.balance.toFixed(2)}</span></div>
                    <div className="text-xs text-gray-500">{account.currency}</div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          <TabsContent value="inventory" className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-semibold">Inventory ({inventory.length})</h2>
              <Button onClick={() => setOpenDialog('inventory')}><Plus className="w-4 h-4 mr-2" />Add Item</Button>
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
                      {item.quantity <= item.reorder_level && <AlertCircle className="w-5 h-5 text-orange-500" />}
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    {item.sku && <div className="flex justify-between"><span className="text-gray-600">SKU:</span><span className="font-medium">{item.sku}</span></div>}
                    <div className="flex justify-between"><span className="text-gray-600">Qty:</span><span className="font-bold">{item.quantity} {item.unit}</span></div>
                    <div className="flex justify-between"><span className="text-gray-600">Unit Price:</span><span className="font-medium">${item.unit_cost}</span></div>
                    <div className="flex justify-between pt-2 border-t"><span className="text-gray-600">Total Value:</span><span className="font-bold text-blue-600">${(item.quantity * item.unit_cost).toFixed(2)}</span></div>
                    {item.quantity <= item.reorder_level && <div className="text-xs text-orange-600 font-medium">Low stock - Reorder needed</div>}
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          <TabsContent value="reports" className="space-y-6">
            <h2 className="text-2xl font-bold">Financial Reports</h2>

            {reports.profitLoss && (
              <Card>
                <CardHeader>
                  <CardTitle>Profit & Loss Statement</CardTitle>
                  <div className="text-sm text-gray-500">This Month</div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div className="grid grid-cols-3 gap-4">
                      <div><div className="text-sm text-gray-600">Total Revenue</div><div className="text-3xl font-bold text-green-600">${reports.profitLoss.total_revenue}</div></div>
                      <div><div className="text-sm text-gray-600">Total Expenses</div><div className="text-3xl font-bold text-red-600">${reports.profitLoss.total_expenses}</div></div>
                      <div><div className="text-sm text-gray-600">Gross Profit</div><div className="text-3xl font-bold text-blue-600">${reports.profitLoss.gross_profit}</div></div>
                    </div>
                    <div className="pt-4 border-t">
                      <div className="text-sm font-medium mb-2">Profit Margin</div>
                      <div className="text-2xl font-bold">{reports.profitLoss.profit_margin}%</div>
                    </div>
                    {reports.profitLoss.expense_breakdown && Object.keys(reports.profitLoss.expense_breakdown).length > 0 && (
                      <div className="pt-4 border-t">
                        <div className="text-sm font-medium mb-3">Expense Breakdown</div>
                        <div className="space-y-2">
                          {Object.entries(reports.profitLoss.expense_breakdown).map(([cat, amount]) => (
                            <div key={cat} className="flex justify-between text-sm">
                              <span className="capitalize text-gray-600">{cat.replace('_', ' ')}:</span>
                              <span className="font-medium">${amount.toFixed(2)}</span>
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
                  <CardTitle>VAT Report</CardTitle>
                  <div className="text-sm text-gray-500">This Month</div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-3 gap-4">
                    <div><div className="text-sm text-gray-600">Sales VAT (Collected)</div><div className="text-2xl font-bold text-green-600">${reports.vat.sales_vat}</div></div>
                    <div><div className="text-sm text-gray-600">Purchase VAT (Paid)</div><div className="text-2xl font-bold text-blue-600">${reports.vat.purchase_vat}</div></div>
                    <div><div className="text-sm text-gray-600">VAT Payable</div><div className="text-2xl font-bold text-red-600">${reports.vat.vat_payable}</div></div>
                  </div>
                </CardContent>
              </Card>
            )}

            {reports.balanceSheet && (
              <Card>
                <CardHeader><CardTitle>Balance Sheet</CardTitle></CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div>
                      <div className="font-semibold mb-3">Assets</div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between"><span className="text-gray-600">Cash:</span><span className="font-medium">${reports.balanceSheet.assets.cash}</span></div>
                        <div className="flex justify-between"><span className="text-gray-600">Inventory:</span><span className="font-medium">${reports.balanceSheet.assets.inventory}</span></div>
                        <div className="flex justify-between"><span className="text-gray-600">Receivables:</span><span className="font-medium">${reports.balanceSheet.assets.receivables}</span></div>
                        <div className="flex justify-between pt-2 border-t font-bold"><span>Total Assets:</span><span className="text-blue-600">${reports.balanceSheet.assets.total}</span></div>
                      </div>
                    </div>
                    <div>
                      <div className="font-semibold mb-3">Liabilities</div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between"><span className="text-gray-600">Payables:</span><span className="font-medium">${reports.balanceSheet.liabilities.payables}</span></div>
                        <div className="flex justify-between pt-2 border-t font-bold"><span>Total Liabilities:</span><span className="text-red-600">${reports.balanceSheet.liabilities.total}</span></div>
                      </div>
                    </div>
                    <div>
                      <div className="font-semibold mb-3">Equity</div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between pt-2 border-t font-bold"><span>Total Equity:</span><span className="text-green-600">${reports.balanceSheet.equity.total}</span></div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>
        </Tabs>

        <InvoiceFormDialog open={openDialog === 'invoice'} onClose={() => setOpenDialog(null)} />
        <ExpenseDialog open={openDialog === 'expense'} onClose={() => setOpenDialog(null)} suppliers={suppliers} />
        <SupplierDialog open={openDialog === 'supplier'} onClose={() => setOpenDialog(null)} />
        <BankAccountDialog open={openDialog === 'bank'} onClose={() => setOpenDialog(null)} />
        <InventoryDialog open={openDialog === 'inventory'} onClose={() => setOpenDialog(null)} />
      </div>
    </Layout>
  );
};

export default InvoiceModule;
