import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Input } from '@/components/ui/input';

const currencyCode = value => String(value || '').trim().toUpperCase().replace(/^TL$/, 'TRY');
const guestName = row => row.guest?.full_name || row.guest_name || row.guest?.name || 'Misafir';

export default function SpaResidentTarget({ currency, onTargetChange }) {
  const [bookings, setBookings] = useState([]);
  const [bookingId, setBookingId] = useState('');
  const [folios, setFolios] = useState([]);
  const [folioId, setFolioId] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadingFolios, setLoadingFolios] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const code = currencyCode(currency);

  useEffect(() => {
    let active = true;
    setLoading(true); setBookings([]); setBookingId(''); setError('');
    axios.get('/frontdesk/inhouse').then(({ data }) => {
      if (!active) return;
      if (!Array.isArray(data)) throw new Error('invalid response');
      setBookings(data.filter(row => row.id && ['checked_in', 'in_house'].includes(row.status)));
    }).catch(() => { if (active) setError('Konaklayan misafirler yüklenemedi. Yenileyip tekrar seçin.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reload]);

  useEffect(() => {
    let active = true;
    setFolios([]); setFolioId(''); onTargetChange(null);
    const booking = bookings.find(row => row.id === bookingId);
    if (!booking || !code || currencyCode(booking.currency) !== code) {
      setLoadingFolios(false);
      return () => { active = false; };
    }
    setLoadingFolios(true); setError('');
    axios.get(`/folio/booking/${encodeURIComponent(booking.id)}`).then(({ data }) => {
      if (!active) return;
      const rows = Array.isArray(data) ? data : data?.folios;
      if (!Array.isArray(rows)) throw new Error('invalid response');
      const targets = rows.filter(row => row.id && row.booking_id === booking.id && row.status === 'open' && !row.invoice_id &&
        currencyCode(row.currency || booking.currency) === code);
      setFolios(targets);
      if (targets.length === 1) {
        setFolioId(targets[0].id);
        onTargetChange({ reservation_id: booking.id, folio_id: targets[0].id, guest_name: guestName(booking) });
      }
    }).catch(() => { if (active) setError('Misafirin açık hesapları yüklenemedi. Yenileyip tekrar seçin.'); })
      .finally(() => { if (active) setLoadingFolios(false); });
    return () => { active = false; };
  }, [bookingId, bookings, code, onTargetChange]);

  const eligible = useMemo(() => bookings.filter(row => code && currencyCode(row.currency) === code), [bookings, code]);
  const visible = eligible.filter(row => row.id === bookingId ||
    `${guestName(row)} ${row.room?.room_number || row.room_number || ''} ${row.booking_number || row.confirmation_code || ''}`.toLocaleLowerCase('tr-TR').includes(query.toLocaleLowerCase('tr-TR')));
  const chooseFolio = id => {
    setFolioId(id);
    const booking = bookings.find(row => row.id === bookingId);
    onTargetChange(booking && folios.some(row => row.id === id)
      ? { reservation_id: booking.id, folio_id: id, guest_name: guestName(booking) } : null);
  };
  return <section className="space-y-3 rounded-lg border p-3" aria-label="SPA oda hesabı seçimi">
    <p className="text-sm text-muted-foreground">Hizmetle aynı para birimindeki konaklayan misafiri ve masrafın yazılacağı hesabı seçin.</p>
    <label className="block text-sm">Misafir veya oda ara<Input value={query} onChange={event => setQuery(event.target.value)} /></label>
    <label className="block text-sm">Konaklayan misafir<select className="mt-1 block w-full rounded border bg-background p-2" value={bookingId} disabled={loading} onChange={event => { onTargetChange(null); setBookingId(event.target.value); }}>
      <option value="">{loading ? 'Misafirler yükleniyor…' : 'Misafir seçin'}</option>
      {visible.map(row => <option key={row.id} value={row.id}>{guestName(row)} · Oda {row.room?.room_number || row.room_number || 'atanmamış'} · {row.check_in?.slice(0, 10)} – {row.check_out?.slice(0, 10)} · {code}</option>)}
    </select></label>
    {!loading && !error && !eligible.length && <p role="status">{code || 'Seçilen hizmetin'} para biriminde konaklayan misafir bulunamadı.</p>}
    {bookingId && <label className="block text-sm">Masrafın yazılacağı hesap<select className="mt-1 block w-full rounded border bg-background p-2" value={folioId} disabled={loadingFolios} onChange={event => chooseFolio(event.target.value)}>
      <option value="">{loadingFolios ? 'Hesaplar yükleniyor…' : 'Açık hesap seçin'}</option>
      {folios.map(row => <option key={row.id} value={row.id}>{row.folio_number || 'Misafir hesabı'} · {({ guest: 'Misafir', company: 'Şirket', agency: 'Acente', master: 'Ana hesap' })[row.payor_type || row.folio_type] || 'Hesap'} · {code}</option>)}
    </select></label>}
    {bookingId && !loadingFolios && !error && !folios.length && <p role="status">Bu konaklamada uygun açık, faturasız hesap yok. Ön bürodan hesabı kontrol edin.</p>}
    {error && <div role="alert" className="text-sm text-destructive">{error} <button type="button" className="underline" onClick={() => setReload(value => value + 1)}>Yenile</button></div>}
  </section>;
}
