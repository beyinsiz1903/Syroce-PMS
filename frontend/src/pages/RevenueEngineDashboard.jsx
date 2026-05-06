import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend
} from 'recharts';
import {
  TrendingUp, DollarSign, BarChart3, Target, Calendar, ArrowUp, ArrowDown,
  Minus, Zap, ShieldAlert, Globe, ChevronRight, RefreshCw, CheckCircle
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

const API = "";
const COLORS = ['#0f766e', '#0ea5e9', '#8b5cf6', '#f59e0b', '#ef4444', '#10b981'];

export default function RevenueEngineDashboard({ user, tenant, onLogout, embedded = false }) {
  const { t } = useTranslation();
  const [dashboard, setDashboard] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [suggestions, setSuggestions] = useState(null);
  const [yieldRecs, setYieldRecs] = useState(null);
  const [channelPerf, setChannelPerf] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const navigate = useNavigate();

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const wrap = (content) => embedded ? content : (
    <>{content}</>
  );

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [dashRes, forecastRes, sugRes, yieldRes, chRes] = await Promise.all([
        axios.get(`/revenue-engine/dashboard`, { headers }),
        axios.get(`/revenue-engine/occupancy-forecast?days=14`, { headers }),
        axios.get(`/revenue-engine/rate-suggestions?days=7`, { headers }),
        axios.get(`/revenue-engine/yield-recommendations`, { headers }),
        axios.get(`/revenue-engine/channel-performance?days_back=30`, { headers }),
      ]);
      setDashboard(dashRes.data);
      setForecast(forecastRes.data);
      setSuggestions(sugRes.data);
      setYieldRecs(yieldRes.data);
      setChannelPerf(chRes.data);
    } catch (err) {
      console.error('Revenue dashboard fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleApplyRate = async (targetDate, newRate) => {
    try {
      await axios.post(`/revenue-engine/apply-rate`, { target_date: targetDate, new_rate: newRate }, { headers });
      fetchAll();
    } catch (err) { console.error(err); }
  };

  const tabs = [
    { id: 'overview', label: 'Genel Bakış', icon: BarChart3 },
    { id: 'forecast', label: 'Tahmin', icon: TrendingUp },
    { id: 'yield', label: 'Yield Kurallari', icon: Target },
    { id: 'channels', label: 'Kanal Analizi', icon: Globe },
  ];

  const recIcon = (rec) => {
    if (rec === 'increase') return <ArrowUp className="w-4 h-4 text-emerald-500" />;
    if (rec === 'decrease') return <ArrowDown className="w-4 h-4 text-red-500" />;
    return <Minus className="w-4 h-4 text-slate-400" />;
  };

  if (loading) {
    return wrap(
      <div className="flex items-center justify-center h-64" data-testid="revenue-loading">
        <RefreshCw className="w-8 h-8 animate-spin text-teal-600" />
      </div>
    );
  }

  const p30 = dashboard?.period_30d || {};

  return wrap(
    <div className="space-y-6 p-4 lg:p-6" data-testid="revenue-engine-dashboard">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{t("techDashboards.revenueEngine")}</h1>
            <p className="text-sm text-slate-500 mt-1">{t("techDashboards.revenueEngineDesc")}</p>
          </div>
          <Button variant="outline" size="sm" onClick={fetchAll} data-testid="revenue-refresh-btn">
            <RefreshCw className="w-4 h-4 mr-2" /> Yenile
          </Button>
        </div>

        {/* KPI Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="revenue-kpi-cards">
          <Card className="border-l-4 border-l-teal-500">
            <CardContent className="p-4">
              <p className="text-xs text-slate-500 uppercase tracking-wide">ADR (30g)</p>
              <p className="text-2xl font-bold text-slate-900 mt-1" data-testid="kpi-adr">{p30.adr?.toFixed(2) || '0'} TL</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-sky-500">
            <CardContent className="p-4">
              <p className="text-xs text-slate-500 uppercase tracking-wide">RevPAR (30g)</p>
              <p className="text-2xl font-bold text-slate-900 mt-1" data-testid="kpi-revpar">{p30.revpar?.toFixed(2) || '0'} TL</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-violet-500">
            <CardContent className="p-4">
              <p className="text-xs text-slate-500 uppercase tracking-wide">Doluluk (Bugün)</p>
              <p className="text-2xl font-bold text-slate-900 mt-1" data-testid="kpi-occupancy">{dashboard?.today_occupancy_pct || 0}%</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-amber-500">
            <CardContent className="p-4">
              <p className="text-xs text-slate-500 uppercase tracking-wide">Toplam Gelir (30g)</p>
              <p className="text-2xl font-bold text-slate-900 mt-1" data-testid="kpi-revenue">{(p30.total_revenue || 0).toLocaleString()} TL</p>
            </CardContent>
          </Card>
        </div>

        {/* Tabs */}
        <div className="flex space-x-1 bg-slate-100 rounded-lg p-1" data-testid="revenue-tabs">
          {tabs.map(t => {
            const Icon = t.icon;
            return (
              <button key={t.id} onClick={() => setActiveTab(t.id)}
                data-testid={`tab-${t.id}`}
                className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${activeTab === t.id ? 'bg-white text-teal-700 shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}>
                <Icon className="w-4 h-4" /> {t.label}
              </button>
            );
          })}
        </div>

        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* ADR & RevPAR Trend */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card>
                <CardHeader><CardTitle className="text-base">ADR Trend (30 Gun)</CardTitle></CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={250}>
                    <AreaChart data={dashboard?.daily_trend || []}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={v => v?.slice(5)} />
                      <YAxis tick={{ fontSize: 10 }} />
                      <Tooltip />
                      <Area type="monotone" dataKey="adr" stroke="#0f766e" fill="#0f766e" fillOpacity={0.15} name="ADR (TL)" />
                    </AreaChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle className="text-base">RevPAR Trend (30 Gun)</CardTitle></CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={250}>
                    <AreaChart data={dashboard?.daily_trend || []}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={v => v?.slice(5)} />
                      <YAxis tick={{ fontSize: 10 }} />
                      <Tooltip />
                      <Area type="monotone" dataKey="revpar" stroke="#0ea5e9" fill="#0ea5e9" fillOpacity={0.15} name="RevPAR (TL)" />
                    </AreaChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </div>

            {/* Revenue & Occupancy Trend */}
            <Card>
              <CardHeader><CardTitle className="text-base">Günlük Gelir ve Doluluk</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={dashboard?.daily_trend || []}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={v => v?.slice(5)} />
                    <YAxis yAxisId="left" tick={{ fontSize: 10 }} />
                    <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10 }} domain={[0, 100]} />
                    <Tooltip />
                    <Legend />
                    <Bar yAxisId="left" dataKey="revenue" fill="#0f766e" name="Gelir (TL)" radius={[2, 2, 0, 0]} />
                    <Line yAxisId="right" type="monotone" dataKey="occupancy_pct" stroke="#f59e0b" name="Doluluk %" strokeWidth={2} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Rate Suggestions */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Zap className="w-4 h-4 text-amber-500" /> Fiyat Onerileri (7 Gun)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm" data-testid="rate-suggestions-table">
                    <thead>
                      <tr className="border-b border-slate-200">
                        <th className="text-left py-2 px-3 text-slate-500 font-medium">Tarih</th>
                        <th className="text-center py-2 px-3 text-slate-500 font-medium">Doluluk</th>
                        <th className="text-center py-2 px-3 text-slate-500 font-medium">Carpan</th>
                        <th className="text-right py-2 px-3 text-slate-500 font-medium">Önerilen ADR</th>
                        <th className="text-right py-2 px-3 text-slate-500 font-medium">Est. RevPAR</th>
                        <th className="text-center py-2 px-3 text-slate-500 font-medium">Oneri</th>
                        <th className="text-center py-2 px-3 text-slate-500 font-medium">İşlem</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(suggestions?.suggestions || []).map((s, i) => (
                        <tr key={i} className="border-b border-slate-100 hover:bg-slate-50">
                          <td className="py-2 px-3 font-medium">{s.date}</td>
                          <td className="py-2 px-3 text-center">{s.current_occupancy_pct}%</td>
                          <td className="py-2 px-3 text-center">x{s.demand_multiplier}</td>
                          <td className="py-2 px-3 text-right font-semibold">{s.ideal_adr?.toFixed(2)} TL</td>
                          <td className="py-2 px-3 text-right">{s.revpar_estimate?.toFixed(2)} TL</td>
                          <td className="py-2 px-3 text-center">
                            <span className="inline-flex items-center gap-1">{recIcon(s.recommendation)} {s.recommendation}</span>
                          </td>
                          <td className="py-2 px-3 text-center">
                            <Button variant="outline" size="sm"
                              data-testid={`apply-rate-${i}`}
                              onClick={() => handleApplyRate(s.date, s.ideal_adr)}>
                              <CheckCircle className="w-3 h-3 mr-1" /> Uygula
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            {/* Revenue Opportunities */}
            {(dashboard?.opportunities || []).length > 0 && (
              <Card>
                <CardHeader><CardTitle className="text-base flex items-center gap-2">
                  <Target className="w-4 h-4 text-emerald-500" /> Gelir Firsatlari
                </CardTitle></CardHeader>
                <CardContent>
                  <div className="space-y-3" data-testid="revenue-opportunities">
                    {dashboard.opportunities.map((o, i) => (
                      <div key={i} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                        <div>
                          <p className="text-sm font-medium text-slate-700">{o.date}</p>
                          <p className="text-xs text-slate-500">{o.message}</p>
                        </div>
                        <Badge variant={o.type === 'price_increase' ? 'default' : 'secondary'}>
                          +{o.potential_revenue?.toLocaleString()} TL
                        </Badge>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        )}

        {/* Forecast Tab */}
        {activeTab === 'forecast' && (
          <div className="space-y-6">
            <Card>
              <CardHeader><CardTitle className="text-base">Doluluk Tahmini (14 Gun)</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={forecast?.forecast || []}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={v => v?.slice(5)} />
                    <YAxis tick={{ fontSize: 10 }} domain={[0, 100]} />
                    <Tooltip />
                    <Bar dataKey="occupancy_pct" name="Doluluk %" radius={[4, 4, 0, 0]}>
                      {(forecast?.forecast || []).map((d, i) => (
                        <Cell key={i} fill={d.occupancy_pct > 85 ? '#ef4444' : d.occupancy_pct > 60 ? '#f59e0b' : '#10b981'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="forecast-cards">
              {(forecast?.forecast || []).map((d, i) => (
                <Card key={i} className="hover:shadow-md transition-shadow">
                  <CardContent className="p-4">
                    <div className="flex justify-between items-center">
                      <p className="font-medium text-sm">{d.date}</p>
                      <Badge variant={d.demand_level === 'high' ? 'destructive' : d.demand_level === 'medium' ? 'default' : 'secondary'}>
                        {d.demand_level}
                      </Badge>
                    </div>
                    <div className="mt-2 grid grid-cols-3 gap-2 text-center">
                      <div>
                        <p className="text-xs text-slate-500">Dolu</p>
                        <p className="font-bold text-lg">{d.booked}</p>
                      </div>
                      <div>
                        <p className="text-xs text-slate-500">Bos</p>
                        <p className="font-bold text-lg text-emerald-600">{d.available}</p>
                      </div>
                      <div>
                        <p className="text-xs text-slate-500">Doluluk</p>
                        <p className="font-bold text-lg">{d.occupancy_pct}%</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )}

        {/* Yield Rules Tab */}
        {activeTab === 'yield' && (
          <div className="space-y-6">
            <Card>
              <CardHeader><CardTitle className="text-base">Yield Kurallari Onerileri</CardTitle></CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm" data-testid="yield-table">
                    <thead>
                      <tr className="border-b border-slate-200">
                        <th className="text-left py-2 px-3 text-slate-500 font-medium">Tarih</th>
                        <th className="text-center py-2 px-3 text-slate-500 font-medium">Doluluk</th>
                        <th className="text-center py-2 px-3 text-slate-500 font-medium">Talep</th>
                        <th className="text-center py-2 px-3 text-slate-500 font-medium">Min Stay</th>
                        <th className="text-center py-2 px-3 text-slate-500 font-medium">Stop Sell</th>
                        <th className="text-center py-2 px-3 text-slate-500 font-medium">CTA</th>
                        <th className="text-center py-2 px-3 text-slate-500 font-medium">CTD</th>
                        <th className="text-left py-2 px-3 text-slate-500 font-medium">Notlar</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(yieldRecs?.recommendations || []).map((r, i) => (
                        <tr key={i} className="border-b border-slate-100 hover:bg-slate-50">
                          <td className="py-2 px-3 font-medium">{r.date}</td>
                          <td className="py-2 px-3 text-center">{r.occupancy_pct}%</td>
                          <td className="py-2 px-3 text-center">
                            <Badge variant={r.demand_level === 'high' ? 'destructive' : r.demand_level === 'medium' ? 'default' : 'secondary'}>
                              {r.demand_level}
                            </Badge>
                          </td>
                          <td className="py-2 px-3 text-center font-semibold">{r.min_stay}</td>
                          <td className="py-2 px-3 text-center">{r.stop_sell ? <ShieldAlert className="w-4 h-4 text-red-500 mx-auto" /> : '-'}</td>
                          <td className="py-2 px-3 text-center">{r.cta ? <Badge variant="destructive">CTA</Badge> : '-'}</td>
                          <td className="py-2 px-3 text-center">{r.ctd ? <Badge variant="outline">CTD</Badge> : '-'}</td>
                          <td className="py-2 px-3 text-xs text-slate-500">{(r.notes || []).join('; ')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Channel Performance Tab */}
        {activeTab === 'channels' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card>
                <CardHeader><CardTitle className="text-base">Kanal Mix (Rezervasyon)</CardTitle></CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={280}>
                    <PieChart>
                      <Pie data={(channelPerf?.channels || []).map(c => ({ name: c.channel, value: c.bookings }))}
                        cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="value" label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                        {(channelPerf?.channels || []).map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle className="text-base">Kanal Gelir Dagilimi</CardTitle></CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={channelPerf?.channels || []} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis type="number" tick={{ fontSize: 10 }} />
                      <YAxis dataKey="channel" type="category" tick={{ fontSize: 11 }} width={80} />
                      <Tooltip />
                      <Bar dataKey="revenue" fill="#0f766e" name="Gelir (TL)" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </div>

            {/* Channel detail table */}
            <Card>
              <CardHeader><CardTitle className="text-base">Kanal Detay</CardTitle></CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm" data-testid="channel-table">
                    <thead>
                      <tr className="border-b border-slate-200">
                        <th className="text-left py-2 px-3 text-slate-500 font-medium">Kanal</th>
                        <th className="text-right py-2 px-3 text-slate-500 font-medium">Rez.</th>
                        <th className="text-right py-2 px-3 text-slate-500 font-medium">Gelir</th>
                        <th className="text-right py-2 px-3 text-slate-500 font-medium">Ort. Deger</th>
                        <th className="text-right py-2 px-3 text-slate-500 font-medium">Rez. Pay %</th>
                        <th className="text-right py-2 px-3 text-slate-500 font-medium">Gelir Pay %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(channelPerf?.channels || []).map((c, i) => (
                        <tr key={i} className="border-b border-slate-100 hover:bg-slate-50">
                          <td className="py-2 px-3 font-medium">{c.channel}</td>
                          <td className="py-2 px-3 text-right">{c.bookings}</td>
                          <td className="py-2 px-3 text-right">{c.revenue?.toLocaleString()} TL</td>
                          <td className="py-2 px-3 text-right">{c.avg_booking_value?.toFixed(2)} TL</td>
                          <td className="py-2 px-3 text-right">{c.booking_share_pct}%</td>
                          <td className="py-2 px-3 text-right">{c.revenue_share_pct}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {channelPerf?.direct_booking_incentive && (
                  <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800" data-testid="direct-booking-alert">
                    Direkt rezervasyon payi %30'un altinda. Direkt kanal tesvik onerilir.
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </div>
  );
}
