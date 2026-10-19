// Cumulative pace curves are step functions. Join both lead-day axes, retain
// comparison-only days and never turn an unobserved future interval into zero.
export function mergePaceSeries(current = [], comparison = []) {
  const sort = rows => [...rows].sort((a, b) => b.days_out - a.days_out);
  const left = sort(current);
  const right = sort(comparison);
  const valueAt = (rows, lead) => {
    if (!rows.length || lead < rows.at(-1).days_out) return null;
    if (lead > rows[0].days_out) return 0;
    let latest = null;
    for (const row of rows) {
      if (row.days_out < lead) break;
      latest = row.rooms_on_books;
    }
    return latest;
  };
  return [...new Set([...left, ...right].map(row => row.days_out))].sort((a, b) => b - a)
    .map(days_out => ({ days_out, bu_yil: valueAt(left, days_out), karsilastirma: valueAt(right, days_out) }));
}
