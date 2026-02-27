import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Home, UserCheck, Crown, Users, Clock, BedDouble, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

const ArrivalList = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [arrivals, setArrivals] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadTodayArrivals();
  }, []);

  const loadTodayArrivals = async () => {
    setLoading(true);
    try {
      const today = new Date().toISOString().split('T')[0];
      const response = await axios.get(`/pms/bookings?start_date=${today}&end_date=${today}&status=confirmed,guaranteed`);
      
      // Get bookings arriving today
      const bookingsData = Array.isArray(response.data) ? response.data : response.data.bookings || [];
      setArrivals(bookingsData);
    } catch (error) {
      toast.error('Varış listesi yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  const getVIPBadge = (booking) => {
    // Check if guest is VIP (from tags or vip_status)
    if (booking.vip_status || booking.tags?.includes('vip')) {
      return <Badge className="bg-purple-600">VIP</Badge>;
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

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button 
              variant="outline" 
              size="icon"
              onClick={() => navigate('/')}
              className="hover:bg-green-50"
            >
              <Home className="w-5 h-5" />
            </Button>
            <div>
              <h1 className="text-3xl font-bold text-gray-900">
                📋 Bugünün Varışları ({t('dashboard.arrivalList')})
              </h1>
              <p className="text-gray-600">
                Bugün check-in yapacak misafirler - VIP, grup ve özel istekler
              </p>
            </div>
          </div>
          <Button onClick={loadTodayArrivals} disabled={loading}>
            🔄 Yenile
          </Button>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-6 text-center">
            <UserCheck className="w-8 h-8 text-blue-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">{arrivals.length}</p>
            <p className="text-sm text-gray-500">Toplam Varış</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <Crown className="w-8 h-8 text-purple-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">
              {arrivals.filter(a => a.vip_status || a.tags?.includes('vip')).length}
            </p>
            <p className="text-sm text-gray-500">VIP Varış</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <Users className="w-8 h-8 text-green-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">
              {arrivals.filter(a => a.group_block_id).length}
            </p>
            <p className="text-sm text-gray-500">Grup Varış</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <Clock className="w-8 h-8 text-orange-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">
              {arrivals.filter(a => a.online_checkin_completed).length}
            </p>
            <p className="text-sm text-gray-500">Online Check-in</p>
          </CardContent>
        </Card>
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
              <p className="text-gray-600">Bugün varış yok</p>
            </CardContent>
          </Card>
        ) : (
          arrivals.map((booking) => (
            <Card key={booking.id} className={`border-l-4 ${
              booking.vip_status ? 'border-purple-500 bg-purple-50' :
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
                    <p className="text-lg font-semibold">€{booking.total_amount}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
};

export default ArrivalList;
