import { useState, useEffect, useCallback, useMemo } from 'react';
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
import { cachedTenantCurrency } from '@/lib/currency';

const DAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
const RT_KEYS = ['standard', 'deluxe', 'cornerSuite', 'juniorSuite', 'kingSuite'];

const defaultOverbooking = () => ({ enabled: false, max_percentage: 5, walk_compensation: 'upgrade_nearby', walk_amount: 0 });
const numeric = (value, minimum = 0, maximum = 1e9, integer = false) => {
  if (typeof value === 'boolean' || value == null || String(value).trim() === '') throw new Error('Invalid value');
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < minimum || parsed > maximum || (integer && !Number.isInteger(parsed))) throw new Error('Invalid value');
  return parsed;
};

const RevenueControls = ({ rooms = [] }) => {
  const { t } = useTranslation();
  const tr = useCallback((k) => t(`pmsComponents.revenue.${k}`), [t]);
  const cur = cachedTenantCurrency();
  const physicalRooms = useMemo(() => rooms.filter(room => room.is_active !== false && !room.is_virtual), [rooms]);
  const roomTypeLabels = useMemo(() => {
    const labels = {};
    physicalRooms.forEach(room => {
      const key = String(room.room_type_id || room.type_id || room.room_type || room.type || '').trim();
      if (key) labels[key] = room.room_type_name || room.type_name || room.room_type || room.type || key;
    });
    return labels;
  }, [physicalRooms]);

  const [activeTab, setActiveTab] = useState('hurdle');
  const [hurdleRates, setHurdleRates] = useState({});
  const [dayPricing, setDayPricing] = useState({});
  const [overbooking, setOverbooking] = useState(defaultOverbooking());
  const [revisions, setRevisions] = useState({});
  const [conflict, setConflict] = useState(false);
  const [walking, setWalking] = useState(false);
  const [showWalkDialog, setShowWalkDialog] = useState(false);
  const [saving, setSaving] = useState(false);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [walkData, setWalkData] = useState({ guest_name: '', room_type: '', compensation_type: 'upgrade_nearby', compensation_amount: 0, nearby_hotel: '', notes: '', request_id: '' });

  const loadSettings = useCallback(async () => {
    setLoadError(false);
    setSettingsLoaded(false);
    try {
      const res = await axios.get('/revenue/settings');
      if (!['hurdle_rates', 'day_pricing', 'overbooking'].every(key => typeof res.data.section_revisions?.[key] === 'string' && res.data.section_revisions[key].length === 64)) throw new Error('Missing section versions');
      setHurdleRates(res.data.hurdle_rates || {});
      setDayPricing(res.data.day_pricing || {});
      setOverbooking({ ...defaultOverbooking(), ...res.data.overbooking });
      setRevisions(res.data.section_revisions || {});
      setConflict(false);
      setSettingsLoaded(true);
    } catch {
      setLoadError(true);
      setSettingsLoaded(false);
      toast.error(tr('loadError'));
    }
  }, [tr]);

  useEffect(() => { loadSettings(); }, [loadSettings]);

  const roomTypeKeys = Object.keys(roomTypeLabels);
  const unsupported = {
    hurdle: Object.keys(hurdleRates).some(key => !roomTypeKeys.includes(key)),
    daypricing: Object.keys(dayPricing).some(key => !roomTypeKeys.includes(key)),
  };
  const roomTypeLabel = key => roomTypeLabels[key] || (RT_KEYS.includes(key) ? tr(`roomTypes.${key}`) : key);

  const updateHurdle = (rt, field, value) => {
    setHurdleRates(prev => ({ ...prev, [rt]: { ...(prev[rt] || { min_rate: 0, bar: 0, active: false }), [field]: value } }));
  };

  const updateDayPrice = (rt, day, field, value) => {
    setDayPricing(prev => ({
      ...prev, [rt]: { ...(prev[rt] || {}), [day]: { ...(prev[rt]?.[day] || { rate: 0, min_stay: 1 }), [field]: value } }
    }));
  };

  const saveAll = async (section) => {
    const field = { hurdle: 'hurdle_rates', daypricing: 'day_pricing', overbooking: 'overbooking' }[section];
    let value;
    try {
      if (!roomTypeKeys.length) throw new Error('Missing inventory');
      if (field === 'hurdle_rates') value = Object.fromEntries(roomTypeKeys.map(rt => [rt, {
        min_rate: numeric(hurdleRates[rt]?.min_rate ?? 0), bar: numeric(hurdleRates[rt]?.bar ?? 0), active: hurdleRates[rt]?.active ?? false
      }]));
      else if (field === 'day_pricing') value = Object.fromEntries(roomTypeKeys.map(rt => [rt, Object.fromEntries(DAY_KEYS.map(day => [day, {
        rate: numeric(dayPricing[rt]?.[day]?.rate ?? 0), min_stay: numeric(dayPricing[rt]?.[day]?.min_stay ?? 1, 1, 365, true)
      }]))]));
      else value = { enabled: overbooking.enabled, max_percentage: numeric(overbooking.max_percentage, 0, 20, true), walk_amount: numeric(overbooking.walk_amount), walk_compensation: overbooking.walk_compensation };
    } catch { toast.error(t('pmsComponents.revenue.validationError', { defaultValue: 'Check room types and numeric limits. Blank, negative or fractional limits are not accepted.' })); return; }
    setSaving(true);
    try {
      const res = await axios.put('/revenue/settings', { [field]: value, expected_revisions: { [field]: revisions[field] } });
      setRevisions(prev => ({ ...prev, ...res.data.section_revisions }));
      toast.success(section === 'hurdle' ? tr('hurdleSaved') : section === 'daypricing' ? tr('dayPricingSaved') : tr('overbookingSaved'));
    } catch (error) {
      if (error.response?.status === 409) setConflict(true);
      toast.error(tr('saveError'));
    } finally {
      setSaving(false);
    }
  };

  const processWalk = async () => {
    let body;
    try {
      if (!walkData.guest_name.trim() || !roomTypeKeys.includes(walkData.room_type)) throw new Error('Missing identity');
      body = { ...walkData, guest_name: walkData.guest_name.trim(), compensation_amount: numeric(walkData.compensation_amount) };
    } catch { toast.error(t('pmsComponents.revenue.validationError', { defaultValue: 'Check the guest, room type and amount.' })); return; }
    setWalking(true);
    try {
      await axios.post('/revenue/walk-out', body);
      toast.success(t('pmsComponents.revenue.walkRecorded', { defaultValue: 'Administrative record saved; no payment or reservation change.' }));
      setShowWalkDialog(false);
      setWalkData({ guest_name: '', room_type: '', compensation_type: 'upgrade_nearby', compensation_amount: 0, nearby_hotel: '', notes: '', request_id: '' });
    } catch {
      toast.error(tr('walkOutError'));
    } finally { setWalking(false); }
  };
  const percentage = Number(overbooking.max_percentage);
  const extraRooms = overbooking.enabled && Number.isInteger(percentage) && percentage >= 0 && percentage <= 20 ? Math.floor(physicalRooms.length * percentage / 100) : 0;
  const cannotSave = saving || !settingsLoaded || conflict || !roomTypeKeys.length;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <TrendingUp className="h-5 w-5" /> {tr('title')}
        </h2>
      </div>
      <div role="note" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">{t('pmsComponents.revenue.planningNote', { defaultValue: 'Planning only: these settings do not automatically apply rates, minimum stays, booking price blocks or overbooking permissions. Use the operational rate/inventory screens for those changes.' })}</div>
      {!roomTypeKeys.length && <div role="alert">{t('pmsComponents.revenue.noInventory', { defaultValue: 'Physical room inventory is required; settings cannot be saved.' })}</div>}
      {(unsupported.hurdle || unsupported.daypricing) && <div role="alert">{t('pmsComponents.revenue.unknownTypes', { defaultValue: 'Stored settings reference room types outside the physical inventory. The affected section cannot be saved; existing values are retained.' })}</div>}
      {conflict && <div role="alert" className="rounded border border-red-300 p-3">{t('pmsComponents.revenue.conflict', { defaultValue: 'Settings changed in another session. Reload before saving.' })}<Button onClick={loadSettings}>{tr('retry')}</Button></div>}

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        {loadError && <div className="mb-3 flex flex-col gap-2 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900 sm:flex-row sm:items-center sm:justify-between"><span>{tr('loadError')}</span><Button size="sm" variant="outline" onClick={loadSettings}>{tr('retry')}</Button></div>}
        <TabsList className="flex w-full justify-start overflow-x-auto">
          <TabsTrigger className="shrink-0" value="hurdle">{tr('hurdleTab')}</TabsTrigger>
          <TabsTrigger className="shrink-0" value="daypricing">{tr('dayPricingTab')}</TabsTrigger>
          <TabsTrigger className="shrink-0" value="overbooking">{tr('overbookingTab')}</TabsTrigger>
        </TabsList>

        <TabsContent value="hurdle" className="space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">{tr('hurdleTitle')}</CardTitle>
                <Button size="sm" onClick={() => saveAll('hurdle')} disabled={cannotSave || unsupported.hurdle}><Save className="h-3 w-3 mr-1" /> {tr('save')}</Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted"><tr><th className="p-2 text-left">{tr('roomType')}</th><th className="p-2 text-center">{tr('minPrice')} ({cur})</th><th className="p-2 text-center">{tr('barPrice')} ({cur})</th><th className="p-2 text-center">{tr('activeLabel')}</th></tr></thead>
                  <tbody>
                    {roomTypeKeys.map(rt => (
                      <tr key={rt} className="border-t">
                        <td className="p-2 font-medium">{roomTypeLabel(rt)}</td>
                        <td className="p-2"><Input aria-label={`${roomTypeLabel(rt)} ${tr('minPrice')}`} type="number" min="0" step="0.01" className="w-28 h-8 text-sm mx-auto" value={hurdleRates[rt]?.min_rate ?? 0} onChange={e => updateHurdle(rt, 'min_rate', e.target.value)} /></td>
                        <td className="p-2"><Input aria-label={`${roomTypeLabel(rt)} ${tr('barPrice')}`} type="number" min="0" step="0.01" className="w-28 h-8 text-sm mx-auto" value={hurdleRates[rt]?.bar ?? 0} onChange={e => updateHurdle(rt, 'bar', e.target.value)} /></td>
                        <td className="p-2 text-center">
                          <Button aria-label={`${roomTypeLabel(rt)} ${tr('activeLabel')}`} aria-pressed={hurdleRates[rt]?.active ?? false} size="sm" variant={hurdleRates[rt]?.active ? 'default' : 'outline'} onClick={() => updateHurdle(rt, 'active', !hurdleRates[rt]?.active)}>
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
                {t('pmsComponents.revenue.planningShort', { defaultValue: 'Saved for planning; no automatic booking-price enforcement.' })}
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="daypricing" className="space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">{tr('dayPricingTitle')}</CardTitle>
                <Button size="sm" onClick={() => saveAll('daypricing')} disabled={cannotSave || unsupported.daypricing}><Save className="h-3 w-3 mr-1" /> {tr('save')}</Button>
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
                    {roomTypeKeys.map(rt => (
                      <tr key={rt} className="border-t">
                        <td className="p-2 font-medium text-xs">{roomTypeLabel(rt)}</td>
                        {DAY_KEYS.map(day => (
                          <td key={day} className="p-1">
                            <Input aria-label={`${roomTypeLabel(rt)} ${day} ${tr('barPrice')}`} type="number" min="0" step="0.01" className="w-16 h-7 text-xs" value={dayPricing[rt]?.[day]?.rate ?? 0} onChange={e => updateDayPrice(rt, day, 'rate', e.target.value)} />
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
                      <Input aria-label={`${day} ${tr('minStayLabel')}`} type="number" min="1" max="365" className="w-12 h-7 text-xs" value={dayPricing[roomTypeKeys[0]]?.[day]?.min_stay ?? 1} onChange={e => { roomTypeKeys.forEach(rt => updateDayPrice(rt, day, 'min_stay', e.target.value)); }} />
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
                  <Input aria-label={tr('maxOverbooking')} type="number" min="0" max="20" step="1" value={overbooking.max_percentage} onChange={e => setOverbooking(p => ({ ...p, max_percentage: e.target.value }))} />
                  <p className="text-xs text-muted-foreground mt-1">{t('pmsComponents.revenue.maxExtra', { count: extraRooms })}</p>
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
                  <Input aria-label={tr('compensationAmount')} type="number" min="0" step="0.01" value={overbooking.walk_amount} onChange={e => setOverbooking(p => ({ ...p, walk_amount: e.target.value }))} />
                </div>
                <Button className="w-full" onClick={() => saveAll('overbooking')} disabled={cannotSave}><Save className="h-4 w-4 mr-1" /> {tr('saveSettings')}</Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">{tr('walkOutSection')}</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <div className="p-4 bg-muted rounded-lg text-center">
                  <div className="text-3xl font-bold">—</div>
                  <div className="text-sm text-muted-foreground">{tr('currentOverbook')}</div>
                  <div className="text-xs text-muted-foreground">{t('pmsComponents.revenue.liveCountUnavailable', { defaultValue: 'A verified live overbooking count is not connected to this screen.' })}</div>
                  <div className="text-xs mt-1">{t('pmsComponents.revenue.plannedCapacity', { defaultValue: 'Planned capacity (not live availability)' })}: {physicalRooms.length} + {extraRooms} = {physicalRooms.length + extraRooms}</div>
                </div>
                <Button className="w-full" variant="destructive" onClick={() => { setWalkData(p => ({ ...p, request_id: p.request_id || crypto.randomUUID() })); setShowWalkDialog(true); }} disabled={!roomTypeKeys.length}>
                  <Users className="h-4 w-4 mr-1" /> {tr('startWalkOut')}
                </Button>
              </CardContent>
            </Card>
          </div>

          <Dialog open={showWalkDialog} onOpenChange={setShowWalkDialog}>
            <DialogContent>
              <DialogHeader><DialogTitle>{tr('walkOutTitle')}</DialogTitle></DialogHeader>
              <div className="space-y-3">
                <p role="note">{t('pmsComponents.revenue.walkNote', { defaultValue: 'Administrative note only. Does not cancel a reservation, change availability or make a compensation payment.' })}</p>
                <div><Label htmlFor="walk-guest">{tr('guestName')}</Label><Input id="walk-guest" maxLength={200} value={walkData.guest_name} onChange={e => setWalkData(p => ({ ...p, guest_name: e.target.value }))} /></div>
                <div><Label>{tr('roomTypeLabel')}</Label><Select value={walkData.room_type} onValueChange={value => setWalkData(p => ({ ...p, room_type: value }))}><SelectTrigger aria-label={tr('roomTypeLabel')}><SelectValue /></SelectTrigger><SelectContent>{roomTypeKeys.map(rt => <SelectItem key={rt} value={rt}>{roomTypeLabel(rt)}</SelectItem>)}</SelectContent></Select></div>
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
                <div><Label htmlFor="walk-amount">{tr('compensationAmount')} ({cur})</Label><Input id="walk-amount" type="number" min="0" step="0.01" value={walkData.compensation_amount} onChange={e => setWalkData(p => ({ ...p, compensation_amount: e.target.value }))} /></div>
                <div><Label>{tr('nearbyHotel')}</Label><Input value={walkData.nearby_hotel} onChange={e => setWalkData(p => ({ ...p, nearby_hotel: e.target.value }))} placeholder={tr('nearbyPlaceholder')} /></div>
                <div><Label>{tr('notes')}</Label><Input value={walkData.notes} onChange={e => setWalkData(p => ({ ...p, notes: e.target.value }))} /></div>
                <Button className="w-full" variant="destructive" onClick={processWalk} disabled={walking}>{t('pmsComponents.revenue.saveWalkRecord', { defaultValue: 'Save administrative note' })}</Button>
              </div>
            </DialogContent>
          </Dialog>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default RevenueControls;
