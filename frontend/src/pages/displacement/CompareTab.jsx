import React, { useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Plus, Trash2, RefreshCw, GitCompare } from 'lucide-react';
import { fmt, fmtPct, tomorrow, dayAfter } from './helpers';

const CompareTab = ({ user, tenant, onLogout } = {}) => {  
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
      const res = await axios.post('/displacement/compare', {
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

export default CompareTab;
