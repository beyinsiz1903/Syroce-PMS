import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
  DollarSign, Calendar, Save, Loader2, ChevronLeft, ChevronRight,
  BedDouble, Lock, Unlock, ArrowUpRight
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

const RateManager = ({ user, tenant, onLogout }) => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [grid, setGrid] = useState([]);
  const [roomTypes, setRoomTypes] = useState([]);
  const [ratePlans, setRatePlans] = useState([]);
  const [selectedRoomType, setSelectedRoomType] = useState('all');
  const [selectedRatePlan, setSelectedRatePlan] = useState('all');
  const [editDialog, setEditDialog] = useState(null);
  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    return d.toISOString().slice(0, 10);
  });
  const [endDate, setEndDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 13);
    return d.toISOString().slice(0, 10);
  });

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

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
    if (selectedRoomType !== 'all' && row.room_type_code !== selectedRoomType) return false;
    if (selectedRatePlan !== 'all' && row.rate_plan_code !== selectedRatePlan) return false;
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

  const openEdit = (row, dateIdx) => {
    const cell = row.dates[dateIdx];
    setEditDialog({
      room_type_code: row.room_type_code,
      room_type_name: row.room_type_name,
      rate_plan_code: row.rate_plan_code,
      rate_plan_name: row.rate_plan_name,
      date: cell.date,
      rate: cell.rate ?? '',
      availability: cell.availability ?? '',
      min_stay: cell.min_stay ?? 1,
      stop_sell: cell.stop_sell ?? false,
      applyRange: false,
      rangeEnd: cell.date,
    });
  };

  const handleSave = async () => {
    if (!editDialog) return;
    setSaving(true);
    try {
      const update = {
        room_type_code: editDialog.room_type_code,
        rate_plan_code: editDialog.rate_plan_code,
        start_date: editDialog.date,
        end_date: editDialog.applyRange ? editDialog.rangeEnd : editDialog.date,
        rate: editDialog.rate !== '' ? parseFloat(editDialog.rate) : null,
        availability: editDialog.availability !== '' ? parseInt(editDialog.availability) : null,
        min_stay: editDialog.min_stay ? parseInt(editDialog.min_stay) : null,
        stop_sell: editDialog.stop_sell,
      };

      const { data } = await axios.post(
        `${API}/api/channel-manager/rate-manager/update`,
        { updates: [update] },
        { headers }
      );

      if (data.all_pushed) {
        toast.success('Fiyat güncellendi ve Exely\'ye gönderildi');
      } else {
        const failed = data.push_results?.filter(r => !r.success) || [];
        if (failed.length > 0) {
          toast.warning(`Kaydedildi ama Exely push hatası: ${failed[0].error}`);
        } else {
          toast.success('Kaydedildi');
        }
      }
      setEditDialog(null);
      fetchGrid();
    } catch (e) {
      toast.error('Kaydetme hatası');
    }
    setSaving(false);
  };

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
          <Badge className="bg-green-500 text-white">
            <ArrowUpRight className="w-3 h-3 mr-1" />
            Exely Push Aktif
          </Badge>
        </div>

        {/* Filters & Date Navigation */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3 flex-wrap">
              <Select value={selectedRoomType} onValueChange={setSelectedRoomType}>
                <SelectTrigger data-testid="room-type-filter" className="w-[180px]">
                  <SelectValue placeholder="Oda Tipi" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Tüm Oda Tipleri</SelectItem>
                  {roomTypes.map(rt => (
                    <SelectItem key={rt.code} value={rt.code}>{rt.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select value={selectedRatePlan} onValueChange={setSelectedRatePlan}>
                <SelectTrigger data-testid="rate-plan-filter" className="w-[200px]">
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
                <Button
                  variant="outline" size="icon"
                  onClick={() => shiftDates(-7)}
                  data-testid="prev-week-btn"
                >
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
                <Button
                  variant="outline" size="icon"
                  onClick={() => shiftDates(7)}
                  data-testid="next-week-btn"
                >
                  <ChevronRight className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Rate Grid */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
          </div>
        ) : (
          <Card className="overflow-hidden">
            <div className="overflow-x-auto">
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
                      {row.dates.map((cell, di) => {
                        const f = formatDate(cell.date);
                        return (
                          <td
                            key={cell.date}
                            className={`px-1 py-1 text-center cursor-pointer transition-colors hover:bg-blue-50 ${
                              f.isWeekend ? 'bg-amber-50/40' : ''
                            } ${cell.stop_sell ? 'bg-red-50' : ''}`}
                            onClick={() => openEdit(row, di)}
                            data-testid={`cell-${row.room_type_code}-${row.rate_plan_code}-${cell.date}`}
                          >
                            <div className="space-y-0.5">
                              {cell.rate != null ? (
                                <div className="text-xs font-semibold text-blue-700">
                                  ${cell.rate}
                                </div>
                              ) : (
                                <div className="text-xs text-gray-300">-</div>
                              )}
                              <div className="text-[10px] text-gray-400">
                                {cell.availability != null ? `${cell.availability} oda` : ''}
                              </div>
                              {cell.min_stay > 1 && (
                                <div className="text-[10px] text-amber-600">
                                  min {cell.min_stay}g
                                </div>
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
          </Card>
        )}

        {/* Edit Dialog */}
        <Dialog open={!!editDialog} onOpenChange={(open) => !open && setEditDialog(null)}>
          <DialogContent className="max-w-md" data-testid="edit-rate-dialog">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <DollarSign className="w-5 h-5 text-blue-600" />
                Fiyat ve Müsaitlik Düzenle
              </DialogTitle>
              <p className="text-xs text-gray-500">Seçili hücrenin değerlerini güncelleyin</p>
            </DialogHeader>
            {editDialog && (
              <div className="space-y-4">
                <div className="flex items-center gap-2 p-2 rounded bg-gray-50 border">
                  <BedDouble className="w-4 h-4 text-gray-400" />
                  <span className="text-sm text-gray-700 font-medium">{editDialog.room_type_name}</span>
                  <span className="text-xs text-gray-400">/ {editDialog.rate_plan_name}</span>
                </div>

                <div className="text-sm text-gray-500">
                  Tarih: <span className="text-gray-800 font-medium">{editDialog.date}</span>
                </div>

                <div className="flex items-center gap-2">
                  <Switch
                    checked={editDialog.applyRange}
                    onCheckedChange={(v) => setEditDialog(prev => ({ ...prev, applyRange: v }))}
                    data-testid="apply-range-switch"
                  />
                  <Label className="text-sm text-gray-600">Tarih aralığına uygula</Label>
                </div>
                {editDialog.applyRange && (
                  <div>
                    <Label className="text-xs text-gray-500">Bitiş Tarihi</Label>
                    <Input
                      type="date"
                      value={editDialog.rangeEnd}
                      onChange={(e) => setEditDialog(prev => ({ ...prev, rangeEnd: e.target.value }))}
                      data-testid="range-end-input"
                    />
                  </div>
                )}

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label className="text-xs text-gray-500">Fiyat (USD)</Label>
                    <Input
                      type="number"
                      step="0.01"
                      placeholder="Fiyat"
                      value={editDialog.rate}
                      onChange={(e) => setEditDialog(prev => ({ ...prev, rate: e.target.value }))}
                      data-testid="rate-input"
                    />
                  </div>
                  <div>
                    <Label className="text-xs text-gray-500">Müsait Oda</Label>
                    <Input
                      type="number"
                      min="0"
                      placeholder="Adet"
                      value={editDialog.availability}
                      onChange={(e) => setEditDialog(prev => ({ ...prev, availability: e.target.value }))}
                      data-testid="availability-input"
                    />
                  </div>
                  <div>
                    <Label className="text-xs text-gray-500">Min. Konaklama (gece)</Label>
                    <Input
                      type="number"
                      min="1"
                      placeholder="1"
                      value={editDialog.min_stay}
                      onChange={(e) => setEditDialog(prev => ({ ...prev, min_stay: e.target.value }))}
                      data-testid="min-stay-input"
                    />
                  </div>
                  <div className="flex items-end pb-1">
                    <div className="flex items-center gap-2">
                      <Switch
                        checked={editDialog.stop_sell}
                        onCheckedChange={(v) => setEditDialog(prev => ({ ...prev, stop_sell: v }))}
                        data-testid="stop-sell-switch"
                      />
                      <Label className="text-sm text-gray-600 flex items-center gap-1">
                        {editDialog.stop_sell ? <Lock className="w-3 h-3 text-red-500" /> : <Unlock className="w-3 h-3 text-green-500" />}
                        Satış Durdur
                      </Label>
                    </div>
                  </div>
                </div>
              </div>
            )}
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setEditDialog(null)}
                data-testid="cancel-edit-btn"
              >
                İptal
              </Button>
              <Button
                onClick={handleSave}
                disabled={saving}
                className="bg-blue-600 hover:bg-blue-700"
                data-testid="save-rate-btn"
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
                Kaydet ve Gönder
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
};

export default RateManager;
