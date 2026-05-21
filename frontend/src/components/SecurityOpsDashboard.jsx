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
import { useTranslation } from 'react-i18next';

function SecretHealthCard({ data }) {
  const { t } = useTranslation();
  if (!data) return <Skeleton className="h-40 bg-gray-100" />;

  const health = data.health || {};
  const config = data.config || {};
  const isHealthy = health.status === "healthy" || health.provider;

  return (
    <Card className="bg-white border-gray-200" data-testid="secrets-health-card">
      <CardHeader className="pb-2 pt-4 px-4">
        <CardTitle className="text-xs font-medium text-gray-600 uppercase tracking-wider flex items-center gap-2">
          <Key className="h-3.5 w-3.5" /> {t('cm.components_SecurityOpsDashboard.sec_001_secrets_yonetimi')}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-3">
        <div className="flex items-center gap-3">
          <Badge
            variant="outline"
            className={`text-[10px] font-mono px-2 py-0 ${
              isHealthy
                ? "text-emerald-600 border-emerald-500/30 bg-emerald-500/10"
                : "text-red-600 border-red-500/30 bg-red-500/10"
            }`}
          >
            {isHealthy ? "SAGLIKLI" : "SORUNLU"}
          </Badge>
          <span className="text-xs text-gray-500">
            Provider: <span className="text-gray-700 font-mono">{config.provider}</span>
          </span>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="flex items-center gap-1.5">
            {config.legacy_fallback === "true" ? (
              <Unlock className="h-3 w-3 text-amber-600" />
            ) : (
              <Lock className="h-3 w-3 text-emerald-600" />
            )}
            <span className="text-gray-500">Legacy Fallback:</span>
            <span className={config.legacy_fallback === "true" ? "text-amber-600" : "text-emerald-600"}>
              {config.legacy_fallback === "true" ? "AKTIF" : "KAPALI"}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <Shield className="h-3 w-3 text-blue-600" />
            <span className="text-gray-500">Audit:</span>
            <span className={config.audit_enabled === "true" ? "text-emerald-600" : "text-gray-500"}>
              {config.audit_enabled === "true" ? "AKTIF" : "KAPALI"}
            </span>
          </div>
        </div>

        {/* Audit Stats */}
        <div className="flex items-center gap-4 text-[10px] text-gray-500">
          {Object.entries(data.audit_24h || {}).map(([action, count]) => (
            <span key={action}>
              {action}: <span className="text-gray-600 font-mono">{count}</span>
            </span>
          ))}
        </div>

        {data.anomalies_24h > 0 && (
          <div className="flex items-center gap-2 text-xs text-red-600 bg-red-500/10 border border-red-500/20 rounded px-2 py-1">
            <AlertTriangle className="h-3 w-3" />
            <span>{data.anomalies_24h} anomali (son 24 saat)</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function CryptoStatusCard({ data }) {
  if (!data) return <Skeleton className="h-40 bg-gray-100" />;

  const config = data.config || {};
  const dualRW = data.dual_read_write || {};

  return (
    <Card className="bg-white border-gray-200" data-testid="crypto-status-card">
      <CardHeader className="pb-2 pt-4 px-4">
        <CardTitle className="text-xs font-medium text-gray-600 uppercase tracking-wider flex items-center gap-2">
          <Lock className="h-3.5 w-3.5" /> SEC-002 Crypto Engine
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-3">
        <div className="flex items-center gap-3">
          <Badge
            variant="outline"
            className={`text-[10px] font-mono px-2 py-0 ${
              config.v2_enabled === "true"
                ? "text-emerald-600 border-emerald-500/30 bg-emerald-500/10"
                : "text-amber-600 border-yellow-500/30 bg-yellow-500/10"
            }`}
          >
            {config.v2_enabled === "true" ? "V2 AKTIF" : "V1 (LEGACY)"}
          </Badge>
          <span className="text-xs text-gray-500">
            Anahtar: <span className="text-gray-700 font-mono">{config.key_version}</span>
          </span>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="flex items-center gap-1.5">
            <FileKey className="h-3 w-3 text-blue-600" />
            <span className="text-gray-500">Yazma:</span>
            <span className="text-gray-700 font-mono text-[10px]">{dualRW.write_format}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Database className="h-3 w-3 text-blue-600" />
            <span className="text-gray-500">Okuma:</span>
            <span className="text-gray-700 font-mono text-[10px]">{(dualRW.read_formats || []).length} format</span>
          </div>
        </div>

        <div className="flex items-center gap-2 text-[10px]">
          <span className="text-gray-500">Master key:</span>
          {config.has_master_key ? (
            <CheckCircle className="h-3 w-3 text-emerald-600" />
          ) : (
            <AlertTriangle className="h-3 w-3 text-red-600" />
          )}
          <span className="text-gray-500 ml-2">Previous key:</span>
          {config.has_previous_key ? (
            <CheckCircle className="h-3 w-3 text-emerald-600" />
          ) : (
            <span className="text-gray-500">-</span>
          )}
          <span className="text-gray-500 ml-2">Legacy key:</span>
          {config.has_legacy_key ? (
            <CheckCircle className="h-3 w-3 text-amber-600" />
          ) : (
            <span className="text-gray-500">-</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function CutoverMetricsCard({ data }) {
  const { t } = useTranslation();
  if (!data) return <Skeleton className="h-32 bg-gray-100" />;

  const cutover = data.cutover || {};
  const pct = cutover.migration_percentage || 0;
  const ready = cutover.cutover_ready;

  return (
    <Card className="bg-white border-gray-200" data-testid="crypto-cutover-card">
      <CardHeader className="pb-2 pt-4 px-4">
        <CardTitle className="text-xs font-medium text-gray-600 uppercase tracking-wider flex items-center gap-2">
          <ArrowRight className="h-3.5 w-3.5" /> Migration Cutover
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-3">
        <div className="flex items-center gap-3">
          <span className="text-2xl font-bold font-mono text-gray-900">{pct}%</span>
          <Badge
            variant="outline"
            className={`text-[10px] font-mono px-2 py-0 ${
              ready
                ? "text-emerald-600 border-emerald-500/30 bg-emerald-500/10"
                : "text-amber-600 border-yellow-500/30 bg-yellow-500/10"
            }`}
          >
            {ready ? "CUTOVER HAZIR" : "MIGRATION GEREKLI"}
          </Badge>
        </div>

        {/* Progress bar */}
        <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ${
              pct >= 100 ? "bg-emerald-500" : pct >= 50 ? "bg-yellow-500" : "bg-red-500"
            }`}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>

        <div className="flex items-center justify-between text-[10px] text-gray-500">
          <span>SYR1: <span className="text-emerald-600 font-mono">{data.totals?.syr1 || 0}</span></span>
          <span>AES-GCM: <span className="text-amber-600 font-mono">{data.totals?.aes_gcm_legacy || 0}</span></span>
          <span>Diger: <span className="text-gray-600 font-mono">{data.totals?.other_legacy || 0}</span></span>
          <span>{t('cm.components_SecurityOpsDashboard.toplam')} <span className="text-gray-700 font-mono">{cutover.total_credential_fields || 0}</span></span>
        </div>

        <p className="text-[10px] text-gray-500">{cutover.recommended_action}</p>
      </CardContent>
    </Card>
  );
}

function RotationPlanCard({ data }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  if (!data) return <Skeleton className="h-32 bg-gray-100" />;

  const summary = data.summary || {};
  const items = data.items || [];

  return (
    <Card className="bg-white border-gray-200" data-testid="rotation-plan-card">
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium text-gray-600 uppercase tracking-wider flex items-center gap-2">
            <RotateCcw className="h-3.5 w-3.5" /> Rotasyon Plani
          </CardTitle>
          {items.length > 0 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-gray-500 hover:text-gray-700 transition-colors"
              data-testid="rotation-plan-expand"
            >
              {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          )}
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-2">
        <div className="flex items-center gap-4 text-xs">
          <span className="text-gray-500">
            {t('cm.components_SecurityOpsDashboard.toplam_68af4')} <span className="text-gray-700 font-mono">{summary.total_secrets}</span>
          </span>
          {summary.urgent_rotations > 0 && (
            <span className="text-red-600">
              Acil: <span className="font-mono">{summary.urgent_rotations}</span>
            </span>
          )}
          {summary.recommended_rotations > 0 && (
            <span className="text-amber-600">
              {t('cm.components_SecurityOpsDashboard.onerilen')} <span className="font-mono">{summary.recommended_rotations}</span>
            </span>
          )}
          <span className="text-emerald-600">
            OK: <span className="font-mono">{summary.ok}</span>
          </span>
        </div>

        {expanded && items.length > 0 && (
          <div className="space-y-1.5 pt-1">
            {items.map((item, i) => (
              <div key={i} className="flex items-center justify-between text-[10px] text-gray-600 border-b border-gray-200/50 pb-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono">{item.provider}</span>
                  <span className="text-gray-500">/</span>
                  <span className="font-mono">{item.property_id}</span>
                </div>
                <div className="flex items-center gap-2">
                  {item.age_days !== null && (
                    <span className="text-gray-500">{item.age_days} gun</span>
                  )}
                  <Badge
                    variant="outline"
                    className={`text-[9px] px-1.5 py-0 ${
                      item.severity === "critical"
                        ? "text-red-600 border-red-500/30"
                        : item.severity === "warning"
                        ? "text-amber-600 border-yellow-500/30"
                        : "text-emerald-600 border-emerald-500/30"
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
          <div className="text-xs text-gray-500 py-1">
            {t('cm.components_SecurityOpsDashboard.henuz_yonetilen_secret_yok')}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function SecurityOpsDashboard() {
  const { t } = useTranslation();
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
      toast.error("Güvenlik verisi yüklenemedi");
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
          <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
            <Shield className="h-4 w-4 text-amber-600" />
            Security Operations
          </h3>
          <p className="text-[10px] text-gray-500 mt-0.5">
            SEC-001 Secrets Management + SEC-002 Crypto Migration
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-xs text-gray-500"
          onClick={fetchAll}
          disabled={loading}
          data-testid="security-refresh-btn"
        >
          <RefreshCw className={`h-3 w-3 mr-1 ${loading ? "animate-spin" : ""}`} />
          {t('cm.components_SecurityOpsDashboard.yenile')}
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
