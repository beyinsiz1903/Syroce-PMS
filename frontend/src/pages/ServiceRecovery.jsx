import React, { useState, useEffect, useCallback } from 'react';
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
import {
  AlertTriangle, CheckCircle2, Clock, XCircle, Home, Plus, Search,
  ArrowUpCircle, User, DoorOpen, Calendar, Filter, ChevronDown,
  ChevronUp, MessageSquare, Trash2, Edit, Eye
} from 'lucide-react';
import Layout from '@/components/Layout';

const CATEGORIES = [
  { value: 'room', label: 'Oda', color: 'bg-blue-100 text-blue-800' },
  { value: 'service', label: 'Hizmet', color: 'bg-purple-100 text-purple-800' },
  { value: 'cleanliness', label: 'Temizlik', color: 'bg-green-100 text-green-800' },
  { value: 'fnb', label: 'F&B', color: 'bg-orange-100 text-orange-800' },
  { value: 'noise', label: 'Gürültü', color: 'bg-yellow-100 text-yellow-800' },
  { value: 'maintenance', label: 'Bakım', color: 'bg-gray-100 text-gray-800' },
];

const SEVERITIES = [
  { value: 'low', label: 'Dusuk', color: 'bg-blue-100 text-blue-800', dot: 'bg-blue-500' },
  { value: 'medium', label: 'Orta', color: 'bg-yellow-100 text-yellow-800', dot: 'bg-yellow-500' },
  { value: 'high', label: 'Yuksek', color: 'bg-orange-100 text-orange-800', dot: 'bg-orange-500' },
  { value: 'critical', label: 'Kritik', color: 'bg-red-100 text-red-800', dot: 'bg-red-500' },
];

const STATUSES = [
  { value: 'open', label: 'Açık', color: 'bg-red-100 text-red-700', icon: Clock },
  { value: 'in_progress', label: 'İşlemde', color: 'bg-yellow-100 text-yellow-700', icon: ArrowUpCircle },
  { value: 'escalated', label: 'Eskalasyon', color: 'bg-purple-100 text-purple-700', icon: AlertTriangle },
  { value: 'resolved', label: 'Çözüldü', color: 'bg-green-100 text-green-700', icon: CheckCircle2 },
];

const DEPARTMENTS = [
  { value: 'front_office', label: 'On Buro' },
  { value: 'housekeeping', label: 'Housekeeping' },
  { value: 'fnb', label: 'F&B' },
  { value: 'maintenance', label: 'Teknik' },
  { value: 'management', label: 'Yönetim' },
];

const COMPENSATIONS = [
  { value: 'none', label: 'Yok' },
  { value: 'free_night', label: 'Bedava Gece' },
  { value: 'room_upgrade', label: 'Oda Upgrade' },
  { value: 'fnb_credit', label: 'F&B Credit' },
  { value: 'spa_voucher', label: 'Spa Voucher' },
  { value: 'discount', label: 'Indirim' },
];

const getBadge = (items, value) => items.find(i => i.value === value) || items[0];

const ServiceRecovery = ({ user, tenant, onLogout }) => {
  const navigate = useNavigate();
  const [complaints, setComplaints] = useState([]);
  const [stats, setStats] = useState({});
  const [rooms, setRooms] = useState([]);
  const [guests, setGuests] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showDetailDialog, setShowDetailDialog] = useState(false);
  const [showResolveDialog, setShowResolveDialog] = useState(false);
  const [selectedComplaint, setSelectedComplaint] = useState(null);
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterCategory, setFilterCategory] = useState('all');
  const [filterSeverity, setFilterSeverity] = useState('all');
  const [searchText, setSearchText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const [newComplaint, setNewComplaint] = useState({
    booking_id: '',
    guest_id: '',
    guest_name: '',
    room_id: '',
    room_number: '',
    room_type: '',
    category: 'room',
    severity: 'medium',
    subject: '',
    description: '',
    assigned_department: 'front_office',
  });

  const [resolveData, setResolveData] = useState({
    resolution_notes: '',
    compensation_offered: 'none',
    compensation_amount: 0,
  });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [complaintsRes, roomsRes, guestsRes, bookingsRes] = await Promise.all([
        axios.get('/service/complaints'),
        axios.get('/service/complaints-rooms'),
        axios.get('/service/complaints-guests'),
        axios.get('/service/complaints-bookings'),
      ]);
      setComplaints(complaintsRes.data.complaints || []);
      setStats(complaintsRes.data.stats || {});
      setRooms(roomsRes.data.rooms || []);
      setGuests(guestsRes.data.guests || []);
      setBookings(bookingsRes.data.bookings || []);
    } catch (error) {
      toast.error('Veriler yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleBookingSelect = (bookingId) => {
    const booking = bookings.find(b => b.id === bookingId);
    if (booking) {
      setNewComplaint(prev => ({
        ...prev,
        booking_id: booking.id,
        guest_id: booking.guest_id || '',
        guest_name: booking.guest_name || '',
        room_id: booking.room_id || '',
        room_number: booking.room_number || '',
        room_type: booking.room_type || '',
      }));
    }
  };

  const handleRoomSelect = (roomId) => {
    const room = rooms.find(r => r.id === roomId);
    if (room) {
      setNewComplaint(prev => ({
        ...prev,
        room_id: room.id,
        room_number: room.room_number,
        room_type: room.room_type || '',
      }));
    }
  };

  const handleGuestSelect = (guestId) => {
    const guest = guests.find(g => g.id === guestId);
    if (guest) {
      setNewComplaint(prev => ({
        ...prev,
        guest_id: guest.id,
        guest_name: guest.name,
      }));
    }
  };

  const handleCreateComplaint = async (e) => {
    e.preventDefault();
    if (!newComplaint.subject.trim() || !newComplaint.description.trim()) {
      toast.error('Konu ve aciklama zorunludur');
      return;
    }
    setSubmitting(true);
    try {
      await axios.post('/service/complaints', newComplaint);
      toast.success('Şikayet başarıyla kaydedildi');
      setShowCreateDialog(false);
      setNewComplaint({
        booking_id: '', guest_id: '', guest_name: '', room_id: '', room_number: '',
        room_type: '', category: 'room', severity: 'medium', subject: '',
        description: '', assigned_department: 'front_office',
      });
      loadData();
    } catch {
      toast.error('Şikayet kaydedilemedi');
    } finally {
      setSubmitting(false);
    }
  };

  const handleResolve = async () => {
    if (!resolveData.resolution_notes.trim()) {
      toast.error('Cozum aciklamasi zorunludur');
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        ...resolveData,
        compensation_offered: resolveData.compensation_offered === 'none' ? null : resolveData.compensation_offered,
      };
      await axios.post(`/service/complaints/${selectedComplaint.id}/resolve`, payload);
      toast.success('Şikayet başarıyla çözüldü');
      setShowResolveDialog(false);
      setShowDetailDialog(false);
      setResolveData({ resolution_notes: '', compensation_offered: 'none', compensation_amount: 0 });
      loadData();
    } catch {
      toast.error('İşlem başarısız');
    } finally {
      setSubmitting(false);
    }
  };

  const handleEscalate = async (complaint) => {
    try {
      await axios.post(`/service/complaints/${complaint.id}/escalate`, {
        escalated_to: 'management',
        notes: 'Yönetim tarafindan incelenmesi gerekiyor',
      });
      toast.success('Şikayet yönetime eskalasyon edildi');
      loadData();
    } catch {
      toast.error('Eskalasyon başarısız');
    }
  };

  const handleStatusChange = async (complaint, newStatus) => {
    try {
      await axios.put(`/service/complaints/${complaint.id}`, { status: newStatus });
      toast.success('Durum güncellendi');
      loadData();
    } catch {
      toast.error('Güncelleme başarısız');
    }
  };

  const handleDelete = async (complaint) => {
    if (!window.confirm('Bu şikayeti silmek istediğinize emin misiniz?')) return;
    try {
      await axios.delete(`/service/complaints/${complaint.id}`);
      toast.success('Şikayet silindi');
      setShowDetailDialog(false);
      loadData();
    } catch {
      toast.error('Silme başarısız');
    }
  };

  const openDetail = (complaint) => {
    setSelectedComplaint(complaint);
    setShowDetailDialog(true);
  };

  const filtered = complaints.filter(c => {
    if (filterStatus !== 'all' && c.status !== filterStatus) return false;
    if (filterCategory !== 'all' && c.category !== filterCategory) return false;
    if (filterSeverity !== 'all' && c.severity !== filterSeverity) return false;
    if (searchText) {
      const q = searchText.toLowerCase();
      return (
        (c.subject || '').toLowerCase().includes(q) ||
        (c.guest_name || '').toLowerCase().includes(q) ||
        (c.room_number || '').toLowerCase().includes(q) ||
        (c.description || '').toLowerCase().includes(q)
      );
    }
    return true;
  });

  if (loading) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout}>
        <div className="flex items-center justify-center h-96">
          <div className="text-center">
            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-red-600 mx-auto mb-4" />
            <p className="text-gray-500">Yükleniyor...</p>
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout}>
    <div className="p-4 md:p-6 max-w-[1400px] mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Button variant="outline" size="icon" onClick={() => navigate('/')} className="shrink-0">
            <Home className="w-4 h-4" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Şikayet Yönetimi</h1>
            <p className="text-sm text-gray-500">Misafir sikayetleri ve cozum takibi</p>
          </div>
        </div>
        <Button onClick={() => setShowCreateDialog(true)} className="bg-red-600 hover:bg-red-700">
          <Plus className="w-4 h-4 mr-2" /> Yeni Şikayet
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          { label: 'Toplam', value: stats.total || 0, icon: MessageSquare, color: 'text-gray-600', bg: 'bg-gray-50' },
          { label: 'Açık', value: stats.open || 0, icon: Clock, color: 'text-red-600', bg: 'bg-red-50' },
          { label: 'İşlemde', value: stats.in_progress || 0, icon: ArrowUpCircle, color: 'text-yellow-600', bg: 'bg-yellow-50' },
          { label: 'Çözüldü', value: stats.resolved || 0, icon: CheckCircle2, color: 'text-green-600', bg: 'bg-green-50' },
          { label: 'Kritik', value: stats.critical || 0, icon: AlertTriangle, color: 'text-red-700', bg: 'bg-red-50' },
        ].map((s, i) => (
          <Card key={i} className={s.bg}>
            <CardContent className="pt-4 pb-3 text-center">
              <s.icon className={`w-6 h-6 ${s.color} mx-auto mb-1`} />
              <p className="text-2xl font-bold">{s.value}</p>
              <p className="text-xs text-gray-500">{s.label}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-4 pb-3">
          <div className="flex flex-col md:flex-row gap-3 items-end">
            <div className="flex-1 min-w-0">
              <Label className="text-xs text-gray-500 mb-1 block">Ara</Label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <Input
                  placeholder="Misafir, oda, konu..."
                  value={searchText}
                  onChange={e => setSearchText(e.target.value)}
                  className="pl-9"
                />
              </div>
            </div>
            <div className="w-full md:w-36">
              <Label className="text-xs text-gray-500 mb-1 block">Durum</Label>
              <Select value={filterStatus} onValueChange={setFilterStatus}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Tumunu Goster</SelectItem>
                  {STATUSES.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="w-full md:w-36">
              <Label className="text-xs text-gray-500 mb-1 block">Kategori</Label>
              <Select value={filterCategory} onValueChange={setFilterCategory}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Tumu</SelectItem>
                  {CATEGORIES.map(c => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="w-full md:w-36">
              <Label className="text-xs text-gray-500 mb-1 block">Onem</Label>
              <Select value={filterSeverity} onValueChange={setFilterSeverity}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Tumu</SelectItem>
                  {SEVERITIES.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Complaint List */}
      <div className="space-y-3">
        {filtered.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <MessageSquare className="w-12 h-12 text-gray-300 mx-auto mb-3" />
              <p className="text-gray-500 font-medium">Şikayet bulunamadı</p>
              <p className="text-sm text-gray-400 mt-1">Filtreleri değiştirmeyi deneyin</p>
            </CardContent>
          </Card>
        ) : (
          filtered.map(complaint => {
            const catBadge = getBadge(CATEGORIES, complaint.category);
            const sevBadge = getBadge(SEVERITIES, complaint.severity);
            const statusBadge = getBadge(STATUSES, complaint.status);
            const StatusIcon = statusBadge.icon || Clock;

            return (
              <Card
                key={complaint.id}
                className={`cursor-pointer hover:shadow-md transition-shadow border-l-4 ${
                  complaint.severity === 'critical' ? 'border-l-red-500' :
                  complaint.severity === 'high' ? 'border-l-orange-500' :
                  complaint.severity === 'medium' ? 'border-l-yellow-500' :
                  'border-l-blue-400'
                }`}
                onClick={() => openDetail(complaint)}
              >
                <CardContent className="py-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <h3 className="font-semibold text-gray-900 truncate">{complaint.subject || 'Şikayet'}</h3>
                        <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${statusBadge.color}`}>
                          {statusBadge.label}
                        </span>
                      </div>
                      <p className="text-sm text-gray-600 line-clamp-1 mb-2">{complaint.description}</p>
                      <div className="flex items-center gap-4 text-xs text-gray-500 flex-wrap">
                        {complaint.guest_name && (
                          <span className="flex items-center gap-1">
                            <User className="w-3 h-3" /> {complaint.guest_name}
                          </span>
                        )}
                        {complaint.room_number && (
                          <span className="flex items-center gap-1">
                            <DoorOpen className="w-3 h-3" /> Oda {complaint.room_number}
                            {complaint.room_type && <span className="text-gray-400">({complaint.room_type})</span>}
                          </span>
                        )}
                        <span className="flex items-center gap-1">
                          <Calendar className="w-3 h-3" />
                          {new Date(complaint.created_at).toLocaleDateString('tr-TR', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className={`px-2 py-0.5 rounded text-[11px] font-medium ${catBadge.color}`}>
                        {catBadge.label}
                      </span>
                      <span className={`px-2 py-0.5 rounded text-[11px] font-medium ${sevBadge.color}`}>
                        {sevBadge.label}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })
        )}
      </div>

      {/* Create Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Yeni Şikayet Kaydi</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreateComplaint} className="space-y-4 mt-2">
            <div>
              <Label className="text-sm font-medium">Aktif Rezervasyon (Otomatik Doldurur)</Label>
              <Select
                value={newComplaint.booking_id}
                onValueChange={handleBookingSelect}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Rezervasyon seçin..." />
                </SelectTrigger>
                <SelectContent>
                  {bookings.map(b => (
                    <SelectItem key={b.id} value={b.id}>
                      {b.guest_name} - Oda {b.room_number} ({b.room_type}) [{b.status === 'checked_in' ? 'Konaklıyor' : 'Onaylı'}]
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-sm font-medium">Oda</Label>
                <Select value={newComplaint.room_id} onValueChange={handleRoomSelect}>
                  <SelectTrigger>
                    <SelectValue placeholder="Oda seçin..." />
                  </SelectTrigger>
                  <SelectContent>
                    {rooms.map(r => (
                      <SelectItem key={r.id} value={r.id}>
                        {r.room_number} - {r.room_type} (Kat {r.floor})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-sm font-medium">Misafir</Label>
                <Select value={newComplaint.guest_id} onValueChange={handleGuestSelect}>
                  <SelectTrigger>
                    <SelectValue placeholder="Misafir seçin..." />
                  </SelectTrigger>
                  <SelectContent>
                    {guests.map(g => (
                      <SelectItem key={g.id} value={g.id}>
                        {g.name} {g.vip_status ? '(VIP)' : ''}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div>
              <Label className="text-sm font-medium">Konu *</Label>
              <Input
                value={newComplaint.subject}
                onChange={e => setNewComplaint(p => ({ ...p, subject: e.target.value }))}
                required
                placeholder="Şikayet konusu..."
              />
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label className="text-sm font-medium">Kategori</Label>
                <Select value={newComplaint.category} onValueChange={v => setNewComplaint(p => ({ ...p, category: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {CATEGORIES.map(c => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-sm font-medium">Onem</Label>
                <Select value={newComplaint.severity} onValueChange={v => setNewComplaint(p => ({ ...p, severity: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {SEVERITIES.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-sm font-medium">Departman</Label>
                <Select value={newComplaint.assigned_department} onValueChange={v => setNewComplaint(p => ({ ...p, assigned_department: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {DEPARTMENTS.map(d => <SelectItem key={d.value} value={d.value}>{d.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div>
              <Label className="text-sm font-medium">Aciklama *</Label>
              <Textarea
                value={newComplaint.description}
                onChange={e => setNewComplaint(p => ({ ...p, description: e.target.value }))}
                required
                rows={3}
                placeholder="Şikayet detaylarını yazın..."
              />
            </div>

            <Button type="submit" className="w-full bg-red-600 hover:bg-red-700" disabled={submitting}>
              {submitting ? 'Kaydediliyor...' : 'Şikayeti Kaydet'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Detail Dialog */}
      <Dialog open={showDetailDialog} onOpenChange={setShowDetailDialog}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Şikayet Detayı</DialogTitle>
          </DialogHeader>
          {selectedComplaint && (
            <div className="space-y-4 mt-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`px-2 py-1 rounded-full text-xs font-semibold ${getBadge(STATUSES, selectedComplaint.status).color}`}>
                  {getBadge(STATUSES, selectedComplaint.status).label}
                </span>
                <span className={`px-2 py-1 rounded text-xs font-medium ${getBadge(SEVERITIES, selectedComplaint.severity).color}`}>
                  {getBadge(SEVERITIES, selectedComplaint.severity).label}
                </span>
                <span className={`px-2 py-1 rounded text-xs font-medium ${getBadge(CATEGORIES, selectedComplaint.category).color}`}>
                  {getBadge(CATEGORIES, selectedComplaint.category).label}
                </span>
              </div>

              <div>
                <Label className="text-xs text-gray-500">Konu</Label>
                <p className="font-semibold text-gray-900">{selectedComplaint.subject}</p>
              </div>

              <div>
                <Label className="text-xs text-gray-500">Aciklama</Label>
                <p className="text-sm text-gray-700 bg-gray-50 p-3 rounded">{selectedComplaint.description}</p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="bg-blue-50 p-3 rounded">
                  <Label className="text-xs text-blue-600 flex items-center gap-1"><User className="w-3 h-3" /> Misafir</Label>
                  <p className="font-medium text-sm mt-1">{selectedComplaint.guest_name || '-'}</p>
                </div>
                <div className="bg-purple-50 p-3 rounded">
                  <Label className="text-xs text-purple-600 flex items-center gap-1"><DoorOpen className="w-3 h-3" /> Oda</Label>
                  <p className="font-medium text-sm mt-1">
                    {selectedComplaint.room_number ? `${selectedComplaint.room_number} (${selectedComplaint.room_type || ''})` : '-'}
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs text-gray-500">Departman</Label>
                  <p className="text-sm font-medium">{(DEPARTMENTS.find(d => d.value === selectedComplaint.assigned_department) || {}).label || '-'}</p>
                </div>
                <div>
                  <Label className="text-xs text-gray-500">Olusturulma</Label>
                  <p className="text-sm">{new Date(selectedComplaint.created_at).toLocaleString('tr-TR')}</p>
                </div>
              </div>

              {selectedComplaint.status === 'resolved' && (
                <div className="bg-green-50 border border-green-200 p-3 rounded space-y-2">
                  <Label className="text-xs text-green-700 font-semibold">Cozum</Label>
                  <p className="text-sm text-green-800">{selectedComplaint.resolution_notes}</p>
                  {selectedComplaint.compensation_offered && (
                    <p className="text-xs text-green-600">
                      Tazminat: {(COMPENSATIONS.find(c => c.value === selectedComplaint.compensation_offered) || {}).label}
                      {selectedComplaint.compensation_amount > 0 && ` (${selectedComplaint.compensation_amount} TL)`}
                    </p>
                  )}
                  {selectedComplaint.resolved_at && (
                    <p className="text-xs text-green-500">Cozum: {new Date(selectedComplaint.resolved_at).toLocaleString('tr-TR')}</p>
                  )}
                </div>
              )}

              <div className="flex gap-2 flex-wrap pt-2 border-t">
                {selectedComplaint.status !== 'resolved' && (
                  <>
                    <Button
                      size="sm"
                      className="bg-green-600 hover:bg-green-700"
                      onClick={() => {
                        setResolveData({ resolution_notes: '', compensation_offered: 'none', compensation_amount: 0 });
                        setShowResolveDialog(true);
                      }}
                    >
                      <CheckCircle2 className="w-3 h-3 mr-1" /> Coz
                    </Button>
                    {selectedComplaint.status === 'open' && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleStatusChange(selectedComplaint, 'in_progress')}
                      >
                        <ArrowUpCircle className="w-3 h-3 mr-1" /> Isleme Al
                      </Button>
                    )}
                    {selectedComplaint.status !== 'escalated' && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-purple-700 border-purple-300 hover:bg-purple-50"
                        onClick={() => handleEscalate(selectedComplaint)}
                      >
                        <AlertTriangle className="w-3 h-3 mr-1" /> Eskalasyon
                      </Button>
                    )}
                  </>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  className="text-red-600 border-red-200 hover:bg-red-50 ml-auto"
                  onClick={() => handleDelete(selectedComplaint)}
                >
                  <Trash2 className="w-3 h-3 mr-1" /> Sil
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Resolve Dialog */}
      <Dialog open={showResolveDialog} onOpenChange={setShowResolveDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Şikayeti Çöz</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-2">
            <div>
              <Label className="text-sm font-medium">Cozum Aciklamasi *</Label>
              <Textarea
                value={resolveData.resolution_notes}
                onChange={e => setResolveData(p => ({ ...p, resolution_notes: e.target.value }))}
                rows={3}
                placeholder="Sorunu nasil cozdunuz?"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-sm font-medium">Tazminat</Label>
                <Select
                  value={resolveData.compensation_offered}
                  onValueChange={v => setResolveData(p => ({ ...p, compensation_offered: v }))}
                >
                  <SelectTrigger><SelectValue placeholder="Secin..." /></SelectTrigger>
                  <SelectContent>
                    {COMPENSATIONS.map(c => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-sm font-medium">Tutar (TL)</Label>
                <Input
                  type="number"
                  value={resolveData.compensation_amount}
                  onChange={e => setResolveData(p => ({ ...p, compensation_amount: parseFloat(e.target.value) || 0 }))}
                  min={0}
                />
              </div>
            </div>
            <Button
              className="w-full bg-green-600 hover:bg-green-700"
              onClick={handleResolve}
              disabled={submitting}
            >
              {submitting ? 'Kaydediliyor...' : 'Cozumu Kaydet'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
    </Layout>
  );
};

export default ServiceRecovery;
