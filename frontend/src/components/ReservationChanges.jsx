export default function ReservationChanges({ changes = [], recorded, limit }) {
  const rows = Array.isArray(changes) ? changes.filter(row => row && typeof row.label === 'string') : [];
  if (!rows.length) return <p className="mt-2 text-xs text-gray-500">{recorded
    ? 'İzlenen konaklama ve ücret alanlarında değişiklik yok.'
    : 'Bu eski bildirimde değişen alanların ayrıntısı kaydedilmemiş.'}</p>;
  const visible = limit ? rows.slice(0, limit) : rows;
  return <div className="mt-2 space-y-1 rounded bg-slate-50 px-2 py-1.5 text-xs text-slate-700">
    {visible.map((row, index) => <div key={index}>
      <span className="font-medium">{row.label}:</span>{' '}
      {String(row.from ?? '—')} → {String(row.to ?? '—')}
    </div>)}
    {visible.length < rows.length && <p className="text-blue-700">+{rows.length - visible.length} değişiklik · Ayrıntılar rezervasyonun Geçmiş sekmesinde</p>}
  </div>;
}
