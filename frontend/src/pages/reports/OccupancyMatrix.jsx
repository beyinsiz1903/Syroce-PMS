import { useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { occupancyDay, occupancyDisplayRows, occupancyPercent, signedRooms } from './occupancyView';
import './OccupancyMatrix.css';

const cellTone = row => row.remaining < 0
  ? 'bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-200'
  : !row.available_rooms ? 'bg-muted text-muted-foreground'
    : row.remaining === 0 ? 'bg-amber-100 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200'
      : 'bg-emerald-50 text-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200';

export function OccupancyTrend({ rows, label }) {
  const height = 160, top = 18, left = 48, width = 960, bottom = 30;
  const maximum = Math.max(100, Math.ceil(Math.max(0, ...rows.map(row => row.occupancy).filter(Number.isFinite)) / 25) * 25);
  const x = index => left + (rows.length === 1 ? .5 : index / (rows.length - 1)) * (width - left - 24);
  const y = value => top + (1 - value / maximum) * (height - top - bottom);
  const paths = [];
  rows.forEach((row, index) => {
    if (row.occupancy == null) { paths.push([]); return; }
    if (!paths.length) paths.push([]);
    paths[paths.length - 1].push(`${x(index)},${y(row.occupancy)}`);
  });
  const every = Math.max(1, Math.ceil((rows.length - 1) / 6));
  return <figure className="rounded-xl border bg-card p-4" data-testid="occupancy-trend">
    <figcaption className="mb-2 text-sm font-semibold">Günlük doluluk grafiği · {label}</figcaption>
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="block h-32 w-full" role="img" aria-label={`Günlük doluluk grafiği: ${label}`}>
      {[0, 50, 100, ...(maximum > 100 ? [maximum] : [])].map(value => <g key={value}>
        <line x1={left} x2={width - 24} y1={y(value)} y2={y(value)} stroke="currentColor" strokeDasharray="3 4" className={value === 100 && maximum > 100 ? 'text-red-500' : 'text-border'} />
        <text x={left - 8} y={y(value) + 4} textAnchor="end" fontSize="11" fill="currentColor" className="text-muted-foreground">{Math.round(value)}%</text>
      </g>)}
      {paths.filter(points => points.length).map((points, index) => <polyline key={index} points={points.join(' ')} fill="none" stroke="currentColor" strokeWidth="2.5" className="text-blue-600 dark:text-blue-400" />)}
      {rows.map((row, index) => <g key={row.date}>
        {row.occupancy != null && <circle cx={x(index)} cy={y(row.occupancy)} r={rows.length > 90 ? 1.8 : 3.5} fill="currentColor" className={row.remaining < 0 ? 'text-red-600' : 'text-blue-600 dark:text-blue-400'}><title>{occupancyDay(row.date)}: {occupancyPercent(row.occupancy)}, net kalan {signedRooms(row.remaining)}</title></circle>}
        {(index % every === 0 || index === rows.length - 1) && <text x={x(index)} y={height - 7} textAnchor="middle" fontSize="11" fill="currentColor" className="text-muted-foreground">{occupancyDay(row.date).slice(0, 5)}</text>}
      </g>)}
    </svg>
  </figure>;
}

export default function OccupancyMatrix({ data, metric }) {
  const [selection, setSelection] = useState(null);
  const rootLabel = data.room_type ? `${data.room_type} toplamı` : 'Tüm tesis';
  const groups = [{ label: rootLabel, physical_rooms: data.rows[0]?.physical_rooms ?? 0,
    rows: occupancyDisplayRows(data.rows, data.business_date), total: true },
  ...(data.room_type_groups || []).map(group => ({ ...group, rows: occupancyDisplayRows(group.rows, data.business_date) }))];
  const excess = groups.slice(1).flatMap(group => group.rows.filter(row => row.remaining < 0).map(row => ({ label: group.label, row })));
  const primary = row => metric === 'remaining' ? signedRooms(row.remaining)
    : metric === 'occupied' ? String(row.occupied ?? '—') : occupancyPercent(row.occupancy);
  const secondary = row => metric === 'remaining' ? occupancyPercent(row.occupancy) : `${signedRooms(row.remaining)} kalan`;
  return <div className="space-y-3">
    {excess.length > 0 && <p role="alert" className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200">Oda tipi bazında fazla satış var: {excess.slice(0, 5).map(({ label, row }) => `${label}, ${occupancyDay(row.date)}: ${signedRooms(row.remaining)}`).join('; ')}{excess.length > 5 ? ` ve ${excess.length - 5} tarih daha` : ''}. Tesis toplamında boş oda olması bu oda tipindeki açığı gidermez.</p>}
    <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
      <span>+ sayı: satılabilecek oda</span><span>0: yer kalmadı</span><span>− sayı: fazla satış</span><span>—: oran hesaplanamıyor</span>
    </div>
    {!Array.isArray(data.room_type_groups) && <p role="status" className="text-sm text-amber-700">Oda tipi kırılımı bu yanıtta bulunmuyor. Sunucu güncellendikten sonra raporu yenileyin.</p>}
    <div className="max-h-[65vh] overflow-auto rounded-xl border bg-card print:hidden" tabIndex={0} role="region" aria-label="Oda tipi doluluk matrisi">
      <table className="w-full border-separate border-spacing-0 text-sm" data-testid="occupancy-matrix">
        <caption className="sr-only">Oda tiplerine göre günlük doluluk ve artı/eksi net kalan oda</caption>
        <thead><tr><th scope="col" className="sticky left-0 top-0 z-30 min-w-48 border-b border-r bg-muted p-3 text-left">Oda tipi</th>{data.rows.map(row => <th key={row.date} scope="col" className="sticky top-0 z-20 min-w-28 border-b border-r bg-muted p-2 text-center">
          <span className="block">{occupancyDay(row.date)}</span><span className="block text-xs font-normal text-muted-foreground">{new Date(`${row.date}T12:00:00Z`).toLocaleDateString('tr-TR', { weekday: 'short', timeZone: 'UTC' })}{row.date === data.business_date ? ' · İş günü' : ''}</span>
        </th>)}</tr></thead>
        <tbody>{groups.map((group, index) => <tr key={index}>
          <th scope="row" className={`sticky left-0 z-10 border-b border-r p-3 text-left ${group.total ? 'bg-blue-50 dark:bg-blue-950' : 'bg-card'}`}><span className="block font-semibold">{group.label}</span><span className="block text-xs font-normal text-muted-foreground">{group.physical_rooms} fiziksel oda</span></th>
          {group.rows.map(row => <td key={row.date} className={`border-b border-r p-0 ${cellTone(row)}`}>
            <button type="button" className="block w-full px-3 py-3 text-center outline-offset-[-3px] hover:brightness-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600" onClick={() => setSelection({ label: group.label, row })}
              aria-label={`${group.label}, ${occupancyDay(row.date)}, doluluk ${occupancyPercent(row.occupancy)}, net kalan ${signedRooms(row.remaining)}; detayları aç`}>
              <strong className="block text-base tabular-nums">{primary(row)}</strong><span className="block text-xs tabular-nums">{secondary(row)}</span>
            </button>
          </td>)}
        </tr>)}</tbody>
      </table>
    </div>
    <div className="occupancy-matrix-print hidden print:block" aria-hidden="true" data-testid="occupancy-print-matrix">
      {Array.from({ length: Math.ceil(data.rows.length / 7) }, (_, block) => <section key={block}>
        <h3>{data.room_type || 'Tüm tesis'} · {occupancyDay(data.rows[block * 7].date)} – {occupancyDay(data.rows[Math.min(block * 7 + 6, data.rows.length - 1)].date)}</h3>
        <table><thead><tr><th>Oda tipi</th>{data.rows.slice(block * 7, block * 7 + 7).map(row => <th key={row.date}>{occupancyDay(row.date)}</th>)}</tr></thead>
          <tbody>{groups.map((group, index) => <tr key={index}><th>{group.label}</th>{group.rows.slice(block * 7, block * 7 + 7).map(row => <td key={row.date} className={row.remaining < 0 ? 'excess' : ''}><strong>{primary(row)}</strong><span>{secondary(row)}</span></td>)}</tr>)}</tbody>
        </table>
      </section>)}
    </div>
    <p className="text-xs text-muted-foreground">Hesaplamayı görmek için hücreye tıklayın. Geçmiş günler gerçekleşen; iş günü ve sonrası devam eden konaklamalar + kesin rezervasyonlardır. Net kalan = satılabilir kapasite − yer tutan oda/rezervasyon sayısı.</p>
    <Dialog open={!!selection} onOpenChange={open => { if (!open) setSelection(null); }}>
      {selection && <DialogContent className="max-w-xl"><DialogHeader>
        <DialogTitle>{selection.label} · {occupancyDay(selection.row.date)}</DialogTitle>
        <DialogDescription>{selection.row.basis} doluluk. Çıkış gecesi dahil değildir. Oda numarası atanmamış kesin rezervasyonlar da kendi oda tipinden düşülür.</DialogDescription>
      </DialogHeader>
        <dl className="grid grid-cols-2 gap-3 text-sm">{[
          ['Doluluk', occupancyPercent(selection.row.occupancy)], ['Net kalan', signedRooms(selection.row.remaining)],
          ['Yer tutan oda / rezervasyon', selection.row.occupied], ['Satılabilir kapasite', selection.row.available_rooms],
          ['Fiziksel oda', selection.row.physical_rooms], ['Satışa kapalı oda', selection.row.blocked_rooms],
          ['Devam eden', selection.row.stayovers], ['O gün başlayan konaklama', selection.row.arrivals],
          ['Atanmamış kesin rezervasyon', selection.row.unassigned_rooms], ['Atama çakışması', selection.row.assignment_conflicts],
        ].map(([label, value]) => <div key={label} className="rounded-lg bg-muted p-3"><dt className="text-muted-foreground">{label}</dt><dd className="font-semibold">{value ?? '—'}</dd></div>)}</dl>
        <p className="text-xs text-muted-foreground">Güncel aktif oda envanteri ve tarihli satışa kapalı odalar kullanılır. Bu ekran kanal satış limitini değiştirmez.</p>
      </DialogContent>}
    </Dialog>
  </div>;
}
