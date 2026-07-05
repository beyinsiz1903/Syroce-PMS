import { useTranslation } from "react-i18next";
import { useState, useEffect, useCallback, lazy, Suspense } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import { Shield, Lock, Users, Server, Eye, RefreshCw, Loader2, KeyRound, ClipboardCheck, Database, AlertTriangle } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { KpiCard } from "@/components/ui/kpi-card";
import { StatusBadge } from "@/components/ui/status-badge";
const piiImport = () => import("@/pages/PIIStrictModeDashboard");
const infraImport = () => import("@/pages/InfraHardeningDashboard");
const PIIStrictModeDashboard = lazy(piiImport);
const InfraHardeningDashboard = lazy(infraImport);
function intentForScore(score) {
  if (score >= 0.9) return "success";
  if (score >= 0.7) return "warning";
  return "danger";
}
function ScoreBadge({
  score,
  label
}) {
  const intent = intentForScore(score);
  return <StatusBadge intent={intent}>{label || `${(score * 100).toFixed(0)}%`}</StatusBadge>;
}
function TabLoader({
  label
}) {
  return <div className="flex items-center justify-center h-64">
      <Loader2 className="h-8 w-8 animate-spin text-slate-500" />
      <span className="ml-3 text-slate-600">{label || "Yükleniyor..."}</span>
    </div>;
}
function PanelSkeleton() {
  return <div className="space-y-2 animate-pulse">
      {[0, 1, 2, 3].map(i => <div key={i} className="h-14 rounded-lg bg-slate-100" />)}
    </div>;
}
function ErrorBlock({
  message,
  onRetry
}) {
  return <div className="p-4 rounded-lg border border-rose-200 bg-rose-50 flex items-start gap-3">
      <AlertTriangle className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-rose-800">Veri yüklenemedi</p>
        <p className="text-xs text-rose-700 mt-0.5">{message || "Bilinmeyen hata."}</p>
      </div>
      {onRetry && <Button variant="outline" size="sm" onClick={onRetry} className="flex-shrink-0">
          <RefreshCw className="w-4 h-4 mr-1.5" />
          Yenile
        </Button>}
    </div>;
}
function EmptyState({
  message
}) {
  return <div className="text-center py-8 text-sm text-slate-500">{message}</div>;
}
const VAULT_INTENT = {
  healthy: "success",
  degraded: "warning",
  unhealthy: "danger",
  critical: "danger",
  unknown: "neutral"
};
const VAULT_LABEL = {
  healthy: "Sağlıklı",
  degraded: "Düşük",
  unhealthy: "Bozuk",
  critical: "Kritik",
  unknown: "Bilinmiyor"
};
function pluralizeUsers(n) {
  return n === 1 ? "1 kullanıcı" : `${n} kullanıcı`;
}
export default function SecurityHardeningDashboard({
  user,
  tenant,
  onLogout,
  embedded = false
}) {
  // i18n hook reserved for future migration; explicit Turkish copy used today.
  const { t, i18n } = useTranslation();
  const [mainTab, setMainTab] = useState("security");
  const [secTab, setSecTab] = useState("isolation");
  // Track which lazy tabs the user has visited so we can keep them mounted
  // (via forceMount + display toggle) on subsequent switches. Without this,
  // Radix Tabs unmounts inactive content → every re-visit pays the full cost
  // of remounting + refetching all data (PII fires 5 axios calls, Infra 1).
  const [visited, setVisited] = useState({
    security: true
  });
  const handleMainTab = next => {
    setMainTab(next);
    setVisited(v => v[next] ? v : {
      ...v,
      [next]: true
    });
  };
  // Prefetch the lazy JS chunk on hover so the bundle is already in cache
  // by the time the user actually clicks the tab.
  const prefetchPii = useCallback(() => {
    piiImport();
  }, []);
  const prefetchInfra = useCallback(() => {
    infraImport();
  }, []);
  const [isolation, setIsolation] = useState(null);
  const [permissions, setPermissions] = useState(null);
  const [vault, setVault] = useState(null);
  const [audit, setAudit] = useState(null);
  const [errors, setErrors] = useState({
    isolation: null,
    permissions: null,
    vault: null,
    audit: null
  });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const fetchData = useCallback(async ({
    silent = false
  } = {}) => {
    if (silent) setRefreshing(true);else setLoading(true);
    const endpoints = [["isolation", "/security-hardening/tenant-scope/check", setIsolation], ["permissions", "/security-hardening/property-permissions", setPermissions], ["vault", "/security-hardening/vault/status", setVault], ["audit", "/security-hardening/audit-completeness?hours=24", setAudit]];
    const results = await Promise.allSettled(endpoints.map(([, url]) => axios.get(url)));
    const nextErrors = {
      isolation: null,
      permissions: null,
      vault: null,
      audit: null
    };
    let failureCount = 0;
    results.forEach((res, idx) => {
      const [key,, setter] = endpoints[idx];
      if (res.status === "fulfilled") {
        setter(res.value.data);
      } else {
        failureCount += 1;
        const reason = res.reason;
        const status = reason?.response?.status;
        const detail = reason?.response?.data?.detail;
        nextErrors[key] = detail || (status ? `Sunucu ${status} döndü` : reason?.message) || "Bilinmeyen hata";
      }
    });
    setErrors(nextErrors);
    if (silent && failureCount > 0) {
      toast.error(failureCount === results.length ? "Tüm güvenlik verileri yüklenemedi." : `${failureCount} bölüm güncellenemedi.`);
    }
    setLoading(false);
    setRefreshing(false);
  }, []);
  useEffect(() => {
    fetchData();
  }, [fetchData]);
  const handleRefresh = () => {
    if (loading || refreshing) return;
    fetchData({
      silent: true
    });
  };
  const isoScore = isolation?.isolation_score ?? 0;
  const auditScore = audit?.completeness_score ?? 0;
  const vaultHealthRaw = typeof vault?.vault_health === "string" ? vault.vault_health : "unknown";
  const vaultHealthKey = vaultHealthRaw.toLowerCase();
  const vaultIntent = VAULT_INTENT[vaultHealthKey] || "neutral";
  const vaultLabel = VAULT_LABEL[vaultHealthKey] || vaultHealthRaw.replace(/_/g, " ");
  const properties = permissions?.properties || {};
  const rotationOverdue = vault?.rotation_overdue_count ?? 0;
  const refreshButton = <Button variant="outline" size="sm" onClick={handleRefresh} disabled={loading || refreshing} data-testid="refresh-security-btn">
      <RefreshCw className={`w-4 h-4 mr-1.5 ${refreshing ? "animate-spin" : ""}`} />
      Yenile
    </Button>;
  return <div data-testid="security-hardening-dashboard" className="space-y-5">
      <PageHeader icon={Shield} title="Güvenlik & Güçlendirme" subtitle="Tenant izolasyonu, PII koruma ve altyapı güçlendirme" actions={refreshButton} />

      {/* Main Tab Switch: Security | PII | Infrastructure */}
      <Tabs value={mainTab} onValueChange={handleMainTab}>
        <TabsList className="bg-slate-100 grid w-full grid-cols-3 max-w-xl" data-testid="main-tabs">
          <TabsTrigger value="security" data-testid="main-tab-security" className="flex items-center gap-2">
            <Lock className="w-4 h-4" /> Güvenlik
          </TabsTrigger>
          <TabsTrigger value="pii" data-testid="main-tab-pii" className="flex items-center gap-2" onMouseEnter={prefetchPii} onFocus={prefetchPii}>
            <Eye className="w-4 h-4" /> PII Koruma
          </TabsTrigger>
          <TabsTrigger value="infra" data-testid="main-tab-infra" className="flex items-center gap-2" onMouseEnter={prefetchInfra} onFocus={prefetchInfra}>
            <Server className="w-4 h-4" /> Altyapı
          </TabsTrigger>
        </TabsList>

        {/* SECURITY TAB */}
        <TabsContent value="security" className="space-y-5 mt-4">
          {/* Top Summary Cards — render skeleton ONLY for KPI row when initial load */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {loading && !isolation && !audit && !vault && !permissions ? <>
                {[0, 1, 2, 3].map(i => <div key={i} className="h-24 rounded-lg bg-slate-100 animate-pulse" />)}
              </> : <>
                <KpiCard data-testid="card-isolation" icon={Database} intent={errors.isolation ? "danger" : intentForScore(isoScore)} label="Tenant İzolasyonu" value={errors.isolation ? "—" : `${(isoScore * 100).toFixed(0)}%`} sub={errors.isolation ? "Veri alınamadı" : `${isolation?.clean_collections ?? 0}/${isolation?.collections_checked ?? 0} koleksiyon temiz`} />
                <KpiCard data-testid="card-audit" icon={ClipboardCheck} intent={errors.audit ? "danger" : intentForScore(auditScore)} label="Audit Tamlığı" value={errors.audit ? "—" : `${(auditScore * 100).toFixed(0)}%`} sub={errors.audit ? "Veri alınamadı" : `${audit?.total_audit_entries ?? 0} kayıt (24 saat)`} />
                <KpiCard data-testid="card-vault" icon={KeyRound} intent={errors.vault ? "danger" : vaultIntent} label="Credential Vault" value={errors.vault ? "—" : vaultLabel} sub={errors.vault ? "Veri alınamadı" : `${vault?.total_credentials ?? 0} credential · ${rotationOverdue} rotasyon bekliyor`} />
                <KpiCard data-testid="card-properties" icon={Users} intent={errors.permissions ? "danger" : "info"} label="Property RBAC" value={errors.permissions ? "—" : Object.keys(properties).length} sub={errors.permissions ? "Veri alınamadı" : "property grupları"} />
              </>}
          </div>

          <Tabs value={secTab} onValueChange={setSecTab} className="space-y-4">
            <TabsList className="bg-slate-100">
              <TabsTrigger value="isolation" data-testid="tab-isolation">
                İzolasyon
              </TabsTrigger>
              <TabsTrigger value="permissions" data-testid="tab-permissions">
                RBAC
              </TabsTrigger>
              <TabsTrigger value="vault" data-testid="tab-vault">
                Vault
              </TabsTrigger>
              <TabsTrigger value="audit" data-testid="tab-audit">
                Audit
              </TabsTrigger>
            </TabsList>

            <TabsContent value="isolation">
              <Card>
                <CardHeader>
                  <CardTitle className="text-slate-900 text-base">Tenant Veri İzolasyonu</CardTitle>
                </CardHeader>
                <CardContent>
                  {loading && !isolation ? <PanelSkeleton /> : errors.isolation ? <ErrorBlock message={errors.isolation} onRetry={handleRefresh} /> : (isolation?.details || []).length === 0 ? <EmptyState message="Hiç koleksiyon raporlanmadı." /> : <div className="space-y-2">
                      {(isolation?.details || []).map((d, i) => <div key={d.id || i} data-testid={`iso-collection-${i}`} className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 border border-slate-200">
                          <div>
                            <p className="text-sm text-slate-900 font-medium">{d.collection}</p>
                            <p className="text-xs text-slate-500">
                              {d.tenant_documents ?? 0} tenant doc · {d.unscoped_documents ?? 0} unscoped
                            </p>
                          </div>
                          <StatusBadge intent={d.isolation_status === "clean" ? "success" : "warning"}>
                            {d.isolation_status === "clean" ? "Temiz" : d.isolation_status || "kontrol edilmedi"}
                          </StatusBadge>
                        </div>)}
                    </div>}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="permissions">
              <Card>
                <CardHeader>
                  <CardTitle className="text-slate-900 text-base">Property Bazlı İzinler</CardTitle>
                </CardHeader>
                <CardContent>
                  {loading && !permissions ? <PanelSkeleton /> : errors.permissions ? <ErrorBlock message={errors.permissions} onRetry={handleRefresh} /> : Object.keys(properties).length === 0 ? <EmptyState message="Kullanıcı bilgisi bulunamadı." /> : <div className="space-y-3">
                      {Object.entries(properties).map(([pid, pdata]) => <div key={pid} data-testid={`property-${pid}`} className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                          <div className="flex items-center justify-between mb-2">
                            <p className="text-sm font-medium text-slate-900">Property: {pid}</p>
                            <StatusBadge intent="info">
                              {pluralizeUsers(pdata?.user_count ?? 0)}
                            </StatusBadge>
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {(pdata?.roles || []).map(r => <Badge key={r} variant="outline" className="text-xs text-slate-700 border-slate-300">
                                {r}
                              </Badge>)}
                          </div>
                        </div>)}
                    </div>}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="vault">
              <Card>
                <CardHeader>
                  <CardTitle className="text-slate-900 text-base">Credential Vault Durumu</CardTitle>
                </CardHeader>
                <CardContent>
                  {loading && !vault ? <PanelSkeleton /> : errors.vault ? <ErrorBlock message={errors.vault} onRetry={handleRefresh} /> : <>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
                        <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-center">
                          <p className="text-xs text-slate-500">Toplam Credential</p>
                          <p className="text-2xl font-bold text-slate-900">
                            {vault?.total_credentials ?? 0}
                          </p>
                        </div>
                        <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-center">
                          <p className="text-xs text-slate-500">Rotasyon Bekleyen</p>
                          <p className={`text-2xl font-bold ${rotationOverdue > 0 ? "text-amber-700" : "text-slate-900"}`}>
                            {rotationOverdue}
                          </p>
                        </div>
                      </div>
                      {(vault?.needs_rotation || []).length > 0 ? <div className="space-y-2">
                          <p className="text-sm font-medium text-amber-800 mb-2">
                            Rotasyon gereken credentialler:
                          </p>
                          {vault.needs_rotation.map((c, i) => <div key={c.id || i} className="flex items-center justify-between p-2 rounded bg-amber-50 border border-amber-200">
                              <span className="text-sm text-amber-900">
                                {c.type}/{c.key}
                              </span>
                              <StatusBadge intent="warning">
                                {c.days_overdue ?? 0} gün geçmiş
                              </StatusBadge>
                            </div>)}
                        </div> : <p className="text-sm text-emerald-700">Tüm credentialler güncel.</p>}
                    </>}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="audit">
              <Card>
                <CardHeader>
                  <CardTitle className="text-slate-900 text-base">Audit Tamlığı (24 Saat)</CardTitle>
                </CardHeader>
                <CardContent>
                  {loading && !audit ? <PanelSkeleton /> : errors.audit ? <ErrorBlock message={errors.audit} onRetry={handleRefresh} /> : (audit?.categories || []).length === 0 ? <EmptyState message="Bu pencerede audit kategorisi yok." /> : <div className="space-y-3">
                      {(audit?.categories || []).map((cat, i) => {
                    const missing = cat?.missing_actions ?? [];
                    const coverage = typeof cat?.coverage === "number" ? cat.coverage : 0;
                    return <div key={cat.id || i} data-testid={`audit-cat-${i}`} className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                            <div className="flex items-center justify-between mb-2">
                              <p className="text-sm font-medium text-slate-900 capitalize">
                                {cat?.category || "—"}
                              </p>
                              <ScoreBadge score={coverage} label={`${(coverage * 100).toFixed(0)}%`} />
                            </div>
                            {missing.length > 0 ? <div className="flex flex-wrap gap-1">
                                {missing.map(a => <StatusBadge key={a} intent="danger">
                                    {a}
                                  </StatusBadge>)}
                              </div> : <p className="text-xs text-emerald-700">
                                Tüm aksiyonlar audit edilmiş.
                              </p>}
                          </div>;
                  })}
                    </div>}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </TabsContent>

        {/* PII TAB - Lazy loaded, kept mounted after first visit */}
        <TabsContent value="pii" forceMount className={mainTab === "pii" ? "mt-4" : "mt-4 hidden"}>
          {visited.pii && <Suspense fallback={<TabLoader />}>
              <PIIStrictModeDashboard user={user} tenant={tenant} onLogout={onLogout} embedded />
            </Suspense>}
        </TabsContent>

        {/* INFRA TAB - Lazy loaded, kept mounted after first visit */}
        <TabsContent value="infra" forceMount className={mainTab === "infra" ? "mt-4" : "mt-4 hidden"}>
          {visited.infra && <Suspense fallback={<TabLoader />}>
              <InfraHardeningDashboard user={user} tenant={tenant} onLogout={onLogout} embedded />
            </Suspense>}
        </TabsContent>
      </Tabs>
    </div>;
}