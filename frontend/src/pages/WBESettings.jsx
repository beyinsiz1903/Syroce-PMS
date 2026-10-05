import { useMemo } from 'react';
import { CheckCircle2, Code, Copy, ExternalLink, Hotel, Link2, ShieldCheck, TriangleAlert } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const copyToClipboard = async (text, message) => {
  try {
    await navigator.clipboard.writeText(text);
    toast.success(message || 'Kopyalandı');
  } catch {
    toast.error('Kopyalama başarısız oldu. Tarayıcı pano iznini kontrol edin.');
  }
};

export default function WBESettings({ tenant }) {
  const tenantId = tenant?.id || tenant?.tenant_id || '';
  const propertyName = tenant?.property_name || tenant?.name || 'Oteliniz';
  const baseUrl = typeof window !== 'undefined' ? window.location.origin : 'https://pms.syroce.com';
  const wbeUrl = tenantId ? `${baseUrl}/wbe/${encodeURIComponent(tenantId)}` : '';
  const iframeCode = wbeUrl
    ? `<iframe src="${wbeUrl}" title="${propertyName} rezervasyon" width="100%" height="800" loading="lazy" frameborder="0" style="border:0;max-width:1200px;margin:0 auto;display:block;border-radius:12px"></iframe>`
    : '';

  const readiness = useMemo(() => [
    { label: 'Otel hesabı ve güvenli bağlantı', ready: Boolean(tenantId) },
    { label: 'Otel adı ve marka bilgisi', ready: Boolean(tenant?.property_name || tenant?.name) },
    { label: 'Rezervasyon motoru lisansı', ready: tenant?.modules?.booking_engine !== false },
  ], [tenant, tenantId]);
  const ready = readiness.every((item) => item.ready);

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-4 md:p-6" data-testid="wbe-settings">
      <header className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm md:flex-row md:items-center md:justify-between md:p-6">
        <div className="flex items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-slate-900 text-white"><Hotel className="h-5 w-5" /></div>
          <div>
            <h1 className="text-2xl font-bold text-slate-950">Web Rezervasyon Motoru</h1>
            <p className="mt-1 text-sm text-slate-600">{propertyName} için doğrudan rezervasyon bağlantısı ve web sitesi kurulumu.</p>
          </div>
        </div>
        <span className={`inline-flex w-fit items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold ${ready ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-800'}`}>
          {ready ? <CheckCircle2 className="h-4 w-4" /> : <TriangleAlert className="h-4 w-4" />}
          {ready ? 'Yayına hazır' : 'Kurulum bilgisi eksik'}
        </span>
      </header>

      <section className="grid gap-4 md:grid-cols-3" aria-label="Kurulum durumu">
        {readiness.map((item) => (
          <div key={item.label} className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
            {item.ready ? <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600" /> : <TriangleAlert className="h-5 w-5 shrink-0 text-amber-600" />}
            <span className="font-medium text-slate-800">{item.label}</span>
          </div>
        ))}
      </section>

      {!tenantId && <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">Otel kimliği oturumdan alınamadığı için bağlantı üretilemedi. Otel çalışma alanına geçip sayfayı yenileyin.</div>}

      <section className="grid gap-6 lg:grid-cols-2">
        <Card className="border-slate-200 shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base"><Link2 className="h-5 w-5" /> Doğrudan rezervasyon bağlantısı</CardTitle>
            <CardDescription>Sosyal medya, e-posta, Google işletme profili veya otel web sitesindeki “Rezervasyon Yap” düğmesinde kullanın.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="wbe-url">Otelin rezervasyon adresi</Label>
              <div className="flex gap-2">
                <Input id="wbe-url" readOnly value={wbeUrl} placeholder="Otel kimliği bekleniyor" className="bg-slate-50" />
                <Button variant="outline" size="icon" disabled={!wbeUrl} onClick={() => copyToClipboard(wbeUrl, 'Rezervasyon bağlantısı kopyalandı')} aria-label="Rezervasyon bağlantısını kopyala"><Copy className="h-4 w-4" /></Button>
              </div>
            </div>
            <Button className="w-full" disabled={!ready || !wbeUrl} asChild={Boolean(ready && wbeUrl)}>
              {ready && wbeUrl ? <a href={wbeUrl} target="_blank" rel="noreferrer">Canlı sayfayı aç<ExternalLink className="ml-2 h-4 w-4" /></a> : <span>Kurulum tamamlanınca açılacak</span>}
            </Button>
          </CardContent>
        </Card>

        <Card className="border-slate-200 shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base"><Code className="h-5 w-5" /> Web sitesine yerleştir</CardTitle>
            <CardDescription>WordPress, Wix veya özel web sitenize erişilebilir ve mobil uyumlu rezervasyon alanı ekleyin.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Label htmlFor="wbe-iframe">Yerleştirme kodu</Label>
            <div className="relative">
              <textarea id="wbe-iframe" readOnly value={iframeCode} placeholder="Otel kimliği bekleniyor" className="h-36 w-full resize-none rounded-lg bg-slate-950 p-3 pr-24 font-mono text-xs text-emerald-300 outline-none" />
              <Button size="sm" variant="secondary" disabled={!iframeCode} className="absolute right-2 top-2" onClick={() => copyToClipboard(iframeCode, 'Yerleştirme kodu kopyalandı')}><Copy className="mr-1 h-4 w-4" /> Kopyala</Button>
            </div>
          </CardContent>
        </Card>
      </section>

      <Card className="border-slate-200 bg-slate-50 shadow-none">
        <CardHeader><CardTitle className="flex items-center gap-2 text-base"><ShieldCheck className="h-5 w-5 text-slate-700" /> Rezervasyon akışı</CardTitle></CardHeader>
        <CardContent className="grid gap-3 text-sm text-slate-700 md:grid-cols-3">
          <p><strong className="block text-slate-950">1. Gerçek müsaitlik</strong>Misafir seçtiği tarihler için satılabilir oda tiplerini ve fiyatları görür.</p>
          <p><strong className="block text-slate-950">2. Güvenli talep</strong>Misafir bilgileri ve konaklama tercihi otelin kendi PMS kaydına aktarılır.</p>
          <p><strong className="block text-slate-950">3. Ön büro takibi</strong>Rezervasyon takvimde görünür; ekip onay, ödeme ve misafir iletişimini tamamlar.</p>
        </CardContent>
      </Card>
    </main>
  );
}
