import { useTranslation } from 'react-i18next';
import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";

const API = "";

function StatusBadge({ status }) {
  const colors = {
    completed: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    running: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    failed: "bg-red-500/20 text-red-400 border-red-500/30",
    ready: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
    deployed: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    stale: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    high: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    medium: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    low: "bg-red-500/20 text-red-400 border-red-500/30",
  };
  return (
    <span data-testid={`status-badge-${status}`} className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${colors[status] || "bg-slate-500/20 text-slate-400 border-slate-500/30"}`}>
      {status}
    </span>
  );
}

function MetricCard({ title, value, subtitle, testId }) {
  return (
    <Card data-testid={testId} className="bg-slate-900/60 border-slate-700/50">
      <CardContent className="p-4">
        <p className="text-xs text-slate-400 uppercase tracking-wider">{title}</p>
        <p className="text-2xl font-bold text-white mt-1">{value}</p>
        {subtitle && <p className="text-xs text-slate-500 mt-1">{subtitle}</p>}
      </CardContent>
    </Card>
  );
}

export default function DataPipelineDashboard() {
  const { t } = useTranslation();
  const [health, setHealth] = useState(null);
  const [runs, setRuns] = useState([]);
  const [predictions, setPredictions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState(null);

  const token = localStorage.getItem("token") || sessionStorage.getItem("token");
  const headers = { Authorization: `Bearer ${token}` };

  const fetchData = useCallback(async () => {
    try {
      const [healthRes, runsRes, predsRes] = await Promise.all([
        axios.get(`/data-pipeline/health`, { headers }),
        axios.get(`/data-pipeline/runs?limit=10`, { headers }),
        axios.get(`/data-pipeline/predictions/confidence`, { headers }),
      ]);
      setHealth(healthRes.data);
      setRuns(runsRes.data);
      setPredictions(predsRes.data);
    } catch (err) {
      console.error("Failed to fetch pipeline data:", err);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const executePipeline = async (modelType) => {
    setExecuting(modelType);
    try {
      await axios.post(`/data-pipeline/runs/execute?model_type=${modelType}`, {}, { headers });
      toast.success(`${modelType} pipeline tamamlandi`);
      fetchData();
    } catch (err) {
      toast.error("Pipeline calistirilamadi");
    } finally {
      setExecuting(null);
    }
  };

  if (loading) return <div className="flex items-center justify-center h-96"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-cyan-500" /></div>;

  const featureSets = health?.feature_store?.feature_sets || [];
  const staleModels = health?.stale_models || [];
  const stalePredictions = health?.stale_predictions || [];
  const modelTypes = health?.model_registry?.model_types || {};
  const predModels = predictions?.models || [];

  return (
    <div data-testid="data-pipeline-dashboard" className="space-y-6 p-6 bg-slate-950 min-h-screen">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">{t("techDashboards.dataPipeline")}</h1>
          <p className="text-sm text-slate-400 mt-1">ML model veri hatti yönetimi</p>
        </div>
        <div className="flex gap-2">
          {["revenue_ml", "operational_ai", "guest_intelligence"].map((mt) => (
            <Button
              key={mt}
              data-testid={`run-pipeline-${mt}`}
              onClick={() => executePipeline(mt)}
              disabled={executing === mt}
              size="sm"
              className="bg-cyan-600 hover:bg-cyan-700 text-white"
            >
              {executing === mt ? "Calisiyor..." : `${mt.replace("_", " ")} Calistir`}
            </Button>
          ))}
        </div>
      </div>

      {/* Top Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard testId="metric-feature-sets" title="Feature Sets" value={featureSets.length || "0"} subtitle={`${health?.feature_store?.available_sets?.length || 3} mevcut`} />
        <MetricCard testId="metric-models" title="Modeller" value={Object.keys(modelTypes).length || "0"} subtitle="Kayıtlı model tipi" />
        <MetricCard testId="metric-stale" title="Stale Uyarilar" value={(staleModels.length + stalePredictions.length) || "0"} subtitle="Dikkat gerektiren" />
        <MetricCard testId="metric-runs" title="Pipeline Runs" value={runs.length || "0"} subtitle="Son calistirmalar" />
      </div>

      <Tabs defaultValue="runs" className="space-y-4">
        <TabsList className="bg-slate-800/80 border-slate-700">
          <TabsTrigger value="runs" data-testid="tab-runs" className="data-[state=active]:bg-cyan-600">Pipeline Runs</TabsTrigger>
          <TabsTrigger value="predictions" data-testid="tab-predictions" className="data-[state=active]:bg-cyan-600">Predictions</TabsTrigger>
          <TabsTrigger value="features" data-testid="tab-features" className="data-[state=active]:bg-cyan-600">Feature Store</TabsTrigger>
          <TabsTrigger value="stale" data-testid="tab-stale" className="data-[state=active]:bg-cyan-600">Stale Alerts</TabsTrigger>
        </TabsList>

        <TabsContent value="runs">
          <Card className="bg-slate-900/60 border-slate-700/50">
            <CardHeader><CardTitle className="text-white text-base">Son Pipeline Calistirmalari</CardTitle></CardHeader>
            <CardContent>
              {runs.length === 0 ? (
                <p className="text-slate-500 text-sm">Henüz pipeline calistirilmamis</p>
              ) : (
                <div className="space-y-3">
                  {runs.map((run, i) => (
                    <div key={run.id || i} data-testid={`pipeline-run-${i}`} className="flex items-center justify-between p-3 rounded-lg bg-slate-800/50 border border-slate-700/40">
                      <div>
                        <p className="text-sm font-medium text-white">{run.model_type}</p>
                        <p className="text-xs text-slate-400">{new Date(run.started_at).toLocaleString("tr-TR")}</p>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-slate-500">{Object.keys(run.steps || {}).length} adim</span>
                        <StatusBadge status={run.status} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="predictions">
          <Card className="bg-slate-900/60 border-slate-700/50">
            <CardHeader><CardTitle className="text-white text-base">Prediction Guven Ozeti</CardTitle></CardHeader>
            <CardContent>
              {predModels.length === 0 ? (
                <p className="text-slate-500 text-sm">Henüz tahmin uretilmemis</p>
              ) : (
                <div className="space-y-3">
                  {predModels.map((m, i) => (
                    <div key={i} data-testid={`prediction-model-${i}`} className="p-3 rounded-lg bg-slate-800/50 border border-slate-700/40">
                      <div className="flex items-center justify-between mb-2">
                        <p className="text-sm font-medium text-white">{m.model_type}</p>
                        <StatusBadge status={m.avg_confidence >= 0.75 ? "high" : m.avg_confidence >= 0.5 ? "medium" : "low"} />
                      </div>
                      <div className="grid grid-cols-3 gap-2">
                        <div>
                          <p className="text-xs text-slate-500">Toplam</p>
                          <p className="text-sm text-white font-medium">{m.total_predictions}</p>
                        </div>
                        <div>
                          <p className="text-xs text-slate-500">Ort. Guven</p>
                          <p className="text-sm text-white font-medium">{(m.avg_confidence * 100).toFixed(1)}%</p>
                        </div>
                        <div>
                          <p className="text-xs text-slate-500">Son Tahmin</p>
                          <p className="text-xs text-slate-300">{m.latest_prediction ? new Date(m.latest_prediction).toLocaleTimeString("tr-TR") : "-"}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="features">
          <Card className="bg-slate-900/60 border-slate-700/50">
            <CardHeader><CardTitle className="text-white text-base">Feature Store</CardTitle></CardHeader>
            <CardContent>
              {featureSets.length === 0 ? (
                <p className="text-slate-500 text-sm">Feature extraction henüz yapilmamis. Pipeline calistirin.</p>
              ) : (
                <div className="space-y-3">
                  {featureSets.map((fs, i) => (
                    <div key={i} data-testid={`feature-set-${i}`} className="p-3 rounded-lg bg-slate-800/50 border border-slate-700/40">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-white">{fs.name}</p>
                        <Badge variant="outline" className="text-cyan-400 border-cyan-500/30">{fs.defined_features} feature</Badge>
                      </div>
                      <p className="text-xs text-slate-400 mt-1">{fs.total_extractions} extraction | {fs.record_count} kayıt</p>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="stale">
          <Card className="bg-slate-900/60 border-slate-700/50">
            <CardHeader><CardTitle className="text-white text-base">Stale Model & Prediction Uyarilari</CardTitle></CardHeader>
            <CardContent>
              {staleModels.length === 0 && stalePredictions.length === 0 ? (
                <p className="text-emerald-400 text-sm">Tüm modeller ve tahminler güncel</p>
              ) : (
                <div className="space-y-2">
                  {stalePredictions.map((sp, i) => (
                    <div key={i} data-testid={`stale-prediction-${i}`} className="flex items-center justify-between p-3 rounded-lg bg-amber-900/20 border border-amber-700/30">
                      <div>
                        <p className="text-sm text-amber-300">{sp.model_type}</p>
                        <p className="text-xs text-amber-500">Son tahmin: {sp.last_prediction || "Yok"}</p>
                      </div>
                      <StatusBadge status="stale" />
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
