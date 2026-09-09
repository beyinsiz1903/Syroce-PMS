import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import {
  Activity, AlertCircle, BarChart3, CheckCircle2, ChevronDown,
  Clock, Gauge, Info, RefreshCw, ServerCog,
} from "lucide-react";
import { toast } from "sonner";

import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const STATUS_META = {
  healthy: { label: "Sağlıklı", dot: "bg-emerald-500", badge: "border-emerald-200 bg-emerald-50 text-emerald-800" },
  degraded: { label: "Uyarı", dot: "bg-amber-500", badge: "border-amber-200 bg-amber-50 text-amber-800" },
  unhealthy: { label: "Kritik", dot: "bg-red-500", badge: "border-red-200 bg-red-50 text-red-800" },
  unknown: { label: "Veri yok", dot: "bg-slate-400", badge: "border-slate-200 bg-slate-50 text-slate-700" },
};

const SERVICE_LABELS = {
  mongodb: "Veritabanı",
  redis: "Önbellek (Redis)",
  event_bus: "Olay altyapısı",
  messaging: "Mesajlaşma",
  data_pipeline: "Veri hattı",
  ml_models: "Yapay zekâ modelleri",
};

const SEVERITY_LABELS = { critical: "Kritik", error: "Hata", warning: "Uyarı", info: "Bilgi" };

const ENDPOINT_LABELS = [
  [/channel-manager|hotelrunner|ari/i, "Kanal yönetimi"],
  [/subscription/i, "Abonelik bilgileri"],
  [/messaging|guest-requests/i, "Mesajlaşma ve misafir talepleri"],
  [/room-blocks/i, "Oda blokları"],
  [/\/rooms/i, "Oda bilgileri"],
  [/\/guests/i, "Misafir bilgileri"],
  [/auth/i, "Oturum ve kullanıcı bilgileri"],
  [/revenue/i, "Gelir analizi"],
  [/occupancy/i, "Doluluk analizi"],
];

function normalizeStatus(status) {
  if (["healthy", "degraded", "unhealthy"].includes(status)) return status;
  if (["critical", "down", "failed"].includes(status)) return "unhealthy";
  return "unknown";
}

function StatusBadge({ status }) {
  const meta = STATUS_META[normalizeStatus(status)];
  return (
    <Badge variant="outline" className={meta.badge}>
      <span className={`mr-1.5 h-2 w-2 rounded-full ${meta.dot}`} aria-hidden="true" />
      {meta.label}
    </Badge>
  );
}

function getEndpointLabel(path = "") {
  return ENDPOINT_LABELS.find(([pattern]) => pattern.test(path))?.[1] || "Teknik API isteği";
}

function formatDuration(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toLocaleString("tr-TR", { maximumFractionDigits: 2 })} ms` : "—";
}

function MetricCard({ icon: Icon, label, value, description, tone = "default", testId }) {
  const tones = {
    default: "border-slate-200 bg-white",
    success: "border-emerald-200 bg-emerald-50/50",
    warning: "border-amber-200 bg-amber-50/60",
    danger: "border-red-200 bg-red-50/60",
  };
  return (
    <Card className={`${tones[tone]} shadow-sm`} data-testid={testId}>
      <CardContent className="p-5">
        <div className="flex items-center gap-2 text-sm font-medium text-slate-600">
          <Icon className="h-4 w-4" aria-hidden="true" /> {label}
        </div>
        <div className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">{value}</div>
        <p className="mt-1 text-xs leading-5 text-slate-600">{description}</p>
      </CardContent>
    </Card>
  );
}

export default function ObservabilityDashboard() {
  const [dashMetrics, setDashMetrics] = useState(null);
  const [traces, setTraces] = useState(null);
  const [errorSummary, setErrorSummary] = useState(null);
  const [health, setHealth] = useState(null);
  const [recentTraces, setRecentTraces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [pendingFlush, setPendingFlush] = useState(null);

  const fetchData = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setRefreshing(true);
    try {
      const [metricsRes, traceRes, errorRes, healthRes, recentRes] = await Promise.all([
        axios.get("/observability/metrics"),
        axios.get("/observability/traces/summary?hours=1"),
        axios.get("/observability/errors/summary?hours=24"),
        axios.get("/observability/health"),
        axios.get("/observability/traces?limit=20&slow_only=false"),
      ]);
      setDashMetrics(metricsRes.data);
      setTraces(traceRes.data);
      setErrorSummary(errorRes.data);
      setHealth(healthRes.data);
      setRecentTraces(Array.isArray(recentRes.data) ? recentRes.data : []);
      setLoadError("");
    } catch (error) {
      console.error("Observability data fetch failed:", error);
      setLoadError("Sistem sağlık verileri alınamadı. Bağlantıyı kontrol edip yeniden deneyin.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData({ silent: true });
  }, [fetchData]);

  const flush = async () => {
    const type = pendingFlush;
    setPendingFlush(null);
    if (!type) return;
    try {
      await axios.post(`/observability/${type}/flush`, {});
      toast.success(type === "traces" ? "İstek izleri kaydedildi" : "Uygulama metrikleri kaydedildi");
      await fetchData({ silent: true });
    } catch {
      toast.error("Teknik veriler kaydedilemedi");
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[360px] items-center justify-center bg-slate-50 p-12" data-testid="obs-loading">
        <div className="flex items-center gap-3 text-sm font-medium text-slate-600">
          <RefreshCw className="h-5 w-5 animate-spin" aria-hidden="true" /> Sistem durumu yükleniyor…
        </div>
      </div>
    );
  }

  const overallStatus = normalizeStatus(health?.overall_status);
  const errorRate = Number(traces?.error_rate || 0);
  const delivery = dashMetrics?.messaging_delivery;
  const deliveryTotal = Number(delivery?.success_count || 0) + Number(delivery?.failure_count || 0);
  const deliveryRate = deliveryTotal > 0 ? `${(Number(delivery?.delivery_rate || 0) * 100).toFixed(1)}%` : "Veri yok";

  return (
    <main className="min-h-screen bg-slate-50" data-testid="observability-dashboard">
      <div className="mx-auto max-w-7xl space-y-6 p-4 md:p-6">
        <header className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-blue-600 p-2.5 text-white shadow-sm"><Activity className="h-5 w-5" aria-hidden="true" /></div>
            <div>
              <h1 className="text-2xl font-bold text-slate-950">Sistem Sağlığı</h1>
              <p className="mt-1 text-sm text-slate-600">Teknik servislerin durumu, hatalar ve yanıt süreleri. Otomatik yenileme kapalı; güncel veriler için “Verileri yenile” düğmesini kullanın.</p>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => fetchData()} disabled={refreshing} data-testid="refresh-btn">
            <RefreshCw className={`mr-2 h-4 w-4 ${refreshing ? "animate-spin" : ""}`} aria-hidden="true" />
            {refreshing ? "Yenileniyor…" : "Verileri yenile"}
          </Button>
        </header>

        <Alert className="border-blue-200 bg-blue-50 text-slate-900">
          <Info className="h-4 w-4" aria-hidden="true" />
          <AlertTitle>Bu ekran neyi gösterir?</AlertTitle>
          <AlertDescription>
            Bu panel teknik yöneticiler içindir. Yeşil durumlar normal çalışmayı, sarı durumlar inceleme gerektiren yavaşlama veya kesintiyi, kırmızı durumlar ise müdahale gerektiren hatayı gösterir.
          </AlertDescription>
        </Alert>

        {loadError && (
          <Alert variant="destructive" data-testid="observability-load-error">
            <AlertCircle className="h-4 w-4" aria-hidden="true" />
            <AlertTitle>Veriler yüklenemedi</AlertTitle>
            <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
              <span>{loadError}</span><Button variant="outline" size="sm" onClick={() => fetchData()}>Tekrar dene</Button>
            </AlertDescription>
          </Alert>
        )}

        <Card className="border-slate-200 bg-white shadow-sm" data-testid="service-health">
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <CardTitle className="flex items-center gap-2 text-lg text-slate-950">
                <ServerCog className="h-5 w-5 text-blue-600" aria-hidden="true" /> Teknik servisler
              </CardTitle>
              <StatusBadge status={overallStatus} />
            </div>
          </CardHeader>
          <CardContent>
            {health?.services && Object.keys(health.services).length > 0 ? (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {Object.entries(health.services).map(([name, info]) => (
                  <div key={name} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-medium text-slate-900">{SERVICE_LABELS[name] || name.replace(/_/g, " ")}</span>
                      <StatusBadge status={info.status} />
                    </div>
                    <div className="mt-2 space-y-1 text-xs text-slate-600">
                      {info.latency_ms != null && <p>Yanıt süresi: {formatDuration(info.latency_ms)}</p>}
                      {info.mode && <p>Çalışma biçimi: {info.mode}</p>}
                      {info.failures_1h != null && <p>Son 1 saatte hata: {info.failures_1h}</p>}
                    </div>
                  </div>
                ))}
              </div>
            ) : <p className="text-sm text-slate-600">Servislerden henüz sağlık verisi alınmadı.</p>}
          </CardContent>
        </Card>

        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4" data-testid="metrics-overview" aria-label="Sistem özeti">
          <MetricCard icon={Gauge} label="API istekleri" value={Number(traces?.total_requests || 0).toLocaleString("tr-TR")} description={`Son 1 saat · ${traces?.total_slow || 0} yavaş · ${traces?.active_traces || 0} devam ediyor`} testId="requests-metric" />
          <MetricCard icon={AlertCircle} label="Hata oranı" value={`${(errorRate * 100).toFixed(2)}%`} description={`Son 1 saatte ${traces?.total_errors || 0} hatalı istek`} tone={errorRate > 0.05 ? "danger" : errorRate > 0.01 ? "warning" : "success"} testId="error-rate-metric" />
          <MetricCard icon={BarChart3} label="İşlenen olay sayısı" value={Number(dashMetrics?.event_throughput || 0).toLocaleString("tr-TR")} description="Ölçüm döneminde veri hattından geçen olaylar" testId="throughput-metric" />
          <MetricCard icon={CheckCircle2} label="Mesaj teslim oranı" value={deliveryRate} description={deliveryTotal > 0 ? `${delivery?.success_count || 0} başarılı · ${delivery?.failure_count || 0} başarısız` : "Henüz mesaj teslim verisi oluşmadı"} tone={deliveryTotal === 0 ? "default" : Number(delivery?.delivery_rate || 0) >= 0.95 ? "success" : "warning"} testId="delivery-rate-metric" />
        </section>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Card className="border-slate-200 bg-white shadow-sm" data-testid="endpoint-performance">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-lg text-slate-950"><Clock className="h-5 w-5 text-blue-600" aria-hidden="true" /> API performansı</CardTitle>
              <p className="text-sm text-slate-600">Son 1 saatte en çok kullanılan teknik işlemlerin yanıt süreleri</p>
            </CardHeader>
            <CardContent className="max-h-96 space-y-2 overflow-y-auto">
              {traces?.endpoints?.length > 0 ? traces.endpoints.map((endpoint, index) => (
                <div key={endpoint.id || index} className="rounded-lg border border-slate-200 p-3" title={endpoint.path}>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-medium text-slate-900">{getEndpointLabel(endpoint.path)}</p>
                      <p className="truncate font-mono text-xs text-slate-500">{endpoint.path}</p>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {endpoint.errors > 0 && <Badge variant="destructive">{endpoint.errors} hata</Badge>}
                      {endpoint.slow > 0 && <Badge className="bg-amber-100 text-amber-800 hover:bg-amber-100">{endpoint.slow} yavaş</Badge>}
                    </div>
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-slate-600 sm:grid-cols-4">
                    <span>{endpoint.count} istek</span><span>Ortalama: {formatDuration(endpoint.avg_ms)}</span>
                    <span className={endpoint.p95_ms > 1000 ? "font-semibold text-red-700" : ""}>%95: {formatDuration(endpoint.p95_ms ?? endpoint.max_ms)}</span>
                    <span>En uzun: {formatDuration(endpoint.max_ms)}</span>
                  </div>
                </div>
              )) : <p className="text-sm text-slate-600">Henüz API performans verisi oluşmadı.</p>}
              <p className="pt-2 text-xs text-slate-500">Canlı WebSocket bağlantıları bu sürelere dahil değildir.</p>
            </CardContent>
          </Card>

          <Card className="border-slate-200 bg-white shadow-sm" data-testid="error-summary">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-lg text-slate-950"><AlertCircle className="h-5 w-5 text-red-600" aria-hidden="true" /> Son 24 saatin hataları</CardTitle>
              <p className="text-sm text-slate-600">Tekrarlanan ve müdahale gerektiren teknik hatalar</p>
            </CardHeader>
            <CardContent>
              <div className="mb-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
                <p className="text-sm text-slate-600">Toplam hata</p><p className="text-3xl font-semibold text-slate-950">{errorSummary?.total_errors || 0}</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {errorSummary?.by_severity && Object.entries(errorSummary.by_severity).map(([severity, count]) => (
                    <Badge key={severity} variant={["critical", "error"].includes(severity) ? "destructive" : "secondary"}>{SEVERITY_LABELS[severity] || severity}: {count}</Badge>
                  ))}
                </div>
              </div>
              {errorSummary?.top_errors?.length > 0 ? (
                <div className="space-y-2">
                  {errorSummary.top_errors.slice(0, 8).map((error, index) => (
                    <div key={error.id || index} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 p-3">
                      <span className="break-words text-sm text-slate-800">{error.error_type}</span>
                      <div className="flex shrink-0 items-center gap-2">
                        <Badge variant={["critical", "error"].includes(error.severity) ? "destructive" : "outline"}>{SEVERITY_LABELS[error.severity] || error.severity}</Badge>
                        <span className="text-sm font-medium text-slate-700">{error.count} kez</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">Son 24 saatte kayıtlı teknik hata bulunmuyor.</div>}
            </CardContent>
          </Card>
        </div>

        <Card className="border-slate-200 bg-white shadow-sm" data-testid="recent-traces">
          <CardHeader className="pb-3"><CardTitle className="text-lg text-slate-950">Son API istekleri</CardTitle><p className="text-sm text-slate-600">Sorun incelemesi için kaydedilen son 20 teknik istek</p></CardHeader>
          <CardContent>
            {recentTraces.length > 0 ? (
              <div className="max-h-80 space-y-2 overflow-y-auto">
                {recentTraces.map((trace, index) => (
                  <div key={trace.id || index} className={`flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3 ${trace.is_slow ? "border-amber-200 bg-amber-50" : "border-slate-200"}`}>
                    <div className="min-w-0"><p className="font-medium text-slate-900">{getEndpointLabel(trace.request_path)}</p><p className="truncate font-mono text-xs text-slate-500">{trace.method} {trace.request_path}</p></div>
                    <div className="flex items-center gap-2">
                      <Badge variant={trace.status_code >= 400 ? "destructive" : "secondary"}>HTTP {trace.status_code}</Badge>
                      <span className={`text-sm ${trace.duration_ms > 1000 ? "font-semibold text-red-700" : "text-slate-700"}`}>{formatDuration(trace.duration_ms)}</span>
                      {trace.is_slow && <Badge className="bg-amber-100 text-amber-800 hover:bg-amber-100">Yavaş</Badge>}
                    </div>
                  </div>
                ))}
              </div>
            ) : <p className="text-sm text-slate-600">Henüz kaydedilmiş API isteği bulunmuyor.</p>}
          </CardContent>
        </Card>

        {dashMetrics && (
          <Card className="border-slate-200 bg-white shadow-sm" data-testid="app-metrics">
            <CardHeader className="pb-3"><CardTitle className="text-lg text-slate-950">Uygulama metrikleri</CardTitle></CardHeader>
            <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[
                ["Canlı bağlantı gecikmesi", formatDuration(dashMetrics.websocket_latency?.avg)],
                ["Yapay zekâ işlem süresi", `${dashMetrics.ml_execution_time?.avg || 0} sn`],
                ["Otomatik fiyatlama başarısı", `${(Number(dashMetrics.autopricing?.success_rate || 0) * 100).toFixed(1)}%`],
                ["Rezervasyon senkron gecikmesi", formatDuration(dashMetrics.reservation_sync_lag?.avg)],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl border border-slate-200 bg-slate-50 p-4"><p className="text-xs text-slate-600">{label}</p><p className="mt-1 text-xl font-semibold text-slate-950">{value}</p></div>
              ))}
            </CardContent>
          </Card>
        )}

        <details className="group rounded-xl border border-slate-200 bg-white shadow-sm" data-testid="advanced-technical-actions">
          <summary className="flex cursor-pointer list-none items-center justify-between p-4 font-medium text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
            <span className="flex items-center gap-2"><ServerCog className="h-4 w-4" aria-hidden="true" /> Gelişmiş teknik işlemler</span>
            <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" aria-hidden="true" />
          </summary>
          <div className="border-t border-slate-200 p-4">
            <p className="mb-4 text-sm text-slate-600">Bellekte bekleyen izleme verilerini kalıcı kayda aktarır. Yalnızca teknik inceleme sırasında kullanın.</p>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => setPendingFlush("traces")} data-testid="flush-traces-btn">İstek izlerini kaydet</Button>
              <Button variant="outline" size="sm" onClick={() => setPendingFlush("metrics")} data-testid="flush-metrics-btn">Uygulama metriklerini kaydet</Button>
            </div>
          </div>
        </details>
      </div>

      <AlertDialog open={Boolean(pendingFlush)} onOpenChange={(open) => !open && setPendingFlush(null)}>
        <AlertDialogContent overlayClassName="bg-slate-950/50">
          <AlertDialogHeader><AlertDialogTitle>Teknik veriler kaydedilsin mi?</AlertDialogTitle><AlertDialogDescription>Bu işlem bekleyen {pendingFlush === "traces" ? "API istek izlerini" : "uygulama metriklerini"} kalıcı kayda aktarır. Otel operasyon verilerini değiştirmez.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Vazgeç</AlertDialogCancel><AlertDialogAction onClick={flush}>Kaydet</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </main>
  );
}
