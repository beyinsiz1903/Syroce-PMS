import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { KpiCard } from "@/components/ui/kpi-card";
import {
  Plug, RefreshCw, CheckCircle2, KeyRound, Wrench,
  ExternalLink, ShieldCheck, AlertCircle, Settings2,
  ArrowRight, Info,
} from "lucide-react";

const CATEGORY_TONE = {
  ai: "bg-indigo-50 text-indigo-700 border-indigo-200",
  messaging: "bg-emerald-50 text-emerald-700 border-emerald-200",
  "channel-manager": "bg-sky-50 text-sky-700 border-sky-200",
  identity: "bg-slate-50 text-slate-700 border-slate-200",
  loyalty: "bg-amber-50 text-amber-700 border-amber-200",
  b2b: "bg-violet-50 text-violet-700 border-violet-200",
  payment: "bg-rose-50 text-rose-700 border-rose-200",
  monitoring: "bg-cyan-50 text-cyan-700 border-cyan-200",
  infrastructure: "bg-zinc-50 text-zinc-700 border-zinc-200",
};

function CategoryBadge({ category, label }) {
  const tone = CATEGORY_TONE[category] || "bg-slate-50 text-slate-600 border-slate-200";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium border ${tone}`}>
      {label}
    </span>
  );
}

function IntegrationCard({ item, status }) {
  // status: "ready" | "needs" | "dev"
  const isReady = status === "ready";
  const isNeeds = status === "needs";
  const isDev = status === "dev";

  return (
    <Card className={`p-4 flex flex-col gap-3 ${isDev ? "opacity-70 bg-slate-50/40" : ""}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-semibold text-slate-900 text-sm leading-tight truncate">{item.name}</h3>
          </div>
          <CategoryBadge category={item.category} label={item.category_label} />
        </div>
        {isReady && <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />}
        {isNeeds && <KeyRound className="w-5 h-5 text-amber-600 flex-shrink-0" />}
        {isDev && <Wrench className="w-5 h-5 text-slate-400 flex-shrink-0" />}
      </div>

      <p className="text-xs text-slate-600 leading-relaxed">{item.description}</p>

      {item.per_tenant && (
        <div className="flex items-start gap-1.5 text-[11px] text-slate-500 bg-slate-50 px-2 py-1.5 rounded">
          <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
          <span>Otele özel kimlik bilgileri (her otel kendi panelinden girer).</span>
        </div>
      )}

      {!item.per_tenant && item.required_envs?.length > 0 && (
        <div className="space-y-1">
          <div className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">
            Gerekli Anahtarlar
          </div>
          <div className="flex flex-wrap gap-1">
            {item.required_envs.map((env) => {
              const missing = (item.missing_envs || []).includes(env);
              return (
                <span
                  key={env}
                  className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                    missing
                      ? "bg-amber-50 text-amber-800 border-amber-200"
                      : "bg-emerald-50 text-emerald-800 border-emerald-200"
                  }`}
                  title={missing ? "Eksik" : "Tanımlı"}
                >
                  {env}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {item.pricing_note && (
        <div className="text-[11px] text-slate-500 italic border-l-2 border-slate-200 pl-2">
          {item.pricing_note}
        </div>
      )}

      <div className="flex items-center justify-between pt-2 mt-auto border-t border-slate-100">
        {item.module_key ? (
          <span className="text-[10px] font-mono text-slate-400">
            modül: {item.module_key}
          </span>
        ) : <span />}
        <div className="flex items-center gap-1">
          {item.doc_url && (
            <a
              href={item.doc_url}
              target="_blank"
              rel="noreferrer"
              className="text-slate-400 hover:text-slate-700 p-1"
              title="Sağlayıcı dokümanı"
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}
          {isNeeds && (
            <Link to={`/admin/integration-credentials#${item.required_envs[0] || ""}`}>
              <Button size="sm" variant="default" className="h-7 text-xs">
                Anahtarları Gir
                <ArrowRight className="w-3 h-3 ml-1" />
              </Button>
            </Link>
          )}
          {isReady && !item.per_tenant && item.required_envs?.length > 0 && (
            <Link to={`/admin/integration-credentials#${item.required_envs[0] || ""}`}>
              <Button size="sm" variant="outline" className="h-7 text-xs">
                <Settings2 className="w-3 h-3 mr-1" />
                Yönet
              </Button>
            </Link>
          )}
        </div>
      </div>
    </Card>
  );
}

function ColumnHeader({ icon: Icon, title, count, intent }) {
  const tones = {
    success: "text-emerald-700 border-emerald-300 bg-emerald-50",
    warning: "text-amber-800 border-amber-300 bg-amber-50",
    neutral: "text-slate-600 border-slate-300 bg-slate-100",
  };
  return (
    <div className={`flex items-center justify-between px-3 py-2 rounded-t-md border ${tones[intent]}`}>
      <div className="flex items-center gap-2">
        <Icon className="w-4 h-4" />
        <h2 className="font-semibold text-sm">{title}</h2>
      </div>
      <Badge variant="outline" className="bg-white text-slate-700 text-xs">
        {count}
      </Badge>
    </div>
  );
}

export default function IntegrationsOverview() {
  const [data, setData] = useState({ ready: [], needs_credentials: [], in_development: [], totals: {} });
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get("/admin/integrations-overview");
      setData(data);
    } catch (e) {
      toast.error("Entegrasyon listesi yüklenemedi: " + (e?.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const totals = data.totals || {};
  const total = totals.all || 0;
  const readyPct = total ? Math.round(((totals.ready || 0) / total) * 100) : 0;

  const sortByCategory = (a, b) => {
    if (a.category === b.category) return a.name.localeCompare(b.name, "tr");
    return a.category.localeCompare(b.category);
  };
  const ready = useMemo(() => [...(data.ready || [])].sort(sortByCategory), [data.ready]);
  const needs = useMemo(() => [...(data.needs_credentials || [])].sort(sortByCategory), [data.needs_credentials]);
  const dev = useMemo(() => [...(data.in_development || [])].sort(sortByCategory), [data.in_development]);

  return (
    <div className="p-4 lg:p-6 max-w-[1600px] mx-auto">
      <PageHeader
        icon={Plug}
        title="Entegrasyon Genel Bakış"
        subtitle="Tüm 3. parti servislerin kod ve API anahtarı durumu. Bir anahtar girildiğinde entegrasyon otomatik olarak Hazır sütununa geçer."
        actions={
          <>
            <Link to="/admin/integration-credentials">
              <Button variant="outline" size="sm">
                <KeyRound className="w-4 h-4 mr-1.5" />
                Anahtar Yönetimi
              </Button>
            </Link>
            <Button variant="outline" size="sm" onClick={load} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? "animate-spin" : ""}`} />
              Yenile
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <KpiCard
          icon={ShieldCheck}
          label="Toplam Entegrasyon"
          value={total}
          sub={`${readyPct}% kullanıma hazır`}
          intent="default"
        />
        <KpiCard
          icon={CheckCircle2}
          label="Hazır"
          value={totals.ready || 0}
          sub="Otellere atanabilir"
          intent="success"
        />
        <KpiCard
          icon={KeyRound}
          label="API Bekleniyor"
          value={totals.needs_credentials || 0}
          sub="Kod tamam, anahtar eksik"
          intent="warning"
        />
        <KpiCard
          icon={Wrench}
          label="Geliştirmede"
          value={totals.in_development || 0}
          sub="Kod henüz tamamlanmadı"
          intent="neutral"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* HAZIR */}
        <div className="flex flex-col">
          <ColumnHeader icon={CheckCircle2} title="Hazır" count={ready.length} intent="success" />
          <div className="border border-t-0 border-emerald-200 rounded-b-md p-3 space-y-3 bg-white min-h-[200px]">
            {loading && <div className="text-xs text-slate-400">Yükleniyor…</div>}
            {!loading && ready.length === 0 && (
              <div className="text-xs text-slate-400 text-center py-8">Henüz hazır entegrasyon yok.</div>
            )}
            {ready.map((it) => (
              <IntegrationCard key={it.key} item={it} status="ready" />
            ))}
          </div>
        </div>

        {/* API GEREKLİ */}
        <div className="flex flex-col">
          <ColumnHeader icon={KeyRound} title="API Bilgileri Gerekli" count={needs.length} intent="warning" />
          <div className="border border-t-0 border-amber-200 rounded-b-md p-3 space-y-3 bg-white min-h-[200px]">
            {!loading && needs.length === 0 && (
              <div className="text-xs text-slate-400 text-center py-8">
                <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
                Tüm anahtarlar tanımlı.
              </div>
            )}
            {needs.map((it) => (
              <IntegrationCard key={it.key} item={it} status="needs" />
            ))}
          </div>
        </div>

        {/* GELİŞTİRMEDE */}
        <div className="flex flex-col">
          <ColumnHeader icon={Wrench} title="Geliştirme Sürecinde" count={dev.length} intent="neutral" />
          <div className="border border-t-0 border-slate-200 rounded-b-md p-3 space-y-3 bg-slate-50/30 min-h-[200px]">
            {!loading && dev.length === 0 && (
              <div className="text-xs text-slate-400 text-center py-8">Bekleyen geliştirme yok.</div>
            )}
            {dev.map((it) => (
              <IntegrationCard key={it.key} item={it} status="dev" />
            ))}
          </div>
        </div>
      </div>

      <div className="mt-6 p-3 bg-sky-50 border border-sky-200 rounded text-xs text-sky-900 flex items-start gap-2">
        <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
        <div>
          <strong>Otomatik geçiş:</strong> "API Bilgileri Gerekli" sütunundaki bir entegrasyona Anahtar Yönetimi'nden eksik
          değerleri girdiğinizde, sayfayı yenilediğinizde otomatik olarak "Hazır" sütununa düşer. Otele özel ayar gereken
          entegrasyonlar (Exely, HotelRunner, WhatsApp) burada hazır görünür — her otel kendi panelinden bağlar.
        </div>
      </div>
    </div>
  );
}
