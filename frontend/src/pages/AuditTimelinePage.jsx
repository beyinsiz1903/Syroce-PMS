import { useTranslation } from 'react-i18next';
import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { ArrowLeft, Clock, Filter, Search, User, Shield, AlertTriangle, ChevronDown, ChevronRight, RefreshCw, Loader2, FileText, Eye, Globe, Monitor, ShieldCheck, ShieldAlert } from "lucide-react";
const API = "";
function SeverityBadge({
  severity
}) {
  const map = {
    critical: "bg-red-100 text-red-700 border-red-300",
    high: "bg-amber-100 text-amber-700 border-amber-300",
    warning: "bg-amber-100 text-amber-800 border-amber-300",
    info: "bg-sky-100 text-sky-700 border-sky-300"
  };
  return <span data-testid={`severity-${severity}`} className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold border ${map[severity] || map.info}`}>
      {severity}
    </span>;
}
function DiffView({
  before,
  after,
  t
}) {
  if (!before && !after) return null;
  return <div className="grid grid-cols-2 gap-2 mt-2 text-xs">
      {before && <div className="bg-red-950/30 border border-red-900/30 rounded p-2">
          <p className="text-red-400 font-mono mb-1">{t("cm.pages_AuditTimelinePage.before")}</p>
          <pre className="text-zinc-400 overflow-auto max-h-24">{JSON.stringify(before, null, 2)}</pre>
        </div>}
      {after && <div className="bg-emerald-950/30 border border-emerald-900/30 rounded p-2">
          <p className="text-emerald-400 font-mono mb-1">{t("cm.pages_AuditTimelinePage.after")}</p>
          <pre className="text-zinc-400 overflow-auto max-h-24">{JSON.stringify(after, null, 2)}</pre>
        </div>}
    </div>;
}
function TimelineEvent({
  event,
  expanded,
  onToggle,
  t,
  i18n
}) {
  const time = event.timestamp ? new Date(event.timestamp).toLocaleString(i18n.language) : "—";
  return <div data-testid={`timeline-event-${event.id || event.operation_name}`} className="border-l-2 border-gray-200 pl-4 pb-4 relative">
      <div className="absolute -left-[5px] top-1 w-2 h-2 rounded-full bg-gray-400" />
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium text-gray-900">{event.operation_name || event.action}</span>
            <SeverityBadge severity={event.severity || "info"} />
            <Badge variant="outline" className="text-[10px] bg-gray-100 text-gray-700 border-gray-300">{event.target_type}</Badge>
            <Badge variant="outline" className={`text-[10px] ${event.result_status === "success" ? "text-emerald-700 bg-emerald-50 border-emerald-300" : "text-red-700 bg-red-50 border-red-300"}`}>
              {event.result_status}
            </Badge>
          </div>
          <div className="flex items-center gap-3 mt-1 text-[11px] text-gray-500 flex-wrap">
            <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{time}</span>
            <span className="flex items-center gap-1"><User className="w-3 h-3" />{event.actor_role || "system"}</span>
            {event.target_id && <span className="font-mono">{event.target_id.substring(0, 8)}...</span>}
            {event.ip_address && <span data-testid="event-ip" className="flex items-center gap-1 font-mono" title={t("cm.pages_AuditTimelinePage.ip_adresi")}>
                <Globe className="w-3 h-3" />{event.ip_address}
              </span>}
            {event.user_agent && <span data-testid="event-device" className="flex items-center gap-1 max-w-[220px] truncate" title={event.user_agent}>
                <Monitor className="w-3 h-3 shrink-0" /><span className="truncate">{event.user_agent}</span>
              </span>}
            {event.duration_ms && <span>{event.duration_ms}{t("cm.pages_AuditTimelinePage.ms")}</span>}
          </div>
        </div>
        {(event.before_snapshot || event.after_snapshot) && <Button size="sm" variant="ghost" className="h-6 text-xs text-gray-500" onClick={onToggle}>
            {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </Button>}
      </div>
      {expanded && <DiffView before={event.before_snapshot} after={event.after_snapshot} t={t} />}
    </div>;
}
export default function AuditTimelinePage({
  user,
  tenant,
  onLogout
}) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [events, setEvents] = useState([]);
  const [summary, setSummary] = useState(null);
  const [chain, setChain] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    severity: "",
    actor: "",
    entity_type: "",
    ip_address: "",
    user_agent: "",
    limit: 50
  });
  const [expandedIds, setExpandedIds] = useState(new Set());
  const [searchEntity, setSearchEntity] = useState({
    type: "",
    id: ""
  });
  const [entityTrail, setEntityTrail] = useState(null);
  const token = localStorage.getItem("token") || localStorage.getItem("access_token");
  const headers = {};
  const fetchTimeline = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.severity) params.append("severity", filters.severity);
      if (filters.actor) params.append("actor", filters.actor);
      if (filters.entity_type) params.append("entity_type", filters.entity_type);
      params.append("limit", filters.limit);
      if (filters.ip_address) params.append("ip_address", filters.ip_address);
      if (filters.user_agent) params.append("user_agent", filters.user_agent);
      const [timelineRes, summaryRes, chainRes] = await Promise.all([axios.get(`/audit/timeline?${params}`, {
        headers
      }), axios.get(`/audit/summary?period=24h`, {
        headers
      }), axios.get(`/audit/chain/verify`, {
        headers
      }).catch(() => null)]);
      setEvents(timelineRes.data?.events || timelineRes.data?.data?.events || []);
      setSummary(summaryRes.data?.data || summaryRes.data || null);
      setChain(chainRes ? chainRes.data?.data || chainRes.data || null : null);
    } catch (err) {
      console.error("Failed to fetch timeline:", err);
    }
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [filters]);
  useEffect(() => {
    fetchTimeline();
  }, [fetchTimeline]);
  const fetchEntityTrail = async () => {
    if (!searchEntity.type || !searchEntity.id) return;
    try {
      const res = await axios.get(`/audit/timeline/${searchEntity.type}/${searchEntity.id}`, {
        headers
      });
      setEntityTrail(res.data?.data || res.data);
    } catch (err) {
      console.error("Entity trail error:", err);
    }
  };
  const toggleExpand = id => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };
  return <>
    <div data-testid="audit-timeline-page" className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex items-center justify-between mb-6">
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="text-gray-600">
            <ArrowLeft className="w-4 h-4 mr-1" />{t("cm.pages_AuditTimelinePage.back")}</Button>
          <Button data-testid="refresh-timeline-btn" size="sm" variant="outline" onClick={fetchTimeline}>
            {loading ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <RefreshCw className="w-3 h-3 mr-1" />}{t("cm.pages_AuditTimelinePage.refresh")}</Button>
        </div>

        {/* Tamper-evidence: hash-chain integrity status (read-only) */}
        {chain && <div data-testid="chain-status" className={`flex items-center gap-2 mb-4 px-3 py-2 rounded border text-sm ${chain.degraded ? "bg-amber-50 border-amber-300 text-amber-800" : chain.ok ? "bg-emerald-50 border-emerald-300 text-emerald-800" : "bg-red-50 border-red-300 text-red-800"}`}>
            {chain.degraded ? <><AlertTriangle className="w-4 h-4" />{t("cm.pages_AuditTimelinePage.zincir_do\u011Frulanamad\u0131_ge\xE7ici_ha")}</> : chain.ok ? <><ShieldCheck className="w-4 h-4" />{t("cm.pages_AuditTimelinePage.denetim_zinciri_b\xFCt\xFCnl\xFC\u011F\xFC_do\u011Fr")}{chain.checked || 0}{t("cm.pages_AuditTimelinePage.kay\u0131t_kurcalama_tespit_edilmed")}</> : <><ShieldAlert className="w-4 h-4" />{t("cm.pages_AuditTimelinePage.uyari_denetim_zinciri_k\u0131r\u0131k")}{(chain.breaks || []).length}{t("cm.pages_AuditTimelinePage.kay\u0131t_de\u011Fi\u015Ftirilmi\u015F_silinmi\u015F_o")}{(chain.breaks || []).length > 0 && <span className="font-mono ml-1">{t("cm.pages_AuditTimelinePage._seq")}{(chain.breaks || []).slice(0, 5).map(b => b.seq).join(", ")})</span>}.</>}
          </div>}

        {/* Summary Cards */}
        {summary && <div data-testid="audit-summary" className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500">{t("cm.pages_AuditTimelinePage.total_events_24h")}</p>
                <p className="text-2xl font-bold text-gray-900">{summary.total_events || 0}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500">{t("cm.pages_AuditTimelinePage.critical")}</p>
                <p className="text-2xl font-bold text-red-600">{summary.by_severity?.critical || 0}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500">{t("cm.pages_AuditTimelinePage.warning")}</p>
                <p className="text-2xl font-bold text-amber-600">{summary.by_severity?.warning || 0}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500">{t("cm.pages_AuditTimelinePage.info")}</p>
                <p className="text-2xl font-bold text-sky-600">{summary.by_severity?.info || 0}</p>
              </CardContent>
            </Card>
          </div>}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Filters + Timeline */}
          <div className="lg:col-span-2 space-y-4">
            {/* Filters */}
            <Card data-testid="timeline-filters">
              <CardContent className="p-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <Filter className="w-4 h-4 text-gray-500" />
                  <select data-testid="filter-severity" value={filters.severity} onChange={e => setFilters(p => ({
                    ...p,
                    severity: e.target.value
                  }))} className="bg-white border border-gray-300 rounded text-xs px-2 py-1 text-gray-700">
                    <option value="">{t("cm.pages_AuditTimelinePage.all_severity")}</option>
                    <option value="critical">{t("cm.pages_AuditTimelinePage.critical")}</option>
                    <option value="warning">{t("cm.pages_AuditTimelinePage.warning")}</option>
                    <option value="info">{t("cm.pages_AuditTimelinePage.info")}</option>
                  </select>
                  <select data-testid="filter-entity" value={filters.entity_type} onChange={e => setFilters(p => ({
                    ...p,
                    entity_type: e.target.value
                  }))} className="bg-white border border-gray-300 rounded text-xs px-2 py-1 text-gray-700">
                    <option value="">{t("cm.pages_AuditTimelinePage.all_entities")}</option>
                    <option value="booking">{t("cm.pages_AuditTimelinePage.booking")}</option>
                    <option value="folio">{t("cm.pages_AuditTimelinePage.folio")}</option>
                    <option value="room">{t("cm.pages_AuditTimelinePage.room")}</option>
                    <option value="pos_transaction">{t("cm.pages_AuditTimelinePage.pos")}</option>
                    <option value="keycard">{t("cm.pages_AuditTimelinePage.keycard")}</option>
                    <option value="inventory">{t("cm.pages_AuditTimelinePage.inventory")}</option>
                  </select>
                  <Input data-testid="filter-actor" placeholder={t("cm.pages_AuditTimelinePage.actor")} value={filters.actor} onChange={e => setFilters(p => ({
                    ...p,
                    actor: e.target.value
                  }))} className="text-xs h-7 w-32 md:w-auto" />
                  <Input data-testid="filter-ip" placeholder={t("cm.pages_AuditTimelinePage.ip_adresi")} value={filters.ip_address} onChange={e => setFilters(p => ({
                    ...p,
                    ip_address: e.target.value
                  }))} className="text-xs h-7 w-32 md:w-auto" />
                  <Input data-testid="filter-device" placeholder={t("cm.pages_AuditTimelinePage.cihaz_taray\u0131c\u0131")} value={filters.user_agent} onChange={e => setFilters(p => ({
                    ...p,
                    user_agent: e.target.value
                  }))} className="text-xs h-7 w-40 md:w-auto" />
                </div>
              </CardContent>
            </Card>

            {/* Timeline Events */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-gray-700 flex items-center gap-2">
                  <Clock className="w-4 h-4" />{t("cm.pages_AuditTimelinePage.event_timeline")}<Badge variant="outline" className="text-[10px] bg-gray-100 text-gray-700 border-gray-300">{events.length}{t("cm.pages_AuditTimelinePage.events")}</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                {loading ? <div className="flex items-center justify-center py-8">
                    <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
                  </div> : events.length === 0 ? <div className="text-center py-8 text-gray-500 text-sm">{t("cm.pages_AuditTimelinePage.no_audit_events_found")}</div> : events.map((ev, idx) => <TimelineEvent key={ev.id || idx} event={ev} expanded={expandedIds.has(ev.id || idx)} onToggle={() => toggleExpand(ev.id || idx)} t={t} i18n={i18n} />)}
              </CardContent>
            </Card>
          </div>

          {/* Entity Search + Sidebar */}
          <div className="space-y-4">
            {/* Entity Trail Search */}
            <Card data-testid="entity-search">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-gray-700 flex items-center gap-2">
                  <Search className="w-4 h-4" />{t("cm.pages_AuditTimelinePage.entity_audit_trail")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <select data-testid="entity-type-select" value={searchEntity.type} onChange={e => setSearchEntity(p => ({
                  ...p,
                  type: e.target.value
                }))} className="w-full bg-white border border-gray-300 rounded text-xs px-2 py-1.5 text-gray-700">
                  <option value="">{t("cm.pages_AuditTimelinePage.select_entity_type")}</option>
                  <option value="booking">{t("cm.pages_AuditTimelinePage.booking")}</option>
                  <option value="folio">{t("cm.pages_AuditTimelinePage.folio")}</option>
                  <option value="room">{t("cm.pages_AuditTimelinePage.room")}</option>
                  <option value="guest">{t("cm.pages_AuditTimelinePage.guest")}</option>
                </select>
                <Input data-testid="entity-id-input" placeholder={t("cm.pages_AuditTimelinePage.entity_id")} value={searchEntity.id} onChange={e => setSearchEntity(p => ({
                  ...p,
                  id: e.target.value
                }))} className="text-xs" />
                <Button data-testid="search-entity-btn" size="sm" onClick={fetchEntityTrail} className="w-full text-xs" disabled={!searchEntity.type || !searchEntity.id}>
                  <Eye className="w-3 h-3 mr-1" />{t("cm.pages_AuditTimelinePage.view_trail")}</Button>

                {entityTrail && <div className="mt-3 space-y-2">
                    <p className="text-xs text-gray-600">{entityTrail.entity_type}: {entityTrail.entity_id} ({entityTrail.count || 0}{t("cm.pages_AuditTimelinePage.events")}</p>
                    {(entityTrail.trail || []).map((t, i) => <div key={t.id || i} className="bg-gray-50 border border-gray-200 rounded p-2 text-xs">
                        <p className="text-gray-800">{t.operation_name || t.action}</p>
                        <p className="text-gray-500">{t.timestamp ? new Date(t.timestamp).toLocaleString(i18n.language) : "—"}</p>
                      </div>)}
                  </div>}
              </CardContent>
            </Card>

            {/* Summary by Operation */}
            {summary && summary.by_operation && <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-700 flex items-center gap-2">
                    <FileText className="w-4 h-4" />{t("cm.pages_AuditTimelinePage.by_operation")}</CardTitle>
                </CardHeader>
                <CardContent>
                  {Object.entries(summary.by_operation).map(([op, count]) => <div key={op} className="flex justify-between items-center py-1 text-xs">
                      <span className="text-gray-600 font-mono">{op}</span>
                      <span className="text-gray-900 font-semibold">{count}</span>
                    </div>)}
                </CardContent>
              </Card>}

            {/* Summary by Actor */}
            {summary && summary.by_actor && <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-700 flex items-center gap-2">
                    <User className="w-4 h-4" />{t("cm.pages_AuditTimelinePage.by_actor")}</CardTitle>
                </CardHeader>
                <CardContent>
                  {Object.entries(summary.by_actor).map(([actor, count]) => <div key={actor} className="flex justify-between items-center py-1 text-xs">
                      <span className="text-gray-600">{actor}</span>
                      <span className="text-gray-900 font-semibold">{count}</span>
                    </div>)}
                </CardContent>
              </Card>}
          </div>
        </div>
      </div>
    </div>
    </>;
}