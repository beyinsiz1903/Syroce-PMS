import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import {
  TrendingUp, Brain, Target, AlertTriangle,
  Users, DollarSign, ChevronRight,
  ArrowUp, ArrowDown, Minus, RefreshCw, Loader2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

const API = "";

function StatBox({ label, value, color = 'text-slate-800' }) {
  return (
    <div>
      <div className="text-xs text-slate-500 mb-1">{label}</div>
      <div className={`text-lg font-bold ${color}`}>{value}</div>
    </div>
  );
}

function ActionBadge({ action }) {
  const map = {
    increase: { label: 'Artir', icon: ArrowUp, cls: 'text-green-600' },
    slight_increase: { label: 'Hafif Artir', icon: ArrowUp, cls: 'text-teal-600' },
    maintain: { label: 'Koru', icon: Minus, cls: 'text-blue-600' },
    decrease: { label: 'Dusur', icon: ArrowDown, cls: 'text-red-600' },
    slight_decrease: { label: 'Hafif Dusur', icon: ArrowDown, cls: 'text-amber-600' },
    no_data: { label: 'Veri Yok', icon: Minus, cls: 'text-slate-400' },
  };
  const item = map[action] || map.no_data;
  return (
    <span className={`flex items-center gap-1 text-xs font-medium ${item.cls}`}>
      <item.icon className="w-3 h-3" /> {item.label}
    </span>
  );
}

export default function RevenueMLPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`/platform/ml/dashboard`, { headers });
      setData(res.data);
    } catch (e) { console.error(e); }
    setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  const forecast = data?.demand_forecast?.forecast || [];
  const priceOpt = data?.price_optimization?.price_points || [];
  const convRates = data?.conversion_rates?.by_source || [];
  const atRisk = data?.cancellation_risk?.bookings || [];

  return (
    <div className="space-y-6" data-testid="revenue-ml-panel">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <Brain className="w-5 h-5 text-indigo-600" /> Revenue ML Sonuclari
        </h3>
        <Button variant="outline" size="sm" onClick={load} data-testid="refresh-ml-btn">
          <RefreshCw className="h-4 w-4 mr-1" /> Yenile
        </Button>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card><CardContent className="p-4">
          <StatBox label="Riskli Rez. Geliri" value={`${(data?.cancellation_risk?.total_at_risk_revenue || 0).toLocaleString()} TL`} color="text-red-600" />
        </CardContent></Card>
        <Card><CardContent className="p-4">
          <StatBox label="Fiyat Opt. Firsati" value={priceOpt.length} color="text-teal-600" />
        </CardContent></Card>
        <Card><CardContent className="p-4">
          <StatBox label="Yüksek Talep Gunu" value={`${data?.summary?.high_demand_days_next_14 || 0}/14`} color="text-indigo-600" />
        </CardContent></Card>
        <Card><CardContent className="p-4">
          <StatBox label="Riskli Rez. Sayısı" value={data?.cancellation_risk?.at_risk_count || 0} color="text-amber-600" />
        </CardContent></Card>
      </div>

      {/* Demand Forecast Chart */}
      <Card data-testid="demand-forecast-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-blue-600" /> Talep Tahmini ({data?.demand_forecast?.model || 'ML'})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {forecast.length > 0 ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={forecast.slice(0, 14).map(f => ({
                  date: f.date?.slice(5),
                  doluluk: f.predicted_occupancy_pct,
                  otb: Math.round((f.on_the_books / (data?.demand_forecast?.total_rooms || 1)) * 100),
                }))}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                  <YAxis domain={[0, 100]} />
                  <Tooltip />
                  <Area type="monotone" dataKey="doluluk" name="Tahmini Doluluk %" stroke="#0f766e" fill="#0f766e" fillOpacity={0.2} />
                  <Area type="monotone" dataKey="otb" name="OTB %" stroke="#0ea5e9" fill="#0ea5e9" fillOpacity={0.1} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : <p className="text-sm text-slate-400 text-center py-8">Tahmin verisi yok</p>}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Price Optimization */}
        <Card data-testid="price-optimization-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Target className="w-4 h-4 text-teal-600" /> Fiyat Optimizasyonu
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {priceOpt.map((pp, i) => (
                <div key={i} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                  <div>
                    <div className="font-medium text-sm">{pp.room_type}</div>
                    <div className="text-xs text-slate-500">Esneklik: {pp.elasticity}</div>
                  </div>
                  <div className="flex items-center gap-3 text-right">
                    <div>
                      <div className="text-xs text-slate-500">Mevcut</div>
                      <div className="text-sm font-medium">{pp.current_avg_price} TL</div>
                    </div>
                    <ChevronRight className="w-4 h-4 text-slate-400" />
                    <div>
                      <div className="text-xs text-slate-500">Önerilen</div>
                      <div className="text-sm font-bold text-teal-700">{pp.suggested_price} TL</div>
                    </div>
                    <ActionBadge action={pp.action} />
                  </div>
                </div>
              ))}
              {priceOpt.length === 0 && <p className="text-sm text-slate-400 text-center py-4">Optimizasyon verisi yok</p>}
            </div>
          </CardContent>
        </Card>

        {/* Conversion Rates */}
        <Card data-testid="conversion-rates-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Users className="w-4 h-4 text-blue-600" /> Donusum Oranlari (Kaynak)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {convRates.length > 0 ? (
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={convRates.map(c => ({ name: c.source, rate: Math.round(c.conversion_rate * 100), total: c.total_bookings }))}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                    <YAxis domain={[0, 100]} />
                    <Tooltip />
                    <Bar dataKey="rate" name="Donusum %" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : <p className="text-sm text-slate-400 text-center py-8">Donusum verisi yok</p>}
          </CardContent>
        </Card>
      </div>

      {/* At-Risk Bookings */}
      <Card data-testid="at-risk-bookings-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-500" /> İptal Riski Yüksek Rezervasyonlar
            <Badge variant="destructive" className="ml-2">{atRisk.length}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="pb-2 text-slate-500 font-medium">Misafir</th>
                  <th className="pb-2 text-slate-500 font-medium">Giriş</th>
                  <th className="pb-2 text-slate-500 font-medium">Kaynak</th>
                  <th className="pb-2 text-slate-500 font-medium text-right">Tutar</th>
                  <th className="pb-2 text-slate-500 font-medium text-right">Risk</th>
                </tr>
              </thead>
              <tbody>
                {atRisk.slice(0, 10).map((b, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="py-2">{b.guest_name || 'N/A'}</td>
                    <td className="py-2">{b.check_in?.slice(0, 10)}</td>
                    <td className="py-2">{b.source || 'direct'}</td>
                    <td className="py-2 text-right">{(b.total_amount || 0).toLocaleString()} TL</td>
                    <td className="py-2 text-right">
                      <Badge variant={b.risk_level === 'high' ? 'destructive' : 'secondary'}>
                        {Math.round(b.cancellation_probability * 100)}%
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {atRisk.length === 0 && <p className="text-sm text-slate-400 text-center py-4">Riskli rezervasyon yok</p>}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
