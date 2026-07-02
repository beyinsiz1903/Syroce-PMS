import { t } from "i18next";
import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { ArrowLeft, AlertTriangle, Bell, CheckCircle2, XCircle, Clock, RefreshCw, Loader2, Shield, Activity, Eye, Check } from "lucide-react";
const API = "";
function AlertCard({
  alert,
  onAck,
  onResolve
}) {
  const sevMap = {
    critical: {
      bg: "bg-red-950/40 border-red-900/50",
      text: "text-red-400",
      icon: XCircle
    },
    high: {
      bg: "bg-amber-950/40 border-amber-900/50",
      text: "text-amber-400",
      icon: AlertTriangle
    },
    warning: {
      bg: "bg-amber-950/40 border-amber-900/50",
      text: "text-amber-400",
      icon: AlertTriangle
    },
    info: {
      bg: "bg-sky-950/40 border-sky-900/50",
      text: "text-sky-400",
      icon: Bell
    }
  };
  const s = sevMap[alert.severity] || sevMap.info;
  const Icon = s.icon;
  return <div data-testid={`alert-${alert.id}`} className={`p-4 rounded-lg border ${s.bg}`}>
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <Icon className={`w-5 h-5 mt-0.5 ${s.text} shrink-0`} />
          <div>
            <p className={`text-sm font-medium ${s.text}`}>{alert.name}</p>
            <p className="text-xs text-zinc-400 mt-0.5">{alert.category}{t("cm.pages_IncidentDashboardPage._blast")}{alert.blast_radius}</p>
            <p className="text-xs text-zinc-500 mt-1">{alert.runbook}</p>
            <div className="flex gap-2 mt-1 text-[10px] text-zinc-600">
              <span><Clock className="w-3 h-3 inline mr-0.5" />{new Date(alert.fired_at).toLocaleString("tr-TR")}</span>
              {alert.mtta && <span>{t("cm.pages_IncidentDashboardPage.mtta")}{alert.mtta}s</span>}
              {alert.mttr && <span>{t("cm.pages_IncidentDashboardPage.mttr")}{alert.mttr}s</span>}
            </div>
          </div>
        </div>
        <div className="flex gap-1 shrink-0">
          {!alert.acknowledged && <Button data-testid={`ack-${alert.id}`} size="sm" variant="outline" onClick={() => onAck(alert.id)} className="h-7 text-xs border-zinc-700 text-zinc-400"><Eye className="w-3 h-3 mr-1" />{t("cm.pages_IncidentDashboardPage.ack")}</Button>}
          {!alert.resolved && <Button data-testid={`resolve-${alert.id}`} size="sm" variant="outline" onClick={() => onResolve(alert.id)} className="h-7 text-xs border-zinc-700 text-emerald-400"><Check className="w-3 h-3 mr-1" />{t("cm.pages_IncidentDashboardPage.resolve")}</Button>}
        </div>
      </div>
    </div>;
}
export default function IncidentDashboardPage() {
  const navigate = useNavigate();
  const [alerts, setAlerts] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [serviceHealth, setServiceHealth] = useState(null);
  const [alertSummary, setAlertSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const token = localStorage.getItem("token") || localStorage.getItem("access_token");
  const headers = {
    Authorization: `Bearer ${token}`
  };
  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [alertRes, incRes, healthRes, summRes] = await Promise.all([axios.get(`/alerts/active`, {
        headers
      }), axios.get(`/incidents/list?limit=20`, {
        headers
      }), axios.get(`/incidents/service-health`, {
        headers
      }), axios.get(`/alerts/summary?hours=24`, {
        headers
      })]);
      setAlerts(alertRes.data?.data?.alerts || []);
      setIncidents(incRes.data?.data?.incidents || []);
      setServiceHealth(healthRes.data?.data || null);
      setAlertSummary(summRes.data?.data || null);
    } catch (err) {
      console.error("Fetch error:", err);
    }
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);
  useEffect(() => {
    fetchAll();
  }, [fetchAll]);
  const ackAlert = async id => {
    try {
      await axios.post(`/alerts/acknowledge`, {
        alert_id: id
      }, {
        headers
      });
      fetchAll();
    } catch (e) {
      console.error(e);
    }
  };
  const resolveAlert = async id => {
    try {
      await axios.post(`/alerts/resolve`, {
        alert_id: id,
        resolution_note: "Resolved from dashboard"
      }, {
        headers
      });
      fetchAll();
    } catch (e) {
      console.error(e);
    }
  };
  const statusColor = s => {
    if (s === "healthy") return "text-emerald-400";
    if (s === "degraded") return "text-amber-400";
    return "text-red-400";
  };
  return <div data-testid="incident-dashboard" className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="text-zinc-400">
              <ArrowLeft className="w-4 h-4 mr-1" />{t("cm.pages_IncidentDashboardPage.back")}</Button>
            <div>
              <h1 className="text-xl font-bold flex items-center gap-2"><Shield className="w-5 h-5" />{t("cm.pages_IncidentDashboardPage.incident_alert_center")}</h1>
              <p className="text-xs text-zinc-500">{t("cm.pages_IncidentDashboardPage.real_time_operational_awarenes")}</p>
            </div>
          </div>
          <Button data-testid="refresh-incidents-btn" size="sm" variant="outline" onClick={fetchAll} className="border-zinc-700 bg-zinc-900 text-zinc-300">
            {loading ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <RefreshCw className="w-3 h-3 mr-1" />}{t("cm.pages_IncidentDashboardPage.refresh")}</Button>
        </div>

        {/* Service Health Matrix */}
        {serviceHealth && <Card data-testid="service-health-matrix" className="bg-zinc-900/60 border-zinc-800 mb-6">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm text-zinc-300 flex items-center gap-2">
                  <Activity className="w-4 h-4" />{t("cm.pages_IncidentDashboardPage.service_health_matrix")}</CardTitle>
                <Badge variant="outline" className={`text-xs ${statusColor(serviceHealth.overall_status)} border-current/40`}>
                  {serviceHealth.overall_status}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {(serviceHealth.services || []).map(svc => <div key={svc.service} data-testid={`svc-${svc.service}`} className="bg-zinc-800/50 rounded-lg p-3 border border-zinc-700/50">
                    <p className="text-xs text-zinc-400 mb-1">{svc.service.replace(/_/g, " ")}</p>
                    <p className={`text-sm font-semibold ${statusColor(svc.status)}`}>{svc.status}</p>
                    {svc.active_incidents > 0 && <p className="text-[10px] text-red-400 mt-0.5">{svc.active_incidents}{t("cm.pages_IncidentDashboardPage.active_incident_s")}</p>}
                  </div>)}
              </div>
            </CardContent>
          </Card>}

        {/* Alert Summary */}
        {alertSummary && <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
            <Card className="bg-zinc-900/60 border-zinc-800">
              <CardContent className="p-3">
                <p className="text-xs text-zinc-500">{t("cm.pages_IncidentDashboardPage.total_alerts_24h")}</p>
                <p className="text-2xl font-bold text-zinc-100">{alertSummary.total_alerts}</p>
              </CardContent>
            </Card>
            <Card className="bg-zinc-900/60 border-zinc-800">
              <CardContent className="p-3">
                <p className="text-xs text-zinc-500">{t("cm.pages_IncidentDashboardPage.alert_rules")}</p>
                <p className="text-2xl font-bold text-sky-400">{alertSummary.rules_count}</p>
              </CardContent>
            </Card>
            <Card className="bg-zinc-900/60 border-zinc-800">
              <CardContent className="p-3">
                <p className="text-xs text-zinc-500">{t("cm.pages_IncidentDashboardPage.by_critical")}</p>
                <p className="text-2xl font-bold text-red-400">{alertSummary.by_severity?.critical || 0}</p>
              </CardContent>
            </Card>
            <Card className="bg-zinc-900/60 border-zinc-800">
              <CardContent className="p-3">
                <p className="text-xs text-zinc-500">{t("cm.pages_IncidentDashboardPage.active_incidents")}</p>
                <p className="text-2xl font-bold text-amber-400">{incidents.length}</p>
              </CardContent>
            </Card>
          </div>}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Active Alerts */}
          <Card className="bg-zinc-950 border-zinc-800/70">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-zinc-300 flex items-center gap-2">
                <Bell className="w-4 h-4" />{t("cm.pages_IncidentDashboardPage.active_alerts")}<Badge variant="outline" className="text-[10px] text-zinc-400 border-zinc-700">{alerts.length}</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 max-h-[500px] overflow-y-auto">
              {alerts.length === 0 ? <div className="text-center py-8 text-zinc-500 text-sm flex flex-col items-center gap-2">
                  <CheckCircle2 className="w-6 h-6 text-emerald-500/50" />{t("cm.pages_IncidentDashboardPage.no_active_alerts")}</div> : alerts.map(a => <AlertCard key={a.id} alert={a} onAck={ackAlert} onResolve={resolveAlert} />)}
            </CardContent>
          </Card>

          {/* Incidents */}
          <Card className="bg-zinc-950 border-zinc-800/70">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-zinc-300 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" />{t("cm.pages_IncidentDashboardPage.incidents")}<Badge variant="outline" className="text-[10px] text-zinc-400 border-zinc-700">{incidents.length}</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 max-h-[500px] overflow-y-auto">
              {incidents.length === 0 ? <div className="text-center py-8 text-zinc-500 text-sm">{t("cm.pages_IncidentDashboardPage.no_incidents_recorded")}</div> : incidents.map(inc => <div key={inc.id} data-testid={`incident-${inc.id}`} className="p-3 rounded-lg border border-zinc-800 bg-zinc-900/50">
                    <div className="flex items-center justify-between">
                      <p className="text-sm text-zinc-200">{inc.title}</p>
                      <Badge variant="outline" className={`text-[10px] ${inc.severity === "P1" ? "text-red-400 border-red-500/40" : inc.severity === "P2" ? "text-amber-400 border-amber-500/40" : "text-amber-400 border-amber-500/40"}`}>{inc.severity}</Badge>
                    </div>
                    <p className="text-xs text-zinc-500 mt-1">{inc.affected_service} | {inc.status}</p>
                    <p className="text-[10px] text-zinc-600 mt-0.5">{new Date(inc.created_at).toLocaleString("tr-TR")}</p>
                  </div>)}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>;
}