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
import { useTranslation } from 'react-i18next';

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

// Ekran sıralaması: TR ürün önceliğine göre stabil sıra (alfabetik
// localeCompare yerine açıkça tanımlı, böylece "ai" ile "Altyapı" yan yana
// gelmek gibi tutarsızlıklar olmaz).
const CATEGORY_ORDER = [
  "channel-manager",
  "ai",
  "messaging",
  "payment",
  "loyalty",
  "b2b",
  "identity",
  "monitoring",
  "infrastructure",
];

function categoryRank(cat) {
  const i = CATEGORY_ORDER.indexOf(cat);
  return i === -1 ? 999 : i;
}

function CategoryBadge({ category, label }) {
  const { t } = useTranslation();
  const tone = CATEGORY_TONE[category] || "bg-slate-50 text-slate-600 border-slate-200";
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium border ${tone}`}
      title={label}
    >
      {label}
    </span>
  );
}

function IntegrationCard({ item, status }) {
  const { t } = useTranslation();
  // status: "ready" | "needs" | "dev"
  const isReady = status === "ready";
  const isNeeds = status === "needs";
  const isDev = status === "dev";
  const firstEnv = (item.required_envs && item.required_envs.length > 0)
    ? item.required_envs[0]
    : null;

  return (
    <Card
      className={`p-4 flex flex-col gap-3 ${
        isDev ? "bg-slate-50/60 border-slate-200" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3
              className={`font-semibold text-sm leading-tight truncate ${
                isDev ? "text-slate-700" : "text-slate-900"
              }`}
            >
              {item.name}
            </h3>
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            <CategoryBadge category={item.category} label={item.category_label} />
            {item.per_tenant && (
              <span
                className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border bg-slate-100 text-slate-600 border-slate-300"
                title={t('cm.pages_admin_IntegrationsOverview.bu_entegrasyon_her_otelin_kendi_panelind')}
              >
                {t('cm.pages_admin_IntegrationsOverview.otel_basina')}
              </span>
            )}
          </div>
        </div>
        {isReady && (
          <CheckCircle2
            className="w-5 h-5 text-emerald-600 flex-shrink-0"
            aria-label={t('cm.pages_admin_IntegrationsOverview.hazir')}
          />
        )}
        {isNeeds && (
          <KeyRound
            className="w-5 h-5 text-amber-600 flex-shrink-0"
            aria-label={t('cm.pages_admin_IntegrationsOverview.api_anahtari_bekleniyor')}
          />
        )}
        {isDev && (
          <Wrench
            className="w-5 h-5 text-slate-500 flex-shrink-0"
            aria-label={t('cm.pages_admin_IntegrationsOverview.gelistirme_asamasinda')}
          />
        )}
      </div>

      <p className={`text-xs leading-relaxed ${isDev ? "text-slate-600" : "text-slate-600"}`}>
        {item.description}
      </p>

      {item.per_tenant && (
        <div className="flex items-start gap-1.5 text-[11px] text-slate-500 bg-slate-50 px-2 py-1.5 rounded">
          <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
          <span>{t('cm.pages_admin_IntegrationsOverview.otele_ozel_kimlik_bilgileri_her_otel_ken')}</span>
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
          <span className="text-[10px] font-mono text-slate-400" title={t('cm.pages_admin_IntegrationsOverview.otele_atama_icin_modul_anahtari')}>
            {t('cm.pages_admin_IntegrationsOverview.modul')} {item.module_key}
          </span>
        ) : <span />}
        <div className="flex items-center gap-1">
          {item.doc_url && (
            <a
              href={item.doc_url}
              target="_blank"
              rel="noreferrer"
              className="text-slate-400 hover:text-slate-700 p-1 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
              title={`Sağlayıcı dokümanı: ${item.name}`}
              aria-label={`${item.name} sağlayıcı dokümanını yeni sekmede aç`}
            >
              <ExternalLink className="w-3.5 h-3.5" aria-hidden="true" />
            </a>
          )}
          {isNeeds && firstEnv && (
            <Link
              to={`/admin/integration-credentials#${firstEnv}`}
              aria-label={`${item.name} için API anahtarlarını gir`}
            >
              <Button size="sm" variant="default" className="h-7 text-xs">
                {t('cm.pages_admin_IntegrationsOverview.anahtarlari_gir')}
                <ArrowRight className="w-3 h-3 ml-1" aria-hidden="true" />
              </Button>
            </Link>
          )}
          {isReady && !item.per_tenant && firstEnv && (
            <Link
              to={`/admin/integration-credentials#${firstEnv}`}
              aria-label={`${item.name} anahtarlarını yönet`}
            >
              <Button size="sm" variant="outline" className="h-7 text-xs">
                <Settings2 className="w-3 h-3 mr-1" aria-hidden="true" />
                {t('cm.pages_admin_IntegrationsOverview.yonet')}
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
  const { t } = useTranslation();
  const [data, setData] = useState({ ready: [], needs_credentials: [], in_development: [], totals: {} });
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await axios.get("/admin/integrations-overview");
      setData(resp.data);
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

  // Önce TR-öncelikli kategori sırası, sonra isim (TR locale).
  const sortByCategory = (a, b) => {
    const ra = categoryRank(a.category);
    const rb = categoryRank(b.category);
    if (ra !== rb) return ra - rb;
    return (a.name || "").localeCompare(b.name || "", "tr");
  };
  const ready = useMemo(() => [...(data.ready || [])].sort(sortByCategory), [data.ready]);
  const needs = useMemo(() => [...(data.needs_credentials || [])].sort(sortByCategory), [data.needs_credentials]);
  const dev = useMemo(() => [...(data.in_development || [])].sort(sortByCategory), [data.in_development]);

  return (
    <div className="p-4 lg:p-6 max-w-[1600px] mx-auto">
      <PageHeader
        icon={Plug}
        title={t('cm.pages_admin_IntegrationsOverview.entegrasyon_genel_bakis')}
        subtitle={t('cm.pages_admin_IntegrationsOverview.tum_3_parti_servislerin_kod_ve_api_anaht')}
        actions={
          <>
            <Link to="/admin/integration-credentials">
              <Button variant="outline" size="sm">
                <KeyRound className="w-4 h-4 mr-1.5" />
                {t('cm.pages_admin_IntegrationsOverview.anahtar_yonetimi')}
              </Button>
            </Link>
            <Button variant="outline" size="sm" onClick={load} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? "animate-spin" : ""}`} />
              {t('cm.pages_admin_IntegrationsOverview.yenile')}
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <KpiCard
          icon={ShieldCheck}
          label={t('cm.pages_admin_IntegrationsOverview.toplam_entegrasyon')}
          value={total}
          sub={`${readyPct}% kullanıma hazır`}
          intent="default"
        />
        <KpiCard
          icon={CheckCircle2}
          label={t('cm.pages_admin_IntegrationsOverview.hazir_3ae38')}
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
          label={t('cm.pages_admin_IntegrationsOverview.gelistirmede')}
          value={totals.in_development || 0}
          sub="Kod henüz tamamlanmadı"
          intent="neutral"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* HAZIR */}
        <div className="flex flex-col">
          <ColumnHeader icon={CheckCircle2} title={t('cm.pages_admin_IntegrationsOverview.hazir_3ae38')} count={ready.length} intent="success" />
          <div className="border border-t-0 border-emerald-200 rounded-b-md p-3 space-y-3 bg-white min-h-[200px]">
            {loading && <div className="text-xs text-slate-400">{t('cm.pages_admin_IntegrationsOverview.yukleniyor')}</div>}
            {!loading && ready.length === 0 && (
              <div className="text-xs text-slate-400 text-center py-8">{t('cm.pages_admin_IntegrationsOverview.henuz_hazir_entegrasyon_yok')}</div>
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
                {t('cm.pages_admin_IntegrationsOverview.tum_anahtarlar_tanimli')}
              </div>
            )}
            {needs.map((it) => (
              <IntegrationCard key={it.key} item={it} status="needs" />
            ))}
          </div>
        </div>

        {/* GELİŞTİRMEDE */}
        <div className="flex flex-col">
          <ColumnHeader icon={Wrench} title={t('cm.pages_admin_IntegrationsOverview.gelistirme_surecinde')} count={dev.length} intent="neutral" />
          <div className="border border-t-0 border-slate-200 rounded-b-md p-3 space-y-3 bg-slate-50/30 min-h-[200px]">
            {!loading && dev.length === 0 && (
              <div className="text-xs text-slate-400 text-center py-8">{t('cm.pages_admin_IntegrationsOverview.bekleyen_gelistirme_yok')}</div>
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
          <strong>{t('cm.pages_admin_IntegrationsOverview.otomatik_gecis')}</strong> {t('cm.pages_admin_IntegrationsOverview.api_bilgileri_gerekli_sutunundaki_bir_en')}
        </div>
      </div>
    </div>
  );
}
