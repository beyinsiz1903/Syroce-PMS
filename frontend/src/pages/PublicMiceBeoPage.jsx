import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatCurrency } from '@/lib/currency';

export default function PublicMiceBeoPage() {
  const [params] = useSearchParams();
  const token = params.get('token');
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [name, setName] = useState('');
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    setData(null); setError(''); setConsent(false); setName('');
    if (!token) { setError('Onay bağlantısı eksik. Otelden yeni bağlantı isteyin.'); return; }
    axios.get('/mice/public/beo/verify', { params: { token } }).then(({ data: result }) => { if (active) setData(result); })
      .catch(() => { if (active) setError('Bağlantı geçersiz, değiştirilmiş veya süresi dolmuş. Otelden yeni bağlantı isteyin.'); });
    return () => { active = false; };
  }, [token]);
  const sign = async e => {
    e.preventDefault();
    if (!consent || !name.trim() || busy) return;
    setBusy(true); setError('');
    try {
      await axios.post('/mice/public/beo/sign', {
        token, signature_name: name.trim(),
        signature_data: JSON.stringify({ type: 'typed_customer_approval', name: name.trim(), acknowledged: true }),
      });
      setData(previous => ({ ...previous, signed: true }));
    } catch { setError('Onay kaydedilemedi. Etkinlik değişmiş olabilir; tekrar göndermeden önce otelle görüşün.'); }
    finally { setBusy(false); }
  };
  return <main className="min-h-screen bg-background px-4 py-8 text-foreground">
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-2xl font-bold">Etkinlik detayları ve müşteri onayı</h1>
      <p className="text-sm text-muted-foreground">Bu bağlantı size özeldir; üçüncü kişilerle paylaşmayın.</p>
      {error && <p role="alert" className="rounded border border-destructive p-3">{error}</p>}
      {!data && !error && <p role="status">Etkinlik yükleniyor…</p>}
      {data && <>
        <Card><CardHeader><CardTitle>{data.event.name}</CardTitle></CardHeader><CardContent className="space-y-3">
          <p>{data.event.client_name} · {data.event.start_date} – {data.event.end_date} · {data.event.expected_pax} kişi</p>
          <p>Durum: {({ tentative: 'Beklemede', definite: 'Kesinleşmiş', confirmed: 'Onaylı', completed: 'Tamamlandı', cancelled: 'İptal' })[data.event.status] || data.event.status}</p>
          {data.event.status === 'cancelled' && <p role="alert">Bu etkinlik iptal edilmiştir. Önceki onay kaydı etkinliğin hâlen geçerli olduğu anlamına gelmez.</p>}
          <h2 className="font-semibold">Salon ve servis planı</h2>
          {data.spaces.map((space, index) => <p key={index}>{space.space_name} · {space.starts_at?.replace('T', ' ')} – {space.ends_at?.replace('T', ' ')} · {space.setup_style}</p>)}
          {data.resources.map((line, index) => <p key={index}>{line.name} · {line.quantity} {line.unit} · {formatCurrency(Number(line.quantity) * Number(line.unit_price), data.event.currency)}</p>)}
          <p className="text-lg font-semibold">Satış bedeli: {formatCurrency(data.event.totals?.grand_total, data.event.currency)}</p>
          <p className="text-xs text-muted-foreground">Vergi/servis bedeli ayrıca tanımlanmamıştır. Bu ekran ödeme veya tahsilat işlemi yapmaz.</p>
          {data.payment_schedule?.length > 0 && <div><h2 className="font-semibold">Ödeme planı</h2>{data.payment_schedule.map((p, index) => <p key={index}>{p.due_date} · {p.label} · {formatCurrency(p.amount, data.event.currency)}</p>)}</div>}
        </CardContent></Card>
        {data.signed ? <p role="status" className="rounded border p-4">Müşteri onayı kaydedildi. Teşekkür ederiz.</p> : !['tentative', 'definite', 'confirmed'].includes(data.event.status) ? <p role="status">Bu etkinlik şu anda müşteri onayına açık değil. Otelle görüşün.</p> : <form onSubmit={sign} className="space-y-4 rounded border p-4">
          <label className="block text-sm">Onaylayan ad soyad<Input required maxLength={200} value={name} onChange={e => setName(e.target.value)} /></label>
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" required checked={consent} onChange={e => setConsent(e.target.checked)} />Yukarıdaki etkinlik detaylarını ve satış bedelini inceledim; müşteri olarak onaylıyorum.</label>
          <p className="text-xs text-muted-foreground">Bu işlem müşteri onay kaydıdır; nitelikli elektronik imza veya ödeme dekontu değildir.</p>
          <Button disabled={busy || !consent || !name.trim()} type="submit">{busy ? 'Kaydediliyor…' : 'Etkinliği onayla'}</Button>
        </form>}
      </>}
    </div>
  </main>;
}
