import { useCallback, useEffect, useMemo, useState } from 'react';
import api from '@/api/axios';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { AlertTriangle, CheckCircle2, Download, FileSpreadsheet, Loader2, RefreshCw, Scale } from 'lucide-react';
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';
import { SectionHeader } from './ReportHelpers';

const REPORTS = {
  gl_trial_balance: {
    title: 'Genel Muhasebe Mizanı',
    description: 'Yevmiye kayıtlarından hesaplanan borç, alacak ve hesap bakiyeleri',
    endpoint: '/gl/trial-balance',
    exportName: 'trial_balance',
  },
  income_statement: {
    title: 'Gelir Tablosu',
    description: 'Seçili dönemde muhasebeleşen gelir, gider ve net faaliyet sonucu',
    endpoint: '/gl/statements/income-statement',
    exportName: 'income_statement',
  },
  balance_sheet: {
    title: 'Bilanço',
    description: 'Seçili tarih itibarıyla varlık, yükümlülük ve özkaynak dengesi',
    endpoint: '/gl/statements/balance-sheet',
    exportName: 'balance_sheet',
  },
  journal: {
    title: 'Yevmiye Defteri',
    description: 'Onaylanmış muhasebe fişlerinin tarih ve belge sırasındaki dökümü',
    endpoint: '/gl/journal',
    exportName: 'journal',
  },
};

const periodStart = (date, period) => {
  if (!date || period === 'daily') return date;
  const value = new Date(`${date}T12:00:00`);
  value.setDate(value.getDate() - 29);
  return value.toISOString().slice(0, 10);
};

const money = (value) => formatCurrency(value, cachedTenantCurrency(), { decimals: 2, compactDecimals: false });

const SummaryCard = ({ label, value, intent = 'default' }) => {
  const color = intent === 'success' ? 'text-emerald-700' : intent === 'danger' ? 'text-rose-700' : 'text-slate-900';
  return <Card className="border-slate-200 shadow-none"><CardContent className="p-4">
    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
    <p className={`mt-1 text-xl font-bold ${color}`}>{value}</p>
  </CardContent></Card>;
};

const AccountTable = ({ rows, amountKey = 'amount', balanceColumns = false }) => (
  <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
    <table className="w-full text-sm">
      <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
        <tr>
          <th className="px-4 py-3 text-left font-semibold">Hesap</th>
          <th className="px-4 py-3 text-left font-semibold">Hesap adı</th>
          {balanceColumns ? <>
            <th className="px-4 py-3 text-right font-semibold">Borç toplamı</th>
            <th className="px-4 py-3 text-right font-semibold">Alacak toplamı</th>
            <th className="px-4 py-3 text-right font-semibold">Borç bakiye</th>
            <th className="px-4 py-3 text-right font-semibold">Alacak bakiye</th>
          </> : <th className="px-4 py-3 text-right font-semibold">Tutar</th>}
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {rows.map((row) => <tr key={`${row.account_code}-${row.account_name}`} className="hover:bg-slate-50/70">
          <td className="whitespace-nowrap px-4 py-3 font-mono text-xs font-semibold text-slate-700">{row.account_code}</td>
          <td className="px-4 py-3 text-slate-700">{row.account_name}</td>
          {balanceColumns ? <>
            <td className="px-4 py-3 text-right tabular-nums">{money(row.total_debit)}</td>
            <td className="px-4 py-3 text-right tabular-nums">{money(row.total_credit)}</td>
            <td className="px-4 py-3 text-right font-medium tabular-nums">{money(row.debit_balance)}</td>
            <td className="px-4 py-3 text-right font-medium tabular-nums">{money(row.credit_balance)}</td>
          </> : <td className="px-4 py-3 text-right font-semibold tabular-nums">{money(row[amountKey])}</td>}
        </tr>)}
      </tbody>
    </table>
  </div>
);

export default function AccountingStatementsSection({ type, reportDate, reportPeriod }) {
  const config = REPORTS[type] || REPORTS.gl_trial_balance;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const start = useMemo(() => periodStart(reportDate, reportPeriod), [reportDate, reportPeriod]);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = ['income_statement', 'journal'].includes(type) ? { start, end: reportDate } : { as_of: reportDate };
      const response = await api.get(config.endpoint, { params });
      setData(response.data);
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || requestError?.message || 'Rapor yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, [config.endpoint, reportDate, start, type]);

  useEffect(() => { load(); }, [load]);

  const download = (format) => {
    const params = new URLSearchParams({ report: config.exportName, format });
    if (['income_statement', 'journal'].includes(type)) {
      params.set('start', start);
      params.set('end', reportDate);
    } else params.set('as_of', reportDate);
    window.open(`/api/gl/reports/export?${params.toString()}`, '_blank', 'noopener,noreferrer');
  };

  const totalRows = type === 'income_statement'
    ? (data?.revenue?.length || 0) + (data?.expenses?.length || 0)
    : type === 'balance_sheet'
      ? (data?.assets?.length || 0) + (data?.liabilities?.length || 0) + (data?.equity?.length || 0)
      : type === 'journal' ? data?.entries?.length || 0 : data?.rows?.length || 0;
  // An empty trial balance has zero debit and zero credit. It is not an
  // imbalance; older API responses may omit `balanced`, so fail closed only
  // when there are actual rows and the backend explicitly reports a mismatch.
  const trialBalanceHasEntries = type === 'gl_trial_balance' && totalRows > 0;
  const trialBalanceBalanced = type === 'gl_trial_balance'
    && (!trialBalanceHasEntries || data?.totals?.balanced !== false);

  return <div className="space-y-5" data-testid={`section-${type}`}>
    <SectionHeader title={config.title} description={config.description} icon={type === 'gl_trial_balance' ? Scale : FileSpreadsheet} actions={<>
      <Button variant="outline" size="sm" onClick={() => download('xlsx')} disabled={!data}><Download className="mr-1.5 h-4 w-4" />Excel</Button>
      <Button variant="outline" size="sm" onClick={load} disabled={loading}><RefreshCw className={`mr-1.5 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />Yenile</Button>
    </>} />

    {loading && !data && <div className="flex min-h-64 items-center justify-center rounded-xl border border-slate-200 bg-white text-sm text-slate-500"><Loader2 className="mr-2 h-5 w-5 animate-spin" />Muhasebe kayıtları hesaplanıyor…</div>}
    {error && <div className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"><AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" /><div><p className="font-semibold">Rapor alınamadı</p><p className="mt-0.5">{String(error)}</p></div></div>}

    {data && <>
      {type === 'gl_trial_balance' && <>
        <div className="grid gap-3 sm:grid-cols-3">
          <SummaryCard label="Borç bakiyesi" value={money(data.totals?.debit_balance)} />
          <SummaryCard label="Alacak bakiyesi" value={money(data.totals?.credit_balance)} />
          <SummaryCard
            label="Mizan kontrolü"
            value={trialBalanceHasEntries ? (trialBalanceBalanced ? 'Dengeli' : 'Dengesiz') : 'Dengeli — kayıt yok'}
            intent={trialBalanceBalanced ? 'success' : 'danger'}
          />
        </div>
        <AccountTable rows={data.rows || []} balanceColumns />
      </>}
      {type === 'income_statement' && <>
        <div className="grid gap-3 sm:grid-cols-3">
          <SummaryCard label="Toplam gelir" value={money(data.totals?.revenue)} />
          <SummaryCard label="Toplam gider" value={money(data.totals?.expenses)} />
          <SummaryCard label="Net dönem sonucu" value={money(data.totals?.net_income)} intent={Number(data.totals?.net_income) >= 0 ? 'success' : 'danger'} />
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="space-y-2"><h3 className="text-sm font-semibold text-slate-800">Gelir hesapları</h3><AccountTable rows={data.revenue || []} /></div>
          <div className="space-y-2"><h3 className="text-sm font-semibold text-slate-800">Gider hesapları</h3><AccountTable rows={data.expenses || []} /></div>
        </div>
      </>}
      {type === 'balance_sheet' && <>
        <div className="grid gap-3 sm:grid-cols-3">
          <SummaryCard label="Toplam varlık" value={money(data.totals?.assets)} />
          <SummaryCard label="Borçlar + özkaynak" value={money(data.totals?.liabilities_and_equity)} />
          <SummaryCard label="Bilanço kontrolü" value={data.totals?.balanced ? 'Dengeli' : `Fark ${money(data.totals?.difference)}`} intent={data.totals?.balanced ? 'success' : 'danger'} />
        </div>
        <div className="grid gap-4 xl:grid-cols-3">
          {[['Varlıklar', data.assets], ['Yükümlülükler', data.liabilities], ['Özkaynaklar', data.equity]].map(([label, rows]) => <div key={label} className="space-y-2"><h3 className="text-sm font-semibold text-slate-800">{label}</h3><AccountTable rows={rows || []} /></div>)}
        </div>
      </>}
      {type === 'journal' && <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500"><tr>
            <th className="px-4 py-3 text-left font-semibold">Tarih</th><th className="px-4 py-3 text-left font-semibold">Fiş no</th><th className="px-4 py-3 text-left font-semibold">Açıklama</th><th className="px-4 py-3 text-left font-semibold">Kaynak</th><th className="px-4 py-3 text-right font-semibold">Borç</th><th className="px-4 py-3 text-right font-semibold">Alacak</th>
          </tr></thead>
          <tbody className="divide-y divide-slate-100">{(data.entries || []).map(entry => {
            const totals = (entry.lines || []).reduce((sum, line) => ({ debit: sum.debit + Number(line.debit || 0), credit: sum.credit + Number(line.credit || 0) }), { debit: 0, credit: 0 });
            return <tr key={entry.id || entry.entry_no} className="hover:bg-slate-50/70"><td className="whitespace-nowrap px-4 py-3 text-slate-600">{entry.date || '—'}</td><td className="whitespace-nowrap px-4 py-3 font-mono text-xs font-semibold text-slate-700">{entry.entry_no || '—'}</td><td className="max-w-sm truncate px-4 py-3 text-slate-700">{entry.memo || entry.description || '—'}</td><td className="px-4 py-3 text-slate-500">{entry.source || 'Manuel'}</td><td className="px-4 py-3 text-right font-medium tabular-nums">{money(totals.debit)}</td><td className="px-4 py-3 text-right font-medium tabular-nums">{money(totals.credit)}</td></tr>;
          })}</tbody>
        </table>
      </div>}
      {!totalRows && <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center"><CheckCircle2 className="mx-auto mb-2 h-7 w-7 text-slate-300" /><p className="text-sm font-medium text-slate-700">Bu dönem için muhasebeleşmiş hareket bulunmuyor.</p><p className="mt-1 text-xs text-slate-500">Rapor yalnızca onaylanmış yevmiye kayıtlarını kullanır.</p></div>}
    </>}
  </div>;
}
