import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle
} from '@/components/ui/dialog';
import {
  Loader2, Shield, Banknote, RefreshCw, Plus, RotateCcw, FileText,
  Search, X, ArrowDownCircle, ArrowUpCircle, Receipt
} from 'lucide-react';

const API = "";

export default function DepositTracking({ user, tenant, onLogout }) {
  const [deposits, setDeposits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');

  // New Deposit Dialog
  const [showNewDeposit, setShowNewDeposit] = useState(false);
  const [newDepositData, setNewDepositData] = useState({ booking_id: '', amount: '', method: 'cash', reference: '' });
  const [savingDeposit, setSavingDeposit] = useState(false);
  const [bookingSearch, setBookingSearch] = useState('');
  const [bookingResults, setBookingResults] = useState([]);
  const [selectedBooking, setSelectedBooking] = useState(null);
  const [searchingBookings, setSearchingBookings] = useState(false);

  // Refund Dialog
  const [showRefund, setShowRefund] = useState(false);
  const [refundTarget, setRefundTarget] = useState(null);
  const [refundData, setRefundData] = useState({ amount: '', method: 'cash', reason: '' });
  const [savingRefund, setSavingRefund] = useState(false);

  // Invoice Dialog
  const [showInvoice, setShowInvoice] = useState(false);
  const [invoiceTarget, setInvoiceTarget] = useState(null);
  const [invoiceHtml, setInvoiceHtml] = useState('');
  const [generatingInvoice, setGeneratingInvoice] = useState(false);

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const loadDeposits = useCallback(async () => {
    try {
      const res = await axios.get(`/pms/deposits/all`, { headers });
      setDeposits(res.data.deposits || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

  useEffect(() => { loadDeposits(); }, [loadDeposits]);

  // Search bookings for new deposit
  useEffect(() => {
    if (!bookingSearch || bookingSearch.length < 2) {
      setBookingResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      setSearchingBookings(true);
      try {
        const res = await axios.get(`/pms/bookings?search=${encodeURIComponent(bookingSearch)}&limit=10`, { headers });
        setBookingResults(res.data.bookings || []);
      } catch {
        setBookingResults([]);
      }
      setSearchingBookings(false);
    }, 300);
    return () => clearTimeout(timer);
  }, [bookingSearch]);

  const handleNewDeposit = async () => {
    if (!selectedBooking) {
      toast.error('Lütfen bir rezervasyon seçin');
      return;
    }
    const amount = parseFloat(newDepositData.amount);
    if (!amount || amount <= 0) {
      toast.error('Geçerli bir tutar girin');
      return;
    }

    setSavingDeposit(true);
    try {
      await axios.post(
        `/pms/reservations/${selectedBooking.id}/record-deposit`,
        { amount, method: newDepositData.method, reference: newDepositData.reference || null },
        { headers }
      );
      toast.success('Depozito kaydedildi');
      setShowNewDeposit(false);
      setNewDepositData({ booking_id: '', amount: '', method: 'cash', reference: '' });
      setSelectedBooking(null);
      setBookingSearch('');
      loadDeposits();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Depozito kaydedilemedi');
    }
    setSavingDeposit(false);
  };

  const handleRefund = async () => {
    if (!refundTarget) return;
    const amount = parseFloat(refundData.amount);
    if (!amount || amount <= 0) {
      toast.error('Geçerli bir iade tutarı girin');
      return;
    }
    if (amount > (refundTarget.amount - (refundTarget.refunded_amount || 0))) {
      toast.error('İade tutarı depozito bakiyesinden büyük olamaz');
      return;
    }

    setSavingRefund(true);
    try {
      await axios.post(
        `/pms/reservations/${refundTarget.booking_id}/refund-deposit`,
        {
          deposit_id: refundTarget.id,
          refund_amount: amount,
          refund_method: refundData.method,
          reason: refundData.reason || null,
        },
        { headers }
      );
      toast.success('Depozito iadesi başarılı');
      setShowRefund(false);
      setRefundTarget(null);
      setRefundData({ amount: '', method: 'cash', reason: '' });
      loadDeposits();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'İade işlemi başarısız');
    }
    setSavingRefund(false);
  };

  const handleGenerateInvoice = async (deposit) => {
    setInvoiceTarget(deposit);
    setShowInvoice(true);
    setGeneratingInvoice(true);
    try {
      const res = await axios.post(
        `/pms/reservations/${deposit.booking_id}/generate-invoice`,
        { selected_charge_ids: [], billing_name: deposit.guest_name || null },
        { headers }
      );
      setInvoiceHtml(res.data.invoice_html || res.data.html || '');
    } catch (e) {
      toast.error('Fatura oluşturulamadı');
      setInvoiceHtml('');
    }
    setGeneratingInvoice(false);
  };

  const printInvoice = () => {
    const win = window.open('', '_blank');
    if (win) {
      win.document.write(invoiceHtml);
      win.document.close();
      setTimeout(() => win.print(), 500);
    }
  };

  // Filtering
  const filtered = deposits.filter(d => {
    if (filterStatus !== 'all' && d.status !== filterStatus) return false;
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      return (d.guest_name || '').toLowerCase().includes(term) ||
        (d.room_number || '').toLowerCase().includes(term) ||
        (d.booking_id || '').toLowerCase().includes(term);
    }
    return true;
  });

  const totalActive = deposits.filter(d => d.status === 'received').reduce((s, d) => s + (d.amount || 0), 0);
  const totalRefunded = deposits.filter(d => d.status === 'refunded').reduce((s, d) => s + (d.amount || 0), 0);
  const totalPartial = deposits.filter(d => d.status === 'partially_refunded').reduce((s, d) => s + ((d.amount || 0) - (d.refunded_amount || 0)), 0);
  const totalAll = totalActive + totalPartial;

  return (
    <>
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-800" data-testid="deposit-page-title">Depozito & Folio Yönetimi</h1>
            <p className="text-sm text-gray-500 mt-1">Depozito kaydı, iade işlemi ve fatura oluşturma</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={loadDeposits} data-testid="refresh-deposits-btn">
              <RefreshCw className="w-4 h-4 mr-1.5" /> Yenile
            </Button>
            <Button
              className="bg-blue-600 hover:bg-blue-700 text-white"
              onClick={() => setShowNewDeposit(true)}
              data-testid="new-deposit-btn"
            >
              <Plus className="w-4 h-4 mr-1.5" /> Yeni Depozito
            </Button>
          </div>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-1">
              <ArrowDownCircle className="w-4 h-4 text-emerald-600" />
              <span className="text-xs text-emerald-600 font-medium uppercase">Aktif Depozitolar</span>
            </div>
            <div className="text-2xl font-bold text-emerald-800">{totalAll.toLocaleString('tr-TR')} TL</div>
            <div className="text-xs text-emerald-500 mt-1">{deposits.filter(d => d.status === 'received').length} kayıt</div>
          </div>
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-1">
              <ArrowUpCircle className="w-4 h-4 text-amber-600" />
              <span className="text-xs text-amber-600 font-medium uppercase">Iade Edilen</span>
            </div>
            <div className="text-2xl font-bold text-amber-800">{totalRefunded.toLocaleString('tr-TR')} TL</div>
            <div className="text-xs text-amber-500 mt-1">{deposits.filter(d => d.status === 'refunded').length} iade</div>
          </div>
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-1">
              <Receipt className="w-4 h-4 text-blue-600" />
              <span className="text-xs text-blue-600 font-medium uppercase">Toplam İşlem</span>
            </div>
            <div className="text-2xl font-bold text-blue-800">{deposits.length}</div>
            <div className="text-xs text-blue-500 mt-1">depozito kaydı</div>
          </div>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="relative flex-1 max-w-sm">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <Input
              placeholder="Misafir, oda no veya rezervasyon ara..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="pl-9 h-9"
              data-testid="deposit-search-input"
            />
          </div>
          <Select value={filterStatus} onValueChange={setFilterStatus}>
            <SelectTrigger className="w-[160px] h-9" data-testid="deposit-status-filter">
              <SelectValue placeholder="Durum" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tüm Durumlar</SelectItem>
              <SelectItem value="received">Aktif</SelectItem>
              <SelectItem value="partially_refunded">Kısmi İade</SelectItem>
              <SelectItem value="refunded">İade Edildi</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Deposits Table */}
        {loading ? (
          <div className="flex items-center justify-center py-16"><Loader2 className="w-8 h-8 animate-spin text-gray-400" /></div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <Shield className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p className="text-lg font-medium">
              {searchTerm || filterStatus !== 'all' ? 'Eşleşen depozito bulunamadı' : 'Henüz depozito yok'}
            </p>
          </div>
        ) : (
          <div className="border rounded-xl overflow-hidden bg-white" data-testid="deposits-table">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="text-left py-3 px-4 font-semibold text-xs text-gray-500 uppercase">Misafir</th>
                  <th className="text-left py-3 px-4 font-semibold text-xs text-gray-500 uppercase">Oda</th>
                  <th className="text-left py-3 px-4 font-semibold text-xs text-gray-500 uppercase">Yöntem</th>
                  <th className="text-right py-3 px-4 font-semibold text-xs text-gray-500 uppercase">Tutar</th>
                  <th className="text-left py-3 px-4 font-semibold text-xs text-gray-500 uppercase">Durum</th>
                  <th className="text-left py-3 px-4 font-semibold text-xs text-gray-500 uppercase">Tarih</th>
                  <th className="text-left py-3 px-4 font-semibold text-xs text-gray-500 uppercase">Kaydeden</th>
                  <th className="text-center py-3 px-4 font-semibold text-xs text-gray-500 uppercase">İşlemler</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((d, i) => (
                  <tr key={d.id || i} className="border-t hover:bg-gray-50" data-testid={`deposit-row-${d.id || i}`}>
                    <td className="py-3 px-4 font-medium text-gray-800">{d.guest_name || '-'}</td>
                    <td className="py-3 px-4">{d.room_number || '-'}</td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1.5">
                        <Banknote className="w-3.5 h-3.5 text-gray-400" />
                        {d.method === 'cash' ? 'Nakit' : d.method === 'card' ? 'Kart' : d.method === 'bank_transfer' ? 'Havale' : d.method || '-'}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-right font-bold text-gray-800">{(d.amount || 0).toLocaleString('tr-TR')} TL</td>
                    <td className="py-3 px-4">
                      <Badge className={`text-xs ${
                        d.status === 'refunded' ? 'bg-red-100 text-red-700' :
                        d.status === 'partially_refunded' ? 'bg-amber-100 text-amber-700' :
                        'bg-emerald-100 text-emerald-700'
                      }`}>
                        {d.status === 'refunded' ? 'İade Edildi' : d.status === 'partially_refunded' ? 'Kısmi İade' : 'Aktif'}
                      </Badge>
                    </td>
                    <td className="py-3 px-4 text-xs text-gray-500">{(d.created_at || '').toString().slice(0, 16).replace('T', ' ')}</td>
                    <td className="py-3 px-4 text-xs text-gray-500">{d.recorded_by || '-'}</td>
                    <td className="py-3 px-4">
                      <div className="flex items-center justify-center gap-1">
                        {d.status === 'received' && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 text-xs text-amber-600 hover:text-amber-700 hover:bg-amber-50"
                            onClick={() => {
                              setRefundTarget(d);
                              setRefundData({ amount: String(d.amount - (d.refunded_amount || 0)), method: 'cash', reason: '' });
                              setShowRefund(true);
                            }}
                            data-testid={`refund-btn-${d.id}`}
                          >
                            <RotateCcw className="w-3 h-3 mr-1" /> İade
                          </Button>
                        )}
                        {d.booking_id && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 text-xs text-blue-600 hover:text-blue-700 hover:bg-blue-50"
                            onClick={() => handleGenerateInvoice(d)}
                            data-testid={`invoice-btn-${d.id}`}
                          >
                            <FileText className="w-3 h-3 mr-1" /> Fatura
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* New Deposit Dialog */}
      <Dialog open={showNewDeposit} onOpenChange={setShowNewDeposit}>
        <DialogContent className="sm:max-w-md" data-testid="new-deposit-dialog">
          <DialogHeader>
            <DialogTitle>Yeni Depozito Kaydı</DialogTitle>
            <DialogDescription>Bir rezervasyon seçin ve depozito tutarını girin</DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {/* Booking Search */}
            {!selectedBooking ? (
              <div>
                <Label className="text-sm">Rezervasyon Ara</Label>
                <div className="relative mt-1">
                  <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                  <Input
                    placeholder="Misafir adı, oda no veya rezervasyon ID..."
                    value={bookingSearch}
                    onChange={e => setBookingSearch(e.target.value)}
                    className="pl-9"
                    data-testid="deposit-booking-search"
                  />
                  {searchingBookings && <Loader2 className="w-4 h-4 animate-spin absolute right-3 top-1/2 -translate-y-1/2 text-gray-400" />}
                </div>
                {bookingResults.length > 0 && (
                  <div className="mt-2 border rounded-lg max-h-[200px] overflow-y-auto" data-testid="booking-search-results">
                    {bookingResults.map(b => (
                      <button
                        key={b.id}
                        className="w-full text-left px-3 py-2 hover:bg-blue-50 border-b last:border-b-0 text-sm"
                        onClick={() => {
                          setSelectedBooking(b);
                          setBookingSearch('');
                          setBookingResults([]);
                        }}
                        data-testid={`booking-result-${b.id}`}
                      >
                        <div className="font-medium text-gray-800">{b.guest_name || 'Misafir'}</div>
                        <div className="text-xs text-gray-500">
                          Oda: {b.room_number || '-'} | {(b.check_in || '').toString().slice(0, 10)} - {(b.check_out || '').toString().slice(0, 10)}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 flex items-start justify-between" data-testid="selected-booking-card">
                <div>
                  <div className="font-medium text-blue-800">{selectedBooking.guest_name || 'Misafir'}</div>
                  <div className="text-xs text-blue-600">
                    Oda: {selectedBooking.room_number || '-'} | Tutar: {(selectedBooking.total_amount || 0).toLocaleString('tr-TR')} TL
                  </div>
                </div>
                <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => setSelectedBooking(null)}>
                  <X className="w-4 h-4" />
                </Button>
              </div>
            )}

            <div>
              <Label className="text-sm">Depozito Tutarı (TL)</Label>
              <Input
                type="number"
                step="0.01"
                min="0"
                placeholder="0.00"
                value={newDepositData.amount}
                onChange={e => setNewDepositData(prev => ({ ...prev, amount: e.target.value }))}
                className="mt-1"
                data-testid="deposit-amount-input"
              />
            </div>

            <div>
              <Label className="text-sm">Ödeme Yöntemi</Label>
              <Select value={newDepositData.method} onValueChange={v => setNewDepositData(prev => ({ ...prev, method: v }))}>
                <SelectTrigger className="mt-1" data-testid="deposit-method-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="cash">Nakit</SelectItem>
                  <SelectItem value="card">Kredi Kartı</SelectItem>
                  <SelectItem value="bank_transfer">Banka Havalesi</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label className="text-sm">Referans (Opsiyonel)</Label>
              <Input
                placeholder="Dekont no, işlem referansı..."
                value={newDepositData.reference}
                onChange={e => setNewDepositData(prev => ({ ...prev, reference: e.target.value }))}
                className="mt-1"
                data-testid="deposit-reference-input"
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowNewDeposit(false)}>İptal</Button>
            <Button
              className="bg-blue-600 hover:bg-blue-700 text-white"
              onClick={handleNewDeposit}
              disabled={savingDeposit || !selectedBooking}
              data-testid="save-deposit-btn"
            >
              {savingDeposit ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <Plus className="w-4 h-4 mr-1.5" />}
              Depozito Kaydet
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Refund Dialog */}
      <Dialog open={showRefund} onOpenChange={setShowRefund}>
        <DialogContent className="sm:max-w-md" data-testid="refund-dialog">
          <DialogHeader>
            <DialogTitle>Depozito İadesi</DialogTitle>
            <DialogDescription>
              {refundTarget && `${refundTarget.guest_name || 'Misafir'} - ${(refundTarget.amount || 0).toLocaleString('tr-TR')} TL depozito`}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div>
              <Label className="text-sm">Iade Tutari (TL)</Label>
              <Input
                type="number"
                step="0.01"
                min="0"
                max={refundTarget ? refundTarget.amount - (refundTarget.refunded_amount || 0) : 0}
                value={refundData.amount}
                onChange={e => setRefundData(prev => ({ ...prev, amount: e.target.value }))}
                className="mt-1"
                data-testid="refund-amount-input"
              />
              {refundTarget && (
                <p className="text-xs text-gray-500 mt-1">
                  Maks: {((refundTarget.amount || 0) - (refundTarget.refunded_amount || 0)).toLocaleString('tr-TR')} TL
                </p>
              )}
            </div>

            <div>
              <Label className="text-sm">İade Yöntemi</Label>
              <Select value={refundData.method} onValueChange={v => setRefundData(prev => ({ ...prev, method: v }))}>
                <SelectTrigger className="mt-1" data-testid="refund-method-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="cash">Nakit</SelectItem>
                  <SelectItem value="card">Kredi Kartı</SelectItem>
                  <SelectItem value="bank_transfer">Banka Havalesi</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label className="text-sm">İade Nedeni (Opsiyonel)</Label>
              <Input
                placeholder="İade nedeni..."
                value={refundData.reason}
                onChange={e => setRefundData(prev => ({ ...prev, reason: e.target.value }))}
                className="mt-1"
                data-testid="refund-reason-input"
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowRefund(false)}>İptal</Button>
            <Button
              className="bg-amber-600 hover:bg-amber-700 text-white"
              onClick={handleRefund}
              disabled={savingRefund}
              data-testid="confirm-refund-btn"
            >
              {savingRefund ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <RotateCcw className="w-4 h-4 mr-1.5" />}
              İade Onayla
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Invoice Dialog */}
      <Dialog open={showInvoice} onOpenChange={setShowInvoice}>
        <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="invoice-dialog">
          <DialogHeader>
            <DialogTitle>Fatura Önizleme</DialogTitle>
            <DialogDescription>
              {invoiceTarget && `${invoiceTarget.guest_name || 'Misafir'} - Rezervasyon Faturası`}
            </DialogDescription>
          </DialogHeader>

          {generatingInvoice ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
              <span className="ml-3 text-gray-500">Fatura oluşturuluyor...</span>
            </div>
          ) : invoiceHtml ? (
            <div
              className="border rounded-lg overflow-hidden"
              dangerouslySetInnerHTML={{ __html: invoiceHtml }}
              data-testid="invoice-preview"
            />
          ) : (
            <div className="text-center py-8 text-gray-400">
              Fatura oluşturulamadı
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowInvoice(false)}>Kapat</Button>
            {invoiceHtml && (
              <Button
                className="bg-blue-600 hover:bg-blue-700 text-white"
                onClick={printInvoice}
                data-testid="print-invoice-btn"
              >
                <FileText className="w-4 h-4 mr-1.5" /> Yazdır
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
