import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { Home, UserCheck, Crown, Users, Clock, BedDouble, AlertCircle, Calendar, LogIn, ScanLine, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import QuickIdScanDialog from '@/components/QuickIdScanDialog';
import IdPhotoViewerButton from '@/components/IdPhotoViewerButton';

import { confirmDialog } from '@/lib/dialogs';
const ArrivalList = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [arrivals, setArrivals] = useState([]);
  const [upcoming, setUpcoming] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [scanBookingId, setScanBookingId] = useState(null);

  const applyScanToBooking = async (bookingId, doc) => {
    try {
      const patch = {};
      if (doc.first_name) patch.guest_first_name = doc.first_name;
      if (doc.last_name) patch.guest_last_name = doc.last_name;
      if (doc.id_number || doc.document_number) patch.guest_id_number = doc.id_number || doc.document_number;
      if (doc.document_type) patch.guest_id_type = doc.document_type;
      if (doc.nationality) patch.guest_nationality = doc.nationality;
      if (doc.birth_date) patch.guest_birth_date = doc.birth_date;
      await axios.patch(`/bookings/${bookingId}/guest-info`, patch).catch(() => {});
      toast.success('Kimlik bilgileri rezervasyona aktarıldı');
      loadTodayArrivals();
    } catch (e) {
      toast.warning('Bilgiler aktarılamadı, manuel güncelleyebilirsiniz');
    }
  };

  useEffect(() => {
    loadTodayArrivals();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  const localISODate = (d) => {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  };

  const loadTodayArrivals = async () => {
    setLoading(true);
    try {
      const today = localISODate(new Date());
      const response = await axios.get(`/pms/arrivals?start_date=${today}&end_date=${today}`);

      const bookingsData = response.data?.bookings || [];
      setArrivals(bookingsData);

      if (bookingsData.length === 0) {
        loadUpcomingArrivals();
      } else {
        setUpcoming([]);
      }
    } catch (error) {
      toast.error('Varış listesi yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  const loadUpcomingArrivals = async () => {
    try {
      const start = new Date();
      start.setDate(start.getDate() + 1);
      const end = new Date();
      end.setDate(end.getDate() + 7);
      const startStr = localISODate(start);
      const endStr = localISODate(end);
      const response = await axios.get(`/pms/arrivals?start_date=${startStr}&end_date=${endStr}&limit=300`);

      const bookingsData = response.data?.bookings || [];

      const grouped = {};
      bookingsData.forEach(b => {
        const day = (b.check_in || '').slice(0, 10);
        if (!day) return;
        if (!grouped[day]) grouped[day] = [];
        grouped[day].push(b);
      });

      const days = Object.keys(grouped).sort().slice(0, 7).map(day => ({
        date: day,
        count: grouped[day].length,
        vip_count: grouped[day].filter(b => b.vip_status || b.tags?.includes('vip')).length,
        group_count: grouped[day].filter(b => b.group_block_id).length,
      }));
      setUpcoming(days);
    } catch (error) {
      setUpcoming([]);
    }
  };

  const formatDay = (iso) => {
    const d = new Date(iso + 'T00:00:00');
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const diff = Math.round((d - today) / (1000 * 60 * 60 * 24));
    const labels = ['Bugün', 'Yarın'];
    const dayName = ['Paz', 'Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt'][d.getDay()];
    if (diff >= 0 && diff < labels.length) return labels[diff];
    return `${dayName} ${d.getDate()}/${d.getMonth() + 1}`;
  };

  const getVIPBadge = (booking) => {
    // Check if guest is VIP (from tags or vip_status)
    if (booking.vip_status || booking.tags?.includes('vip')) {
      return <Badge className="bg-indigo-600">VIP</Badge>;
    }
    return null;
  };

  const getGroupBadge = (booking) => {
    if (booking.group_block_id) {
      return <Badge className="bg-green-600">GROUP</Badge>;
    }
    return null;
  };

  const getOnlineCheckinBadge = (booking) => {
    if (booking.online_checkin_completed) {
      return <Badge className="bg-blue-600">ONLINE CHECK-IN</Badge>;
    }
    return null;
  };

  const assignRoom = async (bookingId) => {
    try {
      // Auto-assign based on preferences
      await axios.post(`/bookings/${bookingId}/assign-room`);
      toast.success('Oda atandı!');
      loadTodayArrivals();
    } catch (error) {
      toast.error('Oda atanamadı');
    }
  };

  const quickCheckIn = async (booking) => {
    if (busyId) return;
    if (!booking.room_id && !booking.room_number) {
      toast.error('Önce oda atayın');
      return;
    }
    const status = (booking.status || '').toLowerCase();
    if (status === 'checked_in') {
      toast.info('Zaten check-in yapılmış');
      return;
    }
    if (!await confirmDialog({ message: `${booking.guest_name || booking.id.slice(0, 8)} için check-in yapılsın mı?` })) return;
    setBusyId(booking.id);
    try {
      await axios.post('/api/pms-core/check-in', { booking_id: booking.id });
      toast.success('Check-in tamamlandı');
      loadTodayArrivals();
    } catch (e) {
      const detail = e.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : detail?.message || detail?.error || 'Check-in başarısız';
      toast.error(msg);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
    <div className="p-6">
      {/* Header */}
      <div className="mb-8">
        <PageHeader
          icon={UserCheck}
          title="Bugünün Varışları"
          subtitle="Bugün check-in yapacak misafirler — VIP, grup ve özel istekler"
          actions={
            <>
              <Button variant="outline" size="sm" onClick={() => navigate('/')}>
                <Home className="w-4 h-4 mr-1.5" /> Ana Sayfa
              </Button>
              <Button variant="outline" size="sm" onClick={loadTodayArrivals} disabled={loading}>
                <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} /> Yenile
              </Button>
            </>
          }
        />
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <KpiCard
          icon={UserCheck}
          intent="info"
          label="Toplam Varış"
          value={arrivals.length}
        />
        <KpiCard
          icon={Crown}
          intent="warning"
          label="VIP Varış"
          value={arrivals.filter(a => a.vip_status || a.tags?.includes('vip')).length}
        />
        <KpiCard
          icon={Users}
          intent="success"
          label="Grup Varış"
          value={arrivals.filter(a => a.group_block_id).length}
        />
        <KpiCard
          icon={Clock}
          intent="neutral"
          label="Online Check-in"
          value={arrivals.filter(a => a.online_checkin_completed).length}
        />
      </div>

      {/* Arrivals List */}
      <div className="space-y-3">
        {loading ? (
          <div className="text-center py-8">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          </div>
        ) : arrivals.length === 0 ? (
          <Card>
            <CardContent className="pt-12 pb-12 text-center">
              <UserCheck className="w-16 h-16 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-600 text-lg font-medium mb-2">Bugün varış yok</p>
              {upcoming.length > 0 ? (
                <>
                  <p className="text-sm text-gray-500 mb-6">Önümüzdeki 7 gün:</p>
                  <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 max-w-4xl mx-auto">
                    {upcoming.map((d) => (
                      <div
                        key={d.date}
                        className="p-3 rounded-lg border bg-white text-left hover:border-blue-400 hover:shadow-sm transition"
                      >
                        <div className="flex items-center gap-1 text-xs text-gray-500 mb-1">
                          <Calendar className="w-3 h-3" />
                          {formatDay(d.date)}
                        </div>
                        <p className="text-2xl font-bold text-blue-600">{d.count}</p>
                        <p className="text-xs text-gray-500">varış</p>
                        {(d.vip_count > 0 || d.group_count > 0) && (
                          <div className="flex gap-1 mt-2 flex-wrap">
                            {d.vip_count > 0 && (
                              <Badge className="bg-indigo-600 text-xs px-1.5 py-0">VIP {d.vip_count}</Badge>
                            )}
                            {d.group_count > 0 && (
                              <Badge className="bg-green-600 text-xs px-1.5 py-0">Grup {d.group_count}</Badge>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <p className="text-sm text-gray-500">Önümüzdeki 7 günde de varış yok</p>
              )}
            </CardContent>
          </Card>
        ) : (
          arrivals.map((booking) => (
            <Card key={booking.id} className={`border-l-4 ${
              booking.vip_status ? 'border-indigo-500 bg-indigo-50' :
              booking.group_block_id ? 'border-green-500 bg-green-50' :
              'border-blue-500'
            }`}>
              <CardContent className="pt-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <h3 className="text-lg font-bold">Booking #{booking.id.substring(0, 8).toUpperCase()}</h3>
                      {getVIPBadge(booking)}
                      {getGroupBadge(booking)}
                      {getOnlineCheckinBadge(booking)}
                    </div>
                    
                    <div className="grid grid-cols-3 gap-4 text-sm">
                      <div>
                        <p className="text-gray-500">Check-in Time</p>
                        <p className="font-semibold">
                          {booking.estimated_arrival_time || '14:00'}
                        </p>
                      </div>
                      <div>
                        <p className="text-gray-500">Adults / Children</p>
                        <p className="font-semibold">{booking.adults} / {booking.children}</p>
                      </div>
                      <div>
                        <p className="text-gray-500">Nights</p>
                        <p className="font-semibold">
                          {Math.ceil((new Date(booking.check_out) - new Date(booking.check_in)) / (1000 * 60 * 60 * 24))}
                        </p>
                      </div>
                    </div>

                    {booking.special_requests && (
                      <div className="mt-3 p-3 bg-yellow-50 rounded-lg border border-yellow-200">
                        <p className="text-sm">
                          <strong>⚠️ Özel İstek:</strong> {booking.special_requests}
                        </p>
                      </div>
                    )}

                    {booking.online_checkin_completed && (
                      <div className="mt-2">
                        <p className="text-xs text-blue-600">
                          ✅ Online check-in tamamlanmış - Express check-in hazır
                        </p>
                      </div>
                    )}
                  </div>

                  <div className="ml-4 text-right">
                    {booking.room_number ? (
                      <div className="mb-3">
                        <p className="text-xs text-gray-500">Oda</p>
                        <p className="text-2xl font-bold text-green-600">{booking.room_number}</p>
                      </div>
                    ) : (
                      <Button 
                        size="sm" 
                        onClick={() => assignRoom(booking.id)}
                        className="mb-3"
                      >
                        <BedDouble className="w-4 h-4 mr-2" />
                        Oda Ata
                      </Button>
                    )}
                    {(booking.status || '').toLowerCase() !== 'checked_in' && (
                      <div className="flex flex-col gap-2 mb-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="border-indigo-300 text-indigo-700 hover:bg-indigo-50"
                          onClick={() => setScanBookingId(booking.id)}
                          data-testid={`btn-scan-arrival-${booking.id}`}
                        >
                          <ScanLine className="w-4 h-4 mr-2" />
                          Kimlik Tara
                        </Button>
                        <IdPhotoViewerButton
                          bookingId={booking.id}
                          guestName={booking.guest_name}
                          user={user}
                          onlineCheckinCompleted={booking.online_checkin_completed}
                          idPhotoUploaded={booking.online_checkin_id_photo_uploaded}
                        />
                        <Button
                          size="sm"
                          className="bg-green-600 hover:bg-green-700"
                          disabled={busyId === booking.id || (!booking.room_id && !booking.room_number)}
                          onClick={() => quickCheckIn(booking)}
                        >
                          <LogIn className="w-4 h-4 mr-2" />
                          {busyId === booking.id ? 'İşleniyor…' : 'Hızlı Check-in'}
                        </Button>
                      </div>
                    )}
                    <p className="text-lg font-semibold">€{booking.total_amount}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
    <QuickIdScanDialog
      open={!!scanBookingId}
      onClose={() => setScanBookingId(null)}
      onExtracted={(doc) => { if (scanBookingId) applyScanToBooking(scanBookingId, doc); }}
    />
    </>
  );
};

export default ArrivalList;
