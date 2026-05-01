import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  Wallet, DollarSign, ArrowRightLeft, Clock,
  LogIn, LogOut, Receipt, RefreshCw,
  Calculator, UserCheck, Users
} from 'lucide-react';

const CashierTab = ({ user }) => {
  const [shift, setShift] = useState(null);
  const [shiftHistory, setShiftHistory] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showOpenDialog, setShowOpenDialog] = useState(false);
  const [showCloseDialog, setShowCloseDialog] = useState(false);
  const [showHandoverDialog, setShowHandoverDialog] = useState(false);
  const [openingAmount, setOpeningAmount] = useState('');
  const [closingCounts, setClosingCounts] = useState({
    cash_200: 0, cash_100: 0, cash_50: 0, cash_20: 0, cash_10: 0, cash_5: 0, cash_1: 0,
    coin_1: 0, coin_050: 0, coin_025: 0
  });
  const [closingNote, setClosingNote] = useState('');
  const [handoverTarget, setHandoverTarget] = useState({ email: '', password: '', note: '' });

  const loadShift = useCallback(async () => {
    try {
      const res = await axios.get('/cashier/current-shift');
      setShift(res.data.shift || null);
      setTransactions(res.data.transactions || []);
    } catch (err) {
      setShift(null);
      setTransactions([]);
      if (err?.response?.status !== 404) {
        toast.error('Kasa vardiyasi yüklenemedi');
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
      toast.success('Kasa vardiyasi acildi');
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
    setLoading(true);
    try {
      await axios.post('/cashier/close-shift', {
        counted_amount: calcTotal(closingCounts),
        denomination_counts: closingCounts,
        notes: closingNote
      });
      toast.success('Kasa vardiyasi kapatildi');
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
      toast.error('Devir alacak kisinin e-posta ve sifresi gerekli');
      return;
    }
    setLoading(true);
    try {
      const res = await axios.post('/cashier/handover-shift', {
        target_email: handoverTarget.email.trim(),
        target_password: handoverTarget.password.trim(),
        note: handoverTarget.note
      });
      toast.success(`Vardiya ${res.data.target_name || handoverTarget.email} adli kullaniciya devredildi`);
      setShowHandoverDialog(false);
      setHandoverTarget({ email: '', password: '', note: '' });
      loadShift();
      loadHistory();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  const countedTotal = calcTotal(closingCounts);
  const expectedCash = shift ? (shift.opening_amount || 0) + (shift.cash_in || 0) - (shift.cash_out || 0) : 0;
  const difference = countedTotal - expectedCash;

  const cashStats = {
    totalIn: transactions.filter(t => t.direction === 'in').reduce((s, t) => s + (t.amount || 0), 0),
    totalOut: transactions.filter(t => t.direction === 'out').reduce((s, t) => s + (t.amount || 0), 0),
    cashCount: transactions.filter(t => t.method === 'cash').length,
    cardCount: transactions.filter(t => t.method === 'card').length,
  };

  const DenominationGrid = ({ counts, setCounts }) => (
    <div className="grid grid-cols-2 gap-3">
      {[
        ['cash_200', '200 TL'], ['cash_100', '100 TL'], ['cash_50', '50 TL'],
        ['cash_20', '20 TL'], ['cash_10', '10 TL'], ['cash_5', '5 TL'],
        ['cash_1', '1 TL'], ['coin_1', '1 TL (Bozuk)'],
        ['coin_050', '50 Krs'], ['coin_025', '25 Krs']
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
    if (s === 'open') return <Badge className="bg-emerald-100 text-emerald-700">Açık</Badge>;
    if (s === 'handed_over') return <Badge className="bg-blue-100 text-blue-700">Devredildi</Badge>;
    return <Badge className="bg-gray-100 text-gray-600">Kapalı</Badge>;
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-semibold flex items-center gap-2">
          <Wallet className="w-6 h-6" /> Kasa Yönetimi
        </h2>
        <div className="flex gap-2">
          {!shift ? (
            <Button onClick={() => setShowOpenDialog(true)} className="bg-emerald-600 hover:bg-emerald-700">
              <LogIn className="w-4 h-4 mr-2" /> Vardiya Ac
            </Button>
          ) : (
            <>
              <Button onClick={() => setShowHandoverDialog(true)} variant="outline" className="border-blue-300 text-blue-700 hover:bg-blue-50">
                <Users className="w-4 h-4 mr-2" /> Devret
              </Button>
              <Button onClick={() => setShowCloseDialog(true)} variant="destructive">
                <LogOut className="w-4 h-4 mr-2" /> Vardiya Kapat
              </Button>
            </>
          )}
          <Button variant="outline" onClick={() => { loadShift(); loadHistory(); }}>
            <RefreshCw className="w-4 h-4 mr-2" /> Yenile
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
                  <span className="font-medium text-emerald-800">Aktif Vardiya</span>
                  <span className="text-emerald-600 mx-2">|</span>
                  <span className="text-emerald-700">Acan: <strong>{shift.opened_by_name || shift.cashier_name || shift.cashier_email}</strong></span>
                  <span className="text-emerald-600 mx-2">|</span>
                  <span className="text-emerald-700">Baslangic: {shift.opened_at?.slice(0, 16).replace('T', ' ')}</span>
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
                <p className="text-xs text-emerald-600">Acilis Tutari</p>
                <p className="text-lg font-bold text-emerald-700">{(shift.opening_amount || 0).toFixed(2)} TL</p>
              </CardContent>
            </Card>
            <Card className="bg-blue-50 border-blue-200">
              <CardContent className="p-3">
                <p className="text-xs text-blue-600">Nakit Giriş</p>
                <p className="text-lg font-bold text-blue-700">{cashStats.totalIn.toFixed(2)} TL</p>
              </CardContent>
            </Card>
            <Card className="bg-amber-50 border-amber-200">
              <CardContent className="p-3">
                <p className="text-xs text-amber-600">Nakit Çıkış</p>
                <p className="text-lg font-bold text-amber-700">{cashStats.totalOut.toFixed(2)} TL</p>
              </CardContent>
            </Card>
            <Card className="bg-purple-50 border-purple-200">
              <CardContent className="p-3">
                <p className="text-xs text-purple-600">Kredi Kartı</p>
                <p className="text-lg font-bold text-purple-700">{cashStats.cardCount} işlem</p>
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
              <CardTitle className="text-sm flex items-center gap-2">
                <Receipt className="w-4 h-4" /> Vardiya Islemleri ({transactions.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {transactions.length === 0 ? (
                <p className="text-sm text-gray-400 py-4 text-center">Henüz işlem yok</p>
              ) : (
                <div className="max-h-[400px] overflow-y-auto space-y-1">
                  {transactions.map((t, i) => (
                    <div key={i} className="flex items-center justify-between p-2 rounded border border-gray-100 hover:bg-gray-50 text-xs">
                      <div className="flex items-center gap-2">
                        {t.direction === 'in' ? <DollarSign className="w-3.5 h-3.5 text-emerald-500" /> : <ArrowRightLeft className="w-3.5 h-3.5 text-red-500" />}
                        <span className="text-gray-700">{t.description || t.type || 'İşlem'}</span>
                        <Badge variant="outline" className="text-[10px]">{t.method}</Badge>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-gray-400">{t.timestamp?.slice(11, 16)}</span>
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
            <p className="text-gray-500 text-lg mb-2">Aktif vardiya yok</p>
            <p className="text-gray-400 text-sm mb-4">İşlem yapabilmek için vardiya acmaniz gerekiyor</p>
            <Button onClick={() => setShowOpenDialog(true)} className="bg-emerald-600 hover:bg-emerald-700">
              <LogIn className="w-4 h-4 mr-2" /> Vardiya Ac
            </Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Clock className="w-4 h-4" /> Geçmiş Vardiyalar
          </CardTitle>
        </CardHeader>
        <CardContent>
          {shiftHistory.length === 0 ? (
            <p className="text-sm text-gray-400 py-4 text-center">Geçmiş vardiya bulunamadı</p>
          ) : (
            <div className="space-y-2">
              {shiftHistory.map((s, i) => (
                <div key={i} className="p-3 rounded-lg border border-gray-200 text-xs">
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
                        <p className="text-gray-500">Acilis: {(s.opening_amount || 0).toFixed(2)}</p>
                        <p className="text-gray-500">Kapanis: {(s.closing_amount || 0).toFixed(2)}</p>
                      </div>
                      {s.difference != null && (
                        <Badge className={Math.abs(s.difference) < 0.01 ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}>
                          {Math.abs(s.difference) < 0.01 ? 'Tam' : `Fark: ${s.difference.toFixed(2)}`}
                        </Badge>
                      )}
                    </div>
                  </div>
                  <div className="mt-2 pt-2 border-t border-gray-100 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-gray-500">
                    {s.opened_by_name && <span>Acan: <strong className="text-gray-700">{s.opened_by_name}</strong></span>}
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
            <DialogTitle className="flex items-center gap-2"><LogIn className="w-5 h-5" /> Vardiya Ac</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label>Acilis Tutari (TL)</Label>
              <Input type="number" value={openingAmount} onChange={e => setOpeningAmount(e.target.value)} placeholder="0.00" />
              <p className="text-xs text-gray-400 mt-1">Kasadaki mevcut nakit miktarini girin</p>
            </div>
            <Button onClick={openShift} disabled={loading} className="w-full bg-emerald-600 hover:bg-emerald-700">
              {loading ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <LogIn className="w-4 h-4 mr-2" />}
              Vardiyayi Ac
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showCloseDialog} onOpenChange={setShowCloseDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Calculator className="w-5 h-5" /> Vardiya Kapat - Kasa Sayimi</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <DenominationGrid counts={closingCounts} setCounts={setClosingCounts} />
            <div className="bg-gray-50 rounded-lg p-3 space-y-1">
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Sayilan Tutar:</span>
                <span className="font-bold">{countedTotal.toFixed(2)} TL</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Beklenen Tutar:</span>
                <span className="font-bold">{expectedCash.toFixed(2)} TL</span>
              </div>
              <div className={`flex justify-between text-sm pt-1 border-t ${Math.abs(difference) < 0.01 ? 'text-emerald-600' : 'text-red-600'}`}>
                <span>Fark:</span>
                <span className="font-bold">{difference.toFixed(2)} TL</span>
              </div>
            </div>
            <div>
              <Label>Not</Label>
              <Input value={closingNote} onChange={e => setClosingNote(e.target.value)} placeholder="Vardiya notu (opsiyonel)" />
            </div>
            <Button onClick={closeShift} disabled={loading} className="w-full" variant="destructive">
              {loading ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <LogOut className="w-4 h-4 mr-2" />}
              Vardiyayi Kapat
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
              Vardiyayi devralacak kisi kendi e-posta ve sifresini girerek onaylamalidir.
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Mevcut Kasa:</span>
                <span className="font-bold">{expectedCash.toFixed(2)} TL</span>
              </div>
            </div>
            <div className="border rounded-lg p-4 space-y-3">
              <p className="text-xs font-semibold text-gray-500 uppercase">Devralacak Kisi Girisi</p>
              <div>
                <Label>E-posta *</Label>
                <Input type="email" value={handoverTarget.email} onChange={e => setHandoverTarget(p => ({ ...p, email: e.target.value }))} placeholder="kullanici@hotel.com" />
              </div>
              <div>
                <Label>Sifre *</Label>
                <Input type="password" value={handoverTarget.password} onChange={e => setHandoverTarget(p => ({ ...p, password: e.target.value }))} placeholder="Sifrenizi girin" />
              </div>
            </div>
            <div>
              <Label>Devir Notu</Label>
              <Input value={handoverTarget.note} onChange={e => setHandoverTarget(p => ({ ...p, note: e.target.value }))} placeholder="Devir notu (opsiyonel)" />
            </div>
            <Button onClick={handoverShift} disabled={loading || !handoverTarget.email.trim() || !handoverTarget.password.trim()} className="w-full bg-blue-600 hover:bg-blue-700">
              {loading ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Users className="w-4 h-4 mr-2" />}
              Onayla ve Devret
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default CashierTab;
