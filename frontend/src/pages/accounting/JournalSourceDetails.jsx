import React from 'react';
import { Input } from '@/components/ui/input';
import { formatCurrency } from '@/lib/currency';

const amount = (line, field) => line[`${field}_minor`] != null
  ? Number(line[`${field}_minor`]) / 100 : Number(line[field] || 0);

export function JournalSourceDetails({ journal, accounts = [], currency = 'TRY' }) {
  const names = new Map(accounts.map(account => [account.code, account.name]));
  return <details className="mt-3 rounded border p-2 text-sm">
    <summary className="cursor-pointer font-medium">Fiş detayını ve kaynak kimliğini göster</summary>
    <div className="mt-3 space-y-3">
      <p className="break-words">{journal.memo || 'Açıklama yok'}</p>
      <label className="block">Kaynak fiş kimliği
        <Input className="mt-1 font-mono text-xs" readOnly value={journal.id || ''} onFocus={event => event.target.select()} />
      </label>
      <p className="text-xs text-muted-foreground">Hediye kartı / cüzdan kaynağı tanımlarken bu kimliği kullanın. Fişin varlığı kullanılabilir bakiye garantisi değildir; hesap, para birimi, mühür ve önceki kullanımlar kaydetme sırasında kontrol edilir.</p>
      <p>Durum: {journal.status === 'posted' ? 'Yevmiyede' : journal.status || 'Belirtilmemiş'}{journal.reversal_status === 'reversed' ? ' · Ters kaydı var' : ''}</p>
      <p className="text-xs">{journal.entry_hash ? 'Mühür bilgisi kayıtlı; bütünlük sonucu ayrıca denetlenir.' : 'Özgün mühür bilgisi yok; mühürlü fonlama olarak kullanılamaz.'}</p>
      <div className="overflow-x-auto"><table className="w-full text-xs">
        <caption className="text-left">Özgün fiş satırları · borç / alacak {currency}</caption>
        <thead><tr><th className="text-left">Hesap</th><th className="text-right">Borç</th><th className="text-right">Alacak</th><th className="text-right">Özgün döviz tutarı</th></tr></thead>
        <tbody>{(journal.lines || []).map((line, index) => <tr key={line.line_no ?? index}>
          <td className="py-2">{line.account_code} · {line.account_name || names.get(line.account_code) || 'Hesap adı yok'}</td>
          <td className="text-right">{formatCurrency(amount(line, 'debit'), currency, { decimals: 2, compactDecimals: false })}</td>
          <td className="text-right">{formatCurrency(amount(line, 'credit'), currency, { decimals: 2, compactDecimals: false })}</td>
          <td className="text-right">{line.currency && (line.foreign_amount_minor != null || line.foreign_amount != null)
            ? formatCurrency(line.foreign_amount_minor != null ? line.foreign_amount_minor / 100 : line.foreign_amount, line.currency, { decimals: 2, compactDecimals: false }) : '—'}</td>
        </tr>)}</tbody>
      </table></div>
      {!(journal.lines || []).length && <p>Bu kaydın satır ayrıntıları yok; kaynak incelemesi gerekli.</p>}
    </div>
  </details>;
}
