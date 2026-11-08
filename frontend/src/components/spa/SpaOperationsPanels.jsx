import { useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { formatSpaTime, spaDateTimeInput } from '@/lib/spaTime';

export function SpaAvailability({ services, timeZone }) {
  const [date, setDate] = useState('');
  const [serviceId, setServiceId] = useState('');
  const [result, setResult] = useState(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(false);
  const selectedDate = date || spaDateTimeInput(new Date(), timeZone).slice(0, 10);
  const slots = (result?.slots ?? []).filter(slot => slot.any_available);

  const search = async (event) => {
    event.preventDefault();
    setPending(true);
    setResult(null);
    setError(false);
    try {
      const { data } = await axios.get('/spa/availability', {
        params: { date: selectedDate, ...(serviceId ? { service_id: serviceId } : {}) },
      });
      setResult(data);
    } catch {
      setError(true);
    } finally {
      setPending(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Terapist ve oda müsaitliği</CardTitle>
        <CardDescription>Seçilen gün ve hizmet süresi için birlikte müsait olan terapistleri ve odaları görün.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={search} className="flex flex-wrap items-end gap-3">
          <label className="space-y-1 text-sm">
            <span>Tarih</span>
            <Input type="date" value={selectedDate} required disabled={pending}
              onChange={event => { setDate(event.target.value); setResult(null); setError(false); }} />
          </label>
          <label className="space-y-1 text-sm">
            <span>Hizmet</span>
            <select className="block h-10 max-w-full rounded-md border bg-background px-2" value={serviceId} disabled={pending}
              onChange={event => { setServiceId(event.target.value); setResult(null); setError(false); }}>
              <option value="">Genel müsaitlik · 30 dk</option>
              {services.filter(service => service.active !== false).map(service => (
                <option key={service.id} value={service.id}>{service.name} · {service.duration_minutes} dk</option>
              ))}
            </select>
          </label>
          <Button type="submit" disabled={pending || !selectedDate}>{pending ? 'Aranıyor…' : 'Müsait saatleri göster'}</Button>
        </form>
        {error && <p role="alert">Müsaitlik bilgisi yüklenemedi. Tekrar deneyin.</p>}
        {result && (
          <div className="space-y-2">
            <p role="status" className="text-sm text-muted-foreground">
              {slots.length ? `${slots.length} uygun başlangıç saati · Tesis saati ${result.timezone}` : 'Seçilen gün ve hizmet için uygun terapist ve oda bulunamadı.'}
            </p>
            {slots.map(slot => (
              <div key={slot.starts_at} className="grid gap-1 rounded-md border p-3 text-sm sm:grid-cols-3">
                <strong>{formatSpaTime(slot.starts_at, result.timezone)} – {formatSpaTime(slot.ends_at, result.timezone)}</strong>
                <span>Terapistler · {slot.therapists.filter(row => row.available).map(row => row.therapist_name).join(', ')}</span>
                <span>Odalar · {slot.rooms.map(room => room.name).join(', ')}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function SpaGuestHistory({ timeZone, statuses, money }) {
  const [name, setName] = useState('');
  const [results, setResults] = useState(null);
  const [profile, setProfile] = useState(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(false);

  const load = async (guest) => {
    setPending(true);
    setError(false);
    setProfile(null);
    if (!guest) setResults(null);
    try {
      const { data } = guest
        ? await axios.get(`/spa/guests/${encodeURIComponent(guest.guest_id)}/history`)
        : await axios.get('/spa/guests/history/search', { params: { q: name.trim() } });
      if (guest) setProfile({ name: guest.guest_name, appointments: data.appointments });
      else setResults(data.appointments);
    } catch {
      setError(true);
    } finally {
      setPending(false);
    }
  };

  const rows = profile?.appointments ?? results;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Misafir SPA geçmişi</CardTitle>
        <CardDescription>SPA randevularında ada göre arayın. Misafir profiline bağlı randevulardan o profilin geçmişini açabilirsiniz.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={event => { event.preventDefault(); if (name.trim().length >= 2) load(); }} className="flex flex-wrap items-end gap-3">
          <label className="space-y-1 text-sm">
            <span>Misafir adı</span>
            <Input value={name} maxLength={100} disabled={pending}
              onChange={event => { setName(event.target.value); setResults(null); setProfile(null); setError(false); }} />
          </label>
          <Button type="submit" disabled={pending || name.trim().length < 2}>{pending ? 'Aranıyor…' : 'Geçmişi ara'}</Button>
        </form>
        {error && <p role="alert">SPA geçmişi yüklenemedi. Tekrar deneyin.</p>}
        {profile && (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <strong>{profile.name} · Profil geçmişi</strong>
            <Button type="button" variant="outline" onClick={() => setProfile(null)}>Arama sonuçlarına dön</Button>
          </div>
        )}
        {rows && !rows.length && <p role="status">Eşleşen SPA randevusu bulunamadı.</p>}
        {rows?.length > 0 && <p className="text-sm text-muted-foreground">En fazla 50 randevu gösterilir.</p>}
        {rows?.map(row => (
          <div key={row.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3 text-sm">
            <div>
              <strong>{row.guest_name}</strong>
              <p>{row.service_name} · {formatSpaTime(row.starts_at, timeZone)} · {statuses[row.status]?.label || row.status}</p>
              {row.currency && row.price != null && <p className="text-muted-foreground">Hizmet bedeli · {money(row.price, row.currency)}</p>}
            </div>
            {!profile && row.guest_id && (
              <Button type="button" variant="outline" size="sm" disabled={pending} onClick={() => load(row)}>
                {row.guest_name} profil geçmişi
              </Button>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
