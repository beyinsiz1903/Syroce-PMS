import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import IdPhotoViewerButton from '@/components/IdPhotoViewerButton';

const API_URL = import.meta.env.VITE_BACKEND_URL || '';

const EnhancedFrontDesk = () => {
  const { t } = useTranslation();
  const [arrivals, setArrivals] = useState([]);
  const [showPassportScan, setShowPassportScan] = useState(false);
  const [showWalkIn, setShowWalkIn] = useState(false);
  const [selectedGuest, setSelectedGuest] = useState(null);
  const [guestAlerts, setGuestAlerts] = useState([]);

  useEffect(() => {
    fetchTodayArrivals();
  }, []);

  const fetchTodayArrivals = async () => {
    try {
      const token = localStorage.getItem('token');
      const today = new Date().toISOString().split('T')[0];
      
      const response = await axios.get(
        `/bookings?check_in=${today}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setArrivals(response.data.bookings || []);
    } catch (error) {
      console.error('Error fetching arrivals:', error);
    }
  };

  const fetchGuestAlerts = async (guestId) => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(
        `/frontdesk/guest-alerts/${guestId}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setGuestAlerts(response.data.alerts || []);
    } catch (error) {
      console.error('Error fetching guest alerts:', error);
    }
  };

  const handlePassportScan = async (imageBase64, bookingId) => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.post(
        `/frontdesk/passport-scan`,
        { image_base64: imageBase64, booking_id: bookingId },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success(t('frontDeskEnhanced.toasts.passportScanned'));
      return response.data.extracted_data;
    } catch (error) {
      console.error('Error scanning passport:', error);
      toast.error(t('frontDeskEnhanced.toasts.passportFailed'));
    }
  };

  const handleWalkInBooking = async (formData) => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.post(
        `/frontdesk/walk-in-booking`,
        formData,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success(t('frontDeskEnhanced.toasts.walkInCreated', { folio: response.data.folio_number }));
      setShowWalkIn(false);
      fetchTodayArrivals();
    } catch (error) {
      console.error('Error creating walk-in:', error);
      toast.error(t('frontDeskEnhanced.toasts.walkInFailed'));
    }
  };

  const handleQuickCheckin = async (bookingId) => {
    try {
      const token = localStorage.getItem('token');
      await axios.post(
        `/mobile/staff/quick-checkin`,
        { booking_id: bookingId },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success(t('frontDeskEnhanced.toasts.checkedIn'));
      fetchTodayArrivals();
    } catch (error) {
      console.error('Error checking in:', error);
      toast.error(t('frontDeskEnhanced.toasts.checkinFailed'));
    }
  };

  return (
    <div className="p-6 bg-white">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">{t('frontDeskEnhanced.title')}</h1>
        <div className="flex gap-4">
          <button
            onClick={() => setShowPassportScan(true)}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2"
          >
            📷 {t('frontDeskEnhanced.scanPassport')}
          </button>
          <button
            onClick={() => setShowWalkIn(true)}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 flex items-center gap-2"
          >
            🚶 {t('frontDeskEnhanced.walkInBooking')}
          </button>
        </div>
      </div>

      {/* Today's Arrivals */}
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-4">{t('frontDeskEnhanced.todayArrivals', { count: arrivals.length })}</h2>
        <div className="space-y-4">
          {arrivals.map(booking => (
            <div key={booking.id} className="border rounded-lg p-4 hover:shadow-lg transition-shadow">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center gap-4 mb-2">
                    <h3 className="text-lg font-semibold">{booking.guest_name || t('frontDeskEnhanced.guest')}</h3>
                    <span className={`px-3 py-1 rounded-full text-sm ${
                      booking.status === 'confirmed' ? 'bg-yellow-100 text-yellow-800' :
                      booking.status === 'checked_in' ? 'bg-green-100 text-green-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {booking.status}
                    </span>
                  </div>
                  <div className="text-gray-600 space-y-1">
                    <div>📧 {booking.guest_email}</div>
                    <div>🛏️ {t('frontDeskEnhanced.room')} {booking.room_number || t('frontDeskEnhanced.tba')}</div>
                    <div>👥 {t('frontDeskEnhanced.adultsChildren', { adults: booking.adults, children: booking.children })}</div>
                    <div>💰 ${booking.total_amount}</div>
                  </div>
                </div>
                <div className="flex flex-col gap-2">
                  <button
                    onClick={() => {
                      setSelectedGuest(booking);
                      fetchGuestAlerts(booking.guest_id);
                    }}
                    className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700"
                  >
                    🔔 {t('frontDeskEnhanced.alerts')}
                  </button>
                  <IdPhotoViewerButton
                    bookingId={booking.id}
                    guestName={booking.guest_name}
                    onlineCheckinCompleted={booking.online_checkin_completed}
                    idPhotoUploaded={booking.online_checkin_id_photo_uploaded}
                  />
                  {booking.status === 'confirmed' && (
                    <button
                      onClick={() => handleQuickCheckin(booking.id)}
                      className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
                    >
                      ✓ {t('frontDeskEnhanced.quickCheckin')}
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Guest Alerts Modal */}
      {selectedGuest && guestAlerts.length > 0 && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-[600px] max-h-[80vh] overflow-y-auto">
            <h3 className="text-xl font-bold mb-4">{t('frontDeskEnhanced.guestAlertsTitle', { name: selectedGuest.guest_name })}</h3>
            <div className="space-y-3">
              {guestAlerts.map((alert, idx) => (
                <div key={idx} className={`p-4 rounded-lg border-l-4 ${
                  alert.priority === 'urgent' ? 'border-red-500 bg-red-50' :
                  alert.priority === 'high' ? 'border-orange-500 bg-orange-50' :
                  'border-blue-500 bg-blue-50'
                }`}>
                  <div className="flex items-start gap-3">
                    <span className="text-2xl">{alert.icon}</span>
                    <div className="flex-1">
                      <h4 className="font-semibold">{alert.title}</h4>
                      <p className="text-gray-700 mt-1">{alert.description}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <button
              onClick={() => setSelectedGuest(null)}
              className="mt-4 px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300 w-full"
            >
              {t('frontDeskEnhanced.close')}
            </button>
          </div>
        </div>
      )}

      {/* Walk-in Booking Modal */}
      {showWalkIn && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-[600px]">
            <h3 className="text-xl font-bold mb-4">{t('frontDeskEnhanced.walkInModal.title')}</h3>
            <form onSubmit={(e) => {
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
        </div>
      )}
    </div>
  );
};

export default EnhancedFrontDesk;
