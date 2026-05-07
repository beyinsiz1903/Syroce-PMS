import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";

import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  ArrowLeft, Clock, Filter, Search, User, Shield, AlertTriangle,
  ChevronDown, ChevronRight, RefreshCw, Loader2, FileText, Eye
} from "lucide-react";

const API = "";

function SeverityBadge({ severity }) {
  const map = {
    critical: "bg-red-100 text-red-700 border-red-300",
    high: "bg-amber-100 text-amber-700 border-amber-300",
    warning: "bg-amber-100 text-amber-800 border-amber-300",
    info: "bg-sky-100 text-sky-700 border-sky-300",
  };
  return (
    <span data-testid={`severity-${severity}`} className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold border ${map[severity] || map.info}`}>
      {severity}
    </span>
  );
}

function DiffView({ before, after }) {
  if (!before && !after) return null;
  return (
    <div className="grid grid-cols-2 gap-2 mt-2 text-xs">
      {before && (
        <div className="bg-red-950/30 border border-red-900/30 rounded p-2">
          <p className="text-red-400 font-mono mb-1">Before</p>
          <pre className="text-zinc-400 overflow-auto max-h-24">{JSON.stringify(before, null, 2)}</pre>
        </div>
      )}
      {after && (
        <div className="bg-emerald-950/30 border border-emerald-900/30 rounded p-2">
          <p className="text-emerald-400 font-mono mb-1">After</p>
          <pre className="text-zinc-400 overflow-auto max-h-24">{JSON.stringify(after, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

function TimelineEvent({ event, expanded, onToggle }) {
  const time = event.timestamp ? new Date(event.timestamp).toLocaleString("tr-TR") : "—";
  return (
    <div data-testid={`timeline-event-${event.id || event.operation_name}`} className="border-l-2 border-gray-200 pl-4 pb-4 relative">
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
          <div className="flex items-center gap-3 mt-1 text-[11px] text-gray-500">
            <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{time}</span>
            <span className="flex items-center gap-1"><User className="w-3 h-3" />{event.actor_role || "system"}</span>
            {event.target_id && <span className="font-mono">{event.target_id.substring(0, 8)}...</span>}
            {event.duration_ms && <span>{event.duration_ms}ms</span>}
          </div>
        </div>
        {(event.before_snapshot || event.after_snapshot) && (
          <Button size="sm" variant="ghost" className="h-6 text-xs text-gray-500" onClick={onToggle}>
            {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </Button>
        )}
      </div>
      {expanded && <DiffView before={event.before_snapshot} after={event.after_snapshot} />}
    </div>
  );
}

export default function AuditTimelinePage({ user, tenant, onLogout }) {
  const navigate = useNavigate();
  const [events, setEvents] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ severity: "", actor: "", entity_type: "", limit: 50 });
  const [expandedIds, setExpandedIds] = useState(new Set());
  const [searchEntity, setSearchEntity] = useState({ type: "", id: "" });
  const [entityTrail, setEntityTrail] = useState(null);

  const token = localStorage.getItem("token") || localStorage.getItem("access_token");
  const headers = { Authorization: `Bearer ${token}` };

  const fetchTimeline = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.severity) params.append("severity", filters.severity);
      if (filters.actor) params.append("actor", filters.actor);
      if (filters.entity_type) params.append("entity_type", filters.entity_type);
      params.append("limit", filters.limit);

      const [timelineRes, summaryRes] = await Promise.all([
        axios.get(`/audit/timeline?${params}`, { headers }),
        axios.get(`/audit/summary?period=24h`, { headers }),
      ]);
      setEvents(timelineRes.data?.events || timelineRes.data?.data?.events || []);
      setSummary(summaryRes.data?.data || summaryRes.data || null);
    } catch (err) {
      console.error("Failed to fetch timeline:", err);
    }
    setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [filters]);

  useEffect(() => { fetchTimeline(); }, [fetchTimeline]);

  const fetchEntityTrail = async () => {
    if (!searchEntity.type || !searchEntity.id) return;
    try {
      const res = await axios.get(
        `/audit/timeline/${searchEntity.type}/${searchEntity.id}`,
        { headers }
      );
      setEntityTrail(res.data?.data || res.data);
    } catch (err) {
      console.error("Entity trail error:", err);
    }
  };

  const toggleExpand = (id) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  return (
    <>
    <div data-testid="audit-timeline-page" className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex items-center justify-between mb-6">
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="text-gray-600">
            <ArrowLeft className="w-4 h-4 mr-1" /> Back
          </Button>
          <Button data-testid="refresh-timeline-btn" size="sm" variant="outline" onClick={fetchTimeline}>
            {loading ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <RefreshCw className="w-3 h-3 mr-1" />}
            Refresh
          </Button>
        </div>

        {/* Summary Cards */}
        {summary && (
          <div data-testid="audit-summary" className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500">Total Events (24h)</p>
                <p className="text-2xl font-bold text-gray-900">{summary.total_events || 0}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500">Critical</p>
                <p className="text-2xl font-bold text-red-600">{summary.by_severity?.critical || 0}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500">Warning</p>
                <p className="text-2xl font-bold text-amber-600">{summary.by_severity?.warning || 0}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <p className="text-xs text-gray-500">Info</p>
                <p className="text-2xl font-bold text-sky-600">{summary.by_severity?.info || 0}</p>
              </CardContent>
            </Card>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Filters + Timeline */}
          <div className="lg:col-span-2 space-y-4">
            {/* Filters */}
            <Card data-testid="timeline-filters">
              <CardContent className="p-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <Filter className="w-4 h-4 text-gray-500" />
                  <select data-testid="filter-severity" value={filters.severity} onChange={(e) => setFilters(p => ({...p, severity: e.target.value}))}
                    className="bg-white border border-gray-300 rounded text-xs px-2 py-1 text-gray-700">
                    <option value="">All Severity</option>
                    <option value="critical">Critical</option>
                    <option value="warning">Warning</option>
                    <option value="info">Info</option>
                  </select>
                  <select data-testid="filter-entity" value={filters.entity_type} onChange={(e) => setFilters(p => ({...p, entity_type: e.target.value}))}
                    className="bg-white border border-gray-300 rounded text-xs px-2 py-1 text-gray-700">
                    <option value="">All Entities</option>
                    <option value="booking">Booking</option>
                    <option value="folio">Folio</option>
                    <option value="room">Room</option>
                    <option value="pos_transaction">POS</option>
                    <option value="keycard">Keycard</option>
                    <option value="inventory">Inventory</option>
                  </select>
                  <Input data-testid="filter-actor" placeholder="Actor..." value={filters.actor}
                    onChange={(e) => setFilters(p => ({...p, actor: e.target.value}))}
                    className="text-xs h-7 w-32" />
                </div>
              </CardContent>
            </Card>

            {/* Timeline Events */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-gray-700 flex items-center gap-2">
                  <Clock className="w-4 h-4" /> Event Timeline
                  <Badge variant="outline" className="text-[10px] bg-gray-100 text-gray-700 border-gray-300">{events.length} events</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                {loading ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
                  </div>
                ) : events.length === 0 ? (
                  <div className="text-center py-8 text-gray-500 text-sm">No audit events found</div>
                ) : (
                  events.map((ev, idx) => (
                    <TimelineEvent
                      key={ev.id || idx}
                      event={ev}
                      expanded={expandedIds.has(ev.id || idx)}
                      onToggle={() => toggleExpand(ev.id || idx)}
                    />
                  ))
                )}
              </CardContent>
            </Card>
          </div>

          {/* Entity Search + Sidebar */}
          <div className="space-y-4">
            {/* Entity Trail Search */}
            <Card data-testid="entity-search">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-gray-700 flex items-center gap-2">
                  <Search className="w-4 h-4" /> Entity Audit Trail
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <select data-testid="entity-type-select" value={searchEntity.type}
                  onChange={(e) => setSearchEntity(p => ({...p, type: e.target.value}))}
                  className="w-full bg-white border border-gray-300 rounded text-xs px-2 py-1.5 text-gray-700">
                  <option value="">Select Entity Type</option>
                  <option value="booking">Booking</option>
                  <option value="folio">Folio</option>
                  <option value="room">Room</option>
                  <option value="guest">Guest</option>
                </select>
                <Input data-testid="entity-id-input" placeholder="Entity ID..." value={searchEntity.id}
                  onChange={(e) => setSearchEntity(p => ({...p, id: e.target.value}))}
                  className="text-xs" />
                <Button data-testid="search-entity-btn" size="sm" onClick={fetchEntityTrail}
                  className="w-full text-xs" disabled={!searchEntity.type || !searchEntity.id}>
                  <Eye className="w-3 h-3 mr-1" /> View Trail
                </Button>

                {entityTrail && (
                  <div className="mt-3 space-y-2">
                    <p className="text-xs text-gray-600">{entityTrail.entity_type}: {entityTrail.entity_id} ({entityTrail.count || 0} events)</p>
                    {(entityTrail.trail || []).map((t, i) => (
                      <div key={i} className="bg-gray-50 border border-gray-200 rounded p-2 text-xs">
                        <p className="text-gray-800">{t.operation_name || t.action}</p>
                        <p className="text-gray-500">{t.timestamp ? new Date(t.timestamp).toLocaleString("tr-TR") : "—"}</p>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Summary by Operation */}
            {summary && summary.by_operation && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-700 flex items-center gap-2">
                    <FileText className="w-4 h-4" /> By Operation
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {Object.entries(summary.by_operation).map(([op, count]) => (
                    <div key={op} className="flex justify-between items-center py-1 text-xs">
                      <span className="text-gray-600 font-mono">{op}</span>
                      <span className="text-gray-900 font-semibold">{count}</span>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            {/* Summary by Actor */}
            {summary && summary.by_actor && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-gray-700 flex items-center gap-2">
                    <User className="w-4 h-4" /> By Actor
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {Object.entries(summary.by_actor).map(([actor, count]) => (
                    <div key={actor} className="flex justify-between items-center py-1 text-xs">
                      <span className="text-gray-600">{actor}</span>
                      <span className="text-gray-900 font-semibold">{count}</span>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
    </>
  );
}
