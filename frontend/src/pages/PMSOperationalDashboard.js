import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  ArrowRightLeft, CalendarCheck, CalendarX, Users, BedDouble, AlertTriangle,
  ClipboardCheck, DoorOpen, DoorClosed, ShieldCheck, RefreshCw, Moon,
  CheckCircle, XCircle, Clock, Wrench
} from "lucide-react";
import { toast } from "sonner";

const API = process.env.REACT_APP_BACKEND_URL;

function StatCard({ title, value, icon: Icon, color = "slate", subtitle, testId }) {
  const colorMap = {
    emerald: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    red: "bg-red-500/10 text-red-400 border-red-500/20",
    amber: "bg-amber-500/10 text-amber-400 border-amber-500/20",
    blue: "bg-blue-500/10 text-blue-400 border-blue-500/20",
    slate: "bg-slate-500/10 text-slate-400 border-slate-500/20",
    violet: "bg-violet-500/10 text-violet-400 border-violet-500/20",
    cyan: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20",
  };
  return (
    <Card data-testid={testId} className={`border ${colorMap[color]} bg-slate-900/50`}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wider">{title}</p>
            <p className="text-2xl font-bold mt-1">{value}</p>
            {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
          </div>
          {Icon && <Icon className="w-8 h-8 opacity-60" />}
        </div>
      </CardContent>
    </Card>
  );
}

function RoomStatusBar({ data }) {
  if (!data) return null;
  const total = data.total || 1;
  const segments = [
    { key: "available", label: "Available", count: data.available, color: "bg-emerald-500" },
    { key: "occupied", label: "Occupied", count: data.occupied, color: "bg-blue-500" },
    { key: "dirty", label: "Dirty", count: data.dirty, color: "bg-amber-500" },
    { key: "cleaning", label: "Cleaning", count: data.cleaning, color: "bg-yellow-400" },
    { key: "inspected", label: "Inspected", count: data.inspected, color: "bg-cyan-400" },
    { key: "out_of_order", label: "OOO", count: data.out_of_order, color: "bg-red-500" },
    { key: "out_of_service", label: "OOS", count: data.out_of_service, color: "bg-slate-500" },
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
            <span className="text-slate-400">{s.label}</span>
            <span className="font-semibold text-slate-200">{s.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ArrivalsList({ arrivals }) {
  if (!arrivals?.arrivals?.length) return <p className="text-sm text-slate-500 py-4">No arrivals today</p>;
  return (
    <div data-testid="arrivals-list" className="space-y-2 max-h-72 overflow-y-auto">
      {arrivals.arrivals.map(a => (
        <div key={a.id} className="flex items-center justify-between p-2.5 rounded-lg bg-slate-800/50 border border-slate-700/50">
          <div>
            <p className="text-sm font-medium text-slate-200">{a.guest_name}</p>
            <p className="text-xs text-slate-500">Room {a.room_number} - {a.status}</p>
          </div>
          <Badge variant={a.room_ready ? "default" : "destructive"} className="text-xs">
            {a.room_ready ? "Ready" : a.room_status}
          </Badge>
        </div>
      ))}
    </div>
  );
}

function DeparturesList({ departures }) {
  if (!departures?.departures?.length) return <p className="text-sm text-slate-500 py-4">No departures today</p>;
  return (
    <div data-testid="departures-list" className="space-y-2 max-h-72 overflow-y-auto">
      {departures.departures.map(d => (
        <div key={d.id} className="flex items-center justify-between p-2.5 rounded-lg bg-slate-800/50 border border-slate-700/50">
          <div>
            <p className="text-sm font-medium text-slate-200">{d.guest_name}</p>
            <p className="text-xs text-slate-500">Room {d.room_number}</p>
          </div>
          {d.has_balance && (
            <Badge variant="destructive" className="text-xs">Balance: {d.folio_balance}</Badge>
          )}
          {!d.has_balance && <Badge className="text-xs bg-emerald-500/20 text-emerald-400">Settled</Badge>}
        </div>
      ))}
    </div>
  );
}

function ExceptionsList({ exceptions, onResolve }) {
  if (!exceptions?.exceptions?.length) return <p className="text-sm text-slate-500 py-4">No open exceptions</p>;
  return (
    <div data-testid="exceptions-list" className="space-y-2 max-h-72 overflow-y-auto">
      {exceptions.exceptions.map(e => (
        <div key={e.id} className="flex items-center justify-between p-2.5 rounded-lg bg-red-900/20 border border-red-700/30">
          <div className="flex-1 mr-2">
            <p className="text-sm font-medium text-red-300">{e.exception_type}</p>
            <p className="text-xs text-slate-500 truncate">{e.description}</p>
          </div>
          <Button size="sm" variant="ghost" className="text-xs" onClick={() => onResolve(e.id)}>Resolve</Button>
        </div>
      ))}
    </div>
  );
}

function BlockedCheckins({ blocked }) {
  if (!blocked?.blocked?.length) return <p className="text-sm text-slate-500 py-4">No blocked check-ins</p>;
  return (
    <div data-testid="blocked-checkins-list" className="space-y-2 max-h-72 overflow-y-auto">
      {blocked.blocked.map(b => (
        <div key={b.booking_id} className="flex items-center justify-between p-2.5 rounded-lg bg-amber-900/20 border border-amber-700/30">
          <div>
            <p className="text-sm font-medium text-amber-300">{b.guest_name}</p>
            <p className="text-xs text-slate-500">Room {b.room_number}</p>
          </div>
          <Badge variant="outline" className="text-xs text-amber-400 border-amber-400">{b.room_status}</Badge>
        </div>
      ))}
    </div>
  );
}

function NightAuditPanel({ token, onRefresh }) {
  const [loading, setLoading] = useState(false);
  const [auditResult, setAuditResult] = useState(null);
  const [businessDate, setBusinessDate] = useState("");

  useEffect(() => {
    axios.get(`${API}/api/pms-core/night-audit/business-date`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => setBusinessDate(r.data.business_date))
      .catch(() => {});
  }, [token]);

  const runAudit = async () => {
    setLoading(true);
    try {
      const { data } = await axios.post(`${API}/api/pms-core/night-audit/run`, { business_date: businessDate }, { headers: { Authorization: `Bearer ${token}` } });
      setAuditResult(data);
      toast.success("Night audit completed");
      if (onRefresh) onRefresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Night audit failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div data-testid="night-audit-panel" className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-slate-400">Business Date</p>
          <p className="text-lg font-semibold text-slate-200">{businessDate}</p>
        </div>
        <Button data-testid="run-night-audit-btn" onClick={runAudit} disabled={loading}
          className="bg-indigo-600 hover:bg-indigo-700">
          <Moon className="w-4 h-4 mr-2" /> {loading ? "Running..." : "Run Night Audit"}
        </Button>
      </div>
      {auditResult && (
        <div className="space-y-3 mt-4">
          <Badge className={auditResult.status === "completed" ? "bg-emerald-600" : "bg-red-600"}>
            {auditResult.status}
          </Badge>
          {auditResult.steps?.map((step, i) => (
            <div key={i} className="text-xs bg-slate-800/60 p-2 rounded border border-slate-700/50">
              <span className="text-slate-400 font-medium">{step.step}: </span>
              <span className="text-slate-300">{JSON.stringify(step.result?.posted || step.result?.count || step.result?.checked || "OK")}</span>
            </div>
          ))}
          {auditResult.exceptions?.length > 0 && (
            <div className="text-xs text-red-400">{auditResult.exceptions.length} exceptions found</div>
          )}
        </div>
      )}
    </div>
  );
}

function AuditTrailPanel({ token }) {
  const [trail, setTrail] = useState([]);
  useEffect(() => {
    axios.get(`${API}/api/pms-core/audit-trail?limit=30`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => setTrail(r.data.trail || []))
      .catch(() => {});
  }, [token]);

  if (!trail.length) return <p className="text-sm text-slate-500 py-4">No audit trail entries</p>;
  return (
    <div data-testid="audit-trail-panel" className="space-y-2 max-h-96 overflow-y-auto">
      {trail.map((e, i) => (
        <div key={i} className="text-xs bg-slate-800/40 p-2 rounded border border-slate-700/40 flex items-start gap-2">
          <ShieldCheck className="w-3.5 h-3.5 text-slate-500 mt-0.5 shrink-0" />
          <div>
            <span className="text-slate-300 font-medium">{e.action}</span>
            <span className="text-slate-500 ml-1">({e.entity_type} {e.entity_id?.slice(0,8)}...)</span>
            <p className="text-slate-600">{e.timestamp?.slice(0,19)}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function PMSOperationalDashboard({ user, tenant }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("overview");
  const token = localStorage.getItem("token");

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const { data: d } = await axios.get(`${API}/api/pms-core/dashboard/operational`, { headers: { Authorization: `Bearer ${token}` } });
      setData(d);
    } catch (e) {
      toast.error("Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleResolveException = async (id) => {
    try {
      await axios.post(`${API}/api/pms-core/night-audit/resolve-exception`,
        { exception_id: id, resolution: "Resolved from dashboard" },
        { headers: { Authorization: `Bearer ${token}` } });
      toast.success("Exception resolved");
      fetchData();
    } catch (e) {
      toast.error("Failed to resolve exception");
    }
  };

  if (loading && !data) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <RefreshCw className="w-8 h-8 animate-spin text-indigo-400" />
      </div>
    );
  }

  return (
    <div data-testid="pms-operational-dashboard" className="min-h-screen bg-slate-950 text-slate-100">
      <div className="max-w-[1600px] mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-slate-100">PMS Operations</h1>
            <p className="text-sm text-slate-500">{data?.business_date} - {tenant?.property_name || "Hotel"}</p>
          </div>
          <Button data-testid="refresh-dashboard-btn" variant="outline" size="sm" onClick={fetchData}
            className="border-slate-700 text-slate-300 hover:bg-slate-800">
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>
        </div>

        {/* KPI Strip */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 mb-6">
          <StatCard testId="stat-arrivals" title="Arrivals" value={data?.arrivals_today?.total || 0} icon={DoorOpen} color="emerald" />
          <StatCard testId="stat-departures" title="Departures" value={data?.departures_today?.total || 0} icon={DoorClosed} color="blue" />
          <StatCard testId="stat-in-house" title="In-House" value={data?.in_house_guests?.count || 0} icon={Users} color="violet" />
          <StatCard testId="stat-ready" title="Ready Rooms" value={data?.room_status?.ready || 0} icon={CheckCircle} color="emerald"
            subtitle={`of ${data?.room_status?.total || 0}`} />
          <StatCard testId="stat-dirty" title="Dirty Rooms" value={(data?.room_status?.dirty || 0) + (data?.room_status?.cleaning || 0)} icon={Wrench} color="amber" />
          <StatCard testId="stat-folio-issues" title="Folio Issues" value={data?.pending_folio_issues?.count || 0} icon={AlertTriangle} color="red" />
          <StatCard testId="stat-exceptions" title="Exceptions" value={data?.audit_exceptions?.count || 0} icon={XCircle} color="red" />
        </div>

        {/* Room Status Bar */}
        <Card className="bg-slate-900/50 border-slate-800 mb-6">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm text-slate-400 uppercase tracking-wider flex items-center gap-2">
              <BedDouble className="w-4 h-4" /> Room Status Overview
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <RoomStatusBar data={data?.room_status} />
          </CardContent>
        </Card>

        {/* Tabbed Content */}
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="bg-slate-900 border border-slate-800 mb-4">
            <TabsTrigger data-testid="tab-overview" value="overview" className="data-[state=active]:bg-indigo-600/20 data-[state=active]:text-indigo-300">
              <CalendarCheck className="w-3.5 h-3.5 mr-1.5" /> Overview
            </TabsTrigger>
            <TabsTrigger data-testid="tab-night-audit" value="night-audit" className="data-[state=active]:bg-indigo-600/20 data-[state=active]:text-indigo-300">
              <Moon className="w-3.5 h-3.5 mr-1.5" /> Night Audit
            </TabsTrigger>
            <TabsTrigger data-testid="tab-audit-trail" value="audit-trail" className="data-[state=active]:bg-indigo-600/20 data-[state=active]:text-indigo-300">
              <ShieldCheck className="w-3.5 h-3.5 mr-1.5" /> Audit Trail
            </TabsTrigger>
          </TabsList>

          <TabsContent value="overview">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <Card className="bg-slate-900/50 border-slate-800">
                <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-emerald-400">Arrivals Today ({data?.arrivals_today?.total || 0})</CardTitle></CardHeader>
                <CardContent className="px-4 pb-3"><ArrivalsList arrivals={data?.arrivals_today} /></CardContent>
              </Card>
              <Card className="bg-slate-900/50 border-slate-800">
                <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-blue-400">Departures Today ({data?.departures_today?.total || 0})</CardTitle></CardHeader>
                <CardContent className="px-4 pb-3"><DeparturesList departures={data?.departures_today} /></CardContent>
              </Card>
              <Card className="bg-slate-900/50 border-slate-800">
                <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-red-400">Audit Exceptions ({data?.audit_exceptions?.count || 0})</CardTitle></CardHeader>
                <CardContent className="px-4 pb-3"><ExceptionsList exceptions={data?.audit_exceptions} onResolve={handleResolveException} /></CardContent>
              </Card>
              <Card className="bg-slate-900/50 border-slate-800">
                <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-amber-400">Blocked Check-ins ({data?.blocked_checkins?.count || 0})</CardTitle></CardHeader>
                <CardContent className="px-4 pb-3"><BlockedCheckins blocked={data?.blocked_checkins} /></CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="night-audit">
            <Card className="bg-slate-900/50 border-slate-800">
              <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-indigo-400">Night Audit Control</CardTitle></CardHeader>
              <CardContent className="px-4 pb-4"><NightAuditPanel token={token} onRefresh={fetchData} /></CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="audit-trail">
            <Card className="bg-slate-900/50 border-slate-800">
              <CardHeader className="pb-2 pt-3 px-4"><CardTitle className="text-sm text-slate-400">PMS Audit Trail (Recent)</CardTitle></CardHeader>
              <CardContent className="px-4 pb-4"><AuditTrailPanel token={token} /></CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
