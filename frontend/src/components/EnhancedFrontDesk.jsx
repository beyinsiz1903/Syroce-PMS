import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import IdPhotoViewerButton from '@/components/IdPhotoViewerButton';
import { performCheckin } from '@/utils/offlineCheckin';
const API_URL = import.meta.env.VITE_BACKEND_URL || '';
const EnhancedFrontDesk = () => {
  const {
    t
  } = useTranslation();
  const [arrivals, setArrivals] = useState([]);
  const [showPassportScan, setShowPassportScan] = useState(false);
  const [showWalkIn, setShowWalkIn] = useState(false);
  const [selectedGuest, setSelectedGuest] = useState(null);
  const [guestAlerts, setGuestAlerts] = useState([]);
  const [overbookingSolutions, setOverbookingSolutions] = useState([]);
  const [overbookingLoaded, setOverbookingLoaded] = useState(false);
  const [applyingBookingId, setApplyingBookingId] = useState(null);
  useEffect(() => {
    fetchTodayArrivals();
    fetchOverbookingSolutions();
  }, []);
  const fetchOverbookingSolutions = async () => {
    try {
      const today = new Date().toISOString().split('T')[0];
      const response = await axios.post(`/ai/solve-overbooking?date=${today}`);
      // API returns solutions already sorted by priority_score descending.
      setOverbookingSolutions(response.data.solutions || []);
    } catch (error) {
      console.error('Error fetching overbooking solutions:', error);
    } finally {
      setOverbookingLoaded(true);
    }
  };
  const handleApplyOverbookingMove = async sol => {
    if (!sol.booking_id || !sol.recommended_room_id) {
      toast.error(t('frontDeskEnhanced.overbooking.applyFailed'));
      return;
    }
    setApplyingBookingId(sol.booking_id);
    try {
      await axios.post(`/frontdesk/v2/room-move`, {
        booking_id: sol.booking_id,
        new_room_id: sol.recommended_room_id,
        reason: 'overbooking_resolution'
      }, {
        headers: {}
      });
      toast.success(t('frontDeskEnhanced.overbooking.applied', {
        to: sol.recommended_room
      }));
      await fetchOverbookingSolutions();
    } catch (error) {
      console.error('Error applying overbooking move:', error);
      toast.error(t('frontDeskEnhanced.overbooking.applyFailed'));
    } finally {
      setApplyingBookingId(null);
    }
  };
  const tierBadgeClass = tier => {
    switch (tier) {
      case 'vip':
        return 'bg-amber-100 text-amber-800 border border-amber-300';
      case 'gold':
        return 'bg-yellow-100 text-yellow-800 border border-yellow-300';
      case 'silver':
        return 'bg-gray-100 text-gray-700 border border-gray-300';
      default:
        return 'bg-blue-100 text-blue-800 border border-blue-300';
    }
  };
  const tierLabel = tier => t(`frontDeskEnhanced.overbooking.tier.${tier}`, {
    defaultValue: tier
  });
  const fetchTodayArrivals = async () => {
    try {
      const today = new Date().toISOString().split('T')[0];
      const response = await axios.get(`/bookings?check_in=${today}`, {
        headers: {}
      });
      setArrivals(response.data.bookings || []);
    } catch (error) {
      console.error('Error fetching arrivals:', error);
    }
  };
  const fetchGuestAlerts = async guestId => {
    try {
      const response = await axios.get(`/frontdesk/guest-alerts/${guestId}`, {
        headers: {}
      });
      setGuestAlerts(response.data.alerts || []);
    } catch (error) {
      console.error('Error fetching guest alerts:', error);
    }
  };
  const handlePassportScan = async (imageBase64, bookingId) => {
    try {
      const response = await axios.post(`/frontdesk/passport-scan`, {
        image_base64: imageBase64,
        booking_id: bookingId
      }, {
        headers: {}
      });
      toast.success(t('frontDeskEnhanced.toasts.passportScanned'));
      return response.data.extracted_data;
    } catch (error) {
      console.error('Error scanning passport:', error);
      toast.error(t('frontDeskEnhanced.toasts.passportFailed'));
    }
  };
  const handleWalkInBooking = async formData => {
    try {
      const response = await axios.post(`/frontdesk/walk-in-booking`, formData, {
        headers: {}
      });
      toast.success(t('frontDeskEnhanced.toasts.walkInCreated', {
        folio: response.data.folio_number
      }));
      setShowWalkIn(false);
      fetchTodayArrivals();
    } catch (error) {
      console.error('Error creating walk-in:', error);
      toast.error(t('frontDeskEnhanced.toasts.walkInFailed'));
    }
  };
  const handleQuickCheckin = async bookingId => {
    try {
      // Cevrimici sicak yol degismeden korunur (regresyon yok); yalniz AG
      // hatasinda performCheckin kuyruga alip otomatik eslestirir.
      const result = await performCheckin(bookingId, {
        onlineRequest: () => axios.post(`/mobile/staff/quick-checkin`, {
          booking_id: bookingId
        }, {
          headers: {}
        })
      });
      if (result.offlineQueued) {
        toast.info(t('frontDeskEnhanced.toasts.checkinQueued', 'Cevrimdisi: check-in kuyruga alindi, baglanti gelince gonderilecek.'));
      } else {
        toast.success(t('frontDeskEnhanced.toasts.checkedIn'));
      }
      fetchTodayArrivals();
    } catch (error) {
      console.error('Error checking in:', error);
      const detail = error.response?.data?.detail;
      const msg = typeof detail === 'object' && detail?.message || (typeof detail === 'string' ? detail : null);
      toast.error(msg || t('frontDeskEnhanced.toasts.checkinFailed'));
    }
  };
  return <div className="p-6 bg-white">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">{t('frontDeskEnhanced.title')}</h1>
        <div className="flex gap-4">
          <button onClick={() => setShowPassportScan(true)} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2">
            {t('frontDeskEnhanced.scanPassport')}
          </button>
          <button onClick={() => setShowWalkIn(true)} className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 flex items-center gap-2">
            {t('frontDeskEnhanced.walkInBooking')}
          </button>
        </div>
      </div>

      {/* Overbooking Suggestions */}
      {overbookingLoaded && <div className="mb-6" data-testid="overbooking-suggestions">
          <h2 className="text-xl font-semibold mb-1">{t('frontDeskEnhanced.overbooking.title')}</h2>
          {overbookingSolutions.length > 0 ? <>
              <p className="text-sm text-gray-500 mb-4">
                {t('frontDeskEnhanced.overbooking.subtitle', {
            count: overbookingSolutions.length
          })}
              </p>
              <div className="space-y-3">
                {overbookingSolutions.map((sol, idx) => <div key={sol.booking_id || idx} data-testid="overbooking-solution" className="border-l-4 border-red-500 bg-red-50 rounded-lg p-4">
                    <div className="flex justify-between items-start gap-4 flex-wrap">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <h3 className="text-lg font-semibold">{sol.guest_name}</h3>
                          <span data-testid="overbooking-loyalty-tier" className={`px-2 py-0.5 rounded-full text-xs font-medium ${tierBadgeClass(sol.loyalty_tier)}`}>
                            {tierLabel(sol.loyalty_tier)}
                          </span>
                        </div>
                        <div className="text-gray-700 text-sm">
                          {t('frontDeskEnhanced.overbooking.move', {
                    from: sol.current_room,
                    to: sol.recommended_room
                  })}
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-2">
                        <span data-testid="overbooking-priority-score" className="px-3 py-1 rounded-full text-sm font-semibold bg-gray-900 text-white whitespace-nowrap">
                          {t('frontDeskEnhanced.overbooking.priority', {
                    score: sol.priority_score
                  })}
                        </span>
                        <button type="button" data-testid="overbooking-apply-move" onClick={() => handleApplyOverbookingMove(sol)} disabled={applyingBookingId === sol.booking_id} className="px-4 py-2 bg-gray-900 text-white rounded-lg hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap">
                          {applyingBookingId === sol.booking_id ? t('frontDeskEnhanced.overbooking.applying') : t('frontDeskEnhanced.overbooking.apply')}
                        </button>
                      </div>
                    </div>
                    {sol.priority_rationale && <div className="mt-2 text-sm text-gray-600">
                        <span className="font-medium">{t('frontDeskEnhanced.overbooking.reasonLabel')}: </span>
                        <span data-testid="overbooking-priority-rationale">{sol.priority_rationale}</span>
                      </div>}
                  </div>)}
              </div>
            </> : <p className="text-sm text-gray-500">{t('frontDeskEnhanced.overbooking.none')}</p>}
        </div>}

      {/* Today's Arrivals */}
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-4">{t('frontDeskEnhanced.todayArrivals', {
          count: arrivals.length
        })}</h2>
        <div className="space-y-4">
          {arrivals.map(booking => <div key={booking.id} data-testid={`fd-arrival-${booking.id}`} className="border rounded-lg p-4 hover:shadow-lg transition-shadow">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center gap-4 mb-2">
                    <h3 className="text-lg font-semibold">{booking.guest_name || t('frontDeskEnhanced.guest')}</h3>
                    <span className={`px-3 py-1 rounded-full text-sm ${booking.status === 'confirmed' ? 'bg-yellow-100 text-yellow-800' : booking.status === 'checked_in' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}`}>
                      {booking.status}
                    </span>
                  </div>
                  <div className="text-gray-600 space-y-1">
                    <div>{booking.guest_email}</div>
                    <div>{t('frontDeskEnhanced.room')} {booking.room_number || t('frontDeskEnhanced.tba')}</div>
                    <div>{t('frontDeskEnhanced.adultsChildren', {
                    adults: booking.adults,
                    children: booking.children
                  })}</div>
                    <div>${booking.total_amount}</div>
                  </div>
                </div>
                <div className="flex flex-col gap-2">
                  <button onClick={() => {
                setSelectedGuest(booking);
                fetchGuestAlerts(booking.guest_id);
              }} className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700">
                    {t('frontDeskEnhanced.alerts')}
                  </button>
                  <IdPhotoViewerButton bookingId={booking.id} guestName={booking.guest_name} onlineCheckinCompleted={booking.online_checkin_completed} idPhotoUploaded={booking.online_checkin_id_photo_uploaded} />
                  {booking.status === 'confirmed' && <button data-testid={`fd-checkin-${booking.id}`} onClick={() => handleQuickCheckin(booking.id)} className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700">
                      {t('frontDeskEnhanced.quickCheckin')}
                    </button>}
                </div>
              </div>
            </div>)}
        </div>
      </div>

      {/* Guest Alerts Modal */}
      {selectedGuest && guestAlerts.length > 0 && <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-[600px] max-h-[80vh] overflow-y-auto">
            <h3 className="text-xl font-bold mb-4">{t('frontDeskEnhanced.guestAlertsTitle', {
            name: selectedGuest.guest_name
          })}</h3>
            <div className="space-y-3">
              {guestAlerts.map((alert, idx) => <div key={idx} className={`p-4 rounded-lg border-l-4 ${alert.priority === 'urgent' ? 'border-red-500 bg-red-50' : alert.priority === 'high' ? 'border-amber-500 bg-amber-50' : 'border-blue-500 bg-blue-50'}`}>
                  <div className="flex items-start gap-3">
                    <span className="text-2xl">{alert.icon}</span>
                    <div className="flex-1">
                      <h4 className="font-semibold">{alert.title}</h4>
                      <p className="text-gray-700 mt-1">{alert.description}</p>
                    </div>
                  </div>
                </div>)}
            </div>
            <button onClick={() => setSelectedGuest(null)} className="mt-4 px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 w-full">
              {t('frontDeskEnhanced.close')}
            </button>
          </div>
        </div>}

      {/* Walk-in Booking Modal */}
      {showWalkIn && <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-[600px]">
            <h3 className="text-xl font-bold mb-4">{t('frontDeskEnhanced.walkInModal.title')}</h3>
            <form onSubmit={e => {
          e.preventDefault();
          const formData = new FormData(e.target);
          handleWalkInBooking({
            guest_name: formData.get('guest_name'),
            guest_phone: formData.get('guest_phone'),
            guest_email: formData.get('guest_email'),
            room_id: formData.get('room_id'),
            nights: parseInt(formData.get('nights')),
            adults: parseInt(formData.get('adults')),
            children: parseInt(formData.get('children') || 0)
          });
        }}>
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div>
                  <label className="block text-sm font-medium mb-2">{t('frontDeskEnhanced.walkInModal.guestName')}</label>
                  <input type="text" name="guest_name" required className="w-full px-4 py-2 border rounded-lg" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">{t('frontDeskEnhanced.walkInModal.phone')}</label>
                  <input type="tel" name="guest_phone" required className="w-full px-4 py-2 border rounded-lg" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">{t('frontDeskEnhanced.walkInModal.email')}</label>
                  <input type="email" name="guest_email" className="w-full px-4 py-2 border rounded-lg" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">{t('frontDeskEnhanced.walkInModal.roomId')}</label>
                  <input type="text" name="room_id" required className="w-full px-4 py-2 border rounded-lg" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">{t('frontDeskEnhanced.walkInModal.nights')}</label>
                  <input type="number" name="nights" defaultValue="1" min="1" required className="w-full px-4 py-2 border rounded-lg" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">{t('frontDeskEnhanced.walkInModal.adults')}</label>
                  <input type="number" name="adults" defaultValue="1" min="1" required className="w-full px-4 py-2 border rounded-lg" />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">{t('frontDeskEnhanced.walkInModal.children')}</label>
                  <input type="number" name="children" defaultValue="0" min="0" className="w-full px-4 py-2 border rounded-lg" />
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => setShowWalkIn(false)} className="px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300">{t('frontDeskEnhanced.walkInModal.cancel')}</button>
                <button type="submit" className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700">{t('frontDeskEnhanced.walkInModal.submit')}</button>
              </div>
            </form>
          </div>
        </div>}
    </div>;
};
export default EnhancedFrontDesk;