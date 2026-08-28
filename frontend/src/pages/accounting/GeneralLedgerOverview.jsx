import React from 'react';
import { BarChart3, BookOpenCheck, CheckCircle2, FileText, ListTree, Plus, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export const GeneralLedgerOverview = ({ accounts, vouchers, trialBalance, periods, onSelect }) => {
  const reviewCount = vouchers.filter((voucher) => ['draft', 'submitted', 'approved', 'posting'].includes(voucher.status)).length;
  const openPeriods = periods.filter((period) => period.status === 'open').length;
  const balanced = trialBalance.totals?.balanced !== false;
  const quickActions = [
    { tab: 'journals', label: 'Yeni Fiş', description: 'Hızlı fiş girişini aç', icon: Plus, primary: true },
    { tab: 'account-ledger', label: 'Muavin', description: 'Hesap hareketlerini incele', icon: BookOpenCheck },
    { tab: 'trial-balance', label: 'Mizan', description: 'Borç ve alacak kontrolü', icon: BarChart3 },
    { tab: 'statements', label: 'Mali Tablolar', description: 'Gelir tablosu ve bilanço', icon: FileText },
  ];
  return (
    <div className="space-y-5" data-testid="gl-overview">
      <Card className="overflow-hidden border-blue-100 bg-gradient-to-br from-blue-50 via-white to-indigo-50">
        <CardContent className="flex flex-col gap-5 p-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="mb-1 flex items-center gap-2 text-sm font-semibold text-blue-700"><Zap className="h-4 w-4" /> Muhasebeci çalışma alanı</p>
            <h2 className="text-2xl font-bold text-slate-900">Sık kullanılan işlemler tek ekranda</h2>
            <p className="mt-1 max-w-2xl text-sm text-slate-600">Fiş girişi, muavin, mizan ve mali tablolara sol menüden veya aşağıdaki kısayollardan ulaşın.</p>
          </div>
          <Button onClick={() => onSelect('journals')} className="shrink-0"><Plus className="mr-2 h-4 w-4" /> Yeni Muhasebe Fişi</Button>
        </CardContent>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Card><CardContent className="pt-5"><ListTree className="mb-3 h-5 w-5 text-blue-600" /><p className="text-xs font-medium text-slate-500">AKTİF HESAP</p><p className="mt-1 text-2xl font-bold">{accounts.filter((account) => account.active !== false).length}</p></CardContent></Card>
        <Card><CardContent className="pt-5"><FileText className="mb-3 h-5 w-5 text-amber-600" /><p className="text-xs font-medium text-slate-500">İŞLEM BEKLEYEN FİŞ</p><p className="mt-1 text-2xl font-bold">{reviewCount}</p></CardContent></Card>
        <Card><CardContent className="pt-5"><CheckCircle2 className={`mb-3 h-5 w-5 ${balanced ? 'text-emerald-600' : 'text-red-600'}`} /><p className="text-xs font-medium text-slate-500">MİZAN DURUMU</p><p className={`mt-1 text-lg font-bold ${balanced ? 'text-emerald-700' : 'text-red-700'}`}>{balanced ? 'Dengeli' : 'Kontrol Gerekli'}</p></CardContent></Card>
        <Card><CardContent className="pt-5"><BookOpenCheck className="mb-3 h-5 w-5 text-indigo-600" /><p className="text-xs font-medium text-slate-500">AÇIK MALİ DÖNEM</p><p className="mt-1 text-2xl font-bold">{openPeriods}</p></CardContent></Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Hızlı İşlemler</CardTitle></CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {quickActions.map((action) => {
            const Icon = action.icon;
            return <button key={action.tab} type="button" onClick={() => onSelect(action.tab)} className={`rounded-xl border p-4 text-left transition hover:-translate-y-0.5 hover:shadow-md ${action.primary ? 'border-blue-200 bg-blue-50' : 'bg-white hover:border-blue-200'}`}><Icon className="mb-3 h-5 w-5 text-blue-600" /><span className="block font-semibold text-slate-900">{action.label}</span><span className="mt-1 block text-xs text-slate-500">{action.description}</span></button>;
          })}
        </CardContent>
      </Card>
    </div>
  );
};

