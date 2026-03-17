import { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  DollarSign, Calendar, Save, Loader2, ChevronLeft, ChevronRight,
  BedDouble, Lock, Unlock, ArrowUpRight, RefreshCw, Eye
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

const RateManager = ({ user, tenant, onLogout }) => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [grid, setGrid] = useState([]);
  const [roomTypes, setRoomTypes] = useState([]);
  const [ratePlans, setRatePlans] = useState([]);

  // Form state (like Channel Manager Rate & Availability tab)
  const [formRoomType, setFormRoomType] = useState('');
  const [formRatePlan, setFormRatePlan] = useState('');
  const [formDateFrom, setFormDateFrom] = useState('');
  const [formDateTo, setFormDateTo] = useState('');
  const [baseRate, setBaseRate] = useState('');
  const [discountPct, setDiscountPct] = useState('');
  const [availableRooms, setAvailableRooms] = useState('');
  const [stopSell, setStopSell] = useState('open');
  const [minStay, setMinStay] = useState('');
  const [maxStay, setMaxStay] = useState('');

  // Grid filters
  const [gridRoomType, setGridRoomType] = useState('all');
  const [gridRatePlan, setGridRatePlan] = useState('all');
  const [startDate, setStartDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [endDate, setEndDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 13);
    return d.toISOString().slice(0, 10);
  });

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const finalRate = useMemo(() => {
    const base = parseFloat(baseRate);
    const disc = parseFloat(discountPct);
    if (Number.isNaN(base)) return '';
    const pct = Number.isNaN(disc) ? 0 : disc;
    const final = base * (1 - pct / 100);
    return final > 0 ? final.toFixed(2) : '';
  }, [baseRate, discountPct]);

  const fetchGrid = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(
        `${API}/api/channel-manager/rate-manager/grid?start_date=${startDate}&end_date=${endDate}`,
        { headers }
      );
      setGrid(data.grid || []);
      setRoomTypes(data.room_types || []);
      setRatePlans(data.rate_plans || []);
    } catch (e) {
      toast.error('Veriler yüklenemedi');
    }
    setLoading(false);
  }, [startDate, endDate]);

  useEffect(() => { fetchGrid(); }, [fetchGrid]);

  const filteredGrid = grid.filter(row => {
    if (gridRoomType !== 'all' && row.room_type_code !== gridRoomType) return false;
    if (gridRatePlan !== 'all' && row.rate_plan_code !== gridRatePlan) return false;
    return true;
  });

  const shiftDates = (days) => {
    const s = new Date(startDate);
    const e = new Date(endDate);
    s.setDate(s.getDate() + days);
    e.setDate(e.getDate() + days);
    setStartDate(s.toISOString().slice(0, 10));
    setEndDate(e.toISOString().slice(0, 10));
  };

  const dates = [];
  if (filteredGrid.length > 0 && filteredGrid[0].dates) {
    filteredGrid[0].dates.forEach(d => dates.push(d.date));
  }

  const formatDate = (ds) => {
    const d = new Date(ds + 'T00:00:00');
    const days = ['Paz', 'Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt'];
    return {
      day: d.getDate(),
      month: d.toLocaleDateString('tr-TR', { month: 'short' }),
      weekday: days[d.getDay()],
      isWeekend: d.getDay() === 0 || d.getDay() === 6,
    };
  };

  const handlePreview = () => {
    const rate = finalRate || baseRate;
    toast.info(
      `Önizleme: ${formRoomType || 'Oda tipi seçilmedi'} için ${formDateFrom || '?'} - ${formDateTo || '?'} arasında ${rate ? rate + ' USD' : 'Fiyat girilmedi'}`
    );
  };

  const handleUpdateRates = async () => {
    if (!formRoomType || !formRatePlan) {
      toast.error('Lütfen oda tipi ve fiyat planı seçin');
      return;
    }
    if (!formDateFrom || !formDateTo) {
      toast.error('Lütfen tarih aralığı seçin');
      return;
    }

    setSaving(true);
    try {
      const rate = finalRate ? parseFloat(finalRate) : (baseRate ? parseFloat(baseRate) : null);
      const update = {
        room_type_code: formRoomType,
        rate_plan_code: formRatePlan,
        start_date: formDateFrom,
        end_date: formDateTo,
        rate: rate,
        availability: availableRooms ? parseInt(availableRooms) : null,
        min_stay: minStay ? parseInt(minStay) : null,
        stop_sell: stopSell === 'closed',
      };

      const { data } = await axios.post(
        `${API}/api/channel-manager/rate-manager/update`,
        { updates: [update] },
        { headers }
      );

      if (data.all_pushed) {
        toast.success('Güncelleme başarılı! Exely\'ye gönderildi.');
      } else {
        const failed = data.push_results?.filter(r => !r.success) || [];
        if (failed.length > 0) {
          toast.warning(`Kaydedildi ama Exely push hatası: ${failed[0].error}`);
        } else {
          toast.success('Kaydedildi');
        }
      }
      fetchGrid();
    } catch (e) {
      toast.error('Güncelleme hatası');
    }
    setSaving(false);
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="rate_manager">
      <div className="p-6 space-y-6" data-testid="rate-manager-page">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Space Grotesk' }}>
              Fiyat ve Müsaitlik Yönetimi
            </h1>
            <p className="text-gray-600">
              Oda fiyatlarını, müsaitliği ve konaklama kısıtlamalarını yönetin
            </p>
          </div>
          <Badge className="bg-green-500 text-white" data-testid="exely-push-badge">
            <ArrowUpRight className="w-3 h-3 mr-1" />
            Exely Push Aktif
          </Badge>
        </div>

        {/* ─── FORM SECTION (like Channel Manager Rate & Availability tab) ─── */}
        <Card>
          <CardHeader>
            <CardTitle>Fiyat ve Müsaitlik Güncelleme</CardTitle>
            <CardDescription>
              Oda tipi, fiyat planı ve tarih aralığı seçerek toplu güncelleme yapın
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Room Type + Rate Plan + Date Range */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <Label>Oda Tipi</Label>
                <select
                  className="w-full border rounded-md p-2 mt-1"
                  value={formRoomType}
                  onChange={(e) => setFormRoomType(e.target.value)}
                  data-testid="form-room-type"
                >
                  <option value="">Bir oda tipi seçin</option>
                  {roomTypes.map((rt) => (
                    <option key={rt.code} value={rt.code}>{rt.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label>Fiyat Planı</Label>
                <select
                  className="w-full border rounded-md p-2 mt-1"
                  value={formRatePlan}
                  onChange={(e) => setFormRatePlan(e.target.value)}
                  data-testid="form-rate-plan"
                >
                  <option value="">Bir fiyat planı seçin</option>
                  {ratePlans.map((rp) => (
                    <option key={rp.code} value={rp.code}>{rp.name}</option>
                  ))}
                </select>
              </div>
              <div className="md:col-span-2">
                <Label>Tarih Aralığı</Label>
                <div className="flex space-x-2 mt-1">
                  <Input
                    type="date"
                    value={formDateFrom}
                    onChange={(e) => setFormDateFrom(e.target.value)}
                    data-testid="form-date-from"
                  />
                  <Input
                    type="date"
                    value={formDateTo}
                    onChange={(e) => setFormDateTo(e.target.value)}
                    data-testid="form-date-to"
                  />
                </div>
              </div>
            </div>

            {/* Rate Settings */}
            <Card className="border-blue-200">
              <CardHeader className="pb-3">
                <CardTitle className="text-lg flex items-center gap-2">
                  <DollarSign className="w-4 h-4 text-blue-600" />
                  Fiyat Ayarları
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <Label>Baz Fiyat (USD)</Label>
                    <Input
                      type="number"
                      step="0.01"
                      placeholder="0.00"
                      className="mt-1"
                      value={baseRate}
                      onChange={(e) => setBaseRate(e.target.value)}
                      data-testid="form-base-rate"
                    />
                  </div>
                  <div>
                    <Label>İndirim (%)</Label>
                    <Input
                      type="number"
                      placeholder="0"
                      min="0"
                      max="100"
                      className="mt-1"
                      value={discountPct}
                      onChange={(e) => setDiscountPct(e.target.value)}
                      data-testid="form-discount"
                    />
                  </div>
                  <div>
                    <Label>Son Fiyat (USD)</Label>
                    <Input
                      type="number"
                      placeholder="0.00"
                      className="mt-1"
                      value={finalRate}
                      disabled
                      data-testid="form-final-rate"
                    />
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Availability Settings */}
            <Card className="border-green-200">
              <CardHeader className="pb-3">
                <CardTitle className="text-lg flex items-center gap-2">
                  <BedDouble className="w-4 h-4 text-green-600" />
                  Müsaitlik Ayarları
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label>Müsait Oda Sayısı</Label>
                    <Input
                      type="number"
                      placeholder="0"
                      min="0"
                      className="mt-1"
                      value={availableRooms}
                      onChange={(e) => setAvailableRooms(e.target.value)}
                      data-testid="form-available-rooms"
                    />
                  </div>
                  <div>
                    <Label>Satış Durumu</Label>
                    <select
                      className="w-full border rounded-md p-2 mt-1"
                      value={stopSell}
                      onChange={(e) => setStopSell(e.target.value)}
                      data-testid="form-stop-sell"
                    >
                      <option value="open">Açık (Satışta)</option>
                      <option value="closed">Kapalı (Satış Durdur)</option>
                    </select>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Restrictions */}
            <Card className="border-purple-200">
              <CardHeader className="pb-3">
                <CardTitle className="text-lg flex items-center gap-2">
                  <Lock className="w-4 h-4 text-purple-600" />
                  Kısıtlamalar
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label>Minimum Konaklama (gece)</Label>
                    <Input
                      type="number"
                      placeholder="1"
                      min="1"
                      className="mt-1"
                      value={minStay}
                      onChange={(e) => setMinStay(e.target.value)}
                      data-testid="form-min-stay"
                    />
                  </div>
                  <div>
                    <Label>Maksimum Konaklama (gece)</Label>
                    <Input
                      type="number"
                      placeholder="30"
                      min="1"
                      className="mt-1"
                      value={maxStay}
                      onChange={(e) => setMaxStay(e.target.value)}
                      data-testid="form-max-stay"
                    />
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Action Buttons */}
            <div className="flex justify-end space-x-3 pt-4">
              <Button
                variant="outline"
                type="button"
                onClick={handlePreview}
                data-testid="preview-btn"
              >
                <Eye className="w-4 h-4 mr-2" />
                Önizleme
              </Button>
              <Button
                type="button"
                className="bg-blue-600 hover:bg-blue-700"
                onClick={handleUpdateRates}
                disabled={saving}
                data-testid="update-exely-btn"
              >
                {saving ? (
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                ) : (
                  <RefreshCw className="w-4 h-4 mr-2" />
                )}
                Güncelle ve Exely'ye Gönder
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* ─── GRID SECTION (Current state view) ─── */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg">Mevcut Fiyat Takvimi</CardTitle>
                <CardDescription>
                  Tarih bazında mevcut fiyat, müsaitlik ve kısıtlamaları görüntüleyin
                </CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={fetchGrid} disabled={loading}>
                <RefreshCw className="w-4 h-4 mr-2" /> Yenile
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {/* Grid Filters & Date Navigation */}
            <div className="flex items-center gap-3 flex-wrap mb-4">
              <Select value={gridRoomType} onValueChange={setGridRoomType}>
                <SelectTrigger data-testid="grid-room-type-filter" className="w-[180px]">
                  <SelectValue placeholder="Oda Tipi" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Tüm Oda Tipleri</SelectItem>
                  {roomTypes.map(rt => (
                    <SelectItem key={rt.code} value={rt.code}>{rt.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select value={gridRatePlan} onValueChange={setGridRatePlan}>
                <SelectTrigger data-testid="grid-rate-plan-filter" className="w-[200px]">
                  <SelectValue placeholder="Fiyat Planı" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Tüm Fiyat Planları</SelectItem>
                  {ratePlans.map(rp => (
                    <SelectItem key={rp.code} value={rp.code}>{rp.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <div className="flex items-center gap-1 ml-auto">
                <Button variant="outline" size="icon" onClick={() => shiftDates(-7)} data-testid="prev-week-btn">
                  <ChevronLeft className="w-4 h-4" />
                </Button>
                <Button
                  variant="outline" size="sm"
                  onClick={() => {
                    const today = new Date().toISOString().slice(0, 10);
                    const end = new Date();
                    end.setDate(end.getDate() + 13);
                    setStartDate(today);
                    setEndDate(end.toISOString().slice(0, 10));
                  }}
                  className="text-xs"
                  data-testid="today-btn"
                >
                  <Calendar className="w-3 h-3 mr-1" />
                  Bugün
                </Button>
                <Button variant="outline" size="icon" onClick={() => shiftDates(7)} data-testid="next-week-btn">
                  <ChevronRight className="w-4 h-4" />
                </Button>
              </div>
            </div>

            {/* Grid Table */}
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
              </div>
            ) : (
              <div className="overflow-x-auto border rounded-lg">
                <table className="w-full text-sm" data-testid="rate-grid-table">
                  <thead>
                    <tr className="border-b bg-gray-50">
                      <th className="sticky left-0 z-10 bg-gray-50 px-3 py-2 text-left text-xs text-gray-500 font-medium min-w-[200px]">
                        Oda / Plan
                      </th>
                      {dates.map(d => {
                        const f = formatDate(d);
                        return (
                          <th
                            key={d}
                            className={`px-2 py-2 text-center text-xs font-medium min-w-[80px] ${
                              f.isWeekend ? 'bg-amber-50 text-amber-700' : 'text-gray-500'
                            }`}
                          >
                            <div>{f.weekday}</div>
                            <div className="text-base font-bold text-gray-800">{f.day}</div>
                            <div className="text-[10px] opacity-70">{f.month}</div>
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredGrid.map((row) => (
                      <tr
                        key={`${row.room_type_code}-${row.rate_plan_code}`}
                        className="border-b hover:bg-gray-50/50"
                      >
                        <td className="sticky left-0 z-10 bg-white px-3 py-2 border-r">
                          <div className="flex items-center gap-2">
                            <BedDouble className="w-4 h-4 text-gray-400 flex-shrink-0" />
                            <div>
                              <div className="font-medium text-gray-800 text-xs">{row.room_type_name}</div>
                              <div className="text-[10px] text-gray-400 truncate max-w-[150px]">{row.rate_plan_name}</div>
                            </div>
                          </div>
                        </td>
                        {row.dates.map((cell) => {
                          const f = formatDate(cell.date);
                          return (
                            <td
                              key={cell.date}
                              className={`px-1 py-1 text-center ${
                                f.isWeekend ? 'bg-amber-50/40' : ''
                              } ${cell.stop_sell ? 'bg-red-50' : ''}`}
                              data-testid={`cell-${row.room_type_code}-${row.rate_plan_code}-${cell.date}`}
                            >
                              <div className="space-y-0.5">
                                {cell.rate != null ? (
                                  <div className="text-xs font-semibold text-blue-700">${cell.rate}</div>
                                ) : (
                                  <div className="text-xs text-gray-300">-</div>
                                )}
                                <div className="text-[10px] text-gray-400">
                                  {cell.availability != null ? (
                                    <span className={cell.availability === 0 ? 'text-red-500 font-semibold' : cell.availability <= 2 ? 'text-amber-500 font-medium' : ''}>
                                      {cell.availability} oda
                                    </span>
                                  ) : ''}
                                  {cell.sold > 0 && (
                                    <span className="text-blue-500 ml-0.5">({cell.sold} satıldı)</span>
                                  )}
                                </div>
                                {cell.min_stay > 1 && (
                                  <div className="text-[10px] text-amber-600">min {cell.min_stay}g</div>
                                )}
                                {cell.stop_sell && (
                                  <Lock className="w-3 h-3 text-red-400 mx-auto" />
                                )}
                              </div>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                    {filteredGrid.length === 0 && (
                      <tr>
                        <td colSpan={dates.length + 1} className="py-12 text-center text-gray-400">
                          Veri bulunamadı
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
};

export default RateManager;
