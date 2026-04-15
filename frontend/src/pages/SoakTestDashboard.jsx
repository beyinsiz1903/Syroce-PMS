import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Activity, Play, Square, RefreshCw, AlertTriangle,
  CheckCircle2, XCircle, Clock, Server, Database,
  Gauge, TrendingUp, Zap, Shield
} from "lucide-react";

const API = "";

function MetricCard({ label, value, unit, icon: Icon, status }) {
  const statusColors = {
    good: "border-emerald-500/30 bg-emerald-950/20",
    warn: "border-amber-500/30 bg-amber-950/20",
    bad: "border-red-500/30 bg-red-950/20",
    neutral: "border-slate-600/30 bg-slate-900/30",
  };
  const iconColors = {
    good: "text-emerald-400",
    warn: "text-amber-400",
    bad: "text-red-400",
    neutral: "text-slate-400",
  };
  return (
    <div data-testid={`metric-${label.toLowerCase().replace(/\s+/g, '-')}`}
      className={`rounded-lg border p-4 ${statusColors[status || "neutral"]}`}>
      <div className="flex items-center gap-2 mb-2">
        <Icon size={16} className={iconColors[status || "neutral"]} />
        <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">{label}</span>
      </div>
      <div className="text-2xl font-bold text-white">
        {value}<span className="text-sm font-normal text-slate-500 ml-1">{unit}</span>
      </div>
    </div>
  );
}

function IssueItem({ issue }) {
  const sevColors = {
    HIGH: "bg-red-500/20 text-red-300 border-red-500/30",
    MEDIUM: "bg-amber-500/20 text-amber-300 border-amber-500/30",
    LOW: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  };
  return (
    <div data-testid={`issue-${issue.type}`}
      className={`rounded border p-3 ${sevColors[issue.severity] || sevColors.LOW}`}>
      <div className="flex items-center gap-2 mb-1">
        <AlertTriangle size={14} />
        <span className="text-xs font-bold uppercase">{issue.severity}</span>
        <span className="text-xs opacity-70">{issue.type}</span>
      </div>
      <p className="text-sm">{issue.detail}</p>
    </div>
  );
}

function EndpointProbeRow({ probe }) {
  return (
    <tr className="border-b border-slate-800/50">
      <td className="py-2 px-3 text-sm font-mono text-slate-300">{probe.endpoint}</td>
      <td className="py-2 px-3 text-center">
        {probe.ok ? (
          <CheckCircle2 size={14} className="text-emerald-400 inline" />
        ) : (
          <XCircle size={14} className="text-red-400 inline" />
        )}
      </td>
      <td className="py-2 px-3 text-right text-sm text-slate-400">{probe.latency_ms?.toFixed(0)}ms</td>
      <td className="py-2 px-3 text-center text-sm text-slate-500">{probe.status}</td>
    </tr>
  );
}

function SnapshotChart({ snapshots }) {
  if (!snapshots || snapshots.length < 2) return null;
  const recent = snapshots.slice(-30);
  const maxMem = Math.max(...recent.map(s => s.backend_memory_mb || 0), 1);
  const maxLat = Math.max(...recent.flatMap(s =>
    (s.endpoint_probes || []).filter(p => p.ok).map(p => p.latency_ms)
  ), 1);

  return (
    <div data-testid="snapshot-chart" className="space-y-4">
      <div>
        <h4 className="text-xs font-medium text-slate-500 uppercase mb-2">Bellek Kullanimi (MB)</h4>
        <div className="flex items-end gap-1 h-16">
          {recent.map((s, i) => {
            const h = Math.max((s.backend_memory_mb / maxMem) * 100, 4);
            return (
              <div key={i} className="flex-1 bg-cyan-500/40 rounded-t transition-all"
                style={{ height: `${h}%` }}
                title={`${s.backend_memory_mb?.toFixed(0)}MB @ ${s.timestamp?.slice(11, 19)}`} />
            );
          })}
        </div>
      </div>
      <div>
        <h4 className="text-xs font-medium text-slate-500 uppercase mb-2">Ortalama Gecikme (ms)</h4>
        <div className="flex items-end gap-1 h-16">
          {recent.map((s, i) => {
            const probes = (s.endpoint_probes || []).filter(p => p.ok);
            const avg = probes.length > 0 ? probes.reduce((a, p) => a + p.latency_ms, 0) / probes.length : 0;
            const h = Math.max((avg / maxLat) * 100, 4);
            return (
              <div key={i} className="flex-1 bg-violet-500/40 rounded-t transition-all"
                style={{ height: `${h}%` }}
                title={`${avg.toFixed(0)}ms @ ${s.timestamp?.slice(11, 19)}`} />
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default function SoakTestDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [duration, setDuration] = useState("15m");
  const [users, setUsers] = useState(20);

  const token = localStorage.getItem("token");
  const headers = { Authorization: `Bearer ${token}` };

  const fetchStatus = useCallback(async () => {
    try {
      const res = await axios.get(`/production/soak-test/status`, { headers });
      setData(res.data);
    } catch (e) {
      console.error("Soak test status fetch error:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 15000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const startTest = async () => {
    setStarting(true);
    try {
      await axios.post(
        `/production/soak-test/start?duration=${duration}&users=${users}`,
        {}, { headers }
      );
      toast.success(`Soak test baslatildi: ${users} kullanici, ${duration}`);
      setTimeout(fetchStatus, 3000);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Test baslatma hatasi");
    } finally {
      setStarting(false);
    }
  };

  const stopTest = async () => {
    setStopping(true);
    try {
      await axios.post(`/production/soak-test/stop`, {}, { headers });
      toast.success("Soak test durduruldu");
      setTimeout(fetchStatus, 2000);
    } catch (e) {
      toast.error("Test durdurma hatasi");
    } finally {
      setStopping(false);
    }
  };

  const fr = data?.final_report;
  const sm = data?.system_metrics;
  const latestSnap = sm?.latest_snapshot;
  const analysis = sm?.analysis;
  const isRunning = data?.soak_running;

  const getVerdictStatus = (v) => v === "PASS" ? "good" : v === "FAIL" ? "bad" : "neutral";

  return (
    <div data-testid="soak-test-dashboard" className="min-h-screen bg-[#0a0e1a] text-white p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-3">
              <Activity className="text-cyan-400" size={28} />
              Staging Soak Test
            </h1>
            <p className="text-slate-500 text-sm mt-1">
              Uzun sureli yuk altinda sistem dayaniklilik testi
            </p>
          </div>
          <div className="flex items-center gap-3">
            {isRunning && (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/20 border border-emerald-500/30">
                <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-xs font-medium text-emerald-300">Test Calisiyor</span>
              </div>
            )}
            <button data-testid="refresh-btn" onClick={fetchStatus}
              className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 transition">
              <RefreshCw size={16} className="text-slate-400" />
            </button>
          </div>
        </div>

        {/* Controls */}
        <div data-testid="soak-controls" className="rounded-xl border border-slate-700/50 bg-slate-900/50 p-5">
          <h2 className="text-sm font-semibold text-slate-300 mb-4 flex items-center gap-2">
            <Zap size={16} className="text-amber-400" /> Test Kontrolleri
          </h2>
          <div className="flex flex-wrap items-end gap-4">
            <div>
              <label className="text-xs text-slate-500 block mb-1">Sure</label>
              <select data-testid="duration-select" value={duration} onChange={e => setDuration(e.target.value)}
                className="bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-white"
                disabled={isRunning}>
                <option value="5m">5 dakika (hizli)</option>
                <option value="15m">15 dakika</option>
                <option value="30m">30 dakika</option>
                <option value="1h">1 saat</option>
                <option value="6h">6 saat</option>
                <option value="12h">12 saat</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-500 block mb-1">Kullanici</label>
              <select data-testid="users-select" value={users} onChange={e => setUsers(Number(e.target.value))}
                className="bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-white"
                disabled={isRunning}>
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={30}>30</option>
                <option value={50}>50</option>
              </select>
            </div>
            {!isRunning ? (
              <button data-testid="start-soak-btn" onClick={startTest} disabled={starting}
                className="flex items-center gap-2 px-5 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-lg text-sm font-medium transition disabled:opacity-50">
                <Play size={14} /> {starting ? "Baslatiliyor..." : "Testi Baslat"}
              </button>
            ) : (
              <button data-testid="stop-soak-btn" onClick={stopTest} disabled={stopping}
                className="flex items-center gap-2 px-5 py-2 bg-red-600 hover:bg-red-500 rounded-lg text-sm font-medium transition disabled:opacity-50">
                <Square size={14} /> {stopping ? "Durduruluyor..." : "Testi Durdur"}
              </button>
            )}
          </div>
        </div>

        {/* Final Report Metrics */}
        {fr && (
          <div data-testid="final-report-section">
            <h2 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
              <Gauge size={16} className="text-cyan-400" /> Test Sonuclari
              <span className={`ml-2 px-2 py-0.5 rounded text-xs font-bold ${
                fr.verdict === "PASS" ? "bg-emerald-500/20 text-emerald-300" : "bg-red-500/20 text-red-300"
              }`}>{fr.verdict}</span>
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
              <MetricCard label="Sure" value={fr.duration_minutes?.toFixed(1)} unit="dk" icon={Clock}
                status="neutral" />
              <MetricCard label="Toplam Istek" value={fr.total_requests?.toLocaleString()} unit="" icon={Activity}
                status="neutral" />
              <MetricCard label="Hata Orani" value={fr.error_rate_pct?.toFixed(2)} unit="%"
                icon={AlertTriangle}
                status={fr.error_rate_pct <= 2 ? "good" : fr.error_rate_pct <= 5 ? "warn" : "bad"} />
              <MetricCard label="p50 Gecikme" value={fr.latency_p50?.toFixed(0)} unit="ms" icon={Gauge}
                status={fr.latency_p50 < 500 ? "good" : fr.latency_p50 < 2000 ? "warn" : "bad"} />
              <MetricCard label="p95 Gecikme" value={fr.latency_p95?.toFixed(0)} unit="ms" icon={TrendingUp}
                status={fr.latency_p95 < 3000 ? "good" : "bad"} />
              <MetricCard label="Bellek" value={fr.memory_rss_mb?.toFixed(0)} unit="MB" icon={Server}
                status={fr.memory_rss_mb < 500 ? "good" : fr.memory_rss_mb < 1000 ? "warn" : "bad"} />
            </div>
          </div>
        )}

        {/* Issues */}
        {fr?.issues?.length > 0 && (
          <div data-testid="issues-section" className="rounded-xl border border-red-500/20 bg-red-950/10 p-5">
            <h3 className="text-sm font-semibold text-red-300 mb-3 flex items-center gap-2">
              <AlertTriangle size={16} /> Tespit Edilen Sorunlar ({fr.issues.length})
            </h3>
            <div className="space-y-2">
              {fr.issues.map((issue, i) => <IssueItem key={i} issue={issue} />)}
            </div>
          </div>
        )}

        {/* System Monitor */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Live Probes */}
          {latestSnap && (
            <div data-testid="live-probes-section" className="rounded-xl border border-slate-700/50 bg-slate-900/50 p-5">
              <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
                <Shield size={16} className="text-violet-400" /> Son Endpoint Probelari
              </h3>
              <div className="grid grid-cols-2 gap-3 mb-4">
                <MetricCard label="Backend Bellek" value={latestSnap.backend_memory_mb?.toFixed(0)}
                  unit="MB" icon={Server}
                  status={latestSnap.backend_memory_mb < 300 ? "good" : "warn"} />
                <MetricCard label="MongoDB Bellek" value={latestSnap.mongo_memory_mb?.toFixed(0)}
                  unit="MB" icon={Database}
                  status={latestSnap.mongo_memory_mb < 500 ? "good" : "warn"} />
              </div>
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="py-2 px-3 text-xs font-medium text-slate-500">Endpoint</th>
                    <th className="py-2 px-3 text-xs font-medium text-slate-500 text-center">Durum</th>
                    <th className="py-2 px-3 text-xs font-medium text-slate-500 text-right">Gecikme</th>
                    <th className="py-2 px-3 text-xs font-medium text-slate-500 text-center">Kod</th>
                  </tr>
                </thead>
                <tbody>
                  {latestSnap.endpoint_probes?.map((p, i) => <EndpointProbeRow key={i} probe={p} />)}
                </tbody>
              </table>
            </div>
          )}

          {/* Trend Charts */}
          {sm?.snapshots && (
            <div data-testid="trend-section" className="rounded-xl border border-slate-700/50 bg-slate-900/50 p-5">
              <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
                <TrendingUp size={16} className="text-cyan-400" /> Zaman Serisi Trendleri
              </h3>
              <SnapshotChart snapshots={sm.snapshots} />
              {analysis && (
                <div className="mt-4 pt-4 border-t border-slate-800">
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                      analysis.status === "PASS" ? "bg-emerald-500/20 text-emerald-300" :
                      analysis.status === "FAIL" ? "bg-red-500/20 text-red-300" :
                      "bg-slate-700 text-slate-400"
                    }`}>{analysis.status}</span>
                    <span className="text-xs text-slate-500">Sistem Analizi</span>
                  </div>
                  {analysis.issues?.length > 0 ? (
                    <div className="space-y-1">
                      {analysis.issues.map((iss, i) => (
                        <p key={i} className="text-xs text-amber-300">{iss.detail}</p>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-emerald-400">Anomali tespit edilmedi</p>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Locust Stats Table */}
        {data?.locust_stats?.length > 0 && (
          <div data-testid="locust-stats-section" className="rounded-xl border border-slate-700/50 bg-slate-900/50 p-5">
            <h3 className="text-sm font-semibold text-slate-300 mb-3">Locust Endpoint Istatistikleri</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="py-2 px-3 text-xs text-slate-500">Endpoint</th>
                    <th className="py-2 px-3 text-xs text-slate-500 text-right">Istek</th>
                    <th className="py-2 px-3 text-xs text-slate-500 text-right">Hata</th>
                    <th className="py-2 px-3 text-xs text-slate-500 text-right">Ort(ms)</th>
                    <th className="py-2 px-3 text-xs text-slate-500 text-right">p95(ms)</th>
                  </tr>
                </thead>
                <tbody>
                  {data.locust_stats.map((s, i) => (
                    <tr key={i} className="border-b border-slate-800/50">
                      <td className="py-1.5 px-3 font-mono text-xs text-slate-300">{s.Name}</td>
                      <td className="py-1.5 px-3 text-right text-slate-400">{s['Request Count']}</td>
                      <td className="py-1.5 px-3 text-right text-red-400">{s['Failure Count']}</td>
                      <td className="py-1.5 px-3 text-right text-slate-400">{parseFloat(s['Average Response Time'] || 0).toFixed(0)}</td>
                      <td className="py-1.5 px-3 text-right text-slate-400">{parseFloat(s['95%'] || 0).toFixed(0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Scenarios Tested */}
        {fr?.scenarios_tested && (
          <div data-testid="scenarios-section" className="rounded-xl border border-slate-700/50 bg-slate-900/50 p-5">
            <h3 className="text-sm font-semibold text-slate-300 mb-3">Test Edilen Senaryolar</h3>
            <div className="flex flex-wrap gap-2">
              {fr.scenarios_tested.map((s, i) => (
                <span key={i} className="px-3 py-1 rounded-full bg-slate-800 text-xs text-slate-300 border border-slate-700">
                  {s.replace(/_/g, " ")}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* No Data State */}
        {!loading && !fr && !sm && !isRunning && (
          <div data-testid="no-data-state" className="text-center py-16 text-slate-500">
            <Activity size={48} className="mx-auto mb-4 opacity-30" />
            <p className="text-lg">Henüz soak test sonucu yok</p>
            <p className="text-sm mt-1">Yukaridaki kontrollerden bir test baslatin</p>
          </div>
        )}
      </div>
    </div>
  );
}
