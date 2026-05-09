import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";
import {
  TrendingUp, TrendingDown, Minus, Award, Shield, Clock,
  ArrowUpRight, ArrowDownRight, BarChart3, RefreshCw,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { toast } from "sonner";
import { useTranslation } from 'react-i18next';

const CHART_COLORS = {
  sync: "#10b981",
  drift: "#f59e0b",
  mttr: "#3b82f6",
  sla: "#a855f7",
  p95: "#ef4444",
};

function CustomTooltip({ active, payload, label }) {
  const { t } = useTranslation();
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 shadow-xl">
      <p className="text-[10px] text-zinc-500 mb-1">{label}</p>
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2 text-xs">
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
          <span className="text-zinc-400">{p.name}:</span>
          <span className="text-zinc-100 font-mono font-medium">{p.value}</span>
        </div>
      ))}
    </div>
  );
}

function ImprovementCard({ icon, label, delta, unit, invertGood, testId }) {
  const isPositive = invertGood ? delta < 0 : delta > 0;
  const isNegative = invertGood ? delta > 0 : delta < 0;
  const trendIcon = delta > 0 ? <ArrowUpRight className="h-4 w-4" /> : delta < 0 ? <ArrowDownRight className="h-4 w-4" /> : <Minus className="h-4 w-4" />;
  const trendColor = isPositive ? "text-emerald-400" : isNegative ? "text-red-400" : "text-zinc-500";
  const borderColor = isPositive ? "border-emerald-500/20" : isNegative ? "border-red-500/20" : "border-zinc-800";
  const sign = delta > 0 ? "+" : "";

  return (
    <div className={`bg-zinc-900/80 border ${borderColor} rounded-xl p-5 transition-all hover:border-zinc-600`} data-testid={testId}>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-zinc-500">{icon}</span>
        <span className="text-xs text-zinc-500 font-medium">{label}</span>
      </div>
      <div className={`flex items-center gap-2 text-2xl font-bold font-mono ${trendColor}`}>
        {trendIcon}
        <span>{sign}{delta}{unit}</span>
      </div>
      <div className="text-[10px] text-zinc-600 mt-1.5">
        {isPositive ? "Iyilesiyor" : isNegative ? "Kotulesme" : "Degisim yok"} (ilk hafta → son hafta)
      </div>
    </div>
  );
}

export function WeeklyProof() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [weeks, setWeeks] = useState(8);

  const fetchData = useCallback(async (showToast = false) => {
    try {
      const res = await axios.get(`/ops/dashboard/channel-health/weekly-proof?weeks=${weeks}`);
      setData(res.data);
      if (showToast) toast.success("Haftalık veriler güncellendi");
    } catch (err) {
      toast.error("Haftalık veri yüklenemedi", { description: err.message });
    } finally {
      setLoading(false);
    }
  }, [weeks]);

  useEffect(() => {
    setLoading(true);
    fetchData();
  }, [fetchData]);

  if (loading) {
    return (
      <div className="space-y-4" data-testid="weekly-proof-loading">
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-28 bg-zinc-800" />)}
        </div>
        <Skeleton className="h-64 bg-zinc-800" />
      </div>
    );
  }

  if (!data || !data.weeks?.length) {
    return (
      <div className="text-center py-16 text-zinc-500" data-testid="weekly-proof-empty">
        <BarChart3 className="h-12 w-12 mx-auto mb-3 opacity-30" />
        <p className="text-sm">{t('cm.components_WeeklyProofDashboard.haftalik_veri_bulunamadi')}</p>
      </div>
    );
  }

  const imp = data.improvements || {};
  const chartData = data.weeks.map(w => ({
    week: w.week_label,
    dates: `${w.week_start.slice(5)} → ${w.week_end.slice(5)}`,
    "Sync %": w.sync_success_rate,
    "SLA %": w.sla_compliance,
    "Drift": w.drift_count,
    "MTTR (s)": w.mttr_hours,
    "p95 (ms)": w.push_latency_p95,
  }));

  return (
    <div className="space-y-6" data-testid="weekly-proof-dashboard">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Award className="h-4 w-4 text-amber-400" />
          <span className="text-xs text-zinc-400 font-mono">
            {t('cm.components_WeeklyProofDashboard.deger_kaniti_hafta_hafta_iyilesme')}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex bg-zinc-900 border border-zinc-800 rounded-lg p-0.5" data-testid="weeks-selector">
            {[4, 8, 12].map(w => (
              <button key={w} onClick={() => setWeeks(w)}
                className={`px-3 py-1 text-xs rounded-md font-medium transition-colors ${weeks === w ? "bg-zinc-700 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"}`}
                data-testid={`weeks-${w}`}>
                {w}h
              </button>
            ))}
          </div>
          <Button variant="ghost" size="sm" className="h-7 text-xs text-zinc-500" onClick={() => { setLoading(true); fetchData(true); }} data-testid="weekly-proof-refresh">
            <RefreshCw className="h-3 w-3 mr-1" />{t('cm.components_WeeklyProofDashboard.yenile')}
          </Button>
        </div>
      </div>

      {/* Improvement cards */}
      {Object.keys(imp).length > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3" data-testid="improvement-cards">
          <ImprovementCard icon={<TrendingUp className="h-4 w-4" />} label="Sync Basari" delta={imp.sync_success_delta ?? 0} unit="%" testId="imp-sync" />
          <ImprovementCard icon={<TrendingDown className="h-4 w-4" />} label={t('cm.components_WeeklyProofDashboard.drift_sayisi')} delta={imp.drift_delta ?? 0} unit="" invertGood testId="imp-drift" />
          <ImprovementCard icon={<Clock className="h-4 w-4" />} label="MTTR" delta={imp.mttr_delta ?? 0} unit="s" invertGood testId="imp-mttr" />
          <ImprovementCard icon={<Shield className="h-4 w-4" />} label="SLA Uyum" delta={imp.sla_delta ?? 0} unit="%" testId="imp-sla" />
          <ImprovementCard icon={<BarChart3 className="h-4 w-4" />} label="Push p95" delta={imp.push_p95_delta ?? 0} unit="ms" invertGood testId="imp-p95" />
        </div>
      )}

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-zinc-500" /> Sync & SLA Trendi
            </CardTitle>
          </CardHeader>
          <CardContent data-testid="chart-sync-sla-weekly">
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                <XAxis dataKey="week" tick={{ fontSize: 10, fill: "#71717a" }} />
                <YAxis tick={{ fontSize: 10, fill: "#71717a" }} domain={[0, 100]} tickFormatter={v => `${v}%`} />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                <Line type="monotone" dataKey="Sync %" stroke={CHART_COLORS.sync} strokeWidth={2} dot={{ r: 3 }} />
                <Line type="monotone" dataKey="SLA %" stroke={CHART_COLORS.sla} strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
              <TrendingDown className="h-4 w-4 text-zinc-500" /> Drift & MTTR Trendi
            </CardTitle>
          </CardHeader>
          <CardContent data-testid="chart-drift-mttr-weekly">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                <XAxis dataKey="week" tick={{ fontSize: 10, fill: "#71717a" }} />
                <YAxis tick={{ fontSize: 10, fill: "#71717a" }} />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                <Bar dataKey="Drift" fill={CHART_COLORS.drift} radius={[3, 3, 0, 0]} />
                <Bar dataKey="MTTR (s)" fill={CHART_COLORS.mttr} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Push latency p95 weekly */}
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-zinc-500" /> {t('cm.components_WeeklyProofDashboard.push_latency_p95_haftalik')}
          </CardTitle>
        </CardHeader>
        <CardContent data-testid="chart-p95-weekly">
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
              <XAxis dataKey="week" tick={{ fontSize: 10, fill: "#71717a" }} />
              <YAxis tick={{ fontSize: 10, fill: "#71717a" }} tickFormatter={v => `${v}ms`} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="p95 (ms)" fill={CHART_COLORS.p95} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
}
