import { useState, useEffect, useCallback } from 'react';
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
import {
  Building2, Plus, RefreshCw, Calendar, BedDouble, Percent, AlertTriangle
} from 'lucide-react';

const ROOM_TYPE_KEYS = ['standard', 'superior', 'deluxe', 'suite', 'family', 'king'];

const AllotmentGrid = () => {
  const { t, i18n } = useTranslation();
  const ta = useCallback((k) => t(`pmsComponents.allotment.${k}`), [t]);
  const cur = t('pmsComponents.common.currency');

  const [contracts, setContracts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showDialog, setShowDialog] = useState(false);
  const [formData, setFormData] = useState({
    tour_operator: '', room_type: 'standard', allocated_rooms: '',
    start_date: '', end_date: '', rate: '', release_days: '7'
  });

  const loadContracts = useCallback(async () => {
    setLoading(true);
    try {
      const response = await axios.get('/pms/allotment-contracts');
      setContracts(response.data?.contracts || response.data || []);
    } catch {
      toast.error(ta('loadError'));
    }
    setLoading(false);
  }, [ta]);

  useEffect(() => { loadContracts(); }, [loadContracts]);

  const createContract = async () => {
    if (!formData.tour_operator.trim()) { toast.error(ta('operatorRequired')); return; }
    if (!formData.start_date || !formData.end_date) { toast.error(ta('datesRequired')); return; }
    if (new Date(formData.end_date) <= new Date(formData.start_date)) { toast.error(ta('endAfterStart')); return; }
    if (!formData.allocated_rooms || parseInt(formData.allocated_rooms) <= 0) { toast.error(ta('roomCountRequired')); return; }
    try {
      await axios.post('/pms/allotment-contracts', {
        ...formData,
        allocated_rooms: parseInt(formData.allocated_rooms) || 0,
        rate: parseFloat(formData.rate) || 0,
        release_days: parseInt(formData.release_days) || 7,
      });
      toast.success(ta('contractCreated'));
      loadContracts();
      setShowDialog(false);
      setFormData({ tour_operator: '', room_type: 'standard', allocated_rooms: '', start_date: '', end_date: '', rate: '', release_days: '7' });
    } catch {
      toast.error(ta('createError'));
    }
  };

  const releaseRooms = async (contractId) => {
    try {
      await axios.post(`/pms/allotment-contracts/${contractId}/release`);
      toast.success(ta('roomsReleased'));
      loadContracts();
    } catch {
      toast.error(ta('releaseError'));
    }
  };

  const fmt = (v) => (v || 0).toLocaleString(i18n.language, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const totalAllocated = contracts.reduce((s, c) => s + (c.allocated_rooms || 0), 0);
  const totalUsed = contracts.reduce((s, c) => s + (c.used_rooms || 0), 0);
  const totalAvailable = totalAllocated - totalUsed;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-2xl font-bold flex items-center gap-2">
            <Building2 className="w-6 h-6" /> {ta('title')}
          </h3>
          <p className="text-gray-600 text-sm">{ta('subtitle')}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={loadContracts} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> {ta('refresh')}
          </Button>
          <Button onClick={() => setShowDialog(true)}>
            <Plus className="w-4 h-4 mr-2" /> {ta('newContract')}
          </Button>
        </div>
      </div>

      <div className="rounded-lg border border-blue-300 bg-blue-50 p-3 flex items-start gap-2">
        <AlertTriangle className="w-5 h-5 text-blue-600 shrink-0 mt-0.5" />
        <div className="text-sm text-blue-900 leading-relaxed space-y-1">
          <div><span className="font-semibold">{ta('cmNoticeTitle')}</span> {ta('cmNoticeBody')}</div>
          <div className="text-xs text-blue-800">{ta('cmNoticeMatchHint')}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Card className="bg-purple-50 border-purple-200">
          <CardContent className="p-4 text-center">
            <Building2 className="w-5 h-5 mx-auto mb-1 text-purple-600" />
            <p className="text-xs text-purple-600">{ta('contractCount')}</p>
            <p className="text-2xl font-bold text-purple-700">{contracts.length}</p>
          </CardContent>
        </Card>
        <Card className="bg-blue-50 border-blue-200">
          <CardContent className="p-4 text-center">
            <BedDouble className="w-5 h-5 mx-auto mb-1 text-blue-600" />
            <p className="text-xs text-blue-600">{ta('totalAllotment')}</p>
            <p className="text-2xl font-bold text-blue-700">{totalAllocated}</p>
          </CardContent>
        </Card>
        <Card className="bg-amber-50 border-amber-200">
          <CardContent className="p-4 text-center">
            <Percent className="w-5 h-5 mx-auto mb-1 text-amber-600" />
            <p className="text-xs text-amber-600">{ta('used')}</p>
            <p className="text-2xl font-bold text-amber-700">{totalUsed}</p>
          </CardContent>
        </Card>
        <Card className="bg-green-50 border-green-200">
          <CardContent className="p-4 text-center">
            <Calendar className="w-5 h-5 mx-auto mb-1 text-green-600" />
            <p className="text-xs text-green-600">{ta('available')}</p>
            <p className="text-2xl font-bold text-green-700">{totalAvailable}</p>
          </CardContent>
        </Card>
      </div>

      {contracts.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-gray-500">
            <Building2 className="w-12 h-12 mx-auto mb-3 text-gray-300" />
            <p className="font-medium">{ta('noContracts')}</p>
            <p className="text-sm mt-1">{ta('noContractsHint')}</p>
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
                        <AlertTriangle className="w-3 h-3 mr-1" /> {ta('expiring')}
                      </Badge>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-600">{ta('roomType')}</span>
                      <span className="font-semibold">{ta(`roomTypes.${contract.room_type}`) || contract.room_type}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">{ta('allotment')}</span>
                      <span className="font-semibold">{contract.allocated_rooms} {ta('rooms')}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">{ta('usedRooms')}</span>
                      <span className="font-semibold">{contract.used_rooms || 0} {ta('rooms')}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">{ta('availableRooms')}</span>
                      <span className={`font-semibold ${available > 0 ? 'text-green-600' : 'text-red-600'}`}>{available} {ta('rooms')}</span>
                    </div>
                    <div className="bg-gray-100 rounded-full h-2 overflow-hidden">
                      <div className="bg-purple-500 h-full rounded-full" style={{ width: `${Math.min(usagePct, 100)}%` }} />
                    </div>
                    <p className="text-xs text-gray-400 text-center">{ta('usage')} %{usagePct}</p>
                    {(contract.bookings_count > 0 || contract.total_revenue > 0) && (
                      <div className="flex justify-between border-t pt-2">
                        <span className="text-gray-600">{ta('matchedRevenue')}</span>
                        <span className="font-semibold text-emerald-600">{fmt(contract.total_revenue)} {cur}</span>
                      </div>
                    )}
                    <div className="flex justify-between">
                      <span className="text-gray-600">{ta('price')}</span>
                      <span className="font-semibold">{fmt(contract.rate)} {cur}{ta('perNight')}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">{ta('period')}</span>
                      <span className="text-xs">
                        {contract.start_date ? new Date(contract.start_date).toLocaleDateString() : '-'} - {contract.end_date ? new Date(contract.end_date).toLocaleDateString() : '-'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">{ta('releaseDays')}</span>
                      <span className="font-semibold">{contract.release_days} {ta('days')}</span>
                    </div>
                    <Button size="sm" variant="outline" className="w-full mt-2" onClick={() => releaseRooms(contract.id)} disabled={available === 0}>
                      {ta('releaseRooms')}
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
            <DialogTitle>{ta('newContractTitle')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>{ta('tourOperator')}</Label>
              <Input value={formData.tour_operator} onChange={(e) => setFormData({ ...formData, tour_operator: e.target.value })} placeholder={ta('tourOperatorPlaceholder')} />
              <p className="text-xs text-gray-500 mt-1">{ta('tourOperatorHint')}</p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>{ta('roomTypeLabel')}</Label>
                <Select value={formData.room_type} onValueChange={(v) => setFormData({ ...formData, room_type: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ROOM_TYPE_KEYS.map(r => (
                      <SelectItem key={r} value={r}>{ta(`roomTypes.${r}`)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>{ta('roomCount')}</Label>
                <Input type="number" min="1" value={formData.allocated_rooms} onChange={(e) => setFormData({ ...formData, allocated_rooms: e.target.value })} placeholder="10" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>{ta('startDate')}</Label>
                <Input type="date" value={formData.start_date} onChange={(e) => setFormData({ ...formData, start_date: e.target.value })} />
              </div>
              <div>
                <Label>{ta('endDate')}</Label>
                <Input type="date" value={formData.end_date} onChange={(e) => setFormData({ ...formData, end_date: e.target.value })} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>{ta('nightlyRate')} ({cur})</Label>
                <Input type="number" min="0" step="0.01" value={formData.rate} onChange={(e) => setFormData({ ...formData, rate: e.target.value })} placeholder="500.00" />
              </div>
              <div>
                <Label>{ta('releasePeriod')}</Label>
                <Input type="number" min="0" value={formData.release_days} onChange={(e) => setFormData({ ...formData, release_days: e.target.value })} />
              </div>
            </div>
            <Button onClick={createContract} className="w-full">{ta('createContract')}</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AllotmentGrid;
