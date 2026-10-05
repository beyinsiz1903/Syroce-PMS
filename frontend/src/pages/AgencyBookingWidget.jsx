import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { BedDouble, CalendarDays, CheckCircle2, Loader2, MapPin, Search } from 'lucide-react';

const RAW_BACKEND_URL = import.meta.env.VITE_BACKEND_URL || '/api';
const API_BASE = RAW_BACKEND_URL.endsWith('/api') ? RAW_BACKEND_URL : `${RAW_BACKEND_URL.replace(/\/+$/, '')}/api`;
const today = new Date();
const tomorrow = new Date(today.getTime() + 86400000);
const dateValue = value => new Date(value.getTime() - value.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const money = (value, currency = 'TRY') => new Intl.NumberFormat('tr-TR', { style: 'currency', currency }).format(Number(value) || 0);

export default function AgencyBookingWidget() {
  const token = useMemo(() => new URLSearchParams(window.location.search).get('key') || '', []);
  const parentOrigin = useMemo(() => {
    try { return new URL(document.referrer).origin; } catch { return ''; }
  }, []);
  const client = useMemo(() => axios.create({
    baseURL: API_BASE,
    timeout: 30000,
    headers: { 'X-Widget-Token': token, 'X-Widget-Origin': parentOrigin },
  }), [token, parentOrigin]);
  const [config, setConfig] = useState(null);
  const [form, setForm] = useState({ check_in: dateValue(today), check_out: dateValue(tomorrow), adults: 2, children: 0, child_ages: [], city: '', q: '' });
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [guest, setGuest] = useState({ guest_name: '', guest_email: '', guest_phone: '', special_requests: '' });
  const [confirmation, setConfirmation] = useState(null);

  useEffect(() => {
    client.get('/marketplace/v1/widget/config').then(({ data }) => setConfig(data)).catch(error_ => setError(error_.response?.data?.detail || 'Widget yüklenemedi. Web sitesi yetkisini kontrol edin.'));
  }, [client]);

  const setChildren = count => setForm(current => ({ ...current, children: count, child_ages: Array.from({ length: count }, (_, index) => current.child_ages[index] ?? 0) }));
  const search = async event => {
    event.preventDefault(); setLoading(true); setError(''); setConfirmation(null); setSelected(null);
    try {
      const { data } = await client.post('/marketplace/v1/widget/search', form);
      setResults(data.results || []);
    } catch (error_) { setError(error_.response?.data?.detail || 'Arama tamamlanamadı.'); }
    finally { setLoading(false); }
  };
  const reserve = async event => {
    event.preventDefault(); setLoading(true); setError('');
    try {
      const idempotency = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
      const { data } = await client.post('/marketplace/v1/widget/reservations', {
        tenant_id: selected.hotel.tenant_id,
        room_type: selected.room.room_type,
        check_in: form.check_in,
        check_out: form.check_out,
        adults: form.adults,
        children: form.children,
        child_ages: form.child_ages,
        total_amount: selected.room.total_price,
        idempotency_key: idempotency,
        ...guest,
      });
      setConfirmation(data.reservation); setSelected(null);
    } catch (error_) { setError(error_.response?.data?.detail || 'Rezervasyon oluşturulamadı.'); }
    finally { setLoading(false); }
  };
  const color = config?.brand_color || '#047857';

  return <main className="min-h-screen bg-slate-50 p-3 text-slate-900 sm:p-5" style={{ '--widget-color': color }}>
    <section className="mx-auto max-w-5xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <header className="border-b border-slate-200 px-5 py-4"><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Güvenli otel rezervasyonu</p><h1 className="mt-1 text-xl font-bold">{config?.agency?.name || 'Otel arama'}</h1></header>
      <form onSubmit={search} className="grid gap-3 p-5 md:grid-cols-6">
        <label className="text-xs font-semibold text-slate-600 md:col-span-2">Giriş<input required type="date" min={dateValue(today)} value={form.check_in} onChange={event => setForm({ ...form, check_in: event.target.value })} className="mt-1 h-11 w-full rounded-lg border border-slate-300 px-3 text-sm" /></label>
        <label className="text-xs font-semibold text-slate-600 md:col-span-2">Çıkış<input required type="date" min={form.check_in} value={form.check_out} onChange={event => setForm({ ...form, check_out: event.target.value })} className="mt-1 h-11 w-full rounded-lg border border-slate-300 px-3 text-sm" /></label>
        <label className="text-xs font-semibold text-slate-600">Yetişkin<input required type="number" min="1" max="20" value={form.adults} onChange={event => setForm({ ...form, adults: Number(event.target.value) })} className="mt-1 h-11 w-full rounded-lg border border-slate-300 px-3 text-sm" /></label>
        <label className="text-xs font-semibold text-slate-600">Çocuk<input type="number" min="0" max="20" value={form.children} onChange={event => setChildren(Number(event.target.value))} className="mt-1 h-11 w-full rounded-lg border border-slate-300 px-3 text-sm" /></label>
        <label className="text-xs font-semibold text-slate-600 md:col-span-3">Şehir<input value={form.city} onChange={event => setForm({ ...form, city: event.target.value })} placeholder="İstanbul" className="mt-1 h-11 w-full rounded-lg border border-slate-300 px-3 text-sm" /></label>
        <label className="text-xs font-semibold text-slate-600 md:col-span-3">Tesis veya bölge<input value={form.q} onChange={event => setForm({ ...form, q: event.target.value })} placeholder="Tesis adı veya bölge" className="mt-1 h-11 w-full rounded-lg border border-slate-300 px-3 text-sm" /></label>
        {form.child_ages.map((age, index) => <label key={index} className="text-xs font-semibold text-slate-600">{index + 1}. çocuk yaşı<input required type="number" min="0" max="17" value={age} onChange={event => setForm(current => ({ ...current, child_ages: current.child_ages.map((item, itemIndex) => itemIndex === index ? Number(event.target.value) : item) }))} className="mt-1 h-11 w-full rounded-lg border border-slate-300 px-3 text-sm" /></label>)}
        <button disabled={loading || !config} className="flex h-11 items-center justify-center gap-2 rounded-lg font-semibold text-white disabled:opacity-50 md:col-span-6" style={{ backgroundColor: color }}>{loading ? <Loader2 className="animate-spin" size={18} /> : <Search size={18} />}Uygun tesisleri ara</button>
      </form>
      {error && <div role="alert" className="mx-5 mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</div>}
      {confirmation && <div className="mx-5 mb-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-900"><div className="flex items-center gap-2 font-bold"><CheckCircle2 size={20} />Rezervasyonunuz oluşturuldu</div><p className="mt-1 text-sm">Onay kodu: <strong>{confirmation.confirmation_code}</strong></p></div>}
      <div className="space-y-4 border-t border-slate-100 bg-slate-50 p-5">
        {!loading && results.length === 0 && <div className="py-8 text-center text-sm text-slate-500"><CalendarDays className="mx-auto mb-2" />Tarihleri girerek canlı fiyat ve müsaitlik arayın.</div>}
        {results.flatMap(hotel => hotel.available_room_types.map(room => ({ hotel, room }))).map(({ hotel, room }) => <article key={`${hotel.tenant_id}-${room.room_type}`} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center"><div><h2 className="font-bold">{hotel.hotel_name}</h2><p className="mt-1 flex items-center gap-1 text-xs text-slate-500"><MapPin size={13} />{hotel.city || 'Konum belirtilmedi'}</p><p className="mt-3 flex items-center gap-2 text-sm font-semibold"><BedDouble size={17} style={{ color }} />{room.room_type}</p><p className="mt-1 text-xs text-slate-500">{room.available_rooms} oda müsait · En fazla {room.capacity} kişi</p></div><div className="sm:text-right"><p className="text-xl font-bold">{money(room.total_price, room.currency || hotel.currency)}</p><p className="text-xs text-slate-500">{room.nights} gece konaklama toplamı</p><button onClick={() => setSelected({ hotel, room })} className="mt-3 rounded-lg px-4 py-2 text-sm font-semibold text-white" style={{ backgroundColor: color }}>Rezervasyon yap</button></div></div>
        </article>)}
      </div>
    </section>
    {selected && <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/55 p-4"><form onSubmit={reserve} className="w-full max-w-lg rounded-2xl bg-white p-5 shadow-2xl"><h2 className="text-lg font-bold">Rezervasyon bilgileri</h2><p className="mb-4 text-sm text-slate-500">{selected.hotel.hotel_name} · {selected.room.room_type}</p><div className="grid gap-3 sm:grid-cols-2"><label className="text-xs font-semibold sm:col-span-2">Ad soyad *<input required minLength="2" value={guest.guest_name} onChange={event => setGuest({ ...guest, guest_name: event.target.value })} className="mt-1 h-11 w-full rounded-lg border border-slate-300 px-3" /></label><label className="text-xs font-semibold">E-posta<input type="email" value={guest.guest_email} onChange={event => setGuest({ ...guest, guest_email: event.target.value })} className="mt-1 h-11 w-full rounded-lg border border-slate-300 px-3" /></label><label className="text-xs font-semibold">Telefon<input value={guest.guest_phone} onChange={event => setGuest({ ...guest, guest_phone: event.target.value })} className="mt-1 h-11 w-full rounded-lg border border-slate-300 px-3" /></label><label className="text-xs font-semibold sm:col-span-2">Özel istek<textarea value={guest.special_requests} onChange={event => setGuest({ ...guest, special_requests: event.target.value })} className="mt-1 min-h-20 w-full rounded-lg border border-slate-300 p-3" /></label></div><div className="mt-5 flex justify-end gap-2"><button type="button" onClick={() => setSelected(null)} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold">Vazgeç</button><button disabled={loading} className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" style={{ backgroundColor: color }}>Rezervasyonu onayla</button></div></form></div>}
  </main>;
}
