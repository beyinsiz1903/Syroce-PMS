import { useEffect, useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import ProductState from '@/components/shared/ProductState';

// Read-only context: never stores profiles in browser storage or automatically sends messages.
export default function GuestContextPanel({ open, onOpenChange, guestId: initialId, scope }) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [guestId, setGuestId] = useState(initialId || '');
  const [results, setResults] = useState([]);
  const [profile, setProfile] = useState(null);
  const [state, setState] = useState('idle');
  const [retry, setRetry] = useState(0);
  useEffect(() => { setGuestId(initialId || ''); setQuery(''); setResults([]); setProfile(null); }, [open, initialId, scope]);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setProfile(null); setResults([]);
    if (!guestId && query.trim().length < 2) { setState('idle'); return () => controller.abort(); }
    setState('loading');
    const timer = setTimeout(async () => {
      try {
        const response = await axios.get(guestId ? `/crm/guest/${encodeURIComponent(guestId)}` : '/pms/guests/search', {
          signal: controller.signal, ...(guestId ? {} : { params: { q: query.trim(), limit: 10 } }),
        });
        if (controller.signal.aborted) return;
        if (guestId) setProfile(response.data); else setResults(Array.isArray(response.data) ? response.data : []);
        setState('ready');
      } catch (error) {
        if (!controller.signal.aborted) setState(error.response?.status === 403 ? 'forbidden' : 'error');
      }
    }, guestId ? 0 : 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [open, guestId, query, retry, scope]);
  const guest = profile?.guest || {};
  const stays = profile?.stay_history || profile?.recent_bookings || [];
  const tags = Array.isArray(guest.tags) ? guest.tags : [];
  return <Sheet open={open} onOpenChange={onOpenChange}><SheetContent className="w-full overflow-y-auto sm:max-w-xl">
    <SheetHeader><SheetTitle>{t('experience.guestContext', 'Misafir özeti')}</SheetTitle><SheetDescription>{t('experience.guestContextHelp', 'Bulunduğunuz ekrandan ayrılmadan misafir ve konaklama bilgilerini inceleyin.')}</SheetDescription></SheetHeader>
    <div className="mt-5 space-y-4">
      <Input aria-label={t('experience.guestSearch', 'Misafir ara')} placeholder={t('experience.guestSearch', 'Misafir ara')} value={query} onChange={e => { setQuery(e.target.value); setGuestId(''); }} />
      {state === 'idle' && <p className="text-sm text-muted-foreground">{t('experience.searchHelp', 'Aramak için en az iki karakter yazın.')}</p>}
      {['loading', 'error', 'forbidden'].includes(state) && <ProductState state={state} compact onRetry={state === 'error' ? () => setRetry(v => v + 1) : undefined} />}
      {state === 'ready' && !profile && (results.length ? <ul className="space-y-2">{results.map(row => <li key={row.id}><Button variant="outline" className="h-auto w-full justify-start whitespace-normal py-3 text-left" onClick={() => setGuestId(row.id)}>{row.name}</Button></li>)}</ul> : <ProductState state="empty" compact />)}
      {state === 'ready' && profile && <>
        <h2 className="text-xl font-semibold">{guest.name || t('experience.guest', 'Misafir')}</h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm"><dt>{t('experience.email', 'E-posta')}</dt><dd className="break-all">{guest.email || '—'}</dd><dt>{t('experience.phone', 'Telefon')}</dt><dd>{guest.phone || '—'}</dd></dl>
        {tags.length > 0 && <div className="flex flex-wrap gap-2">{tags.map(tag => <span key={tag} className="rounded-full bg-muted px-3 py-1 text-xs">{String(tag)}</span>)}</div>}
        <h3 className="font-semibold">{t('experience.stays', 'Konaklama geçmişi')}</h3>
        {stays.length ? <ul className="space-y-2">{stays.map((stay, i) => <li key={stay.id || i} className="rounded-lg border p-3 text-sm"><span>{stay.check_in?.slice(0, 10) || '—'} → {stay.check_out?.slice(0, 10) || '—'}</span><span className="ml-2">{t(`experience.stayStatus.${stay.status}`, { defaultValue: t('experience.unspecified', 'Belirtilmedi') })}</span>{stay.room_number && <p>{t('experience.room', 'Oda')} {stay.room_number}</p>}</li>)}</ul> : <p className="text-sm text-muted-foreground">{t('experience.noStays', 'Görüntülenebilen konaklama kaydı yok.')}</p>}
        <p className="text-xs text-muted-foreground">{t('experience.guestPrivacy', 'Bilgiler mevcut erişiminizle sınırlıdır. İletişim izni bu özetten çıkarılamaz; gönderim öncesinde ilgili kanaldan doğrulanmalıdır.')}</p>
      </>}
    </div>
  </SheetContent></Sheet>;
}
