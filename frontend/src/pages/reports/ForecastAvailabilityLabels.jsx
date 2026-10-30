const roomCount = value => Number.isFinite(value) ? String(value) : '—';
const remainingCount = value => Number.isFinite(value) && value > 0 ? `+${value}` : roomCount(value);

// Position only: the label value always comes from the server's signed remaining_rooms.
// A separate line anchor also renders labels when the final stacked bar has zero height.
export function availabilityLabelAnchor(row) {
  const segments = [row.booked_rooms, row.block_rooms, row.vacant_rooms, row.blocked_rooms];
  return segments.every(Number.isFinite) ? segments.reduce((sum, count) => sum + count, 0) : null;
}

export function RemainingRoomsLabel({ value, viewBox }) {
  if (!viewBox || ![viewBox.x, viewBox.y, viewBox.width].every(Number.isFinite)) return null;
  return <text className="forecast-remaining-room-label" x={viewBox.x + viewBox.width / 2} y={viewBox.y - 8}
    textAnchor="middle" fill={value < 0 ? 'hsl(var(--destructive))' : 'hsl(var(--foreground))'} fontSize={12} fontWeight={600}>
    {remainingCount(value)}
  </text>;
}

export function AvailabilityTooltip({ active, payload, label }) {
  const row = payload?.find(entry => entry?.payload)?.payload;
  if (!active || !row) return null;
  return <div className="rounded-md border bg-card p-3 text-sm text-foreground shadow-sm">
    <p className="mb-2 font-medium">{label}</p>
    <p className={`mb-2 font-semibold ${row.remaining_rooms < 0 ? 'text-destructive' : ''}`}>
      Kalan oda: {remainingCount(row.remaining_rooms)}
    </p>
    <dl className="grid grid-cols-[auto_auto] gap-x-4 gap-y-1">
      {[['Rezervasyon', row.booked_rooms], ['Kesin grup bloğu (kalan)', row.block_rooms], ['Kapalı oda', row.blocked_rooms]].map(([name, count]) =>
        <div className="contents" key={name}><dt>{name}</dt><dd className="text-right tabular-nums">{roomCount(count)}</dd></div>)}
    </dl>
  </div>;
}
