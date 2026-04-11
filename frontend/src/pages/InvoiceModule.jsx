import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { 
  FileText, Plus, DollarSign, Clock, CheckCircle, Building2, 
  Wallet, Package, TrendingUp, AlertCircle, Receipt, BarChart3 
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

  const [newInvoice, setNewInvoice] = useState({
    invoice_type: 'sales',
    customer_name: '',
    customer_email: '',
    customer_tax_office: '',
    customer_tax_number: '',
    customer_address: '',
    items: [{ description: '', quantity: 1, unit_price: 0, vat_rate: 18, vat_amount: 0, total: 0, additional_taxes: [] }],
    due_date: '',
    notes: ''
  });

  const [showAdditionalTaxDialog, setShowAdditionalTaxDialog] = useState(false);
  const [currentItemIndex, setCurrentItemIndex] = useState(null);
  const [newAdditionalTax, setNewAdditionalTax] = useState({
    tax_type: 'otv',
    tax_name: 'ÖTV',
    rate: 0,
    amount: 0,
    is_percentage: true,
    withholding_rate: null
  });

  const [newExpense, setNewExpense] = useState({
    category: 'supplies',
    description: '',
    amount: 0,
    vat_rate: 18,
    date: new Date().toISOString().split('T')[0],
    supplier_id: '',
    payment_method: 'cash',
    notes: ''
  });

  const [newSupplier, setNewSupplier] = useState({
    name: '',
    tax_office: '',
    tax_number: '',
    email: '',
    phone: '',
    address: '',
    category: 'general'
  });

  const [newBankAccount, setNewBankAccount] = useState({
    name: '',
    bank_name: '',
    account_number: '',
    iban: '',
    currency: 'USD',
    balance: 0
  });

  const [newInventoryItem, setNewInventoryItem] = useState({
    name: '',
    category: 'supplies',
    unit: 'piece',
    quantity: 0,
    unit_cost: 0,
    reorder_level: 10,
    sku: ''
  });

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
    return () => {
      mounted = false;
    };
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
      
      setReports({
        profitLoss: plRes.data,
        vat: vatRes.data,
        balanceSheet: bsRes.data
      });
    } catch (error) {
      toast.error('Failed to load reports');
    }
  };

  const calculateInvoiceItem = (index, field, value) => {
    const items = [...newInvoice.items];
    items[index][field] = value;
    
    if (field === 'quantity' || field === 'unit_price' || field === 'vat_rate') {
      const subtotal = items[index].quantity * items[index].unit_price;
      items[index].vat_amount = subtotal * (items[index].vat_rate / 100);
      items[index].total = subtotal + items[index].vat_amount;
    }
    
    setNewInvoice({ ...newInvoice, items });
  };

  const addInvoiceItem = () => {
    setNewInvoice({
      ...newInvoice,
      items: [...newInvoice.items, { description: '', quantity: 1, unit_price: 0, vat_rate: 18, vat_amount: 0, total: 0, additional_taxes: [] }]
    });
  };

  const openAddTaxDialog = (index) => {
    setCurrentItemIndex(index);
    setShowAdditionalTaxDialog(true);
  };

  const addAdditionalTax = () => {
    if (currentItemIndex === null) return;
    
    const items = [...newInvoice.items];
    const item = items[currentItemIndex];
    
    // Calculate the tax amount
    let calculatedAmount = 0;
    const subtotal = item.quantity * item.unit_price;
    
    if (newAdditionalTax.tax_type === 'withholding' && newAdditionalTax.withholding_rate) {
      // For withholding tax, calculate based on VAT amount
      const rateParts = newAdditionalTax.withholding_rate.split('/');
      const ratePercent = (parseInt(rateParts[0]) / parseInt(rateParts[1])) * 100;
      calculatedAmount = item.vat_amount * (ratePercent / 100);
    } else if (newAdditionalTax.is_percentage) {
      calculatedAmount = subtotal * (newAdditionalTax.rate / 100);
    } else {
      calculatedAmount = newAdditionalTax.amount;
    }

    const taxToAdd = {
      ...newAdditionalTax,
      calculated_amount: calculatedAmount
    };

    if (!item.additional_taxes) {
      item.additional_taxes = [];
    }
    item.additional_taxes.push(taxToAdd);
    
    items[currentItemIndex] = item;
    setNewInvoice({ ...newInvoice, items });
    
    // Reset dialog
    setShowAdditionalTaxDialog(false);
    setNewAdditionalTax({
      tax_type: 'otv',
      tax_name: 'ÖTV',
      rate: 0,
      amount: 0,
      is_percentage: true,
      withholding_rate: null
    });
  };

  const removeAdditionalTax = (itemIndex, taxIndex) => {
    const items = [...newInvoice.items];
    items[itemIndex].additional_taxes.splice(taxIndex, 1);
    setNewInvoice({ ...newInvoice, items });
  };

  const handleCreateInvoice = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/accounting/invoices', null, { params: newInvoice });
      toast.success('Invoice created successfully');
      setOpenDialog(null);
      // Refresh handled by main effect or page reload
    } catch (error) {
      toast.error('Failed to create invoice');
    }
  };

  const handleCreateExpense = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/accounting/expenses', null, { params: newExpense });
      toast.success('Expense recorded');
      setOpenDialog(null);
      // Refresh handled by main effect
      setNewExpense({ category: 'supplies', description: '', amount: 0, vat_rate: 18, date: new Date().toISOString().split('T')[0], supplier_id: '', payment_method: 'cash', notes: '' });
    } catch (error) {
      toast.error('Failed to create expense');
    }
  };

  const handleCreateSupplier = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/accounting/suppliers', null, { params: newSupplier });
      toast.success('Supplier added');
      setOpenDialog(null);
      // Refresh handled by main effect
      setNewSupplier({ name: '', tax_office: '', tax_number: '', email: '', phone: '', address: '', category: 'general' });
    } catch (error) {
      toast.error('Failed to create supplier');
    }
  };

  const handleCreateBankAccount = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/accounting/bank-accounts', null, { params: newBankAccount });
      toast.success('Bank account added');
      setOpenDialog(null);
      // Refresh handled by main effect
      setNewBankAccount({ name: '', bank_name: '', account_number: '', iban: '', currency: 'USD', balance: 0 });
    } catch (error) {
      toast.error('Failed to create bank account');
    }
  };

  const handleCreateInventoryItem = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/accounting/inventory', null, { params: newInventoryItem });
      toast.success('Inventory item added');
      setOpenDialog(null);
      // Refresh handled by main effect
      setNewInventoryItem({ name: '', category: 'supplies', unit: 'piece', quantity: 0, unit_cost: 0, reorder_level: 10, sku: '' });
    } catch (error) {
      toast.error('Failed to create item');
    }
  };

  const updateInvoiceStatus = async (invoiceId, newStatus) => {
    try {
      await axios.put(`/accounting/invoices/${invoiceId}`, { status: newStatus });
      toast.success('Invoice status updated');
      // Refresh handled by main effect or manual reload
    } catch (error) {
      toast.error('Failed to update');
    }
  };

  // Props guard - user/tenant eksikken beyaz ekran yerine güvenli yükleme mesajı
  if (!user || !tenant) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="invoices">
        <div className="p-6 text-sm text-slate-600">{t("common.loading")}</div>
      </Layout>
    );
  }

  // Role guard - admin ve super_admin erişebilir
  if (user.role !== 'super_admin' && user.role !== 'admin') {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="invoices">
        <div className="p-6 text-sm text-slate-600">Bu modüle erişim yetkiniz yok.</div>
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
          <div className="text-sm font-medium text-red-600">Fatura modülü açılırken hata oluştu</div>
          <pre className="text-xs bg-slate-950/80 text-slate-200 p-3 rounded-md overflow-auto">
            {String(fatal)}
          </pre>
        </div>
      </Layout>
    );
  }

  const invoiceSubtotal = newInvoice.items.reduce((sum, item) => sum + (item.quantity * item.unit_price), 0);
  const invoiceTotalVAT = newInvoice.items.reduce((sum, item) => sum + item.vat_amount, 0);
  
  // Calculate withholding tax (deduction from VAT)
  let invoiceVATWithholding = 0;
  let invoiceAdditionalTaxes = 0;
  
  newInvoice.items.forEach(item => {
    if (item.additional_taxes && item.additional_taxes.length > 0) {
      item.additional_taxes.forEach(tax => {
        if (tax.tax_type === 'withholding') {
          // Withholding tax calculation
          if (tax.withholding_rate) {
            const rateParts = tax.withholding_rate.split('/');
            const ratePercent = (parseInt(rateParts[0]) / parseInt(rateParts[1])) * 100;
            invoiceVATWithholding += item.vat_amount * (ratePercent / 100);
          }
        } else {
          // Other taxes (ÖTV, accommodation, etc.)
          const subtotal = item.quantity * item.unit_price;
          if (tax.is_percentage) {
            invoiceAdditionalTaxes += subtotal * (tax.rate / 100);
          } else {
            invoiceAdditionalTaxes += tax.amount;
          }
        }
      });
    }
  });
  
  const invoiceTotal = invoiceSubtotal + invoiceTotalVAT + invoiceAdditionalTaxes - invoiceVATWithholding;

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="invoices">
      <div className="p-6 space-y-6">
        <div>
          <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Space Grotesk' }}>{t('invoice.title')}</h1>
          <p className="text-gray-600">{t('invoice.subtitle')}</p>
        </div>

        {/* Dashboard Cards */}
        {dashboard && (
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-gray-600">{t('dashboard.monthlyIncome')}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-green-600">${dashboard.monthly_income}</div>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-gray-600">{t('dashboard.monthlyExpenses')}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-red-600">${dashboard.monthly_expenses}</div>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-gray-600">{t('dashboard.netIncome')}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-blue-600">${dashboard.net_income}</div>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-gray-600">{t('dashboard.bankBalance')}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">${dashboard.total_bank_balance}</div>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-gray-600">{t('invoice.pending')}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-yellow-600">{dashboard.pending_invoices}</div>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-gray-600">{t('dashboard.overdue')}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-red-600">{dashboard.overdue_invoices}</div>
              </CardContent>
            </Card>
          </div>
        )}

        <Tabs defaultValue="invoices" onValueChange={(v) => {
          if (v === 'cashflow') loadCashFlow();
          if (v === 'reports') loadReports();
        }}>
          <TabsList className="grid w-full grid-cols-6">
            <TabsTrigger value="invoices" data-testid="tab-invoices">
              <FileText className="w-4 h-4 mr-2" />
              Invoices
            </TabsTrigger>
            <TabsTrigger value="expenses" data-testid="tab-expenses">
              <Receipt className="w-4 h-4 mr-2" />
              Expenses
            </TabsTrigger>
            <TabsTrigger value="suppliers" data-testid="tab-suppliers">
              <Building2 className="w-4 h-4 mr-2" />
              Suppliers
            </TabsTrigger>
            <TabsTrigger value="banks" data-testid="tab-banks">
              <Wallet className="w-4 h-4 mr-2" />
              Banks
            </TabsTrigger>
            <TabsTrigger value="inventory" data-testid="tab-inventory">
              <Package className="w-4 h-4 mr-2" />
              Inventory
            </TabsTrigger>
            <TabsTrigger value="reports" data-testid="tab-reports">
              <BarChart3 className="w-4 h-4 mr-2" />
              Reports
            </TabsTrigger>
          </TabsList>

          {/* INVOICES TAB */}
          <TabsContent value="invoices" className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-semibold">Invoices ({invoices.length})</h2>
              <Button onClick={() => setOpenDialog('invoice')} data-testid="create-invoice-btn">
                <Plus className="w-4 h-4 mr-2" />
                New Invoice
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
                        {invoice.customer_tax_number && (
                          <div className="text-xs text-gray-500">Tax#: {invoice.customer_tax_number}</div>
                        )}
                        <div className="text-sm text-gray-500 mt-1">
                          Issue: {new Date(invoice.issue_date).toLocaleDateString()} | 
                          Due: {new Date(invoice.due_date).toLocaleDateString()}
                        </div>
                        <div className="text-xs text-gray-400 mt-1 capitalize">Type: {invoice.invoice_type}</div>
                      </div>
                      <div className="text-right">
                        <div className="text-2xl font-bold text-blue-600">${invoice.total.toFixed(2)}</div>
                        <div className="text-xs text-gray-500">VAT: ${invoice.total_vat.toFixed(2)}</div>
                        <div className="mt-2">
                          <Select value={invoice.status} onValueChange={(v) => updateInvoiceStatus(invoice.id, v)}>
                            <SelectTrigger className="w-32 h-8">
                              <SelectValue />
                            </SelectTrigger>
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

          {/* EXPENSES TAB */}
          <TabsContent value="expenses" className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-semibold">Expenses ({expenses.length})</h2>
              <Button onClick={() => setOpenDialog('expense')} data-testid="create-expense-btn">
                <Plus className="w-4 h-4 mr-2" />
                Add Expense
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
                        {expense.payment_method && (
                          <div className="text-xs text-gray-400 capitalize mt-1">Payment: {expense.payment_method}</div>
                        )}
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

          {/* SUPPLIERS TAB */}
          <TabsContent value="suppliers" className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-semibold">Suppliers ({suppliers.length})</h2>
              <Button onClick={() => setOpenDialog('supplier')}>
                <Plus className="w-4 h-4 mr-2" />
                Add Supplier
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {suppliers.map((supplier) => (
                <Card key={supplier.id}>
                  <CardHeader>
                    <CardTitle className="text-lg">{supplier.name}</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    {supplier.tax_number && (
                      <div className="flex justify-between">
                        <span className="text-gray-600">Tax Number:</span>
                        <span className="font-medium">{supplier.tax_number}</span>
                      </div>
                    )}
                    {supplier.email && (
                      <div className="flex justify-between">
                        <span className="text-gray-600">Email:</span>
                        <span className="font-medium">{supplier.email}</span>
                      </div>
                    )}
                    {supplier.phone && (
                      <div className="flex justify-between">
                        <span className="text-gray-600">Phone:</span>
                        <span className="font-medium">{supplier.phone}</span>
                      </div>
                    )}
                    <div className="flex justify-between pt-2 border-t">
                      <span className="text-gray-600">Balance:</span>
                      <span className="font-bold text-red-600">${supplier.account_balance.toFixed(2)}</span>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          {/* BANKS TAB */}
          <TabsContent value="banks" className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-semibold">Bank Accounts ({bankAccounts.length})</h2>
              <Button onClick={() => setOpenDialog('bank')}>
                <Plus className="w-4 h-4 mr-2" />
                Add Account
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {bankAccounts.map((account) => (
                <Card key={account.id}>
                  <CardHeader>
                    <CardTitle className="text-lg">{account.name}</CardTitle>
                    <div className="text-sm text-gray-600">{account.bank_name}</div>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-600">Account:</span>
                      <span className="font-medium">{account.account_number}</span>
                    </div>
                    {account.iban && (
                      <div className="flex justify-between">
                        <span className="text-gray-600">IBAN:</span>
                        <span className="font-medium text-xs">{account.iban}</span>
                      </div>
                    )}
                    <div className="flex justify-between pt-2 border-t">
                      <span className="text-gray-600">Balance:</span>
                      <span className="text-xl font-bold text-green-600">${account.balance.toFixed(2)}</span>
                    </div>
                    <div className="text-xs text-gray-500">{account.currency}</div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          {/* INVENTORY TAB */}
          <TabsContent value="inventory" className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-semibold">Inventory ({inventory.length})</h2>
              <Button onClick={() => setOpenDialog('inventory')}>
                <Plus className="w-4 h-4 mr-2" />
                Add Item
              </Button>
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
                      {item.quantity <= item.reorder_level && (
                        <AlertCircle className="w-5 h-5 text-orange-500" />
                      )}
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm">
                    {item.sku && (
                      <div className="flex justify-between">
                        <span className="text-gray-600">SKU:</span>
                        <span className="font-medium">{item.sku}</span>
                      </div>
                    )}
                    <div className="flex justify-between">
                      <span className="text-gray-600">Quantity:</span>
                      <span className="font-bold">{item.quantity} {item.unit}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Unit Cost:</span>
                      <span className="font-medium">${item.unit_cost}</span>
                    </div>
                    <div className="flex justify-between pt-2 border-t">
                      <span className="text-gray-600">Total Value:</span>
                      <span className="font-bold text-blue-600">${(item.quantity * item.unit_cost).toFixed(2)}</span>
                    </div>
                    {item.quantity <= item.reorder_level && (
                      <div className="text-xs text-orange-600 font-medium">Low stock - Reorder needed</div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          {/* REPORTS TAB */}
          <TabsContent value="reports" className="space-y-6">
            <h2 className="text-2xl font-bold">Financial Reports</h2>

            {/* Profit & Loss */}
            {reports.profitLoss && (
              <Card>
                <CardHeader>
                  <CardTitle>Profit & Loss Statement</CardTitle>
                  <div className="text-sm text-gray-500">This Month</div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div className="grid grid-cols-3 gap-4">
                      <div>
                        <div className="text-sm text-gray-600">Total Revenue</div>
                        <div className="text-3xl font-bold text-green-600">${reports.profitLoss.total_revenue}</div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-600">Total Expenses</div>
                        <div className="text-3xl font-bold text-red-600">${reports.profitLoss.total_expenses}</div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-600">Gross Profit</div>
                        <div className="text-3xl font-bold text-blue-600">${reports.profitLoss.gross_profit}</div>
                      </div>
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

            {/* VAT Report */}
            {reports.vat && (
              <Card>
                <CardHeader>
                  <CardTitle>VAT Report</CardTitle>
                  <div className="text-sm text-gray-500">This Month</div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <div className="text-sm text-gray-600">Sales VAT (Collected)</div>
                      <div className="text-2xl font-bold text-green-600">${reports.vat.sales_vat}</div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600">Purchase VAT (Paid)</div>
                      <div className="text-2xl font-bold text-blue-600">${reports.vat.purchase_vat}</div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600">VAT Payable</div>
                      <div className="text-2xl font-bold text-red-600">${reports.vat.vat_payable}</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Balance Sheet */}
            {reports.balanceSheet && (
              <Card>
                <CardHeader>
                  <CardTitle>Balance Sheet</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div>
                      <div className="font-semibold mb-3">Assets</div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-600">Cash:</span>
                          <span className="font-medium">${reports.balanceSheet.assets.cash}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-600">Inventory:</span>
                          <span className="font-medium">${reports.balanceSheet.assets.inventory}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-600">Receivables:</span>
                          <span className="font-medium">${reports.balanceSheet.assets.receivables}</span>
                        </div>
                        <div className="flex justify-between pt-2 border-t font-bold">
                          <span>Total Assets:</span>
                          <span className="text-blue-600">${reports.balanceSheet.assets.total}</span>
                        </div>
                      </div>
                    </div>
                    
                    <div>
                      <div className="font-semibold mb-3">Liabilities</div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-600">Payables:</span>
                          <span className="font-medium">${reports.balanceSheet.liabilities.payables}</span>
                        </div>
                        <div className="flex justify-between pt-2 border-t font-bold">
                          <span>Total Liabilities:</span>
                          <span className="text-red-600">${reports.balanceSheet.liabilities.total}</span>
                        </div>
                      </div>
                    </div>
                    
                    <div>
                      <div className="font-semibold mb-3">Equity</div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between pt-2 border-t font-bold">
                          <span>Total Equity:</span>
                          <span className="text-green-600">${reports.balanceSheet.equity.total}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>
        </Tabs>

        {/* Invoice Dialog */}
        <Dialog open={openDialog === 'invoice'} onOpenChange={(open) => !open && setOpenDialog(null)}>
          <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{t('invoice.createInvoice')}</DialogTitle>
              <DialogDescription>{t('invoice.subtitle')}</DialogDescription>
            </DialogHeader>
            <form onSubmit={handleCreateInvoice} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>{t('invoice.invoiceType')}</Label>
                  <Select value={newInvoice.invoice_type} onValueChange={(v) => setNewInvoice({...newInvoice, invoice_type: v})}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="sales">{t('invoice.salesInvoice')}</SelectItem>
                      <SelectItem value="e_invoice">{t('invoice.eInvoice')}</SelectItem>
                      <SelectItem value="proforma">{t('invoice.proforma')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>{t('invoice.customerName')} *</Label>
                  <Input value={newInvoice.customer_name} onChange={(e) => setNewInvoice({...newInvoice, customer_name: e.target.value})} required />
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>{t('common.email')}</Label>
                  <Input type="email" value={newInvoice.customer_email} onChange={(e) => setNewInvoice({...newInvoice, customer_email: e.target.value})} />
                </div>
                <div>
                  <Label>{t('invoice.taxNumber')}</Label>
                  <Input value={newInvoice.customer_tax_number} onChange={(e) => setNewInvoice({...newInvoice, customer_tax_number: e.target.value})} />
                </div>
              </div>
              
              <div>
                <Label>{t('invoice.address')}</Label>
                <Textarea value={newInvoice.customer_address} onChange={(e) => setNewInvoice({...newInvoice, customer_address: e.target.value})} rows={2} />
              </div>

              <div>
                <div className="flex justify-between items-center mb-2">
                  <Label>{t('invoice.invoiceItems')}</Label>
                  <Button type="button" size="sm" variant="outline" onClick={addInvoiceItem}>
                    <Plus className="w-4 h-4 mr-1" /> {t('invoice.addItem')}
                  </Button>
                </div>
                <div className="space-y-3">
                  {newInvoice.items.map((item, index) => (
                    <div key={index} className="border rounded-lg p-3 space-y-2">
                      <div className="grid grid-cols-6 gap-2 items-center">
                        <Input placeholder={t('invoice.description')} value={item.description} onChange={(e) => calculateInvoiceItem(index, 'description', e.target.value)} required />
                        <Input type="number" placeholder={t('invoice.qty')} value={item.quantity} onChange={(e) => calculateInvoiceItem(index, 'quantity', parseFloat(e.target.value))} required />
                        <Input type="number" step="0.01" placeholder={t('invoice.price')} value={item.unit_price} onChange={(e) => calculateInvoiceItem(index, 'unit_price', parseFloat(e.target.value))} required />
                        <Select value={item.vat_rate.toString()} onValueChange={(v) => calculateInvoiceItem(index, 'vat_rate', parseFloat(v))}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="0">0%</SelectItem>
                            <SelectItem value="1">1%</SelectItem>
                            <SelectItem value="8">8%</SelectItem>
                            <SelectItem value="10">10%</SelectItem>
                            <SelectItem value="18">18%</SelectItem>
                            <SelectItem value="20">20%</SelectItem>
                          </SelectContent>
                        </Select>
                        <Input type="number" placeholder={t('invoice.total')} value={item.total.toFixed(2)} readOnly />
                        <Button type="button" size="sm" variant="outline" onClick={() => openAddTaxDialog(index)} title={t('invoice.addAdditionalTax')}>
                          <Plus className="w-4 h-4" />
                        </Button>
                      </div>
                      
                      {/* Display additional taxes for this item */}
                      {item.additional_taxes && item.additional_taxes.length > 0 && (
                        <div className="ml-4 space-y-1">
                          {item.additional_taxes.map((tax, taxIndex) => (
                            <div key={taxIndex} className="flex items-center justify-between text-sm bg-blue-50 px-2 py-1 rounded">
                              <span className="text-blue-700">
                                {tax.tax_name}: {tax.is_percentage ? `${tax.rate}%` : `$${tax.amount}`}
                                {tax.withholding_rate && ` (${tax.withholding_rate})`}
                              </span>
                              <Button 
                                type="button" 
                                size="sm" 
                                variant="ghost" 
                                onClick={() => removeAdditionalTax(index, taxIndex)}
                                className="h-6 w-6 p-0 text-red-600"
                              >
                                ×
                              </Button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div className="border-t pt-4">
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-gray-600">{t('invoice.subtotal')}:</span>
                    <span className="font-medium">${invoiceSubtotal.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">{t('invoice.totalVAT')}:</span>
                    <span className="font-medium">${invoiceTotalVAT.toFixed(2)}</span>
                  </div>
                  {invoiceAdditionalTaxes > 0 && (
                    <div className="flex justify-between">
                      <span className="text-gray-600">{t('invoice.additionalTaxes')}:</span>
                      <span className="font-medium">${invoiceAdditionalTaxes.toFixed(2)}</span>
                    </div>
                  )}
                  {invoiceVATWithholding > 0 && (
                    <>
                      <div className="flex justify-between text-red-600">
                        <span>{t('invoice.vatWithholding')}:</span>
                        <span className="font-medium">-${invoiceVATWithholding.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between text-red-600">
                        <span>{t('invoice.totalWithholding')}:</span>
                        <span className="font-medium">-${invoiceVATWithholding.toFixed(2)}</span>
                      </div>
                    </>
                  )}
                  <div className="flex justify-between text-lg font-bold border-t pt-2">
                    <span>{t('invoice.grandTotal')}:</span>
                    <span>${invoiceTotal.toFixed(2)}</span>
                  </div>
                </div>
              </div>

              <div>
                <Label>{t('invoice.dueDate')}</Label>
                <Input type="date" value={newInvoice.due_date} onChange={(e) => setNewInvoice({...newInvoice, due_date: e.target.value})} required />
              </div>

              <Button type="submit" className="w-full" data-testid="submit-invoice-btn">{t('invoice.createInvoice')}</Button>
            </form>
          </DialogContent>
        </Dialog>

        {/* Additional Tax Dialog */}
        <Dialog open={showAdditionalTaxDialog} onOpenChange={setShowAdditionalTaxDialog}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t('invoice.addAdditionalTax')}</DialogTitle>
              <DialogDescription>{t('invoice.subtitle')}</DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label>{t('invoice.taxType')}</Label>
                <Select 
                  value={newAdditionalTax.tax_type} 
                  onValueChange={(v) => {
                    let taxName = 'ÖTV';
                    if (v === 'withholding') taxName = 'Tevkifat';
                    else if (v === 'accommodation') taxName = 'Konaklama Vergisi';
                    else if (v === 'special_communication') taxName = 'ÖİV';
                    setNewAdditionalTax({...newAdditionalTax, tax_type: v, tax_name: taxName});
                  }}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="otv">{t('invoice.specialConsumptionTax')}</SelectItem>
                    <SelectItem value="withholding">{t('invoice.withholdingTax')}</SelectItem>
                    <SelectItem value="accommodation">{t('invoice.accommodationTax')}</SelectItem>
                    <SelectItem value="special_communication">{t('invoice.specialCommunicationTax')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {newAdditionalTax.tax_type === 'withholding' ? (
                <div>
                  <Label>{t('invoice.withholdingRate')}</Label>
                  <Select 
                    value={newAdditionalTax.withholding_rate || ''} 
                    onValueChange={(v) => setNewAdditionalTax({...newAdditionalTax, withholding_rate: v})}
                  >
                    <SelectTrigger><SelectValue placeholder="Select rate" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="10/10">Tümüne Tevkifat Uygula (All)</SelectItem>
                      <SelectItem value="9/10">9/10 Tevkifat Uygula (90%)</SelectItem>
                      <SelectItem value="7/10">7/10 Tevkifat Uygula (70%)</SelectItem>
                      <SelectItem value="5/10">5/10 Tevkifat Uygula (50%)</SelectItem>
                      <SelectItem value="4/10">4/10 Tevkifat Uygula (40%)</SelectItem>
                      <SelectItem value="3/10">3/10 Tevkifat Uygula (30%)</SelectItem>
                      <SelectItem value="2/10">2/10 Tevkifat Uygula (20%)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              ) : (
                <>
                  <div>
                    <Label>{t('invoice.calculationMethod')}</Label>
                    <Select 
                      value={newAdditionalTax.is_percentage ? 'percentage' : 'fixed'} 
                      onValueChange={(v) => setNewAdditionalTax({...newAdditionalTax, is_percentage: v === 'percentage'})}
                    >
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="percentage">{t('invoice.percentage')}</SelectItem>
                        <SelectItem value="fixed">{t('invoice.fixedAmount')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {newAdditionalTax.is_percentage ? (
                    <div>
                      <Label>{t('invoice.taxRate')}</Label>
                      <Input 
                        type="number" 
                        step="0.01" 
                        value={newAdditionalTax.rate} 
                        onChange={(e) => setNewAdditionalTax({...newAdditionalTax, rate: parseFloat(e.target.value)})} 
                        placeholder={t('invoice.taxRate')}
                      />
                    </div>
                  ) : (
                    <div>
                      <Label>{t('invoice.taxAmount')}</Label>
                      <Input 
                        type="number" 
                        step="0.01" 
                        value={newAdditionalTax.amount} 
                        onChange={(e) => setNewAdditionalTax({...newAdditionalTax, amount: parseFloat(e.target.value)})} 
                        placeholder={t('invoice.taxAmount')}
                      />
                    </div>
                  )}
                </>
              )}

              <div className="flex gap-2">
                <Button type="button" variant="outline" onClick={() => setShowAdditionalTaxDialog(false)} className="flex-1">
                  {t('common.cancel')}
                </Button>
                <Button type="button" onClick={addAdditionalTax} className="flex-1">
                  {t('invoice.addTax')}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        {/* Expense Dialog */}
        <Dialog open={openDialog === 'expense'} onOpenChange={(open) => !open && setOpenDialog(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Record Expense</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreateExpense} className="space-y-4">
              <div>
                <Label>Category</Label>
                <Select value={newExpense.category} onValueChange={(v) => setNewExpense({...newExpense, category: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="salaries">Salaries</SelectItem>
                    <SelectItem value="utilities">Utilities</SelectItem>
                    <SelectItem value="supplies">Supplies</SelectItem>
                    <SelectItem value="maintenance">Maintenance</SelectItem>
                    <SelectItem value="marketing">Marketing</SelectItem>
                    <SelectItem value="rent">Rent</SelectItem>
                    <SelectItem value="insurance">Insurance</SelectItem>
                    <SelectItem value="taxes">Taxes</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Description</Label>
                <Input value={newExpense.description} onChange={(e) => setNewExpense({...newExpense, description: e.target.value})} required />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Amount (excl. VAT)</Label>
                  <Input type="number" step="0.01" value={newExpense.amount} onChange={(e) => setNewExpense({...newExpense, amount: parseFloat(e.target.value)})} required />
                </div>
                <div>
                  <Label>VAT Rate %</Label>
                  <Select value={newExpense.vat_rate.toString()} onValueChange={(v) => setNewExpense({...newExpense, vat_rate: parseFloat(v)})}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="0">0%</SelectItem>
                      <SelectItem value="1">1%</SelectItem>
                      <SelectItem value="8">8%</SelectItem>
                      <SelectItem value="10">10%</SelectItem>
                      <SelectItem value="18">18%</SelectItem>
                      <SelectItem value="20">20%</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div>
                <Label>Date</Label>
                <Input type="date" value={newExpense.date} onChange={(e) => setNewExpense({...newExpense, date: e.target.value})} required />
              </div>
              <div>
                <Label>Supplier (Optional)</Label>
                <Select value={newExpense.supplier_id} onValueChange={(v) => setNewExpense({...newExpense, supplier_id: v})}>
                  <SelectTrigger><SelectValue placeholder="Select supplier" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    {suppliers.map(s => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Payment Method</Label>
                <Select value={newExpense.payment_method} onValueChange={(v) => setNewExpense({...newExpense, payment_method: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Cash</SelectItem>
                    <SelectItem value="card">Card</SelectItem>
                    <SelectItem value="bank_transfer">Bank Transfer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="pt-4 border-t">
                <div className="flex justify-between text-lg font-bold">
                  <span>Total (incl. VAT):</span>
                  <span>${(newExpense.amount * (1 + newExpense.vat_rate / 100)).toFixed(2)}</span>
                </div>
              </div>
              <Button type="submit" className="w-full">Record Expense</Button>
            </form>
          </DialogContent>
        </Dialog>

        {/* Supplier Dialog */}
        <Dialog open={openDialog === 'supplier'} onOpenChange={(open) => !open && setOpenDialog(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Supplier</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreateSupplier} className="space-y-4">
              <div>
                <Label>Name *</Label>
                <Input value={newSupplier.name} onChange={(e) => setNewSupplier({...newSupplier, name: e.target.value})} required />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Tax Office</Label>
                  <Input value={newSupplier.tax_office} onChange={(e) => setNewSupplier({...newSupplier, tax_office: e.target.value})} />
                </div>
                <div>
                  <Label>Tax Number</Label>
                  <Input value={newSupplier.tax_number} onChange={(e) => setNewSupplier({...newSupplier, tax_number: e.target.value})} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Email</Label>
                  <Input type="email" value={newSupplier.email} onChange={(e) => setNewSupplier({...newSupplier, email: e.target.value})} />
                </div>
                <div>
                  <Label>Phone</Label>
                  <Input value={newSupplier.phone} onChange={(e) => setNewSupplier({...newSupplier, phone: e.target.value})} />
                </div>
              </div>
              <div>
                <Label>Address</Label>
                <Textarea value={newSupplier.address} onChange={(e) => setNewSupplier({...newSupplier, address: e.target.value})} rows={2} />
              </div>
              <Button type="submit" className="w-full">Add Supplier</Button>
            </form>
          </DialogContent>
        </Dialog>

        {/* Bank Account Dialog */}
        <Dialog open={openDialog === 'bank'} onOpenChange={(open) => !open && setOpenDialog(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Bank Account</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreateBankAccount} className="space-y-4">
              <div>
                <Label>Account Name *</Label>
                <Input value={newBankAccount.name} onChange={(e) => setNewBankAccount({...newBankAccount, name: e.target.value})} required />
              </div>
              <div>
                <Label>Bank Name *</Label>
                <Input value={newBankAccount.bank_name} onChange={(e) => setNewBankAccount({...newBankAccount, bank_name: e.target.value})} required />
              </div>
              <div>
                <Label>Account Number *</Label>
                <Input value={newBankAccount.account_number} onChange={(e) => setNewBankAccount({...newBankAccount, account_number: e.target.value})} required />
              </div>
              <div>
                <Label>IBAN</Label>
                <Input value={newBankAccount.iban} onChange={(e) => setNewBankAccount({...newBankAccount, iban: e.target.value})} />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Currency</Label>
                  <Select value={newBankAccount.currency} onValueChange={(v) => setNewBankAccount({...newBankAccount, currency: v})}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="USD">USD</SelectItem>
                      <SelectItem value="EUR">EUR</SelectItem>
                      <SelectItem value="TRY">TRY</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Initial Balance</Label>
                  <Input type="number" step="0.01" value={newBankAccount.balance} onChange={(e) => setNewBankAccount({...newBankAccount, balance: parseFloat(e.target.value)})} />
                </div>
              </div>
              <Button type="submit" className="w-full">Add Bank Account</Button>
            </form>
          </DialogContent>
        </Dialog>

        {/* Inventory Dialog */}
        <Dialog open={openDialog === 'inventory'} onOpenChange={(open) => !open && setOpenDialog(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Inventory Item</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreateInventoryItem} className="space-y-4">
              <div>
                <Label>Item Name *</Label>
                <Input value={newInventoryItem.name} onChange={(e) => setNewInventoryItem({...newInventoryItem, name: e.target.value})} required />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Category</Label>
                  <Input value={newInventoryItem.category} onChange={(e) => setNewInventoryItem({...newInventoryItem, category: e.target.value})} required />
                </div>
                <div>
                  <Label>SKU</Label>
                  <Input value={newInventoryItem.sku} onChange={(e) => setNewInventoryItem({...newInventoryItem, sku: e.target.value})} />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <Label>Quantity</Label>
                  <Input type="number" step="0.01" value={newInventoryItem.quantity} onChange={(e) => setNewInventoryItem({...newInventoryItem, quantity: parseFloat(e.target.value)})} required />
                </div>
                <div>
                  <Label>Unit</Label>
                  <Input value={newInventoryItem.unit} onChange={(e) => setNewInventoryItem({...newInventoryItem, unit: e.target.value})} required />
                </div>
                <div>
                  <Label>Unit Cost</Label>
                  <Input type="number" step="0.01" value={newInventoryItem.unit_cost} onChange={(e) => setNewInventoryItem({...newInventoryItem, unit_cost: parseFloat(e.target.value)})} required />
                </div>
              </div>
              <div>
                <Label>Reorder Level</Label>
                <Input type="number" value={newInventoryItem.reorder_level} onChange={(e) => setNewInventoryItem({...newInventoryItem, reorder_level: parseFloat(e.target.value)})} />
              </div>
              <Button type="submit" className="w-full">Add Item</Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
};

export default InvoiceModule;
