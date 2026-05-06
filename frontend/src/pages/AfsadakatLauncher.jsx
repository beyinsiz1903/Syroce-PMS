import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Sparkles, ExternalLink, Loader2, ShieldCheck, AlertCircle,
  ShoppingBag, Wrench,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

export default function AfsadakatLauncher({ user, tenant, onLogout }) {
  const navigate = useNavigate();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await axios.get("/integrations/afsadakat/status");
      setStatus(r.data);
    } catch (e) {
      toast.error("Durum alınamadı");
    }
    setLoading(false);
  };

  useEffect(() => { refresh(); }, []);

  const handleLaunch = async () => {
    setOpening(true);
    try {
      const r = await axios.post("/integrations/afsadakat/launch");
      const url = r.data?.url || "";
      if (!url) throw new Error("URL boş");
      // Local-only mode: Af-sadakat sunucusu henüz konfigüre edilmemiş.
      // SSO token üretildi ama yönlendirilecek harici URL yok.
      if (!r.data?.external_ready || url.startsWith("/integrations/afsadakat/not-deployed")) {
        toast.warning(
          "Af-sadakat sunucusu henüz konfigüre edilmemiş. " +
          "Yöneticiniz AFSADAKAT_BASE_URL ayarladığında bu buton hedef sayfayı açacak.",
          { duration: 7000 }
        );
        return;
      }
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Açılamadı");
    }
    setOpening(false);
  };

  if (loading) {
    return (
      <>
        <div className="min-h-[60vh] flex items-center justify-center">
          <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
        </div>
      </>
    );
  }

  const entitled = !!status?.entitled;
  const provisioned = !!status?.provisioned;
  const externalReady = !!status?.external_configured;

  return (
    <>
      <div className="max-w-3xl mx-auto p-4 sm:p-6 space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-violet-600" />
            Sadakat & Omni Inbox
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            Sadakat programı, AI yorum yönetimi, WhatsApp/Meta birleşik mesaj kutusu
            ve misafir servisleri tek panelde — Syroce PMS ile entegre.
          </p>
        </div>

        {!entitled && (
          <Card className="border-amber-200 bg-amber-50">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2 text-amber-900">
                <AlertCircle className="w-5 h-5" /> Aktif aboneliğiniz yok
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-amber-900">
                Bu modülü kullanmak için Modül Pazarı'ndan abonelik başlatın
                (14 gün ücretsiz deneme mevcut).
              </p>
              <Button onClick={() => navigate("/app/module-store")}>
                <ShoppingBag className="w-4 h-4 mr-1" /> Modül Pazarı'na Git
              </Button>
            </CardContent>
          </Card>
        )}

        {entitled && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-emerald-600" />
                Bağlantı Durumu
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="flex items-center justify-between border rounded-md px-3 py-2">
                  <span className="text-slate-600">Abonelik</span>
                  <Badge className="bg-emerald-100 text-emerald-800 border-emerald-200">
                    Aktif
                  </Badge>
                </div>
                <div className="flex items-center justify-between border rounded-md px-3 py-2">
                  <span className="text-slate-600">Hazırlık</span>
                  <Badge className={provisioned
                    ? "bg-emerald-100 text-emerald-800 border-emerald-200"
                    : "bg-amber-100 text-amber-800 border-amber-200"}>
                    {provisioned ? "Tamamlandı" : "Bekliyor"}
                  </Badge>
                </div>
                <div className="flex items-center justify-between border rounded-md px-3 py-2 col-span-2">
                  <span className="text-slate-600">Mod</span>
                  <Badge variant="outline">
                    {status?.mode === "external" ? "Harici sunucu bağlı" :
                     externalReady ? "Bağlanılıyor" : "Yerel (Af-sadakat henüz yayında değil)"}
                  </Badge>
                </div>
              </div>

              {!externalReady && (
                <div className="border-l-4 border-amber-400 bg-amber-50 px-3 py-2 text-sm text-amber-900 flex gap-2">
                  <Wrench className="w-4 h-4 mt-0.5 shrink-0" />
                  <div>
                    Af-sadakat sunucusu henüz konfigüre edilmemiş. Aboneliğiniz aktif —
                    sunucu yayına alındığında "Aç" butonu otomatik olarak çalışacak.
                  </div>
                </div>
              )}

              <Button
                onClick={handleLaunch}
                disabled={opening}
                size="lg"
                className="w-full"
              >
                {opening ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <>
                    <ExternalLink className="w-5 h-5 mr-2" />
                    Sadakat & Inbox'ı Yeni Sekmede Aç
                  </>
                )}
              </Button>
              <p className="text-xs text-slate-500 text-center">
                Tek kullanımlık güvenli giriş bağlantısı (2 dk geçerli)
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </>
  );
}
