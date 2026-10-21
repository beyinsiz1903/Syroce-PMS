import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatCurrencyBreakdown } from '@/lib/reportCurrency';

export function eventReadiness(event, today) {
  if (['completed', 'cancelled'].includes(event.status)) return [];
  const issues = [];
  if (!event.space_bookings?.length) issues.push('Mekan / saat planı eksik');
  if (!event.agenda?.length) issues.push('Operasyon programı eksik');
  if (!event.organizer_user) issues.push('Etkinlik sorumlusu eksik');
  if (!event.client_email && !event.client_phone) issues.push('Müşteri iletişim bilgisi eksik');
  if (!event.payment_schedule?.length && event.totals?.grand_total > 0) issues.push('Ödeme planı eksik');
  const overdue = (event.payment_schedule || []).filter(p => !p.paid && p.due_date < today);
  if (overdue.length) issues.push(`${overdue.length} vadesi geçmiş ödeme planı satırı`);
  return issues;
}

export default function ReadinessPanel({ events, onOpen, totalCount }) {
  const today = new Date().toLocaleDateString('en-CA');
  const rows = events.filter(e => !['cancelled', 'completed'].includes(e.status));
  const due = {};
  const paid = {};
  events.filter(e => e.status !== 'cancelled').forEach(event => {
    const currency = event.currency || 'TRY';
    (event.payment_schedule || []).forEach(p => {
      const bucket = p.paid ? paid : due;
      bucket[currency] = (bucket[currency] || 0) + Number(p.amount || 0);
    });
  });
  return <div className="space-y-4">
    <p className="text-sm text-muted-foreground">Bu kontrol listesi yüklenen {events.length} etkinliği kapsar{totalCount > events.length ? `; filtrede toplam ${totalCount} kayıt var, diğer sayfaları da inceleyin` : ''}. Plan işaretleri banka/kasa mutabakatı veya tahsilat makbuzu değildir.</p>
    <div className="grid gap-4 sm:grid-cols-2">
      <Card><CardHeader><CardTitle className="text-base">Ödenmemiş plan tutarı</CardTitle></CardHeader><CardContent>{formatCurrencyBreakdown(due)}</CardContent></Card>
      <Card><CardHeader><CardTitle className="text-base">Ödendi işaretli plan tutarı</CardTitle></CardHeader><CardContent>{formatCurrencyBreakdown(paid)}</CardContent></Card>
    </div>
    <Card><CardHeader><CardTitle className="text-base">Satış → operasyon hazırlığı</CardTitle></CardHeader><CardContent className="space-y-3">
      {!rows.length && <p className="text-muted-foreground">Bu kapsamda açık etkinlik yok.</p>}
      {rows.map(event => {
        const issues = eventReadiness(event, today);
        return <div key={event.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
          <div className="space-y-2"><strong>{event.name}</strong><p className="text-xs text-muted-foreground">{event.start_date} · {event.client_name}</p>
            <div className="flex flex-wrap gap-1">{issues.length ? issues.map(issue => <Badge key={issue} variant="outline">{issue}</Badge>) : <Badge variant="outline">Kontrol listesi tamam</Badge>}</div>
          </div>
          <Button variant="outline" size="sm" onClick={() => onOpen(event)}>Etkinliği aç</Button>
        </div>;
      })}
    </CardContent></Card>
  </div>;
}
