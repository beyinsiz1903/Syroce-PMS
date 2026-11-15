import { useRef, useState } from 'react';
import axios from 'axios';
import apiErrorText from '@/utils/apiErrorText';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';

export default function ReservationOccupancyEditor({ booking, onSaved }) {
  const [open, setOpen] = useState(false);
  const [adults, setAdults] = useState('');
  const [children, setChildren] = useState('');
  const [ages, setAges] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const lock = useRef(false);
  const save = async e => {
    e.preventDefault();
    if (lock.current) return;
    const a = Number(adults), c = Number(children);
    if (adults === '' || children === '' || !Number.isInteger(a) || !Number.isInteger(c) || a < 1 || a > 50 || c < 0 || c > 50 || ages.some(age => age === '' || !Number.isInteger(Number(age)) || Number(age) < 0 || Number(age) > 17)) {
      setError('Yetişkin, çocuk sayısı ve çocuk yaşlarını kontrol edin.'); return;
    }
    lock.current = true; setBusy(true); setError('');
    try {
      await axios.put(`/pms/bookings/${booking.id}`, { adults: a, children: c, children_ages: ages.map(Number) });
      setOpen(false); toast.success('Konuk sayısı güncellendi');
      void Promise.resolve().then(() => onSaved?.()).catch(() => toast.warning('Konuk sayısı kaydedildi. Kartı yenileyin.'));
    } catch (err) { setError(apiErrorText(err, 'Konuk sayısı güncellenemedi')); }
    finally { lock.current = false; setBusy(false); }
  };
  if (!open) return <Button size="sm" variant="outline" onClick={() => { setAdults(String(booking.adults ?? '')); setChildren(String(booking.children ?? '')); setAges(Array.from({ length: booking.children || 0 }, (_, i) => String(booking.children_ages?.[i] ?? ''))); setOpen(true); }}>Konuk sayısını düzenle</Button>;
  return <form onSubmit={save} className="rounded-lg border p-3 space-y-3">
    <p className="text-sm text-slate-600">Konuk sayısı ve çocuk yaşları rezervasyona kaydedilir. Mevcut fiyat değişmez; fiyat düzenlemesi için günlük fiyatları kullanın.</p>
    <fieldset disabled={busy} className="flex flex-wrap gap-3">
      <label>Yetişkin<input aria-label="Yetişkin sayısı" className="block border rounded p-2 w-24" type="number" min="1" max="50" required value={adults} onChange={e => setAdults(e.target.value)} /></label>
      <label>Çocuk<input aria-label="Çocuk sayısı" className="block border rounded p-2 w-24" type="number" min="0" max="50" required value={children} onChange={e => { setChildren(e.target.value); setAges(prev => Array.from({ length: Math.max(0, Math.min(50, Number(e.target.value) || 0)) }, (_, i) => prev[i] ?? '')); }} /></label>
      {ages.map((age, i) => <label key={i}>{i + 1}. çocuk yaşı<input aria-label={`${i + 1}. çocuk yaşı`} className="block border rounded p-2 w-24" type="number" min="0" max="17" required value={age} onChange={e => setAges(prev => prev.map((v, n) => n === i ? e.target.value : v))} /></label>)}
    </fieldset>
    {error && <p role="alert" className="text-red-700">{error}</p>}
    <div className="flex gap-2"><Button type="submit" disabled={busy}>Kaydet</Button><Button type="button" variant="outline" disabled={busy} onClick={() => setOpen(false)}>Vazgeç</Button></div>
  </form>;
}
