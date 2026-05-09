import React, { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge } from "@/components/ui/status-badge";
import { toast } from "sonner";
import { Network, CheckCircle2, XCircle, Send, Activity, RefreshCw, Link2, Copy } from "lucide-react";
import { useTranslation } from 'react-i18next';

const isoDate = (offset = 0) => {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
};

export default function CapXIntegration({ user, tenant, onLogout }) {
  const { t } = useTranslation();
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
      const resp = await axios.get("/capx/status");
      setStatus(resp.data);
    } catch (e) {
      toast.error("Durum okunamadı: " + (e?.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadCallbackUrl = useCallback(async () => {
    try {
      const params = tenant?.id ? { tenant_id: tenant.id } : {};
      const resp = await axios.get("/capx/callback/url", { params });
      setCallbackUrl(resp.data?.callback_url || "");
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
      const resp = await axios.post("/capx/callback/register", body);
      setCallbackResult(resp.data);
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
      const resp = await axios.post("/capx/ping");
      setPingResult(resp.data);
      if (resp.data?.ok) toast.success("CapX bağlantısı başarılı");
      else toast.error(`Ping başarısız: ${resp.data?.error || "?"}`);
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
      const resp = await axios.post("/capx/sync/availability", avail);
      setAvailResult(resp.data);
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
      const resp = await axios.post("/capx/test-event", event);
      setEventResult(resp.data);
      toast.success("Olay gönderildi (HMAC imzalı)");
    } catch (e) {
      const detail = e?.response?.data?.detail || e.message;
      setEventResult({ ok: false, error: detail });
      toast.error("Olay gönderimi başarısız");
    }
  };

    const missingKeys = useMemo(() => {
      if (!status) return [];
      const out = [];
      if (!status.base_url_set) out.push("CAPX_BASE_URL");
      if (!status.api_key_set) out.push("CAPX_API_KEY");
      if (!status.webhook_secret_set) out.push("CAPX_WEBHOOK_SECRET");
      return out;
    }, [status]);

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <PageHeader
        icon={Network}
        title="CapX Entegrasyonu"
        subtitle={t('cm.pages_CapXIntegration.b2b_kapasite_paylasim_agi_push_entegrasy')}
        actions={
          <Button variant="outline" size="sm" onClick={loadStatus} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? "animate-spin" : ""}`} />
            {t('cm.pages_CapXIntegration.yenile')}
          </Button>
        }
      />

      {/* Status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Activity className="w-5 h-5 text-slate-700" aria-hidden="true" />
            {t('cm.pages_CapXIntegration.baglanti_durumu')}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {!status ? (
            <p className="text-slate-500 text-sm">{t('cm.pages_CapXIntegration.yukleniyor')}</p>
          ) : (
            <>
              <div className="flex items-center gap-2">
                {status.configured
                  ? <CheckCircle2 className="text-emerald-600 w-5 h-5" aria-hidden="true" />
                  : <XCircle className="text-rose-600 w-5 h-5" aria-hidden="true" />}
                <span className="font-medium">
                  {status.configured ? "Yapılandırılmış" : "Yapılandırma eksik"}
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-sm">
                <StatusBadge intent={status.base_url_set ? "success" : "danger"} icon={status.base_url_set ? CheckCircle2 : XCircle}>
                  Base URL {status.base_url_set ? "OK" : "Eksik"}
                </StatusBadge>
                <StatusBadge intent={status.api_key_set ? "success" : "danger"} icon={status.api_key_set ? CheckCircle2 : XCircle}>
                  API Key {status.api_key_set ? "OK" : "Eksik"}
                </StatusBadge>
                <StatusBadge intent={status.webhook_secret_set ? "success" : "danger"} icon={status.webhook_secret_set ? CheckCircle2 : XCircle}>
                  Webhook Secret {status.webhook_secret_set ? "OK" : "Eksik"}
                </StatusBadge>
              </div>
              {status.base_url && (
                <p className="text-xs text-slate-500 break-all font-mono">{status.base_url}</p>
              )}
              {missingKeys.length > 0 && (
                <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-3">
                  Eksik anahtar{missingKeys.length > 1 ? "ları" : "ı"}{" "}
                  {missingKeys.map((k, i) => (
                    <React.Fragment key={k}>
                      <a
                        href={`/admin/integration-credentials#${k}`}
                        className="underline font-mono font-medium hover:text-amber-900"
                      >
                        {k}
                      </a>
                      {i < missingKeys.length - 1 ? ", " : ""}
                    </React.Fragment>
                  ))}
                  {" "}
                  <a href="/admin/integration-credentials" className="underline">
                    {t('cm.pages_CapXIntegration.entegrasyon_anahtarlari')}
                  </a>{" "}
                  {t('cm.pages_CapXIntegration.sayfasindan_ekleyin')}
                </div>
              )}
            </>
          )}
          <Button onClick={ping} disabled={pinging || !status?.configured}>
            <Send className="w-4 h-4 mr-1.5" aria-hidden="true" />
            {pinging ? "Test ediliyor…" : "Canlı Bağlantı Testi"}
          </Button>
          {pingResult && (
            <pre className="text-xs bg-slate-50 border border-slate-200 rounded p-3 overflow-auto max-h-48 font-mono text-slate-700">
              {JSON.stringify(pingResult, null, 2)}
            </pre>
          )}
        </CardContent>
      </Card>

        {/* Inbound callback (CapX → PMS) */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Link2 className="w-5 h-5 text-slate-700" aria-hidden="true" /> Inbound Callback URL (CapX → PMS)
            </CardTitle>
            <p className="text-xs text-slate-500">
              {t('cm.pages_CapXIntegration.capx_in_eslesme_olaylarini_match_created')}
              <code className="mx-1 px-1.5 py-0.5 bg-slate-100 border border-slate-200 rounded text-slate-700 font-mono">
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
                  <Copy className="w-4 h-4" aria-hidden="true" />
                </Button>
              </div>
              <p className="text-xs text-slate-500">
                {t('cm.pages_CapXIntegration.bos_birakirsaniz_ortam_degiskenlerinden_')}
              </p>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">CapX JWT (opsiyonel)</Label>
              <Input
                type="password"
                value={callbackJwt}
                onChange={(e) => setCallbackJwt(e.target.value)}
                placeholder={t('cm.pages_CapXIntegration.otel_hesabinizin_capx_paneli_login_token')}
              />
              <p className="text-xs text-slate-500">
                {t('cm.pages_CapXIntegration.spec_1_jwt_bekliyor_bos_birakirsaniz_bea')}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                onClick={registerCallback}
                disabled={callbackBusy || !status?.configured}
              >
                <Send className="w-4 h-4 mr-1.5" aria-hidden="true" />
                {callbackBusy ? "Bildiriliyor…" : "Aktive Et"}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={loadCallbackUrl}>
                <RefreshCw className="w-3.5 h-3.5 mr-1.5" aria-hidden="true" /> {t('cm.pages_CapXIntegration.varsayilani_yenile')}
              </Button>
            </div>
            {callbackResult && (
              <pre className="text-xs bg-slate-50 border border-slate-200 rounded p-3 overflow-auto max-h-48 font-mono text-slate-700">
                {JSON.stringify(callbackResult, null, 2)}
              </pre>
            )}
          </CardContent>
        </Card>

        {/* Availability sync */}
        <Card>
          <CardHeader><CardTitle>{t('cm.pages_CapXIntegration.musaitlik_snapshot_push')}</CardTitle></CardHeader>
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
                <Send className="w-4 h-4 mr-1.5" aria-hidden="true" /> {t('cm.pages_CapXIntegration.gonder')}
              </Button>
            </div>
            {availResult && (
              <pre className="col-span-2 text-xs bg-slate-50 border border-slate-200 rounded p-3 overflow-auto max-h-48 font-mono text-slate-700">{JSON.stringify(availResult, null, 2)}</pre>
            )}
          </CardContent>
        </Card>

        {/* Reservation event */}
        <Card>
          <CardHeader>
            <CardTitle>{t('cm.pages_CapXIntegration.rezervasyon_olayi_hmac_imzali')}</CardTitle>
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
                <Send className="w-4 h-4 mr-1.5" aria-hidden="true" /> {t('cm.pages_CapXIntegration.gonder_73fb0')}
              </Button>
            </div>
            {eventResult && (
              <pre className="col-span-2 text-xs bg-slate-50 border border-slate-200 rounded p-3 overflow-auto max-h-48 font-mono text-slate-700">{JSON.stringify(eventResult, null, 2)}</pre>
            )}
          </CardContent>
        </Card>
    </div>
  );
}
