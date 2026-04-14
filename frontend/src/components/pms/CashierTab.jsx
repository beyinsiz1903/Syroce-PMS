import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Wallet, DollarSign, CreditCard, ArrowRightLeft, Clock,
  LogIn, LogOut, Receipt, FileText, RefreshCw, AlertTriangle,
  CheckCircle, Banknote, Calculator, Printer
} from 'lucide-react';

const CashierTab = ({ user }) => {
  const [shift, setShift] = useState(null);
  const [shiftHistory, setShiftHistory] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showOpenDialog, setShowOpenDialog] = useState(false);
  const [showCloseDialog, setShowCloseDialog] = useState(false);
  const [openingAmount, setOpeningAmount] = useState('');
  const [closingCounts, setClosingCounts] = useState({
    cash_200: 0, cash_100: 0, cash_50: 0, cash_20: 0, cash_10: 0, cash_5: 0, cash_1: 0,
    coin_1: 0, coin_050: 0, coin_025: 0
  });
  const [closingNote, setClosingNote] = useState('');
  const [activeView, setActiveView] = useState('current');

  const loadShift = useCallback(async () => {
    try {
      const res = await axios.get('/cashier/current-shift');
      setShift(res.data.shift || null);
      setTransactions(res.data.transactions || []);
    } catch {
      setShift(null);
      setTransactions([]);
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

  const closeShift = async () => {
    setLoading(true);
    const countedTotal = (closingCounts.cash_200 * 200) + (closingCounts.cash_100 * 100) +
      (closingCounts.cash_50 * 50) + (closingCounts.cash_20 * 20) + (closingCounts.cash_10 * 10) +
      (closingCounts.cash_5 * 5) + (closingCounts.cash_1 * 1) +
      (closingCounts.coin_1 * 1) + (closingCounts.coin_050 * 0.5) + (closingCounts.coin_025 * 0.25);
    try {
      await axios.post('/cashier/close-shift', {
        counted_amount: countedTotal,
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

  const countedTotal = (closingCounts.cash_200 * 200) + (closingCounts.cash_100 * 100) +
    (closingCounts.cash_50 * 50) + (closingCounts.cash_20 * 20) + (closingCounts.cash_10 * 10) +
    (closingCounts.cash_5 * 5) + (closingCounts.cash_1 * 1) +
    (closingCounts.coin_1 * 1) + (closingCounts.coin_050 * 0.5) + (closingCounts.coin_025 * 0.25);

  const expectedCash = shift ? (shift.opening_amount || 0) + (shift.cash_in || 0) - (shift.cash_out || 0) : 0;
  const difference = countedTotal - expectedCash;

  const cashStats = {
    totalIn: transactions.filter(t => t.direction === 'in').reduce((s, t) => s + (t.amount || 0), 0),
    totalOut: transactions.filter(t => t.direction === 'out').reduce((s, t) => s + (t.amount || 0), 0),
    cashCount: transactions.filter(t => t.method === 'cash').length,
    cardCount: transactions.filter(t => t.method === 'card').length,
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-semibold flex items-center gap-2">
          <Wallet className="w-6 h-6" /> Kasa Yonetimi
        </h2>
        <div className="flex gap-2">
          {!shift ? (
            <Button onClick={() => setShowOpenDialog(true)} className="bg-emerald-600 hover:bg-emerald-700">
              <LogIn className="w-4 h-4 mr-2" /> Vardiya Ac
            </Button>
          ) : (
            <Button onClick={() => setShowCloseDialog(true)} variant="destructive">
              <LogOut className="w-4 h-4 mr-2" /> Vardiya Kapat
            </Button>
          )}
          <Button variant="outline" onClick={() => { loadShift(); loadHistory(); }}>
            <RefreshCw className="w-4 h-4 mr-2" /> Yenile
          </Button>
        </div>
      </div>

      {shift ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <Card className="bg-emerald-50 border-emerald-200">
              <CardContent className="p-3">
                <p className="text-xs text-emerald-600">Acilis Tutari</p>
                <p className="text-lg font-bold text-emerald-700">{(shift.opening_amount || 0).toFixed(2)} TL</p>
              </CardContent>
            </Card>
            <Card className="bg-blue-50 border-blue-200">
              <CardContent className="p-3">
                <p className="text-xs text-blue-600">Nakit Giris</p>
                <p className="text-lg font-bold text-blue-700">{cashStats.totalIn.toFixed(2)} TL</p>
              </CardContent>
            </Card>
            <Card className="bg-amber-50 border-amber-200">
              <CardContent className="p-3">
                <p className="text-xs text-amber-600">Nakit Cikis</p>
                <p className="text-lg font-bold text-amber-700">{cashStats.totalOut.toFixed(2)} TL</p>
              </CardContent>
            </Card>
            <Card className="bg-purple-50 border-purple-200">
              <CardContent className="p-3">
                <p className="text-xs text-purple-600">Kredi Karti</p>
                <p className="text-lg font-bold text-purple-700">{cashStats.cardCount} islem</p>
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
                <p className="text-sm text-gray-400 py-4 text-center">Henuz islem yok</p>
              ) : (
                <div className="max-h-[400px] overflow-y-auto space-y-1">
                  {transactions.map((t, i) => (
                    <div key={i} className="flex items-center justify-between p-2 rounded border border-gray-100 hover:bg-gray-50 text-xs">
                      <div className="flex items-center gap-2">
                        {t.direction === 'in' ? <DollarSign className="w-3.5 h-3.5 text-emerald-500" /> : <ArrowRightLeft className="w-3.5 h-3.5 text-red-500" />}
                        <span className="text-gray-700">{t.description || t.type || 'Islem'}</span>
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
            <p className="text-gray-400 text-sm mb-4">Islem yapabilmek icin vardiya acmaniz gerekiyor</p>
            <Button onClick={() => setShowOpenDialog(true)} className="bg-emerald-600 hover:bg-emerald-700">
              <LogIn className="w-4 h-4 mr-2" /> Vardiya Ac
            </Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Clock className="w-4 h-4" /> Gecmis Vardiyalar
          </CardTitle>
        </CardHeader>
        <CardContent>
          {shiftHistory.length === 0 ? (
            <p className="text-sm text-gray-400 py-4 text-center">Gecmis vardiya bulunamadi</p>
          ) : (
            <div className="space-y-2">
              {shiftHistory.map((s, i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded-lg border border-gray-200 text-xs">
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full ${s.status === 'closed' ? 'bg-gray-400' : 'bg-emerald-500'}`} />
                    <div>
                      <span className="text-gray-700 font-medium">{s.cashier_name || 'Kasiyer'}</span>
                      <p className="text-gray-400">{s.opened_at?.slice(0, 16).replace('T', ' ')} - {s.closed_at?.slice(11, 16) || 'Acik'}</p>
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
                    value={closingCounts[key]} onChange={e => setClosingCounts(p => ({ ...p, [key]: parseInt(e.target.value) || 0 }))} />
                </div>
              ))}
            </div>
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
    </div>
  );
};

export default CashierTab;
