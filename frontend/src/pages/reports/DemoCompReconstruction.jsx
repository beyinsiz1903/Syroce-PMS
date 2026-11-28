import { useRef, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';

const ids = ['cacc4ae5-bd21-55cf-bddb-d975d9ff6ba3', 'fd2a768f-fc39-495b-ae63-716281a43116'];

export default function DemoCompReconstruction({ sources = [], corrected = [], onApplied }) {
  const [plan, setPlan] = useState(null);
  const [reason, setReason] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const request = useRef(null);
  const eligible = ids.every(id => sources.some(source => source.id === id)) || corrected.length > 0;
  if (!eligible) return null;
  const preview = async () => {
    setBusy(true); setError(''); setPlan(null); setConfirmed(false); request.current = null;
    try { const { data } = await axios.get('/pms/demo-comp-reconstruction/preview'); setPlan(data); }
    catch (e) { setError(e.response?.data?.detail || 'Test düzeltmesi alınamadı.'); }
    finally { setBusy(false); }
  };
  const apply = async () => {
    if (!plan || plan.already_applied || !confirmed || reason.trim().length < 20 || busy) return;
    const body = { source_fingerprint: plan.source_fingerprint, reason: reason.trim(), confirmation: 'DEFINE_SYNTHETIC_COMP_25_60_ONLY' };
    if (!request.current || request.current.signature !== JSON.stringify(body)) request.current = { signature: JSON.stringify(body), body: { ...body, request_id: crypto.randomUUID() } };
    setBusy(true); setError('');
    try {
      const { data } = await axios.post('/pms/demo-comp-reconstruction/apply', request.current.body);
      setPlan({ ...data, already_applied: true }); onApplied?.();
    } catch (e) { setError(e.response?.data?.detail || 'Sonuç doğrulanamadı. Yeniden göndermeden önce düzeltmeyi yeniden inceleyin.'); }
    finally { setBusy(false); }
  };
  return <aside className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 print:hidden" aria-label="Sentetik ikram düzeltmesi">
    <Button variant="outline" onClick={preview} disabled={busy}>İki test kaydının düzeltmesini incele</Button>
    {error && <p role="alert">{typeof error === 'string' ? error : 'Test düzeltmesi doğrulanamadı.'}</p>}
    {plan && <div className="mt-3 space-y-3">
      <p>{plan.notice}</p>
      <p>Tahsilat, kaynağın tarihi ve işlenmiş tutar değişmez. Muhasebeye otomatik fiş gönderilmez; 12 Kasımın eski fişi korunur ve kaynak değerlemesi yeniden incelemeye alınır.</p>
      <ul>{plan.documents?.map(source => <li key={source.id}>{source.original_gross} TRY liste bedeli: {source.snapshot.net_amount} TRY net + {source.snapshot.vat_amount} TRY test vergisi.</li>)}</ul>
      {plan.already_applied ? <p role="status">Test düzeltmesi kayıtlı. Önceki sürümler ve düzeltme gerekçesi korunuyor.</p> : <>
        <label className="block">Düzeltme gerekçesi<textarea className="mt-1 block w-full rounded border bg-white p-2" value={reason} onChange={e => setReason(e.target.value)} /></label>
        <label className="flex gap-2"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />Bunun yeni sentetik test tanımı olduğunu, özgün tarihî KDV doğrulaması olmadığını onaylıyorum.</label>
        <Button onClick={apply} disabled={busy || !confirmed || reason.trim().length < 20}>Önceki sürümü koruyarak test düzeltmesini kaydet</Button>
      </>}
    </div>}
  </aside>;
}
