import { useState, useEffect } from 'react';
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

const DAYS = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar'];
const ROOM_TYPES = ['Standart Oda', 'Deluxe Oda', 'Corner Suit', 'Junior Suit', 'Kral Dairesi'];

const defaultHurdle = () => ROOM_TYPES.reduce((acc, rt) => ({ ...acc, [rt]: { min_rate: 0, bar: 0, active: false } }), {});
const defaultDayPricing = () => ROOM_TYPES.reduce((acc, rt) => ({
  ...acc, [rt]: DAYS.reduce((d, day) => ({ ...d, [day]: { rate: 0, min_stay: 1 } }), {})
}), {});
const defaultOverbooking = (total) => ({ enabled: false, max_percentage: 5, walk_compensation: 'upgrade_nearby', walk_amount: 0, current_overbooked: 0, total_rooms: total });

const RevenueControls = ({ rooms = [] }) => {
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
      toast.success(section === 'hurdle' ? 'Engel fiyatlar kaydedildi' : section === 'daypricing' ? 'Gün bazlı fiyatlandırma kaydedildi' : 'Overbooking ayarları kaydedildi');
    } catch {
      toast.error('Ayarlar kaydedilemedi');

    } finally {
      setSaving(false);
    }
  };

  const processWalk = async () => {
    if (!walkData.guest_name) return;
    try {
      await axios.post('/revenue/walk-out', walkData);
      toast.success(`${walkData.guest_name} walk-out işlemi tamamlandı`);
      setShowWalkDialog(false);
      setWalkData({ guest_name: '', room_type: '', compensation_type: 'upgrade_nearby', compensation_amount: 0, nearby_hotel: '', notes: '' });
    } catch {
      toast.error('Walk-out işlemi başarısız');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <TrendingUp className="h-5 w-5" /> Gelir Kontrolleri
        </h2>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="hurdle">Engel Fiyat (BAR)</TabsTrigger>
          <TabsTrigger value="daypricing">Gün Bazlı Fiyat</TabsTrigger>
          <TabsTrigger value="overbooking">Overbooking</TabsTrigger>
        </TabsList>

        <TabsContent value="hurdle" className="space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">Minimum Satış Fiyatları (Hurdle Rate / BAR)</CardTitle>
                <Button size="sm" onClick={() => saveAll('hurdle')} disabled={saving}><Save className="h-3 w-3 mr-1" /> Kaydet</Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted"><tr><th className="p-2 text-left">Oda Tipi</th><th className="p-2 text-center">Min. Fiyat (TL)</th><th className="p-2 text-center">BAR Fiyat (TL)</th><th className="p-2 text-center">Aktif</th></tr></thead>
                  <tbody>
                    {ROOM_TYPES.map(rt => (
                      <tr key={rt} className="border-t">
                        <td className="p-2 font-medium">{rt}</td>
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
                Engel fiyat aktif olduğunda, bu fiyatın altında rezervasyon alınmaz.
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="daypricing" className="space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">Gün Bazlı Fiyatlandırma Matrisi</CardTitle>
                <Button size="sm" onClick={() => saveAll('daypricing')} disabled={saving}><Save className="h-3 w-3 mr-1" /> Kaydet</Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted">
                    <tr>
                      <th className="p-2 text-left">Oda Tipi</th>
                      {DAYS.map(d => <th key={d} className="p-2 text-center text-xs">{d.substring(0,3)}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {ROOM_TYPES.map(rt => (
                      <tr key={rt} className="border-t">
                        <td className="p-2 font-medium text-xs">{rt}</td>
                        {DAYS.map(day => (
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
                <Label className="text-xs">Minimum Konaklama Süresi (tüm oda tipleri için)</Label>
                <div className="flex gap-2 mt-1 flex-wrap">
                  {DAYS.map(day => (
                    <div key={day} className="text-center">
                      <div className="text-xs text-muted-foreground">{day.substring(0,3)}</div>
                      <Input type="number" min="1" max="14" className="w-12 h-7 text-xs" value={dayPricing[ROOM_TYPES[0]]?.[day]?.min_stay || 1} onChange={e => { ROOM_TYPES.forEach(rt => updateDayPrice(rt, day, 'min_stay', e.target.value)); }} />
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
              <CardHeader className="pb-2"><CardTitle className="text-sm">Overbooking Ayarları</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label>Overbooking Aktif</Label>
                  <Button size="sm" variant={overbooking.enabled ? 'destructive' : 'default'} onClick={() => setOverbooking(p => ({ ...p, enabled: !p.enabled }))}>
                    {overbooking.enabled ? 'Kapat' : 'Aç'}
                  </Button>
                </div>
                <div>
                  <Label>Maksimum Overbooking (%)</Label>
                  <Input type="number" min="0" max="20" value={overbooking.max_percentage} onChange={e => setOverbooking(p => ({ ...p, max_percentage: parseInt(e.target.value) || 0 }))} />
                  <p className="text-xs text-muted-foreground mt-1">Maks. {Math.floor(overbooking.total_rooms * overbooking.max_percentage / 100)} ekstra rezervasyon</p>
                </div>
                <div>
                  <Label>Walk-Out Tazminatı</Label>
                  <Select value={overbooking.walk_compensation} onValueChange={v => setOverbooking(p => ({ ...p, walk_compensation: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="upgrade_nearby">Yakındaki otelde upgrade</SelectItem>
                      <SelectItem value="cash">Nakit tazminat</SelectItem>
                      <SelectItem value="free_night">Ücretsiz gece (gelecek konaklama)</SelectItem>
                      <SelectItem value="combo">Nakit + Gelecek ücretsiz gece</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Tazminat Tutarı (₺)</Label>
                  <Input type="number" value={overbooking.walk_amount} onChange={e => setOverbooking(p => ({ ...p, walk_amount: parseInt(e.target.value) || 0 }))} />
                </div>
                <Button className="w-full" onClick={() => saveAll('overbooking')} disabled={saving}><Save className="h-4 w-4 mr-1" /> Ayarları Kaydet</Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Walk-Out İşlemi</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <div className="p-4 bg-muted rounded-lg text-center">
                  <div className="text-3xl font-bold">{overbooking.current_overbooked || 0}</div>
                  <div className="text-sm text-muted-foreground">Mevcut Overbook</div>
                  <div className="text-xs mt-1">Kapasite: {overbooking.total_rooms} + {Math.floor(overbooking.total_rooms * overbooking.max_percentage / 100)} = {overbooking.total_rooms + Math.floor(overbooking.total_rooms * overbooking.max_percentage / 100)}</div>
                </div>
                <Button className="w-full" variant="destructive" onClick={() => setShowWalkDialog(true)}>
                  <Users className="h-4 w-4 mr-1" /> Walk-Out İşlemi Başlat
                </Button>
              </CardContent>
            </Card>
          </div>

          <Dialog open={showWalkDialog} onOpenChange={setShowWalkDialog}>
            <DialogContent>
              <DialogHeader><DialogTitle>Walk-Out Tazminat İşlemi</DialogTitle></DialogHeader>
              <div className="space-y-3">
                <div><Label>Misafir Adı</Label><Input value={walkData.guest_name} onChange={e => setWalkData(p => ({ ...p, guest_name: e.target.value }))} /></div>
                <div><Label>Oda Tipi</Label><Input value={walkData.room_type} onChange={e => setWalkData(p => ({ ...p, room_type: e.target.value }))} /></div>
                <div>
                  <Label>Tazminat Tipi</Label>
                  <Select value={walkData.compensation_type} onValueChange={v => setWalkData(p => ({ ...p, compensation_type: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="upgrade_nearby">Yakın otele yönlendir</SelectItem>
                      <SelectItem value="cash">Nakit tazminat</SelectItem>
                      <SelectItem value="free_night">Ücretsiz gece</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div><Label>Tazminat Tutarı (₺)</Label><Input type="number" value={walkData.compensation_amount} onChange={e => setWalkData(p => ({ ...p, compensation_amount: e.target.value }))} /></div>
                <div><Label>Yönlendirilen Otel</Label><Input value={walkData.nearby_hotel} onChange={e => setWalkData(p => ({ ...p, nearby_hotel: e.target.value }))} placeholder="Otel adı..." /></div>
                <div><Label>Notlar</Label><Input value={walkData.notes} onChange={e => setWalkData(p => ({ ...p, notes: e.target.value }))} /></div>
                <Button className="w-full" variant="destructive" onClick={processWalk}>Walk-Out Tamamla</Button>
              </div>
            </DialogContent>
          </Dialog>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default RevenueControls;
