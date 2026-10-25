import React from 'react';

export default function MappingIssueCard({ booking, onReview }) {
  return (
    <section className="m-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm" data-testid="mapping-issue-card">
      <div className="flex justify-between gap-2">
        <h4 className="font-semibold">{booking.guest_name || 'Misafir'}</h4>
        <span className="text-xs font-semibold text-amber-800">Eşleştirme bekliyor</span>
      </div>
      <p className="mt-1 text-xs">{booking.provider} · {booking.external_reservation_id || 'Kaynak kimliği incelenmeli'}</p>
      <p className="mt-1 text-xs">{String(booking.check_in || 'Tarih eksik').slice(0, 10)} → {String(booking.check_out || 'Tarih eksik').slice(0, 10)}</p>
      <p className="mt-2">PMS'e kabul edilmemiş kanal kaydı. Bu durum giriş, çıkış veya misafirin gelmediği anlamına gelmez.</p>
      <p className="mt-1 text-xs">Oda kodu: {booking.provider_room_code || '—'} · Fiyat kodu: {booking.provider_rate_code || '—'}</p>
      {booking.duplicate_hold_count > 0 && <p className="mt-1 text-xs">Aynı kaynak için {booking.booking_ids.length} eski tutma kaydı var; tek sorun olarak gösteriliyor. Kaynak kayıtları silinmedi.</p>}
      <p className="mt-2 text-xs">Geliş tarihi gelmişse eşleştirme ve kaynak durumu çözümlenmeden gün sonu kapanmaz. Otomatik No-Show uygulanmaz.</p>
      <button type="button" className="mt-3 rounded border border-amber-400 bg-white px-3 py-1 font-medium" onClick={() => onReview(booking.action_url)}>
        Kanal eşleştirmesini incele
      </button>
    </section>
  );
}
