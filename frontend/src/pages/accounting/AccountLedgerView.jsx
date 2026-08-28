import React, { useMemo, useState } from 'react';
import { BookOpenCheck, Search } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';

const lineAmount = (line, field) => {
  const direct = Number(line?.[field]);
  if (Number.isFinite(direct)) return direct;
  const minor = Number(line?.[`${field}_minor`]);
  return Number.isFinite(minor) ? minor / 100 : 0;
};

export const buildAccountLedgerRows = (journals = [], accounts = [], filters = {}) => {
  const accountNames = new Map(accounts.map((account) => [String(account.code), account.name]));
  const accountQuery = String(filters.account || '').trim().toLocaleLowerCase('tr-TR');
  const descriptionQuery = String(filters.description || '').trim().toLocaleLowerCase('tr-TR');
  const documentQuery = String(filters.document || '').trim().toLocaleLowerCase('tr-TR');

  const rows = journals
    .flatMap((journal) => (journal.lines || []).map((line, index) => ({
      id: `${journal.id || journal.entry_no || journal.date}-${line.line_no ?? index}`,
      date: journal.date || '',
      documentNo: journal.entry_no || journal.source_ref || '-',
      accountCode: String(line.account_code || ''),
      accountName: line.account_name || accountNames.get(String(line.account_code || '')) || '-',
      description: line.memo || journal.memo || '-',
      debit: lineAmount(line, 'debit'),
      credit: lineAmount(line, 'credit'),
    })))
    .filter((row) => !filters.start || row.date >= filters.start)
    .filter((row) => !filters.end || row.date <= filters.end)
    .filter((row) => !accountQuery || `${row.accountCode} ${row.accountName}`.toLocaleLowerCase('tr-TR').includes(accountQuery))
    .filter((row) => !descriptionQuery || row.description.toLocaleLowerCase('tr-TR').includes(descriptionQuery))
    .filter((row) => !documentQuery || row.documentNo.toLocaleLowerCase('tr-TR').includes(documentQuery))
    .sort((left, right) => left.date.localeCompare(right.date) || left.documentNo.localeCompare(right.documentNo, 'tr'));

  const runningByAccount = new Map();
  const withBalance = rows.map((row) => {
    const balance = (runningByAccount.get(row.accountCode) || 0) + row.debit - row.credit;
    runningByAccount.set(row.accountCode, balance);
    return { ...row, balance };
  });

  return {
    rows: withBalance,
    totals: withBalance.reduce((totals, row) => ({
      debit: totals.debit + row.debit,
      credit: totals.credit + row.credit,
    }), { debit: 0, credit: 0 }),
  };
};

export const AccountLedgerView = ({ journals, accounts, formatMoney }) => {
  const [filters, setFilters] = useState({ start: '', end: '', account: '', description: '', document: '' });
  const ledger = useMemo(() => buildAccountLedgerRows(journals, accounts, filters), [journals, accounts, filters]);
  const updateFilter = (name, value) => setFilters((current) => ({ ...current, [name]: value }));

  return (
    <Card data-testid="gl-account-ledger">
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><BookOpenCheck className="h-5 w-5 text-blue-600" /> Muavin Defteri</CardTitle>
        <p className="text-sm text-slate-500">Hesap hareketlerini tarih, hesap, açıklama veya fiş numarasıyla inceleyin.</p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 rounded-xl border bg-slate-50 p-3 sm:grid-cols-2 xl:grid-cols-5">
          <label className="text-xs font-medium text-slate-600">Başlangıç
            <Input type="date" className="mt-1 bg-white" value={filters.start} onChange={(event) => updateFilter('start', event.target.value)} />
          </label>
          <label className="text-xs font-medium text-slate-600">Bitiş
            <Input type="date" className="mt-1 bg-white" value={filters.end} onChange={(event) => updateFilter('end', event.target.value)} />
          </label>
          <label className="text-xs font-medium text-slate-600">Hesap kodu veya adı
            <Input className="mt-1 bg-white" value={filters.account} onChange={(event) => updateFilter('account', event.target.value)} placeholder="100 Kasa" list="gl-account-options" />
            <datalist id="gl-account-options">{accounts.map((account) => <option key={account.code} value={`${account.code} ${account.name}`} />)}</datalist>
          </label>
          <label className="text-xs font-medium text-slate-600">Açıklama
            <Input className="mt-1 bg-white" value={filters.description} onChange={(event) => updateFilter('description', event.target.value)} placeholder="İşlem açıklaması" />
          </label>
          <label className="text-xs font-medium text-slate-600">Fiş / belge no
            <span className="relative mt-1 block">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <Input className="bg-white pl-9" value={filters.document} onChange={(event) => updateFilter('document', event.target.value)} placeholder="YEV-..." />
            </span>
          </label>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
          <p>{ledger.rows.length} hareket gösteriliyor</p>
          <p>Bakiye, seçili filtre aralığında hesap bazında yürütülür.</p>
        </div>

        <div className="overflow-x-auto rounded-lg border">
          <table className="min-w-[900px] w-full text-sm">
            <thead className="bg-slate-50 text-left text-slate-600">
              <tr>
                <th className="p-3">Tarih</th><th className="p-3">Fiş / Belge No</th><th className="p-3">Hesap</th><th className="p-3">Açıklama</th>
                <th className="p-3 text-right">Borç</th><th className="p-3 text-right">Alacak</th><th className="p-3 text-right">Bakiye</th>
              </tr>
            </thead>
            <tbody>
              {ledger.rows.map((row) => (
                <tr key={row.id} className="border-t hover:bg-blue-50/40">
                  <td className="whitespace-nowrap p-3">{row.date}</td>
                  <td className="whitespace-nowrap p-3 font-medium text-blue-700">{row.documentNo}</td>
                  <td className="p-3"><span className="font-semibold">{row.accountCode}</span><span className="ml-2 text-slate-500">{row.accountName}</span></td>
                  <td className="max-w-[280px] truncate p-3" title={row.description}>{row.description}</td>
                  <td className="p-3 text-right text-rose-700">{row.debit ? formatMoney(row.debit) : '-'}</td>
                  <td className="p-3 text-right text-emerald-700">{row.credit ? formatMoney(row.credit) : '-'}</td>
                  <td className="p-3 text-right font-semibold">{formatMoney(Math.abs(row.balance))} {row.balance < 0 ? 'A' : row.balance > 0 ? 'B' : ''}</td>
                </tr>
              ))}
              {ledger.rows.length === 0 && <tr><td colSpan="7" className="p-10 text-center text-slate-500">Filtrelere uygun muhasebe hareketi bulunamadı.</td></tr>}
            </tbody>
            <tfoot className="border-t-2 bg-slate-50 font-bold">
              <tr><td colSpan="4" className="p-3 text-right">TOPLAM</td><td className="p-3 text-right text-rose-700">{formatMoney(ledger.totals.debit)}</td><td className="p-3 text-right text-emerald-700">{formatMoney(ledger.totals.credit)}</td><td className="p-3" /></tr>
            </tfoot>
          </table>
        </div>
      </CardContent>
    </Card>
  );
};

