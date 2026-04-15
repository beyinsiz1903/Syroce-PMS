import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  Building2, Plus, RefreshCw, Calendar, BedDouble, Percent, AlertTriangle
} from 'lucide-react';

const ROOM_TYPES = [
  { value: 'standard', label: 'Standart' },
  { value: 'superior', label: 'Superior' },
  { value: 'deluxe', label: 'Deluxe' },
  { value: 'suite', label: 'Süit' },
  { value: 'family', label: 'Aile' },
  { value: 'king', label: 'King' },
];

const AllotmentGrid = () => {
  const [contracts, setContracts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showDialog, setShowDialog] = useState(false);
  const [formData, setFormData] = useState({
    tour_operator: '',
    room_type: 'standard',
    allocated_rooms: '',
    start_date: '',
    end_date: '',
    rate: '',
    release_days: '7'
  });

  const loadContracts = useCallback(async () => {
    setLoading(true);
    try {
      const response = await axios.get('/pms/allotment-contracts');
      setContracts(response.data?.contracts || response.data || []);
    } catch {
      toast.error('Kontenjan sözleşmeleri yüklenemedi');
    }
    setLoading(false);
  }, []);

  useEffect(() => { loadContracts(); }, [loadContracts]);

  const createContract = async () => {
    if (!formData.tour_operator.trim()) {
      toast.error('Tur operatörü adı gerekli');
      return;
    }
    if (!formData.start_date || !formData.end_date) {
      toast.error('Başlangıç ve bitiş tarihi gerekli');
      return;
    }
    if (new Date(formData.end_date) <= new Date(formData.start_date)) {
      toast.error('Bitiş tarihi başlangıçtan sonra olmalı');
      return;
    }
    if (!formData.allocated_rooms || parseInt(formData.allocated_rooms) <= 0) {
      toast.error('Oda sayısı 0\'dan büyük olmalı');
      return;
    }
    try {
      await axios.post('/pms/allotment-contracts', {
        ...formData,
        allocated_rooms: parseInt(formData.allocated_rooms) || 0,
        rate: parseFloat(formData.rate) || 0,
        release_days: parseInt(formData.release_days) || 7,
      });
      toast.success('Sözleşme oluşturuldu');
      loadContracts();
      setShowDialog(false);
      setFormData({ tour_operator: '', room_type: 'standard', allocated_rooms: '', start_date: '', end_date: '', rate: '', release_days: '7' });
    } catch {
      toast.error('Sözleşme oluşturulamadı');
    }
  };

  const releaseRooms = async (contractId) => {
    try {
      await axios.post(`/pms/allotment-contracts/${contractId}/release`);
      toast.success('Boş odalar serbest bırakıldı');
      loadContracts();
    } catch {
      toast.error('Odalar serbest bırakılamadı');
    }
  };

  const getRoomTypeLabel = (val) => ROOM_TYPES.find(r => r.value === val)?.label || val;

  const fmt = (v) => (v || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const totalAllocated = contracts.reduce((s, c) => s + (c.allocated_rooms || 0), 0);
  const totalUsed = contracts.reduce((s, c) => s + (c.used_rooms || 0), 0);
  const totalAvailable = totalAllocated - totalUsed;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-2xl font-bold flex items-center gap-2">
            <Building2 className="w-6 h-6" /> Kontenjan Yönetimi
          </h3>
          <p className="text-gray-600 text-sm">Tur operatörü kontenjan sözleşmeleri</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={loadContracts} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> Yenile
          </Button>
          <Button onClick={() => setShowDialog(true)}>
            <Plus className="w-4 h-4 mr-2" /> Yeni Sözleşme
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Card className="bg-purple-50 border-purple-200">
          <CardContent className="p-4 text-center">
            <Building2 className="w-5 h-5 mx-auto mb-1 text-purple-600" />
            <p className="text-xs text-purple-600">Sözleşme Sayısı</p>
            <p className="text-2xl font-bold text-purple-700">{contracts.length}</p>
          </CardContent>
        </Card>
        <Card className="bg-blue-50 border-blue-200">
          <CardContent className="p-4 text-center">
            <BedDouble className="w-5 h-5 mx-auto mb-1 text-blue-600" />
            <p className="text-xs text-blue-600">Toplam Kontenjan</p>
            <p className="text-2xl font-bold text-blue-700">{totalAllocated}</p>
          </CardContent>
        </Card>
        <Card className="bg-amber-50 border-amber-200">
          <CardContent className="p-4 text-center">
            <Percent className="w-5 h-5 mx-auto mb-1 text-amber-600" />
            <p className="text-xs text-amber-600">Kullanılan</p>
            <p className="text-2xl font-bold text-amber-700">{totalUsed}</p>
          </CardContent>
        </Card>
        <Card className="bg-green-50 border-green-200">
          <CardContent className="p-4 text-center">
            <Calendar className="w-5 h-5 mx-auto mb-1 text-green-600" />
            <p className="text-xs text-green-600">Müsait</p>
            <p className="text-2xl font-bold text-green-700">{totalAvailable}</p>
          </CardContent>
        </Card>
      </div>

      {contracts.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-gray-500">
            <Building2 className="w-12 h-12 mx-auto mb-3 text-gray-300" />
            <p className="font-medium">Henüz kontenjan sözleşmesi yok</p>
            <p className="text-sm mt-1">"Yeni Sözleşme" butonuyla tur operatörü kontenjanyarını tanımlayın</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {contracts.map((contract) => {
            const available = (contract.allocated_rooms || 0) - (contract.used_rooms || 0);
            const usagePct = contract.allocated_rooms > 0 ? Math.round((contract.used_rooms || 0) / contract.allocated_rooms * 100) : 0;
            const isExpiring = contract.end_date && new Date(contract.end_date) < new Date(Date.now() + 7 * 86400000);
            return (
              <Card key={contract.id} className="hover:shadow-lg transition">
                <CardHeader className="pb-2">
                  <div className="flex justify-between items-start">
                    <div className="flex items-center gap-2">
                      <Building2 className="w-5 h-5 text-purple-500" />
                      <CardTitle className="text-lg">{contract.tour_operator}</CardTitle>
                    </div>
                    {isExpiring && (
                      <Badge className="bg-red-100 text-red-700">
                        <AlertTriangle className="w-3 h-3 mr-1" /> Süresi Doluyor
                      </Badge>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-600">Oda Tipi:</span>
                      <span className="font-semibold">{getRoomTypeLabel(contract.room_type)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Kontenjan:</span>
                      <span className="font-semibold">{contract.allocated_rooms} oda</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Kullanılan:</span>
                      <span className="font-semibold">{contract.used_rooms || 0} oda</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Müsait:</span>
                      <span className={`font-semibold ${available > 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {available} oda
                      </span>
                    </div>
                    <div className="bg-gray-100 rounded-full h-2 overflow-hidden">
                      <div className="bg-purple-500 h-full rounded-full" style={{ width: `${Math.min(usagePct, 100)}%` }} />
                    </div>
                    <p className="text-xs text-gray-400 text-center">Kullanım: %{usagePct}</p>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Fiyat:</span>
                      <span className="font-semibold">{fmt(contract.rate)} ₺/gece</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Dönem:</span>
                      <span className="text-xs">
                        {contract.start_date ? new Date(contract.start_date).toLocaleDateString('tr-TR') : '-'} - {contract.end_date ? new Date(contract.end_date).toLocaleDateString('tr-TR') : '-'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Release:</span>
                      <span className="font-semibold">{contract.release_days} gün</span>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-full mt-2"
                      onClick={() => releaseRooms(contract.id)}
                      disabled={available === 0}
                    >
                      Boş Odaları Serbest Bırak
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Yeni Kontenjan Sözleşmesi</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Tur Operatörü *</Label>
              <Input
                value={formData.tour_operator}
                onChange={(e) => setFormData({ ...formData, tour_operator: e.target.value })}
                placeholder="Tur operatörü adı"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Oda Tipi</Label>
                <Select value={formData.room_type} onValueChange={(v) => setFormData({ ...formData, room_type: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ROOM_TYPES.map(r => (
                      <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Oda Sayısı *</Label>
                <Input
                  type="number"
                  min="1"
                  value={formData.allocated_rooms}
                  onChange={(e) => setFormData({ ...formData, allocated_rooms: e.target.value })}
                  placeholder="10"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Başlangıç Tarihi *</Label>
                <Input
                  type="date"
                  value={formData.start_date}
                  onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
                />
              </div>
              <div>
                <Label>Bitiş Tarihi *</Label>
                <Input
                  type="date"
                  value={formData.end_date}
                  onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Gecelik Fiyat (₺)</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={formData.rate}
                  onChange={(e) => setFormData({ ...formData, rate: e.target.value })}
                  placeholder="500.00"
                />
              </div>
              <div>
                <Label>Release Süresi (gün)</Label>
                <Input
                  type="number"
                  min="0"
                  value={formData.release_days}
                  onChange={(e) => setFormData({ ...formData, release_days: e.target.value })}
                />
              </div>
            </div>
            <Button onClick={createContract} className="w-full">Sözleşme Oluştur</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AllotmentGrid;
