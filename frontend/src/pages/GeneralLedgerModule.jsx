import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useCurrency } from '@/context/CurrencyContext';
import { formatAmount } from '@/lib/currency';
import { Plus, Save, FileText, Check, AlertCircle } from 'lucide-react';

const GeneralLedgerModule = () => {
  const { amount: fmtMoney } = useCurrency();
  const [activeTab, setActiveTab] = useState('accounts');
  
  const [accounts, setAccounts] = useState([]);
  const [journals, setJournals] = useState([]);
  const [trialBalance, setTrialBalance] = useState({ lines: [], totals: {} });
  
  // New Journal Entry State
  const [newJournal, setNewJournal] = useState({
    date: new Date().toISOString().split('T')[0],
    type: 'Mahsup',
    description: '',
    lines: [
      { account_code: '', debit: 0, credit: 0, description: '' },
      { account_code: '', debit: 0, credit: 0, description: '' }
    ]
  });

  const fetchAccounts = async () => {
    try {
      const res = await axios.get('/finance/gl/accounts');
      setAccounts(res.data);
    } catch (e) { console.error(e); }
  };

  const fetchJournals = async () => {
    try {
      const res = await axios.get('/finance/gl/journals');
      setJournals(res.data);
    } catch (e) { console.error(e); }
  };

  const fetchTrialBalance = async () => {
    try {
      const res = await axios.get('/finance/gl/trial-balance');
      setTrialBalance(res.data);
    } catch (e) { console.error(e); }
  };

  useEffect(() => {
    if (activeTab === 'accounts') fetchAccounts();
    if (activeTab === 'journals') fetchJournals();
    if (activeTab === 'trial-balance') fetchTrialBalance();
  }, [activeTab]);

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

    try {
      await axios.post('/finance/gl/journals', newJournal);
      toast.success('Yevmiye fişi başarıyla kaydedildi.');
      setNewJournal({
        date: new Date().toISOString().split('T')[0],
        type: 'Mahsup',
        description: '',
        lines: [
          { account_code: '', debit: 0, credit: 0, description: '' },
          { account_code: '', debit: 0, credit: 0, description: '' }
        ]
      });
      fetchJournals();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fiş kaydedilirken hata oluştu.');
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
                    <tr><td colSpan="4" className="text-center p-8 text-gray-500">Kayıtlı hesap bulunamadı.</td></tr>
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
                    <Button onClick={handleSubmitJournal} className="bg-blue-600 hover:bg-blue-700 text-white"><Save className="w-4 h-4 mr-2" /> Fişi Kaydet</Button>
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
                    <div key={j.id} className="p-3 border rounded-lg hover:border-blue-300 transition-colors cursor-pointer bg-white">
                      <div className="flex justify-between items-start mb-2">
                        <div>
                          <span className="text-xs font-bold px-2 py-1 bg-gray-100 text-gray-600 rounded-full">{j.type}</span>
                          <span className="text-xs text-gray-400 ml-2">{j.date}</span>
                        </div>
                        <span className="font-bold text-gray-900">{fmtMoney(j.total)}</span>
                      </div>
                      <p className="text-sm text-gray-600 truncate">{j.description}</p>
                    </div>
                  ))}
                  {journals.length === 0 && <p className="text-center text-sm text-gray-500 py-4">Henüz fiş girilmemiş.</p>}
                </CardContent>
              </Card>
            </div>
          </div>
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
              {trialBalance.totals && trialBalance.totals.total_debit !== trialBalance.totals.total_credit && (
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
      </Tabs>
    </div>
  );
};

export default GeneralLedgerModule;
