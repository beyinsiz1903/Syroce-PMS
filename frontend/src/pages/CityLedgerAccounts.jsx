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

const EMPTY_ACCOUNT = {
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
  const [paymentRequestId, setPaymentRequestId] = useState('');
  const [postingPayment, setPostingPayment] = useState(false);

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
    setPaymentRequestId(globalThis.crypto?.randomUUID?.() || `payment-${Date.now()}`);
    setPaymentDialogOpen(true);
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
        toast.success(`Ayarlama kaydedildi. Yeni bakiye: ₺${res.data.new_balance.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}`);
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

    setPostingPayment(true);
    try {
      const params = new URLSearchParams();
      params.append('account_id', selectedAccount.id);
      params.append('amount', amount.toString());
      params.append('payment_method', paymentMethod);
      params.append('idempotency_key', paymentRequestId);
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
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <Building2 className="w-8 h-8 text-blue-600" />
              Cari Hesaplar
            </h1>
            <p className="text-gray-600 mt-1">Kurumsal ve acente partnerlerine ait doğrudan faturalama hesapları</p>
          </div>
          <div className="flex items-center gap-3">
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
                ₺{accounts.reduce((sum, a) => sum + (a.current_balance || 0), 0).toLocaleString('tr-TR', { minimumFractionDigits: 2 })}
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

                  const fmt = (n) => n.toLocaleString('tr-TR', { minimumFractionDigits: 2 });

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
                          Kredi Limiti: ₺{fmt(creditLimit)} &nbsp;|&nbsp; Bakiye: ₺{fmt(balance)} &nbsp;|&nbsp; Kullanılabilir: ₺{fmt(available)}
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
                        <div className="flex gap-2">
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
                    <label className="text-sm text-gray-600">Kredi Limiti (₺)</label>
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
                    Mevcut Bakiye: ₺{selectedAccount.current_balance?.toLocaleString('tr-TR', { minimumFractionDigits: 2 }) || '0,00'} &nbsp;|&nbsp;
                    Kredi Limiti: ₺{selectedAccount.credit_limit?.toLocaleString('tr-TR', { minimumFractionDigits: 2 }) || '0,00'}
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm text-gray-600">Tutar (₺)</label>
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
                    Mevcut Bakiye: <span className="font-medium text-red-600">₺{(adjustAccount.current_balance || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2 })}</span>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm text-gray-600">Tutar (₺)</label>
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
                    placeholder="ör. Etstur Ağustos komisyonu %15 — 750 TL"
                  />
                </div>

                {adjustAmount && parseFloat(adjustAmount) > 0 && (
                  <div className="bg-amber-50 border border-amber-200 rounded-md p-3 text-sm text-amber-800">
                    Bakiye <strong>₺{(adjustAccount.current_balance || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2 })}</strong> → <strong>₺{Math.max(0, (adjustAccount.current_balance || 0) - parseFloat(adjustAmount || 0)).toLocaleString('tr-TR', { minimumFractionDigits: 2 })}</strong> olacak.
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
