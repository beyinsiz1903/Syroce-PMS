import { useState, useMemo } from 'react';
import { toast } from 'sonner';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Plus, ClipboardList, DollarSign, RotateCcw, FileText, ArrowLeftRight, Printer, Send, Loader2, KeyRound, RefreshCw } from 'lucide-react';

const VAT_OPTIONS = [
  { value: '0', label: '%0' },
  { value: '1', label: '%1' },
  { value: '8', label: '%8' },
  { value: '10', label: '%10 (Konaklama/F&B)' },
  { value: '18', label: '%18' },
  { value: '20', label: '%20' },
];

const fmt = (n) => (Number(n || 0)).toFixed(2);

const FolioViewDialog = ({
  open,
  onClose,
  selectedFolio,
  folios = [],
  folioCharges,
  folioPayments,
  guests,
  bookings,
  onChargePosted,
  onPaymentPosted,
  onPickFolio,
}) => {
  const { t } = useTranslation();
  const [subDialog, setSubDialog] = useState(null);
  const [expandedChargeItems, setExpandedChargeItems] = useState({});
  const [voidTarget, setVoidTarget] = useState(null);
  const [voidReason, setVoidReason] = useState('');
  const [voidLoading, setVoidLoading] = useState(false);
  const [pinGate, setPinGate] = useState({ open: false, label: '', onVerified: null });
  const [pinValue, setPinValue] = useState('');
  const [pinSubmitting, setPinSubmitting] = useState(false);
  const [proforma, setProforma] = useState(null);
  const [proformaLoading, setProformaLoading] = useState(false);
  const [operations, setOperations] = useState(null);
  const [opsLoading, setOpsLoading] = useState(false);
  const [openFolios, setOpenFolios] = useState([]);
  const [transferTargetId, setTransferTargetId] = useState('');
  const [transferChargeIds, setTransferChargeIds] = useState([]);
  const [transferReason, setTransferReason] = useState('');
  const [transferLoading, setTransferLoading] = useState(false);

  const [newFolioCharge, setNewFolioCharge] = useState({
    charge_category: 'room',
    description: '',
    amount: 0,
    quantity: 1,
    auto_calculate_tax: false,
    vat_rate: '0',
    discount_amount: 0,
    discount_reason: '',
  });

  const [newFolioPayment, setNewFolioPayment] = useState({
    amount: 0,
    method: 'card',
    payment_type: 'interim',
    reference: '',
    notes: '',
  });

  const chargePreview = useMemo(() => {
    const sub = (parseFloat(newFolioCharge.amount) || 0) * (parseFloat(newFolioCharge.quantity) || 0);
    const disc = Math.max(0, Math.min(sub, parseFloat(newFolioCharge.discount_amount) || 0));
    const net = sub - disc;
    const rate = parseFloat(newFolioCharge.vat_rate) || 0;
    const vat = (net * rate) / 100;
    const total = net + vat;
    return { sub, disc, net, rate, vat, total };
  }, [newFolioCharge.amount, newFolioCharge.quantity, newFolioCharge.discount_amount, newFolioCharge.vat_rate]);

  const handlePostCharge = async (e) => {
    e.preventDefault();
    if (!selectedFolio) return;
    if (chargePreview.disc > 0 && !newFolioCharge.discount_reason.trim()) {
      toast.error('İndirim için neden zorunlu');
      return;
    }
    try {
      await axios.post(`/folio/${selectedFolio.id}/charge`, {
        charge_category: newFolioCharge.charge_category,
        description: newFolioCharge.description,
        amount: parseFloat(newFolioCharge.amount) || 0,
        quantity: parseFloat(newFolioCharge.quantity) || 1,
        auto_calculate_tax: !!newFolioCharge.auto_calculate_tax,
        vat_rate: parseFloat(newFolioCharge.vat_rate) || 0,
        discount_amount: parseFloat(newFolioCharge.discount_amount) || 0,
        discount_reason: newFolioCharge.discount_reason.trim() || null,
      });
      toast.success('İşlem eklendi');
      onChargePosted(selectedFolio.id);
      setNewFolioCharge({
        charge_category: 'room', description: '', amount: 0, quantity: 1,
        auto_calculate_tax: false, vat_rate: '0', discount_amount: 0, discount_reason: '',
      });
      setSubDialog(null);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'İşlem eklenemedi');
    }
  };

  const handlePostPayment = async (e) => {
    e.preventDefault();
    if (!selectedFolio) return;
    try {
      await axios.post(`/folio/${selectedFolio.id}/payment`, newFolioPayment);
      toast.success('Ödeme alındı');
      onPaymentPosted(selectedFolio.id);
      setNewFolioPayment({ amount: 0, method: 'card', payment_type: 'interim', reference: '', notes: '' });
      setSubDialog(null);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Ödeme eklenemedi');
    }
  };

  const requirePin = (label, onVerified) => {
    setPinValue('');
    setPinGate({ open: true, label, onVerified });
  };
  const closePinGate = () => {
    setPinGate({ open: false, label: '', onVerified: null });
    setPinValue('');
    setPinSubmitting(false);
  };
  const verifyPin = async () => {
    const pin = pinValue.trim();
    if (!pin) { toast.error('PIN gerekli'); return; }
    setPinSubmitting(true);
    try {
      await axios.post('/cashier/peer-verify', { pin });
      const cb = pinGate.onVerified;
      closePinGate();
      if (cb) await cb();
    } catch (e) {
      if (e?.response?.status === 429) {
        const retry =
          e.response.headers?.['retry-after'] ??
          e.response.data?.retry_after ??
          null;
        const detail = e.response?.data?.detail || 'Çok fazla PIN denemesi, lütfen bekleyin';
        toast.error(retry ? `${detail} (${retry}s)` : detail);
      } else if (e?.response?.status === 401) {
        toast.error(e.response?.data?.detail || 'PIN hatalı');
      } else {
        toast.error('PIN doğrulanamadı: ' + (e.response?.data?.detail || e.message));
      }
      setPinSubmitting(false);
    }
  };

  const doVoidPayment = async () => {
    if (!selectedFolio || !voidTarget) return;
    setVoidLoading(true);
    try {
      await axios.post(
        `/folio/${selectedFolio.id}/payment/${voidTarget.id}/void`,
        { reason: voidReason.trim() }
      );
      toast.success('Ödeme iade edildi');
      onPaymentPosted(selectedFolio.id);
      setVoidTarget(null);
      setVoidReason('');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'İade başarısız');
    }
    setVoidLoading(false);
  };
  const handleVoidPayment = () => {
    if (!selectedFolio || !voidTarget) return;
    if (!voidReason.trim()) { toast.error('İade nedeni zorunlu'); return; }
    requirePin('Ödeme iadesi öncesi PIN doğrulayın', doVoidPayment);
  };

  const loadProforma = async () => {
    if (!selectedFolio) return;
    setProformaLoading(true);
    try {
      const res = await axios.post(`/folio/${selectedFolio.id}/proforma`);
      setProforma(res.data);
      setSubDialog('proforma');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Proforma alınamadı');
    }
    setProformaLoading(false);
  };

  const loadOperations = async () => {
    if (!selectedFolio) return;
    setOpsLoading(true);
    try {
      const res = await axios.get(`/folio/${selectedFolio.id}/operations`);
      setOperations(res.data);
      setSubDialog('operations');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Geçmiş alınamadı');
    }
    setOpsLoading(false);
  };

  const openTransferDialog = async () => {
    if (!selectedFolio) return;
    setTransferTargetId('');
    setTransferChargeIds([]);
    setTransferReason('');
    try {
      const res = await axios.get('/folio/list', { params: { status: 'open' } });
      const list = (res.data?.folios || res.data || []).filter(f => f.id !== selectedFolio.id);
      setOpenFolios(list);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Açık folio listesi alınamadı');
      setOpenFolios([]);
    }
    setSubDialog('transfer');
  };

  const toggleTransferCharge = (id) => {
    setTransferChargeIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const handleTransferSubmit = async () => {
    if (!selectedFolio) return;
    if (!transferTargetId) { toast.error('Hedef folio seçin'); return; }
    if (transferChargeIds.length === 0) { toast.error('En az bir işlem seçin'); return; }
    if (!transferReason.trim()) { toast.error('Aktarım nedeni zorunlu'); return; }
    setTransferLoading(true);
    try {
      await axios.post('/folio/transfer', {
        operation_type: 'transfer',
        from_folio_id: selectedFolio.id,
        to_folio_id: transferTargetId,
        charge_ids: transferChargeIds,
        reason: transferReason.trim(),
      });
      toast.success('İşlemler aktarıldı');
      setSubDialog(null);
      onChargePosted(selectedFolio.id);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Aktarım başarısız');
    }
    setTransferLoading(false);
  };

  const printProforma = () => {
    const node = document.getElementById('proforma-printable');
    if (!node) return;
    const win = window.open('', '_blank', 'width=900,height=700');
    if (!win) return;
    win.document.write(`<html><head><title>Proforma ${proforma?.folio?.folio_number || ''}</title>
<style>
body{font-family:system-ui,sans-serif;padding:24px;color:#111}
h1,h2,h3{margin:8px 0}
table{width:100%;border-collapse:collapse;margin:10px 0}
th,td{border:1px solid #ddd;padding:6px 8px;font-size:12px;text-align:left}
th{background:#f5f5f5}
.right{text-align:right}
.muted{color:#666;font-size:11px}
.totals td{font-weight:600}
</style></head><body>${node.innerHTML}</body></html>`);
    win.document.close();
    win.focus();
    setTimeout(() => { win.print(); win.close(); }, 300);
  };

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
        <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('pms.folioManagement', 'Folio Yönetimi')}</DialogTitle>
            <DialogDescription>
              {selectedFolio && `Folio ${selectedFolio.folio_number} - ${selectedFolio.folio_type?.toUpperCase?.()}`}
            </DialogDescription>
          </DialogHeader>

          {!selectedFolio && folios.length === 0 && (
            <div className="py-12 text-center" data-testid="folio-loading">
              <Loader2 className="w-8 h-8 mx-auto animate-spin text-indigo-500 mb-3" />
              <p className="text-sm text-gray-600">Folyo yükleniyor…</p>
              <p className="text-xs text-gray-400 mt-1">
                Birkaç saniye sürebilir. Yanıt gelmezse sayfayı yenileyin.
              </p>
            </div>
          )}

          {!selectedFolio && folios.length > 0 && (
            <div className="py-8 space-y-3" data-testid="folio-picker">
              <p className="text-sm text-gray-600 text-center">
                Bu rezervasyonda birden fazla folyo var — açmak istediğinizi seçin:
              </p>
              <div className="grid gap-2 max-w-md mx-auto">
                {folios.map((f) => (
                  <Button
                    key={f.id}
                    variant="outline"
                    onClick={() => onPickFolio?.(f.id)}
                    className="justify-between h-auto py-2.5"
                  >
                    <span className="font-medium">
                      {f.folio_number || f.id?.slice(0, 8)} · {f.folio_type?.toUpperCase?.()}
                    </span>
                    <span className="text-xs text-gray-500">
                      Bakiye: {fmt(f.balance)} ₺
                    </span>
                  </Button>
                ))}
              </div>
            </div>
          )}

          {selectedFolio && (
            <div className="space-y-6">
              <div className="bg-gradient-to-r from-blue-50 to-indigo-50 p-6 rounded-lg border">
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <div className="text-sm text-gray-600">{t('pms.guest', 'Misafir')}</div>
                    <div className="font-semibold">
                      {guests.find(g => g.id === selectedFolio.guest_id)?.name || '—'}
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600">{t('pms.reservation', 'Rezervasyon')}</div>
                    <div className="font-semibold">
                      {(() => {
                        const booking = bookings.find(b => b.id === selectedFolio.booking_id);
                        if (!booking) return '—';
                        return `${new Date(booking.check_in).toLocaleDateString()} - ${new Date(booking.check_out).toLocaleDateString()}`;
                      })()}
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600">{t('pms.currentBalance', 'Bakiye')}</div>
                    <div className={`text-2xl font-bold ${selectedFolio.balance > 0 ? 'text-red-600' : selectedFolio.balance < 0 ? 'text-green-600' : 'text-gray-600'}`}>
                      {fmt(selectedFolio.balance)} ₺
                    </div>
                    <div className="text-xs text-gray-500">
                      {selectedFolio.balance > 0 ? 'Misafir borçlu' : selectedFolio.balance < 0 ? 'Otel borçlu' : 'Dengeli'}
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex gap-2 flex-wrap">
                <Button onClick={() => setSubDialog('post-charge')} variant="default">
                  <Plus className="w-4 h-4 mr-2" /> İşlem Ekle
                </Button>
                <Button onClick={() => setSubDialog('post-payment')} variant="default">
                  <Plus className="w-4 h-4 mr-2" /> Ödeme Ekle
                </Button>
                <Button onClick={loadProforma} variant="outline" disabled={proformaLoading}>
                  <FileText className="w-4 h-4 mr-2" /> {proformaLoading ? 'Hazırlanıyor…' : 'Proforma Fatura'}
                </Button>
                <Button onClick={loadOperations} variant="outline" disabled={opsLoading}>
                  <ArrowLeftRight className="w-4 h-4 mr-2" /> {opsLoading ? 'Yükleniyor…' : 'Transfer Geçmişi'}
                </Button>
                <Button onClick={openTransferDialog} variant="outline">
                  <Send className="w-4 h-4 mr-2" /> İşlem Aktar
                </Button>
              </div>

              <div className="grid grid-cols-2 gap-6">
                <div>
                  <h3 className="text-lg font-semibold mb-3 flex items-center">
                    <ClipboardList className="w-5 h-5 mr-2" /> İşlemler
                  </h3>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {folioCharges.length === 0 ? (
                      <div className="text-center text-gray-400 py-8">Henüz işlem yok</div>
                    ) :
                      folioCharges.map((charge) => {
                        const isPOSCharge = ['restaurant', 'food', 'bar', 'beverage', 'room_service'].includes(charge.charge_category);
                        const hasLineItems = charge.line_items && charge.line_items.length > 0;
                        const isExpanded = expandedChargeItems[charge.id];
                        const hasDiscount = (charge.discount_amount || 0) > 0;
                        const hasVat = (charge.vat_amount || 0) > 0;
                        const hasCity = (charge.tax_amount || 0) > 0;

                        return (
                          <Card key={charge.id} className={charge.voided ? 'opacity-50 bg-gray-50' : ''}>
                            <CardContent className="p-4">
                              <div
                                className={`flex justify-between items-start ${isPOSCharge && hasLineItems ? 'cursor-pointer hover:bg-gray-50' : ''}`}
                                onClick={() => {
                                  if (isPOSCharge && hasLineItems) {
                                    setExpandedChargeItems(prev => ({ ...prev, [charge.id]: !prev[charge.id] }));
                                  }
                                }}
                              >
                                <div className="flex-1">
                                  <div className="flex items-center gap-2">
                                    <div className="font-semibold">{charge.description}</div>
                                    {charge.voided && (
                                      <span className="text-xs bg-red-100 text-red-700 px-1.5 py-0.5 rounded">İPTAL</span>
                                    )}
                                  </div>
                                  <div className="text-xs text-gray-500 capitalize">{charge.charge_category}</div>
                                  <div className="text-xs text-gray-400">
                                    {new Date(charge.created_at || charge.date).toLocaleString()}
                                  </div>
                                  {hasDiscount && (
                                    <div className="text-xs text-amber-700 mt-1">
                                      İndirim: −{fmt(charge.discount_amount)} ₺
                                      {charge.discount_reason ? ` (${charge.discount_reason})` : ''}
                                    </div>
                                  )}
                                </div>
                                <div className="text-right">
                                  <div className="font-bold">{fmt(charge.total ?? charge.total_amount ?? charge.amount)} ₺</div>
                                  {(hasVat || hasCity) && (
                                    <div className="text-[11px] text-gray-500 leading-tight mt-0.5">
                                      {hasDiscount && <div>Net: {fmt(charge.amount)} ₺</div>}
                                      {hasVat && <div>KDV %{charge.vat_rate}: {fmt(charge.vat_amount)} ₺</div>}
                                      {hasCity && <div>Şehir vergisi: {fmt(charge.tax_amount)} ₺</div>}
                                    </div>
                                  )}
                                </div>
                              </div>
                              {isExpanded && hasLineItems && (
                                <div className="mt-3 pt-3 border-t space-y-1">
                                  {charge.line_items.map((li, i) => (
                                    <div key={i} className="flex justify-between text-xs text-gray-600">
                                      <span>{li.name || li.description} x{li.quantity}</span>
                                      <span>{fmt(li.total ?? li.amount)} ₺</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </CardContent>
                          </Card>
                        );
                      })
                    }
                  </div>
                </div>

                <div>
                  <h3 className="text-lg font-semibold mb-3 flex items-center">
                    <DollarSign className="w-5 h-5 mr-2" /> Ödemeler
                  </h3>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {folioPayments.length === 0 ? (
                      <div className="text-center text-gray-400 py-8">Henüz ödeme yok</div>
                    ) :
                      folioPayments.map((payment) => (
                        <Card key={payment.id} className={payment.voided ? 'opacity-60 bg-red-50/30' : ''}>
                          <CardContent className="p-4">
                            <div className="flex justify-between items-start">
                              <div className="flex-1">
                                <div className="flex items-center gap-2">
                                  <span className="font-semibold capitalize">{payment.method}</span>
                                  {payment.voided && (
                                    <span className="px-1.5 py-0.5 bg-red-100 text-red-700 rounded text-[10px] font-medium">İADE</span>
                                  )}
                                </div>
                                <div className="text-xs text-gray-500 capitalize">{payment.payment_type}</div>
                                {payment.reference && <div className="text-xs text-gray-400">Ref: {payment.reference}</div>}
                                <div className="text-xs text-gray-400">
                                  {new Date(payment.created_at || payment.processed_at).toLocaleString()}
                                </div>
                                {payment.voided && payment.void_reason && (
                                  <div className="text-xs text-red-600 mt-1">İade nedeni: {payment.void_reason}</div>
                                )}
                              </div>
                              <div className="text-right">
                                <div className={`font-bold ${payment.voided ? 'text-gray-400 line-through' : 'text-green-600'}`}>
                                  {fmt(payment.amount)} ₺
                                </div>
                                {!payment.voided && (
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    className="mt-1 h-7 text-red-600 hover:text-red-700 hover:bg-red-50"
                                    onClick={() => { setVoidTarget(payment); setVoidReason(''); }}
                                  >
                                    <RotateCcw className="w-3 h-3 mr-1" /> İade
                                  </Button>
                                )}
                              </div>
                            </div>
                          </CardContent>
                        </Card>
                      ))
                    }
                  </div>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={subDialog === 'post-charge'} onOpenChange={(o) => !o && setSubDialog(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>İşlem Ekle</DialogTitle>
          </DialogHeader>
          <form onSubmit={handlePostCharge} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Kategori</Label>
                <Select value={newFolioCharge.charge_category} onValueChange={(v) => setNewFolioCharge({ ...newFolioCharge, charge_category: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="room">Konaklama</SelectItem>
                    <SelectItem value="food">Yiyecek</SelectItem>
                    <SelectItem value="beverage">İçecek</SelectItem>
                    <SelectItem value="minibar">Minibar</SelectItem>
                    <SelectItem value="laundry">Çamaşır</SelectItem>
                    <SelectItem value="spa">Spa</SelectItem>
                    <SelectItem value="phone">Telefon</SelectItem>
                    <SelectItem value="internet">İnternet</SelectItem>
                    <SelectItem value="parking">Otopark</SelectItem>
                    <SelectItem value="service_charge">Servis Bedeli</SelectItem>
                    <SelectItem value="other">Diğer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>KDV Oranı</Label>
                <Select value={newFolioCharge.vat_rate} onValueChange={(v) => setNewFolioCharge({ ...newFolioCharge, vat_rate: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {VAT_OPTIONS.map(o => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label>Açıklama</Label>
              <Input value={newFolioCharge.description} onChange={(e) => setNewFolioCharge({ ...newFolioCharge, description: e.target.value })} required />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Birim Fiyat (₺)</Label>
                <Input type="number" step="0.01" min="0" value={newFolioCharge.amount}
                  onChange={(e) => setNewFolioCharge({ ...newFolioCharge, amount: e.target.value })} required />
              </div>
              <div>
                <Label>Adet</Label>
                <Input type="number" step="1" min="1" value={newFolioCharge.quantity}
                  onChange={(e) => setNewFolioCharge({ ...newFolioCharge, quantity: e.target.value })} required />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>İndirim (₺)</Label>
                <Input type="number" step="0.01" min="0" value={newFolioCharge.discount_amount}
                  onChange={(e) => setNewFolioCharge({ ...newFolioCharge, discount_amount: e.target.value })} />
              </div>
              <div>
                <Label>İndirim Nedeni {chargePreview.disc > 0 && <span className="text-red-600">*</span>}</Label>
                <Input value={newFolioCharge.discount_reason}
                  onChange={(e) => setNewFolioCharge({ ...newFolioCharge, discount_reason: e.target.value })}
                  placeholder="Ör: Sadakat indirimi" />
              </div>
            </div>

            <div className="bg-gray-50 rounded p-3 text-sm space-y-1">
              <div className="flex justify-between"><span>Ara Toplam</span><span>{fmt(chargePreview.sub)} ₺</span></div>
              {chargePreview.disc > 0 && (
                <div className="flex justify-between text-amber-700"><span>İndirim</span><span>−{fmt(chargePreview.disc)} ₺</span></div>
              )}
              <div className="flex justify-between"><span>Net</span><span>{fmt(chargePreview.net)} ₺</span></div>
              {chargePreview.rate > 0 && (
                <div className="flex justify-between text-gray-600"><span>KDV %{chargePreview.rate}</span><span>{fmt(chargePreview.vat)} ₺</span></div>
              )}
              <div className="flex justify-between font-bold pt-1 border-t"><span>Toplam</span><span>{fmt(chargePreview.total)} ₺</span></div>
              <div className="text-[11px] text-gray-500">Şehir vergisi (varsa) sunucuda otomatik eklenir.</div>
            </div>

            <Button type="submit" className="w-full">Kaydet</Button>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={subDialog === 'post-payment'} onOpenChange={(o) => !o && setSubDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ödeme Ekle</DialogTitle>
          </DialogHeader>
          <form onSubmit={handlePostPayment} className="space-y-4">
            <div>
              <Label>Tutar (₺)</Label>
              <Input type="number" step="0.01" value={newFolioPayment.amount} onChange={(e) => setNewFolioPayment({ ...newFolioPayment, amount: parseFloat(e.target.value) })} required />
            </div>
            <div>
              <Label>Ödeme Yöntemi</Label>
              <Select value={newFolioPayment.method} onValueChange={(v) => setNewFolioPayment({ ...newFolioPayment, method: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="cash">Nakit</SelectItem>
                  <SelectItem value="card">Kredi Kartı</SelectItem>
                  <SelectItem value="bank_transfer">Banka Havalesi</SelectItem>
                  <SelectItem value="online">Online</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Ödeme Tipi</Label>
              <Select value={newFolioPayment.payment_type} onValueChange={(v) => setNewFolioPayment({ ...newFolioPayment, payment_type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="interim">Ara</SelectItem>
                  <SelectItem value="final">Son</SelectItem>
                  <SelectItem value="deposit">Depozito</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Referans</Label>
              <Input value={newFolioPayment.reference} onChange={(e) => setNewFolioPayment({ ...newFolioPayment, reference: e.target.value })} />
            </div>
            <Button type="submit" className="w-full">Kaydet</Button>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={!!voidTarget} onOpenChange={(o) => { if (!o) { setVoidTarget(null); setVoidReason(''); } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ödeme İadesi</DialogTitle>
            <DialogDescription>
              {voidTarget && (
                <>
                  {voidTarget.method?.toUpperCase()} ödemesi {fmt(voidTarget.amount)} ₺ iade edilecek.
                  {voidTarget.method === 'cash' && ' Nakit iadesi için açık bir vardiya gerekir.'}
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>İade Nedeni *</Label>
              <Textarea
                value={voidReason}
                onChange={(e) => setVoidReason(e.target.value)}
                placeholder="Ör: yanlış tutar, müşteri talebi"
                rows={3}
              />
            </div>
            <div className="flex gap-2 justify-end">
              <Button type="button" variant="outline" onClick={() => { setVoidTarget(null); setVoidReason(''); }}>
                Vazgeç
              </Button>
              <Button
                type="button"
                onClick={handleVoidPayment}
                disabled={voidLoading || !voidReason.trim()}
                className="bg-red-600 hover:bg-red-700"
              >
                {voidLoading ? 'İşleniyor...' : 'İadeyi Onayla'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={subDialog === 'proforma'} onOpenChange={(o) => !o && setSubDialog(null)}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center justify-between">
              <span>Proforma Fatura</span>
              <Button type="button" size="sm" variant="outline" onClick={printProforma}>
                <Printer className="w-4 h-4 mr-1" /> Yazdır
              </Button>
            </DialogTitle>
            <DialogDescription>Taslak — yasal fatura yerine geçmez.</DialogDescription>
          </DialogHeader>
          {proforma && (
            <div id="proforma-printable" className="space-y-4 text-sm">
              <div className="flex justify-between border-b pb-3">
                <div>
                  <div className="font-bold text-base">{proforma.hotel?.name || '—'}</div>
                  <div className="muted text-xs text-gray-600">{proforma.hotel?.address || ''}</div>
                  {proforma.hotel?.tax_no && <div className="text-xs text-gray-600">VKN: {proforma.hotel.tax_no} {proforma.hotel?.tax_office ? `(${proforma.hotel.tax_office})` : ''}</div>}
                </div>
                <div className="text-right">
                  <div className="font-semibold">PROFORMA</div>
                  <div className="text-xs text-gray-600">No: {proforma.folio?.folio_number}</div>
                  <div className="text-xs text-gray-600">{new Date(proforma.generated_at).toLocaleString()}</div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="font-semibold">Misafir</div>
                  <div>{proforma.guest?.name || '—'}</div>
                  {proforma.guest?.email && <div className="text-xs text-gray-600">{proforma.guest.email}</div>}
                  {proforma.guest?.phone && <div className="text-xs text-gray-600">{proforma.guest.phone}</div>}
                  {proforma.guest?.tc_no && <div className="text-xs text-gray-600">TC: {proforma.guest.tc_no}</div>}
                </div>
                <div>
                  <div className="font-semibold">Konaklama</div>
                  {proforma.booking?.room_number && <div>Oda: {proforma.booking.room_number}</div>}
                  {proforma.booking?.check_in && (
                    <div className="text-xs text-gray-600">
                      {new Date(proforma.booking.check_in).toLocaleDateString()} → {proforma.booking?.check_out ? new Date(proforma.booking.check_out).toLocaleDateString() : ''}
                    </div>
                  )}
                  {(proforma.booking?.adults != null) && (
                    <div className="text-xs text-gray-600">{proforma.booking.adults} yetişkin {proforma.booking.children ? `+ ${proforma.booking.children} çocuk` : ''}</div>
                  )}
                </div>
              </div>

              <div>
                <div className="font-semibold mb-1">İşlemler</div>
                <table>
                  <thead>
                    <tr>
                      <th>Tarih</th>
                      <th>Açıklama</th>
                      <th className="right">Birim</th>
                      <th className="right">Adet</th>
                      <th className="right">Ara Toplam</th>
                      <th className="right">İnd.</th>
                      <th className="right">Net</th>
                      <th className="right">KDV</th>
                      <th className="right">Toplam</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(proforma.charges || []).map((c) => (
                      <tr key={c.id}>
                        <td>{new Date(c.date || c.created_at).toLocaleDateString()}</td>
                        <td>{c.description}{c.discount_reason ? ` (${c.discount_reason})` : ''}</td>
                        <td className="right">{fmt(c.unit_price)}</td>
                        <td className="right">{c.quantity}</td>
                        <td className="right">{fmt(c.subtotal ?? c.amount)}</td>
                        <td className="right">{fmt(c.discount_amount)}</td>
                        <td className="right">{fmt(c.amount)}</td>
                        <td className="right">{fmt(c.vat_amount)} {c.vat_rate ? `(%${c.vat_rate})` : ''}</td>
                        <td className="right">{fmt(c.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="font-semibold mb-1">KDV Özeti</div>
                  <table>
                    <thead>
                      <tr><th>Oran</th><th className="right">Net</th><th className="right">KDV</th></tr>
                    </thead>
                    <tbody>
                      {(proforma.vat_breakdown || []).map((g) => (
                        <tr key={g.vat_rate}>
                          <td>%{g.vat_rate}</td>
                          <td className="right">{fmt(g.net)}</td>
                          <td className="right">{fmt(g.vat_amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div>
                  <div className="font-semibold mb-1">Toplamlar</div>
                  <table className="totals">
                    <tbody>
                      <tr><td>Ara Toplam</td><td className="right">{fmt(proforma.totals?.subtotal)} ₺</td></tr>
                      <tr><td>İndirim</td><td className="right">−{fmt(proforma.totals?.discount_total)} ₺</td></tr>
                      <tr><td>Net</td><td className="right">{fmt(proforma.totals?.net_total)} ₺</td></tr>
                      <tr><td>KDV</td><td className="right">{fmt(proforma.totals?.vat_total)} ₺</td></tr>
                      <tr><td>Şehir Vergisi</td><td className="right">{fmt(proforma.totals?.city_tax_total)} ₺</td></tr>
                      <tr><td>Genel Toplam</td><td className="right">{fmt(proforma.totals?.grand_total)} ₺</td></tr>
                      <tr><td>Ödenen</td><td className="right">{fmt(proforma.totals?.payments_total)} ₺</td></tr>
                      <tr><td>Bakiye</td><td className="right">{fmt(proforma.totals?.balance_due)} ₺</td></tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="text-[11px] text-gray-500 border-t pt-2">
                Bu belge taslak proformadır; resmi fatura yerine geçmez.
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={subDialog === 'transfer'} onOpenChange={(o) => !o && setSubDialog(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>İşlem Aktar</DialogTitle>
            <DialogDescription>
              Bu folio'daki seçili işlemleri başka bir açık folio'ya taşır. Bakiyeler her iki tarafta yeniden hesaplanır.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Hedef Folio *</Label>
              <Select value={transferTargetId} onValueChange={setTransferTargetId}>
                <SelectTrigger><SelectValue placeholder="Açık folio seçin" /></SelectTrigger>
                <SelectContent>
                  {openFolios.length === 0 ? (
                    <SelectItem value="__none__" disabled>Aktarılabilir açık folio yok</SelectItem>
                  ) : openFolios.map(f => (
                    <SelectItem key={f.id} value={f.id}>
                      {f.folio_number} • {f.folio_type?.toUpperCase?.() || ''} • Bakiye: {fmt(f.balance)} ₺
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Aktarılacak İşlemler ({transferChargeIds.length} seçili)</Label>
              <div className="border rounded max-h-72 overflow-y-auto divide-y">
                {folioCharges.filter(c => !c.voided).length === 0 ? (
                  <div className="p-4 text-center text-sm text-gray-400">Aktarılabilir işlem yok</div>
                ) : folioCharges.filter(c => !c.voided).map(c => (
                  <label key={c.id} className="flex items-center gap-2 p-2 hover:bg-gray-50 cursor-pointer text-sm">
                    <input
                      type="checkbox"
                      checked={transferChargeIds.includes(c.id)}
                      onChange={() => toggleTransferCharge(c.id)}
                    />
                    <div className="flex-1">
                      <div className="font-medium">{c.description}</div>
                      <div className="text-xs text-gray-500 capitalize">{c.charge_category}</div>
                    </div>
                    <div className="text-right">
                      <div className="font-semibold">{fmt(c.total ?? c.amount)} ₺</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>
            <div>
              <Label>Aktarım Nedeni *</Label>
              <Textarea
                value={transferReason}
                onChange={(e) => setTransferReason(e.target.value)}
                placeholder="Ör: misafir oda değişikliği, şirket folio'suna devir"
                rows={2}
              />
            </div>
            <div className="flex gap-2 justify-end">
              <Button type="button" variant="outline" onClick={() => setSubDialog(null)}>Vazgeç</Button>
              <Button
                type="button"
                onClick={handleTransferSubmit}
                disabled={transferLoading || !transferTargetId || transferChargeIds.length === 0 || !transferReason.trim()}
              >
                {transferLoading ? 'Aktarılıyor…' : 'Aktar'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={subDialog === 'operations'} onOpenChange={(o) => !o && setSubDialog(null)}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Transfer Geçmişi</DialogTitle>
            <DialogDescription>{operations?.folio_number} ({operations?.count || 0} kayıt)</DialogDescription>
          </DialogHeader>
          {operations && (
            <div className="space-y-2">
              {(operations.operations || []).length === 0 ? (
                <div className="text-center text-gray-400 py-8">Bu folioda transfer/işlem yok.</div>
              ) : (
                (operations.operations || []).map((op) => (
                  <Card key={op.id}>
                    <CardContent className="p-3">
                      <div className="flex justify-between items-start">
                        <div className="flex-1">
                          <div className="font-semibold capitalize">
                            {op.operation_type === 'transfer' ? 'Transfer' : op.operation_type}
                            <span className={`ml-2 text-xs px-1.5 py-0.5 rounded ${op.direction === 'in' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>
                              {op.direction === 'in' ? 'Gelen' : 'Giden'}
                            </span>
                          </div>
                          <div className="text-xs text-gray-600 mt-1">
                            {op.from_folio_number} → {op.to_folio_number || '—'}
                          </div>
                          {op.reason && <div className="text-xs text-gray-700 mt-1">Neden: {op.reason}</div>}
                          {(op.charge_ids || []).length > 0 && (
                            <div className="text-xs text-gray-500">{op.charge_ids.length} işlem aktarıldı</div>
                          )}
                          <div className="text-[11px] text-gray-400 mt-1">
                            {op.performed_by_name || op.performed_by} • {op.performed_at ? new Date(op.performed_at).toLocaleString() : ''}
                          </div>
                        </div>
                        {op.amount != null && (
                          <div className="font-bold">{fmt(op.amount)} ₺</div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={pinGate.open} onOpenChange={(v) => { if (!v) closePinGate(); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <KeyRound className="w-5 h-5" /> PIN doğrulama
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-gray-600">{pinGate.label}</p>
            <Input
              type="password"
              autoFocus
              inputMode="numeric"
              autoComplete="off"
              placeholder="PIN / şifre"
              value={pinValue}
              onChange={(e) => setPinValue(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !pinSubmitting) verifyPin(); }}
              disabled={pinSubmitting}
            />
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={closePinGate} disabled={pinSubmitting}>
                İptal
              </Button>
              <Button onClick={verifyPin} disabled={pinSubmitting || !pinValue.trim()} className="bg-black hover:bg-gray-800 text-white">
                {pinSubmitting ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <KeyRound className="w-4 h-4 mr-2" />}
                Doğrula
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default FolioViewDialog;
