const percent = value => value == null ? '—' : `%${Number(value).toLocaleString('tr-TR', { maximumFractionDigits: 2 })}`;
const remaining = value => value == null ? '—' : value > 0 ? `+${value}` : String(value).replace('-', '−');

export default function ForecastRoomTypeMatrix({ data, basis, onSelect }) {
  const key = basis === 'sellable' ? 'sellable_occupancy_pct' : 'occupancy_pct';
  const groups = [{ label: data.room_type || 'Tüm tesis', rows: data.rows }, ...(data.room_type ? [] : data.room_type_groups || [])];
  return <div className="p-3">
    <p className="mb-2 text-xs text-muted-foreground">Yüzde ve +/− net kalan oda. Kesin grup blokları dahil; günlük listeyle aynı tarih ve veri anı.</p>
    <div className="overflow-auto rounded border print:hidden" role="region" aria-label="Forecast oda tipi matrisi" tabIndex={0}>
      <table className="w-full border-separate border-spacing-0 text-sm" data-testid="forecast-room-type-matrix"><caption className="sr-only">Oda tipine göre doluluk ve kalan oda</caption>
        <thead><tr><th className="sticky left-0 z-20 min-w-40 border-b border-r bg-muted p-2 text-left">Oda tipi</th>{data.rows.map(row => <th key={row.date} className="min-w-24 border-b border-r bg-muted p-2">{new Date(`${row.date}T12:00:00Z`).toLocaleDateString('tr-TR', { day: '2-digit', month: 'short', timeZone: 'UTC' })}</th>)}</tr></thead>
        <tbody>{groups.map(group => <tr key={group.label}><th scope="row" className="sticky left-0 z-10 border-b border-r bg-card p-2 text-left">{group.label}</th>{group.rows.map(row => <td key={row.date} className={`border-b border-r text-center ${row.remaining_rooms < 0 ? 'bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-100' : row.remaining_rooms === 0 ? 'bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-100' : 'bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100'}`}><button className="w-full p-2" type="button" onClick={() => onSelect(row.date)} aria-label={`${group.label}, ${row.date}, ${percent(row[key])}, ${remaining(row.remaining_rooms)} kalan; günlük listeyi aç`}><strong className="block">{percent(row[key])}</strong><span className="block text-xs">{remaining(row.remaining_rooms)} kalan</span></button></td>)}</tr>)}</tbody>
      </table>
    </div>
    <div className="hidden print:block">{Array.from({ length: Math.ceil(data.rows.length / 7) }, (_, page) => {
      const dates = data.rows.slice(page * 7, page * 7 + 7).map(row => row.date);
      return <section key={page} className="forecast-matrix-print-page"><h3>Oda tipi doluluğu · {dates[0]} – {dates.at(-1)}</h3><table className="w-full text-xs"><thead><tr><th>Oda tipi</th>{dates.map(day => <th key={day}>{day}</th>)}</tr></thead><tbody>{groups.map(group => <tr key={group.label}><th>{group.label}</th>{group.rows.filter(row => dates.includes(row.date)).map(row => <td key={row.date}>{percent(row[key])}<br />{remaining(row.remaining_rooms)} kalan</td>)}</tr>)}</tbody></table></section>;
    })}</div>
  </div>;
}
