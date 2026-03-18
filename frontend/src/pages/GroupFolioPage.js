import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  Merge, Users, DollarSign, FileText, Check, AlertTriangle,
  RefreshCw, ArrowRight, Lock
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;
const fmtTL = (v) => (v || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2 });

const GroupFolioPage = ({ user, tenant, onLogout }) => {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedGroup, setSelectedGroup] = useState(null);
  const [groupDetail, setGroupDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [showMerge, setShowMerge] = useState(false);
  const [masterBookingId, setMasterBookingId] = useState('');
  const [mergePayments, setMergePayments] = useState(true);
  const [merging, setMerging] = useState(false);

  const loadGroups = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/api/pms/group-bookings`);
      setGroups(res.data?.groups || res.data || []);
    } catch (e) {
      console.error('Load groups error', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadGroups(); }, [loadGroups]);

  const loadGroupDetail = async (groupId) => {
    setDetailLoading(true);
    try {
      const res = await axios.get(`${API}/api/pms/group-folio/${groupId}`);
      setGroupDetail(res.data);
    } catch (e) {
      toast.error('Grup detay yuklenemedi');
      console.error(e);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleSelectGroup = (group) => {
    setSelectedGroup(group);
    loadGroupDetail(group.id);
  };

  const handleMerge = async () => {
    if (!masterBookingId || !groupDetail) {
      toast.error('Ana rezervasyon seciniz'); return;
    }

    const mergeIds = groupDetail.bookings
      .filter(b => b.booking_id !== masterBookingId && !b.folio_merged_to)
      .map(b => b.booking_id);

    if (mergeIds.length === 0) {
      toast.error('Birlestirilebilecek folio yok'); return;
    }

    setMerging(true);
    try {
      const res = await axios.post(`${API}/api/pms/group-folio/merge`, {
        group_id: selectedGroup.id,
        master_booking_id: masterBookingId,
        merge_booking_ids: mergeIds,
        merge_payments: mergePayments,
      });
      toast.success(`${res.data?.merged_entries_count || 0} folio girisi ve ${res.data?.merged_payments_count || 0} odeme birlestirildi`);
      setShowMerge(false);
      loadGroupDetail(selectedGroup.id);
    } catch (e) {
      toast.error('Birlestirme hatasi: ' + (e.response?.data?.detail || e.message));
    } finally {
      setMerging(false);
    }
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="pms">
      <div className="p-4 md:p-6 space-y-5 max-w-7xl mx-auto" data-testid="group-folio-page">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Merge className="w-6 h-6 text-violet-600" />
              Grup Folio Birlestirme
            </h1>
            <p className="text-sm text-gray-500 mt-1">Grup rezervasyonlarinin foliolarini tek bir ana folioda birlestirin</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => { setLoading(true); loadGroups(); }}>
            <RefreshCw className="w-4 h-4 mr-1" /> Yenile
          </Button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Groups List */}
          <div className="space-y-3">
            <h2 className="text-sm font-semibold text-gray-600 uppercase">Grup Rezervasyonlari</h2>
            {loading ? (
              <div className="text-center py-8 text-gray-400">Yukleniyor...</div>
            ) : groups.length === 0 ? (
              <Card className="p-8 text-center">
                <Users className="w-10 h-10 text-gray-300 mx-auto mb-2" />
                <p className="text-sm text-gray-500">Henuz grup rezervasyonu yok</p>
              </Card>
            ) : (
              groups.map(group => (
                <Card
                  key={group.id}
                  className={`cursor-pointer transition-all hover:shadow-md ${
                    selectedGroup?.id === group.id ? 'ring-2 ring-violet-400 bg-violet-50/30' : ''
                  }`}
                  onClick={() => handleSelectGroup(group)}
                  data-testid={`group-card-${group.id}`}
                >
                  <CardContent className="p-4">
                    <div className="font-semibold text-sm">{group.group_name}</div>
                    <div className="text-xs text-gray-500 mt-1 flex items-center gap-2">
                      <Users className="w-3 h-3" /> {(group.booking_ids || []).length} rezervasyon
                    </div>
                    <div className="text-xs text-gray-400 mt-1">{group.created_at?.slice(0, 10)}</div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>

          {/* Group Detail */}
          <div className="lg:col-span-2 space-y-4">
            {!selectedGroup ? (
              <Card className="p-12 text-center">
                <Merge className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                <p className="text-gray-500">Soldaki listeden bir grup secin</p>
              </Card>
            ) : detailLoading ? (
              <Card className="p-12 text-center text-gray-400">Yukleniyor...</Card>
            ) : groupDetail ? (
              <>
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold">{selectedGroup.group_name} - Folio Durumu</h2>
                  <Button size="sm" onClick={() => { setShowMerge(true); setMasterBookingId(groupDetail.bookings?.[0]?.booking_id || ''); }}
                    data-testid="merge-btn"
                    disabled={!groupDetail.bookings || groupDetail.bookings.length < 2}
                  >
                    <Merge className="w-4 h-4 mr-1" /> Foliolari Birlesdir
                  </Button>
                </div>

                {/* Bookings in Group */}
                <div className="space-y-2">
                  {(groupDetail.bookings || []).map((b, i) => (
                    <Card key={b.booking_id} data-testid={`booking-folio-${b.booking_id}`}>
                      <CardContent className="p-4">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-violet-100 to-violet-200 flex items-center justify-center text-sm font-bold text-violet-700">
                              {b.room_number || '?'}
                            </div>
                            <div>
                              <div className="font-semibold text-sm">{b.guest_name}</div>
                              <div className="text-xs text-gray-500">Oda: {b.room_number}</div>
                            </div>
                          </div>
                          <div className="grid grid-cols-3 gap-4 text-center">
                            <div>
                              <div className="text-xs text-gray-500">Konaklama</div>
                              <div className="text-sm font-semibold">{fmtTL(b.accommodation_total)} ₺</div>
                            </div>
                            <div>
                              <div className="text-xs text-gray-500">Ekstra</div>
                              <div className="text-sm font-semibold">{fmtTL(b.folio_charges)} ₺</div>
                            </div>
                            <div>
                              <div className="text-xs text-gray-500">Bakiye</div>
                              <div className={`text-sm font-bold ${b.balance > 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                                {fmtTL(b.balance)} ₺
                              </div>
                            </div>
                          </div>
                          <div>
                            {b.folio_merged_to ? (
                              <Badge className="bg-purple-100 text-purple-700 border-purple-200 text-xs">
                                <Lock className="w-3 h-3 mr-1" /> Birlestirildi
                              </Badge>
                            ) : (
                              <Badge className="bg-blue-100 text-blue-700 border-blue-200 text-xs">Aktif</Badge>
                            )}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>

                {/* Grand Total */}
                <Card className="bg-gradient-to-r from-violet-50 to-indigo-50 border-violet-200">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-violet-700">Grup Toplam Bakiye</span>
                      <span className="text-xl font-bold text-violet-700">
                        {fmtTL((groupDetail.bookings || []).reduce((sum, b) => sum + (b.balance || 0), 0))} ₺
                      </span>
                    </div>
                  </CardContent>
                </Card>

                {/* Merge Logs */}
                {groupDetail.merge_logs?.length > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold text-gray-600 mb-2">Birlestirme Gecmisi</h3>
                    {groupDetail.merge_logs.map(log => (
                      <Card key={log.id} className="mb-2">
                        <CardContent className="p-3 text-xs text-gray-600">
                          <div className="flex items-center gap-2">
                            <Check className="w-4 h-4 text-emerald-500" />
                            <span>{log.merged_by} - {log.total_entries_merged} giri, {log.total_payments_merged} odeme birlestirildi</span>
                            <span className="ml-auto text-gray-400">{log.created_at?.slice(0, 16).replace('T', ' ')}</span>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}
              </>
            ) : null}
          </div>
        </div>

        {/* Merge Dialog */}
        <Dialog open={showMerge} onOpenChange={setShowMerge}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Merge className="w-5 h-5 text-violet-600" /> Foliolari Birlesdir
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-700 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>Bu islem diger odalarin folio girislerini secilen ana folioya tasiyacaktir. Bu islem geri alinamaz.</span>
              </div>

              <div>
                <Label>Ana Rezervasyon (Master Folio)</Label>
                <select
                  value={masterBookingId}
                  onChange={e => setMasterBookingId(e.target.value)}
                  className="w-full border rounded-md px-3 py-2 text-sm"
                  data-testid="master-booking-select"
                >
                  {(groupDetail?.bookings || []).filter(b => !b.folio_merged_to).map(b => (
                    <option key={b.booking_id} value={b.booking_id}>
                      Oda {b.room_number} - {b.guest_name} (Bakiye: {fmtTL(b.balance)} ₺)
                    </option>
                  ))}
                </select>
              </div>

              <div className="text-sm text-gray-600">
                <div className="font-medium mb-2">Birlestirilecek Foliolar:</div>
                {(groupDetail?.bookings || []).filter(b => b.booking_id !== masterBookingId && !b.folio_merged_to).map(b => (
                  <div key={b.booking_id} className="flex items-center gap-2 py-1">
                    <ArrowRight className="w-3 h-3 text-violet-500" />
                    Oda {b.room_number} - {b.guest_name} ({fmtTL(b.balance)} ₺)
                  </div>
                ))}
              </div>

              <div className="flex items-center gap-2">
                <input type="checkbox" checked={mergePayments} onChange={e => setMergePayments(e.target.checked)} className="w-4 h-4 rounded" id="merge-payments" />
                <Label htmlFor="merge-payments" className="cursor-pointer text-sm">Odemeleri de birlesdir</Label>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowMerge(false)}>Iptal</Button>
                <Button onClick={handleMerge} disabled={merging} className="bg-violet-600 hover:bg-violet-700" data-testid="confirm-merge-btn">
                  {merging ? 'Birlestiriliyor...' : 'Birlesdir'}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
};

export default GroupFolioPage;
