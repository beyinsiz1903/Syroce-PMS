import { useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import {
  Building2,
  Plus,
  CreditCard,
  Search,
  RefreshCw,
  FileText,
  Scissors,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import EmptyState from '@/components/EmptyState';
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';

export const validateCityLedgerPayment = (amountValue, balanceValue) => {
  const amount = Number(amountValue);
  const outstandingBalance = Number(balanceValue);

  if (!Number.isFinite(amount) || amount <= 0) return 'Geçerli bir ödeme tutarı girin';
  if (!Number.isFinite(outstandingBalance) || outstandingBalance <= 0) {
    return 'Bu hesabın ödenecek bakiyesi bulunmuyor';
  }
  if (amount > outstandingBalance) return 'Ödeme tutarı açık bakiyeyi aşamaz';
  return null;
};

export const getCityLedgerPaymentAllocations = (openItems, allocationValues) => (
  openItems
    .map((item) => ({ booking_id: item.booking_id, amount: Number(allocationValues[item.booking_id] || 0) }))
    .filter((allocation) => Number.isFinite(allocation.amount) && allocation.amount > 0)
);

export const validateCityLedgerPaymentAllocations = (amountValue, openItems, allocationValues) => {
  const amount = Number(amountValue);
  const allocations = getCityLedgerPaymentAllocations(openItems, allocationValues);
  if (!allocations.length) return null; // A general city-ledger payment remains supported.

  const allocationTotal = allocations.reduce((sum, allocation) => sum + allocation.amount, 0);
  if (Math.abs(allocationTotal - amount) > 0.005) {
    return 'Oda bazlı dağıtım toplamı ödeme tutarına eşit olmalıdır';
  }
  const oversubscribed = allocations.some((allocation) => {
    const item = openItems.find((candidate) => candidate.booking_id === allocation.booking_id);
    return item && allocation.amount - Number(item.open_amount || 0) > 0.005;
  });
  return oversubscribed ? 'Bir odaya ayrılan tahsilat o odanın açık bakiyesini aşamaz' : null;
};

const EMPTY_ACCOUNT = {
  source_company_id: '',
  account_name: '',
  company_name: '',
  contact_person: '',
  email: '',
  phone: '',
  credit_limit: '',
  payment_terms: 30,
  // Fatura bilgileri
  tax_number: '',
  tax_office: '',
  billing_address: '',
  billing_city: '',
  billing_postal_code: '',
  billing_country: 'Türkiye',
};

export const buildCityLedgerCandidateAccount = (candidate) => {
  const parsedTerms = Number.parseInt(candidate.payment_terms, 10);
  return {
    ...EMPTY_ACCOUNT,
    ...candidate,
    payment_terms: Number.isFinite(parsedTerms) ? parsedTerms : 30,
    billing_country: candidate.billing_country || 'Türkiye',
  };
};

const CityLedgerAccounts = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const currency = tenant?.currency || cachedTenantCurrency();
  const [accounts, setAccounts] = useState([]);
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedAccount, setSelectedAccount] = useState(null);
  const [paymentDialogOpen, setPaymentDialogOpen] = useState(false);
  const [paymentAmount, setPaymentAmount] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('bank_transfer');
  const [paymentReference, setPaymentReference] = useState('');
  const [paymentRequestId, setPaymentRequestId] = useState('');
  const [postingPayment, setPostingPayment] = useState(false);
  const [paymentOpenItems, setPaymentOpenItems] = useState([]);
  const [paymentAllocations, setPaymentAllocations] = useState({});
  const [loadingPaymentItems, setLoadingPaymentItems] = useState(false);

  const [openItemsDialogOpen, setOpenItemsDialogOpen] = useState(false);
  const [openItemsAccount, setOpenItemsAccount] = useState(null);
  const [openItems, setOpenItems] = useState([]);
  const [openItemsSummary, setOpenItemsSummary] = useState(null);
  const [loadingOpenItems, setLoadingOpenItems] = useState(false);

  const [adjustDialogOpen, setAdjustDialogOpen] = useState(false);
  const [adjustAccount, setAdjustAccount] = useState(null);
  const [adjustAmount, setAdjustAmount] = useState('');
  const [adjustType, setAdjustType] = useState('commission');
  const [adjustDescription, setAdjustDescription] = useState('');
  const [postingAdjust, setPostingAdjust] = useState(false);

  const [newAccountDialogOpen, setNewAccountDialogOpen] = useState(false);
  const [newAccountData, setNewAccountData] = useState(EMPTY_ACCOUNT);
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
      toast.error('Cari hesaplar yüklenemedi');
      setAccounts([]);
    }
    try {
      const candidateResponse = await axios.get('/cashiering/city-ledger-candidates');
      setCandidates(candidateResponse.data?.candidates || []);
    } catch (error) {
      console.error('Failed to load city ledger candidates:', error);
      toast.error('Tanımlanacak şirketler yüklenemedi');
      setCandidates([]);
    } finally {
      setLoading(false);
    }
  };

  const openCandidate = (candidate) => {
    setNewAccountData(buildCityLedgerCandidateAccount(candidate));
    setNewAccountDialogOpen(true);
  };

  const filteredAccounts = accounts.filter((account) => {
    const term = searchTerm.toLowerCase();
    return (
      (account.account_name || '').toLowerCase().includes(term) ||
      (account.company_name || '').toLowerCase().includes(term)
    );
  });

  const loadOpenItems = async (account) => {
    const response = await axios.get(`/cashiering/city-ledger/${account.id}/open-items`);
    return response.data;
  };

  const handleOpenPaymentDialog = async (account) => {
    setSelectedAccount(account);
    setPaymentAmount('');
    setPaymentReference('');
    setPaymentMethod('bank_transfer');
    setPaymentRequestId(globalThis.crypto?.randomUUID?.() || `payment-${Date.now()}`);
    setPaymentOpenItems([]);
    setPaymentAllocations({});
    setPaymentDialogOpen(true);
    setLoadingPaymentItems(true);
    try {
      const data = await loadOpenItems(account);
      setPaymentOpenItems(data.items || []);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Oda bazlı cari bakiyesi yüklenemedi');
    } finally {
      setLoadingPaymentItems(false);
    }
  };

  const handleOpenItemsDialog = async (account) => {
    setOpenItemsAccount(account);
    setOpenItems([]);
    setOpenItemsSummary(null);
    setOpenItemsDialogOpen(true);
    setLoadingOpenItems(true);
    try {
      const data = await loadOpenItems(account);
      setOpenItems(data.items || []);
      setOpenItemsSummary(data.summary || null);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Oda bazlı cari bakiyesi yüklenemedi');
    } finally {
      setLoadingOpenItems(false);
    }
  };

  const setPaymentAllocation = (bookingId, value) => {
    setPaymentAllocations((current) => ({ ...current, [bookingId]: value }));
  };

  const handleOpenAdjustDialog = (account) => {
    setAdjustAccount(account);
    setAdjustAmount('');
    setAdjustType('commission');
    setAdjustDescription('');
    setAdjustDialogOpen(true);
  };

  const handlePostAdjustment = async () => {
    if (!adjustAccount) return;
    const amount = parseFloat(adjustAmount);
    const balance = Number(adjustAccount.current_balance || 0);
    if (!Number.isFinite(amount) || amount <= 0) {
      toast.error('Geçerli bir tutar girin');
      return;
    }
    if (amount > balance + 0.005) {
      toast.error('Ayarlama tutarı mevcut bakiyeyi aşamaz');
      return;
    }
    if (!adjustDescription.trim()) {
      toast.error('Açıklama zorunludur');
      return;
    }
    setPostingAdjust(true);
    try {
      const params = new URLSearchParams({
        account_id: adjustAccount.id,
        amount: amount.toString(),
        description: adjustDescription,
        adjustment_type: adjustType,
        idempotency_key: `adj-${adjustAccount.id}-${Date.now()}`,
      });
      const res = await axios.post(`/cashiering/city-ledger-adjustment?${params.toString()}`);
      if (res.data?.success) {
        toast.success(`Ayarlama kaydedildi. Yeni bakiye: ${formatCurrency(res.data.new_balance, adjustAccount.currency || currency)}`);
        setAdjustDialogOpen(false);
        await loadAccounts();
      } else {
        toast.error('Ayarlama kaydedilemedi');
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Ayarlama sırasında hata oluştu');
    } finally {
      setPostingAdjust(false);
    }
  };

  const handlePostPayment = async () => {
    if (!selectedAccount) return;

    const outstandingBalance = Number(selectedAccount.current_balance || 0);
    const validationError = validateCityLedgerPayment(paymentAmount, outstandingBalance);
    if (validationError) {
      toast.error(validationError);
      return;
    }
    const amount = Number(paymentAmount);
    const allocations = getCityLedgerPaymentAllocations(paymentOpenItems, paymentAllocations);
    const allocationError = validateCityLedgerPaymentAllocations(paymentAmount, paymentOpenItems, paymentAllocations);
    if (allocationError) {
      toast.error(allocationError);
      return;
    }

    setPostingPayment(true);
    try {
      const params = new URLSearchParams();
      params.append('account_id', selectedAccount.id);
      params.append('amount', amount.toString());
      params.append('payment_method', paymentMethod);
      params.append('idempotency_key', paymentRequestId);
      if (paymentReference) params.append('reference', paymentReference);

      const response = await axios.post(`/cashiering/city-ledger-payment?${params.toString()}`, allocations.length ? { allocations } : undefined);
      if (response.data?.success) {
        toast.success('Ödeme başarıyla işlendi');
        setPaymentDialogOpen(false);
        await loadAccounts();
      } else {
        toast.error('Ödeme işlenemedi');
      }
    } catch (error) {
      console.error('Failed to post payment:', error);
      toast.error(error.response?.data?.detail || 'Ödeme kaydedilirken hata oluştu');
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
        toast.success('Cari hesap başarıyla oluşturuldu');
        setNewAccountDialogOpen(false);
        setNewAccountData(EMPTY_ACCOUNT);
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

  const field = (key) => (e) => setNewAccountData({ ...newAccountData, [key]: e.target.value });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600" />
      </div>
    );
  }

  return (
    <>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <Building2 className="w-8 h-8 text-blue-600" />
              Cari Hesaplar
            </h1>
            <p className="text-gray-600 mt-1">Kurumsal ve acente partnerlerine ait doğrudan faturalama hesapları</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="outline" onClick={loadAccounts}>
              <RefreshCw className="w-4 h-4 mr-2" />
              Yenile
            </Button>
            <Button onClick={() => setNewAccountDialogOpen(true)}>
              <Plus className="w-4 h-4 mr-2" />
              Yeni Hesap
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
                  placeholder="Hesap veya şirket adına göre ara..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="text-sm text-gray-600">Aktif Hesaplar</div>
              <div className="text-2xl font-bold text-blue-600 mt-1">{accounts.length}</div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="text-sm text-gray-600">Toplam Bakiye</div>
              <div className="text-2xl font-bold text-red-600 mt-1">
                {formatCurrency(accounts.reduce((sum, a) => sum + Number(a.current_balance || 0), 0), currency)}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Accounts List */}
        <Card>
          <CardHeader>
            <CardTitle>Hesaplar</CardTitle>
            <CardDescription>Bakiye ve kredi limitleriyle cari hesaplar</CardDescription>
          </CardHeader>
          <CardContent>
            {filteredAccounts.length === 0 ? (
              accounts.length === 0 ? (
                <EmptyState
                  icon={Building2}
                  title={t('emptyStates.cityLedger.title')}
                  description={t('emptyStates.cityLedger.desc')}
                  actionText={t('emptyStates.cityLedger.action')}
                  onAction={() => setNewAccountDialogOpen(true)}
                />
              ) : (
                <EmptyState
                  icon={Search}
                  title={t('emptyStates.cityLedger.noResultsTitle')}
                  description={t('emptyStates.cityLedger.noResultsDesc')}
                />
              )
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

                  const accountCurrency = account.currency || currency;

                  return (
                    <div
                      key={account.id}
                      className="border rounded-lg p-4 flex flex-col md:flex-row md:items-center md:justify-between gap-4"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="text-lg font-semibold truncate">{account.account_name}</h3>
                          <Badge variant="outline">{account.company_name}</Badge>
                          {account.tax_number && (
                            <Badge variant="secondary" className="text-xs">VKN: {account.tax_number}</Badge>
                          )}
                        </div>
                        <div className="text-sm text-gray-600 mb-2">
                          Kredi Limiti: {formatCurrency(creditLimit, accountCurrency)} &nbsp;|&nbsp; Bakiye: {formatCurrency(balance, accountCurrency)} &nbsp;|&nbsp; Kullanılabilir: {formatCurrency(available, accountCurrency)}
                        </div>
                        <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
                          <div
                            className="h-2 rounded-full bg-blue-500"
                            style={{ width: `${Math.min(100, utilization)}%` }}
                          />
                        </div>
                        {account.billing_address && (
                          <div className="text-xs text-gray-400 mt-1">
                            {account.billing_address}, {account.billing_city}
                            {account.tax_office && ` — ${account.tax_office} V.D.`}
                          </div>
                        )}
                      </div>

                      <div className="flex flex-col items-end gap-2">
                        <Badge className={statusColor}>
                          Kullanım {creditLimit > 0 ? `${utilization.toFixed(0)}%` : 'Limitsiz'}
                        </Badge>
                        <div className="flex flex-wrap justify-end gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleOpenItemsDialog(account)}
                            title="Bakiyenin rezervasyon ve oda dağılımını gör"
                          >
                            <FileText className="w-4 h-4 mr-1" />
                            Oda Bakiyeleri
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleOpenPaymentDialog(account)}
                            disabled={!Number.isFinite(Number(balance)) || Number(balance) <= 0}
                            title={Number(balance) > 0 ? 'Ödeme kaydet' : 'Açık bakiye yok'}
                          >
                            <CreditCard className="w-4 h-4 mr-1" />
                            Ödeme Kaydet
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleOpenAdjustDialog(account)}
                            disabled={!Number.isFinite(Number(balance)) || Number(balance) <= 0}
                            title={Number(balance) > 0 ? 'Komisyon veya fark ayarla' : 'Açık bakiye yok'}
                          >
                            <Scissors className="w-4 h-4 mr-1" />
                            Komisyon / Fark
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

        <Card>
          <CardHeader>
            <CardTitle>Tanımlanacaklar</CardTitle>
            <CardDescription>
              Şirketler ekranında kayıtlı olup henüz cari hesaba dönüştürülmemiş kurumsal ve acente kayıtları
            </CardDescription>
          </CardHeader>
          <CardContent>
            {candidates.length === 0 ? (
              <div className="rounded-lg border border-dashed p-6 text-center text-sm text-gray-500">
                Cari hesaba dönüştürülmeyi bekleyen şirket bulunmuyor.
              </div>
            ) : (
              <div className="space-y-3">
                {candidates.map((candidate) => (
                  <div key={candidate.source_company_id} className="flex flex-col gap-3 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <div className="font-semibold truncate">{candidate.company_name}</div>
                      <div className="mt-1 text-sm text-gray-500">
                        {[candidate.contact_person, candidate.email, candidate.phone].filter(Boolean).join(' · ') || 'İletişim bilgisi girilmemiş'}
                      </div>
                      {candidate.tax_number && <div className="mt-1 text-xs text-gray-400">VKN / TCKN: {candidate.tax_number}</div>}
                    </div>
                    <Button variant="outline" onClick={() => openCandidate(candidate)}>
                      <Plus className="mr-2 h-4 w-4" />
                      Cari Hesap Oluştur
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* New Account Dialog */}
        <Dialog open={newAccountDialogOpen} onOpenChange={setNewAccountDialogOpen}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Building2 className="w-5 h-5" /> Yeni Cari Hesap
              </DialogTitle>
              <DialogDescription>Kurumsal veya acente partnerlerine ait doğrudan faturalama hesabı oluşturun.</DialogDescription>
            </DialogHeader>

            <div className="space-y-5 mt-2">
              {/* Temel bilgiler */}
              <div>
                <p className="text-sm font-semibold text-gray-700 mb-3">Hesap Bilgileri</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm text-gray-600">Hesap Adı *</label>
                    <Input
                      value={newAccountData.account_name}
                      onChange={field('account_name')}
                      placeholder="ör. ABC Seyahat A.Ş."
                    />
                  </div>
                  <div>
                    <label className="text-sm text-gray-600">Şirket Ticaret Unvanı *</label>
                    <Input
                      value={newAccountData.company_name}
                      onChange={field('company_name')}
                      placeholder="Resmi ticaret unvanı"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-3">
                  <div>
                    <label className="text-sm text-gray-600">Yetkili Kişi</label>
                    <Input value={newAccountData.contact_person} onChange={field('contact_person')} />
                  </div>
                  <div>
                    <label className="text-sm text-gray-600">E-posta</label>
                    <Input type="email" value={newAccountData.email} onChange={field('email')} />
                  </div>
                  <div>
                    <label className="text-sm text-gray-600">Telefon</label>
                    <Input value={newAccountData.phone} onChange={field('phone')} />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
                  <div>
                    <label className="text-sm text-gray-600">Kredi Limiti ({currency})</label>
                    <Input
                      type="number"
                      value={newAccountData.credit_limit}
                      onChange={field('credit_limit')}
                      placeholder="ör. 10000"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-gray-600">Ödeme Vadesi (gün)</label>
                    <Input
                      type="number"
                      value={newAccountData.payment_terms}
                      onChange={field('payment_terms')}
                    />
                  </div>
                </div>
              </div>

              {/* Fatura bilgileri */}
              <div className="border-t pt-4">
                <p className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                  <FileText className="w-4 h-4" /> Fatura Bilgileri
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm text-gray-600">Vergi Kimlik Numarası (VKN / TCKN)</label>
                    <Input
                      value={newAccountData.tax_number}
                      onChange={field('tax_number')}
                      placeholder="ör. 1234567890"
                      maxLength={11}
                    />
                  </div>
                  <div>
                    <label className="text-sm text-gray-600">Vergi Dairesi</label>
                    <Input
                      value={newAccountData.tax_office}
                      onChange={field('tax_office')}
                      placeholder="ör. Kadıköy Vergi Dairesi"
                    />
                  </div>
                </div>

                <div className="mt-3">
                  <label className="text-sm text-gray-600">Fatura Adresi</label>
                  <Input
                    value={newAccountData.billing_address}
                    onChange={field('billing_address')}
                    placeholder="Sokak, mahalle, bina no..."
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-3">
                  <div>
                    <label className="text-sm text-gray-600">Şehir</label>
                    <Input value={newAccountData.billing_city} onChange={field('billing_city')} placeholder="İstanbul" />
                  </div>
                  <div>
                    <label className="text-sm text-gray-600">Posta Kodu</label>
                    <Input value={newAccountData.billing_postal_code} onChange={field('billing_postal_code')} placeholder="34000" />
                  </div>
                  <div>
                    <label className="text-sm text-gray-600">Ülke</label>
                    <Input value={newAccountData.billing_country} onChange={field('billing_country')} />
                  </div>
                </div>
              </div>

              <div className="flex justify-end gap-2 mt-2">
                <Button variant="outline" onClick={() => setNewAccountDialogOpen(false)}>
                  İptal
                </Button>
                <Button onClick={handleCreateAccount} disabled={creatingAccount}>
                  {creatingAccount ? 'Oluşturuluyor...' : 'Hesabı Oluştur'}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        {/* Post Payment Dialog */}
        <Dialog open={paymentDialogOpen} onOpenChange={setPaymentDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Ödeme Kaydet</DialogTitle>
              <DialogDescription>
                Seçilen cari hesaba ödeme kaydı giriniz.
              </DialogDescription>
            </DialogHeader>

            {selectedAccount && (
              <div className="space-y-4 mt-2">
                <div className="text-sm text-gray-700">
                  <div className="font-semibold">{selectedAccount.account_name}</div>
                  <div className="text-gray-500">{selectedAccount.company_name}</div>
                  <div className="mt-1 text-xs text-gray-500">
                    Mevcut Bakiye: {formatCurrency(selectedAccount.current_balance, selectedAccount.currency || currency)} &nbsp;|&nbsp;
                    Kredi Limiti: {formatCurrency(selectedAccount.credit_limit, selectedAccount.currency || currency)}
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm text-gray-600">Tutar ({selectedAccount.currency || currency})</label>
                    <Input
                      type="number"
                      value={paymentAmount}
                      onChange={(e) => setPaymentAmount(e.target.value)}
                      placeholder="ör. 500.00"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-gray-600">Ödeme Yöntemi</label>
                    <select
                      className="border rounded-md px-3 py-2 text-sm w-full"
                      value={paymentMethod}
                      onChange={(e) => setPaymentMethod(e.target.value)}
                    >
                      <option value="bank_transfer">Havale / EFT</option>
                      <option value="credit_card">Kredi Kartı</option>
                      <option value="cash">Nakit</option>
                      <option value="check">Çek</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="text-sm text-gray-600">Referans / Dekont No</label>
                  <Input
                    value={paymentReference}
                    onChange={(e) => setPaymentReference(e.target.value)}
                    placeholder="ör. banka dekontu no, POS slip no..."
                  />
                </div>

                <div className="border rounded-md p-3 space-y-2">
                  <div>
                    <div className="text-sm font-medium text-gray-800">Oda bazlı tahsilat dağıtımı</div>
                    <p className="text-xs text-gray-500 mt-1">
                      Tahsilatı belirli odalara kapatmak için tutarı ilgili rezervasyona yazın. Alanları boş bırakırsanız genel cari ödemesi olarak kaydedilir.
                    </p>
                  </div>
                  {loadingPaymentItems ? (
                    <div className="text-sm text-gray-500">Oda bakiyeleri yükleniyor...</div>
                  ) : paymentOpenItems.length === 0 ? (
                    <div className="text-sm text-gray-500">Bu cari için oda bağlantılı açık bakiye bulunmuyor.</div>
                  ) : (
                    <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                      {paymentOpenItems.map((item) => (
                        <div key={item.booking_id} className="grid grid-cols-[1fr_120px] gap-3 items-center rounded border bg-slate-50 p-2">
                          <div className="min-w-0">
                            <div className="text-sm font-medium truncate">Oda {item.room_number} · {item.guest_name}</div>
                            <div className="text-xs text-gray-500">
                              Açık: {formatCurrency(item.open_amount, item.currency || selectedAccount.currency || currency)}
                              {item.check_in && ` · ${String(item.check_in).slice(0, 10)}`}
                            </div>
                          </div>
                          <Input
                            aria-label={`Oda ${item.room_number} tahsilat tutarı`}
                            type="number"
                            min="0"
                            max={item.open_amount}
                            step="0.01"
                            value={paymentAllocations[item.booking_id] || ''}
                            onChange={(event) => setPaymentAllocation(item.booking_id, event.target.value)}
                            placeholder="0,00"
                          />
                        </div>
                      ))}
                    </div>
                  )}
                  {Object.values(paymentAllocations).some((value) => Number(value) > 0) && (
                    <div className="text-xs text-gray-600 pt-1 border-t">
                      Oda dağıtım toplamı: <strong>{formatCurrency(Object.values(paymentAllocations).reduce((sum, value) => sum + (Number(value) || 0), 0), selectedAccount.currency || currency)}</strong>
                    </div>
                  )}
                </div>

                <div className="flex justify-end gap-2 mt-4">
                  <Button variant="outline" onClick={() => setPaymentDialogOpen(false)}>
                    İptal
                  </Button>
                  <Button onClick={handlePostPayment} disabled={postingPayment}>
                    {postingPayment ? 'Kaydediliyor...' : 'Ödemeyi Kaydet'}
                  </Button>
                </div>
              </div>
            )}
          </DialogContent>
        </Dialog>

        <Dialog open={openItemsDialogOpen} onOpenChange={setOpenItemsDialogOpen}>
          <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Oda Bazlı Cari Bakiye</DialogTitle>
              <DialogDescription>
                {openItemsAccount ? `${openItemsAccount.account_name} hesabındaki bakiyenin hangi rezervasyonlardan kaynaklandığını inceleyin.` : 'Cari bakiyenin rezervasyon dağılımı'}
              </DialogDescription>
            </DialogHeader>

            {loadingOpenItems ? (
              <div className="py-8 text-center text-sm text-gray-500">Oda bakiyeleri yükleniyor...</div>
            ) : (
              <div className="space-y-3">
                {openItems.map((item) => (
                  <div key={item.booking_id} className="rounded-lg border p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <div className="font-medium">Oda {item.room_number} · {item.guest_name}</div>
                        <div className="text-xs text-gray-500 mt-1">
                          {item.check_in ? `${String(item.check_in).slice(0, 10)} → ${String(item.check_out || '').slice(0, 10)}` : `Rezervasyon: ${item.booking_id}`}
                        </div>
                      </div>
                      <Badge variant={Number(item.open_amount) > 0 ? 'destructive' : 'secondary'}>
                        Açık {formatCurrency(item.open_amount, item.currency || openItemsAccount?.currency || currency)}
                      </Badge>
                    </div>
                    <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-gray-600">
                      <div>Tahakkuk: {formatCurrency(item.charged_amount, item.currency || openItemsAccount?.currency || currency)}</div>
                      <div>Odaya işlenen tahsilat: {formatCurrency(item.allocated_payment_amount, item.currency || openItemsAccount?.currency || currency)}</div>
                    </div>
                  </div>
                ))}
                {openItems.length === 0 && <div className="py-6 text-center text-sm text-gray-500">Oda bağlantılı cari hareketi bulunmuyor.</div>}
                {openItemsSummary && (
                  <div className="rounded-md bg-slate-50 border p-3 text-sm space-y-1">
                    <div>Odaların açık toplamı: <strong>{formatCurrency(openItemsSummary.room_open_total, openItemsAccount?.currency || currency)}</strong></div>
                    {Number(openItemsSummary.unallocated_payment_total || 0) > 0 && <div className="text-amber-700">Oda atanmamış eski tahsilat: {formatCurrency(openItemsSummary.unallocated_payment_total, openItemsAccount?.currency || currency)}</div>}
                    {Number(openItemsSummary.adjustment_total || 0) > 0 && <div className="text-amber-700">Komisyon / fark düşümü: {formatCurrency(openItemsSummary.adjustment_total, openItemsAccount?.currency || currency)}</div>}
                    {Math.abs(Number(openItemsSummary.balance_difference || 0)) > 0.005 && <div className="text-amber-700">Cari bakiyesi ile oda dağılımı arasında {formatCurrency(openItemsSummary.balance_difference, openItemsAccount?.currency || currency)} fark var. Eski hareketleri oda seçmeden kaydetmiş olabilirsiniz.</div>}
                  </div>
                )}
              </div>
            )}
          </DialogContent>
        </Dialog>

        {/* Komisyon / Fark Ayarlama Dialog */}
        <Dialog open={adjustDialogOpen} onOpenChange={setAdjustDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Scissors className="w-5 h-5" /> Komisyon / Fark Ayarla
              </DialogTitle>
              <DialogDescription>
                Acentenin ödediği tutardan düştüğü komisyon veya kabul edilen farkı bakiyeden silin.
              </DialogDescription>
            </DialogHeader>

            {adjustAccount && (
              <div className="space-y-4 mt-2">
                <div className="text-sm text-gray-700">
                  <div className="font-semibold">{adjustAccount.account_name}</div>
                  <div className="text-gray-500">{adjustAccount.company_name}</div>
                  <div className="mt-1 text-xs text-gray-500">
                    Mevcut Bakiye: <span className="font-medium text-red-600">{formatCurrency(adjustAccount.current_balance, adjustAccount.currency || currency)}</span>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm text-gray-600">Tutar ({adjustAccount.currency || currency})</label>
                    <Input
                      type="number"
                      value={adjustAmount}
                      onChange={(e) => setAdjustAmount(e.target.value)}
                      placeholder="ör. 750.00"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-gray-600">Ayarlama Tipi</label>
                    <select
                      className="border rounded-md px-3 py-2 text-sm w-full"
                      value={adjustType}
                      onChange={(e) => setAdjustType(e.target.value)}
                    >
                      <option value="commission">Acente Komisyonu</option>
                      <option value="discount">İndirim / Promosyon</option>
                      <option value="writeoff">Şüpheli Alacak Silme</option>
                      <option value="other">Diğer</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="text-sm text-gray-600">Açıklama *</label>
                  <Input
                    value={adjustDescription}
                    onChange={(e) => setAdjustDescription(e.target.value)}
                    placeholder={`ör. Acenta komisyonu %15 — 750 ${adjustAccount.currency || currency}`}
                  />
                </div>

                {adjustAmount && parseFloat(adjustAmount) > 0 && (
                  <div className="bg-amber-50 border border-amber-200 rounded-md p-3 text-sm text-amber-800">
                    Bakiye <strong>{formatCurrency(adjustAccount.current_balance, adjustAccount.currency || currency)}</strong> → <strong>{formatCurrency(Math.max(0, (adjustAccount.current_balance || 0) - parseFloat(adjustAmount || 0)), adjustAccount.currency || currency)}</strong> olacak.
                  </div>
                )}

                <div className="flex justify-end gap-2 mt-4">
                  <Button variant="outline" onClick={() => setAdjustDialogOpen(false)}>
                    İptal
                  </Button>
                  <Button onClick={handlePostAdjustment} disabled={postingAdjust}>
                    {postingAdjust ? 'Kaydediliyor...' : 'Ayarlamayı Kaydet'}
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
