import { useTranslation } from 'react-i18next';
import React, { useState, useEffect, useCallback } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import {
  TrendingUp, TrendingDown, Brain, Users, Activity, Shield,
  AlertTriangle, Target, Zap, BarChart3, Clock, Star,
  ArrowUpRight, ArrowDownRight, Loader2, RefreshCw, ChevronRight,
} from 'lucide-react';

const API = "";

function useAuth() {
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
  return { token, headers };
}

async function fetchAPI(path, headers) {
  const res = await fetch(`${API}${path}`, { credentials: "include", headers });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// ═══════════════════════════════════════════════════════════
// MINI COMPONENTS
// ═══════════════════════════════════════════════════════════

function StatCard({ title, value, subtitle, icon: Icon, trend, color = 'blue', testId }) {
  const colors = {
    blue: 'from-blue-500/10 to-blue-600/5 border-blue-500/20',
    green: 'from-emerald-500/10 to-emerald-600/5 border-emerald-500/20',
    amber: 'from-amber-500/10 to-amber-600/5 border-amber-500/20',
    red: 'from-red-500/10 to-red-600/5 border-red-500/20',
    purple: 'from-violet-500/10 to-violet-600/5 border-violet-500/20',
  };
  return (
    <div data-testid={testId} className={`rounded-xl border bg-gradient-to-br ${colors[color] || colors.blue} p-4`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{title}</span>
        {Icon && <Icon className="h-4 w-4 text-muted-foreground" />}
      </div>
      <div className="text-2xl font-bold">{value}</div>
      {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
      {trend !== undefined && (
        <div className={`flex items-center gap-1 mt-1 text-xs ${trend >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
          {trend >= 0 ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
          {Math.abs(trend)}%
        </div>
      )}
    </div>
  );
}

function ConfidenceBadge({ band }) {
  const map = {
    high: { label: 'Yüksek Guven', cls: 'bg-emerald-100 text-emerald-800 border-emerald-200' },
    medium: { label: 'Orta Guven', cls: 'bg-amber-100 text-amber-800 border-amber-200' },
    low: { label: 'Düşük Guven', cls: 'bg-red-100 text-red-800 border-red-200' },
  };
  const m = map[band] || map.low;
  return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${m.cls}`}>{m.label}</span>;
}

function PressureBadge({ score }) {
  if (score > 70) return <Badge variant="destructive" className="text-xs">Kritik ({score})</Badge>;
  if (score > 40) return <Badge className="bg-amber-100 text-amber-800 text-xs border-amber-200">Orta ({score})</Badge>;
  return <Badge className="bg-emerald-100 text-emerald-800 text-xs border-emerald-200">Normal ({score})</Badge>;
}

function LoadingState() {
  return (
    <div data-testid="loading-state" className="flex items-center justify-center py-20">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      <span className="ml-3 text-muted-foreground">Veriler yükleniyor...</span>
    </div>
  );
}

function ErrorState({ message, onRetry }) {
  return (
    <div data-testid="error-state" className="flex flex-col items-center justify-center py-20">
      <AlertTriangle className="h-10 w-10 text-red-400 mb-3" />
      <p className="text-sm text-muted-foreground mb-3">{message || 'Veri yuklenirken hata olustu'}</p>
      {onRetry && <Button variant="outline" size="sm" onClick={onRetry}><RefreshCw className="h-3 w-3 mr-1" />Tekrar Dene</Button>}
    </div>
  );
}

function EmptyState({ message }) {
  return (
    <div data-testid="empty-state" className="flex flex-col items-center justify-center py-16">
      <BarChart3 className="h-10 w-10 text-muted-foreground/40 mb-3" />
      <p className="text-sm text-muted-foreground">{message || 'Henüz veri bulunmuyor'}</p>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// 1. REVENUE INTELLIGENCE TAB
// ═══════════════════════════════════════════════════════════

function RevenueTab() {
  const { headers } = useAuth();
  const [data, setData] = useState(null);
  const [pipelineResult, setPipelineResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const d = await fetchAPI('/api/data-intelligence/revenue/forecast-dashboard', headers);
      setData(d);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const runPipeline = async () => {
    setRunning(true);
    try {
      const result = await fetch(`/api/data-intelligence/revenue/run-pipeline`, { credentials: "include",
        method: 'POST', headers, body: JSON.stringify({}),
      }).then(r => r.json());
      setPipelineResult(result);
      await loadData();
    } catch (e) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={loadData} />;
  if (!data) return <EmptyState message="Revenue verisi bulunamadı" />;

  const forecast = data.demand_forecast || {};
  const forecastList = forecast.forecast || [];
  const cancellation = data.cancellation_risk || {};
  const autopricing = data.autopricing || {};
  const recs = data.ml_recommendations || [];

  return (
    <div data-testid="revenue-tab" className="space-y-6">
      {/* Action Bar */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Revenue Intelligence</h3>
          <p className="text-sm text-muted-foreground">ML tabanli fiyatlama oneri ve talep tahmin sistemi</p>
        </div>
        <Button data-testid="run-pipeline-btn" onClick={runPipeline} disabled={running} size="sm">
          {running ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Zap className="h-4 w-4 mr-1" />}
          {running ? 'Calistiriliyor...' : 'Pipeline Calistir'}
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard testId="forecast-avg-occ" title="Ort. Doluluk (14g)" value={`${forecastList.length > 0 ? Math.round(forecastList.reduce((s, f) => s + (f.predicted_occupancy_pct || 0), 0) / forecastList.length) : 0}%`} icon={BarChart3} color="blue" />
        <StatCard testId="at-risk-count" title="Riskli Rez." value={cancellation.at_risk_count || 0} subtitle={`${(cancellation.at_risk_revenue || 0).toLocaleString()} TL risk`} icon={AlertTriangle} color="red" />
        <StatCard testId="pending-recs" title="Bekleyen Oneri" value={autopricing.pending_count || 0} icon={Target} color="amber" />
        <StatCard testId="applied-recs" title="Uygulanan" value={autopricing.stats?.applied || 0} icon={TrendingUp} color="green" />
      </div>

      {/* Pipeline Result */}
      {pipelineResult && pipelineResult.recommendations && (
        <Card data-testid="pipeline-result">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Pipeline Sonuclari</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {pipelineResult.recommendations.map((rec, i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-muted/50 border">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-sm">{rec.room_type}</span>
                      <ConfidenceBadge band={rec.confidence_band} />
                      {rec.auto_eligible && <Badge variant="outline" className="text-xs">Auto Uygun</Badge>}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span>Mevcut: {rec.current_rate?.toLocaleString()} TL</span>
                      <ChevronRight className="h-3 w-3" />
                      <span className="font-medium text-foreground">Önerilen: {rec.suggested_rate?.toLocaleString()} TL</span>
                      <span className={rec.direction === 'increase' ? 'text-emerald-600' : 'text-red-500'}>
                        ({rec.direction === 'increase' ? '+' : ''}{rec.change_pct}%)
                      </span>
                    </div>
                    {/* Explainability */}
                    {rec.recommendation_reasons && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {rec.recommendation_reasons.map((r, j) => (
                          <span key={j} className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-background border">
                            {r.direction === 'up' ? <TrendingUp className="h-3 w-3 mr-1 text-emerald-500" /> : <TrendingDown className="h-3 w-3 mr-1 text-red-400" />}
                            {r.detail}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="text-right ml-4">
                    <div className="text-lg font-bold">{Math.round((rec.confidence_score || 0) * 100)}%</div>
                    <div className="text-xs text-muted-foreground">guven</div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Demand Forecast Chart (table-style) */}
      <Card data-testid="demand-forecast">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Talep Tahmini (14 Gun)</CardTitle>
        </CardHeader>
        <CardContent>
          {forecastList.length === 0 ? <EmptyState message="Tahmin verisi yok" /> : (
            <div className="space-y-1.5">
              {forecastList.slice(0, 14).map((f, i) => (
                <div key={i} className="flex items-center gap-3 text-sm">
                  <span className="w-20 text-xs text-muted-foreground">{f.date?.slice(5)}</span>
                  <div className="flex-1 h-5 bg-muted rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${f.demand_level === 'high' ? 'bg-emerald-500' : f.demand_level === 'medium' ? 'bg-amber-400' : 'bg-red-400'}`}
                      style={{ width: `${Math.min(f.predicted_occupancy_pct || 0, 100)}%` }} />
                  </div>
                  <span className="w-12 text-xs font-medium text-right">{f.predicted_occupancy_pct}%</span>
                  <Badge variant="outline" className="text-xs w-14 justify-center">
                    {f.demand_level === 'high' ? 'Yüksek' : f.demand_level === 'medium' ? 'Orta' : 'Düşük'}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Recent ML Recommendations */}
      {recs.length > 0 && (
        <Card data-testid="recent-recommendations">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Son ML Onerileri</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th className="pb-2">Oda Tipi</th>
                    <th className="pb-2">Mevcut</th>
                    <th className="pb-2">Önerilen</th>
                    <th className="pb-2">Degisim</th>
                    <th className="pb-2">Guven</th>
                    <th className="pb-2">Durum</th>
                  </tr>
                </thead>
                <tbody>
                  {recs.slice(0, 10).map((r, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="py-2 font-medium">{r.room_type}</td>
                      <td className="py-2">{r.current_rate?.toLocaleString()} TL</td>
                      <td className="py-2">{r.suggested_rate?.toLocaleString()} TL</td>
                      <td className="py-2">{r.change_pct}%</td>
                      <td className="py-2">{Math.round((r.confidence || 0) * 100)}%</td>
                      <td className="py-2">
                        <Badge variant={r.status === 'applied' ? 'default' : r.status === 'pending' ? 'secondary' : 'outline'} className="text-xs">
                          {r.status === 'applied' ? 'Uygulandı' : r.status === 'pending' ? 'Bekliyor' : r.status === 'rejected' ? 'Reddedildi' : r.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// 2. OPERATIONAL AI TAB
// ═══════════════════════════════════════════════════════════

function OperationalTab() {
  const { headers } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const d = await fetchAPI('/api/data-intelligence/operations/dashboard', headers);
      setData(d);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={loadData} />;
  if (!data) return <EmptyState />;

  const checkin = data.check_in_load || {};
  const hk = data.housekeeping_workload || {};
  const readiness = data.room_readiness || {};
  const maint = data.maintenance_risk || {};
  const hkWorkload = hk.workload || {};
  const hkStaffing = hk.staffing_recommendation || {};
  const checkinStaffing = checkin.staffing_recommendation || {};

  return (
    <div data-testid="operational-tab" className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold">Operational AI</h3>
        <p className="text-sm text-muted-foreground">Operasyon tahmin ve personel onerileri</p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard testId="expected-arrivals" title="Beklenen Varis" value={checkin.total_expected_arrivals || 0} subtitle={`Peak: ${checkin.peak_hour || '-'}`} icon={Users} color="blue" />
        <StatCard testId="hk-rooms" title="Temizlenecek Oda" value={hkWorkload.total_rooms_to_clean || 0} subtitle={`${hkWorkload.total_hours || 0} saat is yuku`} icon={Activity} color="amber" />
        <StatCard testId="rooms-pending" title="Hazirlik Bekleyen" value={readiness.total_rooms_pending || 0} subtitle={`Ort. ${readiness.avg_eta_minutes || 0} dk`} icon={Clock} color="purple" />
        <StatCard testId="maint-risk" title="Bakım Riski" value={maint.at_risk_rooms || 0} subtitle={`${maint.high_risk_count || 0} yüksek risk`} icon={Shield} color="red" />
      </div>

      {/* Staffing Recommendations */}
      <div className="grid md:grid-cols-2 gap-4">
        <Card data-testid="frontdesk-staffing">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2"><Users className="h-4 w-4" />Resepsiyon Personel Onerisi</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="text-3xl font-bold">{checkinStaffing.recommended_agents || 1}</div>
                <div className="text-xs text-muted-foreground">önerilen ajan</div>
              </div>
              <PressureBadge score={checkin.arrival_pressure_score || 0} />
            </div>
            <p className="text-sm text-muted-foreground">{checkinStaffing.note || ''}</p>
          </CardContent>
        </Card>

        <Card data-testid="hk-staffing">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2"><Activity className="h-4 w-4" />Housekeeping Personel Onerisi</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="text-3xl font-bold">{hkStaffing.staff_needed || 1}</div>
                <div className="text-xs text-muted-foreground">önerilen personel</div>
              </div>
              <PressureBadge score={hkStaffing.shift_pressure_score || 0} />
            </div>
            <p className="text-sm text-muted-foreground">{hkStaffing.note || ''}</p>
          </CardContent>
        </Card>
      </div>

      {/* Check-in Hourly Forecast */}
      <Card data-testid="checkin-hourly">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Check-in Saatlik Dağılım</CardTitle>
        </CardHeader>
        <CardContent>
          {Object.keys(checkin.hourly_forecast || {}).length === 0 ? <EmptyState message="Saatlik veri yok" /> : (
            <div className="space-y-1.5">
              {Object.entries(checkin.hourly_forecast || {}).map(([hour, info]) => (
                <div key={hour} className="flex items-center gap-3 text-sm">
                  <span className="w-14 text-xs font-mono text-muted-foreground">{hour}</span>
                  <div className="flex-1 h-4 bg-muted rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${info.pressure === 'high' ? 'bg-red-500' : info.pressure === 'medium' ? 'bg-amber-400' : 'bg-emerald-400'}`}
                      style={{ width: `${Math.min((info.predicted_arrivals / Math.max(checkin.total_expected_arrivals || 1, 1)) * 300, 100)}%` }} />
                  </div>
                  <span className="w-8 text-xs font-medium text-right">{Math.round(info.predicted_arrivals)}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* HK Workload Breakdown */}
      <Card data-testid="hk-workload-breakdown">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Housekeeping Is Yuku Dagilimi</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-4 text-center">
            <div className="p-3 rounded-lg bg-red-50 border border-red-100">
              <div className="text-2xl font-bold text-red-700">{hkWorkload.departures || 0}</div>
              <div className="text-xs text-red-600">Çıkış (Derin Temizlik)</div>
            </div>
            <div className="p-3 rounded-lg bg-amber-50 border border-amber-100">
              <div className="text-2xl font-bold text-amber-700">{hkWorkload.stayovers || 0}</div>
              <div className="text-xs text-amber-600">Devam Eden (Tazeleme)</div>
            </div>
            <div className="p-3 rounded-lg bg-blue-50 border border-blue-100">
              <div className="text-2xl font-bold text-blue-700">{hkWorkload.arrivals || 0}</div>
              <div className="text-xs text-blue-600">Varis (Hazirlama)</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Maintenance Risk */}
      {(maint.risk_items || []).length > 0 && (
        <Card data-testid="maintenance-risk-table">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Bakım Ariza Risk Tablosu</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th className="pb-2">Oda</th>
                    <th className="pb-2">Risk Skoru</th>
                    <th className="pb-2">Seviye</th>
                    <th className="pb-2">Ariza Sayısı</th>
                    <th className="pb-2">Oneri</th>
                  </tr>
                </thead>
                <tbody>
                  {(maint.risk_items || []).slice(0, 10).map((r, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="py-2 font-medium">{r.room_id}</td>
                      <td className="py-2">{Math.round(r.risk_score * 100)}%</td>
                      <td className="py-2">
                        <Badge variant={r.risk_level === 'high' ? 'destructive' : 'secondary'} className="text-xs">
                          {r.risk_level === 'high' ? 'Yüksek' : 'Orta'}
                        </Badge>
                      </td>
                      <td className="py-2">{r.issue_count}</td>
                      <td className="py-2 text-xs text-muted-foreground">{r.recommendation}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// 3. GUEST INTELLIGENCE TAB
// ═══════════════════════════════════════════════════════════

function GuestTab() {
  const { headers } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const d = await fetchAPI('/api/data-intelligence/guests/dashboard?limit=20', headers);
      setData(d);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={loadData} />;
  if (!data) return <EmptyState />;

  const valDist = data.value_distribution || {};
  const segDist = data.segment_distribution || {};
  const churnSummary = data.churn_risk_summary || {};
  const topGuests = data.top_value_guests || [];
  const highChurn = data.high_churn_guests || [];
  const upsellOps = data.upsell_opportunities || [];

  const totalGuests = data.guests_analyzed || 0;

  return (
    <div data-testid="guest-tab" className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold">Guest Intelligence</h3>
        <p className="text-sm text-muted-foreground">Misafir değeri, segmentasyon, kayip riski ve satış firsatlari</p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard testId="total-guests" title="Analiz Edilen" value={totalGuests} icon={Users} color="blue" />
        <StatCard testId="platinum-guests" title="Platinum Misafir" value={valDist.platinum || 0} icon={Star} color="purple" />
        <StatCard testId="high-churn" title="Yüksek Kayip Riski" value={churnSummary.high || 0} icon={AlertTriangle} color="red" />
        <StatCard testId="upsell-count" title="Upsell Firsati" value={upsellOps.length} icon={Target} color="green" />
      </div>

      {/* Value Distribution */}
      <Card data-testid="value-distribution">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Misafir Deger Dagilimi</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-4 gap-3">
            {[
              { tier: 'platinum', label: 'Platinum', color: 'bg-violet-500', count: valDist.platinum || 0 },
              { tier: 'gold', label: 'Gold', color: 'bg-amber-400', count: valDist.gold || 0 },
              { tier: 'silver', label: 'Silver', color: 'bg-gray-400', count: valDist.silver || 0 },
              { tier: 'bronze', label: 'Bronze', color: 'bg-amber-300', count: valDist.bronze || 0 },
            ].map(t => (
              <div key={t.tier} className="text-center p-3 rounded-lg bg-muted/50 border">
                <div className={`w-3 h-3 rounded-full ${t.color} mx-auto mb-2`} />
                <div className="text-xl font-bold">{t.count}</div>
                <div className="text-xs text-muted-foreground">{t.label}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Segment Breakdown */}
      <Card data-testid="segment-breakdown">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Segment Dagilimi</CardTitle>
        </CardHeader>
        <CardContent>
          {Object.keys(segDist).length === 0 ? <EmptyState message="Segment verisi yok" /> : (
            <div className="space-y-2">
              {Object.entries(segDist).sort((a, b) => b[1] - a[1]).map(([seg, count]) => (
                <div key={seg} className="flex items-center justify-between p-2 rounded bg-muted/50">
                  <span className="text-sm font-medium">{seg.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</span>
                  <Badge variant="secondary" className="text-xs">{count}</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid md:grid-cols-2 gap-4">
        {/* Churn Risk Table */}
        <Card data-testid="churn-risk-table">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-red-500" />Yüksek Kayip Riski</CardTitle>
          </CardHeader>
          <CardContent>
            {highChurn.length === 0 ? <EmptyState message="Yüksek riskli misafir yok" /> : (
              <div className="space-y-2">
                {highChurn.map((g, i) => (
                  <div key={i} className="flex items-center justify-between p-2 rounded bg-red-50 border border-red-100">
                    <div>
                      <div className="text-sm font-medium">{g.name || g.guest_id}</div>
                      <div className="text-xs text-muted-foreground">{g.next_action}</div>
                    </div>
                    <Badge variant="destructive" className="text-xs">{Math.round(g.churn_score * 100)}%</Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Upsell Opportunities */}
        <Card data-testid="upsell-opportunities">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2"><Target className="h-4 w-4 text-emerald-500" />Upsell Firsatlari</CardTitle>
          </CardHeader>
          <CardContent>
            {upsellOps.length === 0 ? <EmptyState message="Upsell firsati yok" /> : (
              <div className="space-y-2">
                {upsellOps.map((u, i) => (
                  <div key={i} className="flex items-center justify-between p-2 rounded bg-emerald-50 border border-emerald-100">
                    <div>
                      <div className="text-sm font-medium">{u.name || u.guest_id}</div>
                      <div className="text-xs text-muted-foreground">{u.top_recommendation}</div>
                    </div>
                    <span className="text-sm font-bold text-emerald-700">{u.potential?.toLocaleString()} TL</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Top Value Guests */}
      {topGuests.length > 0 && (
        <Card data-testid="top-value-guests">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">En Degerli Misafirler</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th className="pb-2">Misafir</th>
                    <th className="pb-2">Deger Skoru</th>
                    <th className="pb-2">Toplam Gelir</th>
                    <th className="pb-2">Tier</th>
                  </tr>
                </thead>
                <tbody>
                  {topGuests.map((g, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="py-2 font-medium">{g.name || g.guest_id}</td>
                      <td className="py-2">{g.value_score}</td>
                      <td className="py-2">{g.total_revenue?.toLocaleString()} TL</td>
                      <td className="py-2">
                        <Badge variant="outline" className="text-xs capitalize">{g.tier}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// MAIN DASHBOARD
// ═══════════════════════════════════════════════════════════

export default function DataIntelligenceDashboard() {
  const { t } = useTranslation();
  return (
    <div data-testid="data-intelligence-dashboard" className="p-6 max-w-[1400px] mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Brain className="h-6 w-6" />
          {t("techDashboards.dataIntelligence")}
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          {t("techDashboards.dataIntelligenceDesc")}
        </p>
      </div>

      <Tabs defaultValue="revenue" className="w-full">
        <TabsList data-testid="intelligence-tabs" className="mb-6">
          <TabsTrigger data-testid="tab-revenue" value="revenue" className="gap-1.5">
            <TrendingUp className="h-4 w-4" />Revenue Intelligence
          </TabsTrigger>
          <TabsTrigger data-testid="tab-operational" value="operational" className="gap-1.5">
            <Activity className="h-4 w-4" />Operational AI
          </TabsTrigger>
          <TabsTrigger data-testid="tab-guests" value="guests" className="gap-1.5">
            <Users className="h-4 w-4" />Guest Intelligence
          </TabsTrigger>
        </TabsList>

        <TabsContent value="revenue"><RevenueTab /></TabsContent>
        <TabsContent value="operational"><OperationalTab /></TabsContent>
        <TabsContent value="guests"><GuestTab /></TabsContent>
      </Tabs>
    </div>
  );
}
