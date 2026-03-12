import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import {
  ArrowLeft, Shield, Zap, Activity, Play, RefreshCw, Loader2,
  CheckCircle2, XCircle, AlertTriangle, Target, TrendingUp,
  Clock, BarChart3, Server
} from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL;

function ScoreRing({ score, size = 120, label }) {
  const color = score >= 90 ? "#34d399" : score >= 75 ? "#a3e635" : score >= 60 ? "#fbbf24" : "#f87171";
  const circumference = 2 * Math.PI * 42;
  const offset = circumference - (score / 100) * circumference;
  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size} viewBox="0 0 100 100" className="-rotate-90">
        <circle cx="50" cy="50" r="42" fill="none" stroke="#27272a" strokeWidth="6" />
        <circle cx="50" cy="50" r="42" fill="none" stroke={color} strokeWidth="6"
          strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 0.5s ease" }} />
      </svg>
      <div className="absolute flex flex-col items-center justify-center" style={{ width: size, height: size }}>
        <span className="text-2xl font-bold" style={{ color }}>{score}</span>
      </div>
      {label && <p className="text-xs text-zinc-500 mt-1">{label}</p>}
    </div>
  );
}

function CategoryCard({ name, score, weight, contribution, issues }) {
  const displayName = name.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase());
  const barColor = score >= 90 ? "bg-emerald-400" : score >= 75 ? "bg-lime-400" : score >= 60 ? "bg-amber-400" : "bg-red-400";
  return (
    <div data-testid={`category-${name}`} className="bg-zinc-900/50 rounded-lg p-3 border border-zinc-800">
      <div className="flex items-center justify-between mb-2">
        <p className="text-sm text-zinc-200">{displayName}</p>
        <span className="text-sm font-bold text-zinc-100">{score}%</span>
      </div>
      <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${Math.min(score, 100)}%`, transition: "width 0.5s ease" }} />
      </div>
      <div className="flex justify-between mt-1 text-[10px] text-zinc-600">
        <span>Weight: {weight}</span>
        <span>Contrib: {contribution}</span>
      </div>
      {issues && issues.length > 0 && (
        <div className="mt-2 space-y-0.5">
          {issues.map((iss, i) => (
            <p key={i} className="text-[10px] text-amber-400/80 flex items-center gap-1">
              <AlertTriangle className="w-2.5 h-2.5 shrink-0" /> {iss}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

function ScenarioRow({ scenario, onRun, running }) {
  return (
    <div className="flex items-center justify-between p-2 bg-zinc-800/40 rounded-lg border border-zinc-800/60">
      <div className="flex-1 min-w-0">
        <p className="text-xs text-zinc-200 truncate">{scenario.name}</p>
        <p className="text-[10px] text-zinc-600 truncate">{scenario.description}</p>
      </div>
      <Button size="sm" variant="ghost" onClick={() => onRun(scenario.id)}
        disabled={running} className="h-7 text-xs text-zinc-400 shrink-0 ml-2">
        {running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
      </Button>
    </div>
  );
}

export default function GoLiveDashboardPage() {
  const navigate = useNavigate();
  const [goliveScore, setGoliveScore] = useState(null);
  const [scenarios, setScenarios] = useState({});
  const [validationReport, setValidationReport] = useState(null);
  const [drillHistory, setDrillHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [runningScenario, setRunningScenario] = useState(null);
  const [runningDrill, setRunningDrill] = useState(null);

  const token = localStorage.getItem("token") || localStorage.getItem("access_token");
  const headers = { Authorization: `Bearer ${token}` };

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [scoreRes, scenariosRes, reportRes, drillsRes] = await Promise.all([
        axios.get(`${API}/api/validation/golive-score`, { headers }),
        axios.get(`${API}/api/validation/scenarios`, { headers }),
        axios.get(`${API}/api/validation/report?hours=72`, { headers }),
        axios.get(`${API}/api/validation/drills/history?limit=10`, { headers }),
      ]);
      setGoliveScore(scoreRes.data?.data || null);
      setScenarios(scenariosRes.data?.data?.scenarios || {});
      setValidationReport(reportRes.data?.data || null);
      setDrillHistory(drillsRes.data?.data?.drills || []);
    } catch (err) {
      console.error("Fetch error:", err);
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const runScenario = async (type, id) => {
    setRunningScenario(id);
    try {
      await axios.post(`${API}/api/validation/run`,
        { scenario_type: type, scenario_id: id }, { headers });
      fetchAll();
    } catch (e) { console.error(e); }
    setRunningScenario(null);
  };

  const runDrill = async (drillId) => {
    setRunningDrill(drillId);
    try {
      await axios.post(`${API}/api/validation/drills/execute`,
        { drill_id: drillId }, { headers });
      fetchAll();
    } catch (e) { console.error(e); }
    setRunningDrill(null);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-zinc-500" />
      </div>
    );
  }

  const maturityColor = {
    "Foundation": "text-red-400",
    "Developing": "text-orange-400",
    "Capable": "text-amber-400",
    "Production Ready": "text-lime-400",
    "Elite": "text-emerald-400",
  };

  return (
    <div data-testid="golive-dashboard" className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="text-zinc-400">
              <ArrowLeft className="w-4 h-4 mr-1" /> Back
            </Button>
            <div>
              <h1 className="text-xl font-bold flex items-center gap-2">
                <Target className="w-5 h-5" /> Go-Live Readiness Center
              </h1>
              <p className="text-xs text-zinc-500">Runtime validation, drills & maturity scoring</p>
            </div>
          </div>
          <Button data-testid="refresh-golive-btn" size="sm" variant="outline" onClick={fetchAll}
            className="border-zinc-700 bg-zinc-900 text-zinc-300">
            <RefreshCw className="w-3 h-3 mr-1" /> Refresh
          </Button>
        </div>

        {/* Top Score Row */}
        {goliveScore && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            {/* Score Ring */}
            <Card className="bg-zinc-900/60 border-zinc-800 md:col-span-1">
              <CardContent className="p-6 flex flex-col items-center justify-center relative">
                <ScoreRing score={goliveScore.overall_score} />
                <Badge data-testid="maturity-badge" variant="outline"
                  className={`mt-2 text-xs ${maturityColor[goliveScore.maturity_name] || "text-zinc-400"} border-current/40`}>
                  Level {goliveScore.maturity_level}: {goliveScore.maturity_name}
                </Badge>
                <Badge data-testid="golive-status" variant="outline"
                  className={`mt-1 text-[10px] ${goliveScore.go_live_ready ? "text-emerald-400 border-emerald-500/40" : "text-red-400 border-red-500/40"}`}>
                  {goliveScore.go_live_ready ? "Go-Live Ready" : "Not Ready"}
                </Badge>
              </CardContent>
            </Card>

            {/* Category Breakdown */}
            <Card className="bg-zinc-900/60 border-zinc-800 md:col-span-3">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-zinc-300 flex items-center gap-2">
                  <BarChart3 className="w-4 h-4" /> Category Breakdown
                </CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-2 lg:grid-cols-4 gap-2">
                {Object.entries(goliveScore.categories || {}).map(([name, info]) => (
                  <CategoryCard key={name} name={name} {...info} />
                ))}
              </CardContent>
            </Card>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Validation Scenarios */}
          <Card className="bg-zinc-950 border-zinc-800/70 lg:col-span-2">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-zinc-300 flex items-center gap-2">
                <Zap className="w-4 h-4" /> Validation Scenarios
              </CardTitle>
            </CardHeader>
            <CardContent>
              {Object.entries(scenarios).map(([type, items]) => (
                <div key={type} className="mb-4">
                  <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
                    {type}
                  </p>
                  <div className="space-y-1.5">
                    {items.map((s) => (
                      <ScenarioRow key={s.id} scenario={s}
                        running={runningScenario === s.id}
                        onRun={() => runScenario(type, s.id)} />
                    ))}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Drills + Report */}
          <div className="space-y-4">
            {/* Validation Report */}
            {validationReport && (
              <Card data-testid="validation-report" className="bg-zinc-900/60 border-zinc-800">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-zinc-300 flex items-center gap-2">
                    <TrendingUp className="w-4 h-4" /> Validation Report (72h)
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-3 gap-2 mb-3">
                    <div className="text-center">
                      <p className="text-lg font-bold text-zinc-100">{validationReport.total_runs}</p>
                      <p className="text-[10px] text-zinc-500">Total</p>
                    </div>
                    <div className="text-center">
                      <p className="text-lg font-bold text-emerald-400">{validationReport.passed}</p>
                      <p className="text-[10px] text-zinc-500">Passed</p>
                    </div>
                    <div className="text-center">
                      <p className="text-lg font-bold text-red-400">{validationReport.failed}</p>
                      <p className="text-[10px] text-zinc-500">Failed</p>
                    </div>
                  </div>
                  <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden">
                    <div className="h-full bg-emerald-400 rounded-full"
                      style={{ width: `${validationReport.pass_rate}%` }} />
                  </div>
                  <p className="text-center text-[10px] text-zinc-500 mt-1">{validationReport.pass_rate}% pass rate</p>
                </CardContent>
              </Card>
            )}

            {/* Incident Drills */}
            <Card className="bg-zinc-900/60 border-zinc-800">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-zinc-300 flex items-center gap-2">
                  <Shield className="w-4 h-4" /> Incident Drills
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {["worker_failure", "provider_outage", "database_latency", "cache_failure", "concurrent_mutation_storm"].map((id) => (
                  <Button key={id} data-testid={`drill-${id}`} size="sm" variant="outline"
                    onClick={() => runDrill(id)} disabled={runningDrill === id}
                    className="w-full justify-start h-8 text-xs border-zinc-700 text-zinc-400">
                    {runningDrill === id ? <Loader2 className="w-3 h-3 animate-spin mr-2" /> : <Play className="w-3 h-3 mr-2" />}
                    {id.replace(/_/g, " ")}
                  </Button>
                ))}
              </CardContent>
            </Card>

            {/* Drill History */}
            <Card className="bg-zinc-900/60 border-zinc-800">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-zinc-300 flex items-center gap-2">
                  <Clock className="w-4 h-4" /> Recent Drills
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5 max-h-60 overflow-y-auto">
                {drillHistory.length === 0 ? (
                  <p className="text-xs text-zinc-600 text-center py-4">No drills executed yet</p>
                ) : (
                  drillHistory.map((d) => (
                    <div key={d.id} className="flex items-center justify-between text-xs p-2 rounded bg-zinc-800/40 border border-zinc-800/60">
                      <div>
                        <p className="text-zinc-300">{d.drill_name}</p>
                        <p className="text-[10px] text-zinc-600">{new Date(d.started_at).toLocaleString("tr-TR")}</p>
                      </div>
                      {d.detection_within_threshold
                        ? <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                        : <XCircle className="w-4 h-4 text-red-400 shrink-0" />
                      }
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
