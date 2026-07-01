import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Users, Plus, Mail, Phone, Home, Trash2, UploadCloud, UnlockKeyhole } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const StatusBadge = ({ status }) => {
  const { t } = useTranslation();
  const colors = {
    tentative: 'bg-yellow-100 text-yellow-800',
    definite: 'bg-green-100 text-green-800',
    released: 'bg-gray-100 text-gray-800',
    completed: 'bg-blue-100 text-blue-800',
    cancelled: 'bg-red-100 text-red-800'
  };

  const labels = {
    tentative: 'Opsiyonel',
    definite: 'Kesin',
    released: 'Serbest Bırakıldı',
    completed: 'Tamamlandı',
    cancelled: 'İptal'
  };

  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium ${colors[status] || 'bg-gray-100 text-gray-800'}`}>
      {labels[status] || status}
    </span>
  );
};

const emptyRoomingRow = () => ({
  guest_name: '',
  room_type: 'Standard',
  check_in: '',
  check_out: '',
  email: '',
  phone: '',
  passport_number: '',
  special_requests: '',
});

const GroupSales = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(false);
  const [groups, setGroups] = useState([]);
  const [statusFilter, setStatusFilter] = useState('all');
  const [dateFilter, setDateFilter] = useState('this_month');
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');
  const [selectedGroup, setSelectedGroup] = useState(null);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [groupDetails, setGroupDetails] = useState(null);

  // Rooming list (toplu rezervasyon yükleme)
  const [roomingRows, setRoomingRows] = useState([emptyRoomingRow()]);
  const [roomingLoading, setRoomingLoading] = useState(false);

  // Bloğu serbest bırak (cutoff sonrası N oda iade)
  const [showReleaseDialog, setShowReleaseDialog] = useState(false);
  const [releaseCount, setReleaseCount] = useState(1);
  const [releaseLoading, setReleaseLoading] = useState(false);

  const [newGroup, setNewGroup] = useState({
    group_name: '',
    organization: '',
    contact_name: '',
    contact_email: '',
    contact_phone: '',
    check_in: '',
    check_out: '',
    total_rooms: 10,
    group_rate: 100,
    room_type: 'Standard',
    cutoff_date: '',
    billing_type: 'master_account',
    special_requirements: ''
  });

  useEffect(() => {
    loadGroups();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [statusFilter, dateFilter, customStart, customEnd]);

  const loadGroups = async () => {
    try {
      const params = {};
      if (statusFilter !== 'all') params.status = statusFilter;

      // Backend date filtering
      if (dateFilter === 'today' || dateFilter === 'this_month') {
        params.date_range = dateFilter;
      } else if (dateFilter === 'custom' && customStart && customEnd) {
        params.date_range = 'custom';
        params.start_date = customStart;
        params.end_date = customEnd;
      }

      const response = await axios.get('/groups/blocks', { params });
      const blocks = response.data.blocks || [];

      setGroups(blocks);
    } catch (error) {
      toast.error('Grup listesi yüklenemedi');
    }
  };

  const handleCreateGroup = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post('/groups/create-block', newGroup);
      toast.success('Grup bloğu başarıyla oluşturuldu!');
      setShowCreateDialog(false);
      loadGroups();
      setNewGroup({
        group_name: '',
        organization: '',
        contact_name: '',
        contact_email: '',
        contact_phone: '',
        check_in: '',
        check_out: '',
        total_rooms: 10,
        group_rate: 100,
        room_type: 'Standard',
        cutoff_date: '',
        billing_type: 'master_account',
        special_requirements: ''
      });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Grup oluşturulamadı');
    } finally {
      setLoading(false);
    }
  };

  const loadGroupDetails = async (blockId) => {
    try {
      const response = await axios.get(`/groups/block/${blockId}`);
      setGroupDetails(response.data);
      setSelectedGroup(blockId);
      // Rooming list satırlarını blok tarihleriyle önyükle
      const block = response.data.block || {};
      setRoomingRows([{
        ...emptyRoomingRow(),
        room_type: block.room_type || 'Standard',
        check_in: block.check_in || '',
        check_out: block.check_out || '',
      }]);
    } catch (error) {
      toast.error('Grup detayları yüklenemedi');
    }
  };

  const closeDetail = () => {
    setSelectedGroup(null);
    setGroupDetails(null);
    setRoomingRows([emptyRoomingRow()]);
  };

  // ── Rooming list işlemleri ─────────────────────────────────────────
  const updateRoomingRow = (idx, patch) => {
    setRoomingRows((rows) => rows.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  };
  const addRoomingRow = () => {
    const last = roomingRows[roomingRows.length - 1] || emptyRoomingRow();
    setRoomingRows((rows) => [...rows, {
      ...emptyRoomingRow(),
      room_type: last.room_type,
      check_in: last.check_in,
      check_out: last.check_out,
    }]);
  };
  const removeRoomingRow = (idx) => {
    setRoomingRows((rows) => (rows.length === 1 ? [emptyRoomingRow()] : rows.filter((_, i) => i !== idx)));
  };

  const handleUploadRoomingList = async () => {
    if (!selectedGroup) return;
    const valid = roomingRows.filter(r => r.guest_name && r.check_in && r.check_out && r.room_type);
    if (valid.length === 0) {
      toast.error('En az bir geçerli satır gerekli (Misafir, Oda Tipi, Tarihler).');
      return;
    }
    const payload = valid.map((r) => ({
      guest_name: r.guest_name,
      room_type: r.room_type,
      check_in: r.check_in,
      check_out: r.check_out,
      email: r.email || null,
      phone: r.phone || null,
      passport_number: r.passport_number || null,
      special_requests: r.special_requests || null,
    }));
    setRoomingLoading(true);
    try {
      const res = await axios.post(`/groups/rooming-list/${selectedGroup}`, payload);
      const ok = res.data?.successful ?? 0;
      const failed = res.data?.failed ?? 0;
      if (ok > 0) toast.success(`${ok} rezervasyon oluşturuldu`);
      if (failed > 0) {
        const errs = (res.data?.errors || []).slice(0, 3).join('\n');
        toast.error(`${failed} satır başarısız${errs ? `:\n${errs}` : ''}`);
      }
      await loadGroupDetails(selectedGroup);
      loadGroups();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Rooming list yüklenemedi');
    } finally {
      setRoomingLoading(false);
    }
  };

  // ── Bloğu serbest bırak (release N rooms) ──────────────────────────
  const openReleaseDialog = () => {
    const remaining = (groupDetails?.pickup?.rooms_remaining) ?? 0;
    setReleaseCount(Math.max(1, remaining));
    setShowReleaseDialog(true);
  };
  const handleReleaseBlock = async () => {
    if (!selectedGroup || releaseCount <= 0) return;
    setReleaseLoading(true);
    try {
      const res = await axios.post(
        `/groups/block/${selectedGroup}/release`,
        null,
        { params: { release_count: releaseCount } }
      );
      toast.success(res.data?.message || `${releaseCount} oda serbest bırakıldı`);
      setShowReleaseDialog(false);
      await loadGroupDetails(selectedGroup);
      loadGroups();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Serbest bırakma başarısız');
    } finally {
      setReleaseLoading(false);
    }
  };

  return (
    <>
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <Button 
            variant="outline" 
            size="icon"
            onClick={() => navigate('/')}
            className="hover:bg-indigo-50"
          >
            <Home className="w-5 h-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">
              Grup Satış Yönetimi
            </h1>
            <p className="text-gray-600">
              Grup rezervasyonları, bloklar ve rooming list yönetimi
            </p>
          </div>
        </div>
        
        <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
          <DialogTrigger asChild>
            <Button size="lg" className="bg-indigo-600 hover:bg-indigo-700">
              <Plus className="w-5 h-5 mr-2" />
              Yeni Grup Bloğu
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Yeni Grup Bloğu Oluştur</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreateGroup} className="space-y-4 mt-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Grup Adı *</Label>
                  <Input
                    value={newGroup.group_name}
                    onChange={(e) => setNewGroup({...newGroup, group_name: e.target.value})}
                    required
                    placeholder="ABC Şirketi Toplantısı"
                  />
                </div>
                <div>
                  <Label>Organizasyon *</Label>
                  <Input
                    value={newGroup.organization}
                    onChange={(e) => setNewGroup({...newGroup, organization: e.target.value})}
                    required
                    placeholder="ABC Şirketi"
                  />
                </div>
                <div>
                  <Label>İlgili Kişi *</Label>
                  <Input
                    value={newGroup.contact_name}
                    onChange={(e) => setNewGroup({...newGroup, contact_name: e.target.value})}
                    required
                    placeholder="Ahmet Yılmaz"
                  />
                </div>
                <div>
                  <Label>E-posta *</Label>
                  <Input
                    type="email"
                    value={newGroup.contact_email}
                    onChange={(e) => setNewGroup({...newGroup, contact_email: e.target.value})}
                    required
                    placeholder="ahmet@abc.com"
                  />
                </div>
                <div>
                  <Label>Telefon *</Label>
                  <Input
                    value={newGroup.contact_phone}
                    onChange={(e) => setNewGroup({...newGroup, contact_phone: e.target.value})}
                    required
                    placeholder="+90 555 123 45 67"
                  />
                </div>
                <div>
                  <Label>Toplam Oda Sayısı *</Label>
                  <Input
                    type="number"
                    min="1"
                    value={newGroup.total_rooms}
                    onChange={(e) => setNewGroup({...newGroup, total_rooms: parseInt(e.target.value)})}
                    required
                  />
                </div>
                <div>
                  <Label>Check-in Tarihi *</Label>
                  <Input
                    type="date"
                    value={newGroup.check_in}
                    onChange={(e) => setNewGroup({...newGroup, check_in: e.target.value})}
                    required
                  />
                </div>
                <div>
                  <Label>Check-out Tarihi *</Label>
                  <Input
                    type="date"
                    value={newGroup.check_out}
                    onChange={(e) => setNewGroup({...newGroup, check_out: e.target.value})}
                    required
                  />
                </div>
                <div>
                  <Label>Cutoff Tarihi *</Label>
                  <Input
                    type="date"
                    value={newGroup.cutoff_date}
                    onChange={(e) => setNewGroup({...newGroup, cutoff_date: e.target.value})}
                    required
                  />
                  <p className="text-xs text-gray-500 mt-1">Rezervasyon kapanış tarihi</p>
                </div>
                <div>
                  <Label>Grup Fiyatı (₺) *</Label>
                  <Input
                    type="number"
                    min="0"
                    value={newGroup.group_rate}
                    onChange={(e) => setNewGroup({...newGroup, group_rate: parseFloat(e.target.value)})}
                    required
                  />
                </div>
                <div>
                  <Label>Oda Tipi</Label>
                  <Select 
                    value={newGroup.room_type}
                    onValueChange={(val) => setNewGroup({...newGroup, room_type: val})}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Standard">Standard</SelectItem>
                      <SelectItem value="Deluxe">Deluxe</SelectItem>
                      <SelectItem value="Suite">Suite</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Fatura Tipi</Label>
                  <Select 
                    value={newGroup.billing_type}
                    onValueChange={(val) => setNewGroup({...newGroup, billing_type: val})}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="master_account">Master Hesap</SelectItem>
                      <SelectItem value="individual">Bireysel Fatura</SelectItem>
                      <SelectItem value="split">Karma (Split)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div>
                <Label>Özel Gereksinimler</Label>
                <Textarea
                  value={newGroup.special_requirements}
                  onChange={(e) => setNewGroup({...newGroup, special_requirements: e.target.value})}
                  placeholder="Meeting room, catering, özel istekler..."
                  rows={3}
                />
              </div>

              <div className="flex gap-3">
                <Button type="button" variant="outline" onClick={() => setShowCreateDialog(false)} className="flex-1">
                  İptal
                </Button>
                <Button type="submit" disabled={loading} className="flex-1 bg-indigo-600 hover:bg-indigo-700">
                  {loading ? 'Oluşturuluyor...' : 'Grup Bloğu Oluştur'}
                </Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Filters */}
      <div className="mt-4 mb-6 grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <Label className="text-xs text-gray-600">Durum</Label>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger>
              <SelectValue placeholder="Tüm durumlar" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("common.all")}</SelectItem>
              <SelectItem value="tentative">Opsiyonel</SelectItem>
              <SelectItem value="definite">Kesin</SelectItem>
              <SelectItem value="completed">Tamamlandı</SelectItem>
              <SelectItem value="cancelled">{t("common.cancel")}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs text-gray-600">Tarih Aralığı (Check-in)</Label>
          <Select value={dateFilter} onValueChange={setDateFilter}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="today">Bugün</SelectItem>
              <SelectItem value="this_month">Bu Ay</SelectItem>
              <SelectItem value="next_30">Önümüzdeki 30 Gün</SelectItem>
              <SelectItem value="custom">Özel Aralık</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {dateFilter === 'custom' && (
          <div className="grid grid-cols-2 gap-2">
            <div>
              <Label className="text-xs text-gray-600">Başlangıç</Label>
              <Input type="date" value={customStart} onChange={(e) => setCustomStart(e.target.value)} />
            </div>
            <div>
              <Label className="text-xs text-gray-600">Bitiş</Label>
              <Input type="date" value={customEnd} onChange={(e) => setCustomEnd(e.target.value)} />
            </div>
          </div>
        )}
      </div>

      {/* Group List */}
      <div className="grid grid-cols-1 gap-4">
        {groups.length === 0 ? (
          <Card>
            <CardContent className="pt-12 pb-12 text-center">
              <Users className="w-16 h-16 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-600 mb-4">Henüz grup rezervasyonu yok</p>
              <Button onClick={() => setShowCreateDialog(true)}>
                İlk Grup Bloğunu Oluştur
              </Button>
            </CardContent>
          </Card>
        ) : (
          groups.map((group) => (
            <Card 
              key={group.id} 
              className="cursor-pointer hover:shadow-lg transition-shadow"
              onClick={() => loadGroupDetails(group.id)}
            >
              <CardContent className="pt-6">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h3 className="text-xl font-bold text-gray-900">{group.group_name}</h3>
                      <StatusBadge status={group.status} />
                    </div>
                    <p className="text-gray-600 mb-3">{group.organization}</p>
                    
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
                      <div>
                        <p className="text-xs text-gray-500">Check-in</p>
                        <p className="font-semibold">{new Date(group.check_in).toLocaleDateString('tr-TR')}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500">Toplam Oda</p>
                        <p className="font-semibold">{group.total_rooms} oda</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500">Pickup</p>
                        <p className="font-semibold">{group.rooms_picked_up} / {group.total_rooms}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500">Grup Fiyatı</p>
                        <p className="font-semibold">₺{group.group_rate}</p>
                      </div>
                    </div>
                  </div>
                  
                  <div className="text-right">
                    <div className="text-3xl font-bold text-indigo-600">
                      {Math.round((group.rooms_picked_up / group.total_rooms) * 100)}%
                    </div>
                    <div className="text-xs text-gray-500">Pickup Oranı</div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Group Details Modal */}
      {selectedGroup && groupDetails && (
        <Dialog open={!!selectedGroup} onOpenChange={(open) => { if (!open) closeDetail(); }}>
          <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <div className="flex items-start justify-between gap-3">
                <DialogTitle className="text-2xl">
                  {groupDetails.block.group_name}
                </DialogTitle>
                {(groupDetails.pickup?.rooms_remaining ?? 0) > 0 &&
                  groupDetails.block.status !== 'released' &&
                  groupDetails.block.status !== 'cancelled' && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={openReleaseDialog}
                    className="mr-8 text-amber-700 border-amber-300 hover:bg-amber-50"
                  >
                    <UnlockKeyhole className="w-4 h-4 mr-1" />
                    Bloğu Serbest Bırak
                  </Button>
                )}
              </div>
            </DialogHeader>

            <Tabs defaultValue="overview" className="mt-4">
              <TabsList className="grid w-full grid-cols-4">
                <TabsTrigger value="overview">{t("loyalty.overview")}</TabsTrigger>
                <TabsTrigger value="bookings">Rezervasyonlar ({groupDetails.bookings_count})</TabsTrigger>
                <TabsTrigger value="rooming">Rooming List</TabsTrigger>
                <TabsTrigger value="folio">Master Folio</TabsTrigger>
              </TabsList>

              <TabsContent value="overview" className="space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle>Pickup Durumu</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <span>Toplam Oda:</span>
                        <span className="font-bold">{groupDetails.pickup.total_rooms}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span>Alınan Oda:</span>
                        <span className="font-bold text-green-600">{groupDetails.pickup.rooms_picked_up}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span>Kalan Oda:</span>
                        <span className="font-bold text-amber-600">{groupDetails.pickup.rooms_remaining}</span>
                      </div>
                      
                      <div className="pt-4 border-t">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm font-medium">Pickup Oranı</span>
                          <span className="text-lg font-bold text-indigo-600">
                            {groupDetails.pickup.pickup_percentage}%
                          </span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-3">
                          <div 
                            className="bg-indigo-600 h-3 rounded-full transition-all duration-500"
                            style={{ width: `${groupDetails.pickup.pickup_percentage}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>İletişim Bilgileri</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Users className="w-4 h-4 text-gray-500" />
                      <span>{groupDetails.block.contact_name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Mail className="w-4 h-4 text-gray-500" />
                      <span>{groupDetails.block.contact_email}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Phone className="w-4 h-4 text-gray-500" />
                      <span>{groupDetails.block.contact_phone}</span>
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="bookings">
                <div className="space-y-3">
                  {groupDetails.bookings.length === 0 ? (
                    <div className="text-center py-8 text-gray-500">
                      Henüz rezervasyon oluşturulmamış
                    </div>
                  ) : (
                    groupDetails.bookings.map((booking, idx) => (
                      <Card key={booking.id}>
                        <CardContent className="pt-4">
                          <div className="flex items-center justify-between">
                            <div>
                              <p className="font-semibold">#{idx + 1} - Misafir ID: {booking.guest_id.substring(0, 8)}</p>
                              <p className="text-sm text-gray-600">
                                {new Date(booking.check_in).toLocaleDateString('tr-TR')} - 
                                {new Date(booking.check_out).toLocaleDateString('tr-TR')}
                              </p>
                            </div>
                            <div className="text-right">
                              <p className="text-sm text-gray-500">Tutar</p>
                              <p className="text-lg font-bold">₺{booking.total_amount}</p>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ))
                  )}
                </div>
              </TabsContent>

              <TabsContent value="rooming">
                <Card>
                  <CardHeader>
                    <CardTitle>Rooming List Yükle</CardTitle>
                    <p className="text-xs text-gray-500 mt-1">
                      Misafir listesini gir; her satır bir oda rezervasyonuna dönüşür.
                      Müsait oda bulunamayan satırlar atlanır ve raporlanır.
                    </p>
                  </CardHeader>
                  <CardContent>
                    <div className="border rounded">
                      <div className="bg-gray-50 px-3 py-2 text-xs font-semibold text-gray-700 grid grid-cols-12 gap-2">
                        <div className="col-span-3">Misafir Adı *</div>
                        <div className="col-span-2">Oda Tipi *</div>
                        <div className="col-span-2">Check-in *</div>
                        <div className="col-span-2">Check-out *</div>
                        <div className="col-span-2">İletişim</div>
                        <div className="col-span-1"></div>
                      </div>
                      {roomingRows.map((row, idx) => (
                        <div key={idx} className="px-3 py-2 border-t grid grid-cols-12 gap-2 items-center">
                          <div className="col-span-3">
                            <Input
                              value={row.guest_name}
                              onChange={(e) => updateRoomingRow(idx, { guest_name: e.target.value })}
                              placeholder="Ad Soyad"
                              className="h-9"
                            />
                          </div>
                          <div className="col-span-2">
                            <Select
                              value={row.room_type}
                              onValueChange={(val) => updateRoomingRow(idx, { room_type: val })}
                            >
                              <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                              <SelectContent>
                                <SelectItem value="Standard">Standard</SelectItem>
                                <SelectItem value="Deluxe">Deluxe</SelectItem>
                                <SelectItem value="Suite">Suite</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                          <div className="col-span-2">
                            <Input
                              type="date"
                              value={row.check_in}
                              onChange={(e) => updateRoomingRow(idx, { check_in: e.target.value })}
                              className="h-9"
                            />
                          </div>
                          <div className="col-span-2">
                            <Input
                              type="date"
                              value={row.check_out}
                              onChange={(e) => updateRoomingRow(idx, { check_out: e.target.value })}
                              className="h-9"
                            />
                          </div>
                          <div className="col-span-2">
                            <Input
                              value={row.email}
                              onChange={(e) => updateRoomingRow(idx, { email: e.target.value })}
                              placeholder="E-posta (ops.)"
                              className="h-9"
                            />
                          </div>
                          <div className="col-span-1 flex justify-end">
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              onClick={() => removeRoomingRow(idx)}
                              className="h-9 w-9 text-red-600 hover:bg-red-50"
                              title="Satırı sil"
                            >
                              <Trash2 className="w-4 h-4" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="flex items-center justify-between mt-4">
                      <Button type="button" variant="outline" size="sm" onClick={addRoomingRow}>
                        <Plus className="w-4 h-4 mr-1" /> Satır Ekle
                      </Button>
                      <Button
                        type="button"
                        onClick={handleUploadRoomingList}
                        disabled={roomingLoading}
                        className="bg-indigo-600 hover:bg-indigo-700"
                      >
                        <UploadCloud className="w-4 h-4 mr-1" />
                        {roomingLoading ? 'Yükleniyor...' : 'Rooming List Yükle'}
                      </Button>
                    </div>

                    <p className="text-xs text-gray-400 mt-3">
                      İpucu: Telefon ve pasaport gibi ek alanları daha sonra misafir kartından
                      güncelleyebilirsin. Burada minimum bilgi yeterli.
                    </p>
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="folio">
                <Card>
                  <CardHeader>
                    <CardTitle>Master Folio Özeti</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {(() => {
                      const bookings = groupDetails.bookings || [];
                      const total = bookings.reduce((s, b) => s + Number(b.total_amount || 0), 0);
                      const nightsTotal = bookings.reduce((s, b) => {
                        const ci = new Date(b.check_in);
                        const co = new Date(b.check_out);
                        const n = Math.max(0, Math.round((co - ci) / 86400000));
                        return s + n;
                      }, 0);
                      const avgPerBooking = bookings.length > 0 ? total / bookings.length : 0;
                      const adr = nightsTotal > 0 ? total / nightsTotal : 0;
                      const totalRooms = groupDetails.pickup?.total_rooms || 0;
                      const pickedUp = groupDetails.pickup?.rooms_picked_up || 0;
                      return (
                        <div className="space-y-4">
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                            <div className="bg-indigo-50 border border-indigo-100 rounded p-3">
                              <div className="text-xs text-indigo-700">Toplam Folio Tutarı</div>
                              <div className="text-2xl font-bold text-indigo-900">₺{total.toFixed(2)}</div>
                            </div>
                            <div className="bg-blue-50 border border-blue-100 rounded p-3">
                              <div className="text-xs text-blue-700">Toplam Geceleme</div>
                              <div className="text-2xl font-bold text-blue-900">{nightsTotal}</div>
                            </div>
                            <div className="bg-green-50 border border-green-100 rounded p-3">
                              <div className="text-xs text-green-700">Ortalama Gecelik (ADR)</div>
                              <div className="text-2xl font-bold text-green-900">₺{adr.toFixed(2)}</div>
                            </div>
                            <div className="bg-amber-50 border border-amber-100 rounded p-3">
                              <div className="text-xs text-amber-700">Pickup / Toplam Oda</div>
                              <div className="text-2xl font-bold text-amber-900">{pickedUp} / {totalRooms}</div>
                            </div>
                          </div>

                          <div className="border rounded">
                            <div className="bg-gray-50 px-3 py-2 text-xs font-semibold text-gray-700 grid grid-cols-12 gap-2">
                              <div className="col-span-1">#</div>
                              <div className="col-span-4">Misafir</div>
                              <div className="col-span-3">Tarih</div>
                              <div className="col-span-2 text-right">Gece</div>
                              <div className="col-span-2 text-right">Tutar</div>
                            </div>
                            {bookings.length === 0 ? (
                              <div className="p-6 text-center text-gray-400 text-sm">
                                Henüz rezervasyon yok
                              </div>
                            ) : (
                              bookings.map((b, idx) => {
                                const ci = new Date(b.check_in);
                                const co = new Date(b.check_out);
                                const n = Math.max(0, Math.round((co - ci) / 86400000));
                                return (
                                  <div key={b.id} className="px-3 py-2 text-sm border-t grid grid-cols-12 gap-2 hover:bg-gray-50">
                                    <div className="col-span-1 text-gray-500">{idx + 1}</div>
                                    <div className="col-span-4 font-mono text-xs">{(b.guest_id || "").slice(0, 12)}</div>
                                    <div className="col-span-3 text-xs text-gray-600">
                                      {ci.toLocaleDateString("tr-TR")} → {co.toLocaleDateString("tr-TR")}
                                    </div>
                                    <div className="col-span-2 text-right">{n}</div>
                                    <div className="col-span-2 text-right font-medium">₺{Number(b.total_amount || 0).toFixed(2)}</div>
                                  </div>
                                );
                              })
                            )}
                            {bookings.length > 0 && (
                              <div className="px-3 py-2 text-sm border-t bg-indigo-50 grid grid-cols-12 gap-2 font-bold">
                                <div className="col-span-8 text-right">TOPLAM</div>
                                <div className="col-span-2 text-right">{nightsTotal}</div>
                                <div className="col-span-2 text-right text-indigo-700">₺{total.toFixed(2)}</div>
                              </div>
                            )}
                          </div>

                          <div className="text-xs text-gray-400">
                            * Master folio: Gruba bağlı tüm rezervasyonların konsolide finansal özeti.
                            Ödeme tahsilatı ana otelin folio modülünden takip edilir.
                          </div>
                        </div>
                      );
                    })()}
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          </DialogContent>
        </Dialog>
      )}

      {/* Statistics Summary */}
      {groups.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-6">
          <Card>
            <CardContent className="pt-6">
              <div className="text-center">
                <p className="text-sm text-gray-500">Toplam Grup</p>
                <p className="text-3xl font-bold text-indigo-600">{groups.length}</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-center">
                <p className="text-sm text-gray-500">Toplam Oda</p>
                <p className="text-3xl font-bold text-blue-600">
                  {groups.reduce((sum, g) => sum + g.total_rooms, 0)}
                </p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-center">
                <p className="text-sm text-gray-500">Alınan Oda</p>
                <p className="text-3xl font-bold text-green-600">
                  {groups.reduce((sum, g) => sum + (g.rooms_picked_up || 0), 0)}
                </p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-center">
                <p className="text-sm text-gray-500">Potansiyel Oda Geliri</p>
                <p className="text-xl font-bold text-amber-600">
                  ₺{groups.reduce((sum, g) => sum + (g.total_rooms * (g.group_rate || 0)), 0).toFixed(0)}
                </p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-center">
                <p className="text-sm text-gray-500">Ort. Pickup</p>
                <p className="text-3xl font-bold text-amber-600">
                  {groups.length > 0 
                    ? Math.round(groups.reduce((sum, g) => sum + ((g.rooms_picked_up || 0) / g.total_rooms * 100), 0) / groups.length)
                    : 0}%
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Release block dialog */}
      <Dialog open={showReleaseDialog} onOpenChange={setShowReleaseDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Bloğu Serbest Bırak</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <p className="text-sm text-gray-600">
              Bu işlem grup bloğundan belirttiğin oda sayısı kadar oda iade eder ve toplam
              blok kontenjanını azaltır. Cutoff tarihi geçmişse genelde kalan tüm odalar
              serbest bırakılır.
            </p>
            <div className="grid grid-cols-3 gap-3 text-center text-sm">
              <div className="bg-gray-50 rounded p-2">
                <div className="text-xs text-gray-500">Toplam</div>
                <div className="font-bold">{groupDetails?.pickup?.total_rooms ?? 0}</div>
              </div>
              <div className="bg-green-50 rounded p-2">
                <div className="text-xs text-green-700">Alındı</div>
                <div className="font-bold text-green-700">{groupDetails?.pickup?.rooms_picked_up ?? 0}</div>
              </div>
              <div className="bg-amber-50 rounded p-2">
                <div className="text-xs text-amber-700">Kalan</div>
                <div className="font-bold text-amber-700">{groupDetails?.pickup?.rooms_remaining ?? 0}</div>
              </div>
            </div>
            <div>
              <Label>Serbest bırakılacak oda sayısı</Label>
              <Input
                type="number"
                min={1}
                max={groupDetails?.pickup?.rooms_remaining ?? 0}
                value={releaseCount}
                onChange={(e) => setReleaseCount(parseInt(e.target.value || '0', 10))}
              />
              <p className="text-xs text-gray-500 mt-1">
                En fazla {groupDetails?.pickup?.rooms_remaining ?? 0} oda iade edilebilir.
              </p>
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" onClick={() => setShowReleaseDialog(false)} className="flex-1">
                İptal
              </Button>
              <Button
                onClick={handleReleaseBlock}
                disabled={releaseLoading || releaseCount <= 0 || releaseCount > (groupDetails?.pickup?.rooms_remaining ?? 0)}
                className="flex-1 bg-amber-600 hover:bg-amber-700"
              >
                {releaseLoading ? 'İşleniyor...' : 'Serbest Bırak'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
    </>
  );
};

export default GroupSales;
