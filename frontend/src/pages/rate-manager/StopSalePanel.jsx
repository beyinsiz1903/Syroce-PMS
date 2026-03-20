import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import {
  Ban, CheckCircle, Lock, Unlock, Loader2, AlertTriangle,
  Calendar, RefreshCw, BedDouble, Globe
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

export const StopSalePanel = ({ roomTypes, ratePlans, fetchGrid, loading: parentLoading }) => {
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const today = new Date().toISOString().slice(0, 10);
  const nextMonth = new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10);

  const [dateFrom, setDateFrom] = useState(today);
  const [dateTo, setDateTo] = useState(nextMonth);
  const [selectedRoomTypes, setSelectedRoomTypes] = useState(new Set());
  const [saving, setSaving] = useState(false);
  const [activeStopSales, setActiveStopSales] = useState([]);
  const [loadingActive, setLoadingActive] = useState(true);

  // Operator-level stop sale
  const [operatorStatus, setOperatorStatus] = useState({});
  const [operatorLoading, setOperatorLoading] = useState({});

  const defaultOperators = [
    { id: 'booking_com', name: 'Booking.com' },
    { id: 'expedia', name: 'Expedia' },
    { id: 'tatilsepeti', name: 'Tatilsepeti' },
    { id: 'hotelbeds', name: 'Hotelbeds' },
    { id: 'agoda', name: 'Agoda' },
  ];

  const loadActiveStopSales = useCallback(async () => {
    setLoadingActive(true);
    try {
      const { data } = await axios.get(
        `${API}/api/channel-manager/rate-manager/stop-sale-summary?start_date=${today}&end_date=${nextMonth}`,
        { headers }
      );
      setActiveStopSales(data.stops || []);
    } catch {
      console.error('Stop sale durumu yuklenemedi');
    }
    setLoadingActive(false);
  }, [today, nextMonth]);

  const loadOperatorStatus = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/api/rates/stop-sale/status`, { headers });
      setOperatorStatus(data.operators || {});
    } catch {
      console.error('Operator stop-sale durumu yuklenemedi');
    }
  }, []);

  useEffect(() => {
    loadActiveStopSales();
    loadOperatorStatus();
  }, [loadActiveStopSales, loadOperatorStatus]);

  const toggleRoomType = (code) => {
    setSelectedRoomTypes(prev => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code); else next.add(code);
      return next;
    });
  };

  const selectAllRoomTypes = () => {
    if (selectedRoomTypes.size === roomTypes.length) {
      setSelectedRoomTypes(new Set());
    } else {
      setSelectedRoomTypes(new Set(roomTypes.map(rt => rt.code)));
    }
  };

  const applyStopSale = async (stopSell) => {
    if (selectedRoomTypes.size === 0) {
      toast.error('Lutfen en az bir oda tipi secin');
      return;
    }
    if (!dateFrom || !dateTo) {
      toast.error('Lutfen tarih araligi secin');
      return;
    }

    setSaving(true);
    try {
      const perRoomValues = Array.from(selectedRoomTypes).map(rtCode => ({
        room_type_code: rtCode,
        rate_plan_codes: ratePlans.map(rp => rp.code),
        stop_sell: stopSell,
      }));

      const { data } = await axios.post(
        `${API}/api/channel-manager/rate-manager/bulk-grid-update`,
        {
          per_room_values: perRoomValues,
          start_date: dateFrom,
          end_date: dateTo,
          selected_days: null,
          update_fields: ['stop_sell'],
        },
        { headers }
      );

      if (stopSell) {
        toast.success(`${data.saved} kayit icin satis durduruldu`);
      } else {
        toast.success(`${data.saved} kayit icin satis acildi`);
      }
      if (data.background_push) {
        toast.info('Exely güncellemesi arka planda gönderiliyor...');
      }

      loadActiveStopSales();
      // Delay grid refresh slightly so it doesn't block
      if (fetchGrid) setTimeout(() => fetchGrid(), 500);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Stop sale isleminde hata olustu');
    }
    setSaving(false);
  };

  const toggleOperatorStopSale = async (operatorId, operatorName) => {
    setOperatorLoading(prev => ({ ...prev, [operatorId]: true }));
    try {
      const currentStatus = operatorStatus[operatorId];
      const newStatus = !currentStatus;

      await axios.post(`${API}/api/rates/stop-sale/toggle`, {
        operator_id: operatorId,
        stop_sale: newStatus,
      }, { headers });

      setOperatorStatus(prev => ({ ...prev, [operatorId]: newStatus }));

      if (newStatus) {
        toast.success(`${operatorName} icin stop-sale aktif edildi`);
      } else {
        toast.success(`${operatorName} icin stop-sale kaldirildi`);
      }
    } catch {
      toast.error('Stop-sale durumu degistirilemedi');
    }
    setOperatorLoading(prev => ({ ...prev, [operatorId]: false }));
  };

  // Active stops come pre-grouped from the summary endpoint
  const groupedStops = {};
  for (const s of activeStopSales) {
    groupedStops[s.room_type_code] = { name: s.room_type_name, dates: new Set(s.dates) };
  }

  return (
    <div className="space-y-6" data-testid="stop-sale-panel">
      {/* Quick Stop Sale Controls */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left: Room Type Selection */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <BedDouble className="w-4 h-4" />
              Oda Tipi Sec
            </CardTitle>
            <CardDescription className="text-xs">
              Stop sale uygulanacak oda tiplerini secin
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <button
              onClick={selectAllRoomTypes}
              className="text-xs text-blue-600 hover:underline mb-2"
              data-testid="stop-sale-select-all"
            >
              {selectedRoomTypes.size === roomTypes.length ? 'Tumunu kaldir' : 'Tumunu sec'}
            </button>
            <div className="space-y-1.5 max-h-[280px] overflow-y-auto">
              {roomTypes.map(rt => (
                <label
                  key={rt.code}
                  className="flex items-center gap-2 cursor-pointer text-sm py-1"
                  data-testid={`stop-sale-room-${rt.code}`}
                >
                  <Checkbox
                    checked={selectedRoomTypes.has(rt.code)}
                    onCheckedChange={() => toggleRoomType(rt.code)}
                  />
                  <span className={selectedRoomTypes.has(rt.code) ? 'text-gray-900 font-medium' : 'text-gray-600'}>
                    {rt.name}
                  </span>
                </label>
              ))}
              {roomTypes.length === 0 && (
                <p className="text-xs text-gray-400 py-4 text-center">Oda tipi bulunamadi</p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Center: Date Range + Actions */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Calendar className="w-4 h-4" />
              Tarih Araligi & Islem
            </CardTitle>
            <CardDescription className="text-xs">
              Tarih araligini secin ve satisi durdur/ac
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs text-gray-500">Baslangic</Label>
                <Input
                  type="date"
                  value={dateFrom}
                  onChange={e => setDateFrom(e.target.value)}
                  className="mt-1 h-9"
                  data-testid="stop-sale-date-from"
                />
              </div>
              <div>
                <Label className="text-xs text-gray-500">Bitis</Label>
                <Input
                  type="date"
                  value={dateTo}
                  onChange={e => setDateTo(e.target.value)}
                  className="mt-1 h-9"
                  data-testid="stop-sale-date-to"
                />
              </div>
            </div>

            {/* Summary */}
            <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-600">
              <span className="font-medium">{selectedRoomTypes.size}</span> oda tipi secili
              {selectedRoomTypes.size > 0 && (
                <span className="text-gray-400 ml-1">
                  ({Array.from(selectedRoomTypes).map(c => roomTypes.find(rt => rt.code === c)?.name).filter(Boolean).join(', ')})
                </span>
              )}
            </div>

            {/* Action Buttons */}
            <div className="flex gap-3">
              <Button
                className="flex-1 bg-red-600 hover:bg-red-700 text-white"
                onClick={() => applyStopSale(true)}
                disabled={saving || selectedRoomTypes.size === 0}
                data-testid="apply-stop-sale-btn"
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <Lock className="w-4 h-4 mr-1.5" />}
                Satisi Durdur
              </Button>
              <Button
                className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white"
                onClick={() => applyStopSale(false)}
                disabled={saving || selectedRoomTypes.size === 0}
                data-testid="remove-stop-sale-btn"
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <Unlock className="w-4 h-4 mr-1.5" />}
                Satisi Ac
              </Button>
            </div>

            {/* Warning */}
            <div className="flex items-start gap-2 p-2.5 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-700">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>Stop sale islemleri Exely uzerinden tum kanallara anlik yansitilir.</span>
            </div>
          </CardContent>
        </Card>

        {/* Right: Operator-Level Stop Sales */}
        <Card className="border-orange-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Globe className="w-4 h-4 text-orange-600" />
              Kanal Bazli Stop Sale
            </CardTitle>
            <CardDescription className="text-xs">
              Belirli kanallar icin satisi tek tikla durdurun
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {defaultOperators.map(op => (
              <div
                key={op.id}
                className={`flex items-center justify-between p-2.5 rounded-lg border transition-colors ${
                  operatorStatus[op.id] ? 'bg-red-50 border-red-200' : 'bg-white border-gray-200 hover:bg-gray-50'
                }`}
                data-testid={`operator-stop-${op.id}`}
              >
                <div className="flex items-center gap-2">
                  {operatorStatus[op.id] ? (
                    <Ban className="w-4 h-4 text-red-500" />
                  ) : (
                    <CheckCircle className="w-4 h-4 text-emerald-500" />
                  )}
                  <span className="text-sm font-medium text-gray-800">{op.name}</span>
                </div>
                <Button
                  size="sm"
                  variant={operatorStatus[op.id] ? 'default' : 'destructive'}
                  className={operatorStatus[op.id] ? 'bg-emerald-600 hover:bg-emerald-700 h-7 text-xs' : 'h-7 text-xs'}
                  onClick={() => toggleOperatorStopSale(op.id, op.name)}
                  disabled={operatorLoading[op.id]}
                  data-testid={`operator-toggle-${op.id}`}
                >
                  {operatorLoading[op.id] ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : operatorStatus[op.id] ? (
                    'Satisi Ac'
                  ) : (
                    'Durdur'
                  )}
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Active Stop Sales Overview */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Ban className="w-4 h-4 text-red-500" />
                Aktif Stop Sale Durumu
              </CardTitle>
              <CardDescription className="text-xs">
                Oda bazinda aktif stop sale kayitlari
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={loadActiveStopSales}
              disabled={loadingActive}
              data-testid="refresh-stop-sales"
            >
              <RefreshCw className={`w-4 h-4 mr-1.5 ${loadingActive ? 'animate-spin' : ''}`} />
              Yenile
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loadingActive ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
            </div>
          ) : Object.keys(groupedStops).length === 0 ? (
            <div className="text-center py-8 text-gray-400">
              <CheckCircle className="w-10 h-10 mx-auto mb-2 text-emerald-300" />
              <p className="text-sm font-medium">Aktif stop sale yok</p>
              <p className="text-xs mt-1">Tum odalar satis icin acik</p>
            </div>
          ) : (
            <div className="space-y-3" data-testid="active-stop-sales-list">
              {Object.entries(groupedStops).map(([code, info]) => {
                const dateList = Array.from(info.dates).sort();
                return (
                  <div key={code} className="flex items-start gap-3 p-3 bg-red-50 border border-red-100 rounded-lg">
                    <Lock className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-sm text-gray-800">{info.name}</div>
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {dateList.slice(0, 14).map(d => (
                          <Badge key={d} variant="outline" className="text-[10px] bg-white border-red-200 text-red-600">
                            {new Date(d + 'T00:00:00').toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' })}
                          </Badge>
                        ))}
                        {dateList.length > 14 && (
                          <Badge variant="outline" className="text-[10px] bg-white border-gray-200">
                            +{dateList.length - 14} gun daha
                          </Badge>
                        )}
                      </div>
                    </div>
                    <Badge className="bg-red-100 text-red-700 border-0 text-xs">
                      {dateList.length} gun
                    </Badge>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};
