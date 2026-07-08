import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Copy, ExternalLink, Code } from "lucide-react";
import { toast } from "sonner";

export default function WBESettings() {
  const baseUrl = typeof window !== "undefined" ? window.location.origin : "https://pms.syroce.com";
  const tenantId = "demo-hotel-123";
  const wbeUrl = `${baseUrl}/wbe/${tenantId}`;
  
  const iframeCode = `<iframe src="${wbeUrl}" width="100%" height="800" frameborder="0" style="border: none; max-width: 1200px; margin: 0 auto; display: block; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"></iframe>`;

  const copyToClipboard = (text, message) => {
    navigator.clipboard.writeText(text).then(() => {
      toast.success(message || "Kopyalandı!");
    }).catch(() => {
      toast.error("Kopyalama başarısız oldu.");
    });
  };

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">Web Rezervasyon Motoru (WBE)</h1>
          <p className="text-slate-500 mt-2">Otelinize ait online rezervasyon modülünün entegrasyon ayarları.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ExternalLink className="w-5 h-5 text-indigo-600" /> 
              Direkt Bağlantı (Link)
            </CardTitle>
            <CardDescription>Misafirlerinizi bu linke yönlendirerek doğrudan rezervasyon alabilirsiniz (Örn: Sosyal medya veya e-posta imzanız).</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>WBE URL'niz</Label>
              <div className="flex items-center gap-2">
                <Input readOnly value={wbeUrl} className="bg-slate-50" />
                <Button variant="outline" size="icon" onClick={() => copyToClipboard(wbeUrl, "Link kopyalandı!")}>
                  <Copy className="w-4 h-4" />
                </Button>
              </div>
            </div>
            <div className="pt-2">
              <Button asChild className="w-full bg-indigo-600 hover:bg-indigo-700">
                <a href={wbeUrl} target="_blank" rel="noreferrer">Sayfayı Görüntüle <ExternalLink className="w-4 h-4 ml-2" /></a>
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Code className="w-5 h-5 text-indigo-600" />
              Web Sitesi Entegrasyonu (iframe)
            </CardTitle>
            <CardDescription>Otelinize ait web sitesine (WordPress, Wix vb.) bu kodu yapıştırarak motoru doğrudan sitenizde gösterebilirsiniz.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>iframe Kodu</Label>
              <div className="relative">
                <textarea 
                  readOnly 
                  value={iframeCode} 
                  className="w-full h-32 p-3 text-sm font-mono bg-slate-900 text-green-400 rounded-md outline-none resize-none"
                />
                <Button 
                  size="sm"
                  variant="secondary"
                  className="absolute top-2 right-2 h-8"
                  onClick={() => copyToClipboard(iframeCode, "iframe kodu kopyalandı!")}
                >
                  <Copy className="w-4 h-4 mr-1" /> Kopyala
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="border-indigo-100 bg-indigo-50">
        <CardHeader>
          <CardTitle className="text-lg text-indigo-900">Nasıl Çalışır?</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-indigo-800 text-sm">
          <p>1. WBE linki üzerinden misafirleriniz müsait oda ve fiyatları görüntüleyebilir.</p>
          <p>2. Seçilen odalar için misafir bilgileri girildikten sonra sistemde otomatik olarak bir <b>Ön Rezervasyon (Pending)</b> oluşturulur.</p>
          <p>3. Gelen rezervasyon PMS üzerinden "Bekleyen Rezervasyonlar" veya takvim üzerinde görüntülenir ve tarafınızdan onaylandığında kesinleşir.</p>
        </CardContent>
      </Card>
    </div>
  );
}
