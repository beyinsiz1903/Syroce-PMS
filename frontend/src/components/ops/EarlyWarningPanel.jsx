import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { AlertTriangle, TrendingUp, TrendingDown, Activity, Zap, Clock, Target, RefreshCw, ChevronRight, Gauge, Info, AlertCircle, CheckCircle2, Eye, Play, Square, Sparkles, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
const API = "";


// ── Mini Sparkline Component ─────────────────────────────────────────
const MiniSparkline = ({
  data,
  color = 'blue',
  height = 30
}) => {
  const {
    t
  } = useTranslation();
  if (!data || data.length === 0) return null;
  const values = data.map(d => d.value || 0);
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const points = values.map((v, i) => {
    const x = i / (values.length - 1) * 100;
    const y = height - (v - min) / range * (height - 4);
    return `${x},${y}`;
  }).join(' ');
  const colorMap = {
    blue: '#3b82f6',
    red: '#ef4444',
    green: '#22c55e',
    orange: '#f97316'
  };
  return <svg width="100%" height={height} className="overflow-visible">
      <polyline points={points} fill="none" stroke={colorMap[color] || colorMap.blue} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>;
};

// ── Confidence Badge ─────────────────────────────────────────────────
const ConfidenceBadge = ({
  confidence
}) => {
  const {
    t
  } = useTranslation();
  const getColor = c => {
    if (c >= 80) return 'bg-red-100 text-red-800 border-red-200';
    if (c >= 60) return 'bg-amber-100 text-amber-800 border-amber-200';
    return 'bg-yellow-100 text-yellow-800 border-yellow-200';
  };
  return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold border ${getColor(confidence)}`}>
      {confidence}%
    </span>;
};

// ── Warning Type Badge ───────────────────────────────────────────────
const WarningTypeBadge = ({
  type
}) => {
  const {
    t
  } = useTranslation();
  const typeMap = {
    'predictive.warning.degradation_likely': {
      label: 'Bozulma Riski',
      color: 'bg-red-100 text-red-800',
      icon: TrendingDown
    },
    'predictive.warning.failure_rate_rising': {
      label: 'Hata Artışı',
      color: 'bg-amber-100 text-amber-800',
      icon: TrendingUp
    },
    'predictive.warning.backlog_growth': {
      label: 'Backlog Artışı',
      color: 'bg-yellow-100 text-yellow-800',
      icon: Activity
    },
    'predictive.warning.dlq_spike': {
      label: 'DLQ Spike',
      color: 'bg-red-100 text-red-800',
      icon: AlertCircle
    },
    'predictive.warning.throttle_risk': {
      label: 'Throttle Riski',
      color: 'bg-amber-100 text-amber-800',
      icon: Clock
    },
    'predictive.warning.staleness_risk': {
      label: 'Sessizlik',
      color: 'bg-yellow-100 text-yellow-800',
      icon: Clock
    },
    'predictive.warning.recovery_expected': {
      label: 'İyileşme',
      color: 'bg-green-100 text-green-800',
      icon: CheckCircle2
    }
  };
  const config = typeMap[type] || {
    label: type,
    color: 'bg-gray-100 text-gray-800',
    icon: Info
  };
  const Icon = config.icon;
  return <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${config.color}`}>
      <Icon className="w-3 h-3" />
      {config.label}
    </span>;
};

// ── Health Indicator ─────────────────────────────────────────────────
const SystemHealthIndicator = ({
  health
}) => {
  const {
    t
  } = useTranslation();
  const healthMap = {
    healthy: {
      color: 'bg-green-500',
      label: 'Sağlıklı',
      textColor: 'text-green-700'
    },
    attention: {
      color: 'bg-yellow-500',
      label: 'Dikkat',
      textColor: 'text-yellow-700'
    },
    degraded: {
      color: 'bg-amber-500',
      label: 'Düşük',
      textColor: 'text-amber-700'
    },
    critical: {
      color: 'bg-red-500',
      label: 'Kritik',
      textColor: 'text-red-700'
    },
    unknown: {
      color: 'bg-gray-400',
      label: 'Bilinmiyor',
      textColor: 'text-gray-600'
    }
  };
  const h = healthMap[health] || healthMap.unknown;
  return <div className="flex items-center gap-2">
      <div className={`w-3 h-3 rounded-full ${h.color} animate-pulse`} />
      <span className={`text-sm font-semibold ${h.textColor}`}>{h.label}</span>
    </div>;
};

// ── Warning Card ─────────────────────────────────────────────────────
const WarningCard = ({
  warning,
  onViewDetails,
  onAction
}) => {
  const {
    t
  } = useTranslation();
  const severityBg = {
    critical: 'border-red-300 bg-red-50/80',
    warning: 'border-amber-300 bg-amber-50/80',
    info: 'border-blue-300 bg-blue-50/80'
  };
  return <div className={`border rounded-lg p-3 ${severityBg[warning.severity] || severityBg.warning} hover:shadow-md transition-shadow cursor-pointer`} onClick={() => onViewDetails && onViewDetails(warning)} data-testid={`warning-card-${warning.warning_type}`}>
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <WarningTypeBadge type={warning.warning_type} />
          <ConfidenceBadge confidence={warning.confidence} />
        </div>
        {warning.provider && warning.provider !== 'system' && <span className="text-xs bg-gray-200 px-2 py-0.5 rounded capitalize">{warning.provider}</span>}
      </div>

      <p className="text-sm text-gray-800 font-medium mb-2 line-clamp-2">{warning.reason}</p>

      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500 line-clamp-1">{warning.recommended_action}</p>
        {onViewDetails && <Button size="sm" variant="ghost" className="h-6 text-xs">
            <Eye className="w-3 h-3 mr-1" />
            Detay
          </Button>}
      </div>
      {onAction && <ActionCTA warning={warning} onAction={onAction} />}
    </div>;
};

// ── Recommended Action CTAs ──────────────────────────────────────────
const ActionCTA = ({
  warning,
  onAction
}) => {
  const getActions = warningType => {
    const actionMap = {
      'predictive.warning.degradation_likely': [{
        label: 'Timeline İncele',
        action: 'inspect_timeline',
        icon: Eye
      }, {
        label: 'Connector Filtrele',
        action: 'filter_connector',
        icon: Target
      }],
      'predictive.warning.failure_rate_rising': [{
        label: 'Timeline İncele',
        action: 'inspect_timeline',
        icon: Eye
      }, {
        label: 'Connector Filtrele',
        action: 'filter_connector',
        icon: Target
      }],
      'predictive.warning.backlog_growth': [{
        label: 'Backlog Aç',
        action: 'open_backlog',
        icon: Activity
      }, {
        label: 'Queue İncele',
        action: 'force_queue_review',
        icon: RefreshCw
      }],
      'predictive.warning.dlq_spike': [{
        label: 'DLQ İncele',
        action: 'open_backlog',
        icon: AlertCircle
      }, {
        label: 'Manuel Retry',
        action: 'force_queue_review',
        icon: RefreshCw
      }],
      'predictive.warning.throttle_risk': [{
        label: 'Connector Filtrele',
        action: 'filter_connector',
        icon: Target
      }, {
        label: 'Rate Limit Gör',
        action: 'inspect_timeline',
        icon: Clock
      }],
      'predictive.warning.staleness_risk': [{
        label: 'Connector İncele',
        action: 'filter_connector',
        icon: Target
      }, {
        label: 'Timeline Aç',
        action: 'inspect_timeline',
        icon: Eye
      }],
      'predictive.warning.recovery_expected': [{
        label: 'Durumu Gör',
        action: 'filter_connector',
        icon: CheckCircle2
      }]
    };
    return actionMap[warningType] || [{
      label: 'Detay',
      action: 'inspect_timeline',
      icon: Eye
    }];
  };
  const actions = getActions(warning.warning_type);
  return <div className="flex items-center gap-1.5 mt-2">
      {actions.map((act, i) => {
      const Icon = act.icon;
      return <Button key={act.id || i} variant="outline" size="sm" className="h-6 text-[11px] px-2 bg-white hover:bg-blue-50" onClick={e => {
        e.stopPropagation();
        onAction && onAction(act.action, warning);
      }}>
            <Icon className="w-3 h-3 mr-1" />
            {act.label}
          </Button>;
    })}
    </div>;
};

// ── Main Early Warning Panel ─────────────────────────────────────────
const EarlyWarningPanel = ({
  onViewConnector,
  onOpenTimeline,
  onOpenBacklog
}) => {
  const {
    t
  } = useTranslation();
  const [summary, setSummary] = useState(null);
  const [trends, setTrends] = useState(null);
  const [engineStatus, setEngineStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedWarning, setSelectedWarning] = useState(null);
  const fetchSummary = useCallback(async () => {
    try {
      const resp = await axios.get(`/ops-events/early-warnings/summary`);
      setSummary(resp.data);
    } catch (err) {
      console.error('Early warning summary fetch error:', err);
    }
  }, []);
  const fetchTrends = useCallback(async () => {
    try {
      const resp = await axios.get(`/ops-events/early-warnings/trends?hours=6`);
      setTrends(resp.data);
    } catch (err) {
      console.error('Trends fetch error:', err);
    }
  }, []);
  const fetchEngineStatus = useCallback(async () => {
    try {
      const resp = await axios.get(`/ops-events/early-warnings/engine/status`);
      setEngineStatus(resp.data);
    } catch (err) {
      console.error('Engine status fetch error:', err);
    }
  }, []);
  const toggleEngine = async () => {
    try {
      const endpoint = engineStatus?.running ? 'stop' : 'start';
      await axios.post(`/ops-events/early-warnings/engine/${endpoint}`, {});
      await fetchEngineStatus();
    } catch (err) {
      console.error('Engine toggle error:', err);
    }
  };
  const forceCheck = async () => {
    setRefreshing(true);
    try {
      await axios.post(`/ops-events/early-warnings/force-check`, {});
      await fetchSummary();
    } catch (err) {
      console.error('Force check error:', err);
    } finally {
      setRefreshing(false);
    }
  };
  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await Promise.all([fetchSummary(), fetchTrends(), fetchEngineStatus()]);
      setLoading(false);
    };
    load();

    // Auto-refresh every 30 seconds
    const interval = setInterval(() => {
      fetchSummary();
      fetchTrends();
    }, 30000);
    return () => clearInterval(interval);
  }, [fetchSummary, fetchTrends, fetchEngineStatus]);
  if (loading) {
    return <Card data-testid="early-warning-panel-loading">
        <CardContent className="flex items-center justify-center py-8">
          <RefreshCw className="w-5 h-5 animate-spin text-blue-500 mr-2" />
          <span className="text-gray-500">{t('cm.components_ops_EarlyWarningPanel.erken_uyarilar_yukleniyor')}</span>
        </CardContent>
      </Card>;
  }
  const handleWarningAction = (action, warning) => {
    switch (action) {
      case 'inspect_timeline':
        if (warning.connector_id && onOpenTimeline) {
          onOpenTimeline(warning.connector_id);
        } else if (warning.provider && onViewConnector) {
          onViewConnector(warning.provider);
        }
        break;
      case 'filter_connector':
        if (warning.provider && onViewConnector) {
          onViewConnector(warning.provider);
        }
        break;
      case 'open_backlog':
      case 'force_queue_review':
        if (onOpenBacklog) {
          onOpenBacklog();
        }
        break;
      default:
        break;
    }
  };
  const topWarnings = summary?.top_warnings || [];
  const failureRateSeries = trends?.failure_rate_series || [];
  return <div className="space-y-4" data-testid="early-warning-panel">
      {/* Header Card */}
      <Card className="bg-gradient-to-r from-indigo-50 to-blue-50 border-indigo-200">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-indigo-600" />
              {t('cm.components_ops_EarlyWarningPanel.erken_uyari_sistemi_v1')}
            </CardTitle>
            <div className="flex items-center gap-2">
              <SystemHealthIndicator health={summary?.system_health_indicator || 'unknown'} />
              <Button variant="outline" size="sm" onClick={forceCheck} disabled={refreshing} data-testid="force-check-btn">
                <RefreshCw className={`w-3 h-3 mr-1 ${refreshing ? 'animate-spin' : ''}`} />
                Kontrol Et
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {/* KPI Row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="bg-white rounded-lg p-3 border shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500 uppercase">{t('cm.components_ops_EarlyWarningPanel.toplam_uyari')}</span>
                <Target className="w-4 h-4 text-indigo-500" />
              </div>
              <p className="text-2xl font-bold text-gray-900">{summary?.warning_count || 0}</p>
            </div>
            
            <div className="bg-white rounded-lg p-3 border shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500 uppercase">Kritik</span>
                <AlertCircle className="w-4 h-4 text-red-500" />
              </div>
              <p className="text-2xl font-bold text-red-600">{summary?.critical_count || 0}</p>
            </div>
            
            <div className="bg-white rounded-lg p-3 border shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500 uppercase">{t('cm.components_ops_EarlyWarningPanel.uyari')}</span>
                <AlertTriangle className="w-4 h-4 text-amber-500" />
              </div>
              <p className="text-2xl font-bold text-amber-600">{summary?.warning_count_warning || 0}</p>
            </div>
            
            <div className="bg-white rounded-lg p-3 border shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500 uppercase">{t('cm.components_ops_EarlyWarningPanel.risk_altinda')}</span>
                <Gauge className="w-4 h-4 text-blue-500" />
              </div>
              <p className="text-2xl font-bold text-blue-600">{summary?.connectors_at_risk_count || 0}</p>
              <p className="text-xs text-gray-500 mt-0.5">connector</p>
            </div>
          </div>

          {/* Trend Sparkline */}
          {failureRateSeries.length > 0 && <div className="bg-white rounded-lg p-3 border shadow-sm mb-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-500 uppercase">{t('cm.components_ops_EarlyWarningPanel.hata_orani_trendi_son_6_saat')}</span>
                <div className="flex items-center gap-1 text-xs text-gray-500">
                  <span>{t('cm.components_ops_EarlyWarningPanel.su_an')}</span>
                  <span className={`font-bold ${failureRateSeries[failureRateSeries.length - 1]?.value > 10 ? 'text-red-600' : 'text-green-600'}`}>
                    %{failureRateSeries[failureRateSeries.length - 1]?.value || 0}
                  </span>
                </div>
              </div>
              <MiniSparkline data={failureRateSeries} color={failureRateSeries[failureRateSeries.length - 1]?.value > 10 ? 'red' : 'blue'} height={40} />
            </div>}

          {/* Connectors at Risk */}
          {summary?.connectors_at_risk && summary.connectors_at_risk.length > 0 && <div className="flex items-center gap-2 mb-4">
              <span className="text-xs text-gray-500">{t('cm.components_ops_EarlyWarningPanel.risk_altindaki_connector_lar')}</span>
              {summary.connectors_at_risk.map(prov => <Badge key={prov} variant="outline" className="bg-amber-50 border-amber-300 text-amber-800 capitalize cursor-pointer hover:bg-amber-100" onClick={() => onViewConnector && onViewConnector(prov)}>
                  {prov}
                </Badge>)}
            </div>}

          {/* Engine Status */}
          <div className="flex items-center justify-between bg-gray-50 rounded-lg p-2 text-xs">
            <div className="flex items-center gap-2">
              <Zap className={`w-4 h-4 ${engineStatus?.running ? 'text-green-500' : 'text-gray-400'}`} />
              <span className="text-gray-600">
                Arka Plan Motoru: {engineStatus?.running ? 'Çalışıyor' : 'Durdu'}
              </span>
              {engineStatus?.running && <span className="text-gray-400">(her {engineStatus.check_interval_seconds || 300}s)</span>}
            </div>
            <Button variant="ghost" size="sm" className="h-6 text-xs" onClick={toggleEngine} data-testid="toggle-engine-btn">
              {engineStatus?.running ? <><Square className="w-3 h-3 mr-1" /> Durdur</> : <><Play className="w-3 h-3 mr-1" /> {t('cm.components_ops_EarlyWarningPanel.baslat')}</>}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Top Warnings List */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center justify-between">
            <span className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              {t('cm.components_ops_EarlyWarningPanel.aktif_erken_uyarilar')}
            </span>
            <Badge variant="outline">{topWarnings.length} {t('cm.components_ops_EarlyWarningPanel.uyari_fa6d4')}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {topWarnings.length === 0 ? <div className="text-center py-8 text-gray-500">
              <CheckCircle2 className="w-10 h-10 mx-auto mb-2 text-green-500 opacity-50" />
              <p className="text-sm">{t('cm.components_ops_EarlyWarningPanel.aktif_erken_uyari_yok')}</p>
              <p className="text-xs text-gray-400 mt-1">{t('cm.components_ops_EarlyWarningPanel.sistem_saglikli_gorunuyor')}</p>
            </div> : <div className="space-y-3">
              {topWarnings.map((warning, idx) => <WarningCard key={`${warning.warning_type}-${warning.provider}-${idx}`} warning={warning} onViewDetails={setSelectedWarning} onAction={handleWarningAction} />)}
            </div>}
        </CardContent>
      </Card>

      {/* Warning Detail Modal (simple inline expansion) */}
      {selectedWarning && <Card className="border-blue-300 bg-blue-50/50">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm flex items-center gap-2">
                <Info className="w-4 h-4 text-blue-500" />
                {t('cm.components_ops_EarlyWarningPanel.uyari_detayi')}
              </CardTitle>
              <Button variant="ghost" size="sm" onClick={() => setSelectedWarning(null)}>
                <X className="w-4 h-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="text-xs space-y-2">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <span className="text-gray-500">Tip:</span>
                <WarningTypeBadge type={selectedWarning.warning_type} />
              </div>
              <div>
                <span className="text-gray-500">{t('cm.components_ops_EarlyWarningPanel.guven')}</span>
                <ConfidenceBadge confidence={selectedWarning.confidence} />
              </div>
              <div>
                <span className="text-gray-500">Provider:</span>
                <span className="font-medium capitalize">{selectedWarning.provider || 'Sistem'}</span>
              </div>
              <div>
                <span className="text-gray-500">Seviye:</span>
                <span className={`font-medium ${selectedWarning.severity === 'critical' ? 'text-red-600' : 'text-amber-600'}`}>
                  {selectedWarning.severity}
                </span>
              </div>
            </div>
            <div>
              <span className="text-gray-500 block mb-1">Neden:</span>
              <p className="bg-white p-2 rounded border text-gray-800">{selectedWarning.reason}</p>
            </div>
            <div>
              <span className="text-gray-500 block mb-1">{t('cm.components_ops_EarlyWarningPanel.onerilen_aksiyon')}</span>
              <p className="bg-white p-2 rounded border text-gray-800">{selectedWarning.recommended_action}</p>
            </div>
            <div>
              <span className="text-gray-500 block mb-1">{t('cm.components_ops_EarlyWarningPanel.etki_alani')}</span>
              <p className="bg-white p-2 rounded border text-gray-800">{selectedWarning.impacted_scope}</p>
            </div>
            {selectedWarning.trend_data && Object.keys(selectedWarning.trend_data).length > 0 && <details>
                <summary className="text-gray-500 cursor-pointer hover:text-gray-700">Trend Verileri</summary>
                <pre className="mt-1 p-2 bg-white rounded border text-[10px] overflow-x-auto">
                  {JSON.stringify(selectedWarning.trend_data, null, 2)}
                </pre>
              </details>}
          </CardContent>
        </Card>}
    </div>;
};
export default EarlyWarningPanel;