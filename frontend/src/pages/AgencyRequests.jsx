import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { 
  Building2, 
  Calendar, 
  Users, 
  DollarSign, 
  Clock, 
  CheckCircle, 
  XCircle, 
  AlertCircle,
  Loader2,
  Phone,
  Mail,
  Bed
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';

const AgencyRequests = () => {
  const { t } = useTranslation();
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedRequest, setSelectedRequest] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');

  useEffect(() => {
    loadRequests();
  }, [filterStatus]);

  const loadRequests = async () => {
    try {
      setLoading(true);
      const params = filterStatus !== 'all' ? { status: filterStatus } : {};
      const response = await axios.get('/hotel/booking-requests', { params });
      setRequests(response.data.items || []);
    } catch (error) {
      console.error('Failed to load agency requests:', error);
      toast.error('Acenta talepleri yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (requestId) => {
    if (!confirm('Bu talebi onaylamak istediğinize emin misiniz?\n\nOnaylandığında otomatik olarak rezervasyon oluşturulacaktır.')) {
      return;
    }

    try {
      setActionLoading(true);
      const response = await axios.post(`/hotel/booking-requests/${requestId}/approve`);
      
      toast.success('Talep onaylandı! Rezervasyon oluşturuldu.');
      
      // Refresh list
      await loadRequests();
      
      // Close detail modal
      setSelectedRequest(null);
    } catch (error) {
      console.error('Approve failed:', error);
      const message = error.response?.data?.detail || 'Talep onaylanamadı';
      toast.error(message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async () => {
    if (!rejectReason.trim() || rejectReason.trim().length < 5) {
      toast.error('Red nedeni en az 5 karakter olmalıdır');
      return;
    }

    try {
      setActionLoading(true);
      await axios.post(`/hotel/booking-requests/${selectedRequest.request_id}/reject`, {
        reason: rejectReason.trim()
      });
      
      toast.success('Talep reddedildi');
      
      // Refresh list
      await loadRequests();
      
      // Close modals
      setRejectModalOpen(false);
      setSelectedRequest(null);
      setRejectReason('');
    } catch (error) {
      console.error('Reject failed:', error);
      const message = error.response?.data?.detail || 'Talep reddedilemedi';
      toast.error(message);
    } finally {
      setActionLoading(false);
    }
  };

  const getStatusBadge = (status) => {
    const variants = {
      'submitted': { color: 'bg-yellow-100 text-yellow-800', icon: AlertCircle, text: 'Yeni Talep' },
      'hotel_review': { color: 'bg-blue-100 text-blue-800', icon: Clock, text: 'İnceleniyor' },
      'approved': { color: 'bg-green-100 text-green-800', icon: CheckCircle, text: 'Onaylandı' },
      'rejected': { color: 'bg-red-100 text-red-800', icon: XCircle, text: 'Reddedildi' },
      'expired': { color: 'bg-gray-100 text-gray-800', icon: Clock, text: 'Süresi Doldu' },
      'cancelled': { color: 'bg-gray-100 text-gray-800', icon: XCircle, text: 'İptal Edildi' },
    };

    const config = variants[status] || variants.submitted;
    const Icon = config.icon;

    return (
      <Badge className={`${config.color} flex items-center gap-1`}>
        <Icon className="w-3 h-3" />
        {config.text}
      </Badge>
    );
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('tr-TR', { day: '2-digit', month: 'short', year: 'numeric' });
  };

  const formatDateTime = (dateStr) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString('tr-TR', { 
      day: '2-digit', 
      month: 'short', 
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const calculateNights = (checkIn, checkOut) => {
    const ci = new Date(checkIn);
    const co = new Date(checkOut);
    return Math.ceil((co - ci) / (1000 * 60 * 60 * 24));
  };

  const pendingRequests = requests.filter(r => ['submitted', 'hotel_review'].includes(r.status));

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-3">
              <Building2 className="w-8 h-8 text-blue-600" />
              Acenta Talepleri
            </h1>
            <p className="text-gray-600 mt-2">
              Acentalardan gelen rezervasyon taleplerini inceleyin ve onaylayın
            </p>
          </div>
          
          {pendingRequests.length > 0 && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-2">
              <p className="text-yellow-800 font-semibold">
                {pendingRequests.length} Bekleyen Talep
              </p>
            </div>
          )}
        </div>

        {/* Filters */}
        <div className="flex gap-2 flex-wrap">
          {['all', 'submitted', 'hotel_review', 'approved', 'rejected', 'expired'].map((status) => (
            <Button
              key={status}
              variant={filterStatus === status ? 'default' : 'outline'}
              size="sm"
              onClick={() => setFilterStatus(status)}
            >
              {status === 'all' && 'Tümü'}
              {status === 'submitted' && 'Yeni'}
              {status === 'hotel_review' && 'İnceleniyor'}
              {status === 'approved' && 'Onaylı'}
              {status === 'rejected' && 'Reddedildi'}
              {status === 'expired' && 'Süresi Dolmuş'}
            </Button>
          ))}
        </div>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
        </div>
      )}

      {/* Empty State */}
      {!loading && requests.length === 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <Building2 className="w-16 h-16 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-900 mb-2">
            Henüz Talep Yok
          </h3>
          <p className="text-gray-600">
            {filterStatus === 'all' 
              ? 'Acentalardan gelen talepler burada görünecek'
              : 'Bu filtrede talep bulunamadı'}
          </p>
        </div>
      )}

      {/* Requests Grid */}
      {!loading && requests.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {requests.map((request) => (
            <div
              key={request.request_id}
              className="bg-white rounded-lg border border-gray-200 p-5 hover:shadow-lg transition-shadow cursor-pointer"
              onClick={() => setSelectedRequest(request)}
            >
              {/* Status Badge */}
              <div className="flex items-center justify-between mb-4">
                {getStatusBadge(request.status)}
                <span className="text-xs text-gray-500">
                  {formatDateTime(request.created_at)}
                </span>
              </div>

              {/* Customer Info */}
              <div className="mb-4">
                <h3 className="font-semibold text-gray-900 text-lg mb-1">
                  {request.customer_name}
                </h3>
                <p className="text-sm text-gray-600 flex items-center gap-1">
                  <Phone className="w-3 h-3" />
                  {request.customer_phone}
                </p>
              </div>

              {/* Booking Details */}
              <div className="space-y-2 mb-4">
                <div className="flex items-center gap-2 text-sm">
                  <Calendar className="w-4 h-4 text-gray-400" />
                  <span className="text-gray-700">
                    {formatDate(request.check_in)} - {formatDate(request.check_out)}
                  </span>
                  <span className="text-gray-500">({request.nights} gece)</span>
                </div>
                
                <div className="flex items-center gap-2 text-sm">
                  <Bed className="w-4 h-4 text-gray-400" />
                  <span className="text-gray-700">{request.room_type_id}</span>
                </div>

                <div className="flex items-center gap-2 text-sm">
                  <Users className="w-4 h-4 text-gray-400" />
                  <span className="text-gray-700">
                    {request.adults} Yetişkin
                    {request.children > 0 && `, ${request.children} Çocuk`}
                  </span>
                </div>
              </div>

              {/* Pricing */}
              <div className="border-t border-gray-100 pt-3">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-sm text-gray-600">Toplam Tutar:</span>
                  <span className="text-lg font-bold text-gray-900">
                    {request.total_price.toLocaleString('tr-TR')} {request.currency}
                  </span>
                </div>
                <div className="flex justify-between items-center text-xs">
                  <span className="text-gray-500">Komisyon (%{request.commission_pct}):</span>
                  <span className="text-red-600 font-semibold">
                    -{request.commission_amount.toLocaleString('tr-TR')} {request.currency}
                  </span>
                </div>
                <div className="flex justify-between items-center text-xs mt-1 pt-1 border-t">
                  <span className="text-gray-700 font-medium">Net Tutar:</span>
                  <span className="text-green-600 font-bold">
                    {request.net_to_hotel.toLocaleString('tr-TR')} {request.currency}
                  </span>
                </div>
              </div>

              {/* Actions */}
              {['submitted', 'hotel_review'].includes(request.status) && (
                <div className="mt-4 flex gap-2">
                  <Button
                    size="sm"
                    className="flex-1 bg-green-600 hover:bg-green-700"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleApprove(request.request_id);
                    }}
                  >
                    <CheckCircle className="w-4 h-4 mr-1" />
                    Onayla
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    className="flex-1"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedRequest(request);
                      setRejectModalOpen(true);
                    }}
                  >
                    <XCircle className="w-4 h-4 mr-1" />
                    Reddet
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Detail Modal */}
      {selectedRequest && !rejectModalOpen && (
        <Dialog open={!!selectedRequest} onOpenChange={() => setSelectedRequest(null)}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                Talep Detayı
                {getStatusBadge(selectedRequest.status)}
              </DialogTitle>
              <DialogDescription>
                Talep ID: {selectedRequest.request_id.substring(0, 8)}...
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-6">
              {/* Customer Info */}
              <div className="bg-gray-50 rounded-lg p-4">
                <h3 className="font-semibold text-gray-900 mb-3">Müşteri Bilgileri</h3>
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Users className="w-4 h-4 text-gray-400" />
                    <span className="text-gray-700">{selectedRequest.customer_name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Phone className="w-4 h-4 text-gray-400" />
                    <span className="text-gray-700">{selectedRequest.customer_phone}</span>
                  </div>
                  {selectedRequest.customer_email && (
                    <div className="flex items-center gap-2">
                      <Mail className="w-4 h-4 text-gray-400" />
                      <span className="text-gray-700">{selectedRequest.customer_email}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Booking Details */}
              <div className="bg-blue-50 rounded-lg p-4">
                <h3 className="font-semibold text-gray-900 mb-3">Rezervasyon Detayları</h3>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-gray-600 mb-1">Giriş Tarihi</p>
                    <p className="font-medium">{formatDate(selectedRequest.check_in)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-600 mb-1">Çıkış Tarihi</p>
                    <p className="font-medium">{formatDate(selectedRequest.check_out)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-600 mb-1">Gece Sayısı</p>
                    <p className="font-medium">{selectedRequest.nights} gece</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-600 mb-1">Misafir</p>
                    <p className="font-medium">
                      {selectedRequest.adults} Yetişkin
                      {selectedRequest.children > 0 && `, ${selectedRequest.children} Çocuk`}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-600 mb-1">Oda Tipi</p>
                    <p className="font-medium">{selectedRequest.room_type_id}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-600 mb-1">Fiyat Planı</p>
                    <p className="font-medium">{selectedRequest.rate_plan_id}</p>
                  </div>
                </div>
              </div>

              {/* Pricing Breakdown */}
              <div className="bg-green-50 rounded-lg p-4">
                <h3 className="font-semibold text-gray-900 mb-3">Fiyatlandırma</h3>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Gecelik Fiyat:</span>
                    <span className="font-medium">
                      {selectedRequest.price_per_night.toLocaleString('tr-TR')} {selectedRequest.currency}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Toplam ({selectedRequest.nights} gece):</span>
                    <span className="font-medium">
                      {selectedRequest.total_price.toLocaleString('tr-TR')} {selectedRequest.currency}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm border-t pt-2">
                    <span className="text-red-600">Acenta Komisyonu (%{selectedRequest.commission_pct}):</span>
                    <span className="text-red-600 font-semibold">
                      -{selectedRequest.commission_amount.toLocaleString('tr-TR')} {selectedRequest.currency}
                    </span>
                  </div>
                  <div className="flex justify-between text-lg font-bold border-t pt-2">
                    <span className="text-green-700">Net Otel Geliri:</span>
                    <span className="text-green-700">
                      {selectedRequest.net_to_hotel.toLocaleString('tr-TR')} {selectedRequest.currency}
                    </span>
                  </div>
                </div>
              </div>

              {/* Availability & Restrictions Snapshot */}
              <div className="bg-purple-50 rounded-lg p-4">
                <h3 className="font-semibold text-gray-900 mb-3">Talep Anındaki Durum</h3>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-gray-600">Müsait Oda:</p>
                    <p className="font-medium">
                      {selectedRequest.availability_at_request.available_rooms} oda
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-600">Kontrol Zamanı:</p>
                    <p className="font-medium text-xs">
                      {formatDateTime(selectedRequest.availability_at_request.checked_at)}
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-600">Min Konaklama:</p>
                    <p className="font-medium">
                      {selectedRequest.restrictions_snapshot.min_stay} gece
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-600">Satış Durumu:</p>
                    <p className={`font-medium ${selectedRequest.restrictions_snapshot.stop_sell ? 'text-red-600' : 'text-green-600'}`}>
                      {selectedRequest.restrictions_snapshot.stop_sell ? 'Satışa Kapalı' : 'Satışta'}
                    </p>
                  </div>
                </div>
              </div>

              {/* Timeline */}
              {selectedRequest.audit_events && selectedRequest.audit_events.length > 0 && (
                <div className="bg-gray-50 rounded-lg p-4">
                  <h3 className="font-semibold text-gray-900 mb-3">Talep Geçmişi</h3>
                  <div className="space-y-2">
                    {selectedRequest.audit_events.map((event, idx) => (
                      <div key={idx} className="flex items-start gap-3 text-sm">
                        <div className="w-2 h-2 rounded-full bg-blue-600 mt-1.5"></div>
                        <div className="flex-1">
                          <p className="font-medium text-gray-900 capitalize">
                            {event.event.replace('_', ' ')}
                          </p>
                          <p className="text-xs text-gray-500">
                            {formatDateTime(event.timestamp)} - {event.actor_type}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Resolution Notes */}
              {selectedRequest.resolution_notes && (
                <div className="bg-red-50 rounded-lg p-4 border border-red-200">
                  <h3 className="font-semibold text-red-900 mb-2">Red Nedeni</h3>
                  <p className="text-sm text-red-800">{selectedRequest.resolution_notes}</p>
                </div>
              )}

              {/* Booking Link */}
              {selectedRequest.booking_id && (
                <div className="bg-green-50 rounded-lg p-4 border border-green-200">
                  <h3 className="font-semibold text-green-900 mb-2">Oluşturulan Rezervasyon</h3>
                  <p className="text-sm text-green-800">
                    Rezervasyon ID: {selectedRequest.booking_id.substring(0, 12)}...
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="mt-2"
                    onClick={() => window.open(`/pms?booking_id=${selectedRequest.booking_id}`, '_blank')}
                  >
                    Rezervasyonu Görüntüle
                  </Button>
                </div>
              )}
            </div>

            {/* Actions */}
            {['submitted', 'hotel_review'].includes(selectedRequest.status) && (
              <DialogFooter className="border-t pt-4">
                <Button
                  variant="outline"
                  onClick={() => setSelectedRequest(null)}
                  disabled={actionLoading}
                >
                  Kapat
                </Button>
                <Button
                  variant="destructive"
                  onClick={() => setRejectModalOpen(true)}
                  disabled={actionLoading}
                >
                  <XCircle className="w-4 h-4 mr-2" />
                  Reddet
                </Button>
                <Button
                  className="bg-green-600 hover:bg-green-700"
                  onClick={() => handleApprove(selectedRequest.request_id)}
                  disabled={actionLoading}
                >
                  {actionLoading ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      İşleniyor...
                    </>
                  ) : (
                    <>
                      <CheckCircle className="w-4 h-4 mr-2" />
                      Onayla ve Rezervasyon Oluştur
                    </>
                  )}
                </Button>
              </DialogFooter>
            )}
          </DialogContent>
        </Dialog>
      )}

      {/* Reject Modal */}
      <Dialog open={rejectModalOpen} onOpenChange={setRejectModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Talebi Reddet</DialogTitle>
            <DialogDescription>
              Lütfen red nedenini belirtin (minimum 5 karakter)
            </DialogDescription>
          </DialogHeader>

          <div className="py-4">
            <Textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Örn: Seçilen tarihlerde müsaitlik yok, Fiyat uyuşmazlığı, vb."
              rows={4}
              className="w-full"
            />
            <p className="text-xs text-gray-500 mt-2">
              {rejectReason.length} / 500 karakter
            </p>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setRejectModalOpen(false);
                setRejectReason('');
              }}
              disabled={actionLoading}
            >
              İptal
            </Button>
            <Button
              variant="destructive"
              onClick={handleReject}
              disabled={actionLoading || rejectReason.trim().length < 5}
            >
              {actionLoading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Reddediliyor...
                </>
              ) : (
                'Reddet'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AgencyRequests;
