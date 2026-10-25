import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { formatCurrency } from '@/lib/currency';

const message = error => typeof error?.response?.data?.detail === 'string' ? error.response.data.detail
  : error?.response?.data?.detail?.message || 'İşlem doğrulanamadı. Aynı isteği tekrar deneyebilir veya güncel önizlemeyi okuyabilirsiniz.';

export default function AccountProjectionRepair({ issues = [], user, onRepaired }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState('');
  const [preview, setPreview] = useState(null);
  const [reason, setReason] = useState('');
  const [reference, setReference] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [submission, setSubmission] = useState(null);
  const generation = useRef(0);
  useEffect(() => () => { generation.current += 1; }, []);
  const candidates = issues.filter(issue => issue.reason === 'account_projection_differs_from_sources'
    && /^(cari_accounts|city_ledger_accounts):[^/]+$/.test(issue.account_id));
  if (!['admin', 'super_admin'].includes(user?.role) || !candidates.length) return null;

  const load = async key => {
    const request = ++generation.current;
    setSelected(key); setPreview(null); setError(''); setResult(null); setSubmission(null);
    setConfirmed(false); setReason(''); setReference(''); setBusy(true);
    const [source, id] = key.split(':');
    try {
      const response = await axios.get(`/pms/account-projections/${source}/${encodeURIComponent(id)}/preview`);
      if (request === generation.current) setPreview(response.data);
    } catch (err) {
      if (request === generation.current) setError(message(err));
    } finally {
      if (request === generation.current) setBusy(false);
    }
  };
  const apply = async () => {
    if (busy || result || !preview?.repairable || !preview?.needs_repair || !confirmed || reason.trim().length < 10 || reference.trim().length < 10) return;
    const request = generation.current;
    const body = submission || { request_id: globalThis.crypto.randomUUID(), source_fingerprint: preview.source_fingerprint,
      reason: reason.trim(), source_review_reference: reference.trim(), confirm_sources_authoritative: true };
    setSubmission(body); setBusy(true); setError('');
    try {
      const response = await axios.post(`/pms/account-projections/${preview.source}/${encodeURIComponent(preview.account_id)}/repair`, body);
      if (request !== generation.current) return;
      setResult(response.data);
      onRepaired?.();
    } catch (err) {
      if (request === generation.current) setError(message(err));
    } finally {
      if (request === generation.current) setBusy(false);
    }
  };
  const amount = value => formatCurrency(value, preview.currency, { decimals: 2, compactDecimals: false });

  return <>
    <Button size="sm" variant="outline" className="mt-2" onClick={() => setOpen(true)}>Cari kaynak farklarını incele</Button>
    <Dialog open={open} onOpenChange={value => { if (!busy) setOpen(value); }}>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader><DialogTitle>Cari kaynak / bakiye kontrolü</DialogTitle>
          <DialogDescription>Bu işlem tahsilat, ikram veya borç silme değildir. Kaynak hareketleri değişmez; yalnız türetilmiş hesap bakiyesi gerekçesiyle yeniden kurulur.</DialogDescription>
        </DialogHeader>
        <label className="text-sm">Hesap
          <select className="block w-full rounded border p-2" aria-label="Düzeltilecek cari hesap" value={selected} disabled={busy} onChange={event => load(event.target.value)}>
            <option value="" disabled>Hesap seçin</option>
            {candidates.map(issue => <option key={issue.account_id} value={issue.account_id}>{issue.account_name || issue.account_id} · {issue.account_currency || '—'}</option>)}
          </select>
        </label>
        {busy && <p role="status">Kontrol ediliyor…</p>}
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        {preview && <div className="space-y-3 text-sm">
          <p>Hesap: {preview.account_name || preview.account_id}</p>
          <p>Kaynak hareketi: {preview.source_transaction_count}. Hesap para birimi: {preview.currency}.</p>
          <p>Kayıtlı bakiye: {Object.values(preview.cached_balances).map(amount).join(' / ')}. Kaynak bakiyesi: {preview.source_balance == null ? 'Doğrulanamadı' : amount(preview.source_balance)}.</p>
          {!preview.repairable && <p role="alert">Kaynaklar otomatik düzeltmeye uygun değil: {preview.blocked_reasons.join(', ')}. Eksik hareketleri ödeme/borç silme ile kapatmayın.</p>}
          {preview.repairable && !preview.needs_repair && <p>Bakiye zaten kaynaklarla eşleşiyor.</p>}
          {preview.repairable && preview.needs_repair && !result && <>
            <label className="block">Düzeltme gerekçesi
              <textarea aria-label="Düzeltme gerekçesi" className="block w-full rounded border p-2" maxLength={2000} value={reason} disabled={busy || !!submission} onChange={event => setReason(event.target.value)} />
            </label>
            <label className="block">İncelenen kaynak dökümü / belge referansı
              <textarea aria-label="Kaynak inceleme referansı" className="block w-full rounded border p-2" maxLength={1000} value={reference} disabled={busy || !!submission} onChange={event => setReference(event.target.value)} />
            </label>
            <label className="flex gap-2"><input type="checkbox" checked={confirmed} disabled={busy || !!submission} onChange={event => setConfirmed(event.target.checked)} />Kaynak dökümünün eksiksiz/doğru olduğunu inceledim; yalnız bu kaynaklara göre bakiye kurulmasını onaylıyorum.</label>
            <Button onClick={apply} disabled={busy || !confirmed || reason.trim().length < 10 || reference.trim().length < 10}>{submission ? 'Aynı isteği tekrar kontrol et' : 'Kaynağa göre bakiyeyi yeniden kur'}</Button>
            {submission && <Button variant="outline" disabled={busy} onClick={() => load(selected)}>Güncel önizlemeyi tekrar oku</Button>}
          </>}
          {result && <p role="status">Bakiye {amount(result.new_balance)} olarak yeniden kuruldu. İşlemi yapan kullanıcı ve gerekçe audit kaydında. Kaynak hareketleri korunuyor.</p>}
        </div>}
      </DialogContent>
    </Dialog>
  </>;
}
