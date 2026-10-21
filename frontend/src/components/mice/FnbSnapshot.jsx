export default function FnbSnapshot({ order }) {
  return <div className="space-y-2 text-xs">
    {order.needs_review && <p role="alert" className="rounded border border-destructive p-2 text-destructive">Etkinlik iptal edilmiş, değişmiş veya eski sipariş sürümü doğrulanamıyor. Üretime devam etmeden önce banket ekibiyle teyit edin; gerekiyorsa eski emri iptal edip yeni sürümü gönderin.</p>}
    {order.cancel_reason && <p className="font-semibold">İptal gerekçesi: {order.cancel_reason}</p>}
    {(order.lines || []).map((line, i) => <div key={i} className="rounded bg-muted p-2">
      <p className="font-semibold">{line.name} · {line.quantity} {line.unit}</p>
      {line.notes && <p>{line.notes}</p>}
      {line.menu_id && !line.menu_snapshot && <p className="font-semibold">Eski kayıtta menü içeriği ve alerjen dökümü saklanmamış; üretimden önce teyit edin.</p>}
      {line.menu_snapshot?.allergens?.length > 0 && <p>Alerjenler: {line.menu_snapshot.allergens.join(', ')}</p>}
      {line.menu_snapshot?.dietary_tags?.length > 0 && <p>Diyetler: {line.menu_snapshot.dietary_tags.join(', ')}</p>}
      {line.menu_snapshot?.courses?.map((course, idx) => <p key={idx}>{idx + 1}. {course.name}{course.description ? ` — ${course.description}` : ''}</p>)}
    </div>)}
  </div>;
}
