import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import Layout from "@/components/Layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Network, CheckCircle2, XCircle, Send, Activity, RefreshCw, Link2, Copy } from "lucide-react";

const isoDate = (offset = 0) => {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
};

export default function CapXIntegration({ user, tenant, onLogout }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [pinging, setPinging] = useState(false);
  const [pingResult, setPingResult] = useState(null);

  const [callbackUrl, setCallbackUrl] = useState("");
  const [callbackJwt, setCallbackJwt] = useState("");
  const [callbackBusy, setCallbackBusy] = useState(false);
  const [callbackResult, setCallbackResult] = useState(null);

  const [avail, setAvail] = useState({
    room_type: "DBL_STD",
    start_date: isoDate(7),
    end_date: isoDate(14),
    available_count: 5,
    price_min: 2500,
    price_max: 3200,
    currency: "TRY",
    auto_publish: true,
    pms_external_ref: `syroce-test-${Date.now()}`,
  });
  const [availResult, setAvailResult] = useState(null);

  const [event, setEvent] = useState({
    event_type: "created",
    pms_external_ref: `syroce-test-${Date.now()}`,
    booking_id: `bk-${Date.now()}`,
    guest_name: "Test Misafir",
    check_in: isoDate(7),
    check_out: isoDate(14),
    amount: 3200,
    currency: "TRY",
  });
  const [eventResult, setEventResult] = useState(null);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get("/capx/status");
      setStatus(data);
    } catch (e) {
      toast.error("Durum okunamadı");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadCallbackUrl = useCallback(async () => {
    try {
      const params = tenant?.id ? { tenant_id: tenant.id } : {};
      const { data } = await axios.get("/capx/callback/url", { params });
      setCallbackUrl(data?.callback_url || "");
    } catch (e) {
      // sessiz: tenant_id yoksa endpoint 400 döner
    }
  }, [tenant?.id]);

  useEffect(() => { loadStatus(); loadCallbackUrl(); }, [loadStatus, loadCallbackUrl]);

  const registerCallback = async () => {
    setCallbackBusy(true); setCallbackResult(null);
    try {
      const body = {};
      if (callbackUrl) body.callback_url = callbackUrl;
      if (tenant?.id) body.tenant_id = tenant.id;
      if (callbackJwt) body.jwt_token = callbackJwt;
      const { data } = await axios.post("/capx/callback/register", body);
      setCallbackResult(data);
      toast.success("Callback URL CapX'e bildirildi");
    } catch (e) {
      const detail = e?.response?.data?.detail;
      const msg = typeof detail === "string"
        ? detail
        : (detail?.error || e.message || "Bilinmeyen hata");
      setCallbackResult({ ok: false, error: detail || msg });
      toast.error(`Callback bildirimi başarısız: ${msg}`);
    } finally {
      setCallbackBusy(false);
    }
  };

  const copyCallback = async () => {
    if (!callbackUrl) return;
    try {
      await navigator.clipboard.writeText(callbackUrl);
      toast.success("URL panoya kopyalandı");
    } catch {
      toast.error("Kopyalama başarısız");
    }
  };

  const ping = async () => {
    setPinging(true); setPingResult(null);
    try {
      const { data } = await axios.post("/capx/ping");
      setPingResult(data);
      if (data.ok) toast.success("CapX bağlantısı başarılı");
      else toast.error(`Ping başarısız: ${data.error || "?"}`);
    } catch (e) {
      const detail = e?.response?.data?.detail || e.message;
      setPingResult({ ok: false, error: typeof detail === "string" ? detail : JSON.stringify(detail) });
      toast.error("Ping hatası");
    } finally {
      setPinging(false);
    }
  };

  const sendAvailability = async () => {
    setAvailResult(null);
    try {
      const { data } = await axios.post("/capx/sync/availability", avail);
      setAvailResult(data);
      toast.success("Müsaitlik gönderildi");
    } catch (e) {
      const detail = e?.response?.data?.detail || e.message;
      setAvailResult({ ok: false, error: detail });
      toast.error("Müsaitlik gönderimi başarısız");
    }
  };

  const sendEvent = async () => {
    setEventResult(null);
    try {
      const { data } = await axios.post("/capx/test-event", event);
      setEventResult(data);
      toast.success("Olay gönderildi (HMAC imzalı)");
    } catch (e) {
      const detail = e?.response?.data?.detail || e.message;
      setEventResult({ ok: false, error: detail });
      toast.error("Olay gönderimi başarısız");
    }
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="capx-integration">
      <div className="p-6 space-y-6 max-w-5xl">
        <div className="flex items-center gap-3">
          <Network className="w-7 h-7 text-emerald-500" />
          <div>
            <h1 className="text-2xl font-bold">CapX Entegrasyonu</h1>
            <p className="text-sm text-slate-500">B2B kapasite paylaşım ağı — push entegrasyonu</p>
          </div>
        </div>

        {/* Status */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2"><Activity className="w-5 h-5" /> Bağlantı Durumu</CardTitle>
            <Button size="sm" variant="outline" onClick={loadStatus} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Yenile
            </Button>
          </CardHeader>
          <CardContent className="space-y-2">
            {!status ? (
              <p className="text-slate-500">Yükleniyor…</p>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  {status.configured ? <CheckCircle2 className="text-emerald-500 w-5 h-5" /> : <XCircle className="text-red-500 w-5 h-5" />}
                  <span className="font-medium">{status.configured ? "Yapılandırılmış" : "Yapılandırma eksik"}</span>
                </div>
                <div className="grid grid-cols-3 gap-2 text-sm">
                  <Badge variant={status.base_url_set ? "default" : "destructive"}>Base URL {status.base_url_set ? "✓" : "✗"}</Badge>
                  <Badge variant={status.api_key_set ? "default" : "destructive"}>API Key {status.api_key_set ? "✓" : "✗"}</Badge>
                  <Badge variant={status.webhook_secret_set ? "default" : "destructive"}>Webhook Secret {status.webhook_secret_set ? "✓" : "✗"}</Badge>
                </div>
                {status.base_url && <p className="text-xs text-slate-500 break-all">{status.base_url}</p>}
                {!status.configured && (
                  <p className="text-xs text-amber-600">
                    Eksik anahtarları <a href="/admin/integration-credentials" className="underline">Entegrasyon Anahtarları</a> sayfasından (CAPX_BASE_URL, CAPX_API_KEY, CAPX_WEBHOOK_SECRET) ekleyin.
                  </p>
                )}
              </>
            )}
            <Button onClick={ping} disabled={pinging || !status?.configured} className="mt-2">
              <Send className="w-4 h-4 mr-1" /> {pinging ? "Test ediliyor…" : "Canlı Bağlantı Testi"}
            </Button>
            {pingResult && (
              <pre className="text-xs bg-slate-100 dark:bg-slate-800 rounded p-3 overflow-auto max-h-48">{JSON.stringify(pingResult, null, 2)}</pre>
            )}
          </CardContent>
        </Card>

        {/* Inbound callback (CapX → PMS) */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Link2 className="w-5 h-5" /> Inbound Callback URL (CapX → PMS)
            </CardTitle>
            <p className="text-xs text-slate-500">
              CapX'in eşleşme olaylarını (match.created / match.cancelled) bu otele
              push edeceği herkese açık webhook adresi. "Aktive Et" CapX'e
              <code className="mx-1 px-1 bg-slate-100 dark:bg-slate-800 rounded">
                PUT /api/integrations/v1/pms/callback
              </code>
              ile bildirir.
            </p>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1">
              <Label className="text-xs">Webhook URL</Label>
              <div className="flex gap-2">
                <Input
                  value={callbackUrl}
                  onChange={(e) => setCallbackUrl(e.target.value)}
                  placeholder="https://pms.example.com/api/webhooks/capx/by-tenant/<tenant-id>"
                />
                <Button
                  type="button" variant="outline" size="icon"
                  onClick={copyCallback} disabled={!callbackUrl}
                  aria-label="Kopyala"
                >
                  <Copy className="w-4 h-4" />
                </Button>
              </div>
              <p className="text-xs text-slate-500">
                Boş bırakırsanız ortam değişkenlerinden
                (PUBLIC_BASE_URL/REPLIT_DEV_DOMAIN) tenant-aware varsayılan üretilir.
              </p>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">CapX JWT (opsiyonel)</Label>
              <Input
                type="password"
                value={callbackJwt}
                onChange={(e) => setCallbackJwt(e.target.value)}
                placeholder="otel hesabınızın CapX paneli login token'ı"
              />
              <p className="text-xs text-slate-500">
                Spec §1 JWT bekliyor. Boş bırakırsanız Bearer API key fallback
                denenir; CapX kabul etmezse 401/403 döner.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                onClick={registerCallback}
                disabled={callbackBusy || !status?.configured}
              >
                <Send className="w-4 h-4 mr-1" />
                {callbackBusy ? "Bildiriliyor…" : "Aktive Et"}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={loadCallbackUrl}>
                <RefreshCw className="w-3.5 h-3.5 mr-1" /> Varsayılanı Yenile
              </Button>
            </div>
            {callbackResult && (
              <pre className="text-xs bg-slate-100 dark:bg-slate-800 rounded p-3 overflow-auto max-h-48">
                {JSON.stringify(callbackResult, null, 2)}
              </pre>
            )}
          </CardContent>
        </Card>

        {/* Availability sync */}
        <Card>
          <CardHeader><CardTitle>Müsaitlik Snapshot Push</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-2 gap-3">
            {[
              ["room_type", "Oda Tipi"],
              ["start_date", "Başlangıç (YYYY-MM-DD)"],
              ["end_date", "Bitiş (YYYY-MM-DD)"],
              ["available_count", "Müsait Sayısı"],
              ["price_min", "Min Fiyat"],
              ["price_max", "Max Fiyat"],
              ["currency", "Para Birimi"],
              ["pms_external_ref", "PMS Ref (idempotent)"],
            ].map(([k, lbl]) => (
              <div key={k} className="space-y-1">
                <Label className="text-xs">{lbl}</Label>
                <Input value={avail[k]} onChange={(e) => setAvail({ ...avail, [k]: e.target.value })} />
              </div>
            ))}
            <div className="col-span-2">
              <Button onClick={sendAvailability} disabled={!status?.configured}>
                <Send className="w-4 h-4 mr-1" /> Gönder
              </Button>
            </div>
            {availResult && (
              <pre className="col-span-2 text-xs bg-slate-100 dark:bg-slate-800 rounded p-3 overflow-auto max-h-48">{JSON.stringify(availResult, null, 2)}</pre>
            )}
          </CardContent>
        </Card>

        {/* Reservation event */}
        <Card>
          <CardHeader>
            <CardTitle>Rezervasyon Olayı (HMAC imzalı)</CardTitle>
            <p className="text-xs text-slate-500">X-CapX-Signature: sha256=… + X-CapX-Event-Id (UUID4 idempotent)</p>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3">
            {[
              ["event_type", "Olay Tipi (created/cancelled/no_show)"],
              ["pms_external_ref", "PMS Ref"],
              ["booking_id", "Rezervasyon ID"],
              ["guest_name", "Misafir Adı"],
              ["check_in", "Giriş"],
              ["check_out", "Çıkış"],
              ["amount", "Tutar"],
              ["currency", "Para Birimi"],
            ].map(([k, lbl]) => (
              <div key={k} className="space-y-1">
                <Label className="text-xs">{lbl}</Label>
                <Input value={event[k]} onChange={(e) => setEvent({ ...event, [k]: e.target.value })} />
              </div>
            ))}
            <div className="col-span-2">
              <Button onClick={sendEvent} disabled={!status?.configured || !status?.webhook_secret_set}>
                <Send className="w-4 h-4 mr-1" /> Gönder
              </Button>
            </div>
            {eventResult && (
              <pre className="col-span-2 text-xs bg-slate-100 dark:bg-slate-800 rounded p-3 overflow-auto max-h-48">{JSON.stringify(eventResult, null, 2)}</pre>
            )}
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
}
