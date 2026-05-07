import { useTranslation } from 'react-i18next';
import { useState, useEffect, useCallback, lazy, Suspense } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import { Shield, Lock, FileCheck, Users, Server, Eye, RefreshCw, Loader2 } from "lucide-react";
import Layout from "@/components/MaybeLayout";

const PIIStrictModeDashboard = lazy(() => import("@/pages/PIIStrictModeDashboard"));
const InfraHardeningDashboard = lazy(() => import("@/pages/InfraHardeningDashboard"));

const API = "";

function ScoreBadge({ score, label }) {
  const color = score >= 0.9 ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
    : score >= 0.7 ? "bg-amber-500/20 text-amber-400 border-amber-500/30"
    : "bg-red-500/20 text-red-400 border-red-500/30";
  return <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${color}`}>{label || `${(score * 100).toFixed(0)}%`}</span>;
}

function TabLoader() {
  return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="h-8 w-8 animate-spin text-gray-600" />
      <span className="ml-3 text-gray-600">Yükleniyor...</span>
    </div>
  );
}

export default function SecurityHardeningDashboard({ user, tenant, onLogout, embedded = false }) {
  const { t } = useTranslation();
  const [mainTab, setMainTab] = useState("security");
  const [secTab, setSecTab] = useState("isolation");
  const [isolation, setIsolation] = useState(null);
  const [permissions, setPermissions] = useState(null);
  const [vault, setVault] = useState(null);
  const [audit, setAudit] = useState(null);
  const [loading, setLoading] = useState(true);

  const token = localStorage.getItem("token") || sessionStorage.getItem("token");
  const headers = { Authorization: `Bearer ${token}` };

  const fetchData = useCallback(async () => {
    try {
      const [isoRes, permRes, vaultRes, auditRes] = await Promise.all([
        axios.get(`/security-hardening/tenant-scope/check`, { headers }),
        axios.get(`/security-hardening/property-permissions`, { headers }),
        axios.get(`/security-hardening/vault/status`, { headers }),
        axios.get(`/security-hardening/audit-completeness?hours=24`, { headers }),
      ]);
      setIsolation(isoRes.data);
      setPermissions(permRes.data);
      setVault(vaultRes.data);
      setAudit(auditRes.data);
    } catch (err) {
      console.error("Security data fetch failed:", err);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const isoScore = isolation?.isolation_score || 0;
  const auditScore = audit?.completeness_score || 0;
  const vaultHealth = vault?.vault_health || "unknown";
  const properties = permissions?.properties || {};

  return (
    <Layout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout} currentModule="security">
    <div data-testid="security-hardening-dashboard" className="space-y-6 p-6 bg-white min-h-screen">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Shield className="w-6 h-6 text-rose-500" />
            Güvenlik & Güçlendirme
          </h1>
          <p className="text-sm text-gray-600 mt-1">Tenant izolasyon, PII koruma ve altyapı güçlendirme</p>
        </div>
        {mainTab === "security" && (
          <Button data-testid="refresh-security-btn" onClick={fetchData} size="sm" className="bg-rose-600 hover:bg-rose-700 text-white">
            <RefreshCw className="w-4 h-4 mr-1" /> Yenile
          </Button>
        )}
      </div>

      {/* Main Tab Switch: Security | PII | Infrastructure */}
      <Tabs value={mainTab} onValueChange={setMainTab}>
        <TabsList className="bg-gray-50 border-gray-200 grid w-full grid-cols-3 max-w-xl" data-testid="main-tabs">
          <TabsTrigger value="security" data-testid="main-tab-security" className="data-[state=active]:bg-rose-600 flex items-center gap-2">
            <Lock className="w-4 h-4" /> Güvenlik
          </TabsTrigger>
          <TabsTrigger value="pii" data-testid="main-tab-pii" className="data-[state=active]:bg-rose-600 flex items-center gap-2">
            <Eye className="w-4 h-4" /> PII Koruma
          </TabsTrigger>
          <TabsTrigger value="infra" data-testid="main-tab-infra" className="data-[state=active]:bg-rose-600 flex items-center gap-2">
            <Server className="w-4 h-4" /> Altyapi
          </TabsTrigger>
        </TabsList>

        {/* SECURITY TAB */}
        <TabsContent value="security" className="space-y-6 mt-4">
          {loading ? (
            <TabLoader />
          ) : (
            <>
              {/* Top Summary Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Card data-testid="card-isolation" className="bg-white border-gray-200">
                  <CardContent className="p-4">
                    <p className="text-xs text-gray-600 uppercase tracking-wider">Tenant İzolasyon</p>
                    <div className="flex items-center gap-2 mt-2">
                      <p className="text-2xl font-bold text-white">{(isoScore * 100).toFixed(0)}%</p>
                      <ScoreBadge score={isoScore} />
                    </div>
                    <p className="text-xs text-gray-600 mt-1">{isolation?.clean_collections || 0}/{isolation?.collections_checked || 0} temiz</p>
                  </CardContent>
                </Card>
                <Card data-testid="card-audit" className="bg-white border-gray-200">
                  <CardContent className="p-4">
                    <p className="text-xs text-gray-600 uppercase tracking-wider">Audit Tamlığı</p>
                    <div className="flex items-center gap-2 mt-2">
                      <p className="text-2xl font-bold text-white">{(auditScore * 100).toFixed(0)}%</p>
                      <ScoreBadge score={auditScore} />
                    </div>
                    <p className="text-xs text-gray-600 mt-1">{audit?.total_audit_entries || 0} kayıt (24h)</p>
                  </CardContent>
                </Card>
                <Card data-testid="card-vault" className="bg-white border-gray-200">
                  <CardContent className="p-4">
                    <p className="text-xs text-gray-600 uppercase tracking-wider">Credential Vault</p>
                    <div className="flex items-center gap-2 mt-2">
                      <span className={`w-3 h-3 rounded-full ${vaultHealth === "healthy" ? "bg-emerald-500" : "bg-amber-500"}`} />
                      <p className="text-lg font-bold text-white capitalize">{vaultHealth.replace("_", " ")}</p>
                    </div>
                    <p className="text-xs text-gray-600 mt-1">{vault?.total_credentials || 0} credential | {vault?.rotation_overdue_count || 0} rotasyon bekliyor</p>
                  </CardContent>
                </Card>
                <Card data-testid="card-properties" className="bg-white border-gray-200">
                  <CardContent className="p-4">
                    <p className="text-xs text-gray-600 uppercase tracking-wider">Property RBAC</p>
                    <p className="text-2xl font-bold text-white mt-2">{Object.keys(properties).length}</p>
                    <p className="text-xs text-gray-600 mt-1">property gruplari</p>
                  </CardContent>
                </Card>
              </div>

              <Tabs value={secTab} onValueChange={setSecTab} className="space-y-4">
                <TabsList className="bg-gray-50 border-gray-200">
                  <TabsTrigger value="isolation" data-testid="tab-isolation" className="data-[state=active]:bg-rose-600">İzolasyon</TabsTrigger>
                  <TabsTrigger value="permissions" data-testid="tab-permissions" className="data-[state=active]:bg-rose-600">RBAC</TabsTrigger>
                  <TabsTrigger value="vault" data-testid="tab-vault" className="data-[state=active]:bg-rose-600">Vault</TabsTrigger>
                  <TabsTrigger value="audit" data-testid="tab-audit" className="data-[state=active]:bg-rose-600">Audit</TabsTrigger>
                </TabsList>

                <TabsContent value="isolation">
                  <Card className="bg-white border-gray-200">
                    <CardHeader><CardTitle className="text-white text-base">Tenant Veri İzolasyonu</CardTitle></CardHeader>
                    <CardContent>
                      <div className="space-y-2">
                        {(isolation?.details || []).map((d, i) => (
                          <div key={i} data-testid={`iso-collection-${i}`} className="flex items-center justify-between p-2.5 rounded-lg bg-gray-50 border border-gray-200">
                            <div>
                              <p className="text-sm text-white font-medium">{d.collection}</p>
                              <p className="text-xs text-gray-600">{d.tenant_documents} tenant doc | {d.unscoped_documents} unscoped</p>
                            </div>
                            <span className={`text-xs px-2 py-0.5 rounded-full ${d.isolation_status === "clean" ? "bg-emerald-500/20 text-emerald-400" : "bg-amber-500/20 text-amber-400"}`}>
                              {d.isolation_status}
                            </span>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                </TabsContent>

                <TabsContent value="permissions">
                  <Card className="bg-white border-gray-200">
                    <CardHeader><CardTitle className="text-white text-base">Property Bazli Izinler</CardTitle></CardHeader>
                    <CardContent>
                      {Object.keys(properties).length === 0 ? (
                        <p className="text-gray-600 text-sm">Kullanıcı bilgisi bulunamadı</p>
                      ) : (
                        <div className="space-y-3">
                          {Object.entries(properties).map(([pid, pdata]) => (
                            <div key={pid} data-testid={`property-${pid}`} className="p-3 rounded-lg bg-gray-50 border border-gray-200">
                              <div className="flex items-center justify-between mb-2">
                                <p className="text-sm font-medium text-white">Property: {pid}</p>
                                <Badge variant="outline" className="text-rose-400 border-rose-500/30">{pdata.user_count} kullanici</Badge>
                              </div>
                              <div className="flex flex-wrap gap-1">
                                {(pdata.roles || []).map((r) => (
                                  <Badge key={r} variant="outline" className="text-xs text-gray-700 border-gray-200">{r}</Badge>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </TabsContent>

                <TabsContent value="vault">
                  <Card className="bg-white border-gray-200">
                    <CardHeader><CardTitle className="text-white text-base">Credential Vault Durumu</CardTitle></CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-2 gap-4 mb-4">
                        <div className="p-3 rounded-lg bg-gray-50 border border-gray-200 text-center">
                          <p className="text-xs text-gray-600">Toplam Credential</p>
                          <p className="text-2xl font-bold text-white">{vault?.total_credentials || 0}</p>
                        </div>
                        <div className="p-3 rounded-lg bg-gray-50 border border-gray-200 text-center">
                          <p className="text-xs text-gray-600">Rotasyon Bekleyen</p>
                          <p className="text-2xl font-bold text-amber-400">{vault?.rotation_overdue_count || 0}</p>
                        </div>
                      </div>
                      {(vault?.needs_rotation || []).length > 0 && (
                        <div className="space-y-2">
                          <p className="text-sm text-amber-400 mb-2">Rotasyon Gereken Credentialler:</p>
                          {vault.needs_rotation.map((c, i) => (
                            <div key={i} className="flex items-center justify-between p-2 rounded bg-amber-900/20 border border-amber-700/30">
                              <span className="text-sm text-amber-300">{c.type}/{c.key}</span>
                              <span className="text-xs text-amber-500">{c.days_overdue} gün geçmiş</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </TabsContent>

                <TabsContent value="audit">
                  <Card className="bg-white border-gray-200">
                    <CardHeader><CardTitle className="text-white text-base">Audit Tamlığı (24 Saat)</CardTitle></CardHeader>
                    <CardContent>
                      <div className="space-y-3">
                        {(audit?.categories || []).map((cat, i) => (
                          <div key={i} data-testid={`audit-cat-${i}`} className="p-3 rounded-lg bg-gray-50 border border-gray-200">
                            <div className="flex items-center justify-between mb-2">
                              <p className="text-sm font-medium text-white capitalize">{cat.category}</p>
                              <ScoreBadge score={cat.coverage} label={`${(cat.coverage * 100).toFixed(0)}%`} />
                            </div>
                            {cat.missing_actions.length > 0 && (
                              <div className="flex flex-wrap gap-1">
                                {cat.missing_actions.map((a) => (
                                  <Badge key={a} variant="outline" className="text-xs text-red-400 border-red-500/30">{a}</Badge>
                                ))}
                              </div>
                            )}
                            {cat.missing_actions.length === 0 && (
                              <p className="text-xs text-emerald-400">Tüm aksiyonlar audit edilmiş</p>
                            )}
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                </TabsContent>
              </Tabs>
            </>
          )}
        </TabsContent>

        {/* PII TAB - Lazy loaded */}
        <TabsContent value="pii" className="mt-4">
          <Suspense fallback={<TabLoader />}>
            <PIIStrictModeDashboard user={user} tenant={tenant} onLogout={onLogout} embedded />
          </Suspense>
        </TabsContent>

        {/* INFRA TAB - Lazy loaded */}
        <TabsContent value="infra" className="mt-4">
          <Suspense fallback={<TabLoader />}>
            <InfraHardeningDashboard user={user} tenant={tenant} onLogout={onLogout} embedded />
          </Suspense>
        </TabsContent>
      </Tabs>
    </div>
    </Layout>
  );
}
