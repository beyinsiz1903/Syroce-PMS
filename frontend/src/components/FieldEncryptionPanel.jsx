import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import {
  Database, Shield, Lock, RefreshCw, Play,
  CheckCircle, AlertTriangle, ChevronDown, ChevronUp,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
import { useTranslation } from 'react-i18next';

function CoverageBar({ collection, data }) {
  const { t } = useTranslation();
  const pct = data.coverage_percent || 0;
  const barColor =
    pct >= 100 ? "bg-emerald-500" : pct >= 50 ? "bg-yellow-500" : "bg-red-500";

  return (
    <div className="space-y-1" data-testid={`coverage-${collection}`}>
      <div className="flex items-center justify-between text-xs">
        <span className="text-zinc-300 font-mono">{collection}</span>
        <div className="flex items-center gap-2">
          <span className="text-zinc-500">
            {data.encrypted}/{data.total_documents}
          </span>
          <Badge
            variant="outline"
            className={`text-[9px] px-1.5 py-0 font-mono ${
              pct >= 100
                ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
                : pct > 0
                ? "text-yellow-400 border-yellow-500/30 bg-yellow-500/10"
                : "text-zinc-500 border-zinc-600/30"
            }`}
          >
            {pct}%
          </Badge>
        </div>
      </div>
      <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${barColor}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <div className="flex gap-2 text-[10px] text-zinc-600 flex-wrap">
        {data.fields?.map((f) => (
          <span key={f} className="font-mono">{f}</span>
        ))}
      </div>
    </div>
  );
}

export function FieldEncryptionPanel() {
  const { t } = useTranslation();
  const [status, setStatus] = useState(null);
  const [progress, setProgress] = useState([]);
  const [audit, setAudit] = useState([]);
  const [loading, setLoading] = useState(true);
  const [migrating, setMigrating] = useState({});
  const [auditExpanded, setAuditExpanded] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem("token");
      const headers = { Authorization: `Bearer ${token}` };
      const [statusRes, progressRes, auditRes] = await Promise.allSettled([
        axios.get("/ops/field-encryption/status", { headers }),
        axios.get("/ops/field-encryption/progress", { headers }),
        axios.get("/ops/field-encryption/audit?limit=20", { headers }),
      ]);
      if (statusRes.status === "fulfilled") setStatus(statusRes.value.data);
      if (progressRes.status === "fulfilled") setProgress(progressRes.value.data?.progress || []);
      if (auditRes.status === "fulfilled") setAudit(auditRes.value.data?.audit || []);
    } catch {
      toast.error("Alan sifreleme verileri yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const triggerMigration = async (collection) => {
    setMigrating((prev) => ({ ...prev, [collection]: true }));
    try {
      const token = localStorage.getItem("token");
      const res = await axios.post(
        `/ops/field-encryption/migrate/${collection}?batch_size=100`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      const migration = res.data?.migration || {};
      toast.success(
        `${collection}: ${migration.processed} kayıt sifrelendi (${migration.errors} hata)`
      );
      fetchData();
    } catch (err) {
      toast.error(`Migration hatası: ${err.response?.data?.detail || err.message}`);
    } finally {
      setMigrating((prev) => ({ ...prev, [collection]: false }));
    }
  };

  const ensureIndexes = async () => {
    try {
      const token = localStorage.getItem("token");
      const res = await axios.post(
        "/ops/field-encryption/ensure-indexes",
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success(`${res.data?.indexes_created?.length || 0} index oluşturuldu`);
    } catch (err) {
      toast.error(`Index hatası: ${err.response?.data?.detail || err.message}`);
    }
  };

  if (loading && !status) {
    return <Skeleton className="h-64 bg-zinc-800" data-testid="field-enc-loading" />;
  }

  const collections = status?.collections || {};
  const totalDocs = Object.values(collections).reduce((s, c) => s + (c.total_documents || 0), 0);
  const totalEnc = Object.values(collections).reduce((s, c) => s + (c.encrypted || 0), 0);
  const overallPct = totalDocs > 0 ? Math.round((totalEnc / totalDocs) * 100 * 10) / 10 : 0;

  return (
    <Card className="bg-zinc-900 border-zinc-800" data-testid="field-encryption-panel">
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium text-zinc-400 uppercase tracking-wider flex items-center gap-2">
            <Database className="h-3.5 w-3.5" />
            P2 At-Rest PII Sifreleme
          </CardTitle>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-[10px] text-zinc-500"
              onClick={ensureIndexes}
              data-testid="ensure-indexes-btn"
            >
              <Lock className="h-3 w-3 mr-1" /> Index
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-[10px] text-zinc-500"
              onClick={fetchData}
              disabled={loading}
              data-testid="field-enc-refresh-btn"
            >
              <RefreshCw className={`h-3 w-3 mr-1 ${loading ? "animate-spin" : ""}`} />
              {t('cm.components_FieldEncryptionPanel.yenile')}
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="px-4 pb-4 space-y-4">
        {/* Overall Summary */}
        <div className="flex items-center gap-4" data-testid="field-enc-summary">
          <div className="flex items-center gap-2">
            {overallPct >= 100 ? (
              <CheckCircle className="h-4 w-4 text-emerald-400" />
            ) : overallPct > 0 ? (
              <Shield className="h-4 w-4 text-yellow-400" />
            ) : (
              <AlertTriangle className="h-4 w-4 text-red-400" />
            )}
            <span className="text-xl font-bold font-mono text-zinc-100">{overallPct}%</span>
          </div>
          <div className="text-xs text-zinc-500">
            <span className="text-zinc-300 font-mono">{totalEnc}</span> / {totalDocs} dokuman sifrelendi
          </div>
          <Badge
            variant="outline"
            className={`text-[9px] px-2 py-0 font-mono ${
              overallPct >= 100
                ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
                : "text-yellow-400 border-yellow-500/30 bg-yellow-500/10"
            }`}
          >
            {overallPct >= 100 ? "TAM KAPSAM" : "MIGRATION GEREKLI"}
          </Badge>
        </div>

        {/* Per-collection Coverage */}
        <div className="space-y-3">
          {Object.entries(collections).map(([col, data]) => (
            <div key={col} className="flex items-start gap-2">
              <div className="flex-1">
                <CoverageBar collection={col} data={data} />
              </div>
              {data.unencrypted > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-6 text-[10px] border-zinc-700 text-zinc-400 hover:text-zinc-200 mt-0.5 shrink-0"
                  onClick={() => triggerMigration(col)}
                  disabled={migrating[col]}
                  data-testid={`migrate-${col}-btn`}
                >
                  {migrating[col] ? (
                    <RefreshCw className="h-3 w-3 animate-spin" />
                  ) : (
                    <>
                      <Play className="h-3 w-3 mr-1" /> Migrate
                    </>
                  )}
                </Button>
              )}
              {data.unencrypted === 0 && data.total_documents > 0 && (
                <CheckCircle className="h-4 w-4 text-emerald-500 mt-1 shrink-0" />
              )}
            </div>
          ))}
        </div>

        {/* Migration Progress */}
        {progress.length > 0 && (
          <div className="border-t border-zinc-800 pt-3">
            <h4 className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">
              Son Migration Sonuclari
            </h4>
            <div className="space-y-1">
              {progress.map((p, i) => (
                <div key={i} className="flex items-center justify-between text-[10px] text-zinc-400">
                  <span className="font-mono">{p.collection}</span>
                  <div className="flex items-center gap-2">
                    <span>{p.processed} {t('cm.components_FieldEncryptionPanel.kayit')}</span>
                    {p.errors > 0 && (
                      <Badge variant="outline" className="text-[8px] text-red-400 border-red-500/30 px-1 py-0">
                        {p.errors} hata
                      </Badge>
                    )}
                    <Badge
                      variant="outline"
                      className={`text-[8px] px-1 py-0 ${
                        p.status === "completed"
                          ? "text-emerald-400 border-emerald-500/30"
                          : "text-yellow-400 border-yellow-500/30"
                      }`}
                    >
                      {p.status === "completed" ? "TAMAMLANDI" : p.status}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Audit Trail */}
        {audit.length > 0 && (
          <div className="border-t border-zinc-800 pt-3">
            <button
              onClick={() => setAuditExpanded(!auditExpanded)}
              className="flex items-center gap-2 text-[10px] text-zinc-500 uppercase tracking-wider hover:text-zinc-300 transition-colors w-full"
              data-testid="field-enc-audit-toggle"
            >
              {auditExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              Denetim Izi ({audit.length})
            </button>
            {auditExpanded && (
              <div className="space-y-1 mt-2">
                {audit.map((a, i) => (
                  <div key={i} className="flex items-center justify-between text-[10px] text-zinc-500 border-b border-zinc-800/50 pb-1">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-[8px] px-1 py-0 text-blue-400 border-blue-500/30">
                        {a.action}
                      </Badge>
                      <span className="font-mono">{a.collection}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-zinc-600">{a.actor}</span>
                      <span className="text-zinc-700">
                        {a.timestamp ? new Date(a.timestamp).toLocaleString("tr-TR") : ""}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
