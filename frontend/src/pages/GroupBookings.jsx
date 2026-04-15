import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Users, Plus, LogIn, LogOut, Search, Building2, Calendar, Loader2, ChevronRight, X } from 'lucide-react';

const API = "";

export default function GroupBookings({ user, tenant, onLogout }) {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showDetail, setShowDetail] = useState(null);
  const [groupName, setGroupName] = useState('');
  const [searchBooking, setSearchBooking] = useState('');
  const [allBookings, setAllBookings] = useState([]);
  const [selectedBookingIds, setSelectedBookingIds] = useState([]);
  const [creating, setCreating] = useState(false);

  const loadGroups = useCallback(async () => {
    try {
      const res = await axios.get(`/pms/group-bookings`);
      setGroups(res.data.groups || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

  const loadBookings = async () => {
    try {
      const res = await axios.get(`/pms/bookings`);
      setAllBookings(Array.isArray(res.data) ? res.data : (res.data.bookings || []));
    } catch (e) { console.error(e); }
  };

  useEffect(() => { loadGroups(); }, [loadGroups]);

  const handleCreate = async () => {
    if (!groupName.trim() || selectedBookingIds.length === 0) {
      toast.error('Grup adı ve en az 1 rezervasyon gerekli');
      return;
    }
    setCreating(true);
    try {
      await axios.post(`/pms/group-bookings`, { group_name: groupName, booking_ids: selectedBookingIds });
      toast.success('Grup oluşturuldu');
      setShowCreate(false);
      setGroupName('');
      setSelectedBookingIds([]);
      loadGroups();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setCreating(false);
  };

  const handleGroupCheckin = async (groupId) => {
    try {
      const res = await axios.post(`/pms/group-bookings/${groupId}/check-in-all`);
      toast.success(`${res.data.checked_in_count} misafir giriş yaptı`);
      loadGroups();
      if (showDetail) loadGroupDetail(groupId);
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  const handleGroupCheckout = async (groupId) => {
    try {
      const res = await axios.post(`/pms/group-bookings/${groupId}/check-out-all`);
      toast.success(`${res.data.checked_out_count} misafir çıkış yaptı`);
      loadGroups();
      if (showDetail) loadGroupDetail(groupId);
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  const loadGroupDetail = async (groupId) => {
    try {
      const res = await axios.get(`/pms/group-bookings/${groupId}`);
      setShowDetail(res.data);
    } catch (e) { toast.error('Detay yüklenemedi'); }
  };

  const toggleBookingSelection = (id) => {
    setSelectedBookingIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const filteredBookings = allBookings.filter(b =>
    !b.group_booking_id && b.status !== 'cancelled' &&
    (searchBooking === '' ||
     (b.guest_name || '').toLowerCase().includes(searchBooking.toLowerCase()) ||
     (b.room_number || '').includes(searchBooking))
  );

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="group-bookings">
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">Grup Rezervasyonları</h1>
            <p className="text-sm text-gray-500 mt-1">Grup giriş/çıkış ve toplu yönetim</p>
          </div>
          <Button onClick={() => { setShowCreate(true); loadBookings(); }} className="bg-orange-500 hover:bg-orange-600 text-white" data-testid="create-group-btn">
            <Plus className="w-4 h-4 mr-2" /> Yeni Grup
          </Button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16"><Loader2 className="w-8 h-8 animate-spin text-gray-400" /></div>
        ) : groups.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <Users className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p className="text-lg font-medium">Henüz grup rezervasyon yok</p>
            <p className="text-sm mt-1">Yeni bir grup oluşturun</p>
          </div>
        ) : (
          <div className="grid gap-4">
            {groups.map(g => (
              <div key={g.id} className="border rounded-xl bg-white p-5 hover:shadow-md transition-shadow cursor-pointer" onClick={() => loadGroupDetail(g.id)} data-testid={`group-card-${g.id}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 bg-amber-100 rounded-xl flex items-center justify-center">
                      <Users className="w-6 h-6 text-amber-600" />
                    </div>
                    <div>
                      <h3 className="font-bold text-gray-800">{g.group_name}</h3>
                      <div className="flex items-center gap-3 text-xs text-gray-500 mt-1">
                        <span>{g.total_rooms || g.booking_ids?.length || 0} oda</span>
                        <span>{(g.total_amount || 0).toLocaleString('tr-TR')} TL</span>
                        <span>Ödenen: {(g.total_paid || 0).toLocaleString('tr-TR')} TL</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); handleGroupCheckin(g.id); }} className="h-8 text-xs" data-testid={`group-checkin-${g.id}`}>
                      <LogIn className="w-3 h-3 mr-1" /> Toplu Giriş
                    </Button>
                    <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); handleGroupCheckout(g.id); }} className="h-8 text-xs" data-testid={`group-checkout-${g.id}`}>
                      <LogOut className="w-3 h-3 mr-1" /> Toplu Çıkış
                    </Button>
                    <ChevronRight className="w-4 h-4 text-gray-400" />
                  </div>
                </div>
                {/* Mini booking list */}
                <div className="mt-3 flex flex-wrap gap-2">
                  {(g.bookings || []).slice(0, 6).map(b => (
                    <Badge key={b.id} className={`text-xs ${b.status === 'checked_in' ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-700'}`}>
                      {b.room_number || '?'} - {b.guest_name?.split(' ')[0] || '?'}
                    </Badge>
                  ))}
                  {(g.bookings?.length || 0) > 6 && <Badge className="bg-gray-100 text-gray-500 text-xs">+{g.bookings.length - 6}</Badge>}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Create Group Dialog */}
        <Dialog open={showCreate} onOpenChange={setShowCreate}>
          <DialogContent className="max-w-2xl">
            <DialogHeader><DialogTitle>Yeni Grup Oluştur</DialogTitle></DialogHeader>
            <div className="space-y-4">
              <div>
                <Label>Grup Adı *</Label>
                <Input value={groupName} onChange={e => setGroupName(e.target.value)} placeholder="Örnek: ABC Turizm - 15 Mart" />
              </div>
              <div>
                <Label>Rezervasyonları Seç ({selectedBookingIds.length} seçili)</Label>
                <div className="relative mt-1">
                  <Search className="absolute left-2 top-2 w-4 h-4 text-gray-400" />
                  <Input value={searchBooking} onChange={e => setSearchBooking(e.target.value)} placeholder="Misafir adı veya oda no..." className="pl-8" />
                </div>
              </div>
              <div className="max-h-60 overflow-y-auto border rounded-lg">
                {filteredBookings.length === 0 ? (
                  <div className="p-4 text-center text-gray-400 text-sm">Uygun rezervasyon bulunamadı</div>
                ) : (
                  filteredBookings.map(b => (
                    <div key={b.id} className={`flex items-center gap-3 p-3 border-b last:border-b-0 cursor-pointer hover:bg-gray-50 ${selectedBookingIds.includes(b.id) ? 'bg-blue-50' : ''}`}
                      onClick={() => toggleBookingSelection(b.id)}>
                      <input type="checkbox" checked={selectedBookingIds.includes(b.id)} onChange={() => {}} className="w-4 h-4" />
                      <div className="flex-1">
                        <div className="text-sm font-medium">{b.guest_name || '-'}</div>
                        <div className="text-xs text-gray-500">Oda: {b.room_number || '?'} | {b.check_in?.toString().slice(0, 10)} - {b.check_out?.toString().slice(0, 10)}</div>
                      </div>
                      <span className="text-sm font-medium text-gray-600">{(b.total_amount || 0).toLocaleString('tr-TR')} TL</span>
                    </div>
                  ))
                )}
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setShowCreate(false)}>İptal</Button>
                <Button onClick={handleCreate} disabled={creating} className="bg-orange-500 hover:bg-orange-600 text-white">
                  {creating ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null} Grup Oluştur
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        {/* Group Detail Dialog */}
        <Dialog open={!!showDetail} onOpenChange={() => setShowDetail(null)}>
          <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
            <DialogHeader><DialogTitle>{showDetail?.group_name || 'Grup Detayı'}</DialogTitle></DialogHeader>
            {showDetail && (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-center">
                    <div className="text-xs text-blue-600 font-medium">Toplam Oda</div>
                    <div className="text-lg font-bold text-blue-800">{showDetail.bookings?.length || 0}</div>
                  </div>
                  <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 text-center">
                    <div className="text-xs text-emerald-600 font-medium">Toplam Tutar</div>
                    <div className="text-lg font-bold text-emerald-800">{(showDetail.total_amount || 0).toLocaleString('tr-TR')} TL</div>
                  </div>
                  <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-center">
                    <div className="text-xs text-amber-600 font-medium">Ödenen</div>
                    <div className="text-lg font-bold text-amber-800">{(showDetail.total_paid || 0).toLocaleString('tr-TR')} TL</div>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => handleGroupCheckin(showDetail.id)} className="bg-emerald-600 hover:bg-emerald-700 text-white h-8 text-xs">
                    <LogIn className="w-3 h-3 mr-1" /> Toplu Giriş
                  </Button>
                  <Button size="sm" onClick={() => handleGroupCheckout(showDetail.id)} className="bg-amber-600 hover:bg-amber-700 text-white h-8 text-xs">
                    <LogOut className="w-3 h-3 mr-1" /> Toplu Çıkış
                  </Button>
                </div>
                <div className="border rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="text-left py-2 px-3 font-medium text-xs text-gray-500">Misafir</th>
                        <th className="text-left py-2 px-3 font-medium text-xs text-gray-500">Oda</th>
                        <th className="text-left py-2 px-3 font-medium text-xs text-gray-500">Tarih</th>
                        <th className="text-left py-2 px-3 font-medium text-xs text-gray-500">Durum</th>
                        <th className="text-right py-2 px-3 font-medium text-xs text-gray-500">Tutar</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(showDetail.bookings || []).map(b => (
                        <tr key={b.id} className="border-t">
                          <td className="py-2 px-3">
                            <div className="font-medium">{b.guest_name || b.guest_detail?.name || '-'}</div>
                          </td>
                          <td className="py-2 px-3">{b.room_number || '-'}</td>
                          <td className="py-2 px-3 text-xs">{b.check_in?.toString().slice(0, 10)} - {b.check_out?.toString().slice(0, 10)}</td>
                          <td className="py-2 px-3">
                            <Badge className={`text-xs ${b.status === 'checked_in' ? 'bg-emerald-100 text-emerald-700' : b.status === 'confirmed' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-700'}`}>
                              {b.status === 'checked_in' ? 'Giriş' : b.status === 'confirmed' ? 'Onay' : b.status || '-'}
                            </Badge>
                          </td>
                          <td className="py-2 px-3 text-right font-medium">{(b.total_amount || 0).toLocaleString('tr-TR')} TL</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
}
