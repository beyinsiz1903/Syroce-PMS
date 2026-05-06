import { useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Building2,
  Plus,
  DollarSign,
  CreditCard,
  Search,
  AlertTriangle
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const CityLedgerAccounts = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedAccount, setSelectedAccount] = useState(null);
  const [paymentDialogOpen, setPaymentDialogOpen] = useState(false);
  const [paymentAmount, setPaymentAmount] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('bank_transfer');
  const [paymentReference, setPaymentReference] = useState('');
  const [postingPayment, setPostingPayment] = useState(false);

  const [newAccountDialogOpen, setNewAccountDialogOpen] = useState(false);
  const [newAccountData, setNewAccountData] = useState({
    account_name: '',
    company_name: '',
    contact_person: '',
    email: '',
    phone: '',
    credit_limit: '',
    payment_terms: 30,
  });
  const [creatingAccount, setCreatingAccount] = useState(false);

  useEffect(() => {
    loadAccounts();
  }, []);

  const loadAccounts = async () => {
    setLoading(true);
    try {
      const response = await axios.get('/cashiering/city-ledger');
      const data = response.data?.accounts || [];
      setAccounts(data);
    } catch (error) {
      console.error('Failed to load city ledger accounts:', error);
      toast.error('City ledger hesapları yüklenemedi');
      setAccounts([]);
    } finally {
      setLoading(false);
    }
  };

  const filteredAccounts = accounts.filter((account) => {
    const term = searchTerm.toLowerCase();
    return (
      account.account_name.toLowerCase().includes(term) ||
      (account.company_name || '').toLowerCase().includes(term)
    );
  });

  const handleOpenPaymentDialog = (account) => {
    setSelectedAccount(account);
    setPaymentAmount('');
    setPaymentReference('');
    setPaymentMethod('bank_transfer');
    setPaymentDialogOpen(true);
  };

  const handlePostPayment = async () => {
    if (!selectedAccount) return;

    const amount = parseFloat(paymentAmount);
    if (Number.isNaN(amount) || amount <= 0) {
      toast.error('Geçerli bir ödeme tutarı girin');
      return;
    }

    setPostingPayment(true);
    try {
      const params = new URLSearchParams();
      params.append('account_id', selectedAccount.id);
      params.append('amount', amount.toString());
      params.append('payment_method', paymentMethod);
      if (paymentReference) params.append('reference', paymentReference);

      const response = await axios.post(`/cashiering/city-ledger-payment?${params.toString()}`);
      if (response.data?.success) {
        toast.success('Ödeme başarıyla işlendi');
        setPaymentDialogOpen(false);
        await loadAccounts();
      } else {
        toast.error('Ödeme işlenemedi');
      }
    } catch (error) {
      console.error('Failed to post payment:', error);
      toast.error('Ödeme kaydedilirken hata oluştu');
    } finally {
      setPostingPayment(false);
    }
  };

  const handleCreateAccount = async () => {
    if (!newAccountData.account_name || !newAccountData.company_name) {
      toast.error('Hesap adı ve şirket adı zorunludur');
      return;
    }

    setCreatingAccount(true);
    try {
      const payload = {
        ...newAccountData,
        credit_limit: newAccountData.credit_limit ? parseFloat(newAccountData.credit_limit) : 0,
        payment_terms: newAccountData.payment_terms ? Number(newAccountData.payment_terms) : 30,
      };
      const response = await axios.post('/cashiering/city-ledger', payload);
      if (response.data?.success) {
        toast.success('City ledger hesabı oluşturuldu');
        setNewAccountDialogOpen(false);
        setNewAccountData({
          account_name: '',
          company_name: '',
          contact_person: '',
          email: '',
          phone: '',
          credit_limit: '',
          payment_terms: 30,
        });
        await loadAccounts();
      } else {
        toast.error('Hesap oluşturulamadı');
      }
    } catch (error) {
      console.error('Failed to create city ledger account:', error);
      toast.error('Hesap oluşturulurken hata oluştu');
    } finally {
      setCreatingAccount(false);
    }
  };

  if (loading) {
    return (
      <>
        <div className="flex items-center justify-center h-screen">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600" />
        </div>
      </>
    );
  }

  return (
    <>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <Building2 className="w-8 h-8 text-blue-600" />
              {t('finance.cityLedger')} Accounts
            </h1>
            <p className="text-gray-600 mt-1">Direct billing accounts for corporate and travel agency partners</p>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="outline" onClick={loadAccounts}>
              Refresh
            </Button>
            <Button onClick={() => setNewAccountDialogOpen(true)}>
              <Plus className="w-4 h-4 mr-2" />
              New Account
            </Button>
          </div>
        </div>

        {/* Search & Summary */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <Card className="md:col-span-2">
            <CardContent className="pt-6">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
                <Input
                  className="pl-10"
                  placeholder="Search by account or company name..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="text-sm text-gray-600">Active Accounts</div>
              <div className="text-2xl font-bold text-blue-600 mt-1">{accounts.length}</div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="text-sm text-gray-600">Total Balance</div>
              <div className="text-2xl font-bold text-red-600 mt-1">
                ${accounts.reduce((sum, a) => sum + (a.current_balance || 0), 0).toFixed(2)}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Accounts List */}
        <Card>
          <CardHeader>
            <CardTitle>Accounts</CardTitle>
            <CardDescription>City ledger accounts with balances and credit limits</CardDescription>
          </CardHeader>
          <CardContent>
            {filteredAccounts.length === 0 ? (
              <div className="py-10 text-center text-gray-500">
                <AlertTriangle className="w-12 h-12 mx-auto mb-2" />
                <p className="font-semibold">No city ledger accounts found</p>
                <p className="text-sm mt-1">You can create a new account using the button above.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {filteredAccounts.map((account) => {
                  const balance = account.current_balance || 0;
                  const creditLimit = account.credit_limit || 0;
                  const available = creditLimit - balance;
                  const utilization = creditLimit > 0 ? (balance / creditLimit) * 100 : 0;

                  let statusColor = 'bg-green-100 text-green-800';
                  if (utilization > 90) statusColor = 'bg-red-100 text-red-800';
                  else if (utilization > 70) statusColor = 'bg-yellow-100 text-yellow-800';

                  return (
                    <div
                      key={account.id}
                      className="border rounded-lg p-4 flex flex-col md:flex-row md:items-center md:justify-between gap-4"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="text-lg font-semibold truncate">{account.account_name}</h3>
                          <Badge variant="outline">{account.company_name}</Badge>
                        </div>
                        <div className="text-sm text-gray-600 mb-2">
                          Credit Limit: ${creditLimit.toFixed(2)} | Balance: ${balance.toFixed(2)} | Available: $
                          {available.toFixed(2)}
                        </div>
                        <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
                          <div
                            className="h-2 rounded-full bg-blue-500"
                            style={{ width: `${Math.min(100, utilization)}%` }}
                          />
                        </div>
                      </div>

                      <div className="flex flex-col items-end gap-2">
                        <Badge className={statusColor}>
                          Utilization {creditLimit > 0 ? `${utilization.toFixed(0)}%` : 'N/A'}
                        </Badge>
                        <div className="flex gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleOpenPaymentDialog(account)}
                          >
                            <CreditCard className="w-4 h-4 mr-1" />
                            Post Payment
                          </Button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* New Account Dialog */}
        <Dialog open={newAccountDialogOpen} onOpenChange={setNewAccountDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>New City Ledger Account</DialogTitle>
              <DialogDescription>Create a direct billing account for a company or agency.</DialogDescription>
            </DialogHeader>

            <div className="space-y-4 mt-2">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-sm text-gray-600">Account Name</label>
                  <Input
                    value={newAccountData.account_name}
                    onChange={(e) => setNewAccountData({ ...newAccountData, account_name: e.target.value })}
                    placeholder="e.g. ABC Travel Ltd."
                  />
                </div>
                <div>
                  <label className="text-sm text-gray-600">Company Name</label>
                  <Input
                    value={newAccountData.company_name}
                    onChange={(e) => setNewAccountData({ ...newAccountData, company_name: e.target.value })}
                    placeholder="Legal company name"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="text-sm text-gray-600">Contact Person</label>
                  <Input
                    value={newAccountData.contact_person}
                    onChange={(e) => setNewAccountData({ ...newAccountData, contact_person: e.target.value })}
                  />
                </div>
                <div>
                  <label className="text-sm text-gray-600">Email</label>
                  <Input
                    type="email"
                    value={newAccountData.email}
                    onChange={(e) => setNewAccountData({ ...newAccountData, email: e.target.value })}
                  />
                </div>
                <div>
                  <label className="text-sm text-gray-600">Phone</label>
                  <Input
                    value={newAccountData.phone}
                    onChange={(e) => setNewAccountData({ ...newAccountData, phone: e.target.value })}
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-sm text-gray-600">Credit Limit</label>
                  <Input
                    type="number"
                    value={newAccountData.credit_limit}
                    onChange={(e) => setNewAccountData({ ...newAccountData, credit_limit: e.target.value })}
                    placeholder="e.g. 10000"
                  />
                </div>
                <div>
                  <label className="text-sm text-gray-600">Payment Terms (days)</label>
                  <Input
                    type="number"
                    value={newAccountData.payment_terms}
                    onChange={(e) => setNewAccountData({ ...newAccountData, payment_terms: e.target.value })}
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 mt-4">
                <Button variant="outline" onClick={() => setNewAccountDialogOpen(false)}>
                  Cancel
                </Button>
                <Button onClick={handleCreateAccount} disabled={creatingAccount}>
                  {creatingAccount ? 'Creating...' : 'Create Account'}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        {/* Post Payment Dialog */}
        <Dialog open={paymentDialogOpen} onOpenChange={setPaymentDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Post Payment</DialogTitle>
              <DialogDescription>
                Record a payment against the selected city ledger account.
              </DialogDescription>
            </DialogHeader>

            {selectedAccount && (
              <div className="space-y-4 mt-2">
                <div className="text-sm text-gray-700">
                  <div className="font-semibold">{selectedAccount.account_name}</div>
                  <div className="text-gray-500">{selectedAccount.company_name}</div>
                  <div className="mt-1 text-xs text-gray-500">
                    Current Balance: ${selectedAccount.current_balance?.toFixed(2) || '0.00'} | Credit Limit: $
                    {selectedAccount.credit_limit?.toFixed(2) || '0.00'}
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm text-gray-600">Amount</label>
                    <Input
                      type="number"
                      value={paymentAmount}
                      onChange={(e) => setPaymentAmount(e.target.value)}
                      placeholder="e.g. 500.00"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-gray-600">Payment Method</label>
                    <select
                      className="border rounded-md px-3 py-2 text-sm w-full"
                      value={paymentMethod}
                      onChange={(e) => setPaymentMethod(e.target.value)}
                    >
                      <option value="bank_transfer">Bank Transfer</option>
                      <option value="credit_card">Credit Card</option>
                      <option value="cash">Cash</option>
                      <option value="check">Check</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="text-sm text-gray-600">Reference</label>
                  <Input
                    value={paymentReference}
                    onChange={(e) => setPaymentReference(e.target.value)}
                    placeholder="e.g. Bank slip no, POS ref, etc."
                  />
                </div>

                <div className="flex justify-end gap-2 mt-4">
                  <Button variant="outline" onClick={() => setPaymentDialogOpen(false)}>
                    Cancel
                  </Button>
                  <Button onClick={handlePostPayment} disabled={postingPayment}>
                    {postingPayment ? 'Posting...' : 'Post Payment'}
                  </Button>
                </div>
              </div>
            )}
          </DialogContent>
        </Dialog>
      </div>
    </>
  );
};

export default CityLedgerAccounts;
