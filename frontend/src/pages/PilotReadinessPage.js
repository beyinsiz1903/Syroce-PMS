import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import {
  ArrowLeft, CheckCircle2, XCircle, AlertTriangle, Shield,
  RefreshCw, Loader2, Rocket, ToggleLeft, ToggleRight
} from "lucide-react";

const API = import.meta.env.VITE_BACKEND_URL;

function CheckItem({ item }) {
  const icon = item.passed
    ? <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
    : item.severity === "critical"
      ? <XCircle className="w-4 h-4 text-red-400 shrink-0" />
      : <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />;

  return (
    <div data-testid={`check-${item.id}`} className={`flex items-center gap-3 p-3 rounded-lg border ${
      item.passed ? "bg-emerald-950/20 border-emerald-900/30" : "bg-red-950/20 border-red-900/30"
    }`}>
      {icon}
      <div className="flex-1 min-w-0">
        <p className="text-sm text-zinc-200">{item.name}</p>
        <p className="text-[11px] text-zinc-500">{item.category} | {item.auto_check ? "Auto" : "Manual sign-off"}</p>
      </div>
      <Badge variant="outline" className={`text-[10px] ${
        item.severity === "critical" ? "border-red-500/40 text-red-400" : "border-amber-500/40 text-amber-400"
      }`}>{item.severity}</Badge>
    </div>
  );
}

export default function PilotReadinessPage() {
  const navigate = useNavigate();
  const [readiness, setReadiness] = useState(null);
  const [toggles, setToggles] = useState([]);
  const [loading, setLoading] = useState(true);

  const token = localStorage.getItem("token") || localStorage.getItem("access_token");
  const headers = { Authorization: `Bearer ${token}` };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [readRes, toggleRes] = await Promise.all([
        axios.get(`${API}/api/pilot/readiness`, { headers }),
        axios.get(`${API}/api/pilot/feature-toggles`, { headers }),
      ]);
      setReadiness(readRes.data?.data || readRes.data);
      setToggles(toggleRes.data?.data?.toggles || []);
    } catch (err) {
      console.error("Pilot readiness error:", err);
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const toggleFeature = async (feature, enabled) => {
    try {
      await axios.post(`${API}/api/pilot/feature-toggles`, { feature, enabled: !enabled }, { headers });
      fetchData();
    } catch (err) {
      console.error("Toggle error:", err);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-zinc-500" />
      </div>
    );
  }

  const score = readiness?.score || 0;
  const scoreColor = score >= 90 ? "text-emerald-400" : score >= 60 ? "text-amber-400" : "text-red-400";
  const ringColor = score >= 90 ? "stroke-emerald-400" : score >= 60 ? "stroke-amber-400" : "stroke-red-400";

  return (
    <div data-testid="pilot-readiness-page" className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-5xl mx-auto px-4 py-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="text-zinc-400">
              <ArrowLeft className="w-4 h-4 mr-1" /> Back
            </Button>
            <div>
              <h1 className="text-xl font-bold flex items-center gap-2"><Rocket className="w-5 h-5" /> Pilot Readiness</h1>
              <p className="text-xs text-zinc-500">Pre-pilot validation & feature toggles</p>
            </div>
          </div>
          <Button data-testid="refresh-readiness-btn" size="sm" variant="outline" onClick={fetchData}
            className="border-zinc-700 bg-zinc-900 text-zinc-300">
            <RefreshCw className="w-3 h-3 mr-1" /> Refresh
          </Button>
        </div>

        {/* Score Card */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <Card className="bg-zinc-900/60 border-zinc-800 md:col-span-1">
            <CardContent className="p-6 flex flex-col items-center justify-center">
              <div className="relative w-28 h-28">
                <svg className="w-28 h-28 -rotate-90" viewBox="0 0 100 100">
                  <circle cx="50" cy="50" r="42" stroke="currentColor" strokeWidth="6" fill="none" className="text-zinc-800" />
                  <circle cx="50" cy="50" r="42" strokeWidth="6" fill="none" strokeDasharray={`${score * 2.64} 264`}
                    strokeLinecap="round" className={ringColor} />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className={`text-2xl font-bold ${scoreColor}`}>{score}%</span>
                </div>
              </div>
              <p className="mt-2 text-sm text-zinc-400">Readiness Score</p>
              <Badge data-testid="pilot-status" variant="outline" className={`mt-1 ${readiness?.ready_for_pilot ? "text-emerald-400 border-emerald-500/40" : "text-red-400 border-red-500/40"}`}>
                {readiness?.ready_for_pilot ? "Ready for Pilot" : "Not Ready"}
              </Badge>
            </CardContent>
          </Card>

          <Card className="bg-zinc-900/60 border-zinc-800 md:col-span-2">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-zinc-300">Critical Blockers</CardTitle>
            </CardHeader>
            <CardContent>
              {readiness?.critical_blockers?.length === 0 ? (
                <div className="flex items-center gap-2 text-emerald-400 text-sm py-4">
                  <CheckCircle2 className="w-5 h-5" /> No critical blockers!
                </div>
              ) : (
                <div className="space-y-2">
                  {(readiness?.critical_blockers || []).map((b) => (
                    <div key={b.id} className="flex items-center gap-2 text-red-400 text-sm">
                      <XCircle className="w-4 h-4" /> {b.name} <span className="text-zinc-600 text-xs">({b.category})</span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Checklist */}
          <Card className="bg-zinc-950 border-zinc-800/70">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-zinc-300 flex items-center gap-2">
                <Shield className="w-4 h-4" /> Validation Checklist
                <Badge variant="outline" className="text-[10px] text-zinc-400 border-zinc-700">
                  {readiness?.passed}/{readiness?.total}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {(readiness?.checklist || []).map((item) => (
                <CheckItem key={item.id} item={item} />
              ))}
            </CardContent>
          </Card>

          {/* Feature Toggles */}
          <Card className="bg-zinc-950 border-zinc-800/70">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-zinc-300 flex items-center gap-2">
                <ToggleLeft className="w-4 h-4" /> Feature Toggles
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {toggles.map((t) => (
                <div key={t.feature} data-testid={`toggle-${t.feature}`}
                  className="flex items-center justify-between p-3 rounded-lg bg-zinc-900/50 border border-zinc-800">
                  <div>
                    <p className="text-sm text-zinc-200">{t.feature.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase())}</p>
                    <p className="text-[11px] text-zinc-500">{t.description || ""}</p>
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => toggleFeature(t.feature, t.enabled)}
                    className={t.enabled ? "text-emerald-400" : "text-zinc-500"}>
                    {t.enabled ? <ToggleRight className="w-5 h-5" /> : <ToggleLeft className="w-5 h-5" />}
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
