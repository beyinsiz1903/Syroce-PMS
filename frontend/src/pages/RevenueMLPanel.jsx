import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import {
  TrendingUp, Brain, Target, AlertTriangle,
  Users, ChevronRight, ArrowUp, ArrowDown, Minus,
  RefreshCw, Loader2, DollarSign,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { KpiCard } from '@/components/ui/kpi-card';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

// Sprint A palette: indigo / sky / emerald / rose / amber / slate. Gradient yok.
const COLOR = {
  indigo: '#6366f1', // önceki #8b5cf6 (purple) yerine — palette migration.
  sky: '#0ea5e9',
  emerald: '#10b981',
  amber: '#f59e0b',
  rose: '#f43f5e',
};

function ActionBadge({ action }) {
  const { t } = useTranslation();
  const map = {
    increase:        { label: 'Artır',       icon: ArrowUp,   cls: 'text-emerald-600' },
    slight_increase: { label: 'Hafif Artır', icon: ArrowUp,   cls: 'text-emerald-500' },
    maintain:        { label: 'Koru',        icon: Minus,     cls: 'text-sky-600' },
    decrease:        { label: 'Düşür',       icon: ArrowDown, cls: 'text-rose-600' },
    slight_decrease: { label: 'Hafif Düşür', icon: ArrowDown, cls: 'text-amber-600' },
    no_data:         { label: 'Veri Yok',    icon: Minus,     cls: 'text-slate-400' },
  };
  const item = map[action] || map.no_data;
  const Icon = item.icon;
  return (
    <span className={`flex items-center gap-1 text-xs font-medium ${item.cls}`}>
      <Icon className="w-3 h-3" /> {item.label}
    </span>
  );
}

export default function RevenueMLPanel() {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get('/platform/ml/dashboard', { timeout: 45000 });
      setData(res.data);
    } catch (e) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail || e?.message || 'Bilinmeyen hata';
      let msg;
      if (status === 401) msg = 'Oturum süresi doldu. Lütfen tekrar giriş yapın.';
      else if (status === 403) msg = 'Yetki yok: Bu paneli görüntülemek için "Yönetici Raporları" izni gerekli.';
      else if (e?.code === 'ECONNABORTED') msg = 'Zaman aşımı: ML servisi 45 saniye içinde yanıt vermedi.';
      else if (status) msg = `ML servisi hatası (${status}): ${detail}`;
      else msg = `Bağlantı hatası: ${detail}`;
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
        <span className="ml-3 text-sm text-slate-500">{t('cm.pages_RevenueMLPanel.ml_hesaplaniyor')}</span>
      </div>
    );
  }

  if (error) {
    return (
      <Card data-testid="revenue-ml-error">
        <CardContent className="py-12 text-center space-y-3">
          <AlertTriangle className="h-10 w-10 text-amber-500 mx-auto" />
          <p className="text-sm text-slate-700">{error}</p>
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw className="h-4 w-4 mr-1.5" /> {t('cm.pages_RevenueMLPanel.yenile')}
          </Button>
        </CardContent>
      </Card>
    );
  }

  const forecast = data?.demand_forecast?.forecast || [];
  const priceOpt = data?.price_optimization?.price_points || [];
  const convRates = data?.conversion_rates?.by_source || [];
  const atRisk = data?.cancellation_risk?.bookings || [];
  const sectionErrors = data?.section_errors || {};
  const hasSectionErrors = Object.keys(sectionErrors).length > 0;

  return (
    <div className="space-y-6 p-2" data-testid="revenue-ml-panel">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold flex items-center gap-2 text-slate-900">
          <Brain className="w-5 h-5 text-indigo-600" /> {t('cm.pages_RevenueMLPanel.revenue_ml_sonuclari')}
        </h3>
        <Button variant="outline" size="sm" onClick={load} data-testid="refresh-ml-btn">
          <RefreshCw className="w-4 h-4 mr-1.5" /> {t('cm.pages_RevenueMLPanel.yenile_aedf3')}
        </Button>
      </div>

      {hasSectionErrors && (
        <Card className="border-amber-500/30 bg-amber-50/50">
          <CardContent className="py-3 text-sm text-amber-800 flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 mt-0.5 text-amber-600 flex-shrink-0" />
            <div>
              {t('cm.pages_RevenueMLPanel.bazi_alt_boru_hatlari_basarisiz_oldu_kis')}{' '}
              <strong>{Object.keys(sectionErrors).join(', ')}</strong>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Summary KPIs — Sprint A standardı */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard
          icon={DollarSign}
          intent="danger"
          label="Riskli Rez. Geliri"
          value={`${(data?.cancellation_risk?.total_at_risk_revenue || 0).toLocaleString('tr-TR')} TL`}
        />
        <KpiCard
          icon={Target}
          intent="success"
          label={t('cm.pages_RevenueMLPanel.fiyat_opt_firsati')}
          value={priceOpt.length}
        />
        <KpiCard
          icon={TrendingUp}
          intent="info"
          label={t('cm.pages_RevenueMLPanel.yuksek_talep_gunu')}
          value={`${data?.summary?.high_demand_days_next_14 || 0}/14`}
        />
        <KpiCard
          icon={AlertTriangle}
          intent="warning"
          label={t('cm.pages_RevenueMLPanel.riskli_rez_sayisi')}
          value={data?.cancellation_risk?.at_risk_count || 0}
        />
      </div>

      {/* Demand Forecast Chart */}
      <Card data-testid="demand-forecast-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2 text-slate-800">
            <TrendingUp className="w-4 h-4 text-sky-600" /> Talep Tahmini ({data?.demand_forecast?.model || 'ML'})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {forecast.length > 0 ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={forecast.slice(0, 14).map((f) => ({
                  date: f.date?.slice(5),
                  doluluk: f.predicted_occupancy_pct,
                  otb: Math.round((f.on_the_books / (data?.demand_forecast?.total_rooms || 1)) * 100),
                }))}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                  <YAxis domain={[0, 100]} />
                  <Tooltip />
                  <Area type="monotone" dataKey="doluluk" name="Tahmini Doluluk %"
                    stroke={COLOR.emerald} fill={COLOR.emerald} fillOpacity={0.2} />
                  <Area type="monotone" dataKey="otb" name="OTB %"
                    stroke={COLOR.sky} fill={COLOR.sky} fillOpacity={0.1} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-sm text-slate-400 text-center py-8">Tahmin verisi yok.</p>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Price Optimization */}
        <Card data-testid="price-optimization-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2 text-slate-800">
              <Target className="w-4 h-4 text-emerald-600" /> Fiyat Optimizasyonu
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {priceOpt.map((pp, i) => (
                <div key={i} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                  <div>
                    <div className="font-medium text-sm text-slate-900">{pp.room_type}</div>
                    <div className="text-xs text-slate-500">Esneklik: {pp.elasticity}</div>
                  </div>
                  <div className="flex items-center gap-3 text-right">
                    <div>
                      <div className="text-xs text-slate-500">Mevcut</div>
                      <div className="text-sm font-medium text-slate-800">{pp.current_avg_price} TL</div>
                    </div>
                    <ChevronRight className="w-4 h-4 text-slate-400" />
                    <div>
                      <div className="text-xs text-slate-500">{t('cm.pages_RevenueMLPanel.onerilen')}</div>
                      <div className="text-sm font-bold text-emerald-700">{pp.suggested_price} TL</div>
                    </div>
                    <ActionBadge action={pp.action} />
                  </div>
                </div>
              ))}
              {priceOpt.length === 0 && (
                <p className="text-sm text-slate-400 text-center py-4">Optimizasyon verisi yok.</p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Conversion Rates */}
        <Card data-testid="conversion-rates-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2 text-slate-800">
              <Users className="w-4 h-4 text-sky-600" /> {t('cm.pages_RevenueMLPanel.donusum_oranlari_kaynak')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {convRates.length > 0 ? (
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={convRates.map((c) => ({
                    name: c.source,
                    rate: Math.round(c.conversion_rate * 100),
                    total: c.total_bookings,
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                    <YAxis domain={[0, 100]} />
                    <Tooltip />
                    {/* Sprint A: purple #8b5cf6 → indigo #6366f1 */}
                    <Bar dataKey="rate" name="Dönüşüm %" fill={COLOR.indigo} radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text-sm text-slate-400 text-center py-8">{t('cm.pages_RevenueMLPanel.donusum_verisi_yok')}</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* At-Risk Bookings */}
      <Card data-testid="at-risk-bookings-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2 text-slate-800">
            <AlertTriangle className="w-4 h-4 text-rose-500" /> {t('cm.pages_RevenueMLPanel.iptal_riski_yuksek_rezervasyonlar')}
            <Badge variant="destructive" className="ml-2">{atRisk.length}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="pb-2 text-slate-500 font-medium">{t('cm.pages_RevenueMLPanel.misafir')}</th>
                  <th className="pb-2 text-slate-500 font-medium">{t('cm.pages_RevenueMLPanel.giris')}</th>
                  <th className="pb-2 text-slate-500 font-medium">Kaynak</th>
                  <th className="pb-2 text-slate-500 font-medium text-right">{t('cm.pages_RevenueMLPanel.tutar')}</th>
                  <th className="pb-2 text-slate-500 font-medium text-right">Risk</th>
                </tr>
              </thead>
              <tbody>
                {atRisk.slice(0, 10).map((b, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="py-2 text-slate-800">{b.guest_name || 'N/A'}</td>
                    <td className="py-2 text-slate-700">{b.check_in?.slice(0, 10)}</td>
                    <td className="py-2 text-slate-700">{b.source || 'direct'}</td>
                    <td className="py-2 text-right text-slate-800">
                      {(b.total_amount || 0).toLocaleString('tr-TR')} TL
                    </td>
                    <td className="py-2 text-right">
                      <Badge variant={b.risk_level === 'high' ? 'destructive' : 'secondary'}>
                        {Math.round((b.cancellation_probability || 0) * 100)}%
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {atRisk.length === 0 && (
              <p className="text-sm text-slate-400 text-center py-4">Riskli rezervasyon yok.</p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
