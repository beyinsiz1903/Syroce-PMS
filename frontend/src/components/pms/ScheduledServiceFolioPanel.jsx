import { useEffect, useRef, useState } from 'react';
import api from '@/api/axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { formatCurrency } from '@/lib/currency';

export default function ScheduledServiceFolioPanel({ kind, bookings, names = {}, onChanged }) {
  const prefix = kind === 'activity' ? '/activities' : '/function-space';
  const [source, setSource] = useState(null);
  const [basis, setBasis] = useState(kind === 'activity' ? 'per_booking' : 'hourly');
  const [quote, setQuote] = useState(null);
  const [room, setRoom] = useState('');
  const [target, setTarget] = useState(null);
  const [folios, setFolios] = useState([]);
  const [folioId, setFolioId] = useState('');
  const [reason, setReason] = useState('Operatör onayıyla tamamlanan hizmet');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const attempt = useRef(null);
  const lookupVersion = useRef(0);
  useEffect(() => {
    if (!source) return undefined;
    let current = true;
    setQuote(null); setError('');
    api.get(`${prefix}/bookings/${source.id}/folio-quote`, { params: { billing_basis: basis } })
      .then(({ data }) => { if (current) setQuote(data); })
      .catch(e => { if (current) setError(e.response?.data?.detail || 'Hizmet önizlemesi alınamadı'); });
    return () => { current = false; };
  }, [source, basis, prefix]);
  const open = row => {
    lookupVersion.current += 1;
    attempt.current = null; setUncertain(false); setSource(row); setTarget(null); setFolios([]); setFolioId(''); setRoom(''); setError('');
  };
  const lookup = async () => {
    const version = ++lookupVersion.current;
    setBusy(true); setError(''); setTarget(null); setFolios([]); setFolioId('');
    try {
      const { data } = await api.get(`/bookings/active-by-room/${encodeURIComponent(room.trim())}`);
      if (!data.found || !data.booking_id) throw new Error('Bu odada aktif konaklama bulunamadı');
      const response = await api.get(`/folio-windows/booking/${data.booking_id}`);
      if (version !== lookupVersion.current) return;
      const windows = (Array.isArray(response.data) ? response.data : []).filter(row => row.status === 'open');
      setTarget(data); setFolios(windows);
      if (windows.length === 1) setFolioId(windows[0].folio_id);
    } catch (e) {
      if (version === lookupVersion.current) setError(e.response?.data?.detail || e.message);
    } finally { if (version === lookupVersion.current) setBusy(false); }
  };
  const post = async () => {
    if (!attempt.current) attempt.current = { reservation_id: target.booking_id, folio_id: folioId, quote_hash: quote.quote_hash, billing_basis: basis, reason };
    setBusy(true); setError('');
    try {
      const { data } = await api.post(`${prefix}/bookings/${source.id}/folio`, attempt.current);
      if (!data.success || !data.charge?.id) throw new Error('Ücret kaydı doğrulanamadı');
      attempt.current = null; setUncertain(false); setSource(null); onChanged?.();
    } catch (e) { setUncertain(true); setError(e.response?.data?.detail || 'Sonuç belirsiz. Yalnız aynı kaynak ve aynı hedefle tekrar doğrulayın; yeni hizmet oluşturmayın.'); }
    finally { setBusy(false); }
  };
  if (!bookings.length) return null;
  return <section className="rounded-xl border bg-background p-4 space-y-3">
    <div><h3 className="font-semibold">Hizmet hesabı</h3><p className="text-sm text-muted-foreground">Hizmet tamamlandığında kayıtlı tarife önizlemesini kontrol edip seçilen açık folyoya bir kez işleyin. Bu işlem tahsilat değildir.</p></div>
    {bookings.map(row => <div key={row.id} className="flex flex-wrap justify-between items-center gap-3 border-t pt-3 text-sm">
      <div><p className="font-medium">{names[row.activity_id] || row.event_name || 'Hizmet'}{row.guest_name ? ` · ${row.guest_name}` : ''}</p><p className="text-muted-foreground">{row.starts_at?.slice(0, 10)} {row.starts_at?.slice(11, 16)} – {row.ends_at?.slice(0, 10)} {row.ends_at?.slice(11, 16)}</p></div>
      <Button size="sm" variant="outline" disabled={Boolean(row.folio_charge_id) || row.status === 'cancelled'} onClick={() => open(row)}>{row.folio_charge_id ? 'Folyoya işlendi' : row.status === 'cancelled' ? 'İptal edildi' : 'Tamamla ve folyoya işle'}</Button>
    </div>)}
    <Dialog open={Boolean(source)} onOpenChange={value => { if (!value && !busy) { lookupVersion.current += 1; setSource(null); onChanged?.(); } }}>
      <DialogContent><DialogHeader><DialogTitle>Hizmetin folyo aktarımı</DialogTitle><DialogDescription>Tarife ve seçilen konaklama para birimi aynı olmalı. Eski ücretler, stoklar ve ödemeler değişmez.</DialogDescription></DialogHeader>
        {kind === 'function_space' && <label className="text-sm">Tarife<select aria-label="Ücret tarifesi" disabled={uncertain || busy} value={basis} onChange={e => setBasis(e.target.value)} className="block w-full border rounded p-2"><option value="hourly">Saatlik — süreyle orantılı</option><option value="daily">Günlük — 24 saat üzerinden orantılı</option></select></label>}
        {quote ? <div className="rounded-lg bg-muted p-3 text-sm"><p className="font-semibold">{formatCurrency(Number(quote.gross), quote.currency)}</p><p>{quote.service_date} · {quote.service_time}</p><p>{quote.tax == null ? 'Vergi ayrımı bilinmiyor; %0 olarak kabul edilmez.' : `Dahil vergi: ${formatCurrency(Number(quote.tax), quote.currency)}`}</p></div> : <p className="text-sm">Tarife önizlemesi bekleniyor…</p>}
        <Label>Aktif konaklamanın oda numarası<Input aria-label="Konaklama oda numarası" value={room} disabled={busy || uncertain} onChange={e => { lookupVersion.current += 1; setRoom(e.target.value); setTarget(null); setFolios([]); setFolioId(''); }} /></Label>
        <Button variant="outline" disabled={!room.trim() || busy || uncertain} onClick={lookup}>Konaklamayı bul</Button>
        {target && <p className="text-sm">{target.guest_name || 'Aktif misafir'} · Oda {room}</p>}
        {target && <label className="text-sm">Hedef folyo<select aria-label="Hedef folyo" className="block w-full border rounded p-2" value={folioId} disabled={busy || uncertain} onChange={e => setFolioId(e.target.value)}><option value="">Hedef hesap seçin</option>{folios.map(row => <option key={row.folio_id} value={row.folio_id}>{row.folio_number || `Hesap ${row.window_number}`} · {row.payor_type || 'Misafir'} · {row.currency}</option>)}</select></label>}
        <Label>İşlem gerekçesi<Input value={reason} disabled={busy || uncertain} onChange={e => setReason(e.target.value)} /></Label>
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <Button disabled={busy || !quote?.quote_hash || !target || !folioId || reason.trim().length < 3} onClick={post}>{busy ? 'Doğrulanıyor…' : uncertain ? 'Aynı aktarımın sonucunu doğrula' : 'Hizmeti tamamla ve ücreti işle'}</Button>
      </DialogContent>
    </Dialog>
  </section>;
}
