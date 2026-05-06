import React, { useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  TrendingUp, TrendingDown, BarChart3, Plus, Save, ArrowRight,
  Info, Target, ArrowUpRight, ArrowDownRight, RefreshCw,
  CheckCircle2, XCircle,
} from 'lucide-react';
import { fmt, fmtPct, tomorrow, dayAfter } from './helpers';
import { REC_STYLES, SummaryCard } from './shared';

const AnalysisTab = ({ user, tenant, onLogout } = {}) => {  
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

  const buildPayload = () => ({
    ...form,
    rooms_requested: Number(form.rooms_requested),
    proposed_rate: Number(form.proposed_rate),
    ancillary_per_room: Number(form.ancillary_per_room),
    commission_pct: Number(form.commission_pct),
  });

  const runAnalysis = async () => {
    setLoading(true);
    setResult(null);
    try {
      const res = await axios.post('/displacement/analyze', buildPayload());
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
      await axios.post('/displacement/save', buildPayload());
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
            <SummaryCard label={t('displacement.ancillaryRevenue', 'Ancillary Revenue')} value={`₺${fmt(result.summary.total_ancillary_revenue)}`} icon={Plus} color="text-indigo-600" />
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

export default AnalysisTab;
