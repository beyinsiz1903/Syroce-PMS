import { useRef, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { formatCurrency } from '@/lib/currency';

const CURRENCIES = ['USD', 'EUR', 'GBP', 'CHF'];
const LINK_ACTIONS = ['already_posted', 'already_corrected'];
const POSTABLE_ACTIONS = ['post', 'correct', 'no_activity', ...LINK_ACTIONS];
const PREVIEW_LABELS = {
  post: 'Yeni kaynak fişi',
  correct: 'Bağlı düzeltme fişi',
  no_activity: 'Fiş gerektiren hareket yok',
  already_posted: 'Bu değerleme daha önce kaydedildi',
  already_corrected: 'Bu düzeltme daha önce kaydedildi',
};

const errorMessage = (error, fallback) => {
  const detail = error?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
};

export default function OperationalValuationCard({ runs = [], requestedRunId, onPosted }) {
  const [selectedId, setSelectedId] = useState(null);
  const [rates, setRates] = useState({});
  const [reference, setReference] = useState('');
  const [gain, setGain] = useState('');
  const [loss, setLoss] = useState('');
  const [review, setReview] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const run = runs.find((item) => item.id === (selectedId || requestedRunId))
    || (!selectedId && !requestedRunId ? runs[0] : null);
  const currentReview = review?.runId === run?.id ? review : null;

  const clearReview = () => {
    setReview(null);
    setResult(null);
    setError('');
  };

  const chooseRun = (event) => {
    setSelectedId(event.target.value || null);
    setRates({});
    setReference('');
    setGain('');
    setLoss('');
    clearReview();
  };

  const previewValuation = async (event) => {
    event.preventDefault();
    if (!run || inFlight.current) return;
    clearReview();
    const rateEntries = CURRENCIES.flatMap((code) => {
      const value = rates[code]?.trim().replace(',', '.');
      return value ? [[code, value]] : [];
    });
    if (rateEntries.some(([, value]) => !/^\d+(\.\d{1,6})?$/.test(value) || Number(value) <= 0 || Number(value) > 1000000)) {
      setError('Kurlar pozitif olmalı ve en fazla altı ondalık basamak içermelidir.');
      return;
    }
    if (reference.trim().length < 3 || (Boolean(gain.trim()) !== Boolean(loss.trim())) || (gain.trim() && gain.trim() === loss.trim())) {
      setError('Kur kaynağını belirtin. Kur farkı hesabı gerekiyorsa iki farklı hesap girin.');
      return;
    }
    const payload = {
      business_date: run.business_date,
      base_currency: 'TRY',
      rates_to_try: Object.fromEntries(rateEntries),
      reference: reference.trim(),
      ...(gain.trim() && { realised_fx_accounts: { gain: gain.trim(), loss: loss.trim() } }),
    };
    inFlight.current = true;
    setBusy(true);
    try {
      const { data } = await axios.post(`/gl/integrations/operational/night-audit/${encodeURIComponent(run.id)}/valuation/preview`, payload);
      if (data.run_id !== run.id || data.business_date !== run.business_date || !/^[a-f0-9]{64}$/.test(data.preview_hash)) {
        throw new Error('Beklenmeyen önizleme yanıtı');
      }
      setReview({ runId: run.id, payload, data });
    } catch (failure) {
      setError(errorMessage(failure, 'Değerleme önizlemesi alınamadı.'));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  const postValuation = async () => {
    if (!currentReview || !POSTABLE_ACTIONS.includes(currentReview.data.action) || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError('');
    try {
      const { data } = await axios.post(`/gl/integrations/operational/night-audit/${encodeURIComponent(run.id)}/valuation/post`, {
        ...currentReview.payload,
        expected_preview_hash: currentReview.data.preview_hash,
      });
      if (data.status !== 'no_activity' && (!['posted', 'corrected', 'already_posted', 'already_corrected'].includes(data.status) || !data.entry_id)) {
        throw new Error('Beklenmeyen kayıt yanıtı');
      }
      setSelectedId(run.id);
      setResult({ date: run.business_date, ...data });
      setReview(null);
      await onPosted?.();
    } catch (failure) {
      setReview(null);
      setError(errorMessage(failure, 'Aktarım sonucu doğrulanamadı. Yeniden önizleyip fiş durumunu kontrol edin.'));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  if (!runs.length && !requestedRunId && !result) return null;

  const displayMoney = (value) => formatCurrency(Number(value || 0), 'TRY', { decimals: 2 });
  const lines = currentReview?.data.posting_lines || [];

  return (
    <Card className="mt-4">
      <CardHeader><CardTitle>Gün Sonu Muhasebe Aktarımı</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        {runs.length > 0 && <label className="block max-w-sm space-y-1 text-sm">
          <span>Kaynak iş günü</span>
          <select value={run?.id || ''} onChange={chooseRun} disabled={busy} className="block w-full rounded-md border bg-background px-3 py-2">
            <option value="" disabled>İş günü seçin</option>
            {runs.map((item) => <option key={item.id} value={item.id}>{item.business_date}</option>)}
          </select>
        </label>}
        {result && <p role="status" className="text-sm text-emerald-700">
          {result.date} · {result.entry_id ? `Aktarım kaydedildi. Fiş kimliği ${result.entry_id}` : 'Fiş gerektiren hareket bulunmadı.'}
        </p>}
        {!run && !result && <p className="text-sm text-muted-foreground">Seçilen gün sonu bekleyen aktarımlar arasında bulunamadı.</p>}
        {run && <form onSubmit={previewValuation} className="space-y-3">
          {run.gl_bridge_error && <p className="text-sm text-amber-800">{run.gl_bridge_error}</p>}
          <p className="text-sm text-muted-foreground">Her para birimi için işlem gününe ait 1 birimin TL karşılığını ve kur kaynağını girin.</p>
          <div className="grid gap-3 sm:grid-cols-4">
            {CURRENCIES.map((code) => <label className="space-y-1 text-sm" key={code}>
              <span>{code} / TRY</span>
              <Input value={rates[code] || ''} inputMode="decimal" disabled={busy} onChange={(event) => {
                setRates((previous) => ({ ...previous, [code]: event.target.value }));
                clearReview();
              }} />
            </label>)}
          </div>
          <label className="block space-y-1 text-sm">
            <span>Kur kaynağı ve referansı</span>
            <Input value={reference} maxLength={240} disabled={busy} onChange={(event) => { setReference(event.target.value); clearReview(); }} required />
          </label>
          <details className="text-sm">
            <summary>Gerçekleşen kur farkı hesapları</summary>
            <div className="mt-2 grid gap-3 sm:grid-cols-2">
              <label className="space-y-1"><span>Kur farkı gelir hesabı</span><Input value={gain} maxLength={40} disabled={busy} onChange={(event) => { setGain(event.target.value); clearReview(); }} /></label>
              <label className="space-y-1"><span>Kur farkı gider hesabı</span><Input value={loss} maxLength={40} disabled={busy} onChange={(event) => { setLoss(event.target.value); clearReview(); }} /></label>
            </div>
          </details>
          <Button type="submit" variant="outline" disabled={busy}>Aktarımı Önizle</Button>
        </form>}
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        {currentReview && <div className="space-y-3 rounded-lg border p-3">
          <p className="text-sm font-medium">{currentReview.data.business_date} · {PREVIEW_LABELS[currentReview.data.action]}</p>
          <p className="text-sm">Kaynak hareketi: {currentReview.data.manifest?.sources?.length || 0} · {currentReview.payload.reference}</p>
          {lines.length > 0 && <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead><tr><th>Hesap</th><th>Açıklama</th><th>Borç (TRY)</th><th>Alacak (TRY)</th></tr></thead>
              <tbody>{lines.map((line, index) => <tr className="border-t" key={`${line.account_code}-${index}`}>
                <td>{line.account_code}</td><td>{line.memo}</td><td>{displayMoney(line.debit)}</td><td>{displayMoney(line.credit)}</td>
              </tr>)}</tbody>
              <tfoot><tr className="border-t font-medium"><td colSpan={2}>Toplam</td><td>{displayMoney(lines.reduce((sum, line) => sum + Number(line.debit || 0), 0))}</td><td>{displayMoney(lines.reduce((sum, line) => sum + Number(line.credit || 0), 0))}</td></tr></tfoot>
            </table>
          </div>}
          {POSTABLE_ACTIONS.includes(currentReview.data.action) && <Button type="button" onClick={postValuation} disabled={busy}>
            {LINK_ACTIONS.includes(currentReview.data.action) ? 'Fiş Bağlantısını Doğrula' : 'Önizlemeyi Onayla ve Kaydet'}
          </Button>}
        </div>}
      </CardContent>
    </Card>
  );
}
