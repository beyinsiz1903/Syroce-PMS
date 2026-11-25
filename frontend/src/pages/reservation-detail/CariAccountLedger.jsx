import { useEffect, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { fmtCurrency, fmtTs } from './helpers';

const labels = { charge: 'Hesaba eklenen alacak', adjustment: 'Hesaptan düşülen düzeltme', transfer_in: 'Acenteye devralınan alacak', transfer_out: 'Başka hesaba devredilen alacak', debit: 'Hesaba eklenen alacak', credit: 'Hesaptan düşülen tutar', payment: 'Cari ödeme', reconciliation: 'Hesap düzeltmesi' };

// These are the same debit/credit kinds used by cari_receivable_reporting.
// Amount is an unsigned source value; do not imply an effect for unknown kinds.
const effectSign = { charge: 1, transfer_in: 1, payment: -1, adjustment: -1, transfer_out: -1 };
function balanceEffect(row) {
  if (row.voided || row.deleted || (row.status != null && !['completed', 'posted'].includes(row.status))) return 'Bakiyeye dahil değil';
  const amount = Number(row.amount);
  const sign = effectSign[row.transaction_type];
  if (!row.currency || row.amount == null || row.amount === '' || !Number.isFinite(amount) || sign == null) return 'Etki doğrulanamadı';
  const effect = sign * amount;
  return `${effect > 0 ? '+' : effect < 0 ? '−' : ''}${fmtCurrency(Math.abs(effect), row.currency)}`;
}

export default function CariAccountLedger() {
  const [accounts, setAccounts] = useState([]);
  const [accountId, setAccountId] = useState('');
  const [rows, setRows] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(''); setAccounts([]); setRows([]);
    (async () => {
      try {
        const response = await axios.get('/pms/cari-accounts');
        if (!active) return;
        const available = (response.data.accounts || []).filter(account => account.account_source === 'cari_accounts');
        setAccounts(available);
        if (accountId && available.some(account => account.id === accountId)) {
          const transactions = await axios.get(`/pms/cari-accounts/${encodeURIComponent(accountId)}/transactions`);
          if (active) setRows(transactions.data.transactions || []);
        }
      } catch {
        if (active) { setAccounts([]); setRows([]); setError('Cari hesap hareketleri yüklenemedi. Yenileyerek tekrar deneyin.'); }
      } finally { if (active) setLoading(false); }
    })();
    return () => { active = false; };
  }, [accountId, revision]);
  const account = accounts.find(item => item.id === accountId);
  return <section className="rounded border p-4 space-y-3" aria-label="Cari hesap hareketleri">
    <div className="flex justify-between gap-2"><h3 className="font-semibold">Cari hesap hareketleri</h3><Button type="button" variant="outline" onClick={() => setRevision(value => value + 1)} disabled={loading}>Hareketleri yenile</Button></div>
    <p className="text-sm text-muted-foreground">Seçilen cari hesabın tüm rezervasyonlardaki hareketleri gösterilir. Alacak devri, kasaya para girişi değildir. Eski şehir hesabı hareketleri Cari Hesaplar ekranında izlenir. Bakiyeye etkide + alacağı artırır, − azaltır.</p>
    <label className="block text-sm">Cari hesap
      <select aria-label="Hareketleri gösterilecek cari hesap" className="block w-full rounded border p-2" value={accountId} onChange={event => setAccountId(event.target.value)} disabled={loading}>
        <option value="">Hesap seçin</option>
        {accounts.map(item => <option key={item.id} value={item.id}>{item.name} ({item.currency || 'para birimi eksik'})</option>)}
      </select>
    </label>
    {loading && <p role="status">Hareketler yükleniyor...</p>}
    {error && <p role="alert">{error}</p>}
    {!loading && account && <>
      <p>Hesap bakiyesi: <strong>{account.currency ? fmtCurrency(account.balance, account.currency) : 'Para birimi doğrulanamadı'}</strong></p>
      {rows.length === 0 ? <p>Bu hesap için kayıtlı hareket yok.</p> : <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr><th>Tarih</th><th>İş günü</th><th>İşlem</th><th>Açıklama / referans</th><th>İşlem tutarı</th><th>Bakiyeye etkisi</th></tr></thead><tbody>
        {rows.map((row, index) => <tr key={row.id || index} className="border-t"><td>{fmtTs(row.created_at)}</td><td>{row.business_date || 'Belirtilmemiş'}</td><td>{labels[row.transaction_type] || 'Diğer cari hareket'}</td><td>{row.description || row.reference || '—'}</td><td>{row.currency ? fmtCurrency(row.amount, row.currency) : 'Para birimi eksik'}</td><td>{balanceEffect(row)}</td></tr>)}
      </tbody></table></div>}
    </>}
  </section>;
}
