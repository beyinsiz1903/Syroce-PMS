import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  Shield,
  ShieldAlert,
  ShieldCheck,
  Eye,
  EyeOff,
  Lock,
  Unlock,
  AlertTriangle,
  CheckCircle2,
  ArrowLeft,
  RefreshCw,
  Database,
  FileWarning,
  Clock,
  Users,
  Route,
} from "lucide-react";

const API = "";

function PIIStrictModeDashboard({ user, tenant, onLogout, embedded = false }) {
  const navigate = useNavigate();
  const [config, setConfig] = useState(null);
  const [summary, setSummary] = useState(null);
  const [violations, setViolations] = useState([]);
  const [encStatus, setEncStatus] = useState(null);
  const [policy, setPolicy] = useState(null);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(false);

  const token = localStorage.getItem("token") || sessionStorage.getItem("token");
  const headers = { Authorization: `Bearer ${token}` };

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [cfgRes, sumRes, violRes, encRes, polRes] = await Promise.allSettled([
        axios.get(`/security/pii-strict-mode/config`, { headers }),
        axios.get(`/security/pii-strict-mode/summary`, { headers }),
        axios.get(`/security/pii-strict-mode/violations?limit=20`, { headers }),
        axios.get(`/security/pii-strict-mode/encryption-status`, { headers }),
        axios.get(`/security/pii-strict-mode/policy`, { headers }),
      ]);
      if (cfgRes.status === "fulfilled") setConfig(cfgRes.value.data.config);
      if (sumRes.status === "fulfilled") setSummary(sumRes.value.data.summary);
      if (violRes.status === "fulfilled") setViolations(violRes.value.data.items || []);
      if (encRes.status === "fulfilled") setEncStatus(encRes.value.data.collections);
      if (polRes.status === "fulfilled") setPolicy(polRes.value.data.policy);
    } catch {
      toast.error("Veriler yuklenirken hata olustu");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleToggle = async (enabled) => {
    setToggling(true);
    try {
      const res = await axios.post(`/security/pii-strict-mode/toggle`, { enabled }, { headers });
      setConfig(res.data.config);
      toast.success(enabled ? "Strict Mode AKTIF edildi" : "Strict Mode DEVRE DIŞI bırakıldı");
      fetchAll();
    } catch {
      toast.error("Degisiklik kaydedilemedi");
    } finally {
      setToggling(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-slate-950">
        <RefreshCw className="w-8 h-8 text-emerald-400 animate-spin" />
      </div>
    );
  }

  const isEnabled = config?.enabled || false;

  const content = (
    <div className="space-y-8">
        {/* Strict Mode Toggle Card */}
        <Card className="bg-slate-900 border-slate-800">
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                {isEnabled ? (
                  <div className="w-14 h-14 rounded-xl bg-emerald-500/10 flex items-center justify-center">
                    <ShieldCheck className="w-7 h-7 text-emerald-400" />
                  </div>
                ) : (
                  <div className="w-14 h-14 rounded-xl bg-amber-500/10 flex items-center justify-center">
                    <ShieldAlert className="w-7 h-7 text-amber-400" />
                  </div>
                )}
                <div>
                  <h2 className="text-lg font-semibold">
                    Strict Mode: {isEnabled ? "AKTIF" : "DEVRE DISI"}
                  </h2>
                  <p className="text-sm text-slate-400 mt-1">
                    {isEnabled
                      ? "Tüm API yanıtlarinda PII alanlari otomatik olarak maskeleniyor."
                      : "PII maskeleme endpoint bazinda uygulaniyor. Global zorlama kapalı."}
                  </p>
                  {config?.updated_at && (
                    <p className="text-xs text-slate-500 mt-1">
                      Son güncelleme: {new Date(config.updated_at).toLocaleString("tr-TR")} — {config.updated_by}
                    </p>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm text-slate-400">{isEnabled ? "Aktif" : "Pasif"}</span>
                <Switch
                  data-testid="strict-mode-toggle"
                  checked={isEnabled}
                  disabled={toggling}
                  onCheckedChange={handleToggle}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Stats Row */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <StatCard
            icon={<FileWarning className="w-5 h-5 text-red-400" />}
            label="Ihlal (24s)"
            value={summary?.total_violations ?? 0}
            color={summary?.total_violations > 0 ? "red" : "emerald"}
          />
          <StatCard
            icon={<Route className="w-5 h-5 text-blue-400" />}
            label="Etkilenen Path"
            value={summary?.unique_paths ?? 0}
            color="blue"
          />
          <StatCard
            icon={<Users className="w-5 h-5 text-purple-400" />}
            label="Etkilenen Kullanici"
            value={summary?.unique_users ?? 0}
            color="purple"
          />
          <StatCard
            icon={<Lock className="w-5 h-5 text-emerald-400" />}
            label="Whitelist Yol"
            value={summary?.whitelisted_paths ?? 0}
            color="emerald"
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Encryption Coverage */}
          <Card className="bg-slate-900 border-slate-800">
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Database className="w-4 h-4 text-cyan-400" />
                Sifreleme Kapsami
              </CardTitle>
            </CardHeader>
            <CardContent>
              {encStatus ? (
                <div className="space-y-3">
                  {Object.entries(encStatus).map(([col, info]) => (
                    <div key={col} className="flex items-center justify-between py-2 border-b border-slate-800 last:border-0">
                      <div>
                        <span className="font-mono text-sm text-slate-200">{col}</span>
                        <p className="text-xs text-slate-500 mt-0.5">
                          {info.fields?.join(", ")}
                        </p>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="w-24 bg-slate-800 rounded-full h-2">
                          <div
                            className="h-2 rounded-full transition-all"
                            style={{
                              width: `${info.coverage_percent}%`,
                              backgroundColor: info.coverage_percent >= 80 ? "#10b981" : info.coverage_percent >= 40 ? "#f59e0b" : "#ef4444",
                            }}
                          />
                        </div>
                        <span className="text-xs font-mono w-12 text-right text-slate-300">
                          %{info.coverage_percent}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-500">Veri yok</p>
              )}
            </CardContent>
          </Card>

          {/* PII Policy */}
          <Card className="bg-slate-900 border-slate-800">
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Eye className="w-4 h-4 text-amber-400" />
                PII Politikasi
              </CardTitle>
            </CardHeader>
            <CardContent>
              {policy ? (
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-slate-400">Toplam PII Alan</span>
                    <Badge variant="outline" className="text-slate-200">{policy.total_pii_fields}</Badge>
                  </div>
                  {Object.entries(policy.categories || {}).map(([cat, fields]) => (
                    <div key={cat} className="py-2 border-b border-slate-800 last:border-0">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-slate-200 capitalize">{cat}</span>
                        <Badge variant="secondary" className="text-xs">{fields.length} alan</Badge>
                      </div>
                      <p className="text-xs text-slate-500 mt-1">
                        {fields.map(f => f.field).join(", ")}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-500">Veri yok</p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Whitelisted Paths */}
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Unlock className="w-4 h-4 text-slate-400" />
              Muaf Tutulan Yollar (Whitelist)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {(config?.whitelisted_paths || []).map((p, i) => (
                <Badge key={i} variant="outline" className="font-mono text-xs text-slate-300 bg-slate-800/50">
                  {p}
                </Badge>
              ))}
              {(!config?.whitelisted_paths || config.whitelisted_paths.length === 0) && (
                <p className="text-sm text-slate-500">Whitelist bos</p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Recent Violations */}
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red-400" />
              Son Olaylar
            </CardTitle>
          </CardHeader>
          <CardContent>
            {violations.length > 0 ? (
              <div className="space-y-2 max-h-80 overflow-y-auto">
                {violations.map((v, i) => (
                  <div key={i} className="flex items-center justify-between py-2 px-3 rounded-lg bg-slate-800/40 text-sm">
                    <div className="flex items-center gap-3">
                      {v.event_type === "pii_violation" ? (
                        <EyeOff className="w-4 h-4 text-red-400 shrink-0" />
                      ) : (
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                      )}
                      <div>
                        <span className="text-slate-200">{v.event_type === "strict_mode_toggled" ? (v.enabled ? "Strict Mode AKTIF" : "Strict Mode DEVRE DISI") : v.path}</span>
                        {v.pii_fields_found?.length > 0 && (
                          <p className="text-xs text-slate-500">{v.pii_fields_found.join(", ")}</p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-slate-500">
                      {v.user_role && <Badge variant="outline" className="text-xs">{v.user_role}</Badge>}
                      <Clock className="w-3 h-3" />
                      {v.timestamp ? new Date(v.timestamp).toLocaleString("tr-TR") : "-"}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8">
                <CheckCircle2 className="w-10 h-10 text-emerald-400 mx-auto mb-3" />
                <p className="text-sm text-slate-400">Son 24 saatte ihlal yok</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Top PII Fields in Violations */}
        {summary?.top_fields?.length > 0 && (
          <Card className="bg-slate-900 border-slate-800">
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-amber-400" />
                En Sik Tetiklenen PII Alanlari
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                {summary.top_fields.map(([field, count], i) => (
                  <div key={i} className="bg-slate-800/50 rounded-lg p-3 text-center">
                    <p className="font-mono text-sm text-slate-200">{field}</p>
                    <p className="text-2xl font-bold text-amber-400 mt-1">{count}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
  );

  if (embedded) return <div data-testid="pii-strict-mode-dashboard" className="text-slate-100">{content}</div>;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100" data-testid="pii-strict-mode-dashboard">
      <div className="border-b border-slate-800 bg-slate-950/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" onClick={() => navigate("/app/dashboard")} data-testid="back-btn">
              <ArrowLeft className="w-4 h-4 mr-1" /> Geri
            </Button>
            <div className="flex items-center gap-3">
              <Shield className="w-6 h-6 text-emerald-400" />
              <h1 className="text-xl font-semibold">PII Strict Mode</h1>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <Button variant="outline" size="sm" onClick={fetchAll} data-testid="refresh-btn">
              <RefreshCw className="w-4 h-4 mr-1" /> Yenile
            </Button>
            <span className="text-sm text-slate-400">{user?.email}</span>
          </div>
        </div>
      </div>
      <div className="max-w-7xl mx-auto px-6 py-8">
        {content}
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, color }) {
  const colorMap = {
    red: "text-red-400",
    emerald: "text-emerald-400",
    blue: "text-blue-400",
    purple: "text-purple-400",
    amber: "text-amber-400",
  };
  return (
    <Card className="bg-slate-900 border-slate-800">
      <CardContent className="p-4 flex items-center gap-4">
        <div className="w-10 h-10 rounded-lg bg-slate-800 flex items-center justify-center shrink-0">
          {icon}
        </div>
        <div>
          <p className="text-xs text-slate-400">{label}</p>
          <p className={`text-2xl font-bold ${colorMap[color] || "text-slate-100"}`}>{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}

export default PIIStrictModeDashboard;
