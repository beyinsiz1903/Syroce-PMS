import { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Wallet, DollarSign, ArrowRightLeft, Clock,
  LogIn, LogOut, Receipt, RefreshCw,
  Calculator, UserCheck, Users, Plus, Minus,
  FileText, FileDown, Search, Printer, AlertTriangle,
  Landmark, CalendarRange
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const DIFF_THRESHOLD = 50;
const CURRENCIES = [
  { code: 'TRY', label: 'TRY (₺)' },
  { code: 'USD', label: 'USD ($)' },
  { code: 'EUR', label: 'EUR (€)' },
  { code: 'GBP', label: 'GBP (£)' },
];

const todayIso = () => new Date().toISOString().slice(0, 10);
const monthAgoIso = () => { const d = new Date(); d.setDate(d.getDate() - 30); return d.toISOString().slice(0, 10); };

const CashierTab = () => {
  const { t } = useTranslation();
  const [shift, setShift] = useState(null);
  const [shiftHistory, setShiftHistory] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showOpenDialog, setShowOpenDialog] = useState(false);
  const [showCloseDialog, setShowCloseDialog] = useState(false);
  const [showHandoverDialog, setShowHandoverDialog] = useState(false);
  const [showCashInDialog, setShowCashInDialog] = useState(false);
  const [showPaidOutDialog, setShowPaidOutDialog] = useState(false);
  const [openingAmount, setOpeningAmount] = useState('');
  const [closingCounts, setClosingCounts] = useState({
    cash_200: 0, cash_100: 0, cash_50: 0, cash_20: 0, cash_10: 0, cash_5: 0, cash_1: 0,
    coin_1: 0, coin_050: 0, coin_025: 0
  });
  const [closingNote, setClosingNote] = useState('');
  const [handoverTarget, setHandoverTarget] = useState({ email: '', password: '', note: '' });
  const [manualTxn, setManualTxn] = useState({ amount: '', method: 'cash', description: '', currency: 'TRY', fx_rate: '1' });

  const [txnSearch, setTxnSearch] = useState('');
  const [txnMethodFilter, setTxnMethodFilter] = useState('all');
  const [reportData, setReportData] = useState(null);
  const [showReportDialog, setShowReportDialog] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);

  const [showBankDepositDialog, setShowBankDepositDialog] = useState(false);
  const [bankDeposit, setBankDeposit] = useState({ amount: '', bank_name: '', account_no: '', reference: '', note: '' });

  const [showPeriodReportDialog, setShowPeriodReportDialog] = useState(false);
  const [periodRange, setPeriodRange] = useState({ start: monthAgoIso(), end: todayIso() });
  const [periodData, setPeriodData] = useState(null);
  const [periodLoading, setPeriodLoading] = useState(false);

  const loadShift = useCallback(async () => {
    try {
      const res = await axios.get('/cashier/current-shift');
      setShift(res.data.shift || null);
      setTransactions(res.data.transactions || []);
    } catch (err) {
      setShift(null);
      setTransactions([]);
      if (err?.response?.status !== 404) {
        toast.error('Kasa vardiyası yüklenemedi');
      }
    }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const res = await axios.get('/cashier/shift-history?limit=20');
      setShiftHistory(res.data.shifts || []);
    } catch { setShiftHistory([]); }
  }, []);

  useEffect(() => { loadShift(); loadHistory(); }, [loadShift, loadHistory]);

  const openShift = async () => {
    setLoading(true);
    try {
      await axios.post('/cashier/open-shift', { opening_amount: parseFloat(openingAmount) || 0 });
      toast.success('Kasa vardiyası açıldı');
      setShowOpenDialog(false);
      setOpeningAmount('');
      loadShift();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  const calcTotal = (counts) =>
    (counts.cash_200 * 200) + (counts.cash_100 * 100) + (counts.cash_50 * 50) +
    (counts.cash_20 * 20) + (counts.cash_10 * 10) + (counts.cash_5 * 5) +
    (counts.cash_1 * 1) + (counts.coin_1 * 1) + (counts.coin_050 * 0.5) + (counts.coin_025 * 0.25);

  const closeShift = async () => {
    if (Math.abs(difference) >= DIFF_THRESHOLD && !closingNote.trim()) {
      toast.error(`Fark ${DIFF_THRESHOLD} TL'yi aştığı için açıklama zorunlu`);
      return;
    }
    setLoading(true);
    try {
      await axios.post('/cashier/close-shift', {
        counted_amount: calcTotal(closingCounts),
        denomination_counts: closingCounts,
        notes: closingNote
      });
      toast.success('Kasa vardiyası kapatıldı');
      setShowCloseDialog(false);
      setClosingCounts({ cash_200: 0, cash_100: 0, cash_50: 0, cash_20: 0, cash_10: 0, cash_5: 0, cash_1: 0, coin_1: 0, coin_050: 0, coin_025: 0 });
      setClosingNote('');
      loadShift();
      loadHistory();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  const handoverShift = async () => {
    if (!handoverTarget.email.trim() || !handoverTarget.password.trim()) {
      toast.error('Devir alacak kişinin e-posta ve şifresi gerekli');
      return;
    }
    setLoading(true);
    try {
      const res = await axios.post('/cashier/handover-shift', {
        target_email: handoverTarget.email.trim(),
        target_password: handoverTarget.password.trim(),
        note: handoverTarget.note
      });
      toast.success(`Vardiya ${res.data.target_name || handoverTarget.email} adlı kullanıcıya devredildi`);
      setShowHandoverDialog(false);
      setHandoverTarget({ email: '', password: '', note: '' });
      loadShift();
      loadHistory();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  const submitManual = async (direction) => {
    const amt = parseFloat(manualTxn.amount);
    if (!amt || amt <= 0) { toast.error('Tutar girin'); return; }
    if (!manualTxn.description.trim()) { toast.error('Açıklama girin'); return; }
    const cur = manualTxn.currency || 'TRY';
    const fx = parseFloat(manualTxn.fx_rate) || 1;
    if (cur !== 'TRY' && (!fx || fx <= 0)) { toast.error('Yabancı para için kur girin'); return; }
    setLoading(true);
    try {
      const idemKey = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);
      await axios.post('/cashier/manual-transaction', {
        amount: amt,
        direction,
        method: manualTxn.method,
        description: manualTxn.description.trim(),
        currency: cur,
        fx_rate: cur === 'TRY' ? 1 : fx,
        original_amount: amt,
      }, { headers: { 'X-Idempotency-Key': idemKey } });
      toast.success(direction === 'in' ? 'Nakit girişi kaydedildi' : 'Kasa çıkışı kaydedildi');
      setShowCashInDialog(false);
      setShowPaidOutDialog(false);
      setManualTxn({ amount: '', method: 'cash', description: '', currency: 'TRY', fx_rate: '1' });
      loadShift();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  const submitBankDeposit = async () => {
    const amt = parseFloat(bankDeposit.amount);
    if (!amt || amt <= 0) { toast.error('Tutar girin'); return; }
    if (!bankDeposit.bank_name.trim()) { toast.error('Banka adı zorunlu'); return; }
    setLoading(true);
    try {
      const idemKey = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);
      await axios.post('/cashier/bank-deposit', {
        amount: amt,
        bank_name: bankDeposit.bank_name.trim(),
        account_no: bankDeposit.account_no.trim() || undefined,
        reference: bankDeposit.reference.trim() || undefined,
        note: bankDeposit.note.trim() || undefined,
      }, { headers: { 'X-Idempotency-Key': idemKey } });
      toast.success('Banka yatırma kaydedildi');
      setShowBankDepositDialog(false);
      setBankDeposit({ amount: '', bank_name: '', account_no: '', reference: '', note: '' });
      loadShift();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  const loadPeriodReport = async () => {
    if (!periodRange.start || !periodRange.end) { toast.error('Tarih aralığı seçin'); return; }
    setPeriodLoading(true);
    try {
      const res = await axios.get('/cashier/period-report', {
        params: { start_date: periodRange.start, end_date: periodRange.end }
      });
      setPeriodData(res.data);
    } catch (e) { toast.error('Rapor alınamadı: ' + (e.response?.data?.detail || e.message)); }
    setPeriodLoading(false);
  };

  const exportPeriodCsv = () => {
    if (!periodData) { toast.error('Önce rapor getirin'); return; }
    const t = periodData.totals || {};
    const lines = [];
    const escape = (v) => {
      let s = (v ?? '').toString();
      if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
      s = s.replace(/"/g, '""');
      return /[",\n;]/.test(s) ? `"${s}"` : s;
    };
    lines.push(['Donem Raporu', `${periodData.start_date} - ${periodData.end_date}`].map(escape).join(','));
    lines.push(['Olusturuldu', periodData.generated_at || '', periodData.generated_by || ''].map(escape).join(','));
    lines.push('');
    lines.push(['TOPLAMLAR'].map(escape).join(','));
    lines.push(['Vardiya sayisi', t.shift_count || 0].map(escape).join(','));
    lines.push(['Acilis toplam', (t.opening_total || 0).toFixed(2)].map(escape).join(','));
    lines.push(['Nakit giris', (t.cash_in_total || 0).toFixed(2)].map(escape).join(','));
    lines.push(['Nakit cikis', (t.cash_out_total || 0).toFixed(2)].map(escape).join(','));
    lines.push(['Beklenen', (t.expected_total || 0).toFixed(2)].map(escape).join(','));
    lines.push(['Sayilan kapanis', (t.closing_total || 0).toFixed(2)].map(escape).join(','));
    lines.push(['Fark', (t.difference_total || 0).toFixed(2)].map(escape).join(','));
    lines.push(['Islem sayisi', t.transaction_count || 0].map(escape).join(','));
    lines.push('');
    lines.push(['YONTEM BAZINDA', 'Giris', 'Cikis', 'Net', 'Adet'].map(escape).join(','));
    Object.entries(periodData.by_method || {}).forEach(([m, v]) =>
      lines.push([m, (v.in || 0).toFixed(2), (v.out || 0).toFixed(2), (v.net || 0).toFixed(2), v.count || 0].map(escape).join(',')));
    lines.push('');
    lines.push(['TIP BAZINDA', 'Giris', 'Cikis', 'Adet'].map(escape).join(','));
    Object.entries(periodData.by_type || {}).forEach(([ty, v]) =>
      lines.push([ty, (v.in || 0).toFixed(2), (v.out || 0).toFixed(2), v.count || 0].map(escape).join(',')));
    lines.push('');
    lines.push(['KASIYER BAZINDA', 'Vardiya', 'Nakit Giris', 'Nakit Cikis', 'Islem'].map(escape).join(','));
    Object.entries(periodData.by_cashier || {}).forEach(([k, v]) =>
      lines.push([v.name || k, v.shift_count || 0, (v.cash_in || 0).toFixed(2), (v.cash_out || 0).toFixed(2), v.transaction_count || 0].map(escape).join(',')));
    lines.push('');
    lines.push(['DOVIZ BAZINDA', 'Giris (TL)', 'Cikis (TL)', 'Giris (orj)', 'Cikis (orj)', 'Adet'].map(escape).join(','));
    Object.entries(periodData.by_currency || {}).forEach(([cur, v]) =>
      lines.push([cur, (v.in_try || 0).toFixed(2), (v.out_try || 0).toFixed(2), (v.in_original || 0).toFixed(2), (v.out_original || 0).toFixed(2), v.count || 0].map(escape).join(',')));

    const csv = '\uFEFF' + lines.join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `donem-raporu-${periodData.start_date}_${periodData.end_date}.csv`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success('CSV indirildi');
  };

  const openXReport = async () => {
    setReportLoading(true);
    try {
      const res = await axios.get('/cashier/x-report');
      setReportData(res.data);
      setShowReportDialog(true);
    } catch (e) {
      toast.error('Rapor alınamadı: ' + (e.response?.data?.detail || e.message));
    }
    setReportLoading(false);
  };

  const openZReport = async (shiftId) => {
    setReportLoading(true);
    try {
      const res = await axios.get(`/cashier/z-report/${shiftId}`);
      setReportData(res.data);
      setShowReportDialog(true);
    } catch (e) {
      toast.error('Rapor alınamadı: ' + (e.response?.data?.detail || e.message));
    }
    setReportLoading(false);
  };

  const cashInTotal = transactions.filter(t => t.direction === 'in' && t.method === 'cash').reduce((s, t) => s + (t.amount || 0), 0);
  const cashOutTotal = transactions.filter(t => t.direction === 'out' && t.method === 'cash').reduce((s, t) => s + (t.amount || 0), 0);
  const cardCount = transactions.filter(t => t.method === 'card').length;
  const cardTotal = transactions.filter(t => t.method === 'card').reduce((s, t) => s + (t.amount || 0), 0);
  const countedTotal = calcTotal(closingCounts);
  const expectedCash = shift ? (shift.opening_amount || 0) + cashInTotal - cashOutTotal : 0;
  const difference = countedTotal - expectedCash;

  const txnTypeLabel = (type) => {
    const map = {
      folio_payment: 'Folio ödemesi',
      paid_out: 'Kasa çıkışı',
      manual_in: 'Manuel giriş',
      manual_out: 'Manuel çıkış',
      refund: 'İade',
      bank_deposit: 'Banka yatırma',
    };
    return map[type] || 'İşlem';
  };

  const methodLabel = (m) => {
    const map = { cash: 'Nakit', card: 'Kart', bank_transfer: 'Havale', online: 'Online' };
    return map[m] || m;
  };

  const filteredTransactions = useMemo(() => {
    const q = txnSearch.trim().toLowerCase();
    return transactions.filter(t => {
      if (txnMethodFilter !== 'all' && t.method !== txnMethodFilter) return false;
      if (!q) return true;
      const haystack = [
        t.description, txnTypeLabel(t.type), methodLabel(t.method),
        t.created_by_name, t.ref_id, String(t.amount || '')
      ].join(' ').toLowerCase();
      return haystack.includes(q);
    });
  }, [transactions, txnSearch, txnMethodFilter]);

  const exportTransactionsCsv = () => {
    if (!filteredTransactions.length) { toast.error('Dışa aktarılacak işlem yok'); return; }
    const header = ['Saat', 'Tip', 'Yon', 'Yontem', 'Aciklama', 'Tutar', 'Kullanici', 'Ref'];
    const escape = (v) => {
      let s = (v ?? '').toString();
      // Formula injection guard — Excel/Sheets formula triggers
      if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
      s = s.replace(/"/g, '""');
      return /[",\n;]/.test(s) ? `"${s}"` : s;
    };
    const rows = filteredTransactions.map(t => [
      (t.timestamp || t.created_at || '').slice(0, 19).replace('T', ' '),
      txnTypeLabel(t.type),
      t.direction === 'in' ? 'Giris' : 'Cikis',
      methodLabel(t.method),
      t.description || '',
      (t.amount || 0).toFixed(2),
      t.created_by_name || '',
      t.ref_id || '',
    ].map(escape).join(','));
    const csv = '\uFEFF' + [header.join(','), ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const stamp = new Date().toISOString().slice(0, 16).replace(/[T:]/g, '-');
    a.href = url; a.download = `vardiya-islemler-${stamp}.csv`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success('CSV indirildi');
  };

  const printReport = () => {
    if (typeof window !== 'undefined') window.print();
  };

  const DenominationGrid = ({ counts, setCounts }) => (
    <div className="grid grid-cols-2 gap-3">
      {[
        ['cash_200', '200 TL'], ['cash_100', '100 TL'], ['cash_50', '50 TL'],
        ['cash_20', '20 TL'], ['cash_10', '10 TL'], ['cash_5', '5 TL'],
        ['cash_1', '1 TL'], ['coin_1', '1 TL (Bozuk)'],
        ['coin_050', '50 Krş'], ['coin_025', '25 Krş']
      ].map(([key, label]) => (
        <div key={key} className="flex items-center gap-2">
          <Label className="w-24 text-xs">{label}</Label>
          <Input type="number" min="0" className="h-8 text-xs"
            value={counts[key]} onChange={e => setCounts(p => ({ ...p, [key]: parseInt(e.target.value) || 0 }))} />
        </div>
      ))}
    </div>
  );

  const statusLabel = (s) => {
    if (s === 'open') return <Badge className="bg-emerald-100 text-emerald-700">{t('cm.components_pms_CashierTab.acik')}</Badge>;
    if (s === 'handed_over') return <Badge className="bg-blue-100 text-blue-700">Devredildi</Badge>;
    return <Badge className="bg-gray-100 text-gray-600">{t('cm.components_pms_CashierTab.kapali')}</Badge>;
  };

  const closingDisabled =
    loading ||
    (Math.abs(difference) >= DIFF_THRESHOLD && !closingNote.trim());

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center flex-wrap gap-2">
        <h2 className="text-2xl font-semibold flex items-center gap-2">
          <Wallet className="w-6 h-6" /> {t('cm.components_pms_CashierTab.kasa_yonetimi')}
        </h2>
        <div className="flex gap-2 flex-wrap">
          {!shift ? (
            <Button onClick={() => setShowOpenDialog(true)} className="bg-emerald-600 hover:bg-emerald-700">
              <LogIn className="w-4 h-4 mr-2" /> {t('cm.components_pms_CashierTab.vardiya_ac')}
            </Button>
          ) : (
            <>
              <Button onClick={() => setShowCashInDialog(true)} variant="outline" className="border-emerald-300 text-emerald-700 hover:bg-emerald-50">
                <Plus className="w-4 h-4 mr-2" /> {t('cm.components_pms_CashierTab.nakit_giris')}
              </Button>
              <Button onClick={() => setShowPaidOutDialog(true)} variant="outline" className="border-amber-300 text-amber-700 hover:bg-amber-50">
                <Minus className="w-4 h-4 mr-2" /> {t('cm.components_pms_CashierTab.kasa_cikisi')}
              </Button>
              <Button onClick={() => setShowBankDepositDialog(true)} variant="outline" className="border-indigo-300 text-indigo-700 hover:bg-indigo-50">
                <Landmark className="w-4 h-4 mr-2" /> Banka Yat
              </Button>
              <Button onClick={openXReport} disabled={reportLoading} variant="outline" className="border-indigo-300 text-indigo-700 hover:bg-indigo-50">
                <FileText className="w-4 h-4 mr-2" /> X-Raporu
              </Button>
              <Button onClick={() => setShowHandoverDialog(true)} variant="outline" className="border-blue-300 text-blue-700 hover:bg-blue-50">
                <Users className="w-4 h-4 mr-2" /> Devret
              </Button>
              <Button onClick={() => setShowCloseDialog(true)} variant="destructive">
                <LogOut className="w-4 h-4 mr-2" /> {t('cm.components_pms_CashierTab.vardiya_kapat')}
              </Button>
            </>
          )}
          <Button onClick={() => setShowPeriodReportDialog(true)} variant="outline" className="border-slate-300 text-slate-700 hover:bg-slate-50">
            <CalendarRange className="w-4 h-4 mr-2" /> {t('cm.components_pms_CashierTab.donem_raporu')}
          </Button>
          <Button variant="outline" onClick={() => { loadShift(); loadHistory(); }}>
            <RefreshCw className="w-4 h-4 mr-2" /> {t('cm.components_pms_CashierTab.yenile')}
          </Button>
        </div>
      </div>

      {shift ? (
        <>
          <Card className="border-emerald-200 bg-emerald-50/30">
            <CardContent className="p-4">
              <div className="flex items-center gap-3 text-sm">
                <UserCheck className="w-5 h-5 text-emerald-600" />
                <div>
                  <span className="font-medium text-emerald-800">{t('cm.components_pms_CashierTab.aktif_vardiya')}</span>
                  <span className="text-emerald-600 mx-2">|</span>
                  <span className="text-emerald-700">{t('cm.components_pms_CashierTab.acan')} <strong>{shift.opened_by_name || shift.cashier_name || shift.cashier_email}</strong></span>
                  <span className="text-emerald-600 mx-2">|</span>
                  <span className="text-emerald-700">{t('cm.components_pms_CashierTab.baslangic')} {shift.opened_at?.slice(0, 16).replace('T', ' ')}</span>
                  {shift.handover_from_name && (
                    <>
                      <span className="text-emerald-600 mx-2">|</span>
                      <span className="text-blue-600">Devreden: <strong>{shift.handover_from_name}</strong></span>
                    </>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <Card className="bg-emerald-50 border-emerald-200">
              <CardContent className="p-3">
                <p className="text-xs text-emerald-600">{t('cm.components_pms_CashierTab.acilis_tutari')}</p>
                <p className="text-lg font-bold text-emerald-700">{(shift.opening_amount || 0).toFixed(2)} TL</p>
              </CardContent>
            </Card>
            <Card className="bg-blue-50 border-blue-200">
              <CardContent className="p-3">
                <p className="text-xs text-blue-600">{t('cm.components_pms_CashierTab.nakit_giris_f1615')}</p>
                <p className="text-lg font-bold text-blue-700">{cashInTotal.toFixed(2)} TL</p>
              </CardContent>
            </Card>
            <Card className="bg-amber-50 border-amber-200">
              <CardContent className="p-3">
                <p className="text-xs text-amber-600">{t('cm.components_pms_CashierTab.nakit_cikis')}</p>
                <p className="text-lg font-bold text-amber-700">{cashOutTotal.toFixed(2)} TL</p>
              </CardContent>
            </Card>
            <Card className="bg-indigo-50 border-indigo-200">
              <CardContent className="p-3">
                <p className="text-xs text-indigo-600">{t('cm.components_pms_CashierTab.kredi_karti')}</p>
                <p className="text-lg font-bold text-indigo-700">{cardTotal.toFixed(2)} TL</p>
                <p className="text-[10px] text-indigo-500">{cardCount} {t('cm.components_pms_CashierTab.islem')}</p>
              </CardContent>
            </Card>
            <Card className="bg-gray-50 border-gray-200">
              <CardContent className="p-3">
                <p className="text-xs text-gray-600">Beklenen Kasa</p>
                <p className="text-lg font-bold text-gray-800">{expectedCash.toFixed(2)} TL</p>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Receipt className="w-4 h-4" /> {t('cm.components_pms_CashierTab.vardiya_islemleri')}{filteredTransactions.length}/{transactions.length})
                </CardTitle>
                <div className="flex gap-2 items-center flex-wrap">
                  <div className="relative">
                    <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
                    <Input
                      value={txnSearch}
                      onChange={(e) => setTxnSearch(e.target.value)}
                      placeholder={t('cm.components_pms_CashierTab.ara')}
                      className="h-8 text-xs pl-7 w-44"
                    />
                  </div>
                  <Select value={txnMethodFilter} onValueChange={setTxnMethodFilter}>
                    <SelectTrigger className="h-8 w-32 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">{t('cm.components_pms_CashierTab.tum_yontemler')}</SelectItem>
                      <SelectItem value="cash">Nakit</SelectItem>
                      <SelectItem value="card">Kart</SelectItem>
                      <SelectItem value="bank_transfer">Havale</SelectItem>
                      <SelectItem value="online">Online</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button size="sm" variant="outline" className="h-8 text-xs" onClick={exportTransactionsCsv}>
                    <FileDown className="w-3.5 h-3.5 mr-1" /> CSV
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {filteredTransactions.length === 0 ? (
                <p className="text-sm text-gray-400 py-4 text-center">
                  {transactions.length === 0 ? 'Henüz işlem yok' : 'Filtreye uyan işlem yok'}
                </p>
              ) : (
                <div className="max-h-[400px] overflow-y-auto space-y-1">
                  {filteredTransactions.map((t, i) => (
                    <div key={t.id || i} className="flex items-center justify-between p-2 rounded border border-gray-100 hover:bg-gray-50 text-xs">
                      <div className="flex items-center gap-2">
                        {t.direction === 'in' ? <DollarSign className="w-3.5 h-3.5 text-emerald-500" /> : <ArrowRightLeft className="w-3.5 h-3.5 text-red-500" />}
                        <span className="text-gray-700">{t.description || txnTypeLabel(t.type)}</span>
                        <Badge variant="outline" className="text-[10px]">{methodLabel(t.method)}</Badge>
                        {t.created_by_name && (
                          <span className="text-[10px] text-gray-400">· {t.created_by_name}</span>
                        )}
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-gray-400">{(t.timestamp || t.created_at || '').slice(11, 16)}</span>
                        <span className={`font-medium ${t.direction === 'in' ? 'text-emerald-600' : 'text-red-600'}`}>
                          {t.direction === 'in' ? '+' : '-'}{(t.amount || 0).toFixed(2)} TL
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </>
      ) : (
        <Card className="border-dashed border-2 border-gray-300">
          <CardContent className="py-12 text-center">
            <Wallet className="w-12 h-12 mx-auto mb-4 text-gray-300" />
            <p className="text-gray-500 text-lg mb-2">{t('cm.components_pms_CashierTab.aktif_vardiya_yok')}</p>
            <p className="text-gray-400 text-sm mb-4">{t('cm.components_pms_CashierTab.islem_yapabilmek_icin_vardiya_acmaniz_ge')}</p>
            <Button onClick={() => setShowOpenDialog(true)} className="bg-emerald-600 hover:bg-emerald-700">
              <LogIn className="w-4 h-4 mr-2" /> {t('cm.components_pms_CashierTab.vardiya_ac_4889c')}
            </Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Clock className="w-4 h-4" /> {t('cm.components_pms_CashierTab.gecmis_vardiyalar')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {shiftHistory.length === 0 ? (
            <p className="text-sm text-gray-400 py-4 text-center">{t('cm.components_pms_CashierTab.gecmis_vardiya_bulunamadi')}</p>
          ) : (
            <div className="space-y-2">
              {shiftHistory.map((s, i) => (
                <div key={s.id || i} className="p-3 rounded-lg border border-gray-200 text-xs">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`w-2 h-2 rounded-full ${s.status === 'open' ? 'bg-emerald-500' : s.status === 'handed_over' ? 'bg-blue-500' : 'bg-gray-400'}`} />
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-gray-700 font-medium">{s.cashier_name || s.cashier_email || 'Kasiyer'}</span>
                          {statusLabel(s.status)}
                        </div>
                        <p className="text-gray-400 mt-0.5">{s.opened_at?.slice(0, 16).replace('T', ' ')} - {s.closed_at?.slice(11, 16) || 'Açık'}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <p className="text-gray-500">{t('cm.components_pms_CashierTab.acilis')} {(s.opening_amount || 0).toFixed(2)}</p>
                        <p className="text-gray-500">{t('cm.components_pms_CashierTab.kapanis')} {(s.closing_amount || 0).toFixed(2)}</p>
                      </div>
                      {s.difference != null && (
                        <Badge className={Math.abs(s.difference) < 0.01 ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}>
                          {Math.abs(s.difference) < 0.01 ? 'Tam' : `Fark: ${s.difference.toFixed(2)}`}
                        </Badge>
                      )}
                      {s.status !== 'open' && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 text-[11px] border-indigo-300 text-indigo-700 hover:bg-indigo-50"
                          onClick={() => openZReport(s.id)}
                          disabled={reportLoading}
                        >
                          <FileText className="w-3 h-3 mr-1" /> Z-Rapor
                        </Button>
                      )}
                    </div>
                  </div>
                  <div className="mt-2 pt-2 border-t border-gray-100 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-gray-500">
                    {s.opened_by_name && <span>{t('cm.components_pms_CashierTab.acan_4b8cd')} <strong className="text-gray-700">{s.opened_by_name}</strong></span>}
                    {s.closed_by_name && <span>Kapatan: <strong className="text-gray-700">{s.closed_by_name}</strong></span>}
                    {s.handover_to_name && (
                      <span className="text-blue-600">Devredilen: <strong>{s.handover_to_name}</strong></span>
                    )}
                    {s.handover_from_name && (
                      <span className="text-blue-600">Devreden: <strong>{s.handover_from_name}</strong></span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={showOpenDialog} onOpenChange={setShowOpenDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><LogIn className="w-5 h-5" /> {t('cm.components_pms_CashierTab.vardiya_ac_4889c')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label>{t('cm.components_pms_CashierTab.acilis_tutari_tl')}</Label>
              <Input type="number" value={openingAmount} onChange={e => setOpeningAmount(e.target.value)} placeholder="0.00" />
              <p className="text-xs text-gray-400 mt-1">{t('cm.components_pms_CashierTab.kasadaki_mevcut_nakit_miktarini_girin')}</p>
            </div>
            <Button onClick={openShift} disabled={loading} className="w-full bg-emerald-600 hover:bg-emerald-700">
              {loading ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <LogIn className="w-4 h-4 mr-2" />}
              {t('cm.components_pms_CashierTab.vardiyayi_ac')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showCloseDialog} onOpenChange={setShowCloseDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Calculator className="w-5 h-5" /> {t('cm.components_pms_CashierTab.vardiya_kapat_kasa_sayimi')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <DenominationGrid counts={closingCounts} setCounts={setClosingCounts} />
            <div className="bg-gray-50 rounded-lg p-3 space-y-1">
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">{t('cm.components_pms_CashierTab.sayilan_tutar')}</span>
                <span className="font-bold">{countedTotal.toFixed(2)} TL</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">{t('cm.components_pms_CashierTab.beklenen_tutar')}</span>
                <span className="font-bold">{expectedCash.toFixed(2)} TL</span>
              </div>
              <div className={`flex justify-between text-sm pt-1 border-t ${Math.abs(difference) < 0.01 ? 'text-emerald-600' : 'text-red-600'}`}>
                <span>Fark:</span>
                <span className="font-bold">{difference.toFixed(2)} TL</span>
              </div>
            </div>
            {Math.abs(difference) >= DIFF_THRESHOLD && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-red-600 mt-0.5 flex-shrink-0" />
                <p className="text-xs text-red-700">
                  Fark {DIFF_THRESHOLD} {t('cm.components_pms_CashierTab.tl_yi_asti_kapatabilmek_icin_asagiya_aci')}
                </p>
              </div>
            )}
            <div>
              <Label>
                Not {Math.abs(difference) >= DIFF_THRESHOLD && <span className="text-red-600">*</span>}
              </Label>
              <Textarea
                value={closingNote}
                onChange={e => setClosingNote(e.target.value)}
                placeholder={Math.abs(difference) >= DIFF_THRESHOLD ? 'Fark açıklaması zorunlu' : 'Vardiya notu (opsiyonel)'}
                rows={2}
              />
            </div>
            <Button onClick={closeShift} disabled={closingDisabled} className="w-full" variant="destructive">
              {loading ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <LogOut className="w-4 h-4 mr-2" />}
              {t('cm.components_pms_CashierTab.vardiyayi_kapat')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showHandoverDialog} onOpenChange={setShowHandoverDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Users className="w-5 h-5 text-blue-600" /> Vardiya Devret</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="bg-blue-50 rounded-lg p-3 text-sm text-blue-700">
              {t('cm.components_pms_CashierTab.vardiyayi_devralacak_kisi_kendi_e_posta_')}
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Mevcut Kasa:</span>
                <span className="font-bold">{expectedCash.toFixed(2)} TL</span>
              </div>
            </div>
            <div className="border rounded-lg p-4 space-y-3">
              <p className="text-xs font-semibold text-gray-500 uppercase">{t('cm.components_pms_CashierTab.devralacak_kisi_girisi')}</p>
              <div>
                <Label>E-posta *</Label>
                <Input type="email" value={handoverTarget.email} onChange={e => setHandoverTarget(p => ({ ...p, email: e.target.value }))} placeholder="kullanici@hotel.com" />
              </div>
              <div>
                <Label>{t('cm.components_pms_CashierTab.sifre')}</Label>
                <Input type="password" value={handoverTarget.password} onChange={e => setHandoverTarget(p => ({ ...p, password: e.target.value }))} placeholder={t('cm.components_pms_CashierTab.sifrenizi_girin')} />
              </div>
            </div>
            <div>
              <Label>Devir Notu</Label>
              <Input value={handoverTarget.note} onChange={e => setHandoverTarget(p => ({ ...p, note: e.target.value }))} placeholder="Devir notu (opsiyonel)" />
            </div>
            <Button onClick={handoverShift} disabled={loading || !handoverTarget.email.trim() || !handoverTarget.password.trim()} className="w-full bg-blue-600 hover:bg-blue-700">
              {loading ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Users className="w-4 h-4 mr-2" />}
              {t('cm.components_pms_CashierTab.onayla_ve_devret')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showCashInDialog} onOpenChange={(o) => { setShowCashInDialog(o); if (!o) setManualTxn({ amount: '', method: 'cash', description: '', currency: 'TRY', fx_rate: '1' }); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Plus className="w-5 h-5 text-emerald-600" /> {t('cm.components_pms_CashierTab.nakit_giris_ekle')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <p className="text-xs text-gray-500">{t('cm.components_pms_CashierTab.folio_disi_nakit_girisleri_avans_depozit')}</p>
            <div className="grid grid-cols-3 gap-2">
              <div className="col-span-2">
                <Label>{t('cm.components_pms_CashierTab.tutar')}</Label>
                <Input type="number" step="0.01" value={manualTxn.amount} onChange={e => setManualTxn(p => ({ ...p, amount: e.target.value }))} placeholder="0.00" />
              </div>
              <div>
                <Label>Para Birimi</Label>
                <Select value={manualTxn.currency} onValueChange={v => setManualTxn(p => ({ ...p, currency: v, fx_rate: v === 'TRY' ? '1' : p.fx_rate }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {CURRENCIES.map(c => <SelectItem key={c.code} value={c.code}>{c.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {manualTxn.currency !== 'TRY' && (
              <div>
                <Label>Kur (1 {manualTxn.currency} = ? TL) *</Label>
                <Input type="number" step="0.0001" value={manualTxn.fx_rate} onChange={e => setManualTxn(p => ({ ...p, fx_rate: e.target.value }))} placeholder={t('cm.components_pms_CashierTab.orn_32_50')} />
                {parseFloat(manualTxn.amount) > 0 && parseFloat(manualTxn.fx_rate) > 0 && (
                  <p className="text-[11px] text-gray-500 mt-1">{t('cm.components_pms_CashierTab.tl_karsiligi')} <strong>{(parseFloat(manualTxn.amount) * parseFloat(manualTxn.fx_rate)).toFixed(2)} TL</strong></p>
                )}
              </div>
            )}
            <div>
              <Label>{t('cm.components_pms_CashierTab.yontem')}</Label>
              <Select value={manualTxn.method} onValueChange={v => setManualTxn(p => ({ ...p, method: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="cash">Nakit</SelectItem>
                  <SelectItem value="card">Kart</SelectItem>
                  <SelectItem value="bank_transfer">Havale</SelectItem>
                  <SelectItem value="online">Online</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('cm.components_pms_CashierTab.aciklama')}</Label>
              <Textarea value={manualTxn.description} onChange={e => setManualTxn(p => ({ ...p, description: e.target.value }))} placeholder={t('cm.components_pms_CashierTab.orn_depozito_iadesi_kasa_avansi')} rows={2} />
            </div>
            <Button onClick={() => submitManual('in')} disabled={loading} className="w-full bg-emerald-600 hover:bg-emerald-700">
              {loading ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
              {t('cm.components_pms_CashierTab.girisi_kaydet')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showPaidOutDialog} onOpenChange={(o) => { setShowPaidOutDialog(o); if (!o) setManualTxn({ amount: '', method: 'cash', description: '', currency: 'TRY', fx_rate: '1' }); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Minus className="w-5 h-5 text-amber-600" /> {t('cm.components_pms_CashierTab.kasa_cikisi_ekle')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <p className="text-xs text-gray-500">{t('cm.components_pms_CashierTab.kasadan_cikan_nakit_tedarikci_kucuk_gide')}</p>
            <div className="grid grid-cols-3 gap-2">
              <div className="col-span-2">
                <Label>{t('cm.components_pms_CashierTab.tutar_2e782')}</Label>
                <Input type="number" step="0.01" value={manualTxn.amount} onChange={e => setManualTxn(p => ({ ...p, amount: e.target.value }))} placeholder="0.00" />
              </div>
              <div>
                <Label>Para Birimi</Label>
                <Select value={manualTxn.currency} onValueChange={v => setManualTxn(p => ({ ...p, currency: v, fx_rate: v === 'TRY' ? '1' : p.fx_rate }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {CURRENCIES.map(c => <SelectItem key={c.code} value={c.code}>{c.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {manualTxn.currency !== 'TRY' && (
              <div>
                <Label>Kur (1 {manualTxn.currency} = ? TL) *</Label>
                <Input type="number" step="0.0001" value={manualTxn.fx_rate} onChange={e => setManualTxn(p => ({ ...p, fx_rate: e.target.value }))} placeholder={t('cm.components_pms_CashierTab.orn_32_50_1bd02')} />
                {parseFloat(manualTxn.amount) > 0 && parseFloat(manualTxn.fx_rate) > 0 && (
                  <p className="text-[11px] text-gray-500 mt-1">{t('cm.components_pms_CashierTab.tl_karsiligi_a59f8')} <strong>{(parseFloat(manualTxn.amount) * parseFloat(manualTxn.fx_rate)).toFixed(2)} TL</strong></p>
                )}
              </div>
            )}
            <div>
              <Label>{t('cm.components_pms_CashierTab.yontem_139df')}</Label>
              <Select value={manualTxn.method} onValueChange={v => setManualTxn(p => ({ ...p, method: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="cash">Nakit</SelectItem>
                  <SelectItem value="bank_transfer">Havale</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{t('cm.components_pms_CashierTab.aciklama_bdb34')}</Label>
              <Textarea value={manualTxn.description} onChange={e => setManualTxn(p => ({ ...p, description: e.target.value }))} placeholder={t('cm.components_pms_CashierTab.orn_tedarikci_odemesi_kucuk_gider')} rows={2} />
            </div>
            <Button onClick={() => submitManual('out')} disabled={loading} className="w-full bg-amber-600 hover:bg-amber-700">
              {loading ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Minus className="w-4 h-4 mr-2" />}
              {t('cm.components_pms_CashierTab.cikisi_kaydet')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showReportDialog} onOpenChange={(o) => { if (!o) { setShowReportDialog(false); setReportData(null); } }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto print:max-w-full print:overflow-visible">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="w-5 h-5" />
              {reportData?.report_type === 'Z' ? 'Z-Raporu (Kapanış)' : 'X-Raporu (Ara Rapor)'}
            </DialogTitle>
          </DialogHeader>
          {reportData && (
            <div className="space-y-4 text-sm" id="cashier-report">
              <div className="grid grid-cols-2 gap-3 p-3 bg-gray-50 rounded-lg text-xs">
                <div><span className="text-gray-500">Kasiyer:</span> <strong>{reportData.cashier_name || reportData.cashier_email || '-'}</strong></div>
                <div><span className="text-gray-500">{t('cm.components_pms_CashierTab.durum')}</span> <strong>{reportData.status === 'open' ? 'Açık' : reportData.status === 'handed_over' ? 'Devredildi' : 'Kapalı'}</strong></div>
                <div><span className="text-gray-500">{t('cm.components_pms_CashierTab.acilis_a2719')}</span> {reportData.opened_at?.slice(0, 16).replace('T', ' ') || '-'}</div>
                <div><span className="text-gray-500">{t('cm.components_pms_CashierTab.kapanis_d60bf')}</span> {reportData.closed_at?.slice(0, 16).replace('T', ' ') || 'Açık'}</div>
                <div><span className="text-gray-500">{t('cm.components_pms_CashierTab.rapor_zamani')}</span> {reportData.generated_at?.slice(0, 16).replace('T', ' ') || '-'}</div>
                <div><span className="text-gray-500">Raporu Alan:</span> {reportData.generated_by || '-'}</div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                <div className="p-3 rounded bg-emerald-50 border border-emerald-200">
                  <p className="text-[10px] text-emerald-600 uppercase">{t('cm.components_pms_CashierTab.acilis_3245e')}</p>
                  <p className="text-base font-bold text-emerald-700">{(reportData.opening_amount || 0).toFixed(2)} TL</p>
                </div>
                <div className="p-3 rounded bg-blue-50 border border-blue-200">
                  <p className="text-[10px] text-blue-600 uppercase">{t('cm.components_pms_CashierTab.nakit_giris_f1615')}</p>
                  <p className="text-base font-bold text-blue-700">{(reportData.cash_in || 0).toFixed(2)} TL</p>
                </div>
                <div className="p-3 rounded bg-amber-50 border border-amber-200">
                  <p className="text-[10px] text-amber-600 uppercase">{t('cm.components_pms_CashierTab.nakit_cikis_a878e')}</p>
                  <p className="text-base font-bold text-amber-700">{(reportData.cash_out || 0).toFixed(2)} TL</p>
                </div>
                <div className="p-3 rounded bg-gray-100 border border-gray-300">
                  <p className="text-[10px] text-gray-600 uppercase">Beklenen</p>
                  <p className="text-base font-bold text-gray-800">{(reportData.expected_amount || 0).toFixed(2)} TL</p>
                </div>
              </div>

              {reportData.report_type === 'Z' && reportData.closing_amount != null && (
                <div className="grid grid-cols-2 gap-2">
                  <div className="p-3 rounded bg-indigo-50 border border-indigo-200">
                    <p className="text-[10px] text-indigo-600 uppercase">{t('cm.components_pms_CashierTab.sayilan_kapanis')}</p>
                    <p className="text-base font-bold text-indigo-700">{(reportData.closing_amount || 0).toFixed(2)} TL</p>
                  </div>
                  <div className={`p-3 rounded border ${Math.abs(reportData.difference || 0) < 0.01 ? 'bg-emerald-50 border-emerald-200' : 'bg-red-50 border-red-200'}`}>
                    <p className={`text-[10px] uppercase ${Math.abs(reportData.difference || 0) < 0.01 ? 'text-emerald-600' : 'text-red-600'}`}>Fark</p>
                    <p className={`text-base font-bold ${Math.abs(reportData.difference || 0) < 0.01 ? 'text-emerald-700' : 'text-red-700'}`}>
                      {(reportData.difference || 0).toFixed(2)} TL
                    </p>
                  </div>
                </div>
              )}

              <div>
                <p className="text-xs font-semibold text-gray-600 mb-2">{t('cm.components_pms_CashierTab.yontem_bazinda_ozet')}</p>
                <div className="border rounded-lg overflow-hidden">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="text-left px-3 py-2">{t('cm.components_pms_CashierTab.yontem_139df')}</th>
                        <th className="text-right px-3 py-2">{t('cm.components_pms_CashierTab.giris')}</th>
                        <th className="text-right px-3 py-2">{t('cm.components_pms_CashierTab.cikis')}</th>
                        <th className="text-right px-3 py-2">Net</th>
                        <th className="text-right px-3 py-2">Adet</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(reportData.by_method || {}).length === 0 ? (
                        <tr><td colSpan={5} className="px-3 py-3 text-center text-gray-400">{t('cm.components_pms_CashierTab.kayit_yok')}</td></tr>
                      ) : Object.entries(reportData.by_method).map(([m, v]) => (
                        <tr key={m} className="border-t">
                          <td className="px-3 py-2">{methodLabel(m)}</td>
                          <td className="px-3 py-2 text-right text-emerald-600">{(v.in || 0).toFixed(2)}</td>
                          <td className="px-3 py-2 text-right text-red-600">{(v.out || 0).toFixed(2)}</td>
                          <td className="px-3 py-2 text-right font-medium">{(v.net || 0).toFixed(2)}</td>
                          <td className="px-3 py-2 text-right text-gray-500">{v.count || 0}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div>
                <p className="text-xs font-semibold text-gray-600 mb-2">{t('cm.components_pms_CashierTab.islem_tipi_bazinda')}</p>
                <div className="border rounded-lg overflow-hidden">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="text-left px-3 py-2">Tip</th>
                        <th className="text-right px-3 py-2">{t('cm.components_pms_CashierTab.giris_1ffbd')}</th>
                        <th className="text-right px-3 py-2">{t('cm.components_pms_CashierTab.cikis_b9015')}</th>
                        <th className="text-right px-3 py-2">Adet</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(reportData.by_type || {}).length === 0 ? (
                        <tr><td colSpan={4} className="px-3 py-3 text-center text-gray-400">{t('cm.components_pms_CashierTab.kayit_yok_546b8')}</td></tr>
                      ) : Object.entries(reportData.by_type).map(([ty, v]) => (
                        <tr key={ty} className="border-t">
                          <td className="px-3 py-2">{txnTypeLabel(ty)}</td>
                          <td className="px-3 py-2 text-right text-emerald-600">{(v.in || 0).toFixed(2)}</td>
                          <td className="px-3 py-2 text-right text-red-600">{(v.out || 0).toFixed(2)}</td>
                          <td className="px-3 py-2 text-right text-gray-500">{v.count || 0}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="text-[11px] text-gray-500 text-center pt-3 border-t">
                {t('cm.components_pms_CashierTab.toplam')} {reportData.transaction_count || 0} {t('cm.components_pms_CashierTab.islem_9d951')}
              </div>

              <div className="flex justify-end gap-2 print:hidden">
                <Button variant="outline" onClick={() => { setShowReportDialog(false); setReportData(null); }}>
                  {t('cm.components_pms_CashierTab.kapat')}
                </Button>
                <Button onClick={printReport} className="bg-indigo-600 hover:bg-indigo-700">
                  <Printer className="w-4 h-4 mr-2" /> {t('cm.components_pms_CashierTab.yazdir')}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={showBankDepositDialog} onOpenChange={(o) => { setShowBankDepositDialog(o); if (!o) setBankDeposit({ amount: '', bank_name: '', account_no: '', reference: '', note: '' }); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Landmark className="w-5 h-5 text-indigo-600" /> {t('cm.components_pms_CashierTab.bankaya_yatirma')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <p className="text-xs text-gray-500">{t('cm.components_pms_CashierTab.kasadan_bankaya_nakit_yatirma_aktif_vard')}</p>
            <div>
              <Label>{t('cm.components_pms_CashierTab.tutar_tl')}</Label>
              <Input type="number" step="0.01" value={bankDeposit.amount} onChange={e => setBankDeposit(p => ({ ...p, amount: e.target.value }))} placeholder="0.00" />
            </div>
            <div>
              <Label>{t('cm.components_pms_CashierTab.banka_adi')}</Label>
              <Input value={bankDeposit.bank_name} onChange={e => setBankDeposit(p => ({ ...p, bank_name: e.target.value }))} placeholder={t('cm.components_pms_CashierTab.orn_garanti_bbva')} />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label>Hesap / IBAN</Label>
                <Input value={bankDeposit.account_no} onChange={e => setBankDeposit(p => ({ ...p, account_no: e.target.value }))} placeholder="opsiyonel" />
              </div>
              <div>
                <Label>Dekont / Ref</Label>
                <Input value={bankDeposit.reference} onChange={e => setBankDeposit(p => ({ ...p, reference: e.target.value }))} placeholder="opsiyonel" />
              </div>
            </div>
            <div>
              <Label>Not</Label>
              <Textarea value={bankDeposit.note} onChange={e => setBankDeposit(p => ({ ...p, note: e.target.value }))} placeholder="opsiyonel" rows={2} />
            </div>
            <Button onClick={submitBankDeposit} disabled={loading} className="w-full bg-indigo-600 hover:bg-indigo-700">
              {loading ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Landmark className="w-4 h-4 mr-2" />}
              {t('cm.components_pms_CashierTab.yatirmayi_kaydet')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showPeriodReportDialog} onOpenChange={(o) => { setShowPeriodReportDialog(o); if (!o) setPeriodData(null); }}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto print:max-w-full print:overflow-visible">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><CalendarRange className="w-5 h-5" /> {t('cm.components_pms_CashierTab.donem_raporu_d2bb7')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 text-sm" id="period-report">
            <div className="flex items-end gap-2 flex-wrap print:hidden">
              <div>
                <Label>{t('cm.components_pms_CashierTab.baslangic_677c8')}</Label>
                <Input type="date" value={periodRange.start} onChange={e => setPeriodRange(p => ({ ...p, start: e.target.value }))} />
              </div>
              <div>
                <Label>{t('cm.components_pms_CashierTab.bitis')}</Label>
                <Input type="date" value={periodRange.end} onChange={e => setPeriodRange(p => ({ ...p, end: e.target.value }))} />
              </div>
              <Button onClick={loadPeriodReport} disabled={periodLoading} className="bg-slate-700 hover:bg-slate-800">
                {periodLoading ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <CalendarRange className="w-4 h-4 mr-2" />}
                Getir
              </Button>
              {periodData && (
                <>
                  <Button variant="outline" onClick={exportPeriodCsv}>
                    <FileDown className="w-4 h-4 mr-2" /> CSV
                  </Button>
                  <Button variant="outline" onClick={printReport}>
                    <Printer className="w-4 h-4 mr-2" /> {t('cm.components_pms_CashierTab.yazdir_67197')}
                  </Button>
                </>
              )}
            </div>

            {periodData && (
              <>
                <div className="grid grid-cols-2 gap-3 p-3 bg-gray-50 rounded text-xs">
                  <div><span className="text-gray-500">{t('cm.components_pms_CashierTab.aralik')}</span> <strong>{periodData.start_date} → {periodData.end_date}</strong></div>
                  <div><span className="text-gray-500">Vardiya:</span> <strong>{periodData.totals?.shift_count || 0}</strong> ({periodData.totals?.open_shift_count || 0} {t('cm.components_pms_CashierTab.acik_e1734')}</div>
                  <div><span className="text-gray-500">{t('cm.components_pms_CashierTab.olusturuldu')}</span> {periodData.generated_at?.slice(0, 16).replace('T', ' ')}</div>
                  <div><span className="text-gray-500">Raporu Alan:</span> {periodData.generated_by || '-'}</div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  <div className="p-3 rounded bg-emerald-50 border border-emerald-200">
                    <p className="text-[10px] text-emerald-600 uppercase">{t('cm.components_pms_CashierTab.acilis_toplam')}</p>
                    <p className="text-base font-bold text-emerald-700">{(periodData.totals?.opening_total || 0).toFixed(2)} TL</p>
                  </div>
                  <div className="p-3 rounded bg-blue-50 border border-blue-200">
                    <p className="text-[10px] text-blue-600 uppercase">{t('cm.components_pms_CashierTab.nakit_giris_f1615')}</p>
                    <p className="text-base font-bold text-blue-700">{(periodData.totals?.cash_in_total || 0).toFixed(2)} TL</p>
                  </div>
                  <div className="p-3 rounded bg-amber-50 border border-amber-200">
                    <p className="text-[10px] text-amber-600 uppercase">{t('cm.components_pms_CashierTab.nakit_cikis_a878e')}</p>
                    <p className="text-base font-bold text-amber-700">{(periodData.totals?.cash_out_total || 0).toFixed(2)} TL</p>
                  </div>
                  <div className="p-3 rounded bg-gray-100 border border-gray-300">
                    <p className="text-[10px] text-gray-600 uppercase">Beklenen</p>
                    <p className="text-base font-bold text-gray-800">{(periodData.totals?.expected_total || 0).toFixed(2)} TL</p>
                  </div>
                  <div className="p-3 rounded bg-indigo-50 border border-indigo-200">
                    <p className="text-[10px] text-indigo-600 uppercase">{t('cm.components_pms_CashierTab.sayilan')}</p>
                    <p className="text-base font-bold text-indigo-700">{(periodData.totals?.closing_total || 0).toFixed(2)} TL</p>
                  </div>
                  <div className={`p-3 rounded border ${Math.abs(periodData.totals?.difference_total || 0) < 0.01 ? 'bg-emerald-50 border-emerald-200' : 'bg-red-50 border-red-200'}`}>
                    <p className={`text-[10px] uppercase ${Math.abs(periodData.totals?.difference_total || 0) < 0.01 ? 'text-emerald-600' : 'text-red-600'}`}>{t('cm.components_pms_CashierTab.fark_toplam')}</p>
                    <p className={`text-base font-bold ${Math.abs(periodData.totals?.difference_total || 0) < 0.01 ? 'text-emerald-700' : 'text-red-700'}`}>{(periodData.totals?.difference_total || 0).toFixed(2)} TL</p>
                  </div>
                  <div className="p-3 rounded bg-slate-50 border border-slate-200">
                    <p className="text-[10px] text-slate-600 uppercase">{t('cm.components_pms_CashierTab.islem_792e7')}</p>
                    <p className="text-base font-bold text-slate-700">{periodData.totals?.transaction_count || 0}</p>
                  </div>
                  <div className="p-3 rounded bg-slate-50 border border-slate-200">
                    <p className="text-[10px] text-slate-600 uppercase">{t('cm.components_pms_CashierTab.kapali_vardiya')}</p>
                    <p className="text-base font-bold text-slate-700">{periodData.totals?.closed_shift_count || 0}</p>
                  </div>
                </div>

                <div>
                  <p className="text-xs font-semibold text-gray-600 mb-2">{t('cm.components_pms_CashierTab.yontem_bazinda')}</p>
                  <div className="border rounded-lg overflow-hidden">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50">
                        <tr><th className="text-left px-3 py-2">{t('cm.components_pms_CashierTab.yontem_139df')}</th><th className="text-right px-3 py-2">{t('cm.components_pms_CashierTab.giris_1ffbd')}</th><th className="text-right px-3 py-2">{t('cm.components_pms_CashierTab.cikis_b9015')}</th><th className="text-right px-3 py-2">Net</th><th className="text-right px-3 py-2">Adet</th></tr>
                      </thead>
                      <tbody>
                        {Object.entries(periodData.by_method || {}).length === 0 ? (
                          <tr><td colSpan={5} className="px-3 py-3 text-center text-gray-400">{t('cm.components_pms_CashierTab.kayit_yok_546b8')}</td></tr>
                        ) : Object.entries(periodData.by_method).map(([m, v]) => (
                          <tr key={m} className="border-t">
                            <td className="px-3 py-2">{methodLabel(m)}</td>
                            <td className="px-3 py-2 text-right text-emerald-600">{(v.in || 0).toFixed(2)}</td>
                            <td className="px-3 py-2 text-right text-red-600">{(v.out || 0).toFixed(2)}</td>
                            <td className="px-3 py-2 text-right font-medium">{(v.net || 0).toFixed(2)}</td>
                            <td className="px-3 py-2 text-right text-gray-500">{v.count || 0}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div>
                  <p className="text-xs font-semibold text-gray-600 mb-2">{t('cm.components_pms_CashierTab.islem_tipi_bazinda_7bf40')}</p>
                  <div className="border rounded-lg overflow-hidden">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50">
                        <tr><th className="text-left px-3 py-2">Tip</th><th className="text-right px-3 py-2">{t('cm.components_pms_CashierTab.giris_1ffbd')}</th><th className="text-right px-3 py-2">{t('cm.components_pms_CashierTab.cikis_b9015')}</th><th className="text-right px-3 py-2">Adet</th></tr>
                      </thead>
                      <tbody>
                        {Object.entries(periodData.by_type || {}).length === 0 ? (
                          <tr><td colSpan={4} className="px-3 py-3 text-center text-gray-400">{t('cm.components_pms_CashierTab.kayit_yok_546b8')}</td></tr>
                        ) : Object.entries(periodData.by_type).map(([ty, v]) => (
                          <tr key={ty} className="border-t">
                            <td className="px-3 py-2">{txnTypeLabel(ty)}</td>
                            <td className="px-3 py-2 text-right text-emerald-600">{(v.in || 0).toFixed(2)}</td>
                            <td className="px-3 py-2 text-right text-red-600">{(v.out || 0).toFixed(2)}</td>
                            <td className="px-3 py-2 text-right text-gray-500">{v.count || 0}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div>
                  <p className="text-xs font-semibold text-gray-600 mb-2">{t('cm.components_pms_CashierTab.kasiyer_bazinda')}</p>
                  <div className="border rounded-lg overflow-hidden">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50">
                        <tr><th className="text-left px-3 py-2">Kasiyer</th><th className="text-right px-3 py-2">Vardiya</th><th className="text-right px-3 py-2">{t('cm.components_pms_CashierTab.nakit_giris_f1615')}</th><th className="text-right px-3 py-2">{t('cm.components_pms_CashierTab.nakit_cikis_a878e')}</th><th className="text-right px-3 py-2">{t('cm.components_pms_CashierTab.islem_792e7')}</th></tr>
                      </thead>
                      <tbody>
                        {Object.entries(periodData.by_cashier || {}).length === 0 ? (
                          <tr><td colSpan={5} className="px-3 py-3 text-center text-gray-400">{t('cm.components_pms_CashierTab.kayit_yok_546b8')}</td></tr>
                        ) : Object.entries(periodData.by_cashier).map(([k, v]) => (
                          <tr key={k} className="border-t">
                            <td className="px-3 py-2">{v.name || k}</td>
                            <td className="px-3 py-2 text-right">{v.shift_count || 0}</td>
                            <td className="px-3 py-2 text-right text-emerald-600">{(v.cash_in || 0).toFixed(2)}</td>
                            <td className="px-3 py-2 text-right text-red-600">{(v.cash_out || 0).toFixed(2)}</td>
                            <td className="px-3 py-2 text-right text-gray-500">{v.transaction_count || 0}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div>
                  <p className="text-xs font-semibold text-gray-600 mb-2">{t('cm.components_pms_CashierTab.para_birimi_bazinda')}</p>
                  <div className="border rounded-lg overflow-hidden">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50">
                        <tr><th className="text-left px-3 py-2">Birim</th><th className="text-right px-3 py-2">{t('cm.components_pms_CashierTab.giris_tl')}</th><th className="text-right px-3 py-2">{t('cm.components_pms_CashierTab.cikis_tl')}</th><th className="text-right px-3 py-2">{t('cm.components_pms_CashierTab.giris_orj')}</th><th className="text-right px-3 py-2">{t('cm.components_pms_CashierTab.cikis_orj')}</th><th className="text-right px-3 py-2">Adet</th></tr>
                      </thead>
                      <tbody>
                        {Object.entries(periodData.by_currency || {}).length === 0 ? (
                          <tr><td colSpan={6} className="px-3 py-3 text-center text-gray-400">{t('cm.components_pms_CashierTab.kayit_yok_546b8')}</td></tr>
                        ) : Object.entries(periodData.by_currency).map(([cur, v]) => (
                          <tr key={cur} className="border-t">
                            <td className="px-3 py-2 font-medium">{cur}</td>
                            <td className="px-3 py-2 text-right text-emerald-600">{(v.in_try || 0).toFixed(2)}</td>
                            <td className="px-3 py-2 text-right text-red-600">{(v.out_try || 0).toFixed(2)}</td>
                            <td className="px-3 py-2 text-right text-gray-600">{(v.in_original || 0).toFixed(2)}</td>
                            <td className="px-3 py-2 text-right text-gray-600">{(v.out_original || 0).toFixed(2)}</td>
                            <td className="px-3 py-2 text-right text-gray-500">{v.count || 0}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default CashierTab;
