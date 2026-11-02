import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

export default function NativeExelyStatus({ status, onRetry }) {
  const ready = status.state === 'ready';
  const connected = ready && status.connected;
  const writesEnabled = connected && status.ariEnabled && status.writeAllowed;
  return <Card data-testid="native-exely-status" className="border-blue-200">
    <CardHeader className="pb-2">
      <CardTitle className="text-base">Güncel Exely bağlantısı</CardTitle>
    </CardHeader>
    <CardContent className="space-y-3 text-sm">
      {!ready ? <div role="status">
        <p>{status.state === 'error' ? 'Exely bağlantı durumu doğrulanamadı. Eski tanı kayıtlarından bağlantı sağlığı çıkarılmadı.' : 'Exely bağlantısı kontrol ediliyor…'}</p>
        {status.state === 'error' && <Button variant="outline" onClick={onRetry}>Durumu tekrar kontrol et</Button>}
      </div> : <>
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline">{connected ? 'Bağlantı kaydı aktif' : 'Bağlantı kapalı'}</Badge>
          <Badge variant="outline" data-testid="native-exely-ari-state" className={writesEnabled ? 'border-emerald-300 bg-emerald-50 text-emerald-800' : 'border-amber-300 bg-amber-50 text-amber-800'}>
            {writesEnabled ? 'ARI gönderimi açık' : 'ARI gönderimi kapalı / engelli'}
          </Badge>
          <Badge variant="outline">Otomatik rezervasyon çekimi: {connected && status.autoPull ? 'Açık' : 'Kapalı'}</Badge>
        </div>
        <p>Tesis kodu: {status.hotelCode || '—'}</p>
        {!writesEnabled && status.blockReason && <p role="status">Gönderim engeli: {status.blockReason}</p>}
        <p className="text-xs text-slate-600">Bu durum gerçek Exely bağlantısı ve gönderim kilitlerinden okunur. Açık bağlantı, tek başına teslimat onayı değildir; gönderim sonucu Fiyat ve Müsaitlik ekranında ayrıca gösterilir.</p>
      </>}
      <div className="flex flex-wrap gap-2">
        <Button asChild size="sm" variant="outline"><Link to="/exely">Exely ayarları</Link></Button>
        <Button asChild size="sm" variant="outline"><Link to="/unified-rate-manager">Müsaitliği yönet</Link></Button>
        <Button asChild size="sm" variant="outline"><Link to="/unified-rate-manager">Fiyatları yönet</Link></Button>
      </div>
    </CardContent>
  </Card>;
}
