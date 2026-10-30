import { useEffect, useRef, useState } from 'react';
import { Bar, CartesianGrid, ComposedChart, LabelList, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ChevronLeft, ChevronRight, Download, Printer, RefreshCw } from 'lucide-react';
import api from '@/api/axios';
import { Button } from '@/components/ui/button';
import { useBusinessDate } from '@/hooks/useBusinessDate';
import { formatCurrencyBreakdown } from '@/lib/reportCurrency';
import { validateReportDate } from '@/utils/reportExports';
import './FrontdeskForecastReport.css';
import ForecastRoomTypeMatrix from './ForecastRoomTypeMatrix';
import { availabilityLabelAnchor, AvailabilityTooltip, RemainingRoomsLabel } from './ForecastAvailabilityLabels';

const views = [['availability', 'Müsaitlik'], ['movements', 'Geliş–Ayrılış'], ['occupancy', 'Doluluk'], ['revenue', 'Gelir'], ['stay_types', 'Konaklama Tipleri']];
const percent = value => value == null ? '—' : `%${Number(value).toLocaleString('tr-TR', { maximumFractionDigits: 2 })}`;
const dateText = value => new Date(`${value}T12:00:00Z`).toLocaleDateString('tr-TR', { day: '2-digit', month: 'short', timeZone: 'UTC' });
const moneyText = (value, currency) => value == null ? 'Doğrulanamadı' : formatCurrencyBreakdown(value, 0, currency);
const tooltipStyle = { backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', color: 'hsl(var(--foreground))' };
const legendLabel = label => <span className="text-foreground">{label}</span>;
const shift = (day, days) => { const value = validateReportDate(day); value.setUTCDate(value.getUTCDate() + days); return value.toISOString().slice(0, 10); };
function validRange(first, last) {
  const days = (validateReportDate(last) - validateReportDate(first)) / 86400000;
  if (days < 0 || days > 365) throw new Error('Başlangıç ve bitiş tarihlerini en fazla 366 gün olacak şekilde seçin.');
}
function presetRange(day, preset) {
  const value = validateReportDate(day), year = value.getUTCFullYear(), month = value.getUTCMonth();
  const iso = date => date.toISOString().slice(0, 10);
  if (preset === 'week') { const first = shift(day, -((value.getUTCDay() + 6) % 7)); return [first, shift(first, 6)]; }
  if (preset === 'month') return [iso(new Date(Date.UTC(year, month, 1))), iso(new Date(Date.UTC(year, month + 1, 0)))];
  if (preset === 'year') return [`${year}-01-01`, `${year}-12-31`];
  return [day, day];
}

export default function FrontdeskForecastReport() {
  const businessDate = useBusinessDate();
  const [first, setFirst] = useState(businessDate);
  const [last, setLast] = useState(() => shift(businessDate, 29));
  const [roomType, setRoomType] = useState('');
  const [types, setTypes] = useState([]);
  const [query, setQuery] = useState(null);
  const [result, setResult] = useState(null);
  const [view, setView] = useState('availability');
  const [detailed, setDetailed] = useState(false);
  const [layout, setLayout] = useState('daily');
  const [basis, setBasis] = useState('physical');
  const [selectedDay, setSelectedDay] = useState('');
  const [chartCurrency, setChartCurrency] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const generation = useRef(0);
  const currentFilters = useRef('');
  const scope = JSON.stringify([first, last, roomType]);
  currentFilters.current = JSON.stringify([scope, view, basis, detailed]);
  useEffect(() => {
    setFirst(businessDate); setLast(shift(businessDate, 29)); setRoomType('');
    setQuery({ start_date: businessDate, end_date: shift(businessDate, 29), room_type: '' });
  }, [businessDate]);
  useEffect(() => {
    if (!query) return;
    const request = ++generation.current;
    let alive = true;
    setLoading(true); setError(''); setResult(null); setSelectedDay('');
    api.get('/reports/frontdesk-forecast', { params: query }).then(({ data }) => {
      if (!alive || generation.current !== request) return;
      if (data?.start_date !== query.start_date || data?.end_date !== query.end_date ||
          (data.room_type || '') !== query.room_type || !Array.isArray(data.rows) || !data.totals || views.some(([key]) => !Array.isArray(data.columns?.[key]) || !data.columns[key].length) ||
          data.rows.some((row, i) => row.date !== shift(query.start_date, i)) || data.rows.length !== (validateReportDate(query.end_date) - validateReportDate(query.start_date)) / 86400000 + 1) {
        throw new Error('Forecast yanıtı seçili tarih ve oda tipiyle eşleşmiyor.');
      }
      setResult({ query, data }); setTypes(data.room_types || []);
      const currencies = Object.keys(data.totals.room_revenue_by_currency || {});
      setChartCurrency(currencies.includes(data.currency) ? data.currency : currencies[0] || data.currency);
    }).catch(e => { if (alive && generation.current === request) setError(typeof e.response?.data?.detail === 'string' ? e.response.data.detail : e.message || 'Forecast yüklenemedi.'); })
      .finally(() => { if (alive && generation.current === request) setLoading(false); });
    return () => { alive = false; };
  }, [query]);
  const matches = result && result.query.start_date === first && result.query.end_date === last && result.query.room_type === roomType;
  const data = matches ? result.data : null;
  const occupancyKey = basis === 'physical' ? 'occupancy_pct' : 'sellable_occupancy_pct';
  const summaryKeys = ['physical_rooms', 'total_occupied_rooms', 'block_rooms', 'blocked_rooms', 'remaining_rooms', 'occupancy_pct'];
  const columns = (data?.columns?.[view] || []).filter(column => detailed || view !== 'availability' || summaryKeys.includes(column.key)).map(column => basis === 'sellable' && view !== 'occupancy' && column.key === 'occupancy_pct'
    ? { ...column, key: 'sellable_occupancy_pct', label: 'Doluluk % (satılabilir)' } : column);
  const chartRows = data?.rows.map(row => ({ ...row, label: dateText(row.date), availability_label_anchor: availabilityLabelAnchor(row), chart_revenue: row.room_revenue_by_currency == null ? null : row.room_revenue_by_currency[chartCurrency] ?? 0 })) || [];
  const knownCurrencies = [...new Set(data?.rows.flatMap(row => Object.keys(row.room_revenue_by_currency || {})) || [])].sort();
  const currencies = knownCurrencies.length ? knownCurrencies : data ? [data.currency] : [];
  const submitRange = (start = first, end = last, kind = roomType) => {
    try { validRange(start, end); setFirst(start); setLast(end); setRoomType(kind); setError(''); setQuery({ start_date: start, end_date: end, room_type: kind }); }
    catch (e) { setError(e.message); }
  };
  const moveRange = direction => {
    try { validRange(first, last); const days = (validateReportDate(last) - validateReportDate(first)) / 86400000 + 1; submitRange(shift(first, days * direction), shift(last, days * direction)); }
    catch (e) { setError(e.message); }
  };
  const download = async () => {
    if (!data || exporting) return;
    const exportScope = currentFilters.current;
    setExporting(true); setError('');
    try {
      const response = await api.get('/reports/frontdesk-forecast', { params: { ...result.query, output: 'xlsx', snapshot: data.snapshot, view, basis, detail: detailed ? 'full' : 'summary' }, responseType: 'blob' });
      if (currentFilters.current !== exportScope) throw new Error('Filtre değişti; yeni kapsamı yükleyip çıktıyı yeniden alın.');
      if (!String(response.headers?.['content-type']).includes('spreadsheetml')) throw new Error('Geçerli Excel çıktısı alınamadı.');
      const url = URL.createObjectURL(response.data);
      const link = document.createElement('a'); link.href = url; link.download = `forecast_${first}_${last}.xlsx`;
      document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      if (e.response?.status === 409) { setResult(null); setError('Forecast verisi değişti. Yenile düğmesiyle raporu tekrar yükleyin.'); }
      else setError(e.message || 'Excel indirilemedi.');
    } finally { setExporting(false); }
  };
  const valueText = (row, column) => column.type === 'money' ? moneyText(row[column.key], data.currency)
    : column.type === 'percent' ? percent(row[column.key])
      : row[column.key] == null ? '—' : column.key === 'remaining_rooms' && row[column.key] > 0 ? `+${row[column.key]}` : row[column.key];
  const chooseChartDay = event => { const index = Number(event?.activeTooltipIndex); const day = event?.activePayload?.[0]?.payload?.date || (Number.isInteger(index) ? chartRows[index]?.date : null); if (day) setSelectedDay(previous => previous === day ? '' : day); };
  return <section className="frontdesk-forecast space-y-3" data-testid="frontdesk-forecast">
    <div className="rounded-lg border bg-card p-3">
      <form className="forecast-toolbar" onSubmit={event => { event.preventDefault(); submitRange(); }}>
        <Button type="button" variant="outline" aria-label="Önceki dönem" onClick={() => moveRange(-1)} disabled={loading}><ChevronLeft className="h-4 w-4" /></Button>
        <label>Başlangıç<input aria-label="Forecast başlangıç" type="date" value={first} onChange={e => setFirst(e.target.value)} /></label>
        <label>Bitiş<input aria-label="Forecast bitiş" type="date" value={last} onChange={e => setLast(e.target.value)} /></label>
        <Button type="button" variant="outline" aria-label="Sonraki dönem" onClick={() => moveRange(1)} disabled={loading}><ChevronRight className="h-4 w-4" /></Button>
        <label>Oda tipi<select aria-label="Forecast oda tipi" value={roomType} onChange={e => setRoomType(e.target.value)}><option value="">Tüm tesis</option>{types.map(type => <option key={type} value={type}>{type}</option>)}</select></label>
        <Button type="submit" aria-label="Raporla / Yenile" disabled={loading && query?.start_date === first && query?.end_date === last && query?.room_type === roomType} data-testid="button-load-frontdesk-forecast"><RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />Raporla</Button>
        <div className="forecast-presets">{[['week', 'Bu hafta'], ['month', 'Bu ay'], ['year', 'Bu yıl'], ['today', 'Günlük durum']].map(([key, label]) => <Button key={key} type="button" size="sm" variant="outline" onClick={() => submitRange(...presetRange(businessDate, key))} disabled={loading}>{label}</Button>)}</div>
        <Button type="button" variant="outline" onClick={download} disabled={!data || loading || exporting}><Download className="mr-2 h-4 w-4" />{exporting ? 'Hazırlanıyor…' : 'Excel'}</Button>
        <Button type="button" variant="outline" aria-label="Yazdır / PDF" onClick={() => window.print()} disabled={!data || loading}><Printer className="mr-2 h-4 w-4" />Yazdır</Button>
      </form>
    </div>
    {loading && <p role="status">Ön büro forecast hesaplanıyor…</p>}
    {error && <p role="alert" className="rounded border border-destructive p-3 text-sm text-destructive">{error}</p>}
    {!loading && !data && !error && <p role="status">Seçili tarih / oda tipi değişti. Raporla düğmesine basın.</p>}
    {data && <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm font-medium">{data.start_date} – {data.end_date} · {data.room_type || 'Tüm tesis'} · İş günü: {data.business_date}</p>
        <label className="text-sm print:hidden">Doluluk bazı <select aria-label="Forecast doluluk bazı" className="rounded border bg-background p-2" value={basis} onChange={e => setBasis(e.target.value)}><option value="physical">Fiziksel oda kapasitesi</option><option value="sellable">Satılabilir oda kapasitesi</option></select></label>
      </div>
      <div className="forecast-kpis">
        <Kpi label="Toplam dolu oda-gecesi" value={data.totals.occupied_room_nights} note={`${data.totals.booked_room_nights} rezervasyon + ${data.totals.block_room_nights} kalan kesin grup bloğu`} />
        <Kpi label="Dönem doluluğu" value={percent(data.totals[occupancyKey])} note={`${basis === 'physical' ? 'Fiziksel' : 'Satılabilir'} oda-gecesine göre ağırlıklı`} testid="forecast-occupancy-total" />
        {view === 'revenue' ? <>
          <Kpi label="Rezervasyon oda bedeli" value={moneyText(data.totals.room_revenue_by_currency, data.currency)} note="Tahsilat / kesinleşmiş muhasebe geliri değildir" />
          <Kpi label="Ort. ücretli oda bedeli" value={moneyText(data.totals.adr_by_currency, data.currency)} note="Comp ve pickup yapılmamış bloklar paydada yok" />
        </> : <>
          <Kpi label="İlk gün net kalan" value={data.rows[0]?.remaining_rooms > 0 ? `+${data.rows[0].remaining_rooms}` : data.rows[0]?.remaining_rooms} note="Eksi sayı fazla satışı gösterir" />
          <Kpi label="İlk gün doluluk" value={percent(data.rows[0]?.[occupancyKey])} note={`${data.rows[0]?.total_occupied_rooms ?? '—'} dolu / ${data.rows[0]?.physical_rooms ?? '—'} fiziksel oda`} />
        </>}
      </div>
      {data.warnings?.length > 0 && <div role="alert" className="rounded border border-amber-400 bg-amber-50 p-3 text-sm text-amber-950">{data.warnings.map(warning => <p key={warning}>{warning}</p>)}</div>}
      {data.rows.some(row => row.overbooked_rooms > 0) && <p role="alert" className="rounded border border-destructive p-3 text-sm text-destructive">Fazla satış var. Net kalan negatif gösterilir; doluluk %100'e kırpılmaz.</p>}
      <div className="rounded-lg border bg-card">
        <div role="group" aria-label="Forecast görünümü" className="forecast-tabs print:hidden">{views.map(([key, label]) => <Button key={key} type="button" variant={view === key ? 'default' : 'ghost'} aria-pressed={view === key} onClick={() => { setView(key); setSelectedDay(''); }}>{label}</Button>)}</div>
        <div className="p-3 sm:p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">{views.find(([key]) => key === view)?.[1]} · Günlük görünüm</h3>{view === 'revenue' && <label className="text-sm">Grafik para birimi <select aria-label="Forecast grafik para birimi" value={chartCurrency} onChange={e => setChartCurrency(e.target.value)} className="rounded border bg-background p-1">{currencies.map(code => <option key={code}>{code}</option>)}</select></label>}</div>
          {view === 'availability' && <div aria-label="Grafik renkleri" className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">{[['Rezervasyon', '#38bdf8'], ['Kesin grup bloğu (kalan)', '#818cf8'], ['Müsait oda', '#fde68a'], ['Kapalı oda', '#64748b']].map(([label, color]) => <span key={label} className="flex items-center gap-1"><span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: color }} />{label}</span>)}</div>}
          {view === 'availability' && <p className="mb-2 text-xs text-muted-foreground">Her günün üzerindeki sayı net kalan odadır; oda kapasitesi değildir. 0 müsait oda olmadığını, eksi değer fazla satışı gösterir.</p>}
          <div className="forecast-chart-scroll" aria-label="Günlük forecast grafiği">
            <div className="forecast-chart" style={{ minWidth: Math.max(700, chartRows.length * 38 + 70) }}>
              <ResponsiveContainer width="100%" height={260}>
                {view === 'occupancy' || view === 'revenue' ? <LineChart data={chartRows} onClick={chooseChartDay} margin={{ top: 12, right: 20, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip contentStyle={tooltipStyle} itemStyle={tooltipStyle} /><Legend formatter={legendLabel} />
                  <Line dataKey={view === 'revenue' ? 'chart_revenue' : occupancyKey} name={view === 'revenue' ? `Rezervasyon oda bedeli (${chartCurrency})` : 'Doluluk %'} stroke="#2563eb" strokeWidth={2} connectNulls={false} />
                </LineChart> : <ComposedChart data={chartRows} onClick={chooseChartDay} margin={{ top: 28, right: 20, left: 0, bottom: 0 }} barCategoryGap="12%">
                  <CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" tick={{ fontSize: 11 }} /><YAxis allowDecimals={false} tick={{ fontSize: 11 }} /><Tooltip content={view === 'availability' ? <AvailabilityTooltip /> : undefined} contentStyle={tooltipStyle} itemStyle={tooltipStyle} />{view !== 'availability' && <Legend formatter={legendLabel} wrapperStyle={{ fontSize: 11 }} />}
                  {(view === 'availability' ? [['booked_rooms', 'Rezervasyon', '#38bdf8'], ['block_rooms', 'Kesin grup bloğu (kalan)', '#818cf8'], ['vacant_rooms', 'Müsait oda', '#fde68a'], ['blocked_rooms', 'Kapalı oda', '#64748b']]
                    : view === 'movements' ? [['arrivals', 'Gelen oda', '#2563eb'], ['departures', 'Ayrılan oda', '#64748b'], ['stayovers', 'Devam eden', '#38bdf8']]
                      : [['comp_rooms', 'Comp', '#38bdf8'], ['house_use_rooms', 'House-use', '#64748b'], ['day_use_rooms', 'Day-use', '#fde68a'], ['group_rooms', 'Pickup grup oda', '#818cf8']]).map(([key, label, fill]) => <Bar key={key} dataKey={key} name={label} fill={fill} stackId={view === 'availability' ? 'rooms' : undefined} isAnimationActive={false} />)}
                  {view === 'availability' && <Line dataKey="availability_label_anchor" stroke="none" dot={false} activeDot={false} legendType="none" tooltipType="none" isAnimationActive={false}>
                    <LabelList dataKey="remaining_rooms" position="top" content={<RemainingRoomsLabel />} />
                  </Line>}
                </ComposedChart>}
              </ResponsiveContainer>
            </div>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">Grafikte bir güne tıklayarak tablodaki günü vurgulayabilirsiniz. Kapalı oda arıza/bakım blokajıdır; grup bloğu ile aynı şey değildir. Konaklama tipleri birbiriyle örtüşebilir, toplanmaz.</p>
        </div>
        {view === 'availability' && <div className="m-3 flex flex-wrap items-center gap-3 print:hidden"><div role="group" aria-label="Forecast tablo düzeni"><Button type="button" size="sm" variant={layout === 'daily' ? 'default' : 'outline'} aria-pressed={layout === 'daily'} onClick={() => setLayout('daily')}>Günlük liste</Button><Button type="button" size="sm" variant={layout === 'matrix' ? 'default' : 'outline'} aria-pressed={layout === 'matrix'} disabled={!Array.isArray(data.room_type_groups)} onClick={() => setLayout('matrix')}>Oda tipi matrisi</Button></div>{layout === 'daily' && <label className="inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={detailed} onChange={event => setDetailed(event.target.checked)} />Tüm sütunları göster (kişi, hareket, gelir)</label>}</div>}
        {view === 'availability' && layout === 'matrix' ? <ForecastRoomTypeMatrix data={data} basis={basis} onSelect={day => { setSelectedDay(day); setLayout('daily'); }} /> : <div className="forecast-table-scroll"><table className="forecast-table" data-testid="frontdesk-forecast-table">
          <caption className="sr-only">Ön büro forecast — {views.find(([key]) => key === view)?.[1]}</caption>
          <thead><tr><th scope="col">Tarih</th>{columns.map(column => <th scope="col" key={column.key}>{column.label}</th>)}</tr></thead>
          <tbody>{data.rows.map(row => <tr key={row.date} className={selectedDay === row.date ? 'forecast-selected-day' : ''} aria-selected={selectedDay === row.date}>
            <th scope="row"><button type="button" onClick={() => setSelectedDay(value => value === row.date ? '' : row.date)} aria-label={`${row.date} gününü vurgula`}>{dateText(row.date)}</button><span className="block text-[10px] font-normal text-muted-foreground">{row.basis === 'actual' ? 'Gerçekleşen' : 'Kayıtlı / OTB'}</span></th>
            {columns.map(column => <td key={column.key} className={column.key === 'remaining_rooms' && row.remaining_rooms < 0 ? 'font-bold text-destructive' : ''}>{valueText(row, column)}</td>)}
          </tr>)}</tbody>
        </table></div>}
      </div>
      <details className="rounded-lg border bg-card p-3 text-sm"><summary className="cursor-pointer font-medium">Hesaplama tanımları ve kapsam</summary><div className="mt-2 space-y-2">{Object.entries(data.definitions || {}).map(([key, value]) => <p key={key}>{value}</p>)}{data.rows.filter(row => row.unallocated_group_blocks || row.assignment_conflicts || row.unknown_room_references || row.occupied_blocked_rooms || row.overbooked_rooms).map(row => <p key={row.date}>{row.date}: {row.unallocated_group_blocks || 0} belirsiz grup bloğu · {row.assignment_conflicts || 0} atama çakışması · {row.unknown_room_references || 0} bilinmeyen oda · {row.occupied_blocked_rooms || 0} kapalı odada konaklama · {row.overbooked_rooms || 0} fazla satış.</p>)}</div></details>
      <p className="text-xs text-muted-foreground">İş gününden önce gerçekleşen geceler, iş günü ve sonrasında mevcut kesin rezervasyonlar gösterilir. Ön büro forecast istatistiksel talep tahmini değildir. Grafikteki +/− müsaitlik değerleri ve tablo aynı veri anlık görüntüsünden gelir.</p>
    </>}
  </section>;
}

function Kpi({ label, value, note, testid }) { return <div className="rounded-lg border bg-card p-3"><h3 className="text-xs font-medium text-muted-foreground">{label}</h3><p className="my-1 text-xl font-semibold tabular-nums" data-testid={testid}>{value ?? '—'}</p><p className="text-xs text-muted-foreground">{note}</p></div>; }
