export const occupancyPercent = value => value == null ? '—' : `%${value.toLocaleString('tr-TR', { maximumFractionDigits: 2 })}`;
export const occupancyDay = day => new Date(`${day}T12:00:00Z`).toLocaleDateString('tr-TR', { timeZone: 'UTC' });
export const signedRooms = value => value == null ? '—' : value > 0 ? `+${value}` : String(value).replace('-', '−');

export const occupancyDisplayRows = (rows, businessDate) => rows.map(row => {
  const actual = row.date < businessDate;
  const prefix = actual ? 'actual' : 'expected';
  const occupied = row[`${prefix}_rooms`];
  return { ...row, occupied, occupancy: row[`${prefix}_occupancy`],
    remaining: occupied == null ? null : row.available_rooms - occupied,
    basis: actual ? 'Gerçekleşen' : 'Beklenen' };
});
