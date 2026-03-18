import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import Layout from "@/components/Layout";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  Moon, Play, Clock, CheckCircle2, XCircle, AlertTriangle,
  RefreshCw, Calendar, FileText, ChevronDown, ChevronUp,
  DollarSign, Users, Building2, BarChart3, Eye, Loader2,
  Shield, Info
} from "lucide-react";
import { toast } from "sonner";

const statusConfig = {
  completed: { label: "Tamamlandi", color: "bg-emerald-100 text-emerald-700 border-emerald-200", icon: CheckCircle2 },
  completed_with_exceptions: { label: "Istisnali Tamamlandi", color: "bg-amber-100 text-amber-700 border-amber-200", icon: AlertTriangle },
  running: { label: "Calisiyor", color: "bg-blue-100 text-blue-700 border-blue-200", icon: Loader2 },
  failed: { label: "Basarisiz", color: "bg-red-100 text-red-700 border-red-200", icon: XCircle },
  pending: { label: "Bekliyor", color: "bg-gray-100 text-gray-600 border-gray-200", icon: Clock },
};

const severityConfig = {
  info: { label: "Bilgi", color: "bg-blue-50 text-blue-700 border-blue-200" },
  warning: { label: "Uyari", color: "bg-amber-50 text-amber-700 border-amber-200" },
  error: { label: "Hata", color: "bg-red-50 text-red-700 border-red-200" },
  critical: { label: "Kritik", color: "bg-red-100 text-red-800 border-red-300" },
};

const StatusBadge = ({ status }) => {
  const cfg = statusConfig[status] || statusConfig.pending;
  const Icon = cfg.icon;
  return (
    <Badge data-testid={`status-badge-${status}`} className={`${cfg.color} border gap-1 font-medium`}>
      <Icon className={`w-3 h-3 ${status === "running" ? "animate-spin" : ""}`} />
      {cfg.label}
    </Badge>
  );
};

const SeverityBadge = ({ severity }) => {
  const cfg = severityConfig[severity] || severityConfig.info;
  return (
    <Badge className={`${cfg.color} border text-[11px]`}>{cfg.label}</Badge>
  );
};

const StatCard = ({ icon: Icon, label, value, subValue, color = "text-gray-600" }) => (
  <div className="bg-white border rounded-xl p-4 flex items-start gap-3">
    <div className={`rounded-lg p-2 ${color.replace("text-", "bg-").replace("-600", "-100")}`}>
      <Icon className={`w-5 h-5 ${color}`} />
    </div>
    <div className="min-w-0">
      <p className="text-2xl font-bold text-gray-900 leading-tight">{value}</p>
      <p className="text-xs text-gray-500 mt-0.5">{label}</p>
      {subValue && <p className="text-[11px] text-gray-400 mt-0.5">{subValue}</p>}
    </div>
  </div>
);

const NightAuditDashboard = ({ user, tenant, onLogout }) => {
  const [businessDate, setBusinessDate] = useState(null);
  const [previousDate, setPreviousDate] = useState(null);
  const [history, setHistory] = useState([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [expandedRun, setExpandedRun] = useState(null);
  const [exceptions, setExceptions] = useState({});
  const [showRunDialog, setShowRunDialog] = useState(false);
  const [runOptions, setRunOptions] = useState({
    force_rerun: false,
    skip_validations: false,
    dry_run: false,
    reason: "",
  });

  const fetchBusinessDate = useCallback(async () => {
    try {
      const res = await axios.get("/night-audit/business-date");
      setBusinessDate(res.data.business_date);
      setPreviousDate(res.data.previous_business_date);
    } catch (err) {
      console.error("Business date fetch failed:", err);
    }
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      const res = await axios.get("/night-audit/history", { params: { limit: 20, skip: 0 } });
      setHistory(res.data.runs || []);
      setHistoryTotal(res.data.total || 0);
    } catch (err) {
      console.error("History fetch failed:", err);
    }
  }, []);

  const fetchExceptions = useCallback(async (auditId) => {
    if (exceptions[auditId]) return;
    try {
      const res = await axios.get(`/night-audit/exceptions/${auditId}`);
      setExceptions((prev) => ({ ...prev, [auditId]: res.data.exceptions || [] }));
    } catch (err) {
      console.error("Exceptions fetch failed:", err);
    }
  }, [exceptions]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([fetchBusinessDate(), fetchHistory()]);
    setLoading(false);
  }, [fetchBusinessDate, fetchHistory]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const handleRunAudit = async () => {
    setRunning(true);
    try {
      const payload = {
        business_date: businessDate,
        force_rerun: runOptions.force_rerun,
        skip_validations: runOptions.skip_validations,
        dry_run: runOptions.dry_run,
        reason: runOptions.reason || null,
      };
      const res = await axios.post("/night-audit/run", payload);
      const result = res.data;
      toast.success(
        runOptions.dry_run
          ? `Simuelasyon tamamlandi: ${result.rooms_processed} oda islendi`
          : `Gece denetimi tamamlandi: ${result.charges_posted} masraf kaydedildi`
      );
      setShowRunDialog(false);
      setRunOptions({ force_rerun: false, skip_validations: false, dry_run: false, reason: "" });
      await loadAll();
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (typeof detail === "object" && detail?.message) {
        toast.error(detail.message);
      } else if (typeof detail === "string") {
        toast.error(detail);
      } else {
        toast.error("Gece denetimi basarisiz oldu");
      }
    } finally {
      setRunning(false);
    }
  };

  const toggleExpand = async (auditId) => {
    if (expandedRun === auditId) {
      setExpandedRun(null);
    } else {
      setExpandedRun(auditId);
      await fetchExceptions(auditId);
    }
  };

  const lastRun = history.length > 0 ? history[0] : null;
  const todayCompleted = lastRun?.business_date === businessDate && lastRun?.status?.startsWith("completed");

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="night_audit">
      <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-5">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div>
            <h1 data-testid="night-audit-title" className="text-xl md:text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Moon className="w-6 h-6 text-indigo-600" />
              Gece Denetimi (Night Audit)
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Gun sonu islemleri: oda masrafi kaydi, no-show isleme, folio bakiye kontrolu
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              data-testid="refresh-btn"
              variant="outline"
              size="sm"
              onClick={loadAll}
              disabled={loading}
            >
              <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} />
              Yenile
            </Button>
            <Button
              data-testid="run-audit-btn"
              size="sm"
              onClick={() => setShowRunDialog(true)}
              disabled={running}
              className="bg-indigo-600 hover:bg-indigo-700 text-white"
            >
              <Play className="w-4 h-4 mr-1" />
              Denetim Baslat
            </Button>
          </div>
        </div>

        {/* Business Date & Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard
            icon={Calendar}
            label="Is Gunu (Business Date)"
            value={businessDate || "-"}
            subValue={previousDate ? `Onceki: ${previousDate}` : undefined}
            color="text-indigo-600"
          />
          <StatCard
            icon={BarChart3}
            label="Toplam Denetim"
            value={historyTotal}
            subValue={todayCompleted ? "Bugun tamamlandi" : "Bugun bekliyor"}
            color="text-emerald-600"
          />
          <StatCard
            icon={DollarSign}
            label="Son Oda Geliri"
            value={lastRun ? `${lastRun.total_room_revenue?.toFixed(2) || "0.00"} TL` : "-"}
            subValue={lastRun ? `Vergi: ${lastRun.total_tax_amount?.toFixed(2) || "0.00"} TL` : undefined}
            color="text-blue-600"
          />
          <StatCard
            icon={Users}
            label="Son No-Show"
            value={lastRun?.no_shows_processed ?? "-"}
            subValue={lastRun ? `${lastRun.rooms_processed || 0} oda islendi` : undefined}
            color="text-amber-600"
          />
        </div>

        {/* Latest Run Summary */}
        {lastRun && (
          <Card data-testid="last-run-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <FileText className="w-4 h-4 text-gray-500" />
                Son Denetim Ozeti
                <StatusBadge status={lastRun.status} />
                {lastRun.is_dry_run && (
                  <Badge className="bg-purple-100 text-purple-700 border-purple-200 border text-[11px]">
                    Simuelasyon
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 text-sm">
                <div>
                  <span className="text-gray-500 text-xs">Is Gunu</span>
                  <p className="font-semibold">{lastRun.business_date}</p>
                </div>
                <div>
                  <span className="text-gray-500 text-xs">Odalar</span>
                  <p className="font-semibold">{lastRun.rooms_processed}</p>
                </div>
                <div>
                  <span className="text-gray-500 text-xs">Masraflar</span>
                  <p className="font-semibold">{lastRun.charges_posted}</p>
                </div>
                <div>
                  <span className="text-gray-500 text-xs">Oda Geliri</span>
                  <p className="font-semibold">{lastRun.total_room_revenue?.toFixed(2)} TL</p>
                </div>
                <div>
                  <span className="text-gray-500 text-xs">Vergi</span>
                  <p className="font-semibold">{lastRun.total_tax_amount?.toFixed(2)} TL</p>
                </div>
                <div>
                  <span className="text-gray-500 text-xs">Sure</span>
                  <p className="font-semibold">{lastRun.duration_ms ? `${lastRun.duration_ms}ms` : "-"}</p>
                </div>
              </div>
              {(lastRun.arrivals_pending > 0 || lastRun.departures_pending > 0 || lastRun.folios_unbalanced > 0) && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {lastRun.arrivals_pending > 0 && (
                    <Badge className="bg-blue-50 text-blue-700 border border-blue-200 text-xs">
                      {lastRun.arrivals_pending} bekleyen giris
                    </Badge>
                  )}
                  {lastRun.departures_pending > 0 && (
                    <Badge className="bg-orange-50 text-orange-700 border border-orange-200 text-xs">
                      {lastRun.departures_pending} bekleyen cikis
                    </Badge>
                  )}
                  {lastRun.folios_unbalanced > 0 && (
                    <Badge className="bg-red-50 text-red-700 border border-red-200 text-xs">
                      {lastRun.folios_unbalanced} dengesiz folio
                    </Badge>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* History Table */}
        <Card data-testid="audit-history-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Clock className="w-4 h-4 text-gray-500" />
              Denetim Gecmisi ({historyTotal})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex items-center justify-center py-12 text-gray-500 text-sm">
                <RefreshCw className="w-5 h-5 mr-2 animate-spin" />
                Yukleniyor...
              </div>
            ) : history.length === 0 ? (
              <div data-testid="no-history" className="py-10 text-center text-gray-500 text-sm">
                <Moon className="w-10 h-10 mx-auto text-gray-300 mb-2" />
                Henuz gece denetimi yapilmamis
              </div>
            ) : (
              <div className="space-y-2">
                {history.map((run) => {
                  const isExpanded = expandedRun === run.audit_id;
                  const runExceptions = exceptions[run.audit_id] || [];
                  const startedAt = run.started_at ? new Date(run.started_at) : null;

                  return (
                    <div
                      key={run.audit_id}
                      data-testid={`audit-run-${run.audit_id}`}
                      className="border rounded-lg overflow-hidden"
                    >
                      <div
                        className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-gray-50/50 transition"
                        onClick={() => toggleExpand(run.audit_id)}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <StatusBadge status={run.status} />
                          <div className="min-w-0">
                            <p className="text-sm font-semibold text-gray-900">
                              {run.business_date}
                              {run.is_dry_run && (
                                <span className="ml-1.5 text-purple-600 text-xs font-normal">(Simuelasyon)</span>
                              )}
                              {run.is_rerun && (
                                <span className="ml-1.5 text-orange-600 text-xs font-normal">(Tekrar)</span>
                              )}
                            </p>
                            <p className="text-xs text-gray-500">
                              {startedAt ? startedAt.toLocaleString("tr-TR") : "-"}
                              {run.duration_ms ? ` • ${run.duration_ms}ms` : ""}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          <div className="hidden md:flex items-center gap-4 text-xs text-gray-500">
                            <span>{run.rooms_processed} oda</span>
                            <span>{run.charges_posted} masraf</span>
                            <span>{run.total_room_revenue?.toFixed(0)} TL</span>
                            {run.exceptions_count > 0 && (
                              <Badge className="bg-amber-50 text-amber-700 border border-amber-200 text-[11px]">
                                {run.exceptions_count} istisna
                              </Badge>
                            )}
                          </div>
                          {isExpanded ? (
                            <ChevronUp className="w-4 h-4 text-gray-400" />
                          ) : (
                            <ChevronDown className="w-4 h-4 text-gray-400" />
                          )}
                        </div>
                      </div>

                      {isExpanded && (
                        <div className="border-t bg-gray-50/50 px-4 py-3 space-y-3">
                          {/* Detail Grid */}
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                            <div>
                              <span className="text-gray-500 text-xs">Oda Geliri</span>
                              <p className="font-semibold">{run.total_room_revenue?.toFixed(2)} TL</p>
                            </div>
                            <div>
                              <span className="text-gray-500 text-xs">Vergi</span>
                              <p className="font-semibold">{run.total_tax_amount?.toFixed(2)} TL</p>
                            </div>
                            <div>
                              <span className="text-gray-500 text-xs">No-Show</span>
                              <p className="font-semibold">{run.no_shows_processed}</p>
                            </div>
                            <div>
                              <span className="text-gray-500 text-xs">Folio (Dengeli/Dengesiz)</span>
                              <p className="font-semibold">
                                <span className="text-emerald-600">{run.folios_balanced}</span>
                                {" / "}
                                <span className={run.folios_unbalanced > 0 ? "text-red-600" : "text-gray-400"}>
                                  {run.folios_unbalanced}
                                </span>
                              </p>
                            </div>
                          </div>

                          {/* Exceptions */}
                          {runExceptions.length > 0 ? (
                            <div>
                              <p className="text-xs font-semibold text-gray-600 mb-2 flex items-center gap-1">
                                <AlertTriangle className="w-3.5 h-3.5" />
                                Istisnalar ({runExceptions.length})
                              </p>
                              <div className="space-y-1.5 max-h-60 overflow-y-auto">
                                {runExceptions.map((exc) => (
                                  <div
                                    key={exc.id}
                                    className="flex items-start gap-2 p-2 bg-white border rounded text-xs"
                                  >
                                    <SeverityBadge severity={exc.severity} />
                                    <div className="min-w-0 flex-1">
                                      <p className="text-gray-800">{exc.message}</p>
                                      <p className="text-gray-400 text-[11px] mt-0.5">
                                        {exc.category} • {exc.entity_type}
                                        {exc.entity_id ? ` • ${exc.entity_id.substring(0, 8)}...` : ""}
                                      </p>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ) : run.exceptions_count === 0 ? (
                            <p className="text-xs text-gray-400 flex items-center gap-1">
                              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                              Istisna yok - denetim temiz tamamlandi
                            </p>
                          ) : (
                            <p className="text-xs text-gray-400">Istisnalar yukleniyor...</p>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Run Audit Dialog */}
        <Dialog open={showRunDialog} onOpenChange={setShowRunDialog}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Moon className="w-5 h-5 text-indigo-600" />
                Gece Denetimi Baslat
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="p-3 bg-indigo-50 border border-indigo-200 rounded-lg">
                <p className="text-sm text-indigo-800">
                  <strong>Is Gunu:</strong> {businessDate || "-"}
                </p>
                <p className="text-xs text-indigo-600 mt-1">
                  Bu tarih icin gece denetimi calistirilacak
                </p>
              </div>

              {/* Options */}
              <div className="space-y-3">
                <label className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 cursor-pointer">
                  <input
                    data-testid="dry-run-checkbox"
                    type="checkbox"
                    checked={runOptions.dry_run}
                    onChange={(e) => setRunOptions({ ...runOptions, dry_run: e.target.checked })}
                    className="w-4 h-4 rounded border-gray-300 text-indigo-600"
                  />
                  <div>
                    <p className="text-sm font-medium text-gray-800">Simuelasyon (Dry Run)</p>
                    <p className="text-xs text-gray-500">Degisiklik yapmadan test et</p>
                  </div>
                </label>

                <label className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 cursor-pointer">
                  <input
                    data-testid="force-rerun-checkbox"
                    type="checkbox"
                    checked={runOptions.force_rerun}
                    onChange={(e) => setRunOptions({ ...runOptions, force_rerun: e.target.checked })}
                    className="w-4 h-4 rounded border-gray-300 text-amber-600"
                  />
                  <div>
                    <p className="text-sm font-medium text-gray-800">Tekrar Calistir</p>
                    <p className="text-xs text-gray-500">Daha once tamamlanmissa bile tekrar calistir</p>
                  </div>
                </label>

                <label className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 cursor-pointer">
                  <input
                    data-testid="skip-validations-checkbox"
                    type="checkbox"
                    checked={runOptions.skip_validations}
                    onChange={(e) => setRunOptions({ ...runOptions, skip_validations: e.target.checked })}
                    className="w-4 h-4 rounded border-gray-300 text-red-600"
                  />
                  <div>
                    <p className="text-sm font-medium text-gray-800">Dogrulamalari Atla</p>
                    <p className="text-xs text-gray-500">On kontrolleri atlayarak calistir (dikkatli kullanin)</p>
                  </div>
                </label>

                <div>
                  <label className="text-xs text-gray-600 mb-1 block">Aciklama (opsiyonel)</label>
                  <input
                    data-testid="reason-input"
                    type="text"
                    placeholder="Denetim aciklamasi..."
                    value={runOptions.reason}
                    onChange={(e) => setRunOptions({ ...runOptions, reason: e.target.value })}
                    className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  />
                </div>
              </div>

              {runOptions.skip_validations && (
                <div className="p-2 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-red-700">
                    Dogrulama atlama sadece acil durumlarda kullanilmalidir. On kontrolsuz denetim veri tutarsizliklarina neden olabilir.
                  </p>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowRunDialog(false)} disabled={running}>
                  Iptal
                </Button>
                <Button
                  data-testid="confirm-run-btn"
                  onClick={handleRunAudit}
                  disabled={running}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white"
                >
                  {running ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                      Calisiyor...
                    </>
                  ) : runOptions.dry_run ? (
                    <>
                      <Eye className="w-4 h-4 mr-1" />
                      Simuelasyon Baslat
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4 mr-1" />
                      Denetimi Baslat
                    </>
                  )}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
};

export default NightAuditDashboard;
