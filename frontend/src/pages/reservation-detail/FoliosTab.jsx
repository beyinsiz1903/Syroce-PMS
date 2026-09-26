import { useMemo, useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  CreditCard, ArrowRightLeft, Building2, DollarSign, ArrowDownUp,
  Plus, Receipt, FileText, Loader2, Split, Printer
} from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Select as UiSelect, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { API, fmtCurrency, fmtTs, SummaryCard, FormField, SelectField, FormPanel } from './helpers';
import SplitFolioDialog from '@/components/SplitFolioDialog';
import PrintableFolio from '@/components/PrintableFolio';
import {
  classifyGuestPayment,
  guestPaymentClassificationLabel,
} from '@/utils/paymentClassification';

const normalizeCurrency = (value) => String(value || 'TL').toUpperCase() === 'TL' ? 'TRY' : String(value || 'TL').toUpperCase();
const COMMON_PAYMENT_CURRENCIES = ['USD', 'EUR', 'GBP', 'CHF'];

export function calculateReceivedCurrency(amount, bookingCurrency, receivedCurrency, rates) {
  const numericAmount = Number(amount);
  const base = normalizeCurrency(bookingCurrency);
  const received = normalizeCurrency(receivedCurrency);
  if (!Number.isFinite(numericAmount) || numericAmount <= 0) return null;

  const baseToTry = base === 'TRY' ? 1 : Number(rates?.[base]);
  const receivedToTry = received === 'TRY' ? 1 : Number(rates?.[received]);
  if (!Number.isFinite(baseToTry) || baseToTry <= 0 || !Number.isFinite(receivedToTry) || receivedToTry <= 0) return null;

  const rate = baseToTry / receivedToTry;
  return { rate, amount: numericAmount * rate };
}

export function parseReceivedCurrency(notes) {
  const match = String(notes || '').match(
    /\[Döviz Çevirici\]\s*[\d.,]+\s+[A-Z]{3}\s*=\s*([\d.,]+)\s+([A-Z]{3})/i,
  );
  if (!match) return null;
  const amount = Number(match[1].replace(',', '.'));
  if (!Number.isFinite(amount)) return null;
  return { amount, currency: match[2].toUpperCase() };
}

export function summarizeReceivedPayments(payments, fallbackAmount, fallbackCurrency) {
  const totals = (payments || [])
    .filter(payment => !payment.voided)
    .map(payment => parseReceivedCurrency(payment.notes))
    .filter(Boolean)
    .reduce((result, payment) => {
      result[payment.currency] = (result[payment.currency] || 0) + payment.amount;
      return result;
    }, {});
  const received = Object.entries(totals).map(([currency, amount]) => ({ currency, amount }));
  if (received.length) return received;
  return Number(fallbackAmount) > 0
    ? [{ amount: Number(fallbackAmount), currency: normalizeCurrency(fallbackCurrency) }]
    : [];
}

export function FoliosTab({ folios, charges, payments, extra_charges, summary, booking, guest, room, onRefresh, onSwitchTab, readOnly = false }) {
  const currency = booking?.currency || "TL";
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [showPayment, setShowPayment] = useState(false);
  const [showCari, setShowCari] = useState(false);
  const [showAgency, setShowAgency] = useState(false);
  const [showCariTransfer, setShowCariTransfer] = useState(false);
  const [showReconcile, setShowReconcile] = useState(false);
  const [payForm, setPayForm] = useState({ amount: '', method: 'cash', reference: '' });
  const [cariAccounts, setCariAccounts] = useState([]);
  const [cariForm, setCariForm] = useState({ amount: '', cari_account_id: '', description: '' });
  const [agencyForm, setAgencyForm] = useState({ amount: '', agency_name: '', reference: '' });
  const [cariTransferForm, setCariTransferForm] = useState({ source_id: '', target_id: '', amount: '', description: '' });
  const [showNewCari, setShowNewCari] = useState(false);
  const [newCariForm, setNewCariForm] = useState({ name: '', account_type: 'agency', tax_id: '', tax_office: '', address: '', phone: '', email: '' });
  const [reconcileForm, setReconcileForm] = useState({ cari_account_id: '', amount: '', description: '' });
  const [showSplit, setShowSplit] = useState(false);
  const [showPrintableFolio, setShowPrintableFolio] = useState(false);
  const [printFolioId, setPrintFolioId] = useState('all');
  const [splitSourceId, setSplitSourceId] = useState('');
  const [loading, setLoading] = useState(false);
  const [actionError, setActionError] = useState('');
  const [reconcilingRoomCharge, setReconcilingRoomCharge] = useState(false);
  const [reconcilingStayTotal, setReconcilingStayTotal] = useState(false);
  // Currency Converter state
  const [useCurrencyConverter, setUseCurrencyConverter] = useState(false);
  const [foreignCurrency, setForeignCurrency] = useState('TL');
  const [foreignAmount, setForeignAmount] = useState('');
  const [exchangeRate, setExchangeRate] = useState('');
  const [tcmbRates, setTcmbRates] = useState({});
  const [ratesLoading, setRatesLoading] = useState(false);
  const [ratesError, setRatesError] = useState('');
  const [manualExchangeRate, setManualExchangeRate] = useState(false);

  const fetchExchangeRates = async () => {
    setRatesLoading(true);
    setRatesError('');
    try {
      const res = await axios.get('/exchange-rates', { timeout: 10000 });
      if (res.data?.rates) setTcmbRates(res.data.rates);
      else setRatesError('Güncel kur bilgisi alınamadı. Kuru elle girebilirsiniz.');
    } catch (e) {
      console.error('Failed to fetch exchange rates', e);
      setRatesError('Güncel kur bilgisi alınamadı. Kuru elle girebilirsiniz.');
    } finally {
      setRatesLoading(false);
    }
  };

  useEffect(() => {
    if (useCurrencyConverter && Object.keys(tcmbRates).length === 0) fetchExchangeRates();
  }, [useCurrencyConverter, tcmbRates]);

  useEffect(() => {
    if (!useCurrencyConverter || manualExchangeRate) return;
    const conversion = calculateReceivedCurrency(payForm.amount, currency, foreignCurrency, tcmbRates);
    if (!conversion) {
      setExchangeRate('');
      setForeignAmount('');
      return;
    }
    setExchangeRate(conversion.rate.toFixed(4));
    setForeignAmount(conversion.amount.toFixed(2));
  }, [useCurrencyConverter, manualExchangeRate, payForm.amount, currency, foreignCurrency, tcmbRates]);

  const folioList = useMemo(() => (Array.isArray(folios) ? folios : []), [folios]);

  // Varsayılan kaynak folyo: önce misafir folyosu, yoksa açık folyo, yoksa ilk folyo.
  const defaultSourceId = useMemo(() => {
    if (folioList.length === 0) return '';
    const guest = folioList.find(f => f.folio_type === 'guest');
    const open = folioList.find(f => f.status === 'open');
    return (guest || open || folioList[0]).id;
  }, [folioList]);

  // SplitFolioDialog tek bir folyo bekler: id, folio_number, balance ve KENDİ kalemleri.
  // charge_ids backend'de source_folio_id'den taşınır; bu yüzden kalemler folio.id ile AYNI folyoya ait olmalı.
  const splitFolio = useMemo(() => {
    const sid = splitSourceId || defaultSourceId;
    const src = folioList.find(f => f.id === sid);
    if (!src) return null;
    // Folio kalemleri (folio_id eşleşen) + booking kapsamlı ekstra masraflar.
    // extra_charges'ın folio_id'si yoktur; bölme sırasında backend bunları
    // booking_id ile doğrulayıp hedef folioya folio kalemi olarak taşır.
    const folioItems = (charges || []).filter(c => c.folio_id === src.id && !c.voided);
    const extraItems = (extra_charges || []).filter(c => !c.voided);
    return {
      id: src.id,
      folio_number: src.folio_number,
      guest_name: guest?.name || guest?.full_name || booking?.guest_name,
      room_number: room?.room_number || room?.number || booking?.room_number,
      balance: src.balance,
      charges: [...folioItems, ...extraItems],
    };
  }, [splitSourceId, defaultSourceId, folioList, charges, extra_charges, booking, guest, room]);

  const hasCharges = useMemo(
    () => (charges || []).some(c => !c.voided) || (extra_charges || []).some(c => !c.voided),
    [charges, extra_charges]
  );
  const pendingRoomAmount = Number(summary?.unposted_room_amount) || 0;
  const pricingReconciliationRequired = Boolean(summary?.pricing_reconciliation_required);
  const pricingReconciliationDifference = Number(summary?.pricing_reconciliation_difference) || 0;
  const pricingReconciliationDirection = summary?.pricing_reconciliation_direction;
  const rawFolioBalance = Number(summary?.folio_balance ?? summary?.balance) || 0;
  const reservationTotalDue = Number(summary?.reservation_total_due ?? summary?.balance) || 0;
  const hasAllocatedPrepayment = pendingRoomAmount > 0.01 && reservationTotalDue <= 0.01 && rawFolioBalance < -0.01;
  const hasHistoricalRoomCredit = readOnly && pendingRoomAmount > 0.01 && Number(summary?.folio_balance) < -0.01;
  const accommodationTotal = Number(summary?.accommodation_total ?? summary?.total_amount) || 0;
  const additionalChargeTotal = Number(summary?.additional_charge_total ?? summary?.total_extra) || 0;
  const prepaymentTotal = Number(summary?.prepayment_total) || 0;
  const grossTotal = Number(summary?.gross_total) || (accommodationTotal + additionalChargeTotal);

  const completePendingRoomCharge = async () => {
    setActionError('');
    setReconcilingRoomCharge(true);
    try {
      const response = await axios.post(`/pms/reservations/${booking.id}/complete-pending-room-charge`);
      if (response.data?.posted) toast.success('Eksik konaklama tahakkuku folyoya işlendi');
      else toast.info('Konaklama tahakkuku zaten tamamlanmış');
      await onRefresh?.();
    } catch (e) {
      const message = 'Tahakkuk tamamlanamadı: ' + (e.response?.data?.detail || e.message);
      setActionError(message);
      toast.error(message);
    } finally {
      setReconcilingRoomCharge(false);
    }
  };

  const reconcileStayTotal = async () => {
    setActionError('');
    setReconcilingStayTotal(true);
    try {
      const response = await axios.post(`/pms/reservations/${booking.id}/reconcile-posted-stay-total`);
      toast.success(`Rezervasyon toplamı ${fmtCurrency(response.data?.new_total, currency)} olarak düzeltildi`);
      await onRefresh?.();
    } catch (e) {
      const message = 'Fiyat mutabakatı tamamlanamadı: ' + (e.response?.data?.detail || e.message);
      setActionError(message);
      toast.error(message);
    } finally {
      setReconcilingStayTotal(false);
    }
  };

  const openSplit = async () => {
    // Folio zaten varsa mevcut akış aynen çalışır.
    if (folioList.length > 0) {
      if (!splitSourceId) setSplitSourceId(defaultSourceId);
      setShowSplit(s => !s);
      return;
    }
    // Folio yok ama masraf var: önce garanti-folio uç noktasını çağır,
    // veriyi yenile, sonra bölme panelini aç.
    if (hasCharges) {
      setLoading(true);
      try {
        await axios.post(`/pms/reservations/${booking.id}/ensure-folio`);
        await onRefresh?.();
        setShowSplit(true);
      } catch (e) {
        const message = 'Folyo hazırlanamadı: ' + (e.response?.data?.detail || e.message);
        setActionError(message);
        toast.error(message);
      }
      setLoading(false);
      return;
    }
    // Ne masraf ne folio var: bilgilendirici mesaj.
    toast.error('Bölünecek folyo bulunmuyor');
  };

  const loadCari = async () => { try { const r = await axios.get(`/pms/cari-accounts`); setCariAccounts(r.data.accounts || []); } catch { /* fetch error */ } };

  const exec = async (fn) => { setLoading(true); setActionError(''); try { await fn(); onRefresh?.(); } catch (e) { const message = e.response?.data?.detail || e.message; setActionError(message); toast.error('İşlem Hatası: ' + message); } setLoading(false); };

  const allItems = useMemo(() => {
    const seen = new Set();
    return [
      ...(charges || []).map(c => ({ ...c, _type: 'charge', _source: 'folio' })),
      ...(extra_charges || []).map(c => ({ ...c, _type: 'charge', _source: 'extra' })),
      ...(payments || []).map(p => ({ ...p, _type: 'payment' })),
    ].filter(item => {
      const key = `${item._type}:${item.id || item.charge_id || item.payment_id || `${item.description || item.charge_name}:${item.amount || item.total}:${item.created_at}`}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    }).sort((a, b) => new Date(b.created_at || b.processed_at || 0) - new Date(a.created_at || a.processed_at || 0));
  }, [charges, extra_charges, payments]);
  const allocatedPrepaymentReceipts = useMemo(
    () => summarizeReceivedPayments(payments, Math.abs(rawFolioBalance), currency),
    [payments, rawFolioBalance, currency],
  );

  const itemKind = (item) => {
    if (item._type === 'payment') {
      return String(item.payment_type || '').toLowerCase() === 'prepayment' ? 'Ön ödeme' : 'Tahsilat';
    }
    const category = String(item.category || item.charge_category || '').toLowerCase();
    const categoryLabels = {
      food_beverage: 'Yiyecek & İçecek',
      food_and_beverage: 'Yiyecek & İçecek',
      restaurant: 'Yiyecek & İçecek',
      minibar: 'Minibar',
      spa: 'Spa',
      laundry: 'Çamaşırhane',
      transfer: 'Transfer',
      other: 'Diğer ekstra',
    };
    if (item._source === 'extra') return categoryLabels[category] || item.category || item.charge_category || 'Ekstra hizmet';
    if (item.charge_type === 'room_charge' || item.charge_category === 'room') return 'Konaklama';
    if (item.charge_type === 'tax' || ['tax', 'city_tax'].includes(item.charge_category)) return 'Vergi';
    return categoryLabels[category] || item.category || item.charge_category || 'Ekstra hizmet';
  };

  return (
    <div data-testid="folios-tab" className="space-y-4">
      {actionError && <div role="alert" className="flex items-start justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800"><span><b>İşlem tamamlanamadı:</b> {actionError}</span><button type="button" className="font-semibold text-rose-700 hover:text-rose-900" onClick={() => setActionError('')} aria-label="Hata mesajını kapat">×</button></div>}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <SummaryCard currency={currency} label="Konaklama" value={accommodationTotal} color="blue" />
        <SummaryCard currency={currency} label="Ekstralar" value={additionalChargeTotal} color="amber" />
        <SummaryCard currency={currency} label="Genel Toplam" value={grossTotal} color="blue" />
        <SummaryCard currency={currency} label="Tahsilatlar" value={summary?.total_payments} color="emerald" />
        <SummaryCard currency={currency} label="Kalan Bakiye" value={reservationTotalDue} color={reservationTotalDue > 0 ? 'red' : 'green'} />
        {(summary?.total_discounts || 0) > 0 && (
          <SummaryCard currency={currency} label="İndirimler" value={summary?.total_discounts} color="rose" />
        )}
      </div>
      {prepaymentTotal > 0 && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900" data-testid="prepayment-summary">
          <span className="font-semibold">Ön ödeme alındı:</span> {fmtCurrency(prepaymentTotal, currency)}
          <span className="ml-2 text-xs text-emerald-700">Toplam tahsilata ve kalan bakiyeye dahil edilmiştir.</span>
        </div>
      )}
      {hasAllocatedPrepayment && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800" data-testid="allocated-prepayment-note">
          Peşin tahsilat: {allocatedPrepaymentReceipts.map(receipt => fmtCurrency(receipt.amount, receipt.currency)).join(' + ')}.
          {' '}{fmtCurrency(Math.abs(rawFolioBalance), currency)} rezervasyon bakiyesine mahsup edildi; {fmtCurrency(pendingRoomAmount, currency)} bekleyen konaklama tahakkukuna ayrıldı. Tahsilat bakiyesi kapandı.
        </div>
      )}
      {pricingReconciliationRequired && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900" data-testid="folio-pricing-reconciliation-alert">
          <span>{pricingReconciliationDirection === 'booking_above_posted'
            ? `Rezervasyon toplamı, tamamlanmış oda tahakkuklarından ${fmtCurrency(pricingReconciliationDifference, currency)} fazla görünüyor. Bu tutar misafire yeniden yansıtılmaz.`
            : `Oda tahakkukları, onaylı rezervasyon toplamından ${fmtCurrency(pricingReconciliationDifference, currency)} fazla. Bu fark tahsil edilmez; ödeme almadan önce mutabakatı tamamlayın.`}</span>
          {!readOnly && summary?.room_plan_fully_posted && (
            <Button size="sm" variant="outline" onClick={reconcileStayTotal} disabled={reconcilingStayTotal} className="h-8 border-amber-400 bg-white text-xs text-amber-800" data-testid="btn-reconcile-posted-stay-total">
              {reconcilingStayTotal && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
              Tahakkuklarla Eşitle
            </Button>
          )}
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {!readOnly && <>
          <Button size="sm" disabled={pricingReconciliationRequired} onClick={() => { const bal = reservationTotalDue; setPayForm(p => ({ ...p, amount: bal > 0 ? String(bal) : p.amount })); setShowPayment(!showPayment); }} className="bg-emerald-600 hover:bg-emerald-700 text-white h-8 text-xs" data-testid="btn-odeme-al"><CreditCard className="w-3 h-3 mr-1" /> Ödeme Al</Button>
          <Button size="sm" variant="outline" onClick={() => { const bal = reservationTotalDue; setCariForm(p => ({ ...p, amount: bal > 0 ? String(bal) : p.amount })); setShowCari(!showCari); loadCari(); }} className="h-8 text-xs border-amber-300 text-amber-700 hover:bg-amber-50" data-testid="btn-cariye-aktar"><ArrowRightLeft className="w-3 h-3 mr-1" /> Cariye Aktar</Button>
          <Button size="sm" variant="outline" onClick={() => { const bal = reservationTotalDue; setAgencyForm(p => ({ ...p, amount: bal > 0 ? String(bal) : p.amount })); setShowAgency(!showAgency); }} className="h-8 text-xs border-indigo-300 text-indigo-700 hover:bg-indigo-50" data-testid="btn-acente-odemesi"><Building2 className="w-3 h-3 mr-1" /> Acente Ödemesi</Button>
          <Button size="sm" variant="outline" onClick={() => { setShowCariTransfer(!showCariTransfer); loadCari(); }} className="h-8 text-xs border-indigo-300 text-indigo-700 hover:bg-indigo-50" data-testid="btn-acenteye-aktar"><ArrowDownUp className="w-3 h-3 mr-1" /> Acenteye Aktar</Button>
          <Button size="sm" variant="outline" onClick={() => { const bal = reservationTotalDue; setReconcileForm(p => ({ ...p, amount: bal > 0 ? String(bal) : p.amount })); setShowReconcile(!showReconcile); loadCari(); }} className="h-8 text-xs border-teal-300 text-teal-700 hover:bg-teal-50" data-testid="btn-mahsuplastir"><DollarSign className="w-3 h-3 mr-1" /> Mahsuplaştır</Button>
          <Button size="sm" variant="outline" onClick={openSplit} className="h-8 text-xs border-sky-300 text-sky-700 hover:bg-sky-50" data-testid="btn-folyo-bol"><Split className="w-3 h-3 mr-1" /> Folyo Böl</Button>
        </>}
        {folioList.length > 1 && (
          <UiSelect value={printFolioId} onValueChange={setPrintFolioId}>
            <SelectTrigger className="h-8 w-auto min-w-44 text-xs" aria-label="Yazdırılacak folyo"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tüm folyolar (konsolide)</SelectItem>
              {folioList.map(item => <SelectItem key={item.id} value={item.id}>{item.folio_number || item.id}</SelectItem>)}
            </SelectContent>
          </UiSelect>
        )}
        <Button size="sm" variant="outline" onClick={() => setShowPrintableFolio(true)} className="h-8 text-xs border-slate-300 text-slate-700 hover:bg-slate-50" data-testid="btn-folyo-yazdir"><Printer className="w-3 h-3 mr-1" /> Folyo Yazdır</Button>
        <Button size="sm" variant="outline" onClick={() => onSwitchTab('invoice')} className="h-8 text-xs border-blue-300 text-blue-700 hover:bg-blue-50" data-testid="btn-fatura-pdf">
          <FileText className="w-3 h-3 mr-1" /> {readOnly ? 'Faturayı Görüntüle' : 'Fatura Oluştur'}
        </Button>
        {hasHistoricalRoomCredit && (
          <Button size="sm" variant="outline" onClick={completePendingRoomCharge} disabled={reconcilingRoomCharge} className="h-8 text-xs border-amber-300 text-amber-700 hover:bg-amber-50" data-testid="btn-complete-pending-room-charge">
            {reconcilingRoomCharge ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Receipt className="w-3 h-3 mr-1" />}
            Eksik Konaklamayı Tahakkuk Ettir ({fmtCurrency(pendingRoomAmount, currency)})
          </Button>
        )}
      </div>

      {showSplit && (
        <div className="border rounded-lg p-4 bg-sky-50/40 space-y-3" data-testid="split-folio-panel">
          {folioList.length > 1 && (
            <SelectField
              label="Kaynak Folyo"
              value={splitSourceId || defaultSourceId}
              onChange={setSplitSourceId}
              options={folioList.map(f => [f.id, `${f.folio_number} (${f.folio_type || ''}) — Bakiye ${fmtCurrency(f.balance, currency)}`])}
            />
          )}
          {splitFolio && (
            <SplitFolioDialog
              key={splitFolio.id}
              folio={splitFolio}
              onClose={() => setShowSplit(false)}
              onSuccess={() => { setShowSplit(false); onRefresh?.(); }}
            />
          )}
        </div>
      )}

      {showPayment && (
        <FormPanel color="emerald" title={t('common.paymentRecord')} testid="payment-form" onClose={() => setShowPayment(false)} loading={loading}
          onSubmit={() => exec(async () => {
            if (payForm.method === 'discount' && !payForm.reference) { toast.error('Lütfen indirim sebebini yazın'); return; }
            const amount = parseFloat(payForm.amount);
            await axios.post(`/pms/reservations/${booking.id}/record-payment`, {
              ...payForm,
              amount,
              payment_type: classifyGuestPayment(amount, reservationTotalDue),
              ...(useCurrencyConverter && foreignAmount && exchangeRate ? {
                notes: `[Döviz Çevirici] ${Number(amount).toFixed(2)} ${currency} = ${Number(foreignAmount).toFixed(2)} ${foreignCurrency}. Kur: 1 ${currency} = ${exchangeRate} ${foreignCurrency}`
              } : {}),
            });
            toast.success('Ödeme kaydedildi'); setShowPayment(false); setPayForm({ amount: '', method: 'cash', reference: '' });
            setUseCurrencyConverter(false);
            setForeignAmount('');
            setExchangeRate('');
            setManualExchangeRate(false);
          })}>
          <div className="grid grid-cols-2 gap-3">
            <FormField label={`Tutar (${currency})`} type="number" value={payForm.amount} onChange={v => { setPayForm(p => ({ ...p, amount: v })); if (useCurrencyConverter && manualExchangeRate && exchangeRate && !isNaN(parseFloat(v))) setForeignAmount((parseFloat(v) * parseFloat(exchangeRate)).toFixed(2)); }} />
            <SelectField label={t('common.paymentMethod')} value={payForm.method} onChange={v => setPayForm(p => ({ ...p, method: v }))}
              options={[['cash','Nakit'],['card','Kredi Kartı'],['bank_transfer','Havale/EFT'],['online','Online'],['discount','İndirim (Düzeltme)']]} />
          </div>
          <FormField label={payForm.method === 'discount' ? 'İndirim Sebebi / Not' : 'Referans'} value={payForm.reference} onChange={v => setPayForm(p => ({ ...p, reference: v }))} placeholder={payForm.method === 'discount' ? 'İndirimin nedeni (zorunlu)' : 'Fiş / dekont no'} />
          {/* Currency Converter */}
          <div className="mt-4 border-t pt-3 border-slate-100">
            <div className="flex items-center space-x-2">
              <Checkbox id="useConverter" checked={useCurrencyConverter} onCheckedChange={(checked) => {
                setUseCurrencyConverter(checked);
                setManualExchangeRate(false);
              }} />
              <Label htmlFor="useConverter" className="text-sm font-medium text-slate-700 cursor-pointer">
                Farklı Döviz ile Hesapla (Kur Çevirici)
              </Label>
            </div>
            {useCurrencyConverter && (
              <div className="bg-slate-50 border border-slate-200 rounded p-3 mt-3 space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label className="text-xs">Alınan Döviz Cinsi</Label>
                    <UiSelect value={foreignCurrency} onValueChange={(val) => {
                      setForeignCurrency(val);
                      setManualExchangeRate(false);
                    }}>
                      <SelectTrigger className="h-8 mt-1"><SelectValue /></SelectTrigger>
                      <SelectContent className="z-[80]">
                        <SelectItem value="TL">TL (Türk Lirası)</SelectItem>
                        {[...new Set([...COMMON_PAYMENT_CURRENCIES, ...Object.keys(tcmbRates)])]
                          .filter(cur => !['TL', 'TRY'].includes(cur))
                          .sort()
                          .map(cur => <SelectItem key={cur} value={cur}>{cur}</SelectItem>)}
                      </SelectContent>
                    </UiSelect>
                  </div>
                  <div>
                    <Label className="text-xs">Uygulanan Kur (1 {currency} = kaç {foreignCurrency})</Label>
                    <Input type="number" step="0.0001" className="h-8 mt-1" value={exchangeRate} onChange={e => {
                      setExchangeRate(e.target.value);
                      setManualExchangeRate(true);
                      const rate = parseFloat(e.target.value);
                      const baseAmt = parseFloat(payForm.amount);
                      if (!isNaN(rate) && !isNaN(baseAmt)) setForeignAmount((baseAmt * rate).toFixed(2));
                    }} />
                  </div>
                </div>
                {ratesLoading && <div className="flex items-center gap-2 text-xs text-slate-600" role="status"><Loader2 className="h-3 w-3 animate-spin" /> Güncel kurlar alınıyor…</div>}
                {ratesError && <div className="text-xs text-amber-700" role="alert">{ratesError}</div>}
                <div>
                  <Label className="text-xs">Misafirden Alınacak Tutar ({foreignCurrency})</Label>
                  <Input type="number" step="0.01" className="h-8 mt-1 font-semibold text-emerald-600" value={foreignAmount} onChange={e => {
                    setForeignAmount(e.target.value);
                    const fAmt = parseFloat(e.target.value);
                    const rate = parseFloat(exchangeRate);
                    if (!isNaN(fAmt) && !isNaN(rate) && rate > 0) setPayForm(p => ({...p, amount: (fAmt / rate).toFixed(2)}));
                  }} />
                </div>
                {exchangeRate && foreignAmount && (
                  <div className="text-xs text-slate-600" data-testid="currency-conversion-summary">
                    {Number(payForm.amount).toFixed(2)} {currency} = {Number(foreignAmount).toFixed(2)} {foreignCurrency} · 1 {currency} = {exchangeRate} {foreignCurrency}
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="rounded-md border border-emerald-200 bg-white/70 px-3 py-2 text-xs text-emerald-800" data-testid="payment-classification">
            <div className="font-medium">{guestPaymentClassificationLabel(payForm.amount, reservationTotalDue)}</div>
            <div className="mt-0.5 text-emerald-700">Ödeme türü otomatik belirlenir. Depozito için ayrı Depozito sekmesini kullanın.</div>
          </div>
        </FormPanel>
      )}

      {showCari && (
        <FormPanel color="amber" title="Cariye Aktar" testid="cari-transfer-form" onClose={() => setShowCari(false)} loading={loading}
          onSubmit={() => exec(async () => {
            await axios.post(`/pms/reservations/${booking.id}/transfer-to-cari`, { ...cariForm, amount: parseFloat(cariForm.amount) });
            toast.success('Cariye aktarıldı'); setShowCari(false); setCariForm({ amount: '', cari_account_id: '', description: '' });
          })}>
          <div className="grid grid-cols-2 gap-3">
            <FormField label={`Tutar (${currency})`} type="number" value={cariForm.amount} onChange={v => setCariForm(p => ({ ...p, amount: v }))} />
            <SelectField label="Cari Hesap" value={cariForm.cari_account_id} onChange={v => setCariForm(p => ({ ...p, cari_account_id: v }))}
              options={[['','Hesap Seçiniz...'], ...cariAccounts.map(a => [a.id, `${a.name} (${a.account_type || ''})`])]} />
          </div>
          <FormField label="Açıklama" value={cariForm.description} onChange={v => setCariForm(p => ({ ...p, description: v }))} placeholder="Opsiyonel" />
        </FormPanel>
      )}

      {showAgency && (
        <FormPanel color="blue" title="Acente Ödemesi" testid="agency-payment-form" onClose={() => setShowAgency(false)} loading={loading}
          onSubmit={() => exec(async () => {
            await axios.post(`/pms/reservations/${booking.id}/record-agency-payment`, { ...agencyForm, amount: parseFloat(agencyForm.amount) });
            toast.success('Acente ödemesi kaydedildi'); setShowAgency(false); setAgencyForm({ amount: '', agency_name: '', reference: '' });
          })}>
          <div className="grid grid-cols-2 gap-3">
            <FormField label={`Tutar (${currency})`} type="number" value={agencyForm.amount} onChange={v => setAgencyForm(p => ({ ...p, amount: v }))} />
            <FormField label="Acente Adı" value={agencyForm.agency_name} onChange={v => setAgencyForm(p => ({ ...p, agency_name: v }))} />
          </div>
          <FormField label="Referans" value={agencyForm.reference} onChange={v => setAgencyForm(p => ({ ...p, reference: v }))} placeholder="Voucher No" />
        </FormPanel>
      )}

      {showCariTransfer && (
        <FormPanel color="indigo" title="Cariyi Acenteye Aktar" testid="cari-agency-transfer-form" onClose={() => setShowCariTransfer(false)} loading={loading}
          onSubmit={() => exec(async () => {
            if (!cariTransferForm.source_id || !cariTransferForm.target_id) { toast.error('Kaynak ve hedef cari hesap seçiniz'); return; }
            if (cariTransferForm.source_id === cariTransferForm.target_id) { toast.error('Kaynak ve hedef cari hesap farklı olmalı'); return; }
            await axios.post(`/pms/cari-accounts/${cariTransferForm.source_id}/transfer-to-agency`, {
              amount: parseFloat(cariTransferForm.amount),
              cari_account_id: cariTransferForm.target_id,
              description: cariTransferForm.description || 'Acenteye aktarım'
            });
            toast.success('Cari bakiye acenteye aktarıldı');
            setShowCariTransfer(false);
            setCariTransferForm({ source_id: '', target_id: '', amount: '', description: '' });
          })}>
          <div className="grid grid-cols-2 gap-3">
            <SelectField label="Kaynak Cari Hesap" value={cariTransferForm.source_id} onChange={v => setCariTransferForm(p => ({ ...p, source_id: v }))}
              options={[['','Hesap Seçiniz...'], ...cariAccounts.map(a => [a.id, `${a.name} (${a.account_type || ''})`])]} />
            <div>
              <SelectField label="Hedef Acente Hesabı" value={cariTransferForm.target_id} onChange={v => setCariTransferForm(p => ({ ...p, target_id: v }))}
                options={[['','Acente Seçiniz...'], ...cariAccounts.filter(a => a.account_type === 'agency').map(a => [a.id, a.name])]} />
              <Button size="sm" variant="ghost" className="h-6 text-xs text-indigo-600 mt-1 px-0" onClick={() => setShowNewCari(true)} data-testid="btn-new-cari"><Plus className="w-3 h-3 mr-1" /> Yeni Cari Oluştur</Button>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <FormField label={`Tutar (${currency})`} type="number" value={cariTransferForm.amount} onChange={v => setCariTransferForm(p => ({ ...p, amount: v }))} />
            <FormField label="Açıklama" value={cariTransferForm.description} onChange={v => setCariTransferForm(p => ({ ...p, description: v }))} placeholder="Opsiyonel" />
          </div>
        </FormPanel>
      )}

      {showNewCari && (
        <div className="border rounded-lg p-4 bg-indigo-50/50 space-y-3" data-testid="new-cari-form">
          <div className="text-sm font-semibold text-indigo-800">Yeni Cari Hesap Oluştur</div>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Hesap Adi *" value={newCariForm.name} onChange={v => setNewCariForm(p => ({ ...p, name: v }))} placeholder="Acente / Şirket adi" />
            <SelectField label="Hesap Tipi" value={newCariForm.account_type} onChange={v => setNewCariForm(p => ({ ...p, account_type: v }))}
              options={[['agency','Acente'],['corporate','Kurumsal'],['individual','Bireysel']]} />
            <FormField label="Vergi No" value={newCariForm.tax_id} onChange={v => setNewCariForm(p => ({ ...p, tax_id: v }))} placeholder="Vergi / TC No" />
            <FormField label="Vergi Dairesi" value={newCariForm.tax_office} onChange={v => setNewCariForm(p => ({ ...p, tax_office: v }))} placeholder="Vergi dairesi" />
            <FormField label="Telefon" value={newCariForm.phone} onChange={v => setNewCariForm(p => ({ ...p, phone: v }))} placeholder="Telefon" />
            <FormField label="E-posta" value={newCariForm.email} onChange={v => setNewCariForm(p => ({ ...p, email: v }))} placeholder="E-posta" />
          </div>
          <FormField label="Adres" value={newCariForm.address} onChange={v => setNewCariForm(p => ({ ...p, address: v }))} placeholder="Adres" />
          <div className="flex gap-2">
            <Button size="sm" onClick={async () => {
              if (!newCariForm.name) { toast.error('Hesap adı zorunlu'); return; }
              setLoading(true);
              try {
                await axios.post(`/pms/cari-accounts/create`, newCariForm);
                toast.success('Yeni cari hesap oluşturuldu');
                setShowNewCari(false);
                setNewCariForm({ name: '', account_type: 'agency', tax_id: '', tax_office: '', address: '', phone: '', email: '' });
                loadCari();
              } catch (e) { toast.error('İşlem Hatası: ' + (e.response?.data?.detail || e.message)); }
              setLoading(false);
            }} disabled={loading} className="bg-indigo-600 hover:bg-indigo-700 text-white h-8 text-xs" data-testid="create-cari-btn">
              {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Oluştur'}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowNewCari(false)} className="h-8 text-xs">İptal</Button>
          </div>
        </div>
      )}

      {showReconcile && (
        <FormPanel color="teal" title="Mahsuplaştırma (Cari Ödeme)" testid="reconcile-form" onClose={() => setShowReconcile(false)} loading={loading}
          onSubmit={() => exec(async () => {
            if (!reconcileForm.cari_account_id) { toast.error('Cari hesap seçiniz'); return; }
            await axios.post(`/pms/cari-accounts/${reconcileForm.cari_account_id}/reconcile`, {
              amount: parseFloat(reconcileForm.amount),
              description: reconcileForm.description || 'Mahsuplaştırma'
            });
            toast.success('Mahsuplaştırma kaydedildi');
            setShowReconcile(false);
            setReconcileForm({ cari_account_id: '', amount: '', description: '' });
          })}>
          <div className="grid grid-cols-2 gap-3">
            <SelectField label="Cari Hesap" value={reconcileForm.cari_account_id} onChange={v => setReconcileForm(p => ({ ...p, cari_account_id: v }))}
              options={[['','Hesap Seçiniz...'], ...cariAccounts.map(a => [a.id, `${a.name} (${a.account_type || ''})`])]} />
            <FormField label={`Tutar (${currency})`} type="number" value={reconcileForm.amount} onChange={v => setReconcileForm(p => ({ ...p, amount: v }))} />
          </div>
          <FormField label="Açıklama" value={reconcileForm.description} onChange={v => setReconcileForm(p => ({ ...p, description: v }))} placeholder="Mahsuplaştırma açıklaması" />
        </FormPanel>
      )}

      {showPrintableFolio && (
        <PrintableFolio
          folioData={{
            ...((printFolioId === 'all' ? folioList[0] : folioList.find(item => item.id === printFolioId)) || {}),
            document_title: printFolioId === 'all' && folioList.length > 1 ? 'Konsolide Misafir Folyosu' : 'Misafir Folyosu',
            folio_number: printFolioId === 'all'
              ? folioList.map(item => item.folio_number).filter(Boolean).join(', ') || undefined
              : folioList.find(item => item.id === printFolioId)?.folio_number,
            booking,
            charges: printFolioId === 'all' ? charges : (charges || []).filter(item => item.folio_id === printFolioId),
            extra_charges: printFolioId === 'all' ? extra_charges : (extra_charges || []).filter(item => item.folio_id === printFolioId),
            payments: printFolioId === 'all' ? payments : (payments || []).filter(item => !item.folio_id || item.folio_id === printFolioId),
            currency,
            balance: printFolioId === 'all'
              ? reservationTotalDue
              : folioList.find(item => item.id === printFolioId)?.balance,
          }}
          guest={guest}
          room={room}
          onClose={() => setShowPrintableFolio(false)}
        />
      )}

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="text-xs font-semibold text-gray-500 uppercase">İşlem Geçmişi</div>
          <Button variant="link" size="sm" className="h-auto p-0 text-indigo-600 hover:text-indigo-700" onClick={() => navigate(`/folio-detail/${folios?.[0]?.id}`)} disabled={!folios || folios.length === 0}>
            Gelişmiş Folyo Yönetimi &rarr;
          </Button>
        </div>
        {allItems.length === 0 ? <div className="text-center py-6 text-gray-400 text-sm">Henüz işlem bulunmuyor</div> : (
          allItems.map((item, i) => {
            const received = item._type === 'payment' ? parseReceivedCurrency(item.notes) : null;
            return (
            <div key={item.id || i} className={`flex items-center gap-3 p-3 rounded-lg border ${item.voided ? 'opacity-60 bg-gray-50' : 'bg-white'}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center ${item._type === 'payment' ? 'bg-emerald-100' : 'bg-amber-100'}`}>
                {item._type === 'payment' ? <CreditCard className="w-4 h-4 text-emerald-600" /> : <Receipt className="w-4 h-4 text-amber-600" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-gray-800">
                  {item.description || item.charge_name || item.method || item.payment_type || '-'}
                  {item.voided && <span className="ml-2 rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-700">İPTAL</span>}
                </div>
                <div className="text-xs text-gray-400">
                  <span className="font-medium text-slate-500">{itemKind(item)}</span>
                  <span className="mx-1">·</span>{fmtTs(item.created_at || item.processed_at)}
                  {item.agency_name && <span className="ml-2 text-indigo-600">({item.agency_name})</span>}
                </div>
                {received && !item.voided && (
                  <div className="mt-1 text-xs font-semibold text-emerald-700" data-testid={`received-currency-${item.id || i}`}>
                    Alınan: {fmtCurrency(received.amount, received.currency)}
                  </div>
                )}
              </div>
              <div className={`text-sm font-bold ${item._type === 'payment' ? 'text-emerald-600' : 'text-amber-600'}`}>
                {item._type === 'payment' ? '-' : '+'}{fmtCurrency(item.total ?? item.charge_amount ?? item.amount, currency)}
              </div>
            </div>
          );
          })
        )}
      </div>
    </div>
  );
}
