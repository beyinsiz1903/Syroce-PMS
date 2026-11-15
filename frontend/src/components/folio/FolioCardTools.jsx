import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import apiErrorText from '@/utils/apiErrorText';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { folioPayorLabel } from '@/lib/folioPresentation';
import { formatCurrency } from '@/lib/currency';

const currency = value => String(value || '').toUpperCase().replace(/^TL$/, 'TRY');
const categories = [['', 'Tüm masraflar'], ['ROOM', 'Konaklama'], ['FOOD', 'Yemek'], ['BEVERAGE', 'İçecek'], ['MINIBAR', 'Minibar'], ['SPA', 'SPA'], ['LAUNDRY', 'Çamaşırhane'], ['PARKING', 'Otopark'], ['__custom', 'Diğer masraf kodları']];
export default function FolioCardTools({ booking, folios, onChanged, onClose }) {
  const [mode, setMode] = useState('merge');
  const [sourceId, setSourceId] = useState('');
  const [targetId, setTargetId] = useState('');
  const [reason, setReason] = useState('');
  const [category, setCategory] = useState('');
  const [customCodes, setCustomCodes] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [rules, setRules] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [routingUncertain, setRoutingUncertain] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const intent = useRef(null);
  const lock = useRef(false);
  const windows = folios.filter(f => f.status === 'open');
  const source = windows.find(f => f.id === sourceId);
  const targets = windows.filter(f => f.id !== sourceId && currency(f.currency || booking.currency) === currency(source?.currency || booking.currency));
  const target = targets.find(f => f.id === targetId);
  const code = currency(source?.currency || booking.currency);
  const chargeCodes = category === '__custom' ? [...new Set(customCodes.split(',').map(c => c.trim().toUpperCase()).filter(Boolean))] : category ? [category] : [];
  const invalidCodes = category === '__custom' && (!chargeCodes.length || chargeCodes.length > 50);
  const label = f => `${f.folio_number || f.id} · ${folioPayorLabel(f)} · ${formatCurrency(f.balance, f.currency || booking.currency)}`;
  useEffect(() => {
    let current = true;
    setRules(null); setError('');
    if (sourceId) axios.get('/folio-routing', { params: { folio_id: sourceId } }).then(({ data }) => {
      if (current) setRules((data || []).filter(r => r.source_folio_id === sourceId && folios.some(f => f.id === r.dest_folio_id)));
    }).catch(() => { if (current) setError('Yönlendirme kuralları okunamadı. Kaynak hesabı yeniden seçin.'); });
    return () => { current = false; };
  }, [sourceId, folios]);
  const execute = async action => {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError('');
    try { await action(); }
    catch (e) { setError(apiErrorText(e, e.message || 'İşlem tamamlanamadı. Hareketleri kontrol edin.')); }
    finally { lock.current = false; setBusy(false); }
  };
  const submit = () => execute(async () => {
    if (!source || !target || reason.trim().length < 3 || !confirmed) return;
    if (mode === 'merge') {
      const payload = { booking_id: booking.id, source_folio_id: sourceId, target_folio_id: targetId,
        expected_source_balance: Number(source.balance), expected_target_balance: Number(target.balance), reason: reason.trim() };
      const signature = JSON.stringify(payload);
      if (intent.current && intent.current.signature !== signature) throw new Error('Önceki birleştirmenin sonucu belirsiz. Kartı yenileyip hesapları kontrol edin.');
      intent.current ||= { signature, request_id: window.crypto.randomUUID() };
      try {
        await axios.post('/folio-windows/merge', { ...payload, request_id: intent.current.request_id });
      } catch (e) {
        if (e.response?.status >= 400 && e.response.status < 500) intent.current = null;
        throw e;
      }
      intent.current = null;
      toast.success('Hesaplar birleştirildi');
    } else {
      if (rules === null) return;
      if (routingUncertain) return;
      if (invalidCodes) return;
      try { await axios.post('/folio-routing', { source_folio_id: sourceId, dest_folio_id: targetId,
        charge_codes: chargeCodes, from_date: from || null, to_date: to || null, note: reason.trim() });
      } catch (e) {
        if (!e.response || e.response.status >= 500) {
          setRoutingUncertain(true);
          throw new Error('Kuralın kayıt sonucu doğrulanamadı. Bu alanı kapatıp tekrar açarak kayıtlı kuralları kontrol edin.');
        }
        throw e;
      }
      toast.success('Yönlendirme kuralı kaydedildi. Uygulamak için mevcut masrafları yönlendirin.');
    }
    onClose(); void Promise.resolve().then(() => onChanged?.()).catch(() => toast.warning('İşlem kaydedildi. Kartı yenileyin.'));
  });
  return <section className="rounded-xl border border-indigo-200 bg-indigo-50/30 p-4 space-y-4" aria-label="Folyo birleştirme ve yönlendirme">
    <div className="flex justify-between items-center gap-3"><h3 className="font-semibold">Hesapları düzenle</h3><Button variant="ghost" disabled={busy} onClick={onClose}>Kapat</Button></div>
    <div className="flex flex-wrap gap-2">{[['merge', 'Folyoları birleştir'], ['routing', 'Masrafları yönlendir']].map(([id, text]) => <Button key={id} variant={mode === id ? 'default' : 'outline'} disabled={busy} onClick={() => { setMode(id); setConfirmed(false); }}>{text}</Button>)}</div>
    <p className="text-sm text-slate-600">{mode === 'merge' ? 'Aynı rezervasyonun iki hesabı tek hesapta toplanır. Masraflar ve ödemeler hedefe taşınır; kaynak hesap kapanır. Kaynak hesaba bağlı yönlendirme kuralları kapatılır. Hedef hesabın ödeyeni korunur.' : 'Aynı rezervasyonun hesapları arasında masraf türüne ve iş gününe göre kural oluşturun. Kural yalnız “Mevcut masrafları yönlendir” düğmesiyle uygulanır; gelecekteki masraflar kendiliğinden taşınmaz.'}</p>
    <fieldset disabled={busy} className="grid gap-3 sm:grid-cols-2">
      <label className="text-sm">Kaynak hesap<select aria-label="Kaynak hesap" className="mt-1 block border rounded p-2 w-full" value={sourceId} onChange={e => { setSourceId(e.target.value); setTargetId(''); setConfirmed(false); }}><option value="">Hesap seçin</option>{windows.map(f => <option key={f.id} value={f.id}>{label(f)}</option>)}</select></label>
      <label className="text-sm">Hedef hesap<select aria-label="Hedef hesap" className="mt-1 block border rounded p-2 w-full" value={targetId} disabled={!source} onChange={e => { setTargetId(e.target.value); setConfirmed(false); }}><option value="">Hesap seçin</option>{targets.map(f => <option key={f.id} value={f.id}>{label(f)}</option>)}</select></label>
      {mode === 'routing' && <>
        <label>Masraf türü<select aria-label="Masraf türü" className="block border rounded p-2 w-full" value={category} onChange={e => { setCategory(e.target.value); setConfirmed(false); }}>{categories.map(([id, text]) => <option key={id} value={id}>{text}</option>)}</select></label>
        {category === '__custom' && <label>Masraf kodları<input aria-label="Masraf kodları" className="block border rounded p-2 w-full" value={customCodes} maxLength={1000} placeholder="Örn. TAX, TRANSPORT" onChange={e => { setCustomCodes(e.target.value); setConfirmed(false); }} /><span className="text-xs text-slate-600">Kayıtlı masraf kodlarını virgülle ayırın (en fazla 50).</span></label>}
        <div className="grid grid-cols-2 gap-2"><label>İlk iş günü<input aria-label="İlk iş günü" className="block border rounded p-2 w-full" type="date" value={from} onChange={e => { setFrom(e.target.value); setConfirmed(false); }} /></label><label>Son iş günü<input aria-label="Son iş günü" className="block border rounded p-2 w-full" type="date" value={to} onChange={e => { setTo(e.target.value); setConfirmed(false); }} /></label></div>
      </>}
      <label className="sm:col-span-2">İşlem açıklaması<input aria-label="İşlem açıklaması" className="mt-1 block border rounded p-2 w-full" maxLength={500} value={reason} onChange={e => setReason(e.target.value)} /></label>
    </fieldset>
    {source && target && <div className="rounded-lg bg-white p-3 text-sm border"><p>{source.folio_number} → {target.folio_number}</p>{mode === 'merge' && <p>Birleşen hesap bakiyesi: <strong>{formatCurrency(Number(source.balance) + Number(target.balance), code)}</strong></p>}<label className="flex items-start gap-2 mt-2"><input type="checkbox" checked={confirmed} disabled={busy} onChange={e => setConfirmed(e.target.checked)} />Kaynak, hedef ve işlem kapsamını kontrol ettim.</label></div>}
    {error && <p role="alert" className="text-red-700 text-sm">{error}</p>}
    <Button onClick={submit} disabled={busy || !source || !target || !confirmed || reason.trim().length < 3 || (mode === 'routing' && (invalidCodes || routingUncertain || rules === null || (from && to && from > to)))}>{busy ? 'İşleniyor…' : mode === 'merge' ? 'Birleştir' : 'Kuralı kaydet'}</Button>
    {mode === 'routing' && source && <div className="border-t pt-3 space-y-2"><h4 className="font-medium">Kaynak hesabın yönlendirme kuralları</h4>
      {rules === null ? <p className="text-sm">Kurallar henüz yüklenmedi.</p> : rules.length === 0 ? <p className="text-sm">Kayıtlı kural yok.</p> : <>
        {rules.map(r => <div key={r.id} className="flex justify-between items-center text-sm gap-2"><p>{folios.find(f => f.id === r.dest_folio_id)?.folio_number} · {(r.charge_codes || []).map(c => categories.find(([id]) => id === c)?.[1] || c).join(', ') || 'Tüm masraflar'} · {r.from_date || 'Başlangıç sınırı yok'} – {r.to_date || 'Bitiş sınırı yok'}</p><Button variant="outline" disabled={busy} onClick={() => execute(async () => { await axios.delete(`/folio-routing/${r.id}`); setRules(prev => prev.filter(rule => rule.id !== r.id)); })}>Kuralı kaldır</Button></div>)}
        <Button variant="outline" disabled={busy} onClick={() => execute(async () => { const { data } = await axios.post(`/folio-routing/apply/${sourceId}`); toast.success(`${data.moved} masraf yönlendirildi`); onClose(); void Promise.resolve().then(() => onChanged?.()).catch(() => toast.warning('İşlem kaydedildi. Kartı yenileyin.')); })}>Mevcut masrafları yönlendir</Button>
      </>}
    </div>}
  </section>;
}
