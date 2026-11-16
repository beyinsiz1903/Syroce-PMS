import { useRef, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { formatCurrency } from '@/lib/currency';

export function missingParkingSource(message) {
  if (!message?.startsWith('Unknown source tax must be resolved, not assumed zero: ')) return null;
  try {
    const source = JSON.parse(message.slice(message.indexOf('{')));
    return source?.id && source.charge_category === 'parking' ? source : null;
  } catch { return null; }
}

export default function DepartmentTaxReview({ runId, source, onApplied }) {
  const [rate, setRate] = useState('');
  const [reference, setReference] = useState('');
  const [review, setReview] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const endpoint = `/gl/integrations/operational/night-audit/${encodeURIComponent(runId)}/tax-review`;
  const showMoney = (value) => formatCurrency(value, source.currency);
  const perform = async (apply) => {
    if (inFlight.current) return;
    if (!apply && (!/^\d+(\.\d{1,2})?$/.test(rate.replace(',', '.')) || Number(rate.replace(',', '.')) > 100 || reference.trim().length < 10)) {
      setError('KDV oranını ve vergi kararının dayanağını belirtin.'); return;
    }
    if (apply && !review) return;
    inFlight.current = true; setBusy(true); setError('');
    try {
      if (apply) {
        const { data } = await axios.post(`${endpoint}/apply`, { ...review.payload, expected_preview_hash: review.data.preview_hash });
        if (!['applied', 'already_applied'].includes(data.status) || !data.review_id) throw new Error();
        setReview(null); await onApplied();
      } else {
        const payload = { source_id: source.id, vat_rate: rate.replace(',', '.'), reference: reference.trim() };
        const { data } = await axios.post(`${endpoint}/preview`, payload);
        if (data.source_id !== source.id || data.run_id !== runId || !/^[a-f0-9]{64}$/.test(data.preview_hash)) throw new Error();
        setReview({ data, payload });
      }
    } catch (failure) {
      setReview(null);
      const detail = failure?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Vergi incelemesi doğrulanamadı; yeniden önizleyin.');
    } finally { inFlight.current = false; setBusy(false); }
  };
  return <section className="space-y-3 rounded-lg border border-amber-300 p-3" aria-label="Otopark vergi incelemesi">
    <h3 className="font-medium">Otopark kaydının vergi bilgisi eksik</h3>
    <p className="text-sm">{source.description} · Toplam {showMoney(source.total)}</p>
    <p className="text-sm text-muted-foreground">Toplam borç ve tahsilat değişmez. Yalnız eksik KDV ayrımı, belirttiğiniz dayanakla kaydedilir. Bu işlem fatura veya tahsilat oluşturmaz.</p>
    <label className="block text-sm">Toplama dahil KDV oranı (%)<Input value={rate} disabled={busy} onChange={(event) => { setRate(event.target.value); setReview(null); }} inputMode="decimal" /></label>
    <label className="block text-sm">Vergi kararının dayanağı<Input value={reference} maxLength={240} disabled={busy} onChange={(event) => { setReference(event.target.value); setReview(null); }} /></label>
    <Button type="button" variant="outline" disabled={busy} onClick={() => perform(false)}>Vergi ayrımını önizle</Button>
    {review && <div className="space-y-2 text-sm"><p>Hizmet bedeli: {showMoney(review.data.net)} · KDV: {showMoney(review.data.vat)} · Toplam: {showMoney(review.data.gross)}</p>
      <Button type="button" disabled={busy} onClick={() => perform(true)}>Bu vergi ayrımını kaydet</Button></div>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
