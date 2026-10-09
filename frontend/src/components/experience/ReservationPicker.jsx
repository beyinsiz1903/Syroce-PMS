import { useEffect, useState } from 'react';
import axios from 'axios';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useTranslation } from 'react-i18next';

export default function ReservationPicker({ value, onSelect }) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [rows, setRows] = useState([]);
  const [state, setState] = useState('idle');
  useEffect(() => {
    const controller = new AbortController();
    setRows([]);
    if (value || query.trim().length < 2) { setState('idle'); return () => controller.abort(); }
    setState('loading');
    const timer = setTimeout(async () => {
      try {
        const { data } = await axios.get('/frontdesk/search-bookings', { params: { query: query.trim() }, signal: controller.signal });
        if (!controller.signal.aborted) { setRows(data.bookings || []); setState('ready'); }
      } catch { if (!controller.signal.aborted) setState('error'); }
    }, 300);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [value, query]);
  useEffect(() => { if (!value) setQuery(''); }, [value]);
  return <div className="space-y-2">
    {value ? <Button type="button" variant="outline" className="h-auto w-full whitespace-normal text-left" onClick={() => { onSelect(null); setQuery(''); }}>{query || t('experience.reservationSelected', 'Rezervasyon seçildi')} · {t('experience.change', 'Değiştir')}</Button> : <Input value={query} onChange={e => setQuery(e.target.value)} aria-label={t('experience.reservationSearch', 'Rezervasyon numarası veya misafir ara')} placeholder={t('experience.reservationSearch', 'Rezervasyon numarası veya misafir ara')} />}
    {state === 'loading' && <p role="status" className="text-xs">{t('common.loading', 'Yükleniyor…')}</p>}
    {state === 'error' && <p role="alert" className="text-xs text-destructive">{t('experience.searchError', 'Arama yapılamadı. Bağlantınızı kontrol edip yeniden arayın.')}</p>}
    {state === 'ready' && !rows.length && <p role="status" className="text-xs">{t('experience.noReservation', 'Eşleşen rezervasyon bulunamadı.')}</p>}
    {!!rows.length && <ul className="max-h-48 overflow-y-auto rounded-lg border">{rows.map(row => <li key={row.id}><button type="button" className="w-full p-3 text-left text-sm hover:bg-muted" onClick={() => { setQuery(`${row.guest_name || ''} · ${row.booking_number || ''}`); onSelect(row); setRows([]); }}>{row.guest_name} · {row.booking_number}<span className="block text-xs text-muted-foreground">{row.check_in?.slice(0, 10)} → {row.check_out?.slice(0, 10)}</span></button></li>)}</ul>}
  </div>;
}
