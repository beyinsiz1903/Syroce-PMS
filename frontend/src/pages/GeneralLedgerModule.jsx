import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useCurrency } from '@/context/CurrencyContext';
import { Plus, Save, FileText, AlertCircle, CalendarRange, LockKeyhole, Unlock, RotateCcw, Landmark, TrendingUp, PackageOpen } from 'lucide-react';

export const GL_ENDPOINTS = {
  accounts: '/gl/accounts',
  initializeAccounts: '/gl/accounts/initialize',
  journal: '/gl/journal',
  trialBalance: '/gl/trial-balance',
  periods: '/gl/periods',
  initializePeriods: '/gl/periods/initialize',
  incomeStatement: '/gl/statements/income-statement',
  balanceSheet: '/gl/statements/balance-sheet',
};

export const toJournalPayload = (journal) => ({
  date: journal.date,
  memo: journal.description.trim(),
  source: 'manual',
  source_ref: journal.type,
  ...(journal.idempotency_key ? { idempotency_key: journal.idempotency_key } : {}),
  lines: journal.lines.map((line) => ({
    account_code: line.account_code.trim(),
    debit: Number(line.debit) || 0,
    credit: Number(line.credit) || 0,
    memo: line.description?.trim() || null,
  })),
});

const newRequestKey = () => {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `manual-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const emptyJournal = () => ({
  date: new Date().toISOString().split('T')[0],
  type: 'Mahsup',
  description: '',
  idempotency_key: newRequestKey(),
  lines: [
    { account_code: '', debit: 0, credit: 0, description: '' },
    { account_code: '', debit: 0, credit: 0, description: '' }
  ]
});

export const normalizeTrialBalance = (data = {}) => ({
  lines: (data.rows || []).map((row) => ({
    code: row.account_code,
    name: row.account_name,
    total_debit: row.total_debit || 0,
    total_credit: row.total_credit || 0,
    balance_type: row.debit_balance > 0 ? 'Borç' : row.credit_balance > 0 ? 'Alacak' : '-',
    balance: row.debit_balance || row.credit_balance || 0,
  })),
  totals: {
    total_debit: data.totals?.debit_balance || 0,
    total_credit: data.totals?.credit_balance || 0,
    balanced: data.totals?.balanced ?? true,
  },
});

export const mergeAccountBalances = (accounts = [], trialBalance = {}) => {
  const balances = new Map(
    (trialBalance.rows || []).map((row) => [
      row.account_code,
      (Number(row.debit_balance) || 0) - (Number(row.credit_balance) || 0),
    ])
  );
  return accounts.map((account) => ({ ...account, balance: balances.get(account.code) || 0 }));
};

const GeneralLedgerModule = () => {
  const { amount: fmtMoney } = useCurrency();
  const [activeTab, setActiveTab] = useState('accounts');
  
  const [accounts, setAccounts] = useState([]);
  const [journals, setJournals] = useState([]);
  const [trialBalance, setTrialBalance] = useState({ lines: [], totals: {} });
  const [initializingAccounts, setInitializingAccounts] = useState(false);
  const [periods, setPeriods] = useState([]);
  const [periodYear, setPeriodYear] = useState(new Date().getFullYear());
  const [periodBusy, setPeriodBusy] = useState('');
  const [journalSaving, setJournalSaving] = useState(false);
  const [reversalBusy, setReversalBusy] = useState('');
  const reversalKeys = useRef({});
  const [statements, setStatements] = useState({ income: null, balance: null });
  const [workspace, setWorkspace] = useState({ aging: null, expenseBudget: null, revenueBudget: null, assets: [] });
  
  // New Journal Entry State
  const [newJournal, setNewJournal] = useState(emptyJournal);

  const fetchAccounts = async () => {
    try {
      const [accountsRes, balanceRes] = await Promise.all([
        axios.get(GL_ENDPOINTS.accounts),
        axios.get(GL_ENDPOINTS.trialBalance),
      ]);
      setAccounts(mergeAccountBalances(accountsRes.data?.accounts || [], balanceRes.data));
    } catch {
      toast.error('Hesap planı yüklenemedi.');
    }
  };

  const initializeAccounts = async () => {
    setInitializingAccounts(true);
    try {
      await axios.post(GL_ENDPOINTS.initializeAccounts);
      await fetchAccounts();
      toast.success('Standart hesap planı oluşturuldu.');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Hesap planı oluşturulamadı.');
    } finally {
      setInitializingAccounts(false);
    }
  };

  const fetchJournals = async () => {
    try {
      const res = await axios.get(GL_ENDPOINTS.journal);
      setJournals(res.data?.entries || []);
    } catch {
      toast.error('Yevmiye fişleri yüklenemedi.');
    }
  };

  const fetchTrialBalance = async () => {
    try {
      const res = await axios.get(GL_ENDPOINTS.trialBalance);
      setTrialBalance(normalizeTrialBalance(res.data));
    } catch {
      toast.error('Mizan yüklenemedi.');
    }
  };

  const fetchPeriods = async () => {
    try {
      const res = await axios.get(GL_ENDPOINTS.periods, { params: { fiscal_year: periodYear } });
      setPeriods(res.data?.periods || []);
    } catch {
      toast.error('Mali dönemler yüklenemedi.');
    }
  };

  const fetchStatements = async () => {
    const today = new Date().toISOString().split('T')[0];
    const start = `${today.slice(0, 4)}-01-01`;
    try {
      const [incomeRes, balanceRes] = await Promise.all([
        axios.get(GL_ENDPOINTS.incomeStatement, { params: { start, end: today } }),
        axios.get(GL_ENDPOINTS.balanceSheet, { params: { as_of: today } }),
      ]);
      setStatements({ income: incomeRes.data, balance: balanceRes.data });
    } catch {
      toast.error('Mali tablolar yüklenemedi.');
    }
  };

  const fetchWorkspace = async () => {
    const period = new Date().toISOString().slice(0, 7);
    try {
      const [agingRes, expenseRes, revenueRes, assetsRes] = await Promise.all([
        axios.get('/ap/aging'),
        axios.get('/budget/vs-actual', { params: { period, kind: 'expense' } }),
        axios.get('/budget/vs-actual', { params: { period, kind: 'revenue' } }),
        axios.get('/fixed-assets/assets'),
      ]);
      setWorkspace({
        aging: agingRes.data,
        expenseBudget: expenseRes.data,
        revenueBudget: revenueRes.data,
        assets: assetsRes.data?.assets || [],
      });
    } catch {
      toast.error('Muhasebe alt defterleri yüklenemedi.');
    }
  };

  const initializePeriods = async () => {
    setPeriodBusy('initialize');
    try {
      await axios.post(GL_ENDPOINTS.initializePeriods, { fiscal_year: Number(periodYear) });
      toast.success(`${periodYear} mali dönemleri hazırlandı.`);
      await fetchPeriods();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Mali dönemler oluşturulamadı.');
    } finally {
      setPeriodBusy('');
    }
  };

  const changePeriodStatus = async (period, action) => {
    const reason = window.prompt(action === 'close' ? 'Dönem kapatma gerekçesi:' : 'Yeniden açma gerekçesi:');
    if (!reason || reason.trim().length < 3) return;
    setPeriodBusy(`${period.id}:${action}`);
    try {
      await axios.post(`${GL_ENDPOINTS.periods}/${period.id}/${action}`, { reason: reason.trim() });
      toast.success(action === 'close' ? 'Mali dönem kapatıldı.' : 'Mali dönem yeniden açıldı.');
      await fetchPeriods();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Mali dönem güncellenemedi.');
    } finally {
      setPeriodBusy('');
    }
  };

  useEffect(() => {
    if (activeTab === 'accounts') fetchAccounts();
    if (activeTab === 'journals') fetchJournals();
    if (activeTab === 'trial-balance') fetchTrialBalance();
    if (activeTab === 'periods') fetchPeriods();
    if (activeTab === 'statements') fetchStatements();
    if (activeTab === 'workspace') fetchWorkspace();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, periodYear]);

  const handleAddJournalLine = () => {
    setNewJournal(prev => ({
      ...prev,
      lines: [...prev.lines, { account_code: '', debit: 0, credit: 0, description: '' }]
    }));
  };

  const handleLineChange = (index, field, value) => {
    const updated = [...newJournal.lines];
    if (field === 'debit' || field === 'credit') {
      value = parseFloat(value) || 0;
      // You can only have debit OR credit
      if (field === 'debit' && value > 0) updated[index].credit = 0;
      if (field === 'credit' && value > 0) updated[index].debit = 0;
    }
    updated[index][field] = value;
    setNewJournal({ ...newJournal, lines: updated });
  };

  const handleSubmitJournal = async () => {
    // Calculate total debit and credit
    const tDebit = newJournal.lines.reduce((acc, l) => acc + (parseFloat(l.debit) || 0), 0);
    const tCredit = newJournal.lines.reduce((acc, l) => acc + (parseFloat(l.credit) || 0), 0);
    
    if (Math.abs(tDebit - tCredit) > 0.01) {
      toast.error(`Borç (${tDebit}) ve Alacak (${tCredit}) toplamları eşit olmalıdır!`);
      return;
    }
    if (tDebit === 0) {
      toast.error('Fiş toplamı 0 olamaz.');
      return;
    }
    if (!newJournal.description) {
      toast.error('Fiş açıklaması zorunludur.');
      return;
    }
    if (newJournal.lines.some((line) => !line.account_code.trim())) {
      toast.error('Her satır için hesap kodu zorunludur.');
      return;
    }

    setJournalSaving(true);
    try {
      await axios.post(GL_ENDPOINTS.journal, toJournalPayload(newJournal));
      toast.success('Yevmiye fişi başarıyla kaydedildi.');
      setNewJournal(emptyJournal());
      fetchJournals();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fiş kaydedilirken hata oluştu.');
    } finally {
      setJournalSaving(false);
    }
  };

  const reverseJournal = async (journal) => {
    const reason = window.prompt('Ters kayıt gerekçesi:');
    if (!reason || reason.trim().length < 3) return;
    const reversalDate = window.prompt('Ters kayıt tarihi (YYYY-MM-DD):', new Date().toISOString().split('T')[0]);
    if (!reversalDate) return;
    const key = reversalKeys.current[journal.id] || newRequestKey();
    reversalKeys.current[journal.id] = key;
    setReversalBusy(journal.id);
    try {
      await axios.post(`${GL_ENDPOINTS.journal}/${journal.id}/reverse`, {
        date: reversalDate,
        reason: reason.trim(),
        idempotency_key: key,
      });
      delete reversalKeys.current[journal.id];
      toast.success('Bağlı ters kayıt fişi oluşturuldu.');
      await fetchJournals();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Ters kayıt oluşturulamadı.');
    } finally {
      setReversalBusy('');
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Genel Muhasebe</h1>
        <p className="text-gray-500 mt-1">Tek Düzen Hesap Planı, Yevmiye Kayıtları ve Mizan</p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="mb-4">
          <TabsTrigger value="accounts">Hesap Planı (TDHP)</TabsTrigger>
          <TabsTrigger value="journals">Yevmiye Fişleri</TabsTrigger>
          <TabsTrigger value="trial-balance">Mizan</TabsTrigger>
          <TabsTrigger value="periods">Mali Dönemler</TabsTrigger>
          <TabsTrigger value="statements">Mali Tablolar</TabsTrigger>
          <TabsTrigger value="workspace">Alt Defterler</TabsTrigger>
        </TabsList>

        {/* TDHP Accounts */}
        <TabsContent value="accounts">
          <Card>
            <CardHeader>
              <CardTitle>Tek Düzen Hesap Planı</CardTitle>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm text-left">
                <thead className="bg-gray-50 text-gray-600">
                  <tr>
                    <th className="p-3 font-semibold rounded-tl-lg">Hesap Kodu</th>
                    <th className="p-3 font-semibold">Hesap Adı</th>
                    <th className="p-3 font-semibold">Tip</th>
                    <th className="p-3 font-semibold text-right rounded-tr-lg">Güncel Bakiye</th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map(acc => (
                    <tr key={acc.code} className="border-b last:border-0 hover:bg-gray-50">
                      <td className="p-3 font-medium text-blue-600">{acc.code}</td>
                      <td className="p-3 text-gray-800">{acc.name}</td>
                      <td className="p-3 text-gray-500">{acc.type}</td>
                      <td className="p-3 text-right font-medium">
                        {acc.balance !== 0 ? fmtMoney(Math.abs(acc.balance)) : '-'}
                      </td>
                    </tr>
                  ))}
                  {accounts.length === 0 && (
                    <tr>
                      <td colSpan="4" className="text-center p-8 text-gray-500">
                        <p className="mb-3">Kayıtlı hesap bulunamadı.</p>
                        <Button onClick={initializeAccounts} disabled={initializingAccounts} size="sm">
                          {initializingAccounts ? 'Oluşturuluyor...' : 'Standart Hesap Planını Oluştur'}
                        </Button>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Journals */}
        <TabsContent value="journals">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            {/* New Journal Form */}
            <div className="lg:col-span-2">
              <Card>
                <CardHeader>
                  <CardTitle>Yeni Fiş Girişi</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <label className="text-sm font-medium mb-1 block">Tarih</label>
                      <Input type="date" value={newJournal.date} onChange={e => setNewJournal({...newJournal, date: e.target.value})} />
                    </div>
                    <div>
                      <label className="text-sm font-medium mb-1 block">Fiş Tipi</label>
                      <select className="w-full h-10 px-3 py-2 border rounded-md text-sm bg-white" value={newJournal.type} onChange={e => setNewJournal({...newJournal, type: e.target.value})}>
                        <option value="Mahsup">Mahsup Fişi</option>
                        <option value="Tahsilat">Tahsilat Fişi</option>
                        <option value="Tediye">Tediye Fişi</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-sm font-medium mb-1 block">Açıklama</label>
                      <Input type="text" placeholder="Fiş Geneli Açıklaması" value={newJournal.description} onChange={e => setNewJournal({...newJournal, description: e.target.value})} />
                    </div>
                  </div>

                  <div className="border rounded-md overflow-hidden mt-4">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-100">
                        <tr>
                          <th className="p-2 text-left w-32">Hesap Kodu</th>
                          <th className="p-2 text-left">Açıklama</th>
                          <th className="p-2 text-right w-32">Borç (₺)</th>
                          <th className="p-2 text-right w-32">Alacak (₺)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {newJournal.lines.map((line, idx) => (
                          <tr key={idx} className="border-b">
                            <td className="p-1"><Input className="h-8" value={line.account_code} onChange={e => handleLineChange(idx, 'account_code', e.target.value)} placeholder="100, 120" /></td>
                            <td className="p-1"><Input className="h-8" value={line.description} onChange={e => handleLineChange(idx, 'description', e.target.value)} /></td>
                            <td className="p-1"><Input type="number" className="h-8 text-right bg-red-50" value={line.debit || ''} onChange={e => handleLineChange(idx, 'debit', e.target.value)} /></td>
                            <td className="p-1"><Input type="number" className="h-8 text-right bg-green-50" value={line.credit || ''} onChange={e => handleLineChange(idx, 'credit', e.target.value)} /></td>
                          </tr>
                        ))}
                      </tbody>
                      <tfoot className="bg-gray-50 font-bold">
                        <tr>
                          <td colSpan="2" className="p-2 text-right">TOPLAM:</td>
                          <td className="p-2 text-right text-red-600">{newJournal.lines.reduce((a, b) => a + (parseFloat(b.debit)||0), 0).toFixed(2)}</td>
                          <td className="p-2 text-right text-green-600">{newJournal.lines.reduce((a, b) => a + (parseFloat(b.credit)||0), 0).toFixed(2)}</td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                  <div className="flex justify-between mt-4">
                    <Button variant="outline" onClick={handleAddJournalLine}><Plus className="w-4 h-4 mr-2" /> Satır Ekle</Button>
                    <Button onClick={handleSubmitJournal} disabled={journalSaving} className="bg-blue-600 hover:bg-blue-700 text-white"><Save className="w-4 h-4 mr-2" /> {journalSaving ? 'Kaydediliyor...' : 'Fişi Kaydet'}</Button>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Recent Journals */}
            <div>
              <Card>
                <CardHeader>
                  <CardTitle>Son Fişler</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4 max-h-[600px] overflow-y-auto">
                  {journals.map(j => (
                    <div key={j.id} className="p-3 border rounded-lg hover:border-blue-300 transition-colors bg-white">
                      <div className="flex justify-between items-start mb-2">
                        <div>
                          <span className="text-xs font-bold px-2 py-1 bg-gray-100 text-gray-600 rounded-full">{j.source === 'reversal' ? 'Ters Kayıt' : j.source_ref || j.source || 'Fiş'}</span>
                          <span className="text-xs text-gray-400 ml-2">{j.date}</span>
                        </div>
                        <span className="font-bold text-gray-900">{fmtMoney(j.total_debit)}</span>
                      </div>
                      <p className="text-sm text-gray-600 truncate">{j.memo}</p>
                      {j.reversal_status === 'reversed' && <p className="text-xs text-amber-700 mt-2">Bu fiş için ters kayıt oluşturuldu.</p>}
                      {j.source !== 'reversal' && j.reversal_status !== 'reversed' && (
                        <Button size="sm" variant="outline" className="w-full mt-3" disabled={reversalBusy === j.id} onClick={() => reverseJournal(j)}>
                          <RotateCcw className="w-3.5 h-3.5 mr-1.5" /> {reversalBusy === j.id ? 'Oluşturuluyor...' : 'Ters Kayıt Oluştur'}
                        </Button>
                      )}
                    </div>
                  ))}
                  {journals.length === 0 && <p className="text-center text-sm text-gray-500 py-4">Henüz fiş girilmemiş.</p>}
                </CardContent>
              </Card>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="periods">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-3">
              <div>
                <CardTitle className="flex items-center gap-2"><CalendarRange className="w-5 h-5" /> Mali Dönem Yönetimi</CardTitle>
                <p className="text-sm text-gray-500 mt-1">Kapalı döneme yeni fiş veya entegrasyon kaydı gönderilemez.</p>
              </div>
              <div className="flex items-center gap-2">
                <Input className="w-28" type="number" min="2000" max="2100" value={periodYear} onChange={(e) => setPeriodYear(Number(e.target.value))} />
                <Button variant="outline" onClick={initializePeriods} disabled={periodBusy === 'initialize'}>
                  {periodBusy === 'initialize' ? 'Hazırlanıyor...' : '12 Dönemi Hazırla'}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {periods.length === 0 ? (
                <div className="text-center py-10 text-gray-500">Bu mali yıl için dönem bulunamadı.</div>
              ) : (
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {periods.map((period) => {
                    const closed = period.status === 'closed';
                    const action = closed ? 'reopen' : 'close';
                    const busy = periodBusy === `${period.id}:${action}`;
                    return (
                      <div key={period.id} className={`rounded-lg border p-3 ${closed ? 'border-slate-300 bg-slate-50' : 'border-emerald-200 bg-emerald-50/40'}`}>
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <p className="font-semibold text-gray-900">{period.name}</p>
                            <p className="text-xs text-gray-500">{period.start_date} — {period.end_date}</p>
                          </div>
                          <span className={`text-xs px-2 py-1 rounded-full font-medium ${closed ? 'bg-slate-200 text-slate-700' : 'bg-emerald-100 text-emerald-700'}`}>
                            {closed ? 'Kapalı' : 'Açık'}
                          </span>
                        </div>
                        {closed && period.close_reason && <p className="mt-2 text-xs text-slate-600">Gerekçe: {period.close_reason}</p>}
                        <Button className="w-full mt-3" size="sm" variant={closed ? 'outline' : 'default'} disabled={busy} onClick={() => changePeriodStatus(period, action)}>
                          {closed ? <Unlock className="w-3.5 h-3.5 mr-1.5" /> : <LockKeyhole className="w-3.5 h-3.5 mr-1.5" />}
                          {busy ? 'İşleniyor...' : closed ? 'Yeniden Aç' : 'Dönemi Kapat'}
                        </Button>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Trial Balance */}
        <TabsContent value="trial-balance">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>Geçici Mizan</CardTitle>
              <Button variant="outline" size="sm" onClick={() => window.print()}><FileText className="w-4 h-4 mr-2" />Yazdır</Button>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm text-left">
                <thead className="bg-gray-800 text-white">
                  <tr>
                    <th className="p-3 font-semibold rounded-tl-lg">Hesap</th>
                    <th className="p-3 font-semibold">Hesap Adı</th>
                    <th className="p-3 font-semibold text-right">Borç Toplam</th>
                    <th className="p-3 font-semibold text-right">Alacak Toplam</th>
                    <th className="p-3 font-semibold text-center">Bakiye Yönü</th>
                    <th className="p-3 font-semibold text-right rounded-tr-lg">Bakiye</th>
                  </tr>
                </thead>
                <tbody>
                  {trialBalance.lines?.map((line) => (
                    <tr key={line.code} className="border-b hover:bg-gray-50">
                      <td className="p-3 font-medium text-blue-600">{line.code}</td>
                      <td className="p-3 text-gray-800">{line.name}</td>
                      <td className="p-3 text-right">{line.total_debit > 0 ? fmtMoney(line.total_debit) : '-'}</td>
                      <td className="p-3 text-right">{line.total_credit > 0 ? fmtMoney(line.total_credit) : '-'}</td>
                      <td className="p-3 text-center">
                        <span className={`text-xs px-2 py-1 rounded-full ${line.balance_type === 'Borç' ? 'bg-red-100 text-red-700' : line.balance_type === 'Alacak' ? 'bg-green-100 text-green-700' : 'bg-gray-100'}`}>
                          {line.balance_type}
                        </span>
                      </td>
                      <td className="p-3 text-right font-bold text-gray-900">{line.balance > 0 ? fmtMoney(line.balance) : '-'}</td>
                    </tr>
                  ))}
                  {(!trialBalance.lines || trialBalance.lines.length === 0) && (
                    <tr><td colSpan="6" className="text-center p-8 text-gray-500">Mizan alınacak hareket bulunamadı.</td></tr>
                  )}
                </tbody>
                {trialBalance.lines && trialBalance.lines.length > 0 && (
                  <tfoot className="bg-gray-100 font-bold border-t-2 border-gray-300">
                    <tr>
                      <td colSpan="2" className="p-3 text-right">GENEL TOPLAM:</td>
                      <td className="p-3 text-right text-red-600">{fmtMoney(trialBalance.totals?.total_debit || 0)}</td>
                      <td className="p-3 text-right text-green-600">{fmtMoney(trialBalance.totals?.total_credit || 0)}</td>
                      <td colSpan="2"></td>
                    </tr>
                  </tfoot>
                )}
              </table>
              {trialBalance.totals && !trialBalance.totals.balanced && (
                <div className="mt-4 p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg flex items-start gap-2">
                  <AlertCircle className="w-5 h-5 mt-0.5" />
                  <div>
                    <h4 className="font-bold">Mizan Denk Değil!</h4>
                    <p className="text-sm">Borç ve Alacak toplamları birbirine eşit değil. Bu durum geçmiş hatalı fişlerden veya yuvarlama farklarından kaynaklanabilir.</p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="statements">
          <div className="grid lg:grid-cols-2 gap-5">
            <Card>
              <CardHeader><CardTitle>Gelir Tablosu · Yılbaşından Bugüne</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {(statements.income?.revenue || []).map((row) => <div key={row.account_code} className="flex justify-between text-sm"><span>{row.account_code} · {row.account_name}</span><span className="font-medium">{fmtMoney(row.amount)}</span></div>)}
                <div className="border-t pt-2 flex justify-between font-semibold text-emerald-700"><span>Toplam Gelir</span><span>{fmtMoney(statements.income?.totals?.revenue || 0)}</span></div>
                {(statements.income?.expenses || []).map((row) => <div key={row.account_code} className="flex justify-between text-sm"><span>{row.account_code} · {row.account_name}</span><span className="font-medium">{fmtMoney(row.amount)}</span></div>)}
                <div className="border-t pt-2 flex justify-between font-semibold text-red-700"><span>Toplam Gider</span><span>{fmtMoney(statements.income?.totals?.expenses || 0)}</span></div>
                <div className="rounded-lg bg-slate-900 text-white p-3 flex justify-between font-bold"><span>Net Dönem Kârı / Zararı</span><span>{fmtMoney(statements.income?.totals?.net_income || 0)}</span></div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Bilanço · Bugün</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {['assets', 'liabilities', 'equity'].map((section) => (
                  <div key={section} className="space-y-1">
                    <p className="text-xs font-bold uppercase text-slate-500">{section === 'assets' ? 'Varlıklar' : section === 'liabilities' ? 'Yükümlülükler' : 'Özkaynaklar'}</p>
                    {(statements.balance?.[section] || []).map((row) => <div key={row.account_code} className="flex justify-between text-sm"><span>{row.account_code} · {row.account_name}</span><span>{fmtMoney(row.amount)}</span></div>)}
                  </div>
                ))}
                <div className="flex justify-between text-sm border-t pt-2"><span>Cari dönem kârı/zararı</span><span>{fmtMoney(statements.balance?.current_earnings?.amount || 0)}</span></div>
                <div className={`rounded-lg p-3 flex justify-between font-bold ${statements.balance?.totals?.balanced ? 'bg-emerald-50 text-emerald-800' : 'bg-red-50 text-red-800'}`}>
                  <span>Bilanço dengesi</span><span>{statements.balance?.totals?.balanced ? 'Dengeli' : `Fark: ${fmtMoney(statements.balance?.totals?.difference || 0)}`}</span>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="workspace">
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card><CardContent className="pt-6"><Landmark className="w-7 h-7 text-amber-600 mb-3" /><p className="text-sm text-slate-500">Tedarikçi Borçları</p><p className="text-2xl font-bold">{fmtMoney(workspace.aging?.total_outstanding || 0)}</p><p className="text-xs text-slate-500 mt-2">90+ gün: {fmtMoney(workspace.aging?.buckets?.d90_plus || 0)}</p></CardContent></Card>
            <Card><CardContent className="pt-6"><TrendingUp className="w-7 h-7 text-red-600 mb-3" /><p className="text-sm text-slate-500">Gider Bütçesi · Bu Ay</p><p className="text-2xl font-bold">{fmtMoney(workspace.expenseBudget?.totals?.actual || 0)}</p><p className="text-xs text-slate-500 mt-2">Bütçe: {fmtMoney(workspace.expenseBudget?.totals?.budget || 0)}</p></CardContent></Card>
            <Card><CardContent className="pt-6"><TrendingUp className="w-7 h-7 text-emerald-600 mb-3" /><p className="text-sm text-slate-500">Gelir Bütçesi · Bu Ay</p><p className="text-2xl font-bold">{fmtMoney(workspace.revenueBudget?.totals?.actual || 0)}</p><p className="text-xs text-slate-500 mt-2">Bütçe: {fmtMoney(workspace.revenueBudget?.totals?.budget || 0)}</p></CardContent></Card>
            <Card><CardContent className="pt-6"><PackageOpen className="w-7 h-7 text-indigo-600 mb-3" /><p className="text-sm text-slate-500">Sabit Kıymetler</p><p className="text-2xl font-bold">{workspace.assets.length}</p><p className="text-xs text-slate-500 mt-2">Net defter değeri: {fmtMoney(workspace.assets.reduce((sum, item) => sum + (Number(item.book_value) || 0), 0))}</p></CardContent></Card>
          </div>
          <p className="text-xs text-slate-500 mt-4">Bu özetler AP, bütçe ve sabit kıymet alt defterlerindeki gerçek tenant verisinden okunur; örnek/sabit rakam kullanılmaz.</p>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default GeneralLedgerModule;
