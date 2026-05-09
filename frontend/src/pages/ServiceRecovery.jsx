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
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  AlertTriangle, CheckCircle2, Clock, Home, Plus, Search,
  ArrowUpCircle, ArrowDownCircle, User, DoorOpen, Calendar,
  MessageSquare, Trash2, Edit, Zap, History, Wallet, BellRing, FileText
} from 'lucide-react';

import { confirmDialog, promptDialog } from '@/lib/dialogs';
import { useTranslation } from 'react-i18next';
const CATEGORIES = [
  { value: 'room', label: 'Oda', color: 'bg-blue-100 text-blue-800' },
  { value: 'service', label: 'Hizmet', color: 'bg-indigo-100 text-indigo-800' },
  { value: 'cleanliness', label: 'Temizlik', color: 'bg-green-100 text-green-800' },
  { value: 'fnb', label: 'F&B', color: 'bg-amber-100 text-amber-800' },
  { value: 'noise', label: 'Gürültü', color: 'bg-yellow-100 text-yellow-800' },
  { value: 'maintenance', label: 'Bakım', color: 'bg-gray-100 text-gray-800' },
  { value: 'service_recovery', label: 'Geri Bildirim', color: 'bg-pink-100 text-pink-800' },
];

const SEVERITIES = [
  { value: 'low', label: 'Düşük', color: 'bg-blue-100 text-blue-800', dot: 'bg-blue-500' },
  { value: 'medium', label: 'Orta', color: 'bg-yellow-100 text-yellow-800', dot: 'bg-yellow-500' },
  { value: 'high', label: 'Yüksek', color: 'bg-amber-100 text-amber-800', dot: 'bg-amber-500' },
  { value: 'critical', label: 'Kritik', color: 'bg-red-100 text-red-800', dot: 'bg-red-500' },
];

const STATUSES = [
  { value: 'open', label: 'Açık', color: 'bg-red-100 text-red-700', icon: Clock },
  { value: 'in_progress', label: 'İşlemde', color: 'bg-yellow-100 text-yellow-700', icon: ArrowUpCircle },
  { value: 'escalated', label: 'Yönetimde', color: 'bg-indigo-100 text-indigo-700', icon: AlertTriangle },
  { value: 'resolved', label: 'Çözüldü', color: 'bg-green-100 text-green-700', icon: CheckCircle2 },
];

const DEPARTMENTS = [
  { value: 'front_office', label: 'Ön Büro' },
  { value: 'housekeeping', label: 'Kat Hizmetleri' },
  { value: 'fnb', label: 'F&B' },
  { value: 'maintenance', label: 'Teknik' },
  { value: 'management', label: 'Yönetim' },
];

const COMPENSATIONS = [
  { value: 'none', label: 'Yok' },
  { value: 'free_night', label: 'Bedava Gece' },
  { value: 'room_upgrade', label: 'Oda Upgrade' },
  { value: 'fnb_credit', label: 'F&B Kredisi' },
  { value: 'spa_voucher', label: 'Spa Kuponu' },
  { value: 'discount', label: 'İndirim' },
];

const ESCALATION_TARGETS = [
  { value: 'management', label: 'Yönetim' },
  { value: 'owner', label: 'Otel Sahibi' },
  { value: 'duty_manager', label: 'Nöbetçi Müdür' },
  { value: 'department_head', label: 'Departman Şefi' },
];

const HISTORY_ACTION_LABEL = {
  created: 'Oluşturuldu',
  updated: 'Güncellendi',
  escalated: 'Yönetime iletildi',
  de_escalated: 'Yönetimden geri alındı',
  resolved: 'Çözüldü',
};

const getBadge = (items, value) => items.find(i => i.value === value) || items[0];

const formatDate = (iso) => {
  if (!iso) return '-';
  try {
    return new Date(iso).toLocaleString('tr-TR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
};

const SlaBadge = ({ complaint }) => {
  const { t } = useTranslation();
  if (!complaint?.age_hours && complaint?.age_hours !== 0) return null;
  if (complaint.status === 'resolved') return null;
  const overdue = complaint.is_overdue;
  const hours = complaint.age_hours;
  const label = hours < 1
    ? `${Math.round(hours * 60)} dk`
    : hours < 24
    ? `${Math.round(hours)} sa`
    : `${Math.round(hours / 24)} gün`;
  return (
    <span
      className={`px-2 py-0.5 rounded-full text-[11px] font-medium inline-flex items-center gap-1 ${
        overdue
          ? 'bg-red-100 text-red-700 ring-1 ring-red-300'
          : 'bg-gray-100 text-gray-600'
      }`}
      title={`Çözüm süresi: ${complaint.sla_hours} saat — geçen süre: ${complaint.age_hours} saat`}
    >
      <Clock className="w-3 h-3" />
      {label}
      {overdue && ' (gecikti)'}
    </span>
  );
};

const ServiceRecovery = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [complaints, setComplaints] = useState([]);
  const [stats, setStats] = useState({});
  const [rooms, setRooms] = useState([]);
  const [guests, setGuests] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [auxLoaded, setAuxLoaded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showDetailDialog, setShowDetailDialog] = useState(false);
  const [showResolveDialog, setShowResolveDialog] = useState(false);
  const [showEscalateDialog, setShowEscalateDialog] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [showCompensationDialog, setShowCompensationDialog] = useState(false);
  const [compensationReport, setCompensationReport] = useState(null);
  const [selectedComplaint, setSelectedComplaint] = useState(null);
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterCategory, setFilterCategory] = useState('all');
  const [filterSeverity, setFilterSeverity] = useState('all');
  const [searchText, setSearchText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const [newComplaint, setNewComplaint] = useState({
    booking_id: '', guest_id: '', guest_name: '', room_id: '', room_number: '',
    room_type: '', category: 'room', severity: 'medium', subject: '',
    description: '', assigned_department: 'front_office',
  });

  const [resolveData, setResolveData] = useState({
    resolution_notes: '', compensation_offered: 'none', compensation_amount: 0,
  });

  const [escalateData, setEscalateData] = useState({
    escalated_to: 'management', notes: '',
  });

  const [editData, setEditData] = useState({
    category: 'room', severity: 'medium', assigned_department: 'front_office',
    subject: '', description: '',
  });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const complaintsRes = await axios.get('/service/complaints');
      setComplaints(complaintsRes.data.complaints || []);
      setStats(complaintsRes.data.stats || {});
    } catch {
      toast.error('Şikayetler yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadAuxData = useCallback(async () => {
    if (auxLoaded) return;
    try {
      const [roomsRes, guestsRes, bookingsRes] = await Promise.all([
        axios.get('/service/complaints-rooms'),
        axios.get('/service/complaints-guests'),
        axios.get('/service/complaints-bookings'),
      ]);
      setRooms(roomsRes.data.rooms || []);
      setGuests(guestsRes.data.guests || []);
      setBookings(bookingsRes.data.bookings || []);
      setAuxLoaded(true);
    } catch {
      toast.error('Form verileri yüklenemedi');
    }
  }, [auxLoaded]);

  const openCreateDialog = useCallback(() => {
    loadAuxData();
    setShowCreateDialog(true);
  }, [loadAuxData]);

  useEffect(() => { loadData(); }, [loadData]);

  const refreshSelected = useCallback(async (id) => {
    try {
      const res = await axios.get(`/service/complaints/${id}`);
      setSelectedComplaint(res.data);
    } catch { /* ignore */ }
  }, []);

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
        ...prev, room_id: room.id, room_number: room.room_number, room_type: room.room_type || '',
      }));
    }
  };

  const handleGuestSelect = (guestId) => {
    const guest = guests.find(g => g.id === guestId);
    if (guest) {
      setNewComplaint(prev => ({ ...prev, guest_id: guest.id, guest_name: guest.name }));
    }
  };

  const handleCreateComplaint = async (e) => {
    e.preventDefault();
    if (!newComplaint.subject.trim() || !newComplaint.description.trim()) {
      toast.error('Konu ve açıklama zorunludur');
      return;
    }
    setSubmitting(true);
    try {
      await axios.post('/service/complaints', newComplaint);
      toast.success('Şikayet kaydedildi');
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
      toast.error('Çözüm açıklaması zorunludur');
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        ...resolveData,
        compensation_offered: resolveData.compensation_offered === 'none' ? null : resolveData.compensation_offered,
      };
      const res = await axios.post(`/service/complaints/${selectedComplaint.id}/resolve`, payload);
      toast.success('Şikayet çözüldü, misafire bilgilendirme e-postası gönderildi');
      const folio = res?.data?.folio;
      if (folio?.folio_adjusted) {
        toast.success(
          `Misafirin folyosuna ${Number(folio.amount_credited).toLocaleString('tr-TR')} TL kredi işlendi (yeni bakiye: ${Number(folio.new_balance).toLocaleString('tr-TR')} TL)`,
          { duration: 6000 }
        );
      } else if (folio?.reason && payload.compensation_offered && payload.compensation_amount > 0) {
        toast(`Folyoya işlenmedi: ${folio.reason}`, { icon: 'i', duration: 5000 });
      }
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

  const handleEscalateSubmit = async () => {
    if (!escalateData.notes.trim()) {
      toast.error('Açıklama zorunludur');
      return;
    }
    setSubmitting(true);
    try {
      const res = await axios.post(`/service/complaints/${selectedComplaint.id}/escalate`, escalateData);
      toast.success(res.data?.message || 'Şikayet yönetime iletildi');
      setShowEscalateDialog(false);
      setEscalateData({ escalated_to: 'management', notes: '' });
      await refreshSelected(selectedComplaint.id);
      loadData();
    } catch {
      toast.error('Yönetime iletilemedi');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeEscalate = async () => {
    const notes = await promptDialog({ message: 'Geri alma notu (zorunlu):', defaultValue: '' });
    if (notes === null) return;
    if (!notes.trim()) { toast.error('Not zorunludur'); return; }
    try {
      await axios.post(`/service/complaints/${selectedComplaint.id}/de-escalate`, { notes });
      toast.success('Şikayet geri alındı');
      await refreshSelected(selectedComplaint.id);
      loadData();
    } catch {
      toast.error('Geri alma başarısız');
    }
  };

  const handleStatusChange = async (complaint, newStatus) => {
    try {
      await axios.put(`/service/complaints/${complaint.id}`, { status: newStatus });
      toast.success('Durum güncellendi');
      await refreshSelected(complaint.id);
      loadData();
    } catch {
      toast.error('Güncelleme başarısız');
    }
  };

  const handleDelete = async (complaint) => {
    if (!await confirmDialog({ message: 'Bu şikayeti silmek istediğinize emin misiniz?', variant: 'danger' })) return;
    try {
      await axios.delete(`/service/complaints/${complaint.id}`);
      toast.success('Şikayet silindi');
      setShowDetailDialog(false);
      loadData();
    } catch {
      toast.error('Silme başarısız');
    }
  };

  const handleEditOpen = () => {
    if (!selectedComplaint) return;
    setEditData({
      category: selectedComplaint.category || 'room',
      severity: selectedComplaint.severity || 'medium',
      assigned_department: selectedComplaint.assigned_department || 'front_office',
      subject: selectedComplaint.subject || '',
      description: selectedComplaint.description || '',
    });
    setShowEditDialog(true);
  };

  const handleEditSave = async () => {
    if (!editData.subject.trim() || !editData.description.trim()) {
      toast.error('Konu ve açıklama zorunludur');
      return;
    }
    setSubmitting(true);
    try {
      await axios.put(`/service/complaints/${selectedComplaint.id}`, editData);
      toast.success('Şikayet güncellendi');
      setShowEditDialog(false);
      await refreshSelected(selectedComplaint.id);
      loadData();
    } catch {
      toast.error('Güncelleme başarısız');
    } finally {
      setSubmitting(false);
    }
  };

  const handleAutoEscalate = async () => {
    if (!await confirmDialog({ message: 'Çözüm süresini aşmış tüm açık şikayetler yönetime iletilecek. Devam edilsin mi?', variant: 'danger' })) return;
    try {
      const res = await axios.post('/service/complaints/auto-escalate');
      toast.success(`${res.data.escalated_count || 0} şikayet otomatik olarak yönetime iletildi`);
      loadData();
    } catch {
      toast.error('Toplu iletme başarısız');
    }
  };

  const handleOpenCompensationReport = async () => {
    setShowCompensationDialog(true);
    setCompensationReport(null);
    try {
      const res = await axios.get('/service/complaints/compensation-report');
      setCompensationReport(res.data);
    } catch {
      toast.error('Tazminat raporu alınamadı');
      setCompensationReport({ breakdown: [], totals: { count: 0, amount: 0 } });
    }
  };

  const openDetail = (complaint) => {
    setSelectedComplaint(complaint);
    setShowDetailDialog(true);
  };

  const openResolveDialog = () => {
    setShowDetailDialog(false);
    setResolveData({ resolution_notes: '', compensation_offered: 'none', compensation_amount: 0 });
    setShowResolveDialog(true);
  };

  const openEscalateDialog = () => {
    setShowDetailDialog(false);
    setEscalateData({ escalated_to: 'management', notes: '' });
    setShowEscalateDialog(true);
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
      <>
        <div className="flex items-center justify-center h-96">
          <div className="text-center">
            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-red-600 mx-auto mb-4" />
            <p className="text-gray-500">{t('cm.pages_ServiceRecovery.yukleniyor')}</p>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="p-4 md:p-6 max-w-[1400px] mx-auto space-y-6">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Button variant="outline" size="icon" onClick={() => navigate('/')} className="shrink-0">
              <Home className="w-4 h-4" />
            </Button>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">{t('cm.pages_ServiceRecovery.sikayet_yonetimi')}</h1>
              <p className="text-sm text-gray-500">{t('cm.pages_ServiceRecovery.misafir_sikayetleri_ve_cozum_takibi')}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={handleOpenCompensationReport}>
              <Wallet className="w-4 h-4 mr-2" /> Tazminat Raporu
            </Button>
            <Button
              variant="outline"
              className="text-indigo-700 border-indigo-300 hover:bg-indigo-50"
              onClick={handleAutoEscalate}
              disabled={!stats.overdue}
              title={stats.overdue ? `${stats.overdue} şikayetin çözüm süresi aşıldı` : 'Süresi aşılan şikayet yok'}
            >
              <Zap className="w-4 h-4 mr-2" /> {t('cm.pages_ServiceRecovery.gecikenleri_yonetime_ilet')}
              {stats.overdue ? <span className="ml-2 px-2 py-0.5 bg-red-100 text-red-700 rounded-full text-xs">{stats.overdue}</span> : null}
            </Button>
            <Button onClick={openCreateDialog} className="bg-red-600 hover:bg-red-700">
              <Plus className="w-4 h-4 mr-2" /> {t('cm.pages_ServiceRecovery.yeni_sikayet')}
            </Button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          {[
            { label: 'Toplam', value: stats.total || 0, icon: MessageSquare, color: 'text-gray-600', bg: 'bg-gray-50' },
            { label: 'Açık', value: stats.open || 0, icon: Clock, color: 'text-red-600', bg: 'bg-red-50' },
            { label: 'İşlemde', value: stats.in_progress || 0, icon: ArrowUpCircle, color: 'text-yellow-600', bg: 'bg-yellow-50' },
            { label: 'Yönetimde', value: stats.escalated || 0, icon: AlertTriangle, color: 'text-indigo-600', bg: 'bg-indigo-50' },
            { label: 'Çözüldü', value: stats.resolved || 0, icon: CheckCircle2, color: 'text-green-600', bg: 'bg-green-50' },
            { label: 'Süresi Aşılan', value: stats.overdue || 0, icon: BellRing, color: 'text-red-700', bg: 'bg-red-50' },
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
                <Label className="text-xs text-gray-500 mb-1 block">{t('cm.pages_ServiceRecovery.ara')}</Label>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <Input
                    placeholder={t('cm.pages_ServiceRecovery.misafir_oda_konu')}
                    value={searchText}
                    onChange={e => setSearchText(e.target.value)}
                    className="pl-9"
                  />
                </div>
              </div>
              <div className="w-full md:w-36">
                <Label className="text-xs text-gray-500 mb-1 block">{t('cm.pages_ServiceRecovery.durum')}</Label>
                <Select value={filterStatus} onValueChange={setFilterStatus}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">{t('cm.pages_ServiceRecovery.tumunu_goster')}</SelectItem>
                    {STATUSES.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="w-full md:w-36">
                <Label className="text-xs text-gray-500 mb-1 block">Kategori</Label>
                <Select value={filterCategory} onValueChange={setFilterCategory}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">{t('cm.pages_ServiceRecovery.tumu')}</SelectItem>
                    {CATEGORIES.map(c => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="w-full md:w-36">
                <Label className="text-xs text-gray-500 mb-1 block">{t('cm.pages_ServiceRecovery.onem')}</Label>
                <Select value={filterSeverity} onValueChange={setFilterSeverity}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">{t('cm.pages_ServiceRecovery.tumu_ff12f')}</SelectItem>
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
                <p className="text-gray-500 font-medium">{t('cm.pages_ServiceRecovery.sikayet_bulunamadi')}</p>
                <p className="text-sm text-gray-400 mt-1">{t('cm.pages_ServiceRecovery.filtreleri_degistirmeyi_deneyin')}</p>
              </CardContent>
            </Card>
          ) : (
            filtered.map(complaint => {
              const catBadge = getBadge(CATEGORIES, complaint.category);
              const sevBadge = getBadge(SEVERITIES, complaint.severity);
              const statusBadge = getBadge(STATUSES, complaint.status);
              return (
                <Card
                  key={complaint.id}
                  className={`cursor-pointer hover:shadow-md transition-shadow border-l-4 ${
                    complaint.is_overdue ? 'border-l-red-600 bg-red-50/30' :
                    complaint.severity === 'critical' ? 'border-l-red-500' :
                    complaint.severity === 'high' ? 'border-l-amber-500' :
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
                          {complaint.source === 'guest_qr' && (
                            <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-indigo-100 text-indigo-700">
                              {t('cm.pages_ServiceRecovery.misafir_qr')}
                            </span>
                          )}
                          <SlaBadge complaint={complaint} />
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
                              <DoorOpen className="w-3 h-3" /> {t('cm.pages_ServiceRecovery.oda')} {complaint.room_number}
                              {complaint.room_type && <span className="text-gray-400">({complaint.room_type})</span>}
                            </span>
                          )}
                          <span className="flex items-center gap-1">
                            <Calendar className="w-3 h-3" />
                            {formatDate(complaint.created_at)}
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
              <DialogTitle>{t('cm.pages_ServiceRecovery.yeni_sikayet_kaydi')}</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreateComplaint} className="space-y-4 mt-2">
              <div>
                <Label className="text-sm font-medium">{t('cm.pages_ServiceRecovery.aktif_rezervasyon_otomatik_doldurur')}</Label>
                <Select value={newComplaint.booking_id} onValueChange={handleBookingSelect} disabled={!auxLoaded}>
                  <SelectTrigger><SelectValue placeholder={auxLoaded ? "Rezervasyon seçin..." : "Yükleniyor..."} /></SelectTrigger>
                  <SelectContent>
                    {bookings.map(b => (
                      <SelectItem key={b.id} value={b.id}>
                        {b.guest_name} {t('cm.pages_ServiceRecovery.oda_bec22')} {b.room_number} ({b.room_type}) [{b.status === 'checked_in' ? 'Konaklıyor' : 'Onaylı'}]
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-sm font-medium">{t('cm.pages_ServiceRecovery.oda_e4b47')}</Label>
                  <Select value={newComplaint.room_id} onValueChange={handleRoomSelect} disabled={!auxLoaded}>
                    <SelectTrigger><SelectValue placeholder={auxLoaded ? "Oda seçin..." : "Yükleniyor..."} /></SelectTrigger>
                    <SelectContent>
                      {rooms.map(r => (
                        <SelectItem key={r.id} value={r.id}>
                          {r.room_number} — {r.room_type} (Kat {r.floor})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-sm font-medium">{t('cm.pages_ServiceRecovery.misafir')}</Label>
                  <Select value={newComplaint.guest_id} onValueChange={handleGuestSelect} disabled={!auxLoaded}>
                    <SelectTrigger><SelectValue placeholder={auxLoaded ? "Misafir seçin..." : "Yükleniyor..."} /></SelectTrigger>
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
                  placeholder={t('cm.pages_ServiceRecovery.sikayet_konusu')}
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
                  <Label className="text-sm font-medium">{t('cm.pages_ServiceRecovery.onem_fc622')}</Label>
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
                <Label className="text-sm font-medium">{t('cm.pages_ServiceRecovery.aciklama')}</Label>
                <Textarea
                  value={newComplaint.description}
                  onChange={e => setNewComplaint(p => ({ ...p, description: e.target.value }))}
                  required
                  rows={3}
                  placeholder={t('cm.pages_ServiceRecovery.sikayet_detaylarini_yazin')}
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
          <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{t('cm.pages_ServiceRecovery.sikayet_detayi')}</DialogTitle>
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
                  {selectedComplaint.source === 'guest_qr' && (
                    <span className="px-2 py-1 rounded text-xs font-medium bg-indigo-100 text-indigo-700">
                      {t('cm.pages_ServiceRecovery.misafir_qr_ile_geldi')}
                    </span>
                  )}
                  <SlaBadge complaint={selectedComplaint} />
                </div>

                <div>
                  <Label className="text-xs text-gray-500">Konu</Label>
                  <p className="font-semibold text-gray-900">{selectedComplaint.subject}</p>
                </div>

                <div>
                  <Label className="text-xs text-gray-500">{t('cm.pages_ServiceRecovery.aciklama_1babd')}</Label>
                  <p className="text-sm text-gray-700 bg-gray-50 p-3 rounded">{selectedComplaint.description}</p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-blue-50 p-3 rounded">
                    <Label className="text-xs text-blue-600 flex items-center gap-1"><User className="w-3 h-3" /> {t('cm.pages_ServiceRecovery.misafir_633b8')}</Label>
                    <p className="font-medium text-sm mt-1">{selectedComplaint.guest_name || '-'}</p>
                  </div>
                  <div className="bg-indigo-50 p-3 rounded">
                    <Label className="text-xs text-indigo-600 flex items-center gap-1"><DoorOpen className="w-3 h-3" /> {t('cm.pages_ServiceRecovery.oda_e4b47')}</Label>
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
                    <Label className="text-xs text-gray-500">{t('cm.pages_ServiceRecovery.olusturulma')}</Label>
                    <p className="text-sm">{formatDate(selectedComplaint.created_at)}</p>
                  </div>
                </div>

                {selectedComplaint.status === 'escalated' && (
                  <div className="bg-indigo-50 border border-indigo-200 p-3 rounded space-y-1">
                    <Label className="text-xs text-indigo-700 font-semibold flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" /> {t('cm.pages_ServiceRecovery.yonetime_iletme_bilgileri')}
                    </Label>
                    <p className="text-sm text-indigo-800">
                      <strong>Havale edilen:</strong>{' '}
                      {(ESCALATION_TARGETS.find(t => t.value === selectedComplaint.escalated_to) || {}).label || selectedComplaint.escalated_to}
                    </p>
                    {selectedComplaint.escalation_notes && (
                      <p className="text-sm text-indigo-800"><strong>Not:</strong> {selectedComplaint.escalation_notes}</p>
                    )}
                    {selectedComplaint.escalated_at && (
                      <p className="text-xs text-indigo-600">{formatDate(selectedComplaint.escalated_at)}</p>
                    )}
                  </div>
                )}

                {selectedComplaint.status === 'resolved' && (
                  <div className="bg-green-50 border border-green-200 p-3 rounded space-y-2">
                    <Label className="text-xs text-green-700 font-semibold">{t('cm.pages_ServiceRecovery.cozum')}</Label>
                    <p className="text-sm text-green-800">{selectedComplaint.resolution_notes}</p>
                    {selectedComplaint.compensation_offered && (
                      <p className="text-xs text-green-600">
                        Tazminat: {(COMPENSATIONS.find(c => c.value === selectedComplaint.compensation_offered) || {}).label}
                        {selectedComplaint.compensation_amount > 0 && ` (${selectedComplaint.compensation_amount} TL)`}
                      </p>
                    )}
                    {selectedComplaint.resolved_at && (
                      <p className="text-xs text-green-500">{t('cm.pages_ServiceRecovery.cozum_zamani')} {formatDate(selectedComplaint.resolved_at)}</p>
                    )}
                  </div>
                )}

                {Array.isArray(selectedComplaint.history) && selectedComplaint.history.length > 0 && (
                  <div className="border rounded p-3 bg-gray-50">
                    <Label className="text-xs text-gray-700 font-semibold flex items-center gap-1 mb-2">
                      <History className="w-3 h-3" /> {t('cm.pages_ServiceRecovery.gecmis')}{selectedComplaint.history.length})
                    </Label>
                    <ol className="space-y-2">
                      {selectedComplaint.history.map((h, i) => (
                        <li key={i} className="text-xs flex items-start gap-2 border-l-2 border-gray-300 pl-2">
                          <div className="flex-1">
                            <span className="font-medium text-gray-800">{HISTORY_ACTION_LABEL[h.action] || h.action}</span>
                            {h.actor_name && <span className="text-gray-500"> — {h.actor_name}</span>}
                            {h.escalated_to && (
                              <span className="text-indigo-600">
                                {' '}→ {(ESCALATION_TARGETS.find(t => t.value === h.escalated_to) || {}).label || h.escalated_to}
                              </span>
                            )}
                            {h.notes && <p className="text-gray-600 mt-0.5">{h.notes}</p>}
                            {h.changes && (
                              <p className="text-gray-600 mt-0.5">
                                {t('cm.pages_ServiceRecovery.degisen')} {Object.keys(h.changes).join(', ')}
                              </p>
                            )}
                          </div>
                          <span className="text-gray-400 whitespace-nowrap">{formatDate(h.at)}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}

                <div className="flex gap-2 flex-wrap pt-2 border-t">
                  {selectedComplaint.status !== 'resolved' && (
                    <>
                      <Button size="sm" className="bg-green-600 hover:bg-green-700" onClick={openResolveDialog}>
                        <CheckCircle2 className="w-3 h-3 mr-1" /> {t('cm.pages_ServiceRecovery.coz')}
                      </Button>
                      {selectedComplaint.status === 'open' && (
                        <Button size="sm" variant="outline" onClick={() => handleStatusChange(selectedComplaint, 'in_progress')}>
                          <ArrowUpCircle className="w-3 h-3 mr-1" /> {t('cm.pages_ServiceRecovery.isleme_al')}
                        </Button>
                      )}
                      {selectedComplaint.status !== 'escalated' && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="text-indigo-700 border-indigo-300 hover:bg-indigo-50"
                          onClick={openEscalateDialog}
                        >
                          <AlertTriangle className="w-3 h-3 mr-1" /> {t('cm.pages_ServiceRecovery.yonetime_ilet')}
                        </Button>
                      )}
                      {selectedComplaint.status === 'escalated' && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="text-amber-700 border-amber-300 hover:bg-amber-50"
                          onClick={handleDeEscalate}
                        >
                          <ArrowDownCircle className="w-3 h-3 mr-1" /> Geri Al
                        </Button>
                      )}
                      <Button size="sm" variant="outline" onClick={handleEditOpen}>
                        <Edit className="w-3 h-3 mr-1" /> {t('cm.pages_ServiceRecovery.duzenle')}
                      </Button>
                    </>
                  )}
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-red-600 border-red-200 hover:bg-red-50 ml-auto"
                    onClick={() => handleDelete(selectedComplaint)}
                  >
                    <Trash2 className="w-3 h-3 mr-1" /> {t('cm.pages_ServiceRecovery.sil')}
                  </Button>
                </div>
              </div>
            )}
          </DialogContent>
        </Dialog>

        {/* Escalate Dialog */}
        <Dialog open={showEscalateDialog} onOpenChange={setShowEscalateDialog}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>{t('cm.pages_ServiceRecovery.sikayeti_yonetime_ilet')}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 mt-2">
              <p className="text-sm text-gray-600">
                {t('cm.pages_ServiceRecovery.bu_sikayet_sectiginiz_kisiye_havale_edil')}
              </p>
              <div>
                <Label className="text-sm font-medium">Kime havale edilsin?</Label>
                <Select
                  value={escalateData.escalated_to}
                  onValueChange={v => setEscalateData(p => ({ ...p, escalated_to: v }))}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ESCALATION_TARGETS.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-sm font-medium">{t('cm.pages_ServiceRecovery.aciklama_bdb34')}</Label>
                <Textarea
                  value={escalateData.notes}
                  onChange={e => setEscalateData(p => ({ ...p, notes: e.target.value }))}
                  rows={3}
                  placeholder={t('cm.pages_ServiceRecovery.neden_yonetime_iletiyorsunuz_ne_yapilmas')}
                />
              </div>
              <Button
                className="w-full bg-indigo-600 hover:bg-indigo-700"
                onClick={handleEscalateSubmit}
                disabled={submitting}
              >
                {submitting ? 'Gönderiliyor...' : 'Yönetime İlet'}
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        {/* Edit Dialog */}
        <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>{t('cm.pages_ServiceRecovery.sikayeti_duzenle')}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 mt-2">
              <div>
                <Label className="text-sm font-medium">Konu *</Label>
                <Input
                  value={editData.subject}
                  onChange={e => setEditData(p => ({ ...p, subject: e.target.value }))}
                />
              </div>
              <div>
                <Label className="text-sm font-medium">{t('cm.pages_ServiceRecovery.aciklama_bdb34')}</Label>
                <Textarea
                  value={editData.description}
                  onChange={e => setEditData(p => ({ ...p, description: e.target.value }))}
                  rows={3}
                />
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <Label className="text-sm font-medium">Kategori</Label>
                  <Select value={editData.category} onValueChange={v => setEditData(p => ({ ...p, category: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {CATEGORIES.map(c => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-sm font-medium">{t('cm.pages_ServiceRecovery.onem_fc622')}</Label>
                  <Select value={editData.severity} onValueChange={v => setEditData(p => ({ ...p, severity: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {SEVERITIES.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-sm font-medium">Departman</Label>
                  <Select value={editData.assigned_department} onValueChange={v => setEditData(p => ({ ...p, assigned_department: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {DEPARTMENTS.map(d => <SelectItem key={d.value} value={d.value}>{d.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <Button className="w-full" onClick={handleEditSave} disabled={submitting}>
                {submitting ? 'Kaydediliyor...' : 'Kaydet'}
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        {/* Resolve Dialog */}
        <Dialog open={showResolveDialog} onOpenChange={setShowResolveDialog}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>{t('cm.pages_ServiceRecovery.sikayeti_coz')}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 mt-2">
              <p className="text-xs text-gray-500">
                {t('cm.pages_ServiceRecovery.cozum_kaydedildiginde_misafire_otomatik_')}
              </p>
              <div>
                <Label className="text-sm font-medium">{t('cm.pages_ServiceRecovery.cozum_aciklamasi')}</Label>
                <Textarea
                  value={resolveData.resolution_notes}
                  onChange={e => setResolveData(p => ({ ...p, resolution_notes: e.target.value }))}
                  rows={3}
                  placeholder={t('cm.pages_ServiceRecovery.sorunu_nasil_cozdunuz')}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-sm font-medium">Tazminat</Label>
                  <Select
                    value={resolveData.compensation_offered}
                    onValueChange={v => setResolveData(p => ({ ...p, compensation_offered: v }))}
                  >
                    <SelectTrigger><SelectValue placeholder={t('cm.pages_ServiceRecovery.secin')} /></SelectTrigger>
                    <SelectContent>
                      {COMPENSATIONS.map(c => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-sm font-medium">{t('cm.pages_ServiceRecovery.tutar_tl')}</Label>
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
                {submitting ? 'Kaydediliyor...' : 'Çözümü Kaydet'}
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        {/* Compensation Report Dialog */}
        <Dialog open={showCompensationDialog} onOpenChange={setShowCompensationDialog}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <FileText className="w-5 h-5" /> Tazminat Raporu
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-3 mt-2">
              {!compensationReport ? (
                <p className="text-sm text-gray-500 text-center py-6">{t('cm.pages_ServiceRecovery.yukleniyor_4deb0')}</p>
              ) : compensationReport.breakdown.length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-6">{t('cm.pages_ServiceRecovery.henuz_verilmis_tazminat_yok')}</p>
              ) : (
                <>
                  <div className="bg-blue-50 p-3 rounded text-center">
                    <p className="text-xs text-blue-600">{t('cm.pages_ServiceRecovery.toplam_tazminat')}</p>
                    <p className="text-2xl font-bold text-blue-900">{compensationReport.totals.amount.toLocaleString('tr-TR')} TL</p>
                    <p className="text-xs text-blue-500">{compensationReport.totals.count} {t('cm.pages_ServiceRecovery.sikayetten')}</p>
                  </div>
                  <div className="space-y-2">
                    {compensationReport.breakdown.map(b => (
                      <div key={b.type} className="flex items-center justify-between p-2 bg-gray-50 rounded">
                        <div>
                          <p className="text-sm font-medium">{b.label}</p>
                          <p className="text-xs text-gray-500">{b.count} adet</p>
                        </div>
                        <p className="text-sm font-bold">{(b.total_amount || 0).toLocaleString('tr-TR')} TL</p>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </>
  );
};

export default ServiceRecovery;
