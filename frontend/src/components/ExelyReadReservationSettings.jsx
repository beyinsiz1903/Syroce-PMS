import { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';

const ROOT = '/channel-manager/exely/read-reservation';

export default function ExelyReadReservationSettings({ connection, requestConfig, onChanged }) {
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [number, setNumber] = useState('');
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const enabled = Boolean(connection.read_reservation_enabled);
  const property = String(connection.hotel_code || '');
  const run = async operation => {
    setBusy(true);
    setError('');
    setResult(null);
    try {
      let data;
      if (operation === 'connect') {
        ({ data } = await axios.post(`${ROOT}/connect`, {
          client_id: clientId, client_secret: clientSecret,
          reservation_id: number.trim(), confirmation: `ENABLE_READ_RESERVATION:${property}`,
          ...(property === '501694' && connection.mode === 'sandbox' ? { test_read_only_consent: 'ALLOW_TEST_READ:501694' } : {}),
        }, requestConfig));
        setResult({ status: 'configured', rooms: data.rooms });
        toast.success('Okuma bağlantısı doğrulandı ve şifreli kasaya kaydedildi. Kişi ayrımı henüz değiştirilmedi.');
      } else if (operation === 'pause') {
        await axios.post(`${ROOT}/pause`, {}, requestConfig);
        setResult({ status: 'paused', rooms: [] });
      } else {
        ({ data } = await axios.post(`${ROOT}/reconcile`, { reservation_id: number.trim() }, requestConfig));
        if (!data.success || data.status !== 'verified') throw new Error('EXELY_READ_NOT_VERIFIED');
        setResult(data);
      }
      await onChanged?.();
    } catch (failure) {
      // Do not render request objects, URLs, credentials or vendor bodies.
      const detail = failure.response?.data?.detail;
      const code = typeof detail === 'string' && /^[A-Z0-9_]+$/.test(detail) ? detail : 'EXELY_READ_OPERATION_FAILED';
      setError(code);
      toast.error(code);
    } finally {
      setClientId('');
      setClientSecret('');
      setConsent(false);
      setBusy(false);
    }
  };
  return <Card data-testid="exely-read-reservation-settings">
    <CardHeader>
      <CardTitle>Çocuk yaşı ve kişi ayrımı — Read Reservation API</CardTitle>
      <CardDescription>
        Tesis {property} · {connection.mode === 'sandbox' ? 'Exely TEST ortamı' : 'Exely üretim ortamı'} · {enabled ? 'Okuma bağlantısı açık' : 'Okuma bağlantısı kapalı'}
      </CardDescription>
    </CardHeader>
    <CardContent className="space-y-4">
      <p className="text-sm text-muted-foreground">PMSConnect yatak sayısı yetişkin sayısı değildir. Ayrı okuma API’siyle yetişkin ve çocuk yaşları doğrulanır. Tesis, sürüm, oda, tarih, kişi toplamı ve tutar eşleşmezse işlem durur. Fiyat, tahsilat, folyo, KBS ve Exely teslim onayı değişmez.</p>
      <div className="space-y-2">
        <Label htmlFor="exely-read-number">Doğrulanacak mevcut Exely rezervasyon numarası</Label>
        <Input id="exely-read-number" value={number} onChange={event => setNumber(event.target.value)} placeholder="Örn. YYYYMMDD-tesis-numara" disabled={busy} />
      </div>
      {!enabled && <>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2"><Label htmlFor="exely-read-client">Read Reservation client_id</Label><Input id="exely-read-client" type="password" autoComplete="off" value={clientId} onChange={event => setClientId(event.target.value)} disabled={busy} /></div>
          <div className="space-y-2"><Label htmlFor="exely-read-secret">Read Reservation client_secret</Label><Input id="exely-read-secret" type="password" autoComplete="new-password" value={clientSecret} onChange={event => setClientSecret(event.target.value)} disabled={busy} /></div>
        </div>
        <Label className="flex items-start gap-2"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} disabled={busy} />
          <span>Yalnız bu tesisin rezervasyon okuma anahtarlarının Syroce PMS şifreli kasasında saklanmasını ve otomatik kişi ayrımı doğrulamasını onaylıyorum. Exely’de yalnız Read Reservation API açık olmalıdır.</span>
        </Label>
        {property === '501694' && connection.mode === 'sandbox' && <p className="text-sm text-muted-foreground">Bu onay, genel dış bağlantı deneme kilidi açıkken de yalnız TEST 501694 için token alma ve rezervasyon okuma izni verir. Bu özel izin üretim tesislerine veya yazma API’lerine uygulanmaz; durdurma bu özel izni de kaldırır.</p>}
        <Button onClick={() => run('connect')} disabled={busy || !consent || !number.trim() || !clientId.trim() || !clientSecret.trim()}>Okuma bağlantısını doğrula ve kaydet</Button>
      </>}
      {enabled && <div className="flex flex-wrap gap-2">
        <Button onClick={() => run('reconcile')} disabled={busy || !number.trim()}>Kişi ayrımını doğrula ve düzelt</Button>
        <Button variant="outline" onClick={() => run('pause')} disabled={busy}>Otomatik kişi doğrulamasını durdur</Button>
      </div>}
      <p className="text-xs text-muted-foreground">Otomatik doğrulama, tesisin rezervasyon senkronizasyonu açıksa her çekim sonunda en fazla 25 gelecekteki kaydı kontrol eder. Durdurma, başlamış bir isteği geri almaz. Başlamış konaklama, elle değişmiş kişi bilgileri ve belirsiz çok odalı eşleşmeler otomatik değiştirilmez; hata koduyla incelemeye bırakılır.</p>
      {busy && <p role="status">Exely okuma API’si kontrol ediliyor…</p>}
      {error && <p role="alert">İşlem tamamlanmadı: {error}. Kayıt yeniden okunmadan doğrulandı sayılmaz; çok odalı bir işlemde kısmi sonuç oluşmuş olabilir.</p>}
      {result && <div role="status" className="rounded-md border p-3 space-y-1">
        <p>{result.status === 'verified' ? 'PMS kişi ayrımı güncellendi ve tekrar okunarak doğrulandı.' : result.status === 'paused' ? 'Otomatik kişi doğrulaması durduruldu.' : 'API ve eşleşme doğrulandı; anahtarlar şifreli kasaya kaydedildi. PMS kaydı henüz değiştirilmedi.'}</p>
        {result.rooms?.map((room, index) => <p key={room.booking_id || index}>Oda {index + 1}: {room.adults} yetişkin · {room.children_ages.length} çocuk{room.children_ages.length > 0 ? ` · yaşlar: ${room.children_ages.join(', ')}` : ''}</p>)}
      </div>}
    </CardContent>
  </Card>;
}
