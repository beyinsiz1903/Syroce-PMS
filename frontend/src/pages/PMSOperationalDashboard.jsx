import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { useTranslation } from "react-i18next";

import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  CalendarCheck, Users, BedDouble, AlertTriangle,
  DoorOpen, DoorClosed, ShieldCheck, RefreshCw, Moon,
  CheckCircle, XCircle, Wrench, TrendingUp, Filter,
  Building2, Sparkles, ChevronRight
} from "lucide-react";
import { toast } from "sonner";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, AreaChart, Area
} from "recharts";

const API = "";

/* ─── STAT CARD ─── */
function StatCard({ title, value, icon: Icon, color = "gray", subtitle, testId }) {
  const colorMap = {
    emerald: "border-l-emerald-500 bg-white dark:bg-card",
    red: "border-l-red-500 bg-white dark:bg-card",
    amber: "border-l-amber-500 bg-white dark:bg-card",
    blue: "border-l-blue-500 bg-white dark:bg-card",
    gray: "border-l-gray-400 bg-white dark:bg-card",
    violet: "border-l-violet-500 bg-white dark:bg-card",
    cyan: "border-l-cyan-500 bg-white dark:bg-card",
  };
  const iconColorMap = {
    emerald: "text-emerald-500",
    red: "text-red-500",
    amber: "text-amber-500",
    blue: "text-blue-500",
    gray: "text-gray-400 dark:text-slate-500",
    violet: "text-violet-500",
    cyan: "text-cyan-500",
  };
  return (
    <Card data-testid={testId} className={`border-l-4 ${colorMap[color]} shadow-sm`}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-gray-500 dark:text-slate-400 uppercase tracking-wider font-medium">{title}</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">{value}</p>
            {subtitle && <p className="text-xs text-gray-400 dark:text-slate-500 mt-0.5">{subtitle}</p>}
          </div>
          {Icon && <Icon className={`w-8 h-8 opacity-60 ${iconColorMap[color]}`} />}
        </div>
      </CardContent>
    </Card>
  );
}

/* ─── ROOM STATUS BAR ─── */
function RoomStatusBar({ data, t }) {
  if (!data) return null;
  const total = data.total || 1;
  const segments = [
    { key: "available", label: t("pmsOperations.available"), count: data.available, color: "bg-emerald-500" },
    { key: "occupied", label: t("pmsOperations.occupied"), count: data.occupied, color: "bg-blue-500" },
    { key: "dirty", label: t("pmsOperations.dirty"), count: data.dirty, color: "bg-amber-500" },
    { key: "cleaning", label: t("pmsOperations.cleaning"), count: data.cleaning, color: "bg-yellow-400" },
    { key: "inspected", label: t("pmsOperations.inspected"), count: data.inspected, color: "bg-cyan-400" },
    { key: "out_of_order", label: t("pmsOperations.outOfOrder"), count: data.out_of_order, color: "bg-red-500" },
    { key: "out_of_service", label: t("pmsOperations.outOfService"), count: data.out_of_service, color: "bg-gray-400" },
  ];
  return (
    <div data-testid="room-status-bar">
      <div className="flex rounded-lg overflow-hidden h-6 mb-3">
        {segments.filter(s => s.count > 0).map(s => (
          <div key={s.key} className={`${s.color} transition-all`} style={{ width: `${(s.count / total) * 100}%` }}
               title={`${s.label}: ${s.count}`} />
        ))}
      </div>
      <div className="flex flex-wrap gap-3">
        {segments.map(s => (
          <div key={s.key} className="flex items-center gap-1.5 text-xs">
            <span className={`w-2.5 h-2.5 rounded-sm ${s.color}`} />
            <span className="text-gray-500 dark:text-slate-400">{s.label}</span>
            <span className="font-semibold text-gray-800 dark:text-slate-100">{s.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─── DATE RANGE FILTER ─── */
function DateRangeFilter({ range, onChange, t }) {
  const presets = [
    { key: "today", label: t("pmsOperations.today"), days: 0 },
    { key: "7d", label: t("pmsOperations.days7"), days: 7 },
    { key: "30d", label: t("pmsOperations.days30"), days: 30 },
  ];
  return (
    <div data-testid="date-range-filter" className="flex items-center gap-2">
      <Filter className="w-4 h-4 text-gray-400 dark:text-slate-500" />
      {presets.map(p => (
        <Button key={p.key} data-testid={`filter-${p.key}`}
          size="sm" variant={range === p.key ? "default" : "outline"}
          className={range === p.key
            ? "bg-blue-600 text-white text-xs h-7"
            : "text-gray-600 dark:text-slate-300 text-xs h-7"}
          onClick={() => onChange(p.key)}>
          {p.label}
        </Button>
      ))}
      <input
        data-testid="filter-custom-start"
        type="date"
        className="bg-white dark:bg-card border border-gray-200 dark:border-slate-700 rounded px-2 py-1 text-xs text-gray-700 dark:text-slate-200 h-7"
        onChange={e => {
          const el = document.querySelector('[data-testid="filter-custom-end"]');
          if (el?.value) onChange("custom", e.target.value, el.value);
        }}
      />
      <span className="text-gray-400 dark:text-slate-500 text-xs">-</span>
      <input
        data-testid="filter-custom-end"
        type="date"
        className="bg-white dark:bg-card border border-gray-200 dark:border-slate-700 rounded px-2 py-1 text-xs text-gray-700 dark:text-slate-200 h-7"
        onChange={e => {
          const el = document.querySelector('[data-testid="filter-custom-start"]');
          if (el?.value) onChange("custom", el.value, e.target.value);
        }}
      />
    </div>
  );
}

/* ─── TREND CHART ─── */
function TrendGraph({ title, data, dataKey = "count", color = "#3b82f6", type = "area", testId }) {
  if (!data?.length) return null;
  const formatted = data.map(d => ({ ...d, label: d.date?.slice(5) }));
  const Chart = type === "bar" ? BarChart : AreaChart;
  return (
    <Card data-testid={testId} className="bg-white dark:bg-card border-gray-200 dark:border-slate-700 shadow-sm">
      <CardHeader className="pb-1 pt-3 px-4">
        <CardTitle className="text-xs text-gray-500 dark:text-slate-400 uppercase tracking-wider">{title}</CardTitle>
      </CardHeader>
      <CardContent className="px-2 pb-2 h-[160px]">
        <ResponsiveContainer width="100%" height="100%">
          <Chart data={formatted} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--dash-chart-grid, #e5e7eb)" />
            <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--dash-chart-axis, #6b7280)" }} />
            <YAxis tick={{ fontSize: 10, fill: "var(--dash-chart-axis, #6b7280)" }} />
            <Tooltip
              contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12, color: "hsl(var(--foreground))" }}
              labelStyle={{ color: "hsl(var(--muted-foreground))" }}
            />
            {type === "bar" ? (
              <Bar dataKey={dataKey} fill={color} radius={[3, 3, 0, 0]} />
            ) : (
              <Area type="monotone" dataKey={dataKey} stroke={color} fill={color} fillOpacity={0.1} strokeWidth={2} />
            )}
          </Chart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

/* ─── LIST COMPONENTS ─── */
function ArrivalsList({ arrivals, t }) {
  if (!arrivals?.arrivals?.length) return <p className="text-sm text-gray-400 dark:text-slate-500 py-4">{t("pmsOperations.noArrivals")}</p>;
  return (
    <div data-testid="arrivals-list" className="space-y-2 max-h-72 overflow-y-auto">
      {arrivals.arrivals.map(a => (
        <div key={a.id} className="flex items-center justify-between p-2.5 rounded-lg bg-gray-50 dark:bg-slate-800/50 border border-gray-100 dark:border-slate-800">
          <div>
            <p className="text-sm font-medium text-gray-800 dark:text-slate-100">{a.guest_name}</p>
            <p className="text-xs text-gray-500 dark:text-slate-400">{t("pmsOperations.room")} {a.room_number} - {a.status}</p>
          </div>
          <Badge variant={a.room_ready ? "default" : "destructive"} className="text-xs">
            {a.room_ready ? t("pmsOperations.ready") : a.room_status}
          </Badge>
        </div>
      ))}
    </div>
  );
}

function DeparturesList({ departures, t }) {
  if (!departures?.departures?.length) return <p className="text-sm text-gray-400 dark:text-slate-500 py-4">{t("pmsOperations.noDepartures")}</p>;
  return (
    <div data-testid="departures-list" className="space-y-2 max-h-72 overflow-y-auto">
      {departures.departures.map(d => (
        <div key={d.id} className="flex items-center justify-between p-2.5 rounded-lg bg-gray-50 dark:bg-slate-800/50 border border-gray-100 dark:border-slate-800">
          <div>
            <p className="text-sm font-medium text-gray-800 dark:text-slate-100">{d.guest_name}</p>
            <p className="text-xs text-gray-500 dark:text-slate-400">{t("pmsOperations.room")} {d.room_number}</p>
          </div>
          {d.has_balance
            ? <Badge variant="destructive" className="text-xs">{t("pmsOperations.balance")}: {d.folio_balance}</Badge>
            : <Badge className="text-xs bg-emerald-100 text-emerald-700">{t("pmsOperations.settled")}</Badge>}
        </div>
      ))}
    </div>
  );
}

function ExceptionsList({ exceptions, onResolve, t }) {
  if (!exceptions?.exceptions?.length) return <p className="text-sm text-gray-400 dark:text-slate-500 py-4">{t("pmsOperations.noExceptions")}</p>;
  return (
    <div data-testid="exceptions-list" className="space-y-2 max-h-72 overflow-y-auto">
      {exceptions.exceptions.map(e => (
        <div key={e.id} className="flex items-center justify-between p-2.5 rounded-lg bg-red-50 border border-red-100">
          <div className="flex-1 mr-2">
            <p className="text-sm font-medium text-red-700">{e.exception_type}</p>
            <p className="text-xs text-gray-500 dark:text-slate-400 truncate">{e.description}</p>
          </div>
          <Button size="sm" variant="ghost" className="text-xs text-red-600" onClick={() => onResolve(e.id)}>{t("pmsOperations.resolve")}</Button>
        </div>
      ))}
    </div>
  );
}

function BlockedCheckins({ blocked, t }) {
  if (!blocked?.blocked?.length) return <p className="text-sm text-gray-400 dark:text-slate-500 py-4">{t("pmsOperations.noBlocked")}</p>;
  return (
    <div data-testid="blocked-checkins-list" className="space-y-2 max-h-72 overflow-y-auto">
      {blocked.blocked.map(b => (
        <div key={b.booking_id} className="flex items-center justify-between p-2.5 rounded-lg bg-amber-50 border border-amber-100">
          <div>
            <p className="text-sm font-medium text-amber-700">{b.guest_name}</p>
            <p className="text-xs text-gray-500 dark:text-slate-400">{t("pmsOperations.room")} {b.room_number}</p>
          </div>
          <Badge variant="outline" className="text-xs text-amber-600 border-amber-300">{b.room_status}</Badge>
        </div>
      ))}
    </div>
  );
}

/* ─── NIGHT AUDIT PANEL ─── */
function NightAuditPanel({ token, onRefresh, t }) {
  const [loading, setLoading] = useState(false);
  const [auditResult, setAuditResult] = useState(null);
  const [businessDate, setBusinessDate] = useState("");

  useEffect(() => {
    axios.get(`/pms-core/night-audit/business-date`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => setBusinessDate(r.data.business_date))
      .catch((err) => console.error('Business date load failed:', err));
  }, [token]);

  const runAudit = async () => {
    setLoading(true);
    try {
      const { data } = await axios.post(`/pms-core/night-audit/run`, { business_date: businessDate }, { headers: { Authorization: `Bearer ${token}` } });
      setAuditResult(data);
      toast.success(t("pmsOperations.nightAuditCompleted"));
      if (onRefresh) onRefresh();
    } catch (e) { toast.error(e.response?.data?.detail || t("pmsOperations.nightAuditFailed")); }
    finally { setLoading(false); }
  };

  return (
    <div data-testid="night-audit-panel" className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-500 dark:text-slate-400">{t("pmsOperations.businessDate")}</p>
          <p className="text-lg font-semibold text-gray-900 dark:text-white">{businessDate}</p>
        </div>
        <Button data-testid="run-night-audit-btn" onClick={runAudit} disabled={loading}
          className="bg-blue-600 hover:bg-blue-700 text-white">
          <Moon className="w-4 h-4 mr-2" /> {loading ? t("pmsOperations.running") : t("pmsOperations.runNightAudit")}
        </Button>
      </div>
      {auditResult && (
        <div className="space-y-3 mt-4">
          <Badge className={auditResult.status === "completed" ? "bg-emerald-600" : "bg-red-600"}>{auditResult.status}</Badge>
          {auditResult.steps?.map((step, i) => (
            <div key={i} className="text-xs bg-gray-50 dark:bg-slate-800/50 p-2 rounded border border-gray-100 dark:border-slate-800">
              <span className="text-gray-500 dark:text-slate-400 font-medium">{step.step}: </span>
              <span className="text-gray-700 dark:text-slate-200">{JSON.stringify(step.result?.posted || step.result?.count || step.result?.checked || "OK")}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── MULTI-PROPERTY AUDIT PANEL ─── */
function MultiPropertyAuditPanel({ token, t }) {
  const [board, setBoard] = useState(null);
  const [blockers, setBlockers] = useState(null);

  useEffect(() => {
    const headers = { Authorization: `Bearer ${token}` };
    axios.get(`/pms-core/multi-property/audit-board`, { headers })
      .then(r => setBoard(r.data))
      .catch((err) => console.error('Audit board load failed:', err));
    axios.get(`/pms-core/multi-property/unresolved-blockers`, { headers })
      .then(r => setBlockers(r.data))
      .catch((err) => console.error('Unresolved blockers load failed:', err));
  }, [token]);

  const statusColor = (s) => ({
    completed: "bg-emerald-100 text-emerald-700",
    running: "bg-blue-100 text-blue-700",
    blocked: "bg-amber-100 text-amber-700",
    failed: "bg-red-100 text-red-700",
    pending: "bg-gray-100 text-gray-600",
  }[s] || "bg-gray-100 text-gray-600");

  const statusLabels = {
    completed: t("pmsOperations.completed"),
    running: t("pmsOperations.runningStatus"),
    blocked: t("pmsOperations.blocked"),
    failed: t("pmsOperations.failed"),
    pending: t("pmsOperations.pending"),
  };

  return (
    <div data-testid="multi-property-audit-panel" className="space-y-4">
      {board && (
        <>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="text-center">
                <p className="text-2xl font-bold text-blue-600">{board.readiness_score}%</p>
                <p className="text-xs text-gray-500 dark:text-slate-400">{t("pmsOperations.readinessScore")}</p>
              </div>
              <div className="h-10 w-px bg-gray-200 dark:bg-slate-700" />
              {["completed", "running", "blocked", "failed", "pending"].map(s => (
                <div key={s} className="text-center">
                  <p className="text-lg font-semibold text-gray-800 dark:text-slate-100">{board.summary?.[s] || 0}</p>
                  <p className="text-xs text-gray-500 dark:text-slate-400">{statusLabels[s]}</p>
                </div>
              ))}
            </div>
          </div>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {board.board?.slice(0, 10).map(p => (
              <div key={p.property_id} className="flex items-center justify-between p-2.5 rounded-lg bg-gray-50 dark:bg-slate-800/50 border border-gray-100 dark:border-slate-800">
                <div className="flex items-center gap-2">
                  <Building2 className="w-4 h-4 text-gray-400 dark:text-slate-500" />
                  <div>
                    <p className="text-sm font-medium text-gray-800 dark:text-slate-100">{p.property_name}</p>
                    <p className="text-xs text-gray-500 dark:text-slate-400">{t("pmsOperations.businessDate")}: {p.business_date}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {p.open_exceptions > 0 && <Badge variant="destructive" className="text-xs">{p.open_exceptions} {t("pmsOperations.exc")}</Badge>}
                  <Badge className={`text-xs ${statusColor(p.audit_status)}`}>{statusLabels[p.audit_status] || p.audit_status}</Badge>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
      {blockers && blockers.total > 0 && (
        <Card className="bg-red-50 border-red-200">
          <CardHeader className="pb-1 pt-3 px-4">
            <CardTitle className="text-sm text-red-600">{t("pmsOperations.unresolvedBlockers")} ({blockers.total})</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-3 space-y-1">
            {blockers.critical?.slice(0, 5).map(b => (
              <div key={b.id} className="text-xs text-red-600 flex items-center gap-1">
                <XCircle className="w-3 h-3" /> {b.description?.slice(0, 80)}
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/* ─── AUTO HOUSEKEEPING PANEL ─── */
function AutoHousekeepingPanel({ token, t }) {
  const [suggestions, setSuggestions] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get(`/pms-core/housekeeping/assignment-suggestions`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => setSuggestions(r.data))
      .catch((e) => {
        console.warn('[PMSOpsDashboard] housekeeping suggestions fetch failed:', e?.response?.status ?? e?.message);
      })
      .finally(() => setLoading(false));
  }, [token]);

  const priorityColor = (p) => ({
    critical: "bg-red-100 text-red-700 border-red-200",
    high: "bg-amber-100 text-amber-700 border-amber-200",
    medium: "bg-blue-100 text-blue-700 border-blue-200",
    low: "bg-gray-100 text-gray-600 border-gray-200",
  }[p] || "bg-gray-100 text-gray-600");

  if (loading) return <div className="py-8 text-center text-gray-400 dark:text-slate-500">{t("pmsOperations.loadingSuggestions")}</div>;

  return (
    <div data-testid="auto-housekeeping-panel" className="space-y-4">
      {suggestions?.staff_workload?.length > 0 && (
        <div>
          <p className="text-xs text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-2 font-medium">{t("pmsOperations.staffWorkload")}</p>
          <div className="flex flex-wrap gap-2">
            {suggestions.staff_workload.map(s => (
              <div key={s.staff_id} className="flex items-center gap-2 bg-gray-50 dark:bg-slate-800/50 border border-gray-100 dark:border-slate-800 rounded-lg px-3 py-1.5">
                <span className="text-xs text-gray-700 dark:text-slate-200">{s.staff_name}</span>
                <Badge className="text-xs bg-blue-100 text-blue-700">{s.total_active} {t("pmsOperations.active")}</Badge>
                <span className="text-xs text-gray-400 dark:text-slate-500">{s.completed_today} {t("pmsOperations.done")}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      <div>
        <p className="text-xs text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-2 font-medium">
          {t("pmsOperations.suggestions")} ({suggestions?.total_suggestions || 0})
        </p>
        {!suggestions?.suggestions?.length ? (
          <p className="text-sm text-gray-400 dark:text-slate-500 py-4">{t("pmsOperations.allClean")}</p>
        ) : (
          <div className="space-y-2 max-h-72 overflow-y-auto">
            {suggestions.suggestions.map(s => (
              <div key={s.room_id} className="flex items-center justify-between p-2.5 rounded-lg bg-gray-50 dark:bg-slate-800/50 border border-gray-100 dark:border-slate-800">
                <div className="flex items-center gap-3">
                  <div>
                    <p className="text-sm font-medium text-gray-800 dark:text-slate-100">{t("pmsOperations.room")} {s.room_number}</p>
                    <p className="text-xs text-gray-500 dark:text-slate-400">{s.room_type} - {t("pmsOperations.floor")} {s.floor}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge className={`text-xs ${priorityColor(s.priority?.level)}`}>{s.priority?.level}</Badge>
                  <div className="text-right">
                    <p className="text-xs text-gray-700 dark:text-slate-200">{s.suggested_assignee?.staff_name || t("pmsOperations.unassigned")}</p>
                    <p className="text-xs text-gray-400 dark:text-slate-500">{s.estimated_minutes} {t("pmsOperations.min")}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── AUDIT TRAIL PANEL ─── */
function AuditTrailPanel({ token, t }) {
  const [trail, setTrail] = useState([]);
  useEffect(() => {
    axios.get(`/pms-core/audit-trail?limit=30`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => setTrail(r.data.trail || []))
      .catch((e) => {
        console.warn('[PMSOpsDashboard] audit-trail fetch failed:', e?.response?.status ?? e?.message);
      });
  }, [token]);

  if (!trail.length) return <p className="text-sm text-gray-400 dark:text-slate-500 py-4">{t("pmsOperations.noAuditTrail")}</p>;
  return (
    <div data-testid="audit-trail-panel" className="space-y-2 max-h-96 overflow-y-auto">
      {trail.map((e, i) => (
        <div key={i} className="text-xs bg-gray-50 dark:bg-slate-800/50 p-2 rounded border border-gray-100 dark:border-slate-800 flex items-start gap-2">
          <ShieldCheck className="w-3.5 h-3.5 text-gray-400 dark:text-slate-500 mt-0.5 shrink-0" />
          <div>
            <span className="text-gray-700 dark:text-slate-200 font-medium">{e.action}</span>
            <span className="text-gray-400 dark:text-slate-500 ml-1">({e.entity_type} {e.entity_id?.slice(0,8)}...)</span>
            <p className="text-gray-400 dark:text-slate-500">{e.timestamp?.slice(0,19)}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ══════════════════════════════════════════════ */
/* MAIN DASHBOARD                                */
/* ══════════════════════════════════════════════ */

export default function PMSOperationalDashboard({ user, tenant, onLogout }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [trends, setTrends] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("overview");
  const [dateRange, setDateRange] = useState("7d");
  const token = localStorage.getItem("token");

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const { data: d } = await axios.get(`/pms-core/dashboard/operational`, { headers: { Authorization: `Bearer ${token}` } });
      setData(d);
    } catch { toast.error(t("pmsOperations.failedToLoad")); }
    finally { setLoading(false); }
  }, [token, t]);

  const fetchTrends = useCallback(async (range, customStart, customEnd) => {
    const today = new Date();
    let sd, ed;
    if (range === "custom" && customStart && customEnd) {
      sd = customStart; ed = customEnd;
    } else if (range === "today") {
      sd = today.toISOString().slice(0, 10);
      ed = sd;
    } else if (range === "30d") {
      ed = today.toISOString().slice(0, 10);
      sd = new Date(today - 30 * 86400000).toISOString().slice(0, 10);
    } else {
      ed = today.toISOString().slice(0, 10);
      sd = new Date(today - 7 * 86400000).toISOString().slice(0, 10);
    }
    try {
      const { data: t } = await axios.get(`/pms-core/dashboard/trends?start_date=${sd}&end_date=${ed}`, { headers: { Authorization: `Bearer ${token}` } });
      setTrends(t);
    } catch { /* trends optional */ }
  }, [token]);

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => { fetchTrends(dateRange); }, [dateRange, fetchTrends]);

  const handleDateRangeChange = (range, start, end) => {
    setDateRange(range);
    if (range === "custom") fetchTrends("custom", start, end);
  };

  const handleResolveException = async (id) => {
    try {
      await axios.post(`/pms-core/night-audit/resolve-exception`,
        { exception_id: id, resolution: "Resolved from dashboard" },
        { headers: { Authorization: `Bearer ${token}` } });
      toast.success(t("pmsOperations.exceptionResolved"));
      fetchData();
    } catch { toast.error(t("pmsOperations.exceptionResolveFailed")); }
  };

  if (loading && !data) {
    return (
      <>
        <div className="flex items-center justify-center py-32">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
        </div>
      </>
    );
  }

  const tr = trends?.trends;

  return (
    <>
      <div data-testid="pms-operational-dashboard" className="max-w-[1600px] mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t("pmsOperations.title")}</h1>
            <p className="text-sm text-gray-500 dark:text-slate-400">{data?.business_date} - {tenant?.property_name || "Hotel"}</p>
          </div>
          <Button data-testid="refresh-dashboard-btn" variant="outline" size="sm" onClick={() => { fetchData(); fetchTrends(dateRange); }}
            className="border-gray-200 dark:border-slate-700 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-800/50">
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} /> {t("pmsOperations.refresh")}
          </Button>
        </div>

        {/* KPI Strip */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 mb-6">
          <StatCard testId="stat-arrivals" title={t("pmsOperations.arrivals")} value={data?.arrivals_today?.total || 0} icon={DoorOpen} color="emerald" />
          <StatCard testId="stat-departures" title={t("pmsOperations.departures")} value={data?.departures_today?.total || 0} icon={DoorClosed} color="blue" />
          <StatCard testId="stat-in-house" title={t("pmsOperations.inHouse")} value={data?.in_house_guests?.count || 0} icon={Users} color="violet" />
          <StatCard testId="stat-ready" title={t("pmsOperations.readyRooms")} value={data?.room_status?.ready || 0} icon={CheckCircle} color="emerald" subtitle={t("pmsOperations.of", { total: data?.room_status?.total || 0 })} />
          <StatCard testId="stat-dirty" title={t("pmsOperations.dirtyRooms")} value={(data?.room_status?.dirty || 0) + (data?.room_status?.cleaning || 0)} icon={Wrench} color="amber" />
          <StatCard testId="stat-folio-issues" title={t("pmsOperations.folioIssues")} value={data?.pending_folio_issues?.count || 0} icon={AlertTriangle} color="red" />
          <StatCard testId="stat-exceptions" title={t("pmsOperations.exceptions")} value={data?.audit_exceptions?.count || 0} icon={XCircle} color="red" />
        </div>

        {/* Room Status Bar */}
        <Card className="bg-white dark:bg-card border-gray-200 dark:border-slate-700 shadow-sm mb-6">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm text-gray-500 dark:text-slate-400 uppercase tracking-wider flex items-center gap-2">
              <BedDouble className="w-4 h-4" /> {t("pmsOperations.roomStatusOverview")}
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <RoomStatusBar data={data?.room_status} t={t} />
          </CardContent>
        </Card>

        {/* Tabbed Content */}
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="bg-white dark:bg-card border border-gray-200 dark:border-slate-700 mb-4">
            <TabsTrigger data-testid="tab-overview" value="overview" className="data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700">
              <CalendarCheck className="w-3.5 h-3.5 mr-1.5" /> {t("pmsOperations.tabOverview")}
            </TabsTrigger>
            <TabsTrigger data-testid="tab-trends" value="trends" className="data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700">
              <TrendingUp className="w-3.5 h-3.5 mr-1.5" /> {t("pmsOperations.tabTrends")}
            </TabsTrigger>
            <TabsTrigger data-testid="tab-night-audit" value="night-audit" className="data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700">
              <Moon className="w-3.5 h-3.5 mr-1.5" /> {t("pmsOperations.tabNightAudit")}
            </TabsTrigger>
            <TabsTrigger data-testid="tab-multi-property" value="multi-property" className="data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700">
              <Building2 className="w-3.5 h-3.5 mr-1.5" /> {t("pmsOperations.tabMultiProperty")}
            </TabsTrigger>
            <TabsTrigger data-testid="tab-housekeeping" value="housekeeping" className="data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700">
              <Sparkles className="w-3.5 h-3.5 mr-1.5" /> {t("pmsOperations.tabAutoHK")}
            </TabsTrigger>
            <TabsTrigger data-testid="tab-audit-trail" value="audit-trail" className="data-[state=active]:bg-blue-50 data-[state=active]:text-blue-700">
              <ShieldCheck className="w-3.5 h-3.5 mr-1.5" /> {t("pmsOperations.tabAuditTrail")}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="overview">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <Card className="bg-white dark:bg-card border-gray-200 dark:border-slate-700 shadow-sm">
                <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-emerald-600">{t("pmsOperations.arrivalsToday")} ({data?.arrivals_today?.total || 0})</CardTitle></CardHeader>
                <CardContent className="px-4 pb-3"><ArrivalsList arrivals={data?.arrivals_today} t={t} /></CardContent>
              </Card>
              <Card className="bg-white dark:bg-card border-gray-200 dark:border-slate-700 shadow-sm">
                <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-blue-600">{t("pmsOperations.departuresToday")} ({data?.departures_today?.total || 0})</CardTitle></CardHeader>
                <CardContent className="px-4 pb-3"><DeparturesList departures={data?.departures_today} t={t} /></CardContent>
              </Card>
              <Card className="bg-white dark:bg-card border-gray-200 dark:border-slate-700 shadow-sm">
                <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-red-600">{t("pmsOperations.auditExceptions")} ({data?.audit_exceptions?.count || 0})</CardTitle></CardHeader>
                <CardContent className="px-4 pb-3"><ExceptionsList exceptions={data?.audit_exceptions} onResolve={handleResolveException} t={t} /></CardContent>
              </Card>
              <Card className="bg-white dark:bg-card border-gray-200 dark:border-slate-700 shadow-sm">
                <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-amber-600">{t("pmsOperations.blockedCheckins")} ({data?.blocked_checkins?.count || 0})</CardTitle></CardHeader>
                <CardContent className="px-4 pb-3"><BlockedCheckins blocked={data?.blocked_checkins} t={t} /></CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="trends">
            <div className="space-y-4">
              <DateRangeFilter range={dateRange} onChange={handleDateRangeChange} t={t} />
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <TrendGraph testId="trend-arrivals" title={t("pmsOperations.arrivalsTrend")} data={tr?.arrivals} color="#10b981" />
                <TrendGraph testId="trend-departures" title={t("pmsOperations.departuresTrend")} data={tr?.departures} color="#3b82f6" />
                <TrendGraph testId="trend-occupancy" title={t("pmsOperations.occupancyPercent")} data={tr?.occupancy} dataKey="rate" color="#8b5cf6" />
                <TrendGraph testId="trend-hk-readiness" title={t("pmsOperations.hkReadiness")} data={tr?.housekeeping_readiness} dataKey="rate" color="#06b6d4" />
                <TrendGraph testId="trend-folio-issues" title={t("pmsOperations.folioIssuesTrend")} data={tr?.folio_issues} color="#f59e0b" type="bar" />
                <TrendGraph testId="trend-audit-exceptions" title={t("pmsOperations.auditExceptionsTrend")} data={tr?.audit_exceptions} color="#ef4444" type="bar" />
                <TrendGraph testId="trend-blocked-checkins" title={t("pmsOperations.blockedCheckinsTrend")} data={tr?.blocked_checkins} color="#f97316" type="bar" />
              </div>
            </div>
          </TabsContent>

          <TabsContent value="night-audit">
            <Card className="bg-white dark:bg-card border-gray-200 dark:border-slate-700 shadow-sm">
              <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-blue-600">{t("pmsOperations.nightAuditControl")}</CardTitle></CardHeader>
              <CardContent className="px-4 pb-4"><NightAuditPanel token={token} onRefresh={fetchData} t={t} /></CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="multi-property">
            <Card className="bg-white dark:bg-card border-gray-200 dark:border-slate-700 shadow-sm">
              <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-blue-600">{t("pmsOperations.multiPropertyAudit")}</CardTitle></CardHeader>
              <CardContent className="px-4 pb-4"><MultiPropertyAuditPanel token={token} t={t} /></CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="housekeeping">
            <Card className="bg-white dark:bg-card border-gray-200 dark:border-slate-700 shadow-sm">
              <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-blue-600">{t("pmsOperations.autoHKAssignment")}</CardTitle></CardHeader>
              <CardContent className="px-4 pb-4"><AutoHousekeepingPanel token={token} t={t} /></CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="audit-trail">
            <Card className="bg-white dark:bg-card border-gray-200 dark:border-slate-700 shadow-sm">
              <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-gray-500 dark:text-slate-400">{t("pmsOperations.auditTrailRecent")}</CardTitle></CardHeader>
              <CardContent className="px-4 pb-4"><AuditTrailPanel token={token} t={t} /></CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </>
  );
}
