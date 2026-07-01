import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  AlertTriangle, CheckCircle, XCircle, RotateCcw,
  Eye, Shield, RefreshCw, Loader2, Clock, Filter,
  ChevronDown, ChevronRight, MessageSquare, Zap,
  ArrowUpRight, Archive, Search
} from 'lucide-react';

const API = "";

// ─── Severity Config ─────────────────────────────────────────
const SEVERITY_CONFIG = {
  critical: { color: 'bg-red-500/15 text-red-400 border-red-500/30', dot: 'bg-red-500 animate-pulse' },
  high: { color: 'bg-amber-500/15 text-amber-400 border-amber-500/30', dot: 'bg-amber-500' },
  medium: { color: 'bg-amber-500/15 text-amber-400 border-amber-500/30', dot: 'bg-amber-500' },
  low: { color: 'bg-slate-100 text-slate-600 border-slate-300', dot: 'bg-slate-300' },
  P1: { color: 'bg-red-500/15 text-red-400 border-red-500/30', dot: 'bg-red-500 animate-pulse' },
  P2: { color: 'bg-amber-500/15 text-amber-400 border-amber-500/30', dot: 'bg-amber-500' },
  P3: { color: 'bg-amber-500/15 text-amber-400 border-amber-500/30', dot: 'bg-amber-500' },
  P4: { color: 'bg-slate-100 text-slate-600 border-slate-300', dot: 'bg-slate-300' },
};

const STATUS_CONFIG = {
  open: { color: 'bg-red-500/15 text-red-400', label: 'Açık' },
  investigating: { color: 'bg-amber-500/15 text-amber-400', label: 'İnceleniyor' },
  resolved: { color: 'bg-emerald-500/15 text-emerald-400', label: 'Çözüldü' },
  suppressed: { color: 'bg-slate-100 text-slate-500', label: 'Bastırıldı' },
};

// ─── Summary Cards ───────────────────────────────────────────
const SummaryCard = ({ label, value, icon: Icon, accent, testId }) => (
  <Card data-testid={testId} className="bg-white border-slate-200">
    <CardContent className="p-4 flex items-center gap-3">
      <div className={`p-2 rounded-lg ${accent}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-xs text-slate-500 font-medium">{label}</p>
        <p className="text-xl font-bold text-slate-900">{value}</p>
      </div>
    </CardContent>
  </Card>
);

// ─── Incident Row ────────────────────────────────────────────
const IncidentRow = ({ incident, onAction, expanded, onToggle }) => {
  const sev = SEVERITY_CONFIG[incident.severity] || SEVERITY_CONFIG.medium;
  const stat = STATUS_CONFIG[incident.status] || STATUS_CONFIG.open;
  const isOpen = incident.status === 'open' || incident.status === 'investigating';

  return (
    <div data-testid={`incident-row-${incident.id}`} className="border-b border-slate-200 last:border-0">
      <div
        className="flex items-center gap-3 px-4 py-3 hover:bg-slate-50 cursor-pointer transition-colors"
        onClick={onToggle}
      >
        {expanded ? <ChevronDown className="w-4 h-4 text-slate-500" /> : <ChevronRight className="w-4 h-4 text-slate-500" />}
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${sev.dot}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-800 truncate">
              {(incident.issue_type || incident.case_type || incident.drift_type || 'Bilinmiyor').replace(/_/g, ' ')}
            </span>
            <Badge className={`${sev.color} border text-[10px] px-1.5`}>
              {incident.severity || 'medium'}
            </Badge>
            <Badge className={`${stat.color} text-[10px] px-1.5`}>
              {stat.label}
            </Badge>
          </div>
          <div className="flex items-center gap-3 mt-0.5 text-xs text-slate-500">
            {incident.provider && <span>{incident.provider}</span>}
            {incident.external_reservation_id && (
              <span>Res: {incident.external_reservation_id}</span>
            )}
            {incident.room_type_code && <span>Oda: {incident.room_type_code}</span>}
            {incident.created_at && (
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {new Date(incident.created_at).toLocaleString('tr-TR')}
              </span>
            )}
          </div>
        </div>
        {isOpen && (
          <div className="flex items-center gap-1 flex-shrink-0">
            {incident.can_auto_heal && (
              <Button
                data-testid={`incident-retry-${incident.id}`}
                size="sm" variant="ghost"
                className="h-7 px-2 text-amber-400 hover:text-amber-300 hover:bg-amber-500/10"
                onClick={e => { e.stopPropagation(); onAction(incident.id, 'retry'); }}
              >
                <RotateCcw className="w-3.5 h-3.5 mr-1" /> Tekrarla
              </Button>
            )}
            <Button
              data-testid={`incident-resolve-${incident.id}`}
              size="sm" variant="ghost"
              className="h-7 px-2 text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10"
              onClick={e => { e.stopPropagation(); onAction(incident.id, 'resolve'); }}
            >
              <CheckCircle className="w-3.5 h-3.5 mr-1" /> Çöz
            </Button>
            <Button
              data-testid={`incident-suppress-${incident.id}`}
              size="sm" variant="ghost"
              className="h-7 px-2 text-slate-500 hover:text-slate-600 hover:bg-slate-100"
              onClick={e => { e.stopPropagation(); onAction(incident.id, 'suppress'); }}
            >
              <Archive className="w-3.5 h-3.5 mr-1" /> Bastır
            </Button>
          </div>
        )}
      </div>
      {expanded && (
        <div className="px-10 pb-4 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <div>
              <span className="text-slate-500 block">Önerilen</span>
              <span className="text-slate-700 font-medium">
                {incident.recommended_action?.replace(/_/g, ' ') || '-'}
              </span>
            </div>
            <div>
              <span className="text-slate-500 block">Altın Kaynak</span>
              <span className="text-slate-700 font-medium">{incident.gold_source || '-'}</span>
            </div>
            <div>
              <span className="text-slate-500 block">Otomatik Düzeltme</span>
              <span className={`font-medium ${incident.can_auto_heal ? 'text-emerald-400' : 'text-slate-500'}`}>
                {incident.can_auto_heal ? 'Evet' : 'Hayır'}
              </span>
            </div>
            <div>
              <span className="text-slate-500 block">Son İşlem</span>
              <span className="text-slate-700 font-medium">{incident.last_action || '-'}</span>
            </div>
          </div>
          {incident.auto_heal_description && (
            <div className="text-xs text-slate-500 bg-slate-50 p-2 rounded">
              <Zap className="w-3 h-3 inline mr-1 text-amber-400" />
              {incident.auto_heal_description}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ─── Main Component ──────────────────────────────────────────
export default function OperatorIncidentPanel({ user, tenant, onLogout }) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [summary, setSummary] = useState(null);
  const [incidents, setIncidents] = useState([]);
  const [total, setTotal] = useState(0);
  const [expandedId, setExpandedId] = useState(null);
  const [filter, setFilter] = useState({ status: '', severity: '', provider: '' });

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const fetchData = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (filter.status) params.append('status', filter.status);
      if (filter.severity) params.append('severity', filter.severity);
      if (filter.provider) params.append('provider', filter.provider);
      params.append('limit', '50');

      const [sumRes, listRes] = await Promise.allSettled([
        axios.get(`/ops/incidents/summary`, { headers }),
        axios.get(`/ops/incidents/list?${params}`, { headers }),
      ]);

      if (sumRes.status === 'fulfilled') setSummary(sumRes.value.data);
      if (listRes.status === 'fulfilled') {
        setIncidents(listRes.value.data.incidents || []);
        setTotal(listRes.value.data.total || 0);
      }
    } catch {
      toast.error('Olay verileri yüklenemedi');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [token, filter]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleAction = async (incidentId, action) => {
    try {
      await axios.post(
        `/ops/incidents/action/${incidentId}`,
        { action },
        { headers },
      );
      toast.success(`Olay ${action === 'resolve' ? 'çözüldü' : action === 'retry' ? 'tekrarlandı' : 'bastırıldı'}`);
      fetchData();
    } catch {
      toast.error(`İşlem başarısız`);
    }
  };

  const handleRefresh = () => { setRefreshing(true); fetchData(); };

  if (loading) {
    return (
      <>
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-8 h-8 animate-spin text-slate-500" />
        </div>
      </>
    );
  }

  const openCount = summary?.open_count || 0;
  const criticals = summary?.by_severity?.critical || 0;

  return (
    <>
      <div data-testid="incident-panel" className="space-y-6 max-w-[1400px] mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
              <Shield className="w-6 h-6 text-amber-400" />
              Olay Merkezi
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              Reconciliation, drift ve hard fail yönetimi
            </p>
          </div>
          <Button
            data-testid="incident-refresh-btn"
            variant="outline" size="sm"
            className="border-slate-300 text-slate-600"
            onClick={handleRefresh}
            disabled={refreshing}
          >
            {refreshing ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <RefreshCw className="w-4 h-4 mr-1" />}
            Yenile
          </Button>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <SummaryCard
            testId="summary-total" label="Toplam" value={summary?.total_incidents || 0}
            icon={AlertTriangle} accent="bg-slate-100 text-slate-700"
          />
          <SummaryCard
            testId="summary-open" label="Açık"
            value={openCount}
            icon={XCircle}
            accent={openCount > 0 ? 'bg-red-500/20 text-red-400' : 'bg-slate-100 text-slate-700'}
          />
          <SummaryCard
            testId="summary-critical" label="Kritik"
            value={criticals}
            icon={AlertTriangle}
            accent={criticals > 0 ? 'bg-red-500/20 text-red-400' : 'bg-slate-100 text-slate-700'}
          />
          <SummaryCard
            testId="summary-resolved" label={t('common.solvedCount')} value={summary?.resolved_count || 0}
            icon={CheckCircle} accent="bg-emerald-500/20 text-emerald-400"
          />
        </div>

        {/* Type Breakdown */}
        {summary?.by_type && Object.keys(summary.by_type).length > 0 && (
          <Card className="bg-white border-slate-200">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-slate-600 font-medium">Olay Türü Dağılımı</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {Object.entries(summary.by_type).map(([type, count]) => (
                <Badge key={type} className="bg-slate-100 text-slate-700 border-slate-300 text-xs">
                  {type.replace(/_/g, ' ')}: {count}
                </Badge>
              ))}
              {summary.ari_dead_letters > 0 && (
                <Badge className="bg-red-500/15 text-red-400 border-red-500/30 text-xs">
                  ARI Dead Letters: {summary.ari_dead_letters}
                </Badge>
              )}
            </CardContent>
          </Card>
        )}

        {/* Filters */}
        <div className="flex items-center gap-3 flex-wrap">
          <Filter className="w-4 h-4 text-slate-500" />
          <select
            data-testid="filter-status"
            className="bg-slate-100 border border-slate-300 text-slate-700 text-xs rounded px-2 py-1.5"
            value={filter.status}
            onChange={e => setFilter(f => ({ ...f, status: e.target.value }))}
          >
            <option value="">Tüm Durumlar</option>
            <option value="open">Açık</option>
            <option value="investigating">İnceleniyor</option>
            <option value="resolved">Çözüldü</option>
            <option value="suppressed">Bastırıldı</option>
          </select>
          <select
            data-testid="filter-severity"
            className="bg-slate-100 border border-slate-300 text-slate-700 text-xs rounded px-2 py-1.5"
            value={filter.severity}
            onChange={e => setFilter(f => ({ ...f, severity: e.target.value }))}
          >
            <option value="">Tüm Öncelikler</option>
            <option value="critical">Kritik</option>
            <option value="high">Yüksek</option>
            <option value="medium">Orta</option>
            <option value="low">Düşük</option>
          </select>
          <select
            data-testid="filter-provider"
            className="bg-slate-100 border border-slate-300 text-slate-700 text-xs rounded px-2 py-1.5"
            value={filter.provider}
            onChange={e => setFilter(f => ({ ...f, provider: e.target.value }))}
          >
            <option value="">Tüm Sağlayıcılar</option>
            <option value="exely">Exely</option>
            <option value="hotelrunner">HotelRunner</option>
          </select>
          <span className="text-xs text-slate-500 ml-auto">{total} olay</span>
        </div>

        {/* Incident List */}
        <Card data-testid="incident-list" className="bg-white border-slate-200">
          <CardContent className="p-0">
            {incidents.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-slate-500">
                <CheckCircle className="w-10 h-10 mb-3 text-emerald-500/50" />
                <p className="text-sm font-medium">Açık olay yok</p>
                <p className="text-xs mt-1">Sistem sağlığı iyi durumda</p>
              </div>
            ) : (
              incidents.map(inc => (
                <IncidentRow
                  key={inc.id}
                  incident={inc}
                  expanded={expandedId === inc.id}
                  onToggle={() => setExpandedId(expandedId === inc.id ? null : inc.id)}
                  onAction={handleAction}
                />
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
