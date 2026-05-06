import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Users, Plus, LogIn, LogOut, Search, Loader2, ChevronRight, X, Trash2 } from 'lucide-react';

const API = "";

const todayISO = () => new Date().toISOString().slice(0, 10);
const tomorrowISO = () => {
  const d = new Date(); d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
};
const emptyRow = () => ({
  guest_name: '',
  room_id: '',
  check_in: todayISO(),
  check_out: tomorrowISO(),
  total_amount: '',
  adults: 1,
});

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
  // YENİ: tab + yeni rezervasyon satırları
  const [createMode, setCreateMode] = useState('existing'); // 'existing' | 'new'
  const [allRooms, setAllRooms] = useState([]);
  const [newRows, setNewRows] = useState([emptyRow()]);

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

  const loadRooms = async () => {
    try {
      const res = await axios.get(`/pms/rooms`);
      setAllRooms(Array.isArray(res.data) ? res.data : (res.data.rooms || []));
    } catch (e) { console.error(e); }
  };

  const openCreateDialog = () => {
    setShowCreate(true);
    setCreateMode('existing');
    setGroupName('');
    setSelectedBookingIds([]);
    setNewRows([emptyRow()]);
    loadBookings();
    loadRooms();
  };

  useEffect(() => { loadGroups(); }, [loadGroups]);

  const updateRow = (idx, patch) => {
    setNewRows(prev => prev.map((r, i) => i === idx ? { ...r, ...patch } : r));
  };
  const addRow = () => setNewRows(prev => [...prev, emptyRow()]);
  const removeRow = (idx) => setNewRows(prev => prev.filter((_, i) => i !== idx));

  const handleCreate = async () => {
    if (!groupName.trim()) {
      toast.error('Grup adı gerekli');
      return;
    }

    let payload = { group_name: groupName.trim() };

    if (createMode === 'existing') {
      if (selectedBookingIds.length === 0) {
        toast.error('En az 1 rezervasyon seçin');
        return;
      }
      payload.booking_ids = selectedBookingIds;
    } else {
      // Yeni rezervasyon modu — istemci-tarafı ön doğrulama
      const cleanRows = newRows.filter(r => r.guest_name.trim() || r.room_id);
      if (cleanRows.length === 0) {
        toast.error('En az 1 satır doldurun');
        return;
      }
      for (let i = 0; i < cleanRows.length; i++) {
        const r = cleanRows[i];
        if (!r.guest_name.trim()) { toast.error(`${i+1}. satır: misafir adı zorunlu`); return; }
        if (!r.room_id)            { toast.error(`${i+1}. satır: oda seçin`); return; }
        if (!(parseFloat(r.total_amount) > 0)) { toast.error(`${i+1}. satır: tutar girin`); return; }
        if (r.check_out <= r.check_in) { toast.error(`${i+1}. satır: çıkış tarihi giriş sonrası olmalı`); return; }
      }
      payload.new_bookings = cleanRows.map(r => ({
        guest_name: r.guest_name.trim(),
        room_id: r.room_id,
        check_in: r.check_in,
        check_out: r.check_out,
        total_amount: parseFloat(r.total_amount),
        adults: parseInt(r.adults) || 1,
      }));
    }

    setCreating(true);
    try {
      const res = await axios.post(`/pms/group-bookings`, payload);
      const created = res.data?.created_booking_ids?.length || 0;
      toast.success(
        created > 0
          ? `Grup oluşturuldu (${created} yeni rezervasyon yaratıldı)`
          : 'Grup oluşturuldu'
      );
      setShowCreate(false);
      setGroupName('');
      setSelectedBookingIds([]);
      setNewRows([emptyRow()]);
      await loadGroups();
    } catch (e) {
      toast.error('Hata: ' + (e.response?.data?.detail || e.message));
    }
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
    <>
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">Grup Rezervasyonları</h1>
            <p className="text-sm text-gray-500 mt-1">Grup giriş/çıkış ve toplu yönetim</p>
          </div>
          <Button onClick={openCreateDialog} className="bg-amber-500 hover:bg-amber-600 text-white" data-testid="create-group-btn">
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
          <DialogContent className="max-w-3xl max-h-[88vh] overflow-y-auto">
            <DialogHeader><DialogTitle>Yeni Grup Oluştur</DialogTitle></DialogHeader>
            <div className="space-y-4">
              <div>
                <Label>Grup Adı *</Label>
                <Input value={groupName} onChange={e => setGroupName(e.target.value)} placeholder="Örnek: ABC Turizm - 15 Mart" />
              </div>

              {/* Mode tabs */}
              <div className="flex gap-1 bg-gray-100 p-1 rounded-lg">
                <button
                  type="button"
                  onClick={() => setCreateMode('existing')}
                  className={`flex-1 text-sm font-medium py-2 rounded-md transition ${createMode === 'existing' ? 'bg-white shadow text-gray-900' : 'text-gray-500 hover:text-gray-700'}`}
                  data-testid="tab-existing"
                >
                  Mevcut Rezervasyonları Grupla
                </button>
                <button
                  type="button"
                  onClick={() => setCreateMode('new')}
                  className={`flex-1 text-sm font-medium py-2 rounded-md transition ${createMode === 'new' ? 'bg-white shadow text-gray-900' : 'text-gray-500 hover:text-gray-700'}`}
                  data-testid="tab-new"
                >
                  Yeni Rezervasyonlar Oluştur
                </button>
              </div>

              {createMode === 'existing' ? (
                <>
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
                </>
              ) : (
                <>
                  <div className="flex items-center justify-between">
                    <Label>Rezervasyonlar ({newRows.length} satır)</Label>
                    <div className="flex items-center gap-2">
                      <Button
                        type="button" size="sm" variant="outline"
                        onClick={() => {
                          // Tüm satırlara üst-satırdaki tarihleri uygula
                          const first = newRows[0];
                          if (!first) return;
                          setNewRows(prev => prev.map(r => ({ ...r, check_in: first.check_in, check_out: first.check_out })));
                          toast.success('Tarihler tüm satırlara uygulandı');
                        }}
                        className="h-8 text-xs"
                      >
                        Tarihleri Eşitle
                      </Button>
                      <Button type="button" size="sm" onClick={addRow} className="bg-blue-600 hover:bg-blue-700 text-white h-8 text-xs">
                        <Plus className="w-3 h-3 mr-1" /> Satır Ekle
                      </Button>
                    </div>
                  </div>
                  <div className="border rounded-lg overflow-hidden">
                    <div className="max-h-[50vh] overflow-y-auto">
                      <table className="w-full text-sm">
                        <thead className="bg-gray-50 sticky top-0 z-10">
                          <tr>
                            <th className="text-left py-2 px-2 font-medium text-xs text-gray-500">Misafir *</th>
                            <th className="text-left py-2 px-2 font-medium text-xs text-gray-500">Oda *</th>
                            <th className="text-left py-2 px-2 font-medium text-xs text-gray-500">Giriş</th>
                            <th className="text-left py-2 px-2 font-medium text-xs text-gray-500">Çıkış</th>
                            <th className="text-right py-2 px-2 font-medium text-xs text-gray-500">Tutar (TL) *</th>
                            <th className="py-2 px-2"></th>
                          </tr>
                        </thead>
                        <tbody>
                          {newRows.map((r, idx) => (
                            <tr key={idx} className="border-t">
                              <td className="py-1 px-2">
                                <Input value={r.guest_name} onChange={e => updateRow(idx, { guest_name: e.target.value })}
                                  placeholder="Ad Soyad" className="h-8 text-sm" />
                              </td>
                              <td className="py-1 px-2">
                                <select value={r.room_id} onChange={e => updateRow(idx, { room_id: e.target.value })}
                                  className="h-8 text-sm border rounded px-2 w-full bg-white">
                                  <option value="">Seç...</option>
                                  {allRooms.map(room => (
                                    <option key={room.id} value={room.id}>
                                      {room.room_number || room.number} {room.room_type ? `(${room.room_type})` : ''}
                                    </option>
                                  ))}
                                </select>
                              </td>
                              <td className="py-1 px-2">
                                <Input type="date" value={r.check_in} onChange={e => updateRow(idx, { check_in: e.target.value })}
                                  className="h-8 text-sm" />
                              </td>
                              <td className="py-1 px-2">
                                <Input type="date" value={r.check_out} onChange={e => updateRow(idx, { check_out: e.target.value })}
                                  className="h-8 text-sm" />
                              </td>
                              <td className="py-1 px-2">
                                <Input type="number" min="0" step="0.01" value={r.total_amount}
                                  onChange={e => updateRow(idx, { total_amount: e.target.value })}
                                  placeholder="0" className="h-8 text-sm text-right" />
                              </td>
                              <td className="py-1 px-2 text-center">
                                <button type="button" onClick={() => removeRow(idx)}
                                  disabled={newRows.length === 1}
                                  className="text-red-500 hover:text-red-700 disabled:opacity-30">
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                  <p className="text-xs text-gray-500">
                    Toplam tutar:{' '}
                    <strong>
                      {newRows.reduce((s, r) => s + (parseFloat(r.total_amount) || 0), 0).toLocaleString('tr-TR')} TL
                    </strong>
                    {' · '}
                    Misafir adları placeholder olarak kaydedilir; sonra her rezervasyondan misafir bilgilerini güncelleyebilirsiniz.
                  </p>
                </>
              )}

              <div className="flex justify-end gap-2 pt-2 border-t">
                <Button variant="outline" onClick={() => setShowCreate(false)}>İptal</Button>
                <Button onClick={handleCreate} disabled={creating} className="bg-amber-500 hover:bg-amber-600 text-white">
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
    </>
  );
}
