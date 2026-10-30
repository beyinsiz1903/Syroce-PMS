export function scheduleSpan(row, day) {
  const minutes = value => Number(value.slice(11, 13)) * 60 + Number(value.slice(14, 16));
  if (!row.starts_at || !row.ends_at || row.status === 'cancelled') return null;
  if (row.starts_at.slice(0, 10) > day || row.ends_at.slice(0, 10) < day) return null;
  const start = row.starts_at.slice(0, 10) < day ? 0 : minutes(row.starts_at);
  const end = row.ends_at.slice(0, 10) > day ? 1440 : minutes(row.ends_at);
  return end > start ? { start, end } : null;
}

export function scheduleCells(rows, day, hours, keyField) {
  const map = new Map();
  for (const booking of rows) {
    const span = scheduleSpan(booking, day);
    if (!span || !booking[keyField]) continue;
    const first = Math.max(Math.floor(span.start / 60), hours[0]);
    for (const hour of hours) {
      if (hour * 60 >= span.end || (hour + 1) * 60 <= span.start) continue;
      const key = `${booking[keyField]}@${hour}`;
      if (!map.has(key)) map.set(key, []);
      map.get(key).push({ booking, isStart: hour === first, isFirstVisible: hour === first });
    }
  }
  return map;
}

export function scheduleOutsideGrid(rows, day, hours) {
  return rows.filter(row => { const span = scheduleSpan(row, day); return span && (span.start < hours[0] * 60 || span.end > (hours.at(-1) + 1) * 60); });
}
