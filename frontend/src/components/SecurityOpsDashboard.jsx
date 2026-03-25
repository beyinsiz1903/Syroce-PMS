import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import {
  Shield, Key, Lock, Unlock, AlertTriangle, CheckCircle,
  RefreshCw, FileKey, RotateCcw, ChevronDown, ChevronUp,
  Database, ArrowRight,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
import { RotationOpsPanel } from "./RotationOpsPanel";
import { FieldEncryptionPanel } from "./FieldEncryptionPanel";

function SecretHealthCard({ data }) {
  if (!data) return <Skeleton className="h-40 bg-zinc-800" />;

  const health = data.health || {};
  const config = data.config || {};
  const isHealthy = health.status === "healthy" || health.provider;

  return (
    <Card className="bg-zinc-900 border-zinc-800" data-testid="secrets-health-card">
      <CardHeader className="pb-2 pt-4 px-4">
        <CardTitle className="text-xs font-medium text-zinc-400 uppercase tracking-wider flex items-center gap-2">
          <Key className="h-3.5 w-3.5" /> SEC-001 Secrets Yonetimi
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-3">
        <div className="flex items-center gap-3">
          <Badge
            variant="outline"
            className={`text-[10px] font-mono px-2 py-0 ${
              isHealthy
                ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
                : "text-red-400 border-red-500/30 bg-red-500/10"
            }`}
          >
            {isHealthy ? "SAGLIKLI" : "SORUNLU"}
          </Badge>
          <span className="text-xs text-zinc-500">
            Provider: <span className="text-zinc-300 font-mono">{config.provider}</span>
          </span>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="flex items-center gap-1.5">
            {config.legacy_fallback === "true" ? (
              <Unlock className="h-3 w-3 text-yellow-400" />
            ) : (
              <Lock className="h-3 w-3 text-emerald-400" />
            )}
            <span className="text-zinc-500">Legacy Fallback:</span>
            <span className={config.legacy_fallback === "true" ? "text-yellow-400" : "text-emerald-400"}>
              {config.legacy_fallback === "true" ? "AKTIF" : "KAPALI"}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <Shield className="h-3 w-3 text-blue-400" />
            <span className="text-zinc-500">Audit:</span>
            <span className={config.audit_enabled === "true" ? "text-emerald-400" : "text-zinc-600"}>
              {config.audit_enabled === "true" ? "AKTIF" : "KAPALI"}
            </span>
          </div>
        </div>

        {/* Audit Stats */}
        <div className="flex items-center gap-4 text-[10px] text-zinc-600">
          {Object.entries(data.audit_24h || {}).map(([action, count]) => (
            <span key={action}>
              {action}: <span className="text-zinc-400 font-mono">{count}</span>
            </span>
          ))}
        </div>

        {data.anomalies_24h > 0 && (
          <div className="flex items-center gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded px-2 py-1">
            <AlertTriangle className="h-3 w-3" />
            <span>{data.anomalies_24h} anomali (son 24 saat)</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function CryptoStatusCard({ data }) {
  if (!data) return <Skeleton className="h-40 bg-zinc-800" />;

  const config = data.config || {};
  const dualRW = data.dual_read_write || {};

  return (
    <Card className="bg-zinc-900 border-zinc-800" data-testid="crypto-status-card">
      <CardHeader className="pb-2 pt-4 px-4">
        <CardTitle className="text-xs font-medium text-zinc-400 uppercase tracking-wider flex items-center gap-2">
          <Lock className="h-3.5 w-3.5" /> SEC-002 Crypto Engine
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-3">
        <div className="flex items-center gap-3">
          <Badge
            variant="outline"
            className={`text-[10px] font-mono px-2 py-0 ${
              config.v2_enabled === "true"
                ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
                : "text-yellow-400 border-yellow-500/30 bg-yellow-500/10"
            }`}
          >
            {config.v2_enabled === "true" ? "V2 AKTIF" : "V1 (LEGACY)"}
          </Badge>
          <span className="text-xs text-zinc-500">
            Anahtar: <span className="text-zinc-300 font-mono">{config.key_version}</span>
          </span>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="flex items-center gap-1.5">
            <FileKey className="h-3 w-3 text-blue-400" />
            <span className="text-zinc-500">Yazma:</span>
            <span className="text-zinc-300 font-mono text-[10px]">{dualRW.write_format}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Database className="h-3 w-3 text-blue-400" />
            <span className="text-zinc-500">Okuma:</span>
            <span className="text-zinc-300 font-mono text-[10px]">{(dualRW.read_formats || []).length} format</span>
          </div>
        </div>

        <div className="flex items-center gap-2 text-[10px]">
          <span className="text-zinc-600">Master key:</span>
          {config.has_master_key ? (
            <CheckCircle className="h-3 w-3 text-emerald-400" />
          ) : (
            <AlertTriangle className="h-3 w-3 text-red-400" />
          )}
          <span className="text-zinc-600 ml-2">Previous key:</span>
          {config.has_previous_key ? (
            <CheckCircle className="h-3 w-3 text-emerald-400" />
          ) : (
            <span className="text-zinc-600">-</span>
          )}
          <span className="text-zinc-600 ml-2">Legacy key:</span>
          {config.has_legacy_key ? (
            <CheckCircle className="h-3 w-3 text-yellow-400" />
          ) : (
            <span className="text-zinc-600">-</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function CutoverMetricsCard({ data }) {
  if (!data) return <Skeleton className="h-32 bg-zinc-800" />;

  const cutover = data.cutover || {};
  const pct = cutover.migration_percentage || 0;
  const ready = cutover.cutover_ready;

  return (
    <Card className="bg-zinc-900 border-zinc-800" data-testid="crypto-cutover-card">
      <CardHeader className="pb-2 pt-4 px-4">
        <CardTitle className="text-xs font-medium text-zinc-400 uppercase tracking-wider flex items-center gap-2">
          <ArrowRight className="h-3.5 w-3.5" /> Migration Cutover
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-3">
        <div className="flex items-center gap-3">
          <span className="text-2xl font-bold font-mono text-zinc-100">{pct}%</span>
          <Badge
            variant="outline"
            className={`text-[10px] font-mono px-2 py-0 ${
              ready
                ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
                : "text-yellow-400 border-yellow-500/30 bg-yellow-500/10"
            }`}
          >
            {ready ? "CUTOVER HAZIR" : "MIGRATION GEREKLI"}
          </Badge>
        </div>

        {/* Progress bar */}
        <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ${
              pct >= 100 ? "bg-emerald-500" : pct >= 50 ? "bg-yellow-500" : "bg-red-500"
            }`}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>

        <div className="flex items-center justify-between text-[10px] text-zinc-500">
          <span>SYR1: <span className="text-emerald-400 font-mono">{data.totals?.syr1 || 0}</span></span>
          <span>AES-GCM: <span className="text-yellow-400 font-mono">{data.totals?.aes_gcm_legacy || 0}</span></span>
          <span>Diger: <span className="text-zinc-400 font-mono">{data.totals?.other_legacy || 0}</span></span>
          <span>Toplam: <span className="text-zinc-300 font-mono">{cutover.total_credential_fields || 0}</span></span>
        </div>

        <p className="text-[10px] text-zinc-600">{cutover.recommended_action}</p>
      </CardContent>
    </Card>
  );
}

function RotationPlanCard({ data }) {
  const [expanded, setExpanded] = useState(false);
  if (!data) return <Skeleton className="h-32 bg-zinc-800" />;

  const summary = data.summary || {};
  const items = data.items || [];

  return (
    <Card className="bg-zinc-900 border-zinc-800" data-testid="rotation-plan-card">
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium text-zinc-400 uppercase tracking-wider flex items-center gap-2">
            <RotateCcw className="h-3.5 w-3.5" /> Rotasyon Plani
          </CardTitle>
          {items.length > 0 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-zinc-500 hover:text-zinc-300 transition-colors"
              data-testid="rotation-plan-expand"
            >
              {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          )}
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-2">
        <div className="flex items-center gap-4 text-xs">
          <span className="text-zinc-500">
            Toplam: <span className="text-zinc-300 font-mono">{summary.total_secrets}</span>
          </span>
          {summary.urgent_rotations > 0 && (
            <span className="text-red-400">
              Acil: <span className="font-mono">{summary.urgent_rotations}</span>
            </span>
          )}
          {summary.recommended_rotations > 0 && (
            <span className="text-yellow-400">
              Onerilen: <span className="font-mono">{summary.recommended_rotations}</span>
            </span>
          )}
          <span className="text-emerald-400">
            OK: <span className="font-mono">{summary.ok}</span>
          </span>
        </div>

        {expanded && items.length > 0 && (
          <div className="space-y-1.5 pt-1">
            {items.map((item, i) => (
              <div key={i} className="flex items-center justify-between text-[10px] text-zinc-400 border-b border-zinc-800/50 pb-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono">{item.provider}</span>
                  <span className="text-zinc-600">/</span>
                  <span className="font-mono">{item.property_id}</span>
                </div>
                <div className="flex items-center gap-2">
                  {item.age_days !== null && (
                    <span className="text-zinc-600">{item.age_days} gun</span>
                  )}
                  <Badge
                    variant="outline"
                    className={`text-[9px] px-1.5 py-0 ${
                      item.severity === "critical"
                        ? "text-red-400 border-red-500/30"
                        : item.severity === "warning"
                        ? "text-yellow-400 border-yellow-500/30"
                        : "text-emerald-400 border-emerald-500/30"
                    }`}
                  >
                    {item.recommendation}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        )}

        {items.length === 0 && (
          <div className="text-xs text-zinc-600 py-1">
            Henuz yonetilen secret yok
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function SecurityOpsDashboard() {
  const [secretsStatus, setSecretsStatus] = useState(null);
  const [cryptoStatus, setCryptoStatus] = useState(null);
  const [cutoverMetrics, setCutoverMetrics] = useState(null);
  const [rotationPlan, setRotationPlan] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [secRes, cryptoRes, cutRes, rotRes] = await Promise.allSettled([
        axios.get("/ops/secrets/status"),
        axios.get("/ops/crypto/status"),
        axios.get("/ops/crypto/cutover-metrics"),
        axios.get("/ops/secrets/rotation-plan"),
      ]);
      if (secRes.status === "fulfilled") setSecretsStatus(secRes.value.data);
      if (cryptoRes.status === "fulfilled") setCryptoStatus(cryptoRes.value.data);
      if (cutRes.status === "fulfilled") setCutoverMetrics(cutRes.value.data);
      if (rotRes.status === "fulfilled") setRotationPlan(rotRes.value.data);
    } catch {
      toast.error("Guvenlik verisi yuklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  return (
    <div className="space-y-4" data-testid="security-ops-dashboard">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2">
            <Shield className="h-4 w-4 text-amber-400" />
            Security Operations
          </h3>
          <p className="text-[10px] text-zinc-600 mt-0.5">
            SEC-001 Secrets Management + SEC-002 Crypto Migration
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-xs text-zinc-500"
          onClick={fetchAll}
          disabled={loading}
          data-testid="security-refresh-btn"
        >
          <RefreshCw className={`h-3 w-3 mr-1 ${loading ? "animate-spin" : ""}`} />
          Yenile
        </Button>
      </div>

      {/* Top Row: Secrets + Crypto */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SecretHealthCard data={secretsStatus} />
        <CryptoStatusCard data={cryptoStatus} />
      </div>

      {/* Bottom Row: Cutover + Rotation */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <CutoverMetricsCard data={cutoverMetrics} />
        <RotationPlanCard data={rotationPlan} />
      </div>

      {/* Secret Rotation Operations Panel */}
      <RotationOpsPanel />

      {/* Field-Level Encryption Panel */}
      <FieldEncryptionPanel />
    </div>
  );
}
