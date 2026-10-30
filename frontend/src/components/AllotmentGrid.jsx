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
import {
  Building2, Plus, RefreshCw, Calendar, BedDouble, Percent, AlertTriangle
} from 'lucide-react';
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';

const ROOM_TYPE_KEYS = ['standard', 'superior', 'deluxe', 'suite', 'family', 'king'];

const AllotmentGrid = ({ rooms = [] }) => {
  const { t, i18n } = useTranslation();
  const ta = useCallback((k) => t(`pmsComponents.allotment.${k}`), [t]);
  const currency = cachedTenantCurrency();
  const roomTypes = useMemo(() => {
    const actual = [...new Set(rooms.filter(room => room.is_active !== false && !room.is_virtual).map(room => room.room_type || room.type).filter(Boolean))];
    return actual.sort((a, b) => a.localeCompare(b, i18n.language));
  }, [rooms, i18n.language]);

  const [contracts, setContracts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [releasing, setReleasing] = useState(null);
  const [loadError, setLoadError] = useState(false);
  const [showDialog, setShowDialog] = useState(false);
  const [formData, setFormData] = useState({
    tour_operator: '', room_type: '', allocated_rooms: '',
    start_date: '', end_date: '', rate: '', release_days: '7'
  });

  useEffect(() => {
    setFormData(prev => {
      const selected = roomTypes.includes(prev.room_type) ? prev.room_type : roomTypes[0] || '';
      return prev.room_type === selected ? prev : { ...prev, room_type: selected };
    });
  }, [roomTypes]);

  const loadContracts = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const all = [];
      for (let page = 1; ; page += 1) {
        const response = await axios.get('/pms/allotment-contracts', { params: { page, page_size: 200 } });
        const rows = response.data?.contracts || response.data || [];
        all.push(...rows);
        if (Array.isArray(response.data) || all.length >= (response.data?.total ?? all.length)) break;
        if (!rows.length) throw new Error('Incomplete contract page');
      }
      setContracts(all);
    } catch {
      setLoadError(true);
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
    const count = Number(formData.allocated_rooms), rate = Number(formData.rate), release = Number(formData.release_days);
    if (!roomTypes.includes(formData.room_type) || !Number.isInteger(count) || count < 1 || count > 10000
      || !formData.rate.trim() || !Number.isFinite(rate) || rate < 0 || !formData.release_days.trim()
      || !Number.isInteger(release) || release < 0 || release > 365) {
      toast.error('Oda tipi, fiyat, oda sayısı ve release süresini kontrol edin.'); return;
    }
    setCreating(true);
    try {
      await axios.post('/pms/allotment-contracts', {
        ...formData,
        allocated_rooms: count, rate, release_days: release, currency,
      });
      toast.success(ta('contractCreated'));
      loadContracts();
      setShowDialog(false);
      setFormData({ tour_operator: '', room_type: roomTypes[0] || '', allocated_rooms: '', start_date: '', end_date: '', rate: '', release_days: '7' });
    } catch {
      toast.error(ta('createError'));
    } finally {
      setCreating(false);
    }
  };

  const releaseRooms = async (contractId) => {
    setReleasing(contractId);
    try {
      await axios.post(`/pms/allotment-contracts/${contractId}/release`);
      toast.success(ta('roomsReleased'));
      loadContracts();
    } catch {
      toast.error(ta('releaseError'));
    } finally {
      setReleasing(null);
    }
  };

  const totalAllocated = contracts.reduce((s, c) => s + (c.allocated_rooms || 0), 0);
  const totalUsed = contracts.reduce((s, c) => s + (c.used_rooms || 0), 0);
  const contractAvailable = c => c.available_rooms ?? Math.max(0, (c.allocated_rooms || 0) - (c.used_rooms || 0) - (c.released_rooms || 0));
  const totalAvailable = contracts.reduce((s, c) => s + contractAvailable(c), 0);

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
          <Button onClick={() => setShowDialog(true)} disabled={loading || loadError || !roomTypes.length}>
            <Plus className="w-4 h-4 mr-2" /> {ta('newContract')}
          </Button>
        </div>
      </div>
      {loadError && <div role="alert">Sözleşmeler yüklenemedi; görünen sayılar güncel kabul edilmemeli. Yenileyin.</div>}
      {!roomTypes.length && <div role="alert">Fiziksel oda envanteri yüklenmeden sözleşme oluşturulamaz.</div>}

      <div className="rounded-lg border border-blue-300 bg-blue-50 p-3 flex items-start gap-2">
        <AlertTriangle className="w-5 h-5 text-blue-600 shrink-0 mt-0.5" />
        <div className="text-sm text-blue-900 leading-relaxed space-y-1">
          <div><span className="font-semibold">{ta('cmNoticeTitle')}</span> {ta('cmNoticeBody')}</div>
          <div className="text-xs text-blue-800">{ta('cmNoticeMatchHint')}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Card className="bg-indigo-50 border-indigo-200">
          <CardContent className="p-4 text-center">
            <Building2 className="w-5 h-5 mx-auto mb-1 text-indigo-600" />
            <p className="text-xs text-indigo-600">{ta('contractCount')}</p>
            <p className="text-2xl font-bold text-indigo-700">{contracts.length}</p>
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
            const available = contractAvailable(contract);
            const usagePct = contract.allocated_rooms > 0 ? Math.round((contract.used_rooms || 0) / contract.allocated_rooms * 100) : 0;
            const endDate = contract.end_date ? new Date(contract.end_date) : null;
            const isExpiring = endDate && endDate >= new Date() && endDate < new Date(Date.now() + 7 * 86400000);
            return (
              <Card key={contract.id} className="hover:shadow-lg transition">
                <CardHeader className="pb-2">
                  <div className="flex justify-between items-start">
                    <div className="flex items-center gap-2">
                      <Building2 className="w-5 h-5 text-indigo-500" />
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
                      <span className="font-semibold">{ROOM_TYPE_KEYS.includes(contract.room_type) ? ta(`roomTypes.${contract.room_type}`) : contract.room_type}</span>
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
                      <div className="bg-indigo-500 h-full rounded-full" style={{ width: `${Math.min(usagePct, 100)}%` }} />
                    </div>
                    <p className="text-xs text-gray-400 text-center">{ta('usage')} %{usagePct}</p>
                    {contract.bookings_count > 0 && (
                      <div className="flex justify-between border-t pt-2">
                        <span className="text-gray-600">{ta('matchedRevenue')}</span>
                        <span className="font-semibold text-emerald-600">
                          {Object.entries(contract.total_revenue_by_currency || {}).map(([code, amount]) => <span key={code} className="block">{formatCurrency(amount, code)}</span>)}
                          {contract.unknown_currency_bookings > 0 && <span className="block">Para birimi eksik: {contract.unknown_currency_bookings} rezervasyon</span>}
                        </span>
                      </div>
                    )}
                    <div className="flex justify-between">
                      <span className="text-gray-600">{ta('price')}</span>
                      <span className="font-semibold">{contract.currency ? formatCurrency(contract.rate, contract.currency) : `${contract.rate ?? '—'} (para birimi belirtilmemiş)`}{ta('perNight')}</span>
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
                    <Button size="sm" variant="outline" className="w-full mt-2" onClick={() => releaseRooms(contract.id)} disabled={available === 0 || loading || loadError || releasing !== null}>
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
              <Label htmlFor="allotment-operator">{ta('tourOperator')}</Label>
              <Input id="allotment-operator" value={formData.tour_operator} onChange={(e) => setFormData({ ...formData, tour_operator: e.target.value })} placeholder={ta('tourOperatorPlaceholder')} />
              <p className="text-xs text-gray-500 mt-1">{ta('tourOperatorHint')}</p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>{ta('roomTypeLabel')}</Label>
                <Select value={formData.room_type} onValueChange={(v) => setFormData({ ...formData, room_type: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {roomTypes.map(r => (
                      <SelectItem key={r} value={r}>{ROOM_TYPE_KEYS.includes(r) ? ta(`roomTypes.${r}`) : r}</SelectItem>
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
                <Label>{ta('nightlyRate')} ({currency})</Label>
                <Input type="number" min="0" step="0.01" value={formData.rate} onChange={(e) => setFormData({ ...formData, rate: e.target.value })} placeholder="500.00" />
              </div>
              <div>
                <Label>{ta('releasePeriod')}</Label>
                <Input type="number" min="0" value={formData.release_days} onChange={(e) => setFormData({ ...formData, release_days: e.target.value })} />
              </div>
            </div>
            <Button onClick={createContract} disabled={creating || loadError || !roomTypes.length} className="w-full">{ta('createContract')}</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AllotmentGrid;
