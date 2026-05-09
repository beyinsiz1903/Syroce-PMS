import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import MaybeLayout from '@/components/MaybeLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Ban, TrendingDown, Building2, Radio, AlertTriangle, Flame,
  Calendar, Shield, Brain, ChevronRight, Info, Plus, Trash2,
  ToggleLeft, ToggleRight, RefreshCw, Target, Zap, BarChart3
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

/* ─── Color maps ───────────────────────────────────────── */
const CHANNEL_COLORS = {
  direct: { bar: 'bg-emerald-500', text: 'text-emerald-700', light: 'bg-emerald-50' },
  booking: { bar: 'bg-blue-600', text: 'text-blue-700', light: 'bg-blue-50' },
  expedia: { bar: 'bg-yellow-500', text: 'text-yellow-700', light: 'bg-yellow-50' },
  airbnb: { bar: 'bg-rose-500', text: 'text-rose-700', light: 'bg-rose-50' },
  agency: { bar: 'bg-indigo-500', text: 'text-indigo-700', light: 'bg-indigo-50' },
};
const getChColor = (ch) => CHANNEL_COLORS[ch] || { bar: 'bg-gray-500', text: 'text-gray-700', light: 'bg-gray-50' };

const RISK_STYLES = {
  high: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700', badge: 'bg-red-100 text-red-700' },
  medium: { bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-700', badge: 'bg-amber-100 text-amber-700' },
  low: { bg: 'bg-green-50', border: 'border-green-200', text: 'text-green-700', badge: 'bg-green-100 text-green-700' },
};

const CONFIDENCE_ICONS = { low: '', medium: '', high: '' };

const WEEKDAY_SHORT = ['Pzt', 'Sal', 'Car', 'Per', 'Cum', 'Cmt', 'Paz'];

/* ─── Data quality banner ──────────────────────────────── */
const DataQualityBanner = ({ dq }) => {
  const { t } = useTranslation();
  if (!dq) return null;
  const colors = { low: 'bg-red-50 border-red-200 text-red-700', medium: 'bg-amber-50 border-amber-200 text-amber-700', high: 'bg-emerald-50 border-emerald-200 text-emerald-700' };
  return (
    <div className={`rounded-lg border px-4 py-2.5 flex items-center gap-2 text-sm ${colors[dq.confidence] || colors.low}`} data-testid="data-quality-banner">
      <Info className="w-4 h-4 flex-shrink-0" />
      <span>{CONFIDENCE_ICONS[dq.confidence]} <strong>{t('cm.pages_NoShowAnalytics.guvenilirlik')} {dq.confidence === 'high' ? 'Yüksek' : dq.confidence === 'medium' ? 'Orta' : 'Düşük'}</strong> — {dq.note}</span>
    </div>
  );
};

/* ─────────────────────────────────────────────────────────
   TAB 1: Channel Loss (FULL)
   ───────────────────────────────────────────────────────── */
const ChannelLossTab = ({ period }) => {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    axios.get(`/pms/channel-loss-analytics?days=${period}`)
      .then(r => setData(r.data))
      .catch(e => console.error(e))
      .finally(() => setLoading(false));
  }, [period]);

  if (loading) return <Loader />;
  if (!data) return <Empty />;

  const maxLoss = Math.max(...(data.channels?.map(c => c.total_loss) || [1]), 1);

  return (
    <div className="space-y-5" data-testid="channel-loss-tab">
      <DataQualityBanner dq={data.data_quality} />

      {/* Summary row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="border-l-4 border-l-red-500" data-testid="ch-total-loss">
          <CardContent className="pt-4 pb-3">
            <p className="text-xs font-medium text-gray-500 uppercase">{t('cm.pages_NoShowAnalytics.toplam_kayip')}</p>
            <p className="text-2xl font-bold text-red-600 mt-1">{data.total_loss?.toLocaleString('tr-TR')} TL</p>
            <p className="text-xs text-gray-400 mt-1">{data.total_no_shows} no-show</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-amber-500" data-testid="ch-worst-channel">
          <CardContent className="pt-4 pb-3">
            <p className="text-xs font-medium text-gray-500 uppercase">{t('cm.pages_NoShowAnalytics.en_kotu_kanal')}</p>
            <p className="text-2xl font-bold text-gray-900 mt-1 capitalize">{data.top3_worst?.[0]?.channel || '-'}</p>
            <p className="text-xs text-gray-400 mt-1">{data.top3_worst?.[0]?.total_loss?.toLocaleString('tr-TR')} {t('cm.pages_NoShowAnalytics.tl_kayip')}</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-blue-500" data-testid="ch-channels-count">
          <CardContent className="pt-4 pb-3">
            <p className="text-xs font-medium text-gray-500 uppercase">{t('cm.pages_NoShowAnalytics.kanal_sayisi')}</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{data.channels?.length || 0}</p>
            <p className="text-xs text-gray-400 mt-1">{t('cm.pages_NoShowAnalytics.aktif_kanal')}</p>
          </CardContent>
        </Card>
      </div>

      {/* Top 3 worst */}
      <Card data-testid="top3-worst-card">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            <Flame className="w-4 h-4 text-red-500" />
            <CardTitle className="text-sm font-semibold text-gray-700">Top 3 En Riskli Kanal</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {(data.top3_worst || []).map((ch, i) => {
              const clr = getChColor(ch.channel);
              return (
                <div key={ch.channel} className={`rounded-lg border p-4 ${clr.light}`} data-testid={`worst-ch-${i}`}>
                  <div className="flex items-center justify-between mb-2">
                    <Badge className={`text-xs font-bold ${clr.bar} text-white`}>#{i + 1}</Badge>
                    <span className="text-xs text-gray-500">{ch.no_show_rate}% oran</span>
                  </div>
                  <p className={`text-lg font-bold capitalize ${clr.text}`}>{ch.channel}</p>
                  <div className="mt-2 space-y-1 text-xs text-gray-600">
                    <div className="flex justify-between"><span>No-show</span><span className="font-semibold">{ch.no_show_count}</span></div>
                    <div className="flex justify-between"><span>{t('cm.pages_NoShowAnalytics.toplam_kayip_e38cc')}</span><span className="font-semibold text-red-600">-{ch.total_loss?.toLocaleString('tr-TR')} TL</span></div>
                    <div className="flex justify-between"><span>{t('cm.pages_NoShowAnalytics.ort_kayip')}</span><span className="font-semibold">{ch.avg_loss?.toLocaleString('tr-TR')} TL</span></div>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Full channel table */}
      <Card data-testid="channel-table-card">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_NoShowAnalytics.kanal_bazli_detay')}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-gray-500 uppercase tracking-wide">
                  <th className="pb-2 pr-3">Kanal</th>
                  <th className="pb-2 pr-3 text-right">No-Show</th>
                  <th className="pb-2 pr-3 text-right">{t('cm.pages_NoShowAnalytics.toplam_kayip_e38cc')}</th>
                  <th className="pb-2 pr-3 text-right">{t('cm.pages_NoShowAnalytics.ort_kayip_d319f')}</th>
                  <th className="pb-2 pr-3 text-right">No-Show %</th>
                  <th className="pb-2 text-right">{t('cm.pages_NoShowAnalytics.rez_sayisi')}</th>
                </tr>
              </thead>
              <tbody>
                {(data.channels || []).map((ch, i) => (
                  <tr key={ch.channel} className="border-b last:border-0 hover:bg-gray-50" data-testid={`ch-detail-row-${i}`}>
                    <td className="py-2.5 pr-3 capitalize font-medium">
                      <div className="flex items-center gap-2">
                        <div className={`w-2.5 h-2.5 rounded-full ${getChColor(ch.channel).bar}`} />
                        {ch.channel}
                      </div>
                    </td>
                    <td className="py-2.5 pr-3 text-right font-semibold">{ch.no_show_count}</td>
                    <td className="py-2.5 pr-3 text-right text-red-600 font-semibold">-{ch.total_loss?.toLocaleString('tr-TR')} TL</td>
                    <td className="py-2.5 pr-3 text-right">{ch.avg_loss?.toLocaleString('tr-TR')} TL</td>
                    <td className="py-2.5 pr-3 text-right">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${ch.no_show_rate > 10 ? 'bg-red-100 text-red-700' : ch.no_show_rate > 5 ? 'bg-amber-100 text-amber-700' : 'bg-green-100 text-green-700'}`}>
                        {ch.no_show_rate}%
                      </span>
                    </td>
                    <td className="py-2.5 text-right text-gray-500">{ch.total_bookings}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Channel trend chart */}
      <Card data-testid="channel-trend-card">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_NoShowAnalytics.kanal_bazli_zaman_trendi')}</CardTitle>
        </CardHeader>
        <CardContent>
          {data.trend?.length > 0 ? (
            <div className="space-y-4">
              {/* Legend */}
              <div className="flex flex-wrap gap-3">
                {(data.trend_channels || []).map(ch => (
                  <div key={ch} className="flex items-center gap-1.5 text-xs">
                    <div className={`w-3 h-3 rounded-sm ${getChColor(ch).bar}`} />
                    <span className="capitalize text-gray-600">{ch}</span>
                  </div>
                ))}
              </div>
              {/* Stacked bars */}
              <div className="flex items-end gap-[2px] h-36">
                {data.trend.slice(-30).map((d, i) => {
                  const total = (data.trend_channels || []).reduce((s, ch) => s + (d[ch] || 0), 0);
                  const maxT = Math.max(...data.trend.slice(-30).map(t => (data.trend_channels || []).reduce((s, ch) => s + (t[ch] || 0), 0)), 1);
                  return (
                    <div key={d.date} className="flex-1 flex flex-col justify-end group relative" data-testid={`trend-bar-${i}`}>
                      <div className="absolute -top-8 left-1/2 -translate-x-1/2 hidden group-hover:block bg-gray-800 text-white text-[10px] px-2 py-1 rounded whitespace-nowrap z-10">
                        {d.date}: {total}
                      </div>
                      {(data.trend_channels || []).map(ch => {
                        const pct = total > 0 ? ((d[ch] || 0) / maxT * 100) : 0;
                        return pct > 0 ? <div key={ch} className={`w-full ${getChColor(ch).bar} first:rounded-t`} style={{ height: `${pct}%`, minHeight: '2px' }} /> : null;
                      })}
                    </div>
                  );
                })}
              </div>
              {data.trend.length > 0 && (
                <div className="flex justify-between text-[10px] text-gray-400">
                  <span>{data.trend[Math.max(data.trend.length - 30, 0)]?.date}</span>
                  <span>{data.trend[data.trend.length - 1]?.date}</span>
                </div>
              )}
            </div>
          ) : (
            <Empty />
          )}
        </CardContent>
      </Card>
    </div>
  );
};

/* ─────────────────────────────────────────────────────────
   TAB 2: Overbooking Heatmap (FULL)
   ───────────────────────────────────────────────────────── */
const OverbookingHeatmapTab = ({ period }) => {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    axios.get(`/pms/overbooking-heatmap?days=${period}`)
      .then(r => setData(r.data))
      .catch(e => console.error(e))
      .finally(() => setLoading(false));
  }, [period]);

  if (loading) return <Loader />;
  if (!data) return <Empty />;

  const maxOB = Math.max(...(data.heatmap?.map(h => h.overbooking_count) || [0]), 1);

  // Build calendar grid (last N days)
  const calDays = (data.heatmap || []).slice(-60);
  const getHeatColor = (count) => {
    if (count === 0) return 'bg-gray-100';
    const intensity = Math.min(count / maxOB, 1);
    if (intensity > 0.75) return 'bg-red-500';
    if (intensity > 0.5) return 'bg-red-400';
    if (intensity > 0.25) return 'bg-amber-400';
    return 'bg-yellow-400';
  };

  return (
    <div className="space-y-5" data-testid="heatmap-tab">
      <DataQualityBanner dq={data.data_quality} />

      {/* Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="border-l-4 border-l-red-500" data-testid="ob-total">
          <CardContent className="pt-4 pb-3">
            <p className="text-xs font-medium text-gray-500 uppercase">{t('cm.pages_NoShowAnalytics.toplam_overbooking')}</p>
            <p className="text-2xl font-bold text-red-600 mt-1">{data.total_overbookings}</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-amber-500" data-testid="ob-loss">
          <CardContent className="pt-4 pb-3">
            <p className="text-xs font-medium text-gray-500 uppercase">{t('cm.pages_NoShowAnalytics.overbooking_kaybi')}</p>
            <p className="text-2xl font-bold text-amber-600 mt-1">{data.total_loss?.toLocaleString('tr-TR')} TL</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-blue-500" data-testid="ob-peak-day">
          <CardContent className="pt-4 pb-3">
            <p className="text-xs font-medium text-gray-500 uppercase">{t('cm.pages_NoShowAnalytics.en_riskli_gun')}</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{data.peak_days?.[0]?.date || '-'}</p>
            <p className="text-xs text-gray-400">{data.peak_days?.[0]?.overbooking_count || 0} overbooking</p>
          </CardContent>
        </Card>
      </div>

      {/* Heatmap grid */}
      <Card data-testid="heatmap-grid-card">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-gray-500" />
            <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_NoShowAnalytics.overbooking_haritasi')}</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          {calDays.length > 0 ? (
            <>
              <div className="flex flex-wrap gap-1">
                {calDays.map((d, i) => (
                  <div
                    key={d.date}
                    className={`w-7 h-7 rounded-sm ${getHeatColor(d.overbooking_count)} cursor-pointer group relative flex items-center justify-center`}
                    data-testid={`heat-cell-${i}`}
                  >
                    {d.overbooking_count > 0 && <span className="text-[9px] font-bold text-white">{d.overbooking_count}</span>}
                    <div className="absolute -top-12 left-1/2 -translate-x-1/2 hidden group-hover:block bg-gray-800 text-white text-[10px] px-2 py-1.5 rounded whitespace-nowrap z-20">
                      <div>{d.date}</div>
                      <div>OB: {d.overbooking_count} {t('cm.pages_NoShowAnalytics.toplam_ns')} {d.total_noshow}</div>
                      <div>Kayip: {d.loss?.toLocaleString('tr-TR')} TL</div>
                    </div>
                  </div>
                ))}
              </div>
              {/* Legend */}
              <div className="flex items-center gap-2 mt-3 text-[10px] text-gray-500">
                <span>Az</span>
                <div className="w-4 h-4 rounded-sm bg-gray-100" />
                <div className="w-4 h-4 rounded-sm bg-yellow-400" />
                <div className="w-4 h-4 rounded-sm bg-amber-400" />
                <div className="w-4 h-4 rounded-sm bg-red-400" />
                <div className="w-4 h-4 rounded-sm bg-red-500" />
                <span>{t('cm.pages_NoShowAnalytics.cok')}</span>
              </div>
            </>
          ) : (
            <Empty />
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Peak days (Top 5) */}
        <Card data-testid="peak-days-card">
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Flame className="w-4 h-4 text-red-500" />
              <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_NoShowAnalytics.top_5_riskli_gun')}</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {(data.peak_days || []).map((d, i) => (
                <div key={d.date} className="flex items-center gap-3 p-2.5 rounded-lg bg-gray-50 border" data-testid={`peak-day-${i}`}>
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-white text-xs font-bold ${i === 0 ? 'bg-red-500' : i === 1 ? 'bg-amber-500' : 'bg-amber-500'}`}>
                    #{i + 1}
                  </div>
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-800">{d.date}</p>
                    <p className="text-xs text-gray-500">{d.total_noshow} toplam no-show | {d.loss?.toLocaleString('tr-TR')} {t('cm.pages_NoShowAnalytics.tl_kayip_72ee7')}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-bold text-red-600">{d.overbooking_count}</p>
                    <p className="text-[10px] text-gray-400">overbooking</p>
                  </div>
                </div>
              ))}
              {(!data.peak_days || data.peak_days.length === 0) && <Empty />}
            </div>
          </CardContent>
        </Card>

        {/* Weekly pattern */}
        <Card data-testid="weekly-pattern-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_NoShowAnalytics.haftalik_desen_hafta_sonu_vs_hafta_ici')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {(data.weekly_pattern || []).map((d, i) => {
                const maxAvg = Math.max(...(data.weekly_pattern || []).map(w => w.avg_overbooking), 1);
                const pct = (d.avg_overbooking / maxAvg) * 100;
                return (
                  <div key={d.day_index} className="flex items-center gap-3" data-testid={`weekly-row-${i}`}>
                    <div className={`w-10 text-xs font-medium ${d.is_weekend ? 'text-red-600 font-bold' : 'text-gray-600'}`}>
                      {WEEKDAY_SHORT[d.day_index]}
                    </div>
                    <div className="flex-1 h-6 bg-gray-100 rounded relative overflow-hidden">
                      <div
                        className={`h-full rounded transition-all ${d.is_weekend ? 'bg-red-400' : 'bg-blue-400'}`}
                        style={{ width: `${Math.max(pct, 2)}%` }}
                      />
                      <div className="absolute inset-0 flex items-center px-2">
                        <span className="text-[10px] font-medium text-gray-700">ort. {d.avg_overbooking}</span>
                      </div>
                    </div>
                    <div className="w-16 text-right text-xs text-gray-500">
                      {d.overbooking_total} toplam
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Channel overlay */}
      {data.channel_overlay?.length > 0 && (
        <Card data-testid="ob-channel-overlay-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_NoShowAnalytics.overbooking_kanal_katkisi')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              {data.channel_overlay.map((ch, i) => {
                const clr = getChColor(ch.channel);
                return (
                  <div key={ch.channel} className={`rounded-lg border p-3 ${clr.light} min-w-[120px]`} data-testid={`ob-ch-${i}`}>
                    <p className={`text-sm font-medium capitalize ${clr.text}`}>{ch.channel}</p>
                    <p className="text-xl font-bold text-gray-900 mt-1">{ch.count}</p>
                    <p className="text-[10px] text-gray-400">overbooking</p>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

/* ─────────────────────────────────────────────────────────
   TAB 3: Rule Engine (LIGHT)
   ───────────────────────────────────────────────────────── */
const RuleEngineTab = () => {
  const { t } = useTranslation();
  const [rules, setRules] = useState([]);
  const [history, setHistory] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [form, setForm] = useState({
    rule_name: '', rule_type: 'overbooking_high',
    condition_metric: 'overbooking_count', condition_operator: 'gt',
    condition_value: '', action_suggestion: '',
    channel_filter: '',
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rRes, hRes] = await Promise.all([
        axios.get('/pms/alert-rules'),
        axios.get('/pms/alert-rules/history?limit=20'),
      ]);
      setRules(rRes.data.rules || []);
      setHistory(hRes.data.history || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const createRule = async () => {
    if (!form.rule_name || !form.condition_value || !form.action_suggestion) return;
    try {
      await axios.post('/pms/alert-rules', {
        ...form,
        condition_value: parseFloat(form.condition_value),
        channel_filter: form.channel_filter || null,
      });
      setShowForm(false);
      setForm({ rule_name: '', rule_type: 'overbooking_high', condition_metric: 'overbooking_count', condition_operator: 'gt', condition_value: '', action_suggestion: '', channel_filter: '' });
      load();
    } catch (e) { console.error(e); }
  };

  const deleteRule = async (id) => {
    try { await axios.delete(`/pms/alert-rules/${id}`); load(); } catch (e) { console.error(e); }
  };

  const toggleRule = async (id) => {
    try { await axios.patch(`/pms/alert-rules/${id}/toggle`); load(); } catch (e) { console.error(e); }
  };

  const evaluate = async () => {
    setEvaluating(true);
    try {
      const res = await axios.post('/pms/alert-rules/evaluate?days=7');
      setAlerts(res.data.alerts || []);
      setMetrics(res.data.metrics || null);
      load(); // Refresh history
    } catch (e) { console.error(e); }
    setEvaluating(false);
  };

  if (loading) return <Loader />;

  const METRIC_OPTIONS = [
    { value: 'overbooking_count', label: 'Overbooking Sayısı' },
    { value: 'noshow_count', label: 'No-Show Sayısı' },
    { value: 'noshow_rate', label: 'No-Show Oranı (%)' },
  ];

  const ACTION_PRESETS = [
    { value: 'rate_dusur', label: 'Rate Düşür' },
    { value: 'prepaid_zorunlu', label: 'Prepaid Zorunlu' },
    { value: 'kanal_kapat', label: 'Kanalı Kapat' },
    { value: 'manuel_inceleme', label: 'Manuel İnceleme' },
  ];

  return (
    <div className="space-y-5" data-testid="rule-engine-tab">
      {/* Alert banner */}
      <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-2.5 flex items-center gap-2 text-sm text-amber-700">
        <Shield className="w-4 h-4" />
        <span>Kurallar sadece <strong>{t('cm.pages_NoShowAnalytics.oneri_alert')}</strong> {t('cm.pages_NoShowAnalytics.modunda_calisir_otomatik_yazma_islemi_ya')}</span>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 flex-wrap">
        <Button variant="outline" size="sm" onClick={() => setShowForm(!showForm)} data-testid="add-rule-btn">
          <Plus className="w-4 h-4 mr-1" /> {t('cm.pages_NoShowAnalytics.kural_ekle')}
        </Button>
        <Button variant="default" size="sm" onClick={evaluate} disabled={evaluating} data-testid="evaluate-btn">
          <RefreshCw className={`w-4 h-4 mr-1 ${evaluating ? 'animate-spin' : ''}`} /> {t('cm.pages_NoShowAnalytics.kurallari_degerlendir')}
        </Button>
      </div>

      {/* New rule form */}
      {showForm && (
        <Card className="border-dashed border-2 border-blue-300" data-testid="rule-form">
          <CardContent className="pt-4 space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-gray-500 mb-1 block">{t('cm.pages_NoShowAnalytics.kural_adi')}</label>
                <Input placeholder={t('cm.pages_NoShowAnalytics.orn_yuksek_overbooking_alarmi')} value={form.rule_name} onChange={e => setForm(p => ({...p, rule_name: e.target.value}))} data-testid="rule-name-input" />
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Metrik</label>
                <Select value={form.condition_metric} onValueChange={v => setForm(p => ({...p, condition_metric: v}))}>
                  <SelectTrigger data-testid="rule-metric-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {METRIC_OPTIONS.map(m => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">{t('cm.pages_NoShowAnalytics.esik_degeri')}</label>
                <Input type="number" placeholder={t('cm.pages_NoShowAnalytics.orn_5')} value={form.condition_value} onChange={e => setForm(p => ({...p, condition_value: e.target.value}))} data-testid="rule-threshold-input" />
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">{t('cm.pages_NoShowAnalytics.oneri_aksiyonu')}</label>
                <Select value={form.action_suggestion} onValueChange={v => setForm(p => ({...p, action_suggestion: v}))}>
                  <SelectTrigger data-testid="rule-action-select"><SelectValue placeholder={t('cm.pages_NoShowAnalytics.aksiyon_sec')} /></SelectTrigger>
                  <SelectContent>
                    {ACTION_PRESETS.map(a => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Kanal Filtresi (opsiyonel)</label>
                <Input placeholder={t('cm.pages_NoShowAnalytics.orn_booking')} value={form.channel_filter} onChange={e => setForm(p => ({...p, channel_filter: e.target.value}))} data-testid="rule-channel-input" />
              </div>
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={createRule} data-testid="save-rule-btn">{t('cm.pages_NoShowAnalytics.kaydet')}</Button>
              <Button size="sm" variant="ghost" onClick={() => setShowForm(false)}>{t('cm.pages_NoShowAnalytics.iptal')}</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Active rules */}
      <Card data-testid="active-rules-card">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_NoShowAnalytics.tanimli_kurallar')}{rules.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {rules.length > 0 ? (
            <div className="space-y-2">
              {rules.map((r, i) => (
                <div key={r.id} className={`flex items-center gap-3 p-3 rounded-lg border ${r.is_active ? 'bg-white' : 'bg-gray-50 opacity-60'}`} data-testid={`rule-row-${i}`}>
                  <button onClick={() => toggleRule(r.id)} className="flex-shrink-0" data-testid={`toggle-rule-${i}`}>
                    {r.is_active ? <ToggleRight className="w-6 h-6 text-emerald-500" /> : <ToggleLeft className="w-6 h-6 text-gray-400" />}
                  </button>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-800 truncate">{r.rule_name}</p>
                    <p className="text-xs text-gray-500">{r.condition_metric} &gt; {r.condition_value} → {r.action_suggestion}{r.channel_filter ? ` (${r.channel_filter})` : ''}</p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-xs text-gray-500">{r.trigger_count || 0}x tetiklendi</p>
                    {r.last_triggered && <p className="text-[10px] text-gray-400">Son: {r.last_triggered.slice(0, 10)}</p>}
                  </div>
                  <button onClick={() => deleteRule(r.id)} className="text-red-400 hover:text-red-600" data-testid={`delete-rule-${i}`}>
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400 py-4 text-center">{t('cm.pages_NoShowAnalytics.henuz_kural_tanimlanmadi')}</p>
          )}
        </CardContent>
      </Card>

      {/* Evaluation results */}
      {alerts.length > 0 && (
        <Card className="border-red-200" data-testid="alerts-card">
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red-500" />
              <CardTitle className="text-sm font-semibold text-red-700">Tetiklenen Alertler ({alerts.length})</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {alerts.map((a, i) => (
                <div key={a.id} className="p-3 bg-red-50 border border-red-200 rounded-lg" data-testid={`alert-item-${i}`}>
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-red-800">{a.rule_name}</p>
                    <Badge variant="destructive" className="text-xs">ALERT</Badge>
                  </div>
                  <p className="text-xs text-red-600 mt-1">
                    Metrik: {a.metric_value} {t('cm.pages_NoShowAnalytics.esik')} {a.threshold}{t('cm.pages_NoShowAnalytics.oneri')} <strong>{a.action_suggestion}</strong>
                    {a.channel_filter ? ` [${a.channel_filter}]` : ''}
                  </p>
                </div>
              ))}
            </div>
            {metrics && (
              <div className="mt-3 p-2 bg-gray-50 rounded text-xs text-gray-500">
                Mevcut metrikler: OB={metrics.overbooking_count}, NS={metrics.noshow_count}, NS%={metrics.noshow_rate}%
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Trigger history */}
      <Card data-testid="trigger-history-card">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_NoShowAnalytics.tetikleme_gecmisi')}</CardTitle>
        </CardHeader>
        <CardContent>
          {history.filter(h => h.rule_name).length > 0 ? (
            <div className="space-y-1.5 max-h-60 overflow-y-auto">
              {history.filter(h => h.rule_name).map((h, i) => (
                <div key={h.id || i} className="flex items-center gap-3 text-xs p-2 rounded hover:bg-gray-50" data-testid={`history-row-${i}`}>
                  <Zap className="w-3 h-3 text-amber-500 flex-shrink-0" />
                  <span className="text-gray-500 w-24 flex-shrink-0">{(h.triggered_at || '').slice(0, 10)}</span>
                  <span className="font-medium text-gray-700 flex-1 truncate">{h.rule_name}</span>
                  <span className="text-gray-500">{t('cm.pages_NoShowAnalytics.deger')} {h.metric_value}</span>
                  <ChevronRight className="w-3 h-3 text-gray-400" />
                  <span className="text-amber-600 font-medium">{h.action_suggestion}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400 py-4 text-center">{t('cm.pages_NoShowAnalytics.henuz_tetikleme_gecmisi_yok')}</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

/* ─────────────────────────────────────────────────────────
   TAB 4: Prediction (BASIC)
   ───────────────────────────────────────────────────────── */
const PredictionTab = () => {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [daysAhead, setDaysAhead] = useState('7');

  useEffect(() => {
    setLoading(true);
    axios.get(`/pms/noshow-prediction?days_ahead=${daysAhead}`)
      .then(r => setData(r.data))
      .catch(e => console.error(e))
      .finally(() => setLoading(false));
  }, [daysAhead]);

  if (loading) return <Loader />;
  if (!data) return <Empty />;

  return (
    <div className="space-y-5" data-testid="prediction-tab">
      <DataQualityBanner dq={data.data_quality} />

      {/* Controls */}
      <div className="flex items-center gap-3">
        <Select value={daysAhead} onValueChange={setDaysAhead}>
          <SelectTrigger className="w-36" data-testid="pred-days-select"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="3">{t('cm.pages_NoShowAnalytics.3_gun_sonrasi')}</SelectItem>
            <SelectItem value="7">{t('cm.pages_NoShowAnalytics.7_gun_sonrasi')}</SelectItem>
            <SelectItem value="14">{t('cm.pages_NoShowAnalytics.14_gun_sonrasi')}</SelectItem>
            <SelectItem value="30">{t('cm.pages_NoShowAnalytics.30_gun_sonrasi')}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card className="border-l-4 border-l-red-500" data-testid="pred-high-risk">
          <CardContent className="pt-4 pb-3">
            <p className="text-xs font-medium text-gray-500 uppercase">{t('cm.pages_NoShowAnalytics.yuksek_risk')}</p>
            <p className="text-2xl font-bold text-red-600 mt-1">{data.summary?.high_risk || 0}</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-amber-500" data-testid="pred-medium-risk">
          <CardContent className="pt-4 pb-3">
            <p className="text-xs font-medium text-gray-500 uppercase">Orta Risk</p>
            <p className="text-2xl font-bold text-amber-600 mt-1">{data.summary?.medium_risk || 0}</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-green-500" data-testid="pred-low-risk">
          <CardContent className="pt-4 pb-3">
            <p className="text-xs font-medium text-gray-500 uppercase">{t('cm.pages_NoShowAnalytics.dusuk_risk')}</p>
            <p className="text-2xl font-bold text-green-600 mt-1">{data.summary?.low_risk || 0}</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-indigo-500" data-testid="pred-potential-loss">
          <CardContent className="pt-4 pb-3">
            <p className="text-xs font-medium text-gray-500 uppercase">{t('cm.pages_NoShowAnalytics.potansiyel_kayip')}</p>
            <p className="text-2xl font-bold text-indigo-600 mt-1">{data.summary?.potential_loss?.toLocaleString('tr-TR') || 0} TL</p>
          </CardContent>
        </Card>
      </div>

      {/* Prediction table */}
      <Card data-testid="prediction-table-card">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            <Brain className="w-4 h-4 text-indigo-500" />
            <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_NoShowAnalytics.rezervasyon_risk_tahminleri')}</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          {(data.predictions || []).length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-gray-500 uppercase tracking-wide">
                    <th className="pb-2 pr-3">Risk</th>
                    <th className="pb-2 pr-3">{t('cm.pages_NoShowAnalytics.misafir')}</th>
                    <th className="pb-2 pr-3">Kanal</th>
                    <th className="pb-2 pr-3">Check-in</th>
                    <th className="pb-2 pr-3">{t('cm.pages_NoShowAnalytics.oda_tipi')}</th>
                    <th className="pb-2 pr-3 text-right">{t('cm.pages_NoShowAnalytics.tutar')}</th>
                    <th className="pb-2 text-right">Skor</th>
                  </tr>
                </thead>
                <tbody>
                  {data.predictions.map((p, i) => {
                    const rs = RISK_STYLES[p.risk_level] || RISK_STYLES.low;
                    return (
                      <tr key={p.booking_id} className={`border-b last:border-0 ${rs.bg}`} data-testid={`pred-row-${i}`}>
                        <td className="py-2.5 pr-3">
                          <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${rs.badge}`}>
                            {p.risk_level === 'high' ? 'YÜKSEK' : p.risk_level === 'medium' ? 'ORTA' : 'DÜŞÜK'}
                          </span>
                        </td>
                        <td className="py-2.5 pr-3 font-medium text-gray-800">{p.guest_name}</td>
                        <td className="py-2.5 pr-3 capitalize text-gray-600">{p.channel}</td>
                        <td className="py-2.5 pr-3 text-gray-600">{p.check_in}</td>
                        <td className="py-2.5 pr-3 text-gray-600">{p.room_type}</td>
                        <td className="py-2.5 pr-3 text-right font-medium">{p.total_amount?.toLocaleString('tr-TR')} TL</td>
                        <td className="py-2.5 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <div className="w-12 h-2 bg-gray-200 rounded-full overflow-hidden">
                              <div className={`h-full rounded-full ${p.risk_score > 60 ? 'bg-red-500' : p.risk_score > 30 ? 'bg-amber-500' : 'bg-green-500'}`} style={{ width: `${p.risk_score}%` }} />
                            </div>
                            <span className="text-xs font-bold text-gray-700 w-6 text-right">{p.risk_score}</span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-gray-400 py-6 text-center">{t('cm.pages_NoShowAnalytics.yaklasan_rezervasyon_bulunamadi')}</p>
          )}
        </CardContent>
      </Card>

      {/* Historical rates */}
      {data.historical_rates && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <Card data-testid="hist-channel-rates-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_NoShowAnalytics.kanal_bazli_gecmis_no_show_orani')}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {Object.entries(data.historical_rates.by_channel || {}).sort((a, b) => b[1] - a[1]).map(([ch, rate], i) => (
                  <div key={ch} className="flex items-center gap-3" data-testid={`hist-ch-${i}`}>
                    <div className="w-16 text-xs font-medium text-gray-700 capitalize truncate">{ch}</div>
                    <div className="flex-1 h-5 bg-gray-100 rounded relative overflow-hidden">
                      <div className={`h-full rounded ${getChColor(ch).bar}`} style={{ width: `${Math.min(rate * 3, 100)}%` }} />
                    </div>
                    <span className="w-12 text-right text-xs font-semibold text-gray-700">{rate}%</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card data-testid="hist-dow-rates-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_NoShowAnalytics.gun_bazli_gecmis_no_show_orani')}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {Object.entries(data.historical_rates.by_day_of_week || {}).map(([dow, rate], i) => (
                  <div key={dow} className="flex items-center gap-3" data-testid={`hist-dow-${i}`}>
                    <div className={`w-10 text-xs font-medium ${parseInt(dow) >= 5 ? 'text-red-600 font-bold' : 'text-gray-600'}`}>
                      {WEEKDAY_SHORT[parseInt(dow)] || dow}
                    </div>
                    <div className="flex-1 h-5 bg-gray-100 rounded relative overflow-hidden">
                      <div className={`h-full rounded ${parseInt(dow) >= 5 ? 'bg-red-400' : 'bg-blue-400'}`} style={{ width: `${Math.min(rate * 3, 100)}%` }} />
                    </div>
                    <span className="w-12 text-right text-xs font-semibold text-gray-700">{rate}%</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
};

/* ─── Shared helpers ───────────────────────────────────── */
const Loader = () => (
  <div className="flex items-center justify-center h-40">
    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-amber-600" />
  </div>
);
const Empty = () => <p className="text-sm text-gray-400 py-6 text-center">Veri yok</p>;

/* ─────────────────────────────────────────────────────────
   MAIN PAGE
   ───────────────────────────────────────────────────────── */
const TABS = [
  { id: 'channel', label: 'Kanal Kaybı', icon: BarChart3, color: 'text-blue-600' },
  { id: 'heatmap', label: 'Overbooking Haritası', icon: Flame, color: 'text-red-600' },
  { id: 'rules', label: 'Kural Motoru', icon: Shield, color: 'text-amber-600' },
  { id: 'prediction', label: 'Tahmin', icon: Brain, color: 'text-indigo-600' },
];

const NoShowAnalytics = ({ user, tenant, onLogout, embedded = false }) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('channel');
  const [period, setPeriod] = useState('30');

  return (
    <MaybeLayout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout} currentModule="no-show-analytics">
      <div className="p-6 space-y-5 max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3" data-testid="noshow-analytics-header">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500 to-red-500 flex items-center justify-center shadow-lg">
              <Ban className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">No-Show & Gelir Analitik</h1>
              <p className="text-sm text-gray-500">{t('cm.pages_NoShowAnalytics.kanal_kaybi_overbooking_haritasi_kuralla')}</p>
            </div>
          </div>
          {activeTab !== 'rules' && activeTab !== 'prediction' && (
            <Select value={period} onValueChange={setPeriod}>
              <SelectTrigger className="w-36" data-testid="period-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7">{t('cm.pages_NoShowAnalytics.son_7_gun')}</SelectItem>
                <SelectItem value="30">{t('cm.pages_NoShowAnalytics.son_30_gun')}</SelectItem>
                <SelectItem value="90">{t('cm.pages_NoShowAnalytics.son_90_gun')}</SelectItem>
                <SelectItem value="365">{t('cm.pages_NoShowAnalytics.son_1_yil')}</SelectItem>
              </SelectContent>
            </Select>
          )}
        </div>

        {/* Tab Navigation */}
        <div className="flex gap-1 bg-gray-100 rounded-xl p-1" data-testid="tab-nav">
          {TABS.map(tab => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all flex-1 justify-center
                  ${active
                    ? 'bg-white shadow-sm text-gray-900'
                    : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                  }`}
                data-testid={`tab-${tab.id}`}
              >
                <Icon className={`w-4 h-4 ${active ? tab.color : ''}`} />
                <span className="hidden sm:inline">{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Tab Content */}
        {activeTab === 'channel' && <ChannelLossTab period={period} />}
        {activeTab === 'heatmap' && <OverbookingHeatmapTab period={period} />}
        {activeTab === 'rules' && <RuleEngineTab />}
        {activeTab === 'prediction' && <PredictionTab />}
      </div>
    </MaybeLayout>
  );
};

export default NoShowAnalytics;
