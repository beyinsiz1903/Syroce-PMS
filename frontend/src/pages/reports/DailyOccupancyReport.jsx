import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { useBusinessDate } from '@/hooks/useBusinessDate';

const shiftOccupancyDate = (day, offset) => {
  const value = new Date(`${day}T12:00:00Z`);
  value.setUTCDate(value.getUTCDate() + offset);
  return value.toISOString().slice(0, 10);
};
const percent = value => value == null ? '—' : `%${value.toLocaleString('tr-TR', { maximumFractionDigits: 2 })}`;
const dayLabel = day => new Date(`${day}T12:00:00Z`).toLocaleDateString('tr-TR', { timeZone: 'UTC' });
const columns = [['date', 'Tarih'], ['physical_rooms', 'Fiziksel'], ['blocked_rooms', 'Satışa kapalı'],
  ['available_rooms', 'Satılabilir'], ['actual_rooms', 'Gerçekleşen oda'], ['actual_occupancy', 'Gerçekleşen %'],
  ['stayovers', 'Devam eden'], ['arrivals', 'Giriş'], ['expected_rooms', 'Beklenen oda'],
  ['expected_occupancy', 'Beklenen %'], ['unassigned_rooms', 'Atanmamış'], ['overbooked_rooms', 'Fazla satış']];

export default function DailyOccupancyReport() {
  const businessDate = useBusinessDate();
  const [first, setFirst] = useState('');
  const [last, setLast] = useState('');
  const [roomType, setRoomType] = useState('');
  const [query, setQuery] = useState(null);
  const [result, setResult] = useState(null);
  const [types, setTypes] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const request = useRef(0);
  useEffect(() => {
    if (!businessDate) return;
    const end = shiftOccupancyDate(businessDate, 29);
    setFirst(businessDate); setLast(end); setRoomType('');
    setQuery({ start_date: businessDate, end_date: end, room_type: '' });
  }, [businessDate]);
  useEffect(() => {
    if (!query) return;
    const version = ++request.current;
    let active = true;
    setLoading(true); setError(''); setResult(null);
    axios.get('/reports/occupancy-calendar', { params: query }).then(({ data }) => {
      if (!active || version !== request.current) return;
      if (data?.start_date !== query.start_date || data?.end_date !== query.end_date ||
          (data.room_type || '') !== query.room_type || !Array.isArray(data.rows)) {
        throw new Error('Doluluk yanıtının kapsamı seçiminizle eşleşmiyor.');
      }
      setResult({ query, data }); setTypes(data.room_types || []);
    }).catch(e => { if (active && version === request.current) setError(e.response?.data?.detail || e.message || 'Doluluk raporu yüklenemedi.'); })
      .finally(() => { if (active && version === request.current) setLoading(false); });
    return () => { active = false; };
  }, [query]);
  const matches = result && result.query.start_date === first && result.query.end_date === last && result.query.room_type === roomType;
  const data = matches ? result.data : null;
  // Presentation only: historical actuals, then on-the-books demand. Today
  // uses demand so arrivals are included; never add actual + expected together.
  const rows = data ? data.rows.map(row => {
    const actual = row.date < data.business_date;
    const prefix = actual ? 'actual' : 'expected';
    const occupied = row[`${prefix}_rooms`];
    return { ...row, occupied, occupancy: row[`${prefix}_occupancy`],
      vacant: occupied == null ? null : Math.max(0, row.available_rooms - occupied),
      basis: actual ? 'Gerçekleşen' : 'Beklenen' };
  }) : [];
  const known = rows.filter(row => row.occupied != null);
  const nights = known.reduce((sum, row) => sum + row.occupied, 0);
  const capacity = known.reduce((sum, row) => sum + row.available_rooms, 0);
  const apply = event => {
    event.preventDefault();
    const start = new Date(`${first}T00:00:00Z`), end = new Date(`${last}T00:00:00Z`);
    const days = (end - start) / 86400000;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(first) || !/^\d{4}-\d{2}-\d{2}$/.test(last) ||
        !Number.isFinite(days) || days < 0 || days > 365) {
      setError('Geçerli bir başlangıç ve bitiş tarihi seçin (en fazla 366 gün).'); return;
    }
    setQuery({ start_date: first, end_date: last, room_type: roomType });
  };
  const download = async () => {
    if (!data || exporting) return;
    setExporting(true); setError('');
    try {
      const response = await axios.get('/reports/occupancy-calendar', {
        params: { ...result.query, output: 'xlsx', snapshot: data.snapshot }, responseType: 'blob',
      });
      if (!String(response.headers?.['content-type']).includes('spreadsheetml')) throw new Error('Geçersiz Excel yanıtı.');
      const url = URL.createObjectURL(response.data);
      const link = document.createElement('a'); link.href = url;
      link.download = `doluluk_${result.query.start_date}_${result.query.end_date}.xlsx`;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      if (e.response?.status === 409) { setResult(null); setError('Doluluk verisi değişti. Ekranı yenileyip Excel çıktısını yeniden alın.'); }
      else setError('Excel çıktısı hazırlanamadı.');
    } finally { setExporting(false); }
  };
  return <section data-testid="section-occupancy" className="space-y-4">
    <h2 className="text-xl font-semibold">Günlük Tesis Doluluğu</h2>
    <form onSubmit={apply} className="flex flex-wrap items-end gap-3 print:hidden">
      <label className="text-sm">Başlangıç<input aria-label="Doluluk başlangıç" type="date" value={first} onChange={e => setFirst(e.target.value)} className="block rounded border p-2" /></label>
      <label className="text-sm">Bitiş<input aria-label="Doluluk bitiş" type="date" value={last} onChange={e => setLast(e.target.value)} className="block rounded border p-2" /></label>
      <label className="text-sm">Oda tipi<select aria-label="Doluluk oda tipi" value={roomType} onChange={e => setRoomType(e.target.value)} className="block rounded border p-2"><option value="">Tüm tesis</option>{types.map(t => <option key={t}>{t}</option>)}</select></label>
      <Button type="submit" disabled={loading}>Göster / Yenile</Button>
      {[1, 7, 30].map(days => <Button key={days} type="button" variant="outline" disabled={!businessDate} onClick={() => { setFirst(businessDate); setLast(shiftOccupancyDate(businessDate, days - 1)); }}>{days === 1 ? 'Bugün' : `Önümüzdeki ${days} gün`}</Button>)}
      <Button type="button" variant="outline" onClick={download} disabled={!data || loading || exporting}>Excel İndir</Button>
      <Button type="button" variant="outline" onClick={() => window.print()} disabled={!data || loading}>Yazdır / PDF</Button>
    </form>
    {loading && <p role="status">Doluluk hesaplanıyor…</p>}
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {!loading && !data && !error && <p role="status">Seçtiğiniz aralığı görüntülemek için Göster düğmesine basın.</p>}
    {data && <>
      <p className="text-sm font-medium">{dayLabel(data.start_date)} – {dayLabel(data.end_date)} · {data.room_type || 'Tüm tesis'}</p>
      <div className="flex flex-wrap items-center gap-x-8 gap-y-2 rounded-lg border bg-white p-4">
        <div><h3 className="text-sm text-slate-600">Seçili dönem doluluğu</h3><strong className="text-3xl" data-testid="occupancy-period-total">{percent(capacity ? nights * 100 / capacity : null)}</strong></div>
        <p className="text-sm text-slate-600">{rows.length} gün · {nights} dolu / {capacity} satılabilir oda-gecesi<br />Günlük yüzdelerin basit ortalaması değildir.</p>
      </div>
      <p className="text-sm text-slate-600">PMS iş günü: {dayLabel(data.business_date)}. Önceki günler gerçekleşen; iş günü ve sonrası beklenen doluluktur. Beklenen doluluğa devam eden konaklamalar ve giriş yapacak kesin rezervasyonlar dahildir.</p>
      <div className="overflow-x-auto rounded-lg border bg-white"><table className="w-full text-sm" data-testid="daily-occupancy-table">
        <caption className="sr-only">Günlük doluluk özeti</caption>
        <thead className="bg-slate-50"><tr>{['Tarih', 'Doluluk %', 'Dolu oda', 'Boş oda', 'Satılabilir oda', 'Veri türü'].map(label => <th key={label} scope="col" className="whitespace-nowrap p-3 text-right first:text-left">{label}</th>)}</tr></thead>
        <tbody>{rows.map(row => <tr key={row.date} className="border-t even:bg-slate-50/50">
          <th scope="row" className="whitespace-nowrap p-3 text-left font-normal">{dayLabel(row.date)}</th>
          <td className="p-3 text-right font-bold">{percent(row.occupancy)}</td>
          <td className="p-3 text-right">{row.occupied ?? '—'}</td>
          <td className="p-3 text-right">{row.vacant ?? '—'}</td>
          <td className="p-3 text-right">{row.available_rooms}</td>
          <td className="whitespace-nowrap p-3 text-right text-slate-600">{row.basis}</td>
        </tr>)}</tbody>
      </table></div>
      {data.rows.some(r => r.assignment_conflicts || r.unknown_room_references || r.occupied_blocked_rooms || r.overbooked_rooms) && <div role="alert" className="rounded border border-amber-400 p-3 text-sm">Envanter tutarsızlığı / fazla satış var; oranlar %100'e kırpılmadı. {data.rows.filter(r => r.assignment_conflicts || r.unknown_room_references || r.occupied_blocked_rooms || r.overbooked_rooms).map(r => <p key={r.date}>{r.date}: {r.assignment_conflicts} atama çakışması, {r.unknown_room_references} bilinmeyen oda, {r.occupied_blocked_rooms} satışa kapalı odada konaklama, {r.overbooked_rooms} fazla satış.</p>)}</div>}
      <Button type="button" variant="outline" className="print:hidden" aria-expanded={showDetails} aria-controls="occupancy-details" onClick={() => setShowDetails(value => !value)}>{showDetails ? 'Detayları gizle' : 'Hesaplama detaylarını göster'}</Button>
      {showDetails && <div id="occupancy-details" className="space-y-3">
        <h3 className="font-semibold">Hesaplama detayları</h3>
        <p className="text-sm text-slate-600">Gerçekleşen iş günü için henüz nihai değildir. Çıkış gecesi, iptal/no-show ve opsiyonlar dahil değildir. Atanmamış kesin rezervasyonlar beklenene dahildir. Kapasite güncel aktif oda envanterine dayanır; tarihsel envanter değildir.</p>
        <div className="grid gap-3 sm:grid-cols-2">{Object.entries(data.totals).map(([key, total]) => <div key={key} className="rounded-lg border p-3"><h4>{key === 'actual' ? 'Gerçekleşen dönem doluluğu' : 'Beklenen dönem doluluğu'}</h4><strong>{percent(total.occupancy)}</strong><p className="text-sm">{total.room_nights} / {total.available_room_nights} oda-gecesi</p></div>)}</div>
        <div className="overflow-x-auto rounded-lg border"><table className="w-full text-sm" data-testid="occupancy-details-table">
          <thead><tr>{columns.map(([key, label]) => <th scope="col" key={key} className="whitespace-nowrap p-2 text-right">{label}</th>)}</tr></thead>
          <tbody>{data.rows.map(row => <tr key={row.date} className="border-t">{columns.map(([key]) => <td key={key} className="whitespace-nowrap p-2 text-right">{key === 'date' ? dayLabel(row[key]) : key.endsWith('_occupancy') ? percent(row[key]) : row[key] ?? '—'}</td>)}</tr>)}</tbody>
        </table></div>
      </div>}
    </>}
  </section>;
}
