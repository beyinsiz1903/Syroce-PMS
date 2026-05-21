import { useState, useEffect, useCallback, useMemo } from "react";
import { useTranslation } from 'react-i18next';
import axios from "axios";
import {
  RotateCcw, Shield, AlertTriangle, CheckCircle, XCircle,
  Clock, ChevronDown, ChevronUp, Play, Zap, Undo2,
  Activity, History, ShieldAlert, Timer, RefreshCw,
  AlertOctagon, Eye,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "../components/ui/alert-dialog";
import { toast } from "sonner";

// ── Status badge styles ───────────────────────────────────────────
const STATUS_STYLES = {
  overdue: { label: "SÜRESI GEÇMIŞ", icon: AlertOctagon, cls: "text-red-600 border-red-500/40 bg-red-500/15" },
  warning: { label: "UYARI", icon: AlertTriangle, cls: "text-amber-600 border-amber-500/40 bg-amber-500/15" },
  healthy: { label: "SAĞLIKLI", icon: CheckCircle, cls: "text-emerald-600 border-emerald-500/40 bg-emerald-500/15" },
};

const ACTION_STYLES = {
  rotation_initiated: { label: "Başlatıldı", icon: Play, cls: "text-blue-600" },
  rotation_tested: { label: "Test Edildi", icon: Zap, cls: "text-cyan-400" },
  rotation_activated: { label: "Aktifleştirildi", icon: CheckCircle, cls: "text-emerald-600" },
  rotation_rolled_back: { label: "Geri Alındı", icon: Undo2, cls: "text-amber-600" },
  rotation_activation_failed: { label: "Aktivasyon Başarısız", icon: XCircle, cls: "text-red-600" },
};

// ── Risk Summary Cards ────────────────────────────────────────────
function RiskSummaryCards({ dashboard, audit }) {
  const items = dashboard?.items || [];
  const auditItems = audit?.items || [];
  const summary = dashboard?.summary || {};

  const overdueCount = summary.overdue || 0;
  const warningCount = summary.warning || 0;

  // Failed tests in last 7 days
  const now = new Date();
  const sevenDaysAgo = new Date(now - 7 * 86400000);
  const recentAudit = auditItems.filter(a => new Date(a.timestamp) > sevenDaysAgo);
  const testFailCount = recentAudit.filter(a =>
    a.action === "rotation_tested" && a.details?.success === false
  ).length;
  const rollbackCount = recentAudit.filter(a => a.action === "rotation_rolled_back").length;

  // Riskiest connector: most overdue items grouped by provider
  const providerRisk = {};
  items.forEach(item => {
    if (item.is_overdue || item.is_warning) {
      const p = item.provider || "unknown";
      providerRisk[p] = (providerRisk[p] || 0) + (item.is_overdue ? 2 : 1);
    }
  });
  const riskiestConnector = Object.keys(providerRisk).length > 0
    ? Object.entries(providerRisk).sort((a, b) => b[1] - a[1])[0][0]
    : null;

  const cards = [
    {
      title: "Süresi Geçmiş",
      value: overdueCount,
      icon: AlertOctagon,
      color: overdueCount > 0 ? "text-red-600" : "text-gray-500",
      bg: overdueCount > 0 ? "bg-red-500/10 border-red-500/20" : "bg-gray-100/50 border-gray-300/50",
      pulse: overdueCount > 0,
    },
    {
      title: "Uyarı",
      value: warningCount,
      icon: AlertTriangle,
      color: warningCount > 0 ? "text-amber-600" : "text-gray-500",
      bg: warningCount > 0 ? "bg-amber-500/10 border-amber-500/20" : "bg-gray-100/50 border-gray-300/50",
    },
    {
      title: "Son 7 Gün Rollback",
      value: rollbackCount,
      icon: Undo2,
      color: rollbackCount > 0 ? "text-amber-600" : "text-gray-500",
      bg: rollbackCount > 0 ? "bg-amber-500/10 border-amber-500/20" : "bg-gray-100/50 border-gray-300/50",
    },
    {
      title: "Test Başarısız",
      value: testFailCount,
      icon: XCircle,
      color: testFailCount > 0 ? "text-red-600" : "text-gray-500",
      bg: testFailCount > 0 ? "bg-red-500/10 border-red-500/20" : "bg-gray-100/50 border-gray-300/50",
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
      {cards.map((card, i) => {
        const Icon = card.icon;
        return (
          <div
            key={i}
            className={`rounded-lg border px-3 py-2.5 ${card.bg} transition-all`}
            data-testid={`risk-card-${i}`}
          >
            <div className="flex items-center gap-2 mb-1">
              <Icon className={`h-3.5 w-3.5 ${card.color} ${card.pulse ? "animate-pulse" : ""}`} />
              <span className="text-[10px] text-gray-500 uppercase tracking-wider font-medium">{card.title}</span>
            </div>
            <span className={`text-xl font-bold font-mono ${card.color}`}>{card.value}</span>
          </div>
        );
      })}
      {/* Riskiest connector */}
      <div
        className={`rounded-lg border px-3 py-2.5 ${riskiestConnector ? "bg-red-500/5 border-red-500/20" : "bg-gray-100/50 border-gray-300/50"} transition-all`}
        data-testid="risk-card-connector"
      >
        <div className="flex items-center gap-2 mb-1">
          <ShieldAlert className={`h-3.5 w-3.5 ${riskiestConnector ? "text-red-600" : "text-gray-500"}`} />
          <span className="text-[10px] text-gray-500 uppercase tracking-wider font-medium">En Riskli</span>
        </div>
        <span className={`text-sm font-bold font-mono ${riskiestConnector ? "text-red-700" : "text-gray-500"}`}>
          {riskiestConnector || "—"}
        </span>
      </div>
    </div>
  );
}

// ── Secret Rotation Table ─────────────────────────────────────────
function RotationTable({ items, onViewDetail }) {
  const [sortField, setSortField] = useState("status");

  const sorted = useMemo(() => {
    const priority = { overdue: 0, warning: 1, healthy: 2 };
    return [...items].sort((a, b) => {
      if (sortField === "status") return (priority[a.status] || 3) - (priority[b.status] || 3);
      if (sortField === "age") return (b.age_days || 0) - (a.age_days || 0);
      if (sortField === "provider") return (a.provider || "").localeCompare(b.provider || "");
      return 0;
    });
  }, [items, sortField]);

  if (items.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500 text-xs" data-testid="rotation-table-empty">
        Henüz yönetilen secret yok
      </div>
    );
  }

  return (
    <div className="overflow-x-auto" data-testid="rotation-table">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-200 text-gray-500">
            <th className="text-left py-2 pr-3 font-medium">
              <button onClick={() => setSortField("status")} className="hover:text-gray-700 transition-colors flex items-center gap-1">
                Durum {sortField === "status" && <ChevronDown className="h-3 w-3" />}
              </button>
            </th>
            <th className="text-left py-2 pr-3 font-medium">
              <button onClick={() => setSortField("provider")} className="hover:text-gray-700 transition-colors flex items-center gap-1">
                Connector {sortField === "provider" && <ChevronDown className="h-3 w-3" />}
              </button>
            </th>
            <th className="text-left py-2 pr-3 font-medium">Secret Path</th>
            <th className="text-center py-2 pr-3 font-medium">Aktif V.</th>
            <th className="text-left py-2 pr-3 font-medium">Son Rotasyon</th>
            <th className="text-left py-2 pr-3 font-medium">Sonraki Due</th>
            <th className="text-left py-2 pr-3 font-medium">
              <button onClick={() => setSortField("age")} className="hover:text-gray-700 transition-colors flex items-center gap-1">
                Yaş {sortField === "age" && <ChevronDown className="h-3 w-3" />}
              </button>
            </th>
            <th className="text-center py-2 font-medium">Detay</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((item, i) => {
            const st = STATUS_STYLES[item.status] || STATUS_STYLES.healthy;
            const StIcon = st.icon;
            const agePct = item.max_rotation_days > 0 ? Math.min((item.age_days || 0) / item.max_rotation_days * 100, 100) : 0;
            const barColor = item.is_overdue ? "bg-red-500" : item.is_warning ? "bg-amber-500" : "bg-emerald-500";

            return (
              <tr key={i} className="border-b border-gray-200/50 hover:bg-gray-100/30 transition-colors">
                <td className="py-2 pr-3">
                  <Badge variant="outline" className={`text-[9px] px-1.5 py-0 font-mono ${st.cls}`}>
                    <StIcon className="h-2.5 w-2.5 mr-1" />
                    {st.label}
                  </Badge>
                </td>
                <td className="py-2 pr-3">
                  <span className="font-mono text-gray-700">{item.provider}</span>
                </td>
                <td className="py-2 pr-3">
                  <span className="font-mono text-gray-500 text-[10px] truncate max-w-[200px] block" title={item.secret_path}>
                    {item.secret_path}
                  </span>
                </td>
                <td className="py-2 pr-3 text-center">
                  {item.active_version ? (
                    <span className="font-mono text-emerald-600">v{item.active_version}</span>
                  ) : (
                    <span className="text-gray-500">—</span>
                  )}
                </td>
                <td className="py-2 pr-3">
                  <span className="text-gray-600 text-[10px]">
                    {item.last_rotated ? new Date(item.last_rotated).toLocaleDateString("tr-TR") : "—"}
                  </span>
                </td>
                <td className="py-2 pr-3">
                  <span className={`text-[10px] ${item.is_overdue ? "text-red-600 font-semibold" : "text-gray-600"}`}>
                    {item.next_rotation_due ? new Date(item.next_rotation_due).toLocaleDateString("tr-TR") : "—"}
                  </span>
                </td>
                <td className="py-2 pr-3">
                  <div className="flex items-center gap-2">
                    <div className="w-12 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${barColor}`} style={{ width: `${agePct}%` }} />
                    </div>
                    <span className="text-gray-500 font-mono text-[10px]">{item.age_days ?? "—"}g</span>
                  </div>
                </td>
                <td className="py-2 text-center">
                  <button
                    onClick={() => onViewDetail(item)}
                    className="text-gray-500 hover:text-gray-700 transition-colors p-1"
                    data-testid={`view-detail-${i}`}
                  >
                    <Eye className="h-3.5 w-3.5" />
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Audit Trail ───────────────────────────────────────────────────
function AuditTrail({ audit, loading }) {
  const [expanded, setExpanded] = useState(false);
  const items = audit?.items || [];
  const shown = expanded ? items : items.slice(0, 5);

  if (loading) return <Skeleton className="h-32 bg-gray-100" />;

  return (
    <Card className="bg-white border-gray-200" data-testid="rotation-audit-trail">
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium text-gray-600 uppercase tracking-wider flex items-center gap-2">
            <History className="h-3.5 w-3.5" /> Rotasyon Audit Trail
          </CardTitle>
          <Badge variant="outline" className="text-[9px] text-gray-500 border-gray-300 font-mono">
            {audit?.total || 0} kayıt
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        {items.length === 0 ? (
          <div className="text-xs text-gray-500 py-3">Henüz kayıt yok</div>
        ) : (
          <div className="space-y-0">
            {shown.map((item, i) => {
              const style = ACTION_STYLES[item.action] || { label: item.action, icon: Activity, cls: "text-gray-600" };
              const ActionIcon = style.icon;
              const failed = item.action === "rotation_tested" && item.details?.success === false;

              return (
                <div key={i} className="flex items-center gap-3 py-1.5 border-b border-gray-200/40 last:border-b-0">
                  <ActionIcon className={`h-3 w-3 flex-shrink-0 ${failed ? "text-red-600" : style.cls}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-medium ${failed ? "text-red-600" : style.cls}`}>
                        {failed ? "Test BAŞARISIZ" : style.label}
                      </span>
                      <span className="text-[10px] text-gray-500 truncate" title={item.secret_path}>
                        {item.secret_path?.split("/").slice(-2).join("/")}
                      </span>
                    </div>
                    {item.details && (
                      <span className="text-[9px] text-gray-500 block truncate">
                        {typeof item.details === "object" ? (item.details.details || item.details.reason || JSON.stringify(item.details)) : item.details}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-[10px] text-gray-500 flex-shrink-0">
                    <span className="font-mono">v{item.version}</span>
                    <span>{item.actor}</span>
                    <span>{new Date(item.timestamp).toLocaleString("tr-TR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
                  </div>
                </div>
              );
            })}
            {items.length > 5 && (
              <button
                onClick={() => setExpanded(!expanded)}
                className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-700 pt-2 transition-colors"
                data-testid="audit-expand-btn"
              >
                {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                {expanded ? "Daralt" : `Tümünü göster (${items.length})`}
              </button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Detail Sheet (for a single secret) ─────────────────────────────
function SecretDetailSheet({ item, onClose, onAction }) {
  const [versions, setVersions] = useState(null);
  const [loadingVersions, setLoadingVersions] = useState(false);

  useEffect(() => {
    if (!item) return;
    const fetchVersions = async () => {
      setLoadingVersions(true);
      try {
        const realPath = item._realPath || item.secret_path;
        const res = await axios.get(`/ops/secrets/rotation/status?secret_path=${encodeURIComponent(realPath)}`);
        setVersions(res.data);
      } catch {
        setVersions({ versions: [], active_version: null, total_versions: 0 });
      } finally {
        setLoadingVersions(false);
      }
    };
    fetchVersions();
  }, [item]);

  if (!item) return null;

  const versionList = versions?.versions || [];
  const st = STATUS_STYLES[item.status] || STATUS_STYLES.healthy;
  const StIcon = st.icon;

  const versionStatusStyles = {
    active: "text-emerald-600 border-emerald-500/30 bg-emerald-500/10",
    pending_test: "text-blue-600 border-blue-500/30 bg-blue-500/10",
    test_passed: "text-cyan-400 border-cyan-500/30 bg-cyan-500/10",
    test_failed: "text-red-600 border-red-500/30 bg-red-500/10",
    archived: "text-gray-500 border-gray-300/30 bg-gray-200/10",
    rolled_back: "text-amber-600 border-amber-500/30 bg-amber-500/10",
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-end" data-testid="secret-detail-sheet">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg h-full bg-white border-l border-gray-200 overflow-y-auto shadow-2xl animate-in slide-in-from-right">
        {/* Header */}
        <div className="sticky top-0 bg-white/95 backdrop-blur-sm border-b border-gray-200 px-5 py-4 z-10">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                <Shield className="h-4 w-4 text-amber-600" />
                Secret Detay
              </h3>
              <p className="text-[10px] text-gray-500 mt-0.5 font-mono truncate max-w-[300px]" title={item.secret_path}>
                {item.secret_path}
              </p>
            </div>
            <button onClick={onClose} className="text-gray-500 hover:text-gray-700 text-lg leading-none">&times;</button>
          </div>
        </div>

        <div className="px-5 py-4 space-y-5">
          {/* Status overview */}
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg bg-gray-100/50 border border-gray-300/50 p-3">
              <span className="text-[10px] text-gray-500 uppercase tracking-wider block mb-1">Durum</span>
              <Badge variant="outline" className={`text-[10px] font-mono px-2 py-0.5 ${st.cls}`}>
                <StIcon className="h-3 w-3 mr-1" />
                {st.label}
              </Badge>
            </div>
            <div className="rounded-lg bg-gray-100/50 border border-gray-300/50 p-3">
              <span className="text-[10px] text-gray-500 uppercase tracking-wider block mb-1">Connector</span>
              <span className="text-sm font-mono text-gray-900">{item.provider}</span>
            </div>
            <div className="rounded-lg bg-gray-100/50 border border-gray-300/50 p-3">
              <span className="text-[10px] text-gray-500 uppercase tracking-wider block mb-1">Aktif Versiyon</span>
              <span className="text-sm font-mono text-emerald-600">{item.active_version ? `v${item.active_version}` : "—"}</span>
            </div>
            <div className="rounded-lg bg-gray-100/50 border border-gray-300/50 p-3">
              <span className="text-[10px] text-gray-500 uppercase tracking-wider block mb-1">Yaş</span>
              <span className={`text-sm font-mono ${item.is_overdue ? "text-red-600" : item.is_warning ? "text-amber-600" : "text-gray-700"}`}>
                {item.age_days ?? "—"} gün
              </span>
            </div>
          </div>

          {/* Timeline */}
          <div>
            <div className="flex items-center gap-2 text-[10px] text-gray-500 uppercase tracking-wider mb-2">
              <Timer className="h-3 w-3" /> Rotasyon Zamanlama
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <span className="text-gray-500 block">Son Rotasyon</span>
                <span className="text-gray-700 font-mono">
                  {item.last_rotated ? new Date(item.last_rotated).toLocaleDateString("tr-TR") : "—"}
                </span>
              </div>
              <div>
                <span className="text-gray-500 block">Sonraki Due Date</span>
                <span className={`font-mono ${item.is_overdue ? "text-red-600" : "text-gray-700"}`}>
                  {item.next_rotation_due ? new Date(item.next_rotation_due).toLocaleDateString("tr-TR") : "—"}
                </span>
              </div>
              <div>
                <span className="text-gray-500 block">Maks Rotasyon Süresi</span>
                <span className="text-gray-700 font-mono">{item.max_rotation_days} gün</span>
              </div>
              <div>
                <span className="text-gray-500 block">Tip</span>
                <span className="text-gray-700 font-mono">{item.secret_type}</span>
              </div>
            </div>
          </div>

          {/* Version History */}
          <div>
            <div className="flex items-center gap-2 text-[10px] text-gray-500 uppercase tracking-wider mb-2">
              <History className="h-3 w-3" /> Versiyon Geçmişi
            </div>
            {loadingVersions ? (
              <Skeleton className="h-20 bg-gray-100" />
            ) : versionList.length === 0 ? (
              <div className="text-xs text-gray-500 py-2">Versiyon geçmişi yok</div>
            ) : (
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {versionList.map((v, i) => (
                  <div key={i} className="flex items-center justify-between text-[10px] border-b border-gray-200/40 pb-1.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-gray-700">v{v.version}</span>
                      <Badge variant="outline" className={`text-[9px] px-1.5 py-0 ${versionStatusStyles[v.status] || "text-gray-500 border-gray-300"}`}>
                        {v.status?.replace(/_/g, " ").toUpperCase()}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2 text-gray-500">
                      <span>{v.created_by}</span>
                      <span>{new Date(v.created_at).toLocaleDateString("tr-TR")}</span>
                      {v.test_result && (
                        v.test_result.success
                          ? <CheckCircle className="h-3 w-3 text-emerald-600" />
                          : <XCircle className="h-3 w-3 text-red-600" />
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Actions */}
          <div>
            <div className="flex items-center gap-2 text-[10px] text-gray-500 uppercase tracking-wider mb-2">
              <Zap className="h-3 w-3" /> Aksiyonlar
            </div>
            <div className="flex flex-wrap gap-2">
              {/* Show relevant actions based on version states */}
              {versionList.some(v => v.status === "pending_test") && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-[10px] border-blue-500/30 text-blue-600 hover:bg-blue-500/10"
                  onClick={() => {
                    const pendingV = versionList.find(v => v.status === "pending_test");
                    if (pendingV) onAction("test", item, pendingV.version);
                  }}
                  data-testid="action-test-btn"
                >
                  <Zap className="h-3 w-3 mr-1" /> Test Et
                </Button>
              )}
              {versionList.some(v => v.status === "test_passed") && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-[10px] border-emerald-500/30 text-emerald-600 hover:bg-emerald-500/10"
                  onClick={() => {
                    const passedV = versionList.find(v => v.status === "test_passed");
                    if (passedV) onAction("activate", item, passedV.version);
                  }}
                  data-testid="action-activate-btn"
                >
                  <CheckCircle className="h-3 w-3 mr-1" /> Aktifleştir
                </Button>
              )}
              {versionList.some(v => v.status === "archived") && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-[10px] border-amber-500/30 text-amber-600 hover:bg-amber-500/10"
                  onClick={() => onAction("rollback", item, null)}
                  data-testid="action-rollback-btn"
                >
                  <Undo2 className="h-3 w-3 mr-1" /> Rollback
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Confirm Dialog for Critical Actions ───────────────────────────
function ConfirmActionDialog({ open, action, item, version, onConfirm, onCancel, loading }) {
  const configs = {
    activate: {
      title: "Secret Aktivasyonu Onayla",
      desc: `v${version} versiyonunu aktifleştirmek istediğinizden emin misiniz? Mevcut aktif versiyon arşivlenecek.`,
      confirmText: "Evet, Aktifleştir",
      confirmCls: "bg-emerald-600 hover:bg-emerald-700 text-white",
      icon: CheckCircle,
      iconCls: "text-emerald-600",
    },
    rollback: {
      title: "Secret Rollback Onayla",
      desc: `${item?.provider || ""} secret'ını önceki versiyona geri almak istediğinizden emin misiniz? Bu aksiyon hemen uygulanacak.`,
      confirmText: "Evet, Geri Al",
      confirmCls: "bg-amber-600 hover:bg-amber-700 text-white",
      icon: Undo2,
      iconCls: "text-amber-600",
    },
    test: {
      title: "Secret Test Onayla",
      desc: `v${version} versiyonu için dry-run test başlatmak istediğinizden emin misiniz? Bu test gerçek API bağlantısı ile yapılacak.`,
      confirmText: "Evet, Test Et",
      confirmCls: "bg-blue-600 hover:bg-blue-700 text-white",
      icon: Zap,
      iconCls: "text-blue-600",
    },
  };

  const cfg = configs[action] || configs.test;
  const Icon = cfg.icon;

  return (
    <AlertDialog open={open} onOpenChange={(v) => !v && onCancel()}>
      <AlertDialogContent className="bg-white border-gray-300 max-w-md" data-testid="confirm-action-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2 text-gray-900 text-sm">
            <Icon className={`h-5 w-5 ${cfg.iconCls}`} />
            {cfg.title}
          </AlertDialogTitle>
          <AlertDialogDescription className="text-gray-600 text-xs leading-relaxed">
            {cfg.desc}
            {item && (
              <span className="block mt-2 font-mono text-[10px] text-gray-500 bg-gray-100 rounded px-2 py-1">
                {item.secret_path}
              </span>
            )}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel className="bg-gray-100 border-gray-300 text-gray-600 hover:bg-gray-200 text-xs h-8" disabled={loading}>
            İptal
          </AlertDialogCancel>
          <AlertDialogAction
            className={`${cfg.confirmCls} text-xs h-8`}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? <RefreshCw className="h-3 w-3 animate-spin mr-1" /> : null}
            {cfg.confirmText}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// ══════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ══════════════════════════════════════════════════════════════════
export function RotationOpsPanel() {
  const { t } = useTranslation();
  const [dashboard, setDashboard] = useState(null);
  const [audit, setAudit] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedItem, setSelectedItem] = useState(null);
  const [confirmDialog, setConfirmDialog] = useState({ open: false, action: null, item: null, version: null });
  const [actionLoading, setActionLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [dashRes, auditRes] = await Promise.allSettled([
        axios.get("/ops/secrets/rotation/dashboard"),
        axios.get("/ops/secrets/rotation/audit?limit=50"),
      ]);
      if (dashRes.status === "fulfilled") setDashboard(dashRes.value.data);
      if (auditRes.status === "fulfilled") setAudit(auditRes.value.data);
    } catch {
      toast.error("Rotasyon verisi yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleAction = (action, item, version) => {
    setConfirmDialog({ open: true, action, item, version });
  };

  const executeAction = async () => {
    const { action, item, version } = confirmDialog;
    setActionLoading(true);
    try {
      const realPath = item._realPath || item.secret_path;
      if (action === "test") {
        await axios.post("/ops/secrets/rotation/test", {
          secret_path: realPath,
          version,
          actor: "ops_panel",
        });
        toast.success(`v${version} testi başarıyla tamamlandı`);
      } else if (action === "activate") {
        await axios.post("/ops/secrets/rotation/activate", {
          secret_path: realPath,
          version,
          actor: "ops_panel",
        });
        toast.success(`v${version} başarıyla aktifleştirildi`);
      } else if (action === "rollback") {
        await axios.post("/ops/secrets/rotation/rollback", {
          secret_path: realPath,
          actor: "ops_panel",
        });
        toast.success("Rollback başarıyla tamamlandı");
      }
      setConfirmDialog({ open: false, action: null, item: null, version: null });
      setSelectedItem(null);
      fetchData();
    } catch (err) {
      const detail = err.response?.data?.detail || err.response?.data?.error || t('common.operationFailed');
      toast.error(detail);
    } finally {
      setActionLoading(false);
    }
  };

  if (loading && !dashboard) {
    return (
      <div className="space-y-3" data-testid="rotation-ops-loading">
        <Skeleton className="h-20 bg-gray-100" />
        <Skeleton className="h-40 bg-gray-100" />
        <Skeleton className="h-32 bg-gray-100" />
      </div>
    );
  }

  const items = dashboard?.items || [];

  return (
    <div className="space-y-4" data-testid="rotation-ops-panel">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
            <RotateCcw className="h-4 w-4 text-amber-600" />
            Secret Rotation Yönetimi
          </h3>
          <p className="text-[10px] text-gray-500 mt-0.5">
            Aktif secret'lar, rotasyon durumu, overdue/warning bayrakları ve operasyonel aksiyonlar
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-xs text-gray-500"
          onClick={fetchData}
          disabled={loading}
          data-testid="rotation-refresh-btn"
        >
          <RefreshCw className={`h-3 w-3 mr-1 ${loading ? "animate-spin" : ""}`} />
          Yenile
        </Button>
      </div>

      {/* Risk Summary */}
      <RiskSummaryCards dashboard={dashboard} audit={audit} />

      {/* Main Table */}
      <Card className="bg-white border-gray-200" data-testid="rotation-dashboard-card">
        <CardHeader className="pb-2 pt-4 px-4">
          <div className="flex items-center justify-between">
            <CardTitle className="text-xs font-medium text-gray-600 uppercase tracking-wider flex items-center gap-2">
              <Shield className="h-3.5 w-3.5" /> Rotasyon Dashboard — {items.length} Secret
            </CardTitle>
            <div className="flex items-center gap-2 text-[10px]">
              <span className="text-emerald-600">{dashboard?.summary?.healthy || 0} sağlıklı</span>
              <span className="text-gray-500">|</span>
              <span className="text-amber-600">{dashboard?.summary?.warning || 0} uyarı</span>
              <span className="text-gray-500">|</span>
              <span className="text-red-600">{dashboard?.summary?.overdue || 0} geçmiş</span>
            </div>
          </div>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          <RotationTable items={items} onViewDetail={setSelectedItem} />
        </CardContent>
      </Card>

      {/* Audit Trail */}
      <AuditTrail audit={audit} loading={loading && !audit} />

      {/* Detail Sheet */}
      {selectedItem && (
        <SecretDetailSheet
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
          onAction={handleAction}
        />
      )}

      {/* Confirm Dialog */}
      <ConfirmActionDialog
        open={confirmDialog.open}
        action={confirmDialog.action}
        item={confirmDialog.item}
        version={confirmDialog.version}
        onConfirm={executeAction}
        onCancel={() => setConfirmDialog({ open: false, action: null, item: null, version: null })}
        loading={actionLoading}
      />
    </div>
  );
}
