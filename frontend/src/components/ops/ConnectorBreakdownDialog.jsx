import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  RefreshCw,
  AlertTriangle,
  AlertCircle,
  CheckCircle2,
  Wifi,
  WifiOff,
  TrendingUp,
  Clock,
  Activity,
  Shield,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const RiskBadge = ({ risk }) => {
  const { t } = useTranslation();
  const map = {
    high: { color: 'bg-red-100 text-red-700 border-red-300', label: 'Yüksek' },
    medium: { color: 'bg-amber-100 text-amber-700 border-amber-300', label: 'Orta' },
    low: { color: 'bg-emerald-100 text-emerald-700 border-emerald-300', label: 'Düşük' },
  };
  const r = map[risk] || map.low;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${r.color}`}>
      {r.label}
    </span>
  );
};

const SeverityIcon = ({ severity }) => {
  if (severity === 'critical') return <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />;
  if (severity === 'warning') return <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0" />;
  return <CheckCircle2 className="w-4 h-4 text-emerald-500 flex-shrink-0" />;
};

/**
 * Tek connector için detaylı erken-uyarı, trend ve risk dökümü.
 * Backend: GET /ops-events/early-warnings/connector/{connector_id}
 */
const ConnectorBreakdownDialog = ({ open, connectorId, onClose }) => {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    if (!connectorId) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await axios.get(
        `/ops-events/early-warnings/connector/${connectorId}`,
        { headers: getAuthHeaders() }
      );
      setData(resp.data);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Connector dökümü alınamadı');
    } finally {
      setLoading(false);
    }
  }, [connectorId]);

  useEffect(() => {
    if (open && connectorId) fetchData();
    if (!open) {
      setData(null);
      setError(null);
    }
  }, [open, connectorId, fetchData]);

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="connector-breakdown-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {data?.status === 'healthy' || data?.risk_assessment?.overall_risk === 'low' ? (
              <Wifi className="w-5 h-5 text-emerald-600" />
            ) : (
              <WifiOff className="w-5 h-5 text-rose-600" />
            )}
            <span className="capitalize">{data?.provider || 'Connector'} {t('cm.components_ops_ConnectorBreakdownDialog.detayi')}</span>
            {data?.property_name && (
              <span className="text-sm font-normal text-slate-500">— {data.property_name}</span>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="ml-auto h-7"
              onClick={fetchData}
              disabled={loading}
              data-testid="connector-breakdown-refresh"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          </DialogTitle>
        </DialogHeader>

        {loading && !data && (
          <div className="flex items-center justify-center py-10 text-slate-500">
            <RefreshCw className="w-5 h-5 animate-spin mr-2" />
            {t('cm.components_ops_ConnectorBreakdownDialog.yukleniyor')}
          </div>
        )}

        {error && (
          <div className="bg-rose-50 border border-rose-200 text-rose-700 rounded-md p-3 text-sm">
            {error}
          </div>
        )}

        {data && !loading && (
          <div className="space-y-4">
            {/* Risk Özeti */}
            <div className="flex items-center justify-between bg-slate-50 rounded-lg p-3 border">
              <div className="flex items-center gap-3">
                <Shield className="w-5 h-5 text-slate-600" />
                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wider">Genel Risk</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <RiskBadge risk={data.risk_assessment?.overall_risk} />
                    <span className="text-xs text-slate-500">
                      {t('cm.components_ops_ConnectorBreakdownDialog.maks_guven')} <strong>%{data.risk_assessment?.max_confidence ?? 0}</strong>
                    </span>
                  </div>
                </div>
              </div>
              <div className="text-right">
                <p className="text-xs text-slate-500 uppercase tracking-wider">{t('cm.components_ops_ConnectorBreakdownDialog.aktif_uyari')}</p>
                <p className="text-2xl font-bold text-slate-900">{data.warning_count || 0}</p>
              </div>
            </div>

            {/* Aktif Uyarılar */}
            <div>
              <h4 className="text-sm font-semibold text-slate-700 mb-2 flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4 text-amber-500" />
                {t('cm.components_ops_ConnectorBreakdownDialog.aktif_uyarilar')}
              </h4>
              {(data.warnings || []).length === 0 ? (
                <div className="text-center py-6 text-slate-500 bg-emerald-50/50 rounded-md border border-emerald-200">
                  <CheckCircle2 className="w-7 h-7 mx-auto mb-1.5 text-emerald-500 opacity-70" />
                  <p className="text-sm">{t('cm.components_ops_ConnectorBreakdownDialog.bu_connector_icin_aktif_uyari_yok')}</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {(data.warnings || []).map((w, i) => (
                    <div
                      key={w.id || i}
                      className={`border rounded-md p-2.5 text-sm flex items-start gap-2 ${
                        w.severity === 'critical' ? 'bg-rose-50 border-rose-200' : 'bg-amber-50 border-amber-200'
                      }`}
                      data-testid={`breakdown-warning-${i}`}
                    >
                      <SeverityIcon severity={w.severity} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <p className="font-medium text-slate-900 truncate">{w.reason || w.title}</p>
                          {w.confidence != null && (
                            <Badge variant="outline" className="text-[10px] flex-shrink-0">
                              %{w.confidence}
                            </Badge>
                          )}
                        </div>
                        {w.description && (
                          <p className="text-xs text-slate-600 mt-0.5">{w.description}</p>
                        )}
                        {w.metric && (
                          <p className="text-[11px] text-slate-500 mt-1">
                            <span className="font-mono bg-white px-1.5 py-0.5 rounded border">{w.metric}</span>
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Trend Özetleri */}
            <div>
              <h4 className="text-sm font-semibold text-slate-700 mb-2 flex items-center gap-1.5">
                <TrendingUp className="w-4 h-4 text-indigo-500" />
                {t('cm.components_ops_ConnectorBreakdownDialog.trend_ozeti')}
              </h4>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-white border rounded-md p-2.5">
                  <p className="text-slate-500 uppercase tracking-wider text-[10px]">{t('cm.components_ops_ConnectorBreakdownDialog.hata_orani')}</p>
                  <p className="text-base font-bold text-slate-900 mt-0.5">
                    %{data.trends?.failure_rate?.current ?? data.trends?.failure_rate?.latest ?? 0}
                  </p>
                  {data.trends?.failure_rate?.trend && (
                    <p className="text-[10px] text-slate-500 mt-0.5">{t('cm.components_ops_ConnectorBreakdownDialog.yon')} {data.trends.failure_rate.trend}</p>
                  )}
                </div>
                <div className="bg-white border rounded-md p-2.5">
                  <p className="text-slate-500 uppercase tracking-wider text-[10px]">{t('cm.components_ops_ConnectorBreakdownDialog.saglik_skoru')}</p>
                  <p className="text-base font-bold text-slate-900 mt-0.5">
                    {data.trends?.health_score?.current ?? data.trends?.health_score?.latest ?? '—'}
                  </p>
                </div>
                <div className="bg-white border rounded-md p-2.5">
                  <p className="text-slate-500 uppercase tracking-wider text-[10px] flex items-center gap-1">
                    <Clock className="w-3 h-3" /> {t('cm.components_ops_ConnectorBreakdownDialog.son_basari')}
                  </p>
                  <p className="text-xs text-slate-700 mt-0.5">
                    {data.trends?.staleness?.last_success_at
                      ? new Date(data.trends.staleness.last_success_at).toLocaleString('tr-TR')
                      : '—'}
                  </p>
                </div>
                <div className="bg-white border rounded-md p-2.5">
                  <p className="text-slate-500 uppercase tracking-wider text-[10px] flex items-center gap-1">
                    <Activity className="w-3 h-3" /> Throttle
                  </p>
                  <p className="text-base font-bold text-slate-900 mt-0.5">
                    {data.trends?.throttle?.events_24h ?? data.trends?.throttle?.count ?? 0}
                  </p>
                </div>
              </div>
            </div>

            <div className="text-[10px] text-slate-400 text-right border-t pt-2">
              {t('cm.components_ops_ConnectorBreakdownDialog.uretildi')} {data.generated_at ? new Date(data.generated_at).toLocaleString('tr-TR') : '—'}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default ConnectorBreakdownDialog;
