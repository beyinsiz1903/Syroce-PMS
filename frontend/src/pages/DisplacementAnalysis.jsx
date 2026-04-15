import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useTranslation } from 'react-i18next';
import {
  TrendingUp, TrendingDown, DollarSign, BarChart3, Calendar,
  Users, Building2, AlertTriangle, CheckCircle2, XCircle,
  Plus, Trash2, RefreshCw, Save, ArrowRight, Info,
  Percent, Target, ArrowUpRight, ArrowDownRight, Minus,
  History, GitCompare, LayoutDashboard
} from 'lucide-react';

const RISK_COLORS = {
  high: 'bg-red-100 text-red-700 border-red-200',
  medium: 'bg-amber-100 text-amber-700 border-amber-200',
  low: 'bg-emerald-100 text-emerald-700 border-emerald-200',
};

const REC_STYLES = {
  accept: { bg: 'bg-emerald-50', border: 'border-emerald-300', icon: CheckCircle2, color: 'text-emerald-700' },
  reject: { bg: 'bg-red-50', border: 'border-red-300', icon: XCircle, color: 'text-red-700' },
  conditional: { bg: 'bg-amber-50', border: 'border-amber-300', icon: AlertTriangle, color: 'text-amber-700' },
};

const fmt = (n) => {
  if (n == null) return '—';
  return new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
};

const fmtPct = (n) => {
  if (n == null) return '—';
  return `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`;
};

const tomorrow = () => {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
};

const dayAfter = (ds, n = 3) => {
  const d = new Date(ds);
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
};

const MarketOverviewTab = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(14);

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`/api/displacement/market-overview?days=${days}`);
      setData(res.data);
    } catch (e) {
      console.error('Market overview error:', e);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { fetch(); }, [fetch]);

  if (loading) return <LoadingState text={t('displacement.loadingMarket', 'Loading market data...')} />;
  if (!data) return <EmptyState text={t('displacement.noData', 'No data available')} />;

  const maxOcc = Math.max(...(data.forecast || []).map(f => f.occupancy_pct), 1);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <MetricCard icon={Building2} label={t('displacement.totalRooms', 'Total Rooms')} value={data.total_rooms} />
        <MetricCard icon={DollarSign} label={t('displacement.historicalAdr', 'Historical ADR')} value={fmt(data.historical_adr)} prefix="₺" />
        <MetricCard icon={Percent} label={t('displacement.cancelRate', 'Cancel Rate')} value={`${data.cancellation_rate_pct}%`} />
        <MetricCard icon={BarChart3} label={t('displacement.channels', 'Channels')} value={data.channel_mix?.length || 0} />
      </div>

      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base font-semibold">{t('displacement.occupancyForecast', 'Occupancy & Displacement Risk')}</CardTitle>
            <div className="flex items-center gap-2">
              {[7, 14, 30].map(d => (
                <Button key={d} size="sm" variant={days === d ? 'default' : 'outline'} onClick={() => setDays(d)}>
                  {d} {t('displacement.days', 'days')}
                </Button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-1.5">
            {(data.forecast || []).map((f, i) => (
              <div key={i} className="flex items-center gap-3 text-sm">
                <span className="w-20 text-gray-500 font-mono text-xs">{f.date?.slice(5)}</span>
                <span className="w-12 text-gray-400 text-xs">{f.day_of_week?.slice(0, 3)}</span>
                <div className="flex-1 h-5 bg-gray-100 rounded-full overflow-hidden relative">
                  <div
                    className={`h-full rounded-full transition-all ${f.occupancy_pct >= 85 ? 'bg-red-500' : f.occupancy_pct >= 65 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                    style={{ width: `${Math.min(f.occupancy_pct, 100)}%` }}
                  />
                  <span className="absolute inset-0 flex items-center justify-center text-[10px] font-semibold text-gray-800">
                    {f.occupancy_pct}%
                  </span>
                </div>
                <span className="w-16 text-right text-xs text-gray-500">{f.available} {t('displacement.avail', 'avail')}</span>
                <Badge className={`text-[10px] px-1.5 ${RISK_COLORS[f.displacement_risk]}`}>
                  {f.displacement_risk === 'high' ? t('displacement.highRisk', 'High Risk') : f.displacement_risk === 'medium' ? t('displacement.medRisk', 'Medium') : t('displacement.lowRisk', 'Low')}
                </Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {data.channel_mix?.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold">{t('displacement.channelMix', 'Channel Mix')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {data.channel_mix.map((ch, i) => (
                <div key={i} className="flex items-center gap-3 p-3 rounded-lg border bg-white">
                  <div className="w-2 h-10 rounded-full bg-blue-500" style={{ opacity: 0.3 + (ch.share_pct / 100) * 0.7 }} />
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm truncate capitalize">{ch.channel}</p>
                    <p className="text-xs text-gray-500">{ch.bookings} {t('displacement.bookings', 'bookings')} · {ch.share_pct}%</p>
                  </div>
                  <p className="text-sm font-semibold">₺{fmt(ch.avg_rate)}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

const AnalysisTab = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [form, setForm] = useState({
    group_name: '',
    check_in: tomorrow(),
    check_out: dayAfter(tomorrow()),
    rooms_requested: 10,
    proposed_rate: 100,
    ancillary_per_room: 0,
    commission_pct: 0,
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const handleChange = (field, value) => {
    setForm(prev => ({ ...prev, [field]: value }));
  };

  const runAnalysis = async () => {
    setLoading(true);
    setResult(null);
    try {
      const res = await axios.post('/api/displacement/analyze', {
        ...form,
        rooms_requested: Number(form.rooms_requested),
        proposed_rate: Number(form.proposed_rate),
        ancillary_per_room: Number(form.ancillary_per_room),
        commission_pct: Number(form.commission_pct),
      });
      setResult(res.data);
    } catch (e) {
      console.error('Analysis error:', e);
    } finally {
      setLoading(false);
    }
  };

  const saveAnalysis = async () => {
    setSaving(true);
    try {
      await axios.post('/api/displacement/save', {
        ...form,
        rooms_requested: Number(form.rooms_requested),
        proposed_rate: Number(form.proposed_rate),
        ancillary_per_room: Number(form.ancillary_per_room),
        commission_pct: Number(form.commission_pct),
      });
    } catch (e) {
      console.error('Save error:', e);
    } finally {
      setSaving(false);
    }
  };

  const rec = result?.recommendation;
  const recStyle = rec ? REC_STYLES[rec.action] || REC_STYLES.conditional : null;
  const RecIcon = recStyle?.icon || Info;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Target className="w-4 h-4" />
            {t('displacement.scenarioBuilder', 'Scenario Builder')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <Label className="text-xs">{t('displacement.groupName', 'Group / Event Name')}</Label>
              <Input value={form.group_name} onChange={e => handleChange('group_name', e.target.value)} placeholder={t('displacement.groupPlaceholder', 'e.g. ABC Conference')} />
            </div>
            <div>
              <Label className="text-xs">{t('displacement.checkIn', 'Check-in')}</Label>
              <Input type="date" value={form.check_in} onChange={e => handleChange('check_in', e.target.value)} />
            </div>
            <div>
              <Label className="text-xs">{t('displacement.checkOut', 'Check-out')}</Label>
              <Input type="date" value={form.check_out} onChange={e => handleChange('check_out', e.target.value)} />
            </div>
            <div>
              <Label className="text-xs">{t('displacement.roomsRequested', 'Rooms Requested')}</Label>
              <Input type="number" min={1} value={form.rooms_requested} onChange={e => handleChange('rooms_requested', e.target.value)} />
            </div>
            <div>
              <Label className="text-xs">{t('displacement.proposedRate', 'Proposed Rate (₺)')}</Label>
              <Input type="number" min={0} step={0.01} value={form.proposed_rate} onChange={e => handleChange('proposed_rate', e.target.value)} />
            </div>
            <div>
              <Label className="text-xs">{t('displacement.ancillary', 'Ancillary / Room / Night (₺)')}</Label>
              <Input type="number" min={0} step={0.01} value={form.ancillary_per_room} onChange={e => handleChange('ancillary_per_room', e.target.value)} />
            </div>
            <div>
              <Label className="text-xs">{t('displacement.commission', 'Commission %')}</Label>
              <Input type="number" min={0} max={100} step={0.1} value={form.commission_pct} onChange={e => handleChange('commission_pct', e.target.value)} />
            </div>
            <div className="flex items-end">
              <Button onClick={runAnalysis} disabled={loading} className="w-full">
                {loading ? <RefreshCw className="w-4 h-4 animate-spin mr-2" /> : <ArrowRight className="w-4 h-4 mr-2" />}
                {t('displacement.analyze', 'Run Analysis')}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {result && (
        <>
          <div className={`rounded-xl border-2 p-5 ${recStyle?.bg} ${recStyle?.border}`}>
            <div className="flex items-start gap-4">
              <RecIcon className={`w-8 h-8 mt-0.5 ${recStyle?.color}`} />
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-1">
                  <h3 className={`text-lg font-bold ${recStyle?.color}`}>
                    {rec.action === 'accept' ? t('displacement.accept', 'ACCEPT') : rec.action === 'reject' ? t('displacement.reject', 'REJECT') : t('displacement.conditional', 'CONDITIONAL')}
                  </h3>
                  <Badge className={recStyle?.bg + ' ' + recStyle?.color + ' border'}>
                    {rec.confidence === 'high' ? t('displacement.highConf', 'High Confidence') : rec.confidence === 'medium' ? t('displacement.medConf', 'Medium') : t('displacement.lowConf', 'Low')}
                  </Badge>
                </div>
                <p className="text-sm text-gray-700">{rec.reason}</p>
              </div>
              <Button size="sm" variant="outline" onClick={saveAnalysis} disabled={saving}>
                <Save className="w-4 h-4 mr-1" />
                {t('displacement.save', 'Save')}
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <SummaryCard label={t('displacement.displacedRevenue', 'Displaced Revenue')} value={`₺${fmt(result.summary.total_displaced_revenue)}`} icon={TrendingDown} color="text-red-600" />
            <SummaryCard label={t('displacement.proposedRevenue', 'Proposed Revenue')} value={`₺${fmt(result.summary.total_proposed_revenue)}`} icon={TrendingUp} color="text-blue-600" />
            <SummaryCard label={t('displacement.ancillaryRevenue', 'Ancillary Revenue')} value={`₺${fmt(result.summary.total_ancillary_revenue)}`} icon={Plus} color="text-purple-600" />
            <SummaryCard
              label={t('displacement.netDisplacement', 'Net Displacement')}
              value={`₺${fmt(result.summary.net_displacement)}`}
              icon={result.summary.net_displacement >= 0 ? ArrowUpRight : ArrowDownRight}
              color={result.summary.net_displacement >= 0 ? 'text-emerald-600' : 'text-red-600'}
            />
            <SummaryCard label={t('displacement.roi', 'ROI')} value={fmtPct(result.summary.roi_pct)} icon={Target} color="text-indigo-600" />
            <SummaryCard label={t('displacement.revparDelta', 'RevPAR Delta')} value={`₺${fmt(result.summary.revpar_delta)}`} icon={BarChart3} color="text-cyan-600" />
          </div>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-semibold">{t('displacement.dailyBreakdown', 'Daily Breakdown')}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs text-gray-500">
                      <th className="py-2 pr-3">{t('displacement.date', 'Date')}</th>
                      <th className="py-2 pr-3">{t('displacement.day', 'Day')}</th>
                      <th className="py-2 pr-3 text-right">{t('displacement.occ', 'Occ%')}</th>
                      <th className="py-2 pr-3 text-right">{t('displacement.availShort', 'Avail')}</th>
                      <th className="py-2 pr-3 text-right">{t('displacement.transientRate', 'Transient Rate')}</th>
                      <th className="py-2 pr-3 text-right">{t('displacement.displaced', 'Displaced')}</th>
                      <th className="py-2 pr-3 text-right">{t('displacement.proposed', 'Proposed')}</th>
                      <th className="py-2 pr-3 text-right">{t('displacement.net', 'Net')}</th>
                      <th className="py-2 pr-3 text-center">{t('displacement.verdict', 'Verdict')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(result.daily_analysis || []).map((d, i) => (
                      <tr key={i} className="border-b last:border-0 hover:bg-gray-50">
                        <td className="py-2 pr-3 font-mono text-xs">{d.date?.slice(5)}</td>
                        <td className="py-2 pr-3 text-xs text-gray-500">{d.day_of_week?.slice(0, 3)}</td>
                        <td className="py-2 pr-3 text-right">
                          <span className={`font-medium ${d.current_occupancy_pct >= 85 ? 'text-red-600' : d.current_occupancy_pct >= 65 ? 'text-amber-600' : 'text-emerald-600'}`}>
                            {d.current_occupancy_pct}%
                          </span>
                        </td>
                        <td className="py-2 pr-3 text-right text-gray-600">{d.available_rooms}</td>
                        <td className="py-2 pr-3 text-right font-medium">₺{fmt(d.expected_transient_rate)}</td>
                        <td className="py-2 pr-3 text-right text-red-600">₺{fmt(d.displaced_revenue)}</td>
                        <td className="py-2 pr-3 text-right text-blue-600">₺{fmt(d.proposed_revenue)}</td>
                        <td className={`py-2 pr-3 text-right font-semibold ${d.net_displacement >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                          ₺{fmt(d.net_displacement)}
                        </td>
                        <td className="py-2 pr-3 text-center">
                          {d.recommendation === 'accept' ?
                            <CheckCircle2 className="w-4 h-4 text-emerald-500 inline" /> :
                            <XCircle className="w-4 h-4 text-red-500 inline" />
                          }
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-semibold">{t('displacement.marketContext', 'Market Context')}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div className="p-3 bg-gray-50 rounded-lg">
                  <p className="text-gray-500 text-xs">{t('displacement.historicalAdr', 'Historical ADR')}</p>
                  <p className="text-lg font-bold">₺{fmt(result.summary.historical_adr)}</p>
                </div>
                <div className="p-3 bg-gray-50 rounded-lg">
                  <p className="text-gray-500 text-xs">{t('displacement.cancelRate', 'Cancel Rate')}</p>
                  <p className="text-lg font-bold">{result.summary.cancellation_rate}%</p>
                </div>
                <div className="p-3 bg-gray-50 rounded-lg">
                  <p className="text-gray-500 text-xs">{t('displacement.totalRoomNights', 'Total Room Nights')}</p>
                  <p className="text-lg font-bold">{result.scenario.total_room_nights}</p>
                </div>
                <div className="p-3 bg-gray-50 rounded-lg">
                  <p className="text-gray-500 text-xs">{t('displacement.oppCost', 'Opportunity Cost')}</p>
                  <p className="text-lg font-bold text-amber-600">₺{fmt(result.summary.total_opportunity_cost)}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
};

const CompareTab = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [form, setForm] = useState({
    check_in: tomorrow(),
    check_out: dayAfter(tomorrow()),
    rooms_requested: 10,
  });
  const [scenarios, setScenarios] = useState([
    { name: t('displacement.scenarioA', 'Scenario A'), rate: 120, ancillary: 10, commission: 0 },
    { name: t('displacement.scenarioB', 'Scenario B'), rate: 100, ancillary: 20, commission: 5 },
  ]);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const addScenario = () => {
    if (scenarios.length >= 5) return;
    setScenarios([...scenarios, { name: `${t('displacement.scenario', 'Scenario')} ${String.fromCharCode(65 + scenarios.length)}`, rate: 100, ancillary: 0, commission: 0 }]);
  };

  const removeScenario = (idx) => {
    setScenarios(scenarios.filter((_, i) => i !== idx));
  };

  const updateScenario = (idx, field, value) => {
    setScenarios(scenarios.map((s, i) => i === idx ? { ...s, [field]: value } : s));
  };

  const runCompare = async () => {
    setLoading(true);
    setResult(null);
    try {
      const res = await axios.post('/api/displacement/compare', {
        check_in: form.check_in,
        check_out: form.check_out,
        rooms_requested: Number(form.rooms_requested),
        scenarios: scenarios.map(s => ({
          name: s.name,
          rate: Number(s.rate),
          ancillary: Number(s.ancillary),
          commission: Number(s.commission),
        })),
      });
      setResult(res.data);
    } catch (e) {
      console.error('Compare error:', e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <GitCompare className="w-4 h-4" />
            {t('displacement.compareScenarios', 'Compare Scenarios')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            <div>
              <Label className="text-xs">{t('displacement.checkIn', 'Check-in')}</Label>
              <Input type="date" value={form.check_in} onChange={e => setForm({ ...form, check_in: e.target.value })} />
            </div>
            <div>
              <Label className="text-xs">{t('displacement.checkOut', 'Check-out')}</Label>
              <Input type="date" value={form.check_out} onChange={e => setForm({ ...form, check_out: e.target.value })} />
            </div>
            <div>
              <Label className="text-xs">{t('displacement.roomsRequested', 'Rooms Requested')}</Label>
              <Input type="number" min={1} value={form.rooms_requested} onChange={e => setForm({ ...form, rooms_requested: e.target.value })} />
            </div>
          </div>

          <div className="space-y-3">
            {scenarios.map((sc, i) => (
              <div key={i} className="flex items-end gap-3 p-3 border rounded-lg bg-gray-50">
                <div className="flex-1">
                  <Label className="text-xs">{t('displacement.name', 'Name')}</Label>
                  <Input value={sc.name} onChange={e => updateScenario(i, 'name', e.target.value)} />
                </div>
                <div className="w-28">
                  <Label className="text-xs">{t('displacement.rate', 'Rate (₺)')}</Label>
                  <Input type="number" min={0} value={sc.rate} onChange={e => updateScenario(i, 'rate', e.target.value)} />
                </div>
                <div className="w-28">
                  <Label className="text-xs">{t('displacement.ancShort', 'Ancillary')}</Label>
                  <Input type="number" min={0} value={sc.ancillary} onChange={e => updateScenario(i, 'ancillary', e.target.value)} />
                </div>
                <div className="w-24">
                  <Label className="text-xs">{t('displacement.commShort', 'Comm%')}</Label>
                  <Input type="number" min={0} max={100} value={sc.commission} onChange={e => updateScenario(i, 'commission', e.target.value)} />
                </div>
                {scenarios.length > 1 && (
                  <Button size="icon" variant="ghost" onClick={() => removeScenario(i)} className="text-red-500">
                    <Trash2 className="w-4 h-4" />
                  </Button>
                )}
              </div>
            ))}
          </div>

          <div className="flex items-center gap-3 mt-4">
            <Button variant="outline" onClick={addScenario} disabled={scenarios.length >= 5}>
              <Plus className="w-4 h-4 mr-1" /> {t('displacement.addScenario', 'Add Scenario')}
            </Button>
            <Button onClick={runCompare} disabled={loading}>
              {loading ? <RefreshCw className="w-4 h-4 animate-spin mr-2" /> : <GitCompare className="w-4 h-4 mr-2" />}
              {t('displacement.compare', 'Compare')}
            </Button>
          </div>
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base font-semibold">{t('displacement.comparisonResults', 'Comparison Results')}</CardTitle>
              {result.best_scenario && (
                <Badge className="bg-emerald-100 text-emerald-700">
                  {t('displacement.bestChoice', 'Best')}: {result.best_scenario}
                </Badge>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {(result.scenarios || []).map((sc, i) => {
                const isAccept = sc.recommendation === 'accept';
                const isBest = sc.scenario_name === result.best_scenario;
                return (
                  <div key={i} className={`p-4 rounded-xl border-2 ${isBest ? 'border-emerald-400 bg-emerald-50/50 ring-2 ring-emerald-200' : 'border-gray-200 bg-white'}`}>
                    <div className="flex items-center justify-between mb-3">
                      <h4 className="font-semibold text-sm">{sc.scenario_name || `Scenario ${i + 1}`}</h4>
                      <Badge className={isAccept ? 'bg-emerald-100 text-emerald-700' : sc.recommendation === 'conditional' ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'}>
                        {sc.recommendation?.toUpperCase()}
                      </Badge>
                    </div>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-500">{t('displacement.rate', 'Rate')}</span>
                        <span className="font-medium">₺{fmt(sc.proposed_rate)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-500">{t('displacement.proposedRevenue', 'Proposed')}</span>
                        <span className="font-medium text-blue-600">₺{fmt(sc.total_proposed)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-500">{t('displacement.displaced', 'Displaced')}</span>
                        <span className="font-medium text-red-600">₺{fmt(sc.total_displaced)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-500">{t('displacement.ancillaryRevenue', 'Ancillary')}</span>
                        <span className="font-medium text-purple-600">₺{fmt(sc.total_ancillary)}</span>
                      </div>
                      <div className="border-t pt-2 flex justify-between">
                        <span className="font-semibold">{t('displacement.net', 'Net')}</span>
                        <span className={`font-bold ${sc.net_displacement >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                          ₺{fmt(sc.net_displacement)}
                        </span>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="text-gray-400">ROI</span>
                        <span className="font-medium">{fmtPct(sc.roi_pct)}</span>
                      </div>
                    </div>
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

const HistoryTab = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await axios.get('/api/displacement/history?limit=20');
        setData(Array.isArray(res.data) ? res.data : []);
      } catch (e) {
        console.error('History error:', e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <LoadingState text={t('displacement.loadingHistory', 'Loading history...')} />;

  if (!data.length) {
    return (
      <EmptyState text={t('displacement.noHistory', 'No saved analyses yet. Run an analysis and save it to see history here.')} />
    );
  }

  return (
    <div className="space-y-3">
      {data.map((item, i) => {
        const rec = item.recommendation?.action;
        const recS = REC_STYLES[rec] || REC_STYLES.conditional;
        const RecI = recS.icon;
        return (
          <Card key={i}>
            <CardContent className="p-4">
              <div className="flex items-center gap-4">
                <RecI className={`w-6 h-6 ${recS.color}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h4 className="font-semibold text-sm truncate">{item.scenario?.group_name || 'Unnamed'}</h4>
                    <Badge className={recS.bg + ' ' + recS.color + ' text-[10px]'}>
                      {rec?.toUpperCase()}
                    </Badge>
                  </div>
                  <p className="text-xs text-gray-500">
                    {item.scenario?.check_in} → {item.scenario?.check_out} · {item.scenario?.rooms_requested} {t('displacement.rooms', 'rooms')} · ₺{item.scenario?.proposed_rate}/{t('displacement.night', 'night')}
                  </p>
                </div>
                <div className="text-right">
                  <p className={`font-bold ${item.summary?.net_displacement >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                    ₺{fmt(item.summary?.net_displacement)}
                  </p>
                  <p className="text-[10px] text-gray-400">{item.created_at?.slice(0, 10)}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
};

const MetricCard = ({ icon: Icon, label, value, prefix = '' }) => (
  <Card>
    <CardContent className="p-4 flex items-center gap-3">
      <div className="p-2.5 rounded-lg bg-blue-50">
        <Icon className="w-5 h-5 text-blue-600" />
      </div>
      <div>
        <p className="text-xs text-gray-500">{label}</p>
        <p className="text-lg font-bold">{prefix}{value}</p>
      </div>
    </CardContent>
  </Card>
);

const SummaryCard = ({ label, value, icon: Icon, color }) => (
  <Card>
    <CardContent className="p-3 text-center">
      <Icon className={`w-5 h-5 mx-auto mb-1 ${color}`} />
      <p className={`text-sm font-bold ${color}`}>{value}</p>
      <p className="text-[10px] text-gray-500 mt-0.5">{label}</p>
    </CardContent>
  </Card>
);

const LoadingState = ({ text }) => (
  <div className="flex items-center justify-center py-20 text-gray-500">
    <RefreshCw className="w-5 h-5 animate-spin mr-2" />
    {text}
  </div>
);

const EmptyState = ({ text }) => (
  <div className="flex flex-col items-center justify-center py-20 text-gray-400">
    <Info className="w-10 h-10 mb-3" />
    <p className="text-sm text-center max-w-md">{text}</p>
  </div>
);

const TABS = [
  { id: 'overview', icon: LayoutDashboard, labelKey: 'displacement.tabOverview' },
  { id: 'analyze', icon: Target, labelKey: 'displacement.tabAnalyze' },
  { id: 'compare', icon: GitCompare, labelKey: 'displacement.tabCompare' },
  { id: 'history', icon: History, labelKey: 'displacement.tabHistory' },
];

const TAB_LABELS = {
  'displacement.tabOverview': 'Market Overview',
  'displacement.tabAnalyze': 'Analyze',
  'displacement.tabCompare': 'Compare',
  'displacement.tabHistory': 'History',
};

const DisplacementAnalysis = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('overview');

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="displacement_analysis">
      <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{t('displacement.title', 'Displacement Analysis')}</h1>
            <p className="text-sm text-gray-500 mt-1">{t('displacement.subtitle', 'Evaluate group bookings against transient displacement to maximize revenue')}</p>
          </div>
        </div>

        <div className="flex gap-1 border-b">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {t(tab.labelKey, TAB_LABELS[tab.labelKey])}
            </button>
          ))}
        </div>

        {activeTab === 'overview' && <MarketOverviewTab user={user} tenant={tenant} onLogout={onLogout} />}
        {activeTab === 'analyze' && <AnalysisTab user={user} tenant={tenant} onLogout={onLogout} />}
        {activeTab === 'compare' && <CompareTab user={user} tenant={tenant} onLogout={onLogout} />}
        {activeTab === 'history' && <HistoryTab user={user} tenant={tenant} onLogout={onLogout} />}
      </div>
    </Layout>
  );
};

export default DisplacementAnalysis;
