import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  TrendingUp, AlertTriangle, Lock, Unlock, Save, Users
} from 'lucide-react';

const DAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
const RT_KEYS = ['standard', 'deluxe', 'cornerSuite', 'juniorSuite', 'kingSuite'];

const defaultHurdle = () => RT_KEYS.reduce((acc, rt) => ({ ...acc, [rt]: { min_rate: 0, bar: 0, active: false } }), {});
const defaultDayPricing = () => RT_KEYS.reduce((acc, rt) => ({
  ...acc, [rt]: DAY_KEYS.reduce((d, day) => ({ ...d, [day]: { rate: 0, min_stay: 1 } }), {})
}), {});
const defaultOverbooking = (total) => ({ enabled: false, max_percentage: 5, walk_compensation: 'upgrade_nearby', walk_amount: 0, current_overbooked: 0, total_rooms: total });

const RevenueControls = ({ rooms = [] }) => {
  const { t } = useTranslation();
  const tr = (k) => t(`pmsComponents.revenue.${k}`);
  const cur = t('pmsComponents.common.currency');

  const [activeTab, setActiveTab] = useState('hurdle');
  const [hurdleRates, setHurdleRates] = useState(defaultHurdle());
  const [dayPricing, setDayPricing] = useState(defaultDayPricing());
  const [overbooking, setOverbooking] = useState(defaultOverbooking(rooms.length || 30));
  const [showWalkDialog, setShowWalkDialog] = useState(false);
  const [saving, setSaving] = useState(false);
  const [walkData, setWalkData] = useState({ guest_name: '', room_type: '', compensation_type: 'upgrade_nearby', compensation_amount: 0, nearby_hotel: '', notes: '' });

  useEffect(() => { loadSettings(); }, []);

  const loadSettings = async () => {
    try {
      const res = await axios.get('/revenue/settings');
      if (res.data.hurdle_rates && Object.keys(res.data.hurdle_rates).length > 0) setHurdleRates(res.data.hurdle_rates);
      if (res.data.day_pricing && Object.keys(res.data.day_pricing).length > 0) setDayPricing(res.data.day_pricing);
      if (res.data.overbooking) setOverbooking(prev => ({ ...prev, ...res.data.overbooking, total_rooms: rooms.length || prev.total_rooms }));
    } catch {
      /* use defaults */
    }
  };

  const updateHurdle = (rt, field, value) => {
    setHurdleRates(prev => ({ ...prev, [rt]: { ...prev[rt], [field]: field === 'active' ? value : parseFloat(value) || 0 } }));
  };

  const updateDayPrice = (rt, day, field, value) => {
    setDayPricing(prev => ({
      ...prev, [rt]: { ...prev[rt], [day]: { ...prev[rt][day], [field]: field === 'min_stay' ? parseInt(value) || 1 : parseFloat(value) || 0 } }
    }));
  };

  const saveAll = async (section) => {
    setSaving(true);
    try {
      await axios.put('/revenue/settings', { hurdle_rates: hurdleRates, day_pricing: dayPricing, overbooking });
      toast.success(section === 'hurdle' ? tr('hurdleSaved') : section === 'daypricing' ? tr('dayPricingSaved') : tr('overbookingSaved'));
    } catch {
      toast.error(tr('saveError'));
    } finally {
      setSaving(false);
    }
  };

  const processWalk = async () => {
    if (!walkData.guest_name) return;
    try {
      await axios.post('/revenue/walk-out', walkData);
      toast.success(tr('walkOutCompleted'));
      setShowWalkDialog(false);
      setWalkData({ guest_name: '', room_type: '', compensation_type: 'upgrade_nearby', compensation_amount: 0, nearby_hotel: '', notes: '' });
    } catch {
      toast.error(tr('walkOutError'));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <TrendingUp className="h-5 w-5" /> {tr('title')}
        </h2>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="hurdle">{tr('hurdleTab')}</TabsTrigger>
          <TabsTrigger value="daypricing">{tr('dayPricingTab')}</TabsTrigger>
          <TabsTrigger value="overbooking">{tr('overbookingTab')}</TabsTrigger>
        </TabsList>

        <TabsContent value="hurdle" className="space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">{tr('hurdleTitle')}</CardTitle>
                <Button size="sm" onClick={() => saveAll('hurdle')} disabled={saving}><Save className="h-3 w-3 mr-1" /> {tr('save')}</Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted"><tr><th className="p-2 text-left">{tr('roomType')}</th><th className="p-2 text-center">{tr('minPrice')} ({cur})</th><th className="p-2 text-center">{tr('barPrice')} ({cur})</th><th className="p-2 text-center">{tr('activeLabel')}</th></tr></thead>
                  <tbody>
                    {RT_KEYS.map(rt => (
                      <tr key={rt} className="border-t">
                        <td className="p-2 font-medium">{tr(`roomTypes.${rt}`)}</td>
                        <td className="p-2"><Input type="number" className="w-28 h-8 text-sm mx-auto" value={hurdleRates[rt]?.min_rate || ''} onChange={e => updateHurdle(rt, 'min_rate', e.target.value)} placeholder="0" /></td>
                        <td className="p-2"><Input type="number" className="w-28 h-8 text-sm mx-auto" value={hurdleRates[rt]?.bar || ''} onChange={e => updateHurdle(rt, 'bar', e.target.value)} placeholder="0" /></td>
                        <td className="p-2 text-center">
                          <Button size="sm" variant={hurdleRates[rt]?.active ? 'default' : 'outline'} onClick={() => updateHurdle(rt, 'active', !hurdleRates[rt]?.active)}>
                            {hurdleRates[rt]?.active ? <Lock className="h-3 w-3" /> : <Unlock className="h-3 w-3" />}
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                <AlertTriangle className="h-3 w-3 inline mr-1" />
                {tr('hurdleNote')}
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="daypricing" className="space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">{tr('dayPricingTitle')}</CardTitle>
                <Button size="sm" onClick={() => saveAll('daypricing')} disabled={saving}><Save className="h-3 w-3 mr-1" /> {tr('save')}</Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted">
                    <tr>
                      <th className="p-2 text-left">{tr('roomType')}</th>
                      {DAY_KEYS.map(d => <th key={d} className="p-2 text-center text-xs">{tr(`days.${d}`)}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {RT_KEYS.map(rt => (
                      <tr key={rt} className="border-t">
                        <td className="p-2 font-medium text-xs">{tr(`roomTypes.${rt}`)}</td>
                        {DAY_KEYS.map(day => (
                          <td key={day} className="p-1">
                            <Input type="number" className="w-16 h-7 text-xs" value={dayPricing[rt]?.[day]?.rate || ''} onChange={e => updateDayPrice(rt, day, 'rate', e.target.value)} placeholder="0" />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-3">
                <Label className="text-xs">{tr('minStayLabel')}</Label>
                <div className="flex gap-2 mt-1 flex-wrap">
                  {DAY_KEYS.map(day => (
                    <div key={day} className="text-center">
                      <div className="text-xs text-muted-foreground">{tr(`days.${day}`)}</div>
                      <Input type="number" min="1" max="14" className="w-12 h-7 text-xs" value={dayPricing[RT_KEYS[0]]?.[day]?.min_stay || 1} onChange={e => { RT_KEYS.forEach(rt => updateDayPrice(rt, day, 'min_stay', e.target.value)); }} />
                    </div>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="overbooking" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">{tr('overbookingSettings')}</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label>{tr('overbookingActive')}</Label>
                  <Button size="sm" variant={overbooking.enabled ? 'destructive' : 'default'} onClick={() => setOverbooking(p => ({ ...p, enabled: !p.enabled }))}>
                    {overbooking.enabled ? tr('turnOff') : tr('turnOn')}
                  </Button>
                </div>
                <div>
                  <Label>{tr('maxOverbooking')}</Label>
                  <Input type="number" min="0" max="20" value={overbooking.max_percentage} onChange={e => setOverbooking(p => ({ ...p, max_percentage: parseInt(e.target.value) || 0 }))} />
                  <p className="text-xs text-muted-foreground mt-1">{t('pmsComponents.revenue.maxExtra', { count: Math.floor(overbooking.total_rooms * overbooking.max_percentage / 100) })}</p>
                </div>
                <div>
                  <Label>{tr('walkCompensation')}</Label>
                  <Select value={overbooking.walk_compensation} onValueChange={v => setOverbooking(p => ({ ...p, walk_compensation: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="upgrade_nearby">{tr('upgradeNearby')}</SelectItem>
                      <SelectItem value="cash">{tr('cashComp')}</SelectItem>
                      <SelectItem value="free_night">{tr('freeNight')}</SelectItem>
                      <SelectItem value="combo">{tr('combo')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>{tr('compensationAmount')} ({cur})</Label>
                  <Input type="number" value={overbooking.walk_amount} onChange={e => setOverbooking(p => ({ ...p, walk_amount: parseInt(e.target.value) || 0 }))} />
                </div>
                <Button className="w-full" onClick={() => saveAll('overbooking')} disabled={saving}><Save className="h-4 w-4 mr-1" /> {tr('saveSettings')}</Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">{tr('walkOutSection')}</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <div className="p-4 bg-muted rounded-lg text-center">
                  <div className="text-3xl font-bold">{overbooking.current_overbooked || 0}</div>
                  <div className="text-sm text-muted-foreground">{tr('currentOverbook')}</div>
                  <div className="text-xs mt-1">{tr('capacity')} {overbooking.total_rooms} + {Math.floor(overbooking.total_rooms * overbooking.max_percentage / 100)} = {overbooking.total_rooms + Math.floor(overbooking.total_rooms * overbooking.max_percentage / 100)}</div>
                </div>
                <Button className="w-full" variant="destructive" onClick={() => setShowWalkDialog(true)}>
                  <Users className="h-4 w-4 mr-1" /> {tr('startWalkOut')}
                </Button>
              </CardContent>
            </Card>
          </div>

          <Dialog open={showWalkDialog} onOpenChange={setShowWalkDialog}>
            <DialogContent>
              <DialogHeader><DialogTitle>{tr('walkOutTitle')}</DialogTitle></DialogHeader>
              <div className="space-y-3">
                <div><Label>{tr('guestName')}</Label><Input value={walkData.guest_name} onChange={e => setWalkData(p => ({ ...p, guest_name: e.target.value }))} /></div>
                <div><Label>{tr('roomTypeLabel')}</Label><Input value={walkData.room_type} onChange={e => setWalkData(p => ({ ...p, room_type: e.target.value }))} /></div>
                <div>
                  <Label>{tr('compensationType')}</Label>
                  <Select value={walkData.compensation_type} onValueChange={v => setWalkData(p => ({ ...p, compensation_type: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="upgrade_nearby">{tr('redirectToNearby')}</SelectItem>
                      <SelectItem value="cash">{tr('cashComp')}</SelectItem>
                      <SelectItem value="free_night">{tr('freeNight')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div><Label>{tr('compensationAmount')} ({cur})</Label><Input type="number" value={walkData.compensation_amount} onChange={e => setWalkData(p => ({ ...p, compensation_amount: e.target.value }))} /></div>
                <div><Label>{tr('nearbyHotel')}</Label><Input value={walkData.nearby_hotel} onChange={e => setWalkData(p => ({ ...p, nearby_hotel: e.target.value }))} placeholder={tr('nearbyPlaceholder')} /></div>
                <div><Label>{tr('notes')}</Label><Input value={walkData.notes} onChange={e => setWalkData(p => ({ ...p, notes: e.target.value }))} /></div>
                <Button className="w-full" variant="destructive" onClick={processWalk}>{tr('completeWalkOut')}</Button>
              </div>
            </DialogContent>
          </Dialog>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default RevenueControls;
